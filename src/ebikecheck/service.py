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
from .engine.findings import CheckResult
from .paths import data_dir_candidates, exe_dir, find_data_dir, is_frozen, within
from .profile import Profile, load_profile

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


def check_profile(
    profile_path: str,
    data_dir: Optional[str] = None,
    version_key: Optional[str] = None,
) -> CheckResult:
    """单车型核查：版本锚定 → 加载规则包 → 门控 → 判定 → 汇总。"""
    resolved = resolve_data_dir(data_dir)
    manifest = rules_mod.load_manifest(resolved)
    profile = load_profile(profile_path)

    if version_key:
        known = version_mod.available_version_keys(manifest.version_anchors)
        if version_key not in known:
            raise ServiceError(
                "未知版本键 {0!r}；可用: {1}".format(version_key, ", ".join(known) or "（无）")
            )
        anchor_info = {
            "basis": "explicit",
            "value": version_key,
            "rule": "explicit",
            "note": "由 --version-of 显式指定（未按日期锚定）",
        }
    else:
        version_key, anchor_info = version_mod.anchor_version(profile.raw, manifest.version_anchors)
        if version_key == version_mod.AMBIGUOUS:
            fallback = version_mod.default_version_key(manifest.version_anchors)
            raise ServiceError(
                "档案缺少设计/上市日期，无法锚定标准版本；"
                "请显式指定 --version-of（当前生效版本: {0}）".format(fallback or "未知")
            )

    ruleset = rules_mod.load_ruleset_by_key(resolved, manifest, version_key)
    findings = matrix.check_params(ruleset.effective_rules(), profile.params)

    result = CheckResult(
        profile_id=profile.profile_id,
        ruleset_file=ruleset.file_name,
        ruleset_sha256=ruleset.sha256,
        version_key=version_key,
        version_anchor=anchor_info,
        findings=findings,
        excluded_rules=list(ruleset.excluded),
        profile_sha256=profile.sha256,
        source_blocks=matrix.collect_source_blocks(ruleset.effective_rules()),
    )
    return result


def check_profile_all_versions(
    profile_path: str, data_dir: Optional[str] = None
) -> List[Tuple[str, CheckResult]]:
    """同一档案在两版下各判一次（版本差异对照的数据来源，M4 的 FR-07 用）。"""
    resolved = resolve_data_dir(data_dir)
    manifest = rules_mod.load_manifest(resolved)
    profile = load_profile(profile_path)
    results: List[Tuple[str, CheckResult]] = []
    for key in version_mod.available_version_keys(manifest.version_anchors):
        ruleset = rules_mod.load_ruleset_by_key(resolved, manifest, key)
        findings = matrix.check_params(ruleset.effective_rules(), profile.params)
        results.append(
            (
                key,
                CheckResult(
                    profile_id=profile.profile_id,
                    ruleset_file=ruleset.file_name,
                    ruleset_sha256=ruleset.sha256,
                    version_key=key,
                    version_anchor={
                        "basis": "forced_compare",
                        "value": key,
                        "rule": "compare",
                        "note": "版本差异对照（同档案两版各判一次）",
                    },
                    findings=findings,
                    excluded_rules=list(ruleset.excluded),
                    profile_sha256=profile.sha256,
                    source_blocks=matrix.collect_source_blocks(ruleset.effective_rules()),
                ),
            )
        )
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
