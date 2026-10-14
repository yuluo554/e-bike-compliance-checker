"""服务层：编排的**单一事实源**。

CLI 与 GUI（M5）都只经这里的公开函数取数 —— 于是"界面结论 == CLI 结论"
成为**结构性质**而非人工承诺（见 plan/03 §2.2）。

本模块不含判定逻辑，只负责装配顺序：
     定位数据 → 加载 manifest → 版本锚定 → 加载规则包 → 门控 → 判定 → 汇总
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from .engine import matrix, rules as rules_mod, version as version_mod
from .engine.findings import DIMENSION_ORDER, CheckResult, ProfileCheckResult
from .paths import data_dir_candidates, exe_dir, find_data_dir, is_frozen, within
from .profile import Profile, load_profile, profile_from_dict

#: 服务层错误（→ CLI 退出码 2）。
class ServiceError(Exception):
    pass


class DataDirError(ServiceError):
    """找不到可用数据根。"""


def resolve_data_dir(explicit: Optional[str] = None) -> str:
    """定位数据根；失败抛 :class:`DataDirError`（调用方退出码 2）。"""
    found = find_data_dir(explicit=explicit)
    if found:
        return found
    tried = "\n  ".join(data_dir_candidates(explicit=explicit))
    raise DataDirError("找不到数据目录（需含 rules/manifest.json）。已尝试:\n  {0}".format(tried))


def selfcheck(data_dir: Optional[str] = None) -> Dict[str, Any]:
    """自检：数据目录定位 + 规则库加载 + 门控计数 + 冻结态数据目录断言。"""
    resolved = resolve_data_dir(data_dir)
    manifest = rules_mod.load_manifest(resolved)

    per_ruleset: List[Dict[str, Any]] = []
    verified_total = 0
    pending_total = 0
    for entry in manifest.rulesets:
        ruleset = rules_mod.load_ruleset_file(
            os.path.join(resolved, "rules", entry["file"]),
            expect_sha256=entry.get("sha256"),
            scope=entry.get("scope"),
            standard_code=entry.get("standard"),
        )
        verified_total += len(ruleset.rules)
        pending_total += len(ruleset.excluded)
        per_ruleset.append(
            {
                "file": entry["file"],
                "standard": entry["standard"],
                "version_key": entry["version_key"],
                "scope": entry["scope"],
                "verified": len(ruleset.rules),
                "pending": len(ruleset.excluded),
                "excluded_ids": [item.rule_id for item in ruleset.excluded],
            }
        )

    frozen_check: Optional[bool] = None
    if is_frozen():
        # 冻结态专属断言：数据必须随包走，落在 exe 目录内。
        # 非冻结态返回 None（**不是** FAIL），不让源码运行被误判。
        frozen_check = within(resolved, exe_dir())

    return {
        "schema": "ebikecheck.selfcheck/1.0",
        "data_dir": resolved,
        "data_dir_candidates": data_dir_candidates(data_dir),
        "frozen": is_frozen(),
        "data_dir_within_exe_dir": frozen_check,
        "manifest": {
            "path": manifest.path,
            "sha256": manifest.sha256,
            "generated_by": manifest.generated_by,
            "generator_version": manifest.generator_version,
        },
        "rulesets": per_ruleset,
        "verified_total": verified_total,
        "pending_total": pending_total,
        "thresholds": manifest.thresholds,
    }


def _select_scope_entry(
    manifest: rules_mod.Manifest, scope: str, anchor_date: Optional[str]
) -> Optional[Dict[str, Any]]:
    """按作用域选分册条目：取**生效日不晚于锚定日**的最新一版；无则取最早一版。

    ``anchor_date`` 为空（显式 ``--version-of``，无日期可锚定）时取最新一版。
    这样新增电池/充电器标准版本时无需改代码（数据驱动）。
    """
    entries = [item for item in manifest.rulesets if item.get("scope") == scope]
    if not entries:
        return None
    ordered = sorted(entries, key=lambda item: str(item.get("effective_from", "")))
    if not anchor_date:
        return ordered[-1]
    eligible = [item for item in ordered if str(item.get("effective_from", "")) <= anchor_date]
    return eligible[-1] if eligible else ordered[0]


def _applicability(entry: Dict[str, Any], scope: str, anchor_info: Dict[str, Any]) -> Dict[str, Any]:
    """维度适用性：标准生效日 vs 档案锚定日（整车维度恒适用，它是锚定基准）。

    ``basis`` 为日期字段时才比对；显式 ``--version-of``（无日期）视为适用 ——
    用户已显式选择版本，不再用生效日替他做减法。
    """
    if scope == rules_mod.SCOPE_VEHICLE:
        return {"applicable": True, "reason": ""}
    effective = str(entry.get("effective_from", ""))
    basis = anchor_info.get("basis")
    anchor_date = str(anchor_info.get("value") or "")
    if basis not in ("model_design_date", "market_date") or not anchor_date:
        return {
            "applicable": True,
            "reason": "档案未按日期锚定（显式指定版本），按适用处理",
        }
    if effective and anchor_date < effective:
        return {
            "applicable": False,
            "reason": "标准生效日 {0} 晚于档案锚定日 {1}（该标准对本车型尚未生效）".format(
                effective, anchor_date
            ),
        }
    return {"applicable": True, "reason": ""}


def _build_dimension(
    resolved: str,
    manifest: rules_mod.Manifest,
    entry: Dict[str, Any],
    profile: Profile,
    version_key: str,
    anchor_info: Dict[str, Any],
) -> CheckResult:
    """装配单个维度（加载分册 → 门控 → 判定 → 维度元数据）。"""
    ruleset = rules_mod.load_ruleset_by_key(resolved, manifest, entry["version_key"])
    applicability = _applicability(entry, entry["scope"], anchor_info)
    if applicability["applicable"]:
        findings = matrix.check_params(ruleset.effective_rules(), profile.params)
        source_blocks = matrix.collect_source_blocks(ruleset.effective_rules())
    else:
        # 不适用的标准不跑判定（否则会拿"尚未生效"的限值判出不符合）。
        findings = []
        source_blocks = []
    return CheckResult(
        profile_id=profile.profile_id,
        ruleset_file=ruleset.file_name,
        ruleset_sha256=ruleset.sha256,
        version_key=entry["version_key"],
        version_anchor=dict(anchor_info),
        findings=findings,
        excluded_rules=list(ruleset.excluded),
        profile_sha256=profile.sha256,
        source_blocks=source_blocks,
        scope=entry["scope"],
        standard=str(entry.get("standard", "")),
        effective_rule_count=len(ruleset.rules),
        applicability=applicability,
    )


def _assemble(
    resolved: str,
    manifest: rules_mod.Manifest,
    profile: Profile,
    version_key: str,
    anchor_info: Dict[str, Any],
) -> ProfileCheckResult:
    """三维装配：整车（按 version_key）→ 电池 → 充电器（各按作用域取分册）。"""
    anchor_date = (
        str(anchor_info.get("value") or "")
        if anchor_info.get("basis") in ("model_design_date", "market_date")
        else None
    )
    dimensions: List[CheckResult] = []
    for scope in DIMENSION_ORDER:
        if scope == rules_mod.SCOPE_VEHICLE:
            entry = manifest.ruleset_entry(version_key)
        else:
            entry = _select_scope_entry(manifest, scope, anchor_date)
        if entry is None:
            continue
        dimensions.append(
            _build_dimension(resolved, manifest, entry, profile, version_key, anchor_info)
        )
    return ProfileCheckResult(
        profile_id=profile.profile_id,
        profile_sha256=profile.sha256,
        version_key=version_key,
        version_anchor=dict(anchor_info),
        dimensions=dimensions,
    )


def _resolve_version(
    manifest: rules_mod.Manifest, profile: Profile, version_key: Optional[str]
) -> Tuple[str, Dict[str, Any]]:
    """版本锚定（显式优先；无日期报错要求显式指定，**不猜**）。"""
    if version_key:
        known = version_mod.available_version_keys(manifest.version_anchors)
        if version_key not in known:
            raise ServiceError(
                "未知版本键 {0!r}；可用: {1}".format(version_key, ", ".join(known) or "（无）")
            )
        return version_key, {
            "basis": "explicit",
            "value": version_key,
            "rule": "explicit",
            "note": "由 --version-of 显式指定（未按日期锚定）",
        }
    resolved_key, anchor_info = version_mod.anchor_version(profile.raw, manifest.version_anchors)
    if resolved_key == version_mod.AMBIGUOUS:
        fallback = version_mod.default_version_key(manifest.version_anchors)
        raise ServiceError(
            "档案缺少设计/上市日期，无法锚定标准版本；"
            "请显式指定 --version-of（当前生效版本: {0}）".format(fallback or "未知")
        )
    return resolved_key, anchor_info


def check_profile(
    profile_path: str,
    data_dir: Optional[str] = None,
    version_key: Optional[str] = None,
) -> ProfileCheckResult:
    """单车型核查（**三维**）：版本锚定 → 整车/电池/充电器三册各判一次 → 统一结论。

    电池册与充电器册是**独立标准**，各自成维度、各挂自身条款号，不混进整车册；
    统一结论由 :func:`engine.findings.aggregate_overall` 按"最弱优先"聚合。
    """
    resolved = resolve_data_dir(data_dir)
    manifest = rules_mod.load_manifest(resolved)
    profile = load_profile(profile_path)
    return check_profile_obj(profile, resolved, manifest, version_key)


def check_profile_obj(
    profile: Profile,
    resolved: str,
    manifest: rules_mod.Manifest,
    version_key: Optional[str] = None,
) -> ProfileCheckResult:
    """三维核查的内存通路（基准层与测试用；**与 CLI 同一装配**）。"""
    resolved_key, anchor_info = _resolve_version(manifest, profile, version_key)
    return _assemble(resolved, manifest, profile, resolved_key, anchor_info)


def check_profile_dict(
    raw_profile: Dict[str, Any],
    data_dir: Optional[str] = None,
    version_key: Optional[str] = None,
) -> ProfileCheckResult:
    """直接对内存档案做三维核查（基准层不落盘临时文件；与 CLI 同一装配）。"""
    resolved = resolve_data_dir(data_dir)
    manifest = rules_mod.load_manifest(resolved)
    profile = profile_from_dict(raw_profile)
    return check_profile_obj(profile, resolved, manifest, version_key)


def check_profile_all_versions(
    profile_path: str, data_dir: Optional[str] = None
) -> List[Tuple[str, ProfileCheckResult]]:
    """同一档案在两版下各判一次（版本差异对照的数据来源，M4 的 FR-07 用）。

    每个版本下都做完整三维装配（电池/充电器维度在两版下相同）。
    """
    resolved = resolve_data_dir(data_dir)
    manifest = rules_mod.load_manifest(resolved)
    profile = load_profile(profile_path)
    results: List[Tuple[str, ProfileCheckResult]] = []
    for key in version_mod.available_version_keys(manifest.version_anchors):
        anchor_info = {
            "basis": "forced_compare",
            "value": key,
            "rule": "compare",
            "note": "版本差异对照（同档案两版各判一次）",
        }
        results.append((key, _assemble(resolved, manifest, profile, key, anchor_info)))
    return results


def ruleset_overview(data_dir: Optional[str] = None) -> Dict[str, Any]:
    """规则库概览（报告"规则包坐标"与门控"未启用"节的数据来源）。"""
    resolved = resolve_data_dir(data_dir)
    manifest = rules_mod.load_manifest(resolved)
    entries: List[Dict[str, Any]] = []
    for entry in manifest.rulesets:
        ruleset = rules_mod.load_ruleset_file(
            os.path.join(resolved, "rules", entry["file"]),
            expect_sha256=entry.get("sha256"),
        )
        entries.append(
            {
                "file": entry["file"],
                "standard": entry["standard"],
                "standard_title": ruleset.standard.get("title", ""),
                "version_key": entry["version_key"],
                "scope": entry["scope"],
                "effective": len(ruleset.rules),
                "excluded": [item.to_dict() for item in ruleset.excluded],
            }
        )
    return {
        "data_dir": resolved,
        "manifest": {
            "sha256": manifest.sha256,
            "generated_by": manifest.generated_by,
            "generator_version": manifest.generator_version,
        },
        "rulesets": entries,
        "version_anchors": manifest.version_anchors,
        "thresholds": manifest.thresholds,
    }
