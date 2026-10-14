"""引擎层测试：schema 校验、门控、四态判定、Decimal 边界、版本锚定。"""

from __future__ import annotations

import json
import os

import pytest
from conftest import DATA, load_rule_values, param

from ebikecheck.engine import matrix, rules as rules_mod, version as version_mod
from ebikecheck.engine.findings import (
    COMPLIANT,
    NON_COMPLIANT,
    NOT_APPLICABLE,
    NOT_ASSESSED,
    NOT_PROVIDED,
    CheckResult,
    Finding,
)


# ---- schema 校验 ----


def _minimal_rule(**overrides):
    rule = {
        "id": "X-1",
        "param": "p",
        "op": "<=",
        "value": "1",
        "unit": "kg",
        "clause": None,
        "clause_status": "pending",
        "source": {"kind": "to_verify", "retrieved_on": "2026-10-14"},
        "status": "verified",
    }
    rule.update(overrides)
    return rule


def _minimal_ruleset(rules):
    return {
        "schema_version": "1.0",
        "standard": {
            "code": "GB 17761-2024",
            "title": "t",
            "published": "2024-12-31",
            "effective": "2025-09-01",
            "status": "current",
        },
        "scope": "vehicle",
        "rules": rules,
    }


def test_schema_rejects_op_out_of_whitelist():
    payload = _minimal_ruleset([_minimal_rule(op="~=")])
    with pytest.raises(rules_mod.RulesetError):
        rules_mod.validate_ruleset(payload, "probe.json")


def test_schema_rejects_missing_required_field():
    payload = _minimal_ruleset([{"id": "X-1", "param": "p"}])
    with pytest.raises(rules_mod.RulesetError):
        rules_mod.validate_ruleset(payload, "probe.json")


def test_schema_rejects_verified_with_null_value():
    """未核对不得生效：verified + value=null 必须被拒（防"待核对却已进核查路径"）。"""
    payload = _minimal_ruleset([_minimal_rule(status="verified", value=None)])
    with pytest.raises(rules_mod.RulesetError):
        rules_mod.validate_ruleset(payload, "probe.json")
    with pytest.raises(rules_mod.RulesetError):
        rules_mod._parse_rule(_minimal_rule(value=None), "GB 17761-2024", "probe")

def test_schema_rejects_pending_with_prefilled_value():
    """待核对不得预填数值。"""
    with pytest.raises(rules_mod.RulesetError):
        rules_mod._parse_rule(
            _minimal_rule(status="pending", value="5"), "GB 17761-2024", "probe"
        )


def test_schema_rejects_clause_verified_without_clause():
    """clause_status=verified 必须有条款号（不编造纪律的反面：也不许空标 verified）。"""
    with pytest.raises(rules_mod.RulesetError):
        rules_mod._parse_rule(
            _minimal_rule(clause=None, clause_status="verified"), "GB 17761-2024", "probe"
        )


def test_schema_rejects_prefilled_clause_when_pending():
    """clause_status=pending 时不得预填条款号。"""
    with pytest.raises(rules_mod.RulesetError):
        rules_mod._parse_rule(
            _minimal_rule(clause="6.1.1", clause_status="pending"), "GB 17761-2024", "probe"
        )


def test_schema_rejects_scope_and_standard_status():
    payload = _minimal_ruleset([_minimal_rule()])
    payload["scope"] = "unknown-scope"
    with pytest.raises(rules_mod.RulesetError):
        rules_mod.validate_ruleset(payload, "probe.json")

    payload = _minimal_ruleset([_minimal_rule()])
    payload["standard"]["status"] = "weird"
    with pytest.raises(rules_mod.RulesetError):
        rules_mod.validate_ruleset(payload, "probe.json")


def test_schema_rejects_duplicate_rule_id_in_ruleset():
    """同一分册内 id 重复必须被拒（防同一目标出双份结论）。"""
    payload = _minimal_ruleset([_minimal_rule(id="DUP"), _minimal_rule(id="DUP")])
    rules_mod.validate_ruleset(payload, "probe.json")
    with pytest.raises(rules_mod.RulesetError):
        rules_mod.load_ruleset_file_from_dict(payload, "probe.json")


def test_schema_rejects_duplicate_param_same_condition():
    """同 (param, clause, applies_if) 重复 = 双份结论来源，必须被拒。"""
    payload = _minimal_ruleset([_minimal_rule(id="A"), _minimal_rule(id="B")])
    rules_mod.validate_ruleset(payload, "probe.json")
    with pytest.raises(rules_mod.RulesetError):
        rules_mod.load_ruleset_file_from_dict(payload, "probe.json")


def test_duplicate_param_with_different_condition_allowed():
    """同一参数配不同 applies_if 是正常形态（不同电池类型的质量限值），不得误判重复。"""
    first = _minimal_rule(id="A", applies_if={"param": "battery_type", "op": "==", "value": "lead_acid"})
    second = _minimal_rule(
        id="B",
        applies_if={"not": {"param": "battery_type", "op": "==", "value": "lead_acid"}},
    )
    parsed_a = rules_mod._parse_rule(first, "GB 17761-2024", "a")
    parsed_b = rules_mod._parse_rule(second, "GB 17761-2024", "b")
    key_a = (parsed_a.param, parsed_a.clause or "", json.dumps(parsed_a.applies_if_raw, sort_keys=True))
    key_b = (parsed_b.param, parsed_b.clause or "", json.dumps(parsed_b.applies_if_raw, sort_keys=True))
    assert key_a != key_b


# ---- 门控 ----


def test_status_gating_excludes_pending(data_dir):
    """门控纪律：``pending`` 零进入核查路径，且全库仍存在 ``pending`` 条目。

    M1 后 GB 17761 两册已全部转 ``verified``（条款号与数值均以正式标准全文核对），
    电池/充电器册的首期不参数化条目仍为 ``pending`` —— 门控因此按**全库**口径断言，
    不绑定某一分册的具体计数。
    """
    manifest = rules_mod.load_manifest(data_dir)
    total_excluded = 0
    for entry in manifest.rulesets:
        ruleset = rules_mod.load_ruleset_by_key(data_dir, manifest, entry["version_key"])
        effective_ids = {rule.id for rule in ruleset.rules}
        excluded_ids = {item.rule_id for item in ruleset.excluded}
        assert effective_ids.isdisjoint(excluded_ids), "pending 条目不得同时出现在生效集"
        for item in ruleset.excluded:
            assert item.reason == "not_verified"
        total_excluded += len(excluded_ids)
    assert total_excluded > 0, "全库应仍存在 pending 条目（电池/充电器册首期不参数化）"


def test_pending_rule_is_excluded_from_check_path():
    """机制（与数据状态解耦）：``pending`` 条目被门控排除、``verified`` 才生效。"""
    payload = _minimal_ruleset(
        [
            _minimal_rule(id="OK", param="p", value="1"),
            _minimal_rule(id="WAIT", param="q", status="pending", value=None),
        ]
    )
    ruleset = rules_mod.load_ruleset_file_from_dict(payload, "probe.json")
    assert {rule.id for rule in ruleset.rules} == {"OK"}
    assert {item.rule_id for item in ruleset.excluded} == {"WAIT"}


def test_selfcheck_counts_match_manifest(data_dir):
    from ebikecheck import service

    payload = service.selfcheck(data_dir)
    verified = sum(item["verified"] for item in payload["rulesets"])
    pending = sum(item["pending"] for item in payload["rulesets"])
    assert payload["verified_total"] == verified
    assert payload["pending_total"] == pending
    assert verified > 0


# ---- 四态判定 ----


VALUES = load_rule_values(DATA)


def test_boundary_at_limit_is_compliant(data_dir, written_profile):
    speed = VALUES["max_design_speed"]
    params = {
        "max_design_speed": param(speed["value"], speed["unit"]),
        "over_speed_power_cutoff": param(True, ""),
        "battery_type": param("lead_acid", ""),
        "anti_tamper_battery_pack": param(True, ""),
        "anti_tamper_controller": param(True, ""),
        "anti_tamper_speed_limiter": param(True, ""),
    }
    from ebikecheck import service

    result = service.check_profile(written_profile(params), data_dir)
    states = {f.param: f.state for f in result.findings}
    assert states["max_design_speed"] == COMPLIANT


def test_boundary_over_limit_is_non_compliant_using_decimal(data_dir, written_profile):
    """边界差一个最小计量单位必须判出——这就是禁用 float 的理由。"""
    speed = VALUES["max_design_speed"]
    from decimal import Decimal

    over = str(Decimal(speed["value"]) + Decimal("0.1"))
    params = {
        "max_design_speed": param(over, speed["unit"]),
        "battery_type": param("lead_acid", ""),
    }
    from ebikecheck import service

    result = service.check_profile(written_profile(params), data_dir)
    states = {f.param: f.state for f in result.findings}
    assert states["max_design_speed"] == NON_COMPLIANT


def test_missing_param_is_not_provided_never_compliant(data_dir, written_profile):
    """**核心硬约束**：未提供参数绝不判为符合。"""
    params = {
        "max_design_speed": param("20", "km/h"),
        "battery_type": param("lead_acid", ""),
    }
    from ebikecheck import service

    result = service.check_profile(written_profile(params), data_dir)
    states = {f.param: f.state for f in result.findings}
    assert states["plastic_mass_ratio"] == NOT_PROVIDED
    assert states["plastic_mass_ratio"] != COMPLIANT
    reasons = {f.param: f.reason for f in result.findings}
    assert reasons["plastic_mass_ratio"] == "missing"


def test_condition_false_is_not_applicable(data_dir, written_profile):
    """铅蓄电池条款对锂电池车型不适用。"""
    lead_rule = _find_rule(data_dir, "GB17761-2024", "vehicle_mass", "lead_acid")
    params = {
        "battery_type": param("lithium_ion", ""),
        "max_design_speed": param("20", "km/h"),
    }
    finding = matrix.check_param(lead_rule, params)
    assert finding.state == NOT_APPLICABLE


def test_condition_unknown_is_not_provided(data_dir, written_profile):
    """条件引用参数缺失 → unknown ≠ not_applicable（保守判未提供）。"""
    lead_rule = _find_rule(data_dir, "GB17761-2024", "vehicle_mass", "lead_acid")
    finding = matrix.check_param(lead_rule, {"max_design_speed": param("20", "km/h")})
    assert finding.state == NOT_PROVIDED
    assert finding.reason == "condition_unknown"


def test_all_not_applicable_yields_not_assessed():
    """一条都不适用 → not_assessed，绝不输出 compliant。"""
    result = CheckResult(
        profile_id="P",
        ruleset_file="f.json",
        ruleset_sha256="x",
        version_key="K",
        version_anchor={},
        findings=[
            Finding("R1", "p", "S", None, "pending", "<=", "1", "kg", None, NOT_APPLICABLE)
        ],
    )
    assert result.overall() == NOT_ASSESSED
    assert result.overall() != COMPLIANT


def test_empty_findings_yields_not_assessed():
    result = CheckResult("P", "f.json", "x", "K", {}, findings=[])
    assert result.overall() == NOT_ASSESSED


def test_unit_conversion_downgrades_to_warning(data_dir, written_profile):
    """g → kg 显式换算后判定，结论降级 warning（只报不阻断）。"""
    mass_rule = _find_rule(data_dir, "GB17761-2024", "vehicle_mass", "lead_acid")
    grams = str(int(mass_rule.value) * 1000)
    finding = matrix.check_param(
        mass_rule, {"vehicle_mass": param(grams, "g"), "battery_type": param("lead_acid", "")}
    )
    assert finding.state == COMPLIANT
    assert finding.severity == "warning"


def test_incompatible_unit_is_not_provided(data_dir):
    """未登记换算 → not_provided，绝不臆测。"""
    speed_rule = _find_rule(data_dir, "GB17761-2024", "max_design_speed", None)
    finding = matrix.check_param(speed_rule, {"max_design_speed": param("15", "mph")})
    assert finding.state == NOT_PROVIDED
    assert finding.reason == "unit_incompatible"


def test_missing_unit_is_not_provided(data_dir):
    speed_rule = _find_rule(data_dir, "GB17761-2024", "max_design_speed", None)
    finding = matrix.check_param(speed_rule, {"max_design_speed": param("20", "")})
    assert finding.state == NOT_PROVIDED
    assert finding.reason == "unit_unknown"


def test_boolean_true_matches_string_limit(data_dir):
    """档案布尔字面量与规则包字符串承载必须可比（否则"已达标"被误判不符合）。"""
    rule = _find_rule(data_dir, "GB17761-2024", "over_speed_power_cutoff", None)
    assert matrix.check_param(rule, {"over_speed_power_cutoff": param(True, "")}).state == COMPLIANT
    assert (
        matrix.check_param(rule, {"over_speed_power_cutoff": param(False, "")}).state
        == NON_COMPLIANT
    )


def _find_rule(data_dir, version_key, param_name, condition_value):
    manifest = rules_mod.load_manifest(data_dir)
    ruleset = rules_mod.load_ruleset_by_key(data_dir, manifest, version_key)
    for rule in ruleset.rules:
        if rule.param != param_name:
            continue
        if condition_value is None:
            return rule
        expr = rule.applies_if_raw or {}
        if expr.get("value") == condition_value:
            return rule
    raise AssertionError("未找到规则 {0}/{1}".format(version_key, param_name))


# ---- 版本锚定 ----


def test_version_anchor_boundaries(data_dir):
    manifest = rules_mod.load_manifest(data_dir)
    anchors = manifest.version_anchors

    before = {"model_design_date": "2025-08-31"}
    key, _ = version_mod.anchor_version(before, anchors)
    assert key == "GB17761-2018"

    at = {"model_design_date": "2025-09-01"}
    key, _ = version_mod.anchor_version(at, anchors)
    assert key == "GB17761-2024"

    after = {"model_design_date": "2026-01-01"}
    key, _ = version_mod.anchor_version(after, anchors)
    assert key == "GB17761-2024"


def test_version_anchor_falls_back_to_market_date(data_dir):
    manifest = rules_mod.load_manifest(data_dir)
    key, info = version_mod.anchor_version(
        {"market_date": "2025-06-01"}, manifest.version_anchors
    )
    assert key == "GB17761-2018"
    assert info["basis"] == "market_date"


def test_version_anchor_ambiguous_without_dates(data_dir):
    manifest = rules_mod.load_manifest(data_dir)
    key, info = version_mod.anchor_version({}, manifest.version_anchors)
    assert key == version_mod.AMBIGUOUS
    assert info["rule"] == "no_date"


def test_check_requires_explicit_version_when_no_date(data_dir, written_profile):
    from ebikecheck import service

    path = written_profile({"max_design_speed": param("20", "km/h")}, design_date=None)
    with pytest.raises(service.ServiceError):
        service.check_profile(path, data_dir)
    # 显式指定则可用
    result = service.check_profile(path, data_dir, version_key="GB17761-2024")
    assert result.version_key == "GB17761-2024"


def test_explicit_unknown_version_key_rejected(data_dir, written_profile):
    from ebikecheck import service

    path = written_profile({"max_design_speed": param("20", "km/h")})
    with pytest.raises(service.ServiceError):
        service.check_profile(path, data_dir, version_key="NOPE-9999")


# ---- 版本差异 ----


def test_same_profile_different_verdict_across_versions(data_dir, written_profile):
    """同一档案在两版下结论不同 —— 版本切换必须真实生效。"""
    from ebikecheck import service
    from decimal import Decimal

    lead = _find_rule(data_dir, "GB17761-2024", "vehicle_mass", "lead_acid")
    old = _find_rule(data_dir, "GB17761-2018", "vehicle_mass", None)
    between = (Decimal(str(old.value)) + Decimal(str(lead.value))) / 2
    params = {
        "vehicle_mass": param(str(between), lead.unit),
        "battery_type": param("lead_acid", ""),
        "max_design_speed": param("20", "km/h"),
    }
    path = written_profile(params)
    results = dict(service.check_profile_all_versions(path, data_dir))

    def state_for(result, param_name):
        for finding in result.findings:
            if finding.param == param_name:
                return finding.state
        return None

    assert state_for(results["GB17761-2024"], "vehicle_mass") == COMPLIANT
    assert state_for(results["GB17761-2018"], "vehicle_mass") == NON_COMPLIANT
