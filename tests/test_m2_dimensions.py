"""M2 三维判定与跨标准统一结论测试（整车 / 电池 / 充电器）。

覆盖 [plan/05](../../plan/05-数据计划与里程碑.md) §四 M2 DoD：

- 一份档案同时得到**三维**结论，各挂自身标准号与条款号；
- 统一结论跨三维按"不符合 > 未提供 > 未评估 > 符合"聚合；
- ``not_applicable`` 不覆盖另一条适用规则的结论（D-38，勿回退）；
- 标准生效日晚于档案锚定日 → 该维度**不适用且不参与聚合**（D-43）；
- 单位书写变体（``公里/小时``）经别名表归一后仍可判定（M2-5）。
"""

from __future__ import annotations

import os

import pytest
from conftest import DATA, load_all_rule_values, load_rule_values, param

from ebikecheck import service
from ebikecheck.benchmark import probes
from ebikecheck.engine import rules as rules_mod
from ebikecheck.engine.findings import (
    COMPLIANT,
    NON_COMPLIANT,
    NOT_ASSESSED,
    NOT_PROVIDED,
    CheckResult,
    Finding,
    aggregate_overall,
)

VALUES = load_rule_values(DATA)
ALL_VALUES = load_all_rule_values(DATA)


def _compliant(extra=None, exclude=()):
    params = {}
    for name, rule in ALL_VALUES.items():
        if name in exclude:
            continue
        good = [value for value, state in probes.probe_values(rule) if state == COMPLIANT]
        if good:
            params[name] = {"value": good[0], "unit": rule.get("unit", "")}
    params.setdefault("battery_type", param("lead_acid", ""))
    if extra:
        params.update(extra)
    return params


# ---- 三维装配 ----


def test_check_returns_three_dimensions_each_with_own_standard(written_profile):
    """M2-1：一份档案同时得到整车 + 电池 + 充电器三维结论，各挂自身标准号。"""
    path = written_profile(_compliant())
    result = service.check_profile(path, DATA)
    scopes = [item.scope for item in result.dimensions]
    assert scopes == ["vehicle", "battery", "charger"]
    standards = {item.scope: item.standard for item in result.dimensions}
    assert standards["vehicle"] == "GB 17761-2024"
    assert standards["battery"] == "GB 43854-2024"
    assert standards["charger"] == "GB 42296-2022"


def test_dimensions_are_independent_rulesets_not_merged(written_profile):
    """FR-02/FR-04：电池/充电器是独立标准，不得混进整车册。

    每个维度的 ``ruleset_file`` 必须是该标准自己的分册，且 finding 的 ``standard``
    与该维度一致（"跨标准混册"会让条款号挂错标准）。
    """
    path = written_profile(_compliant())
    result = service.check_profile(path, DATA)
    expected_file = {
        "vehicle": "gb17761-2024.json",
        "battery": "gb43854-2024.json",
        "charger": "gb42296-2022.json",
    }
    for dimension in result.dimensions:
        assert dimension.ruleset_file == expected_file[dimension.scope]
        for finding in dimension.findings:
            assert finding.standard == dimension.standard


def test_charger_dimension_flags_its_own_over_limit(written_profile):
    """充电器维度独立判定：空载输出电压越限 → 充电器维度不符合，整车维度不背锅。"""
    rule = ALL_VALUES["charger_no_load_output_voltage"]
    bad = [value for value, state in probes.probe_values(rule) if state == NON_COMPLIANT][0]
    params = _compliant({"charger_no_load_output_voltage": param(str(bad), rule["unit"])})
    result = service.check_profile(written_profile(params), DATA)

    assert result.dimension("charger").overall() == NON_COMPLIANT
    assert result.dimension("vehicle").overall() == COMPLIANT
    assert result.overall() == NON_COMPLIANT


# ---- 跨标准统一结论（M2-2） ----


def test_unified_conclusion_takes_weakest_across_dimensions(written_profile):
    """统一结论跨三维按"最弱优先"聚合（不适用维度不参与）。"""
    path = written_profile(_compliant())
    result = service.check_profile(path, DATA)
    assert result.overall() == COMPLIANT
    # 电池册首期零生效规则 → 该维度 not_assessed 但**不参与**聚合，不拉低结论。
    battery = result.dimension("battery")
    assert battery.effective_rule_count == 0
    assert battery.overall() == NOT_ASSESSED
    assert battery.participates() is False


def test_aggregate_overall_ignores_non_participating_dimensions():
    """纯函数口径：零生效规则与"标准未生效"的维度都不参与聚合。"""
    vehicle = CheckResult(
        "P", "v.json", "x", "K", {}, findings=[
            Finding("R1", "p", "S", None, "pending", "<=", "1", "kg", "0", COMPLIANT)
        ], scope="vehicle", effective_rule_count=1,
    )
    battery = CheckResult(
        "P", "b.json", "x", "K", {}, findings=[], scope="battery", effective_rule_count=0,
    )
    assert aggregate_overall([vehicle, battery]) == COMPLIANT

    # 标准尚未生效 → 不适用，也不参与。
    future = CheckResult(
        "P", "c.json", "x", "K", {}, findings=[], scope="charger", effective_rule_count=3,
        applicability={"applicable": False, "reason": "未生效"},
    )
    assert future.participates() is False
    assert aggregate_overall([vehicle, future]) == COMPLIANT


def test_aggregate_overall_zero_participants_is_not_assessed():
    """零个维度参与 → not_assessed，**绝不输出 compliant**。"""
    empty = CheckResult("P", "b.json", "x", "K", {}, scope="battery", effective_rule_count=0)
    assert aggregate_overall([empty]) == NOT_ASSESSED
    assert aggregate_overall([]) == NOT_ASSESSED


def test_not_applicable_does_not_override_applicable_conclusion():
    """D-38 勿回退：一条不适用不得覆盖另一条适用规则的明确结论。"""
    findings = [
        Finding("R-lead", "vehicle_mass", "S", "6.1.3", "verified", "<=", "63", "kg", None, "not_applicable"),
        Finding("R-other", "vehicle_mass", "S", "6.1.3", "verified", "<=", "55", "kg", "50", COMPLIANT),
    ]
    result = CheckResult("P", "f.json", "x", "K", {}, findings=findings)
    assert result.overall() == COMPLIANT


def test_dimension_inapplicable_when_standard_not_yet_effective():
    """D-43：标准生效日晚于档案锚定日 → 该维度不适用、不跑判定、不参与聚合。

    GB 43854—2024 生效日 2024-11-01；把档案设计日锚到 2024-10-01（< 2025-09-01，
    命中 2018 版整车册）即早于电池标准生效日。
    """
    manifest = rules_mod.load_manifest(DATA)
    profile = service.profile_from_dict(
        {
            "profile_id": "SYN-EB-EARLY",
            "model_design_date": "2024-10-01",
            "params": {"max_design_speed": param("20", "km/h"), "battery_type": param("lead_acid", "")},
        }
    )
    result = service.check_profile_obj(profile, DATA, manifest)
    battery = result.dimension("battery")
    assert battery.applicability["applicable"] is False
    assert battery.findings == []  # 不适用的标准不跑判定
    assert battery.participates() is False
    # 整车维度仍判定（2018 版锚定），充电器标准 2023-07-01 已生效 → 参与。
    assert result.dimension("vehicle").participates() is True
    assert result.dimension("charger").participates() is True


def test_battery_dimension_applicable_after_its_effective_date():
    """生效日之后 → 电池维度适用（反向对照，防"永远不适用"的假绿）。"""
    manifest = rules_mod.load_manifest(DATA)
    profile = service.profile_from_dict(
        {
            "profile_id": "SYN-EB-LATE",
            "model_design_date": "2025-10-01",
            "params": {"max_design_speed": param("20", "km/h"), "battery_type": param("lead_acid", "")},
        }
    )
    result = service.check_profile_obj(profile, DATA, manifest)
    assert result.dimension("battery").applicability["applicable"] is True


def test_unified_conclusion_not_provided_when_a_participating_dimension_is(written_profile):
    """未提供优先于符合（但低于不符合）：充电器参数缺失 → 统一结论未提供。"""
    params = _compliant(exclude=("charger_no_load_output_voltage",))
    result = service.check_profile(written_profile(params), DATA)
    assert result.dimension("charger").overall() == NOT_PROVIDED
    assert result.overall() == NOT_PROVIDED


# ---- 单位别名归一（M2-5） ----


def test_unit_alias_variant_is_resolved_and_judged(written_profile):
    """档案写"公里/小时"（别名变体）仍可判定 —— 归一后等价于规范单位。"""
    params = _compliant({"max_design_speed": param("20", "公里/小时")})
    result = service.check_profile(written_profile(params), DATA)
    speed = [f for f in result.findings if f.param == "max_design_speed"][0]
    assert speed.state == COMPLIANT
    # 别名归一不是"换算"，不降级。
    assert speed.severity == "normal"


def test_unit_alias_variant_of_mass_in_chinese_is_judged(written_profile):
    """「公斤」变体归一为 kg 后可判定（覆盖别名表的中文写法）。"""
    rule = ALL_VALUES["vehicle_mass"]
    good = [value for value, state in probes.probe_values(rule) if state == COMPLIANT][0]
    params = _compliant({"vehicle_mass": param(str(good), "公斤")})
    result = service.check_profile(written_profile(params), DATA)
    mass = [f for f in result.findings if f.param == "vehicle_mass"][0]
    assert mass.state == COMPLIANT


def test_unregistered_unit_variant_still_not_provided(written_profile):
    """别名表未登记的写法不得被臆测换算（``mph`` → not_provided）。"""
    params = _compliant({"max_design_speed": param("15", "mph")})
    result = service.check_profile(written_profile(params), DATA)
    speed = [f for f in result.findings if f.param == "max_design_speed"][0]
    assert speed.state == NOT_PROVIDED
    assert speed.reason == "unit_incompatible"


# ---- 确定性 ----


def test_three_dimension_result_serialization_is_deterministic(written_profile):
    from ebikecheck.io_utils import dumps_json

    path = written_profile(_compliant())
    first = service.check_profile(path, DATA)
    second = service.check_profile(path, DATA)
    assert dumps_json(first.to_dict()) == dumps_json(second.to_dict())


def test_all_versions_returns_three_dimensions_each(written_profile):
    """版本对照通路同样做完整三维装配。"""
    path = written_profile(_compliant())
    results = dict(service.check_profile_all_versions(path, DATA))
    assert set(results) == {"GB17761-2018", "GB17761-2024"}
    for key, result in results.items():
        assert [item.scope for item in result.dimensions] == ["vehicle", "battery", "charger"]
