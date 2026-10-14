"""服务层：编排的**单一事实源**。

CLI 与 GUI（M5）都只经这里的公开函数取数 —— 于是"界面结论 == CLI 结论"
成为**结构性质**而非人工承诺（见 plan/03 §2.2）。

本模块不含判定逻辑，只负责装配顺序：
     定位数据 → 加载 manifest → 版本锚定 → 加载规则包 → 门控 → 判定 → 汇总
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from .engine import matrix, rules as rules_mod, version as version_mod
from .engine.findings import DIMENSION_ORDER, CheckResult, ProfileCheckResult
from .paths import data_dir_candidates, exe_dir, find_data_dir, is_frozen, within
from .profile import (
    Profile,
    ProfileError,
    load_profile,
    profile_from_dict,
    profile_sha256_of_content,
)

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


# ---- M3-2 批量扫描 + 失败件隔离（FR-09） ----

#: 失败件原因码（运行期外部输入态；plan/02 §5.3 预留的 ``input_required`` 落点）。
FAIL_REASON_UNREADABLE = "unreadable"      # 文件不可读 / 非 UTF-8
FAIL_REASON_BAD_JSON = "bad_json"          # JSON 解析失败
FAIL_REASON_BAD_SCHEMA = "bad_schema"      # 结构校验失败（ProfileError）


def scan_dir(
    directory: str,
    data_dir: Optional[str] = None,
    version_key: Optional[str] = None,
    pattern: str = "*.json",
) -> Dict[str, Any]:
    """批量扫描一个目录下的车型档案（FR-09）。

    纪律：

    - **单件坏格式不中断整批**：异常件单列进 ``failed``（带原因码与错误摘要），
      其余照常核查；``failed`` **不改变退出码语义**（O-5：0/1/2 三语义由
      "判出不符合"决定，失败件与 ``not_provided`` 同为"未判定"）；
    - 失败件（``failed``）与越限件（``findings``）**分列**，不混在一个桶里；
    - 每件结果带档案 sha256（文件级 + 内容级，FR-11 证据链的批量通路）。
    """
    resolved = resolve_data_dir(data_dir)
    manifest = rules_mod.load_manifest(resolved)
    paths = sorted(glob.glob(os.path.join(directory, pattern)))
    scanned: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    results: List[CheckResult] = []
    for path in paths:
        try:
            profile = load_profile(path)
        except json.JSONDecodeError as error:
            failed.append(
                {
                    "path": path,
                    "reason": FAIL_REASON_BAD_JSON,
                    "detail": str(error),
                }
            )
            continue
        except ProfileError as error:
            failed.append(
                {
                    "path": path,
                    "reason": FAIL_REASON_BAD_SCHEMA,
                    "detail": str(error),
                }
            )
            continue
        except UnicodeDecodeError:
            failed.append(
                {
                    "path": path,
                    "reason": FAIL_REASON_UNREADABLE,
                    "detail": "文件不是合法 UTF-8 文本",
                }
            )
            continue
        except OSError as error:
            failed.append(
                {
                    "path": path,
                    "reason": FAIL_REASON_UNREADABLE,
                    "detail": str(error),
                }
            )
            continue
        try:
            result = check_profile_obj(profile, resolved, manifest, version_key)
        except ServiceError as error:
            # 版本锚定失败等档案级语义错误：同样单列，不中断整批。
            failed.append(
                {
                    "path": path,
                    "reason": FAIL_REASON_BAD_SCHEMA,
                    "detail": str(error),
                }
            )
            continue
        results.append(result)
        scanned.append(
            {
                "path": path,
                "profile_id": profile.profile_id,
                "profile_sha256": profile.sha256,
                "profile_content_sha256": profile_sha256_of_content(profile.raw),
                "overall": result.overall(),
                "counts": result.counts(),
            }
        )
    nonpass = [
        {
            "profile_id": item.profile_id,
            "overall": item.overall(),
            "nonpass_params": _nonpass_params(item),
        }
        for item in results
        if item.overall() != "compliant" or _nonpass_params(item)
    ]
    return {
        "schema": "ebikecheck.scan/1.0",
        "directory": directory,
        "pattern": pattern,
        "total": len(paths),
        "scanned": scanned,
        "failed": failed,
        "nonpass": nonpass,
        "overall_counts": _scan_counts(results),
    }


def _nonpass_params(result: CheckResult) -> List[str]:
    """该档案参数级"非通过"参数名清单（口径：``benchmark.cases.observed_nonpass``）。"""
    from .benchmark.cases import observed_nonpass

    return [param for param, _state in observed_nonpass(result)]


def _scan_counts(results: List[CheckResult]) -> Dict[str, int]:
    out: Dict[str, int] = {"compliant": 0, "non_compliant": 0, "other": 0}
    for result in results:
        state = result.overall()
        if state in out:
            out[state] += 1
        else:
            out["other"] += 1
    out["failed_separate"] = 0  # 失败件在 failed 列表单独计数，不混入
    return out


# ---- M3-3 跨轮对账（FR-10） ----


def compare_rounds(
    baseline_dir: str,
    current_dir: str,
    data_dir: Optional[str] = None,
    version_key: Optional[str] = None,
) -> Dict[str, Any]:
    """两轮扫描目录对账（三集合：新增越限 / 已整改 / 持续越限）。

    配对主键 = ``profile_id``（稳定身份键，非内容指纹）；参数级口径单一实现源
    为 ``benchmark.cases.observed_nonpass``（O-12 纪律的 M3 落点）。
    """
    from .engine.reconcile import reconcile_rounds

    baseline_scan = scan_dir(baseline_dir, data_dir, version_key)
    current_scan = scan_dir(current_dir, data_dir, version_key)
    baseline = _results_of_scan(baseline_scan, baseline_dir, data_dir, version_key)
    current = _results_of_scan(current_scan, current_dir, data_dir, version_key)
    reconciliation = reconcile_rounds(baseline, current)
    return {
        "schema": "ebikecheck.reconciliation.report/1.0",
        "baseline_dir": baseline_dir,
        "current_dir": current_dir,
        "reconciliation": reconciliation.to_dict(),
        "baseline_failed": baseline_scan["failed"],
        "current_failed": current_scan["failed"],
    }


def _results_of_scan(
    scan_payload: Dict[str, Any], directory: str, data_dir: Optional[str], version_key: Optional[str]
) -> List[CheckResult]:
    """从扫描 payload 还原逐件 ``CheckResult``（对账复用同一装配，与单件口径同源）。"""
    resolved = resolve_data_dir(data_dir)
    manifest = rules_mod.load_manifest(resolved)
    results: List[CheckResult] = []
    for item in scan_payload.get("scanned", []):
        try:
            profile = load_profile(item["path"])
        except (ProfileError, OSError):
            continue
        try:
            results.append(check_profile_obj(profile, resolved, manifest, version_key))
        except ServiceError:
            continue
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


# ---- M3-4 证据链（FR-11） ----


class TraceabilityError(ServiceError):
    """溯源完整性断言失败（明细与溯源对不上 / 引用 id 不可解析）→ 拒绝交出。"""


def assert_traceability(result: ProfileCheckResult) -> None:
    """溯源完整性硬断言（NFR-10）：导出/交出前必须通过，不满足即拒。

    三条：

    1. **明细行数 == 溯源行数**：每条 finding 必须能在该维度的
       ``source_blocks`` 里按 ``(param, standard)`` 找到来源块；
    2. **引用 id 可解析**：每条 finding 的 ``rule_id`` 必须能在该维度
       ``effective_rules`` 的产物坐标里回查 —— 这里以 ``source_blocks``
       的参数级来源为准（规则 id 与来源块同源于同一分册）；
    3. **指纹在位**：档案 sha256 非空（文件通路加载即有；内存通路显式给出）。
    """
    if not result.profile_sha256:
        raise TraceabilityError(
            "档案 sha256 缺失（证据链断链：结论无法挂到输入指纹）"
        )
    for dimension in result.dimensions:
        blocks = {
            (block.get("param"), block.get("standard"))
            for block in dimension.source_blocks
        }
        for finding in dimension.findings:
            if (finding.param, finding.standard) not in blocks:
                raise TraceabilityError(
                    "溯源完整性失败: 维度 {0} finding {1}（参数 {2}）无对应来源块".format(
                        dimension.scope, finding.rule_id, finding.param
                    )
                )
    if len(result.source_blocks) != sum(
        len(dimension.source_blocks) for dimension in result.dimensions
    ):  # 防御性：并集视图与逐维度之和必须一致（结构性质，正常恒真）
        raise TraceabilityError("溯源完整性失败: 来源块并集视图与逐维度之和不一致")


def evidence_chain(result: ProfileCheckResult) -> Dict[str, Any]:
    """证据链装配（FR-11）：档案 + 报告双 sha256 + 规则包坐标 + 溯源断言。

    - 档案指纹：``profile_sha256``（加载时落定的文件级 sha256）；
    - 报告指纹：对**结果载荷**（``to_dict()``，含全部 findings 与来源块）的
      规范 JSON 取 sha256 —— 报告被改动即可检出；
    - 调用前先跑 :func:`assert_traceability`，断言失败直接抛
      :class:`TraceabilityError`（**拒交出**，不降级为警告）。
    """
    assert_traceability(result)
    from .io_utils import sha256_bytes

    payload = result.to_dict()
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    report_sha256 = sha256_bytes(canonical.encode("utf-8"))
    rulesets = [
        {
            "scope": dimension.scope,
            "standard": dimension.standard,
            "file": dimension.ruleset_file,
            "sha256": dimension.ruleset_sha256,
            "version_key": dimension.version_key,
        }
        for dimension in result.dimensions
    ]
    return {
        "schema": "ebikecheck.evidence/1.0",
        "profile_id": result.profile_id,
        "profile_sha256": result.profile_sha256,
        "report_sha256": report_sha256,
        "rulesets": rulesets,
        "traceability": "ok",
    }
