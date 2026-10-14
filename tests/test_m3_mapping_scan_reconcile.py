"""M3 测试：字段映射（FR-08）、批量扫描（FR-09）、跨轮对账（FR-10）、证据链（FR-11）。

口径纪律（HANDOFF-M3）：

- 映射引擎走 ``data/mapping/mapping.json`` 同一张表（不另立单位口径）；
- 歧义列名 → ``not_provided(mapping_uncertain)``，绝不猜；
- 批量失败件不改退出码语义、与越限件分列；
- 对账配对主键 = ``profile_id``；口径单一实现源 ``benchmark.cases.observed_nonpass``；
- 溯源完整性断言失败 → 拒绝交出（不降级为警告）。
"""

from __future__ import annotations

import json
import os

import pytest

from conftest import DATA, SRC
import sys

sys.path.insert(0, SRC)

from ebikecheck import service
from ebikecheck.benchmark.cases import observed_nonpass
from ebikecheck.engine import mapping as mapping_mod
from ebikecheck.engine.findings import NOT_PROVIDED
from ebikecheck.engine.reconcile import (
    NEW_VIOLATION,
    PERSISTENT,
    RESOLVED,
    reconcile_rounds,
)
from ebikecheck.profile import profile_sha256_of_content


# ---- FR-08 字段映射引擎 ----


@pytest.fixture(scope="module")
def mapping_table():
    return mapping_mod.load_param_mapping(DATA)


def test_registered_variant_maps_to_param(mapping_table):
    assert mapping_table.resolve("最高车速") == (mapping_mod.MAPPED, "max_design_speed")


def test_ambiguous_variant_is_uncertain(mapping_table):
    verdict, owner = mapping_table.resolve("车速")
    assert verdict == mapping_mod.UNCERTAIN
    assert owner is None


def test_unregistered_column_is_unmapped(mapping_table):
    assert mapping_table.resolve("神秘参数")[0] == mapping_mod.UNMAPPED


def test_empty_column_is_unmapped(mapping_table):
    assert mapping_table.resolve("")[0] == mapping_mod.UNMAPPED


def test_no_variant_maps_to_two_params():
    raw = json.load(open(os.path.join(DATA, "mapping", "mapping.json"), encoding="utf-8"))
    seen = {}
    for item in raw["parameters"]:
        for variant in item["variants"]:
            assert variant not in seen, "变体 {0} 登记到两个参数".format(variant)
            seen[variant] = item["param"]


def test_normalize_params_maps_and_drops_unmapped(mapping_table):
    out = mapping_mod.normalize_params(
        {
            "最高车速": {"value": "24.5", "unit": "km/h"},
            "神秘列": {"value": "1", "unit": "kg"},
        },
        mapping_table,
    )
    assert out["max_design_speed"]["value"] == "24.5"
    assert "神秘列" not in out
    assert "__unmapped__" not in out  # 未登记列直接丢弃，走 not_provided(missing) 路径


def test_normalize_params_injects_uncertain_marker(mapping_table):
    out = mapping_mod.normalize_params({"车速": {"value": "20", "unit": "km/h"}}, mapping_table)
    assert out["max_design_speed"]["reason"] == "mapping_uncertain"
    assert out["max_design_speed"]["value"] is None


def test_ambiguous_column_yields_mapping_uncertain_finding():
    """歧义列名经完整核查路径 → ``not_provided(mapping_uncertain)``（绝不猜值）。"""
    result = service.check_profile_dict(
        {
            "profile_id": "M3-MAP-1",
            "model_design_date": "2025-10-01",
            "params": mapping_mod.normalize_params(
                {"车速": {"value": "20", "unit": "km/h"}}, mapping_mod.load_param_mapping(DATA)
            ),
        },
        DATA,
        "GB17761-2024",
    )
    findings = [f for f in result.findings if f.param == "max_design_speed"]
    assert findings, "max_design_speed 应有判定结论"
    assert all(f.state == NOT_PROVIDED for f in findings)
    assert any(f.reason == "mapping_uncertain" for f in findings)


def test_variant_column_yields_judged_finding():
    """已登记变体（最高车速）经完整核查路径 → 正常判定（不因映射而降级）。"""
    params = mapping_mod.normalize_params(
        {"最高车速": {"value": "24.5", "unit": "km/h"}}, mapping_mod.load_param_mapping(DATA)
    )
    result = service.check_profile_dict(
        {
            "profile_id": "M3-MAP-2",
            "model_design_date": "2025-10-01",
            "params": params,
        },
        DATA,
        "GB17761-2024",
    )
    findings = [f for f in result.findings if f.param == "max_design_speed"]
    assert findings and all(f.state == "compliant" for f in findings)


def test_mapping_missing_table_raises(tmp_path):
    with pytest.raises(mapping_mod.MappingError):
        mapping_mod.load_param_mapping(str(tmp_path))


# ---- FR-09 批量扫描 + 失败件隔离 ----


@pytest.fixture()
def scan_dirs(tmp_path):
    """好件 ×1（真值库干净档案）、越限件 ×1、坏 JSON ×1、坏 schema ×1。"""
    good = json.load(open(os.path.join(DATA, "truth", "cases", "SYN-CASE-011.json"), encoding="utf-8"))
    over = json.load(open(os.path.join(DATA, "truth", "cases", "SYN-CASE-002.json"), encoding="utf-8"))
    round_dir = tmp_path / "round1"
    round_dir.mkdir()
    (round_dir / "good.json").write_text(
        json.dumps(good["profile"], ensure_ascii=False), encoding="utf-8"
    )
    (round_dir / "over.json").write_text(
        json.dumps(over["profile"], ensure_ascii=False), encoding="utf-8"
    )
    (round_dir / "bad_json.json").write_text("{oops", encoding="utf-8")
    (round_dir / "bad_schema.json").write_text('{"no_profile_id": 1}', encoding="utf-8")
    return str(round_dir)


def test_scan_isolates_failures(scan_dirs):
    payload = service.scan_dir(scan_dirs, DATA, "GB17761-2024")
    assert payload["total"] == 4
    assert len(payload["scanned"]) == 2
    reasons = {item["reason"] for item in payload["failed"]}
    assert reasons == {"bad_json", "bad_schema"}
    # 失败件与越限件分列：failed 里没有越限件，nonpass 里没有失败件。
    failed_paths = {item["path"] for item in payload["failed"]}
    assert all(item["path"] not in failed_paths for item in payload["scanned"])


def test_scan_failure_does_not_create_finding(scan_dirs):
    """失败件不进结论统计（"未判定"与"判出违规"分列）。"""
    payload = service.scan_dir(scan_dirs, DATA, "GB17761-2024")
    assert payload["overall_counts"]["non_compliant"] == 1  # 只有越限件
    assert len(payload["failed"]) == 2


def test_scan_carries_both_sha256(scan_dirs):
    payload = service.scan_dir(scan_dirs, DATA, "GB17761-2024")
    for item in payload["scanned"]:
        assert item["profile_sha256"]
        assert item["profile_content_sha256"]


def test_content_sha256_is_path_independent():
    raw = {"profile_id": "X", "params": {}}
    import hashlib

    a = json.dumps(raw, ensure_ascii=False, indent=2)
    b = json.dumps(raw, ensure_ascii=False)
    assert profile_sha256_of_content(raw) == profile_sha256_of_content(
        json.loads(a)
    ) == profile_sha256_of_content(json.loads(b))


def test_profile_sha256_of_content_is_deterministic():
    raw = {"profile_id": "Y", "params": {"a": {"value": "1"}}}
    assert profile_sha256_of_content(raw) == profile_sha256_of_content(raw)


def test_profile_from_dict_accepts_scalar_columns():
    from ebikecheck.profile import profile_from_dict

    profile = profile_from_dict({"profile_id": "S", "params": {"最高车速": "24.5"}})
    assert profile.params["最高车速"] == "24.5"


# ---- FR-10 跨轮对账三集合 ----


def _check_case(case_id, version="GB17761-2024"):
    case = json.load(
        open(os.path.join(DATA, "truth", "cases", "{0}.json".format(case_id)), encoding="utf-8")
    )
    return service.check_profile_dict(case["profile"], DATA, case.get("case_version", version))


def test_reconcile_self_compare_is_all_persistent():
    result = _check_case("SYN-CASE-001")
    rec = reconcile_rounds([result], [result])
    assert rec.counts() == {NEW_VIOLATION: 0, RESOLVED: 0, PERSISTENT: len(observed_nonpass(result))}


def test_reconcile_repair_and_new_violation():
    before = _check_case("SYN-CASE-002")
    case = json.load(
        open(os.path.join(DATA, "truth", "cases", "SYN-CASE-002.json"), encoding="utf-8")
    )
    repaired_profile = json.loads(json.dumps(case["profile"], ensure_ascii=False))
    repaired_profile["params"]["max_design_speed"] = {"value": "24.9", "unit": "km/h"}
    after = service.check_profile_dict(repaired_profile, DATA, "GB17761-2024")
    rec = reconcile_rounds([before], [after])
    assert ("SYN-EB-002", "max_design_speed", "non_compliant") in rec.resolved
    assert not any(item[0] == "SYN-EB-002" and item[1] == "max_design_speed" for item in rec.persistent)


def test_reconcile_missing_profile_is_not_resolved():
    """本轮未扫描的档案不得计入已整改（文件移走 ≠ 整改）。"""
    result = _check_case("SYN-CASE-001")
    rec = reconcile_rounds([result], [])
    assert rec.counts() == {NEW_VIOLATION: 0, RESOLVED: 0, PERSISTENT: 0}


def test_reconcile_new_profile_counts_as_new_violation():
    result = _check_case("SYN-CASE-001")
    rec = reconcile_rounds([], [result])
    assert rec.counts()[NEW_VIOLATION] == len(observed_nonpass(result))


def test_reconcile_key_basis_is_profile_id():
    rec = reconcile_rounds([], [])
    assert rec.key_basis == "profile_id"


def test_reconcile_uses_single_source_semantics():
    """三集合口径必须来自 ``observed_nonpass``（单一实现源）。"""
    result = _check_case("SYN-CASE-001")
    rec = reconcile_rounds([], [result])
    expected = {(result.profile_id, param, state) for param, state in observed_nonpass(result)}
    assert set(rec.new_violations) == expected


def test_service_compare_rounds_end_to_end(tmp_path):
    round1 = tmp_path / "r1"
    round2 = tmp_path / "r2"
    round1.mkdir()
    round2.mkdir()
    case = json.load(
        open(os.path.join(DATA, "truth", "cases", "SYN-CASE-002.json"), encoding="utf-8")
    )
    (round1 / "a.json").write_text(
        json.dumps(case["profile"], ensure_ascii=False), encoding="utf-8"
    )
    repaired = json.loads(json.dumps(case["profile"], ensure_ascii=False))
    repaired["params"]["max_design_speed"] = {"value": "24.9", "unit": "km/h"}
    (round2 / "a.json").write_text(
        json.dumps(repaired, ensure_ascii=False), encoding="utf-8"
    )
    payload = service.compare_rounds(str(round1), str(round2), DATA, "GB17761-2024")
    counts = payload["reconciliation"]["counts"]
    assert counts[RESOLVED] >= 1
    assert counts[PERSISTENT] >= 1  # 其余 not_provided 参数仍在


# ---- FR-11 证据链 ----


def test_evidence_chain_carries_both_sha256():
    case = json.load(
        open(os.path.join(DATA, "truth", "cases", "SYN-CASE-011.json"), encoding="utf-8")
    )
    result = service.check_profile_dict(case["profile"], DATA, "GB17761-2024")
    # 内存通路无文件指纹 → 先补内容指纹（导出通路的责任），再装配证据链。
    result.profile_sha256 = profile_sha256_of_content(case["profile"])
    evidence = service.evidence_chain(result)
    assert evidence["traceability"] == "ok"
    assert evidence["profile_sha256"]
    assert evidence["report_sha256"]
    assert evidence["rulesets"]


def test_report_sha256_detects_tampering():
    case = json.load(
        open(os.path.join(DATA, "truth", "cases", "SYN-CASE-011.json"), encoding="utf-8")
    )
    result = service.check_profile_dict(case["profile"], DATA, "GB17761-2024")
    result.profile_sha256 = profile_sha256_of_content(case["profile"])
    original = service.evidence_chain(result)["report_sha256"]
    result.dimensions[0].findings[0].observed = "999"
    tampered = service.evidence_chain(result)["report_sha256"]
    assert original != tampered


def test_traceability_rejects_missing_profile_sha256():
    case = json.load(
        open(os.path.join(DATA, "truth", "cases", "SYN-CASE-011.json"), encoding="utf-8")
    )
    result = service.check_profile_dict(case["profile"], DATA, "GB17761-2024")
    result.profile_sha256 = ""
    with pytest.raises(service.TraceabilityError):
        service.evidence_chain(result)


def test_traceability_rejects_orphan_finding():
    case = json.load(
        open(os.path.join(DATA, "truth", "cases", "SYN-CASE-011.json"), encoding="utf-8")
    )
    result = service.check_profile_dict(case["profile"], DATA, "GB17761-2024")
    result.profile_sha256 = profile_sha256_of_content(case["profile"])
    # 造一条"无来源块"的孤儿 finding（参数与标准号都对不上任何来源块）。
    from ebikecheck.engine.findings import Finding

    orphan = Finding(
        rule_id="ORPHAN-1",
        param="__orphan__",
        standard="GB 99999-9999",
        clause=None,
        clause_status="pending",
        op="<=",
        limit="1",
        unit="",
        observed="0",
        state="compliant",
    )
    result.dimensions[0].findings.append(orphan)
    with pytest.raises(service.TraceabilityError):
        service.assert_traceability(result)


def test_finding_detail_rows_match_source_blocks():
    """溯源完整性：明细行数 == 溯源行数（每条 finding 都有来源块）。"""
    case = json.load(
        open(os.path.join(DATA, "truth", "cases", "SYN-CASE-011.json"), encoding="utf-8")
    )
    result = service.check_profile_dict(case["profile"], DATA, "GB17761-2024")
    for dimension in result.dimensions:
        if not dimension.findings:
            continue
        keys = {(b["param"], b["standard"]) for b in dimension.source_blocks}
        for finding in dimension.findings:
            assert (finding.param, finding.standard) in keys
