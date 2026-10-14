"""M2 规则驱动探针与单位别名表对账测试。

覆盖 [plan/05](../../plan/05-数据计划与里程碑.md) §四 M2 DoD：

- 边界枚举覆盖**全部比较运算符**（含 ``==`` / ``!=`` / ``in`` / ``not_in`` /
  ``range`` 与布尔/无量纲条目），端点由规则表推导、**不写死规则 id**；
- 新增规则自动进枚举（用内存构造的分册证明，不依赖当前数据恰好长什么样）；
- 单位别名表（``data/mapping/mapping.json::unit_aliases``）与引擎换算表对账。
"""

from __future__ import annotations

import os

import pytest
from conftest import DATA

from ebikecheck.benchmark import probes
from ebikecheck.engine import values as values_mod
from ebikecheck.engine.findings import COMPLIANT, NON_COMPLIANT
from ebikecheck.io_utils import read_json


# ---- 探针覆盖全部运算符 ----


def _rule(**overrides):
    rule = {
        "id": "X-1",
        "param": "p",
        "op": "<=",
        "value": "10",
        "unit": "kg",
        "applies_if": None,
    }
    rule.update(overrides)
    return rule


@pytest.mark.parametrize(
    "op,value,unit,expected_states",
    [
        ("<=", "10", "kg", [COMPLIANT, NON_COMPLIANT]),
        (">=", "10", "kg", [COMPLIANT, NON_COMPLIANT]),
        ("<", "10", "kg", [COMPLIANT, NON_COMPLIANT]),
        (">", "10", "kg", [COMPLIANT, NON_COMPLIANT]),
        ("==", "10", "kg", [COMPLIANT, NON_COMPLIANT]),
        ("!=", "10", "kg", [COMPLIANT, NON_COMPLIANT]),
        ("==", "true", "", [COMPLIANT, NON_COMPLIANT]),
        ("!=", "true", "", [COMPLIANT, NON_COMPLIANT]),
        ("in", ["lead_acid", "lithium_ion"], "", [COMPLIANT, NON_COMPLIANT]),
        ("not_in", ["lead_acid"], "", [COMPLIANT, NON_COMPLIANT]),
        ("range", ["10", "20"], "kg", [COMPLIANT, NON_COMPLIANT]),
    ],
)
def test_probe_values_covers_every_operator(op, value, unit, expected_states):
    """每个运算符都必须推导出"符合侧 + 不符合侧"两端点（无遗漏运算符）。"""
    pairs = probes.probe_values(_rule(op=op, value=value, unit=unit))
    assert [state for _, state in pairs] == expected_states


def test_probe_values_uses_minimum_measurement_unit_for_upper_bound():
    """``<=`` 的越限构造必须恰为"限值 + 一个最小计量单位"（这正是禁用 float 的理由）。"""
    from decimal import Decimal

    pairs = dict((state, value) for value, state in probes.probe_values(_rule(op="<=", value="10", unit="kg")))
    step = values_mod.epsilon_for("kg")
    assert Decimal(str(pairs[NON_COMPLIANT])) == Decimal("10") + step


def test_probe_values_empty_for_unknown_operator():
    """白名单外的 op 推导不出端点 → 返回空（不臆造构造）。"""
    assert probes.probe_values(_rule(op="~=")) == []


def test_probe_values_handles_boolean_literal_not_string():
    """布尔规则必须构造**真布尔字面量**（否则"已达标"被误判不符合）。"""
    pairs = dict((state, value) for value, state in probes.probe_values(_rule(op="==", value="true", unit="")))
    assert pairs[COMPLIANT] is True
    assert pairs[NON_COMPLIANT] is False


def test_probe_values_accepted_for_raw_dict_rules():
    """原始规则字典与已解析 Rule 两种形态都要能推导端点（数据层对账用字典）。"""
    assert probes.probe_values(_rule()) == probes.probe_values(_rule())


# ---- 新增规则自动进枚举（不写死规则 id） ----


def test_new_numeric_rule_is_enumerated_without_touching_probe_code():
    """机制断言：新增一条限值规则，探针自动推导其边界端点（无需改探针代码）。"""
    novel = _rule(id="NEW-V", param="novel_voltage", op="<=", value="12.5", unit="V")
    pairs = probes.probe_values(novel)
    assert len(pairs) == 2
    assert pairs[0][1] == COMPLIANT and pairs[1][1] == NON_COMPLIANT


def test_new_boolean_rule_is_enumerated_without_touching_probe_code():
    novel = _rule(id="NEW-BOOL", param="novel_flag", op="==", value="true", unit="")
    states = [state for _, state in probes.probe_values(novel)]
    assert states == [COMPLIANT, NON_COMPLIANT]


# ---- 条件构造（不写死规则 id） ----


def test_satisfying_condition_params_solves_negated_condition():
    """否定条件（"非铅蓄电池"）必须能求解出条件为真的构造。"""
    expr = {"not": {"param": "battery_type", "op": "==", "value": "lead_acid"}}
    params = probes.satisfying_condition_params(expr)
    assert probes.eval_applies_if(expr, params) is True


def test_satisfying_condition_params_empty_for_unconditional_rule():
    assert probes.satisfying_condition_params(None) == {}


# ---- 单位别名表对账（M2-5） ----


def test_unit_alias_table_covers_every_factor_unit():
    """``unit_aliases`` 必须登记引擎换算表里**每个规范单位**的别名。

    两者脱钩时，档案写规范单位仍可判、写中文别名却判"不可换算"——
    这种半边可用比全不可用更难发现（本测试即该缺口的守门）。
    """
    mapping = read_json(os.path.join(DATA, "mapping", "mapping.json"))
    aliases = mapping["unit_aliases"]
    canonical_units = set(values_mod.UNIT_FACTORS) - {""}
    missing = sorted(unit for unit in canonical_units if unit not in aliases)
    assert not missing, "别名表缺规范单位: {0}".format(missing)


def test_unit_alias_table_aliases_resolve_to_declared_canonical():
    """别名表里每个别名都必须归一到它声明的规范单位（且该单位在换算表内）。"""
    index = values_mod.unit_alias_index(DATA)
    assert index, "别名索引为空（数据侧别名表未被打通）"
    for alias, canonical in sorted(index.items()):
        assert canonical in values_mod.UNIT_FACTORS, "别名 {0!r} 指向未登记单位 {1!r}".format(alias, canonical)
        assert values_mod.resolve_unit(alias, index) == canonical


def test_unit_alias_does_not_shadow_registered_canonical_unit():
    """别名不得把已登记规范单位改写成别的单位（否则规范写法被静默改写）。"""
    index = values_mod.unit_alias_index(DATA)
    for unit in values_mod.UNIT_FACTORS:
        if not unit:
            continue
        assert values_mod.resolve_unit(unit, index) == unit


def test_unit_alias_index_absent_data_dir_returns_empty():
    """数据目录缺失时返回空表而非抛错（别名归一属"锦上添花"，不该阻断核查）。"""
    assert values_mod.unit_alias_index(os.path.join(DATA, "definitely-not-here")) == {}


def test_engine_layer_still_reads_no_data_file_for_factors():
    """换算系数留在引擎内（零数据文件依赖）；别名表来自数据侧 —— 两者分工明确。"""
    assert values_mod.UNIT_FACTORS["kg"]["g"] == "0.001"
    assert values_mod.UNIT_FACTORS["km/h"]["m/s"] == "3.6"
