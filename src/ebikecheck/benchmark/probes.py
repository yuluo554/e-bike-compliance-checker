"""规则驱动探针构造 —— **只从规则表推导端点**，不读真值库。

用途（[plan/05](../../../plan/05-数据计划与里程碑.md) §四 M2-3/M2-4）：

- ``boundary`` 套件：对每条生效规则直接跑 :func:`probe_values` 得到的
  (构造值, 期望结论) 对，覆盖**全部比较运算符**（含 ``==`` / ``!=`` / ``in`` /
  ``not_in`` / ``range`` 与布尔/无量纲条目）——新增规则自动进枚举，**不写死规则 id**；
- ``rule_driven`` 套件：用同一套构造走**完整三维核查路径**，证明"规则表 → 服务层 →
  引擎"端到端一致，且同样不依赖真值库。

**本模块不得内联任何限值数值** —— 端点全部由规则包的 ``op``/``value``/``unit`` 推出
（零字面量门禁扫描面含 ``benchmark/``）。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from ..engine.findings import COMPLIANT, NON_COMPLIANT
from ..engine.rules import eval_applies_if
from ..engine.values import epsilon_for

#: 条件参数候选值（枚举/布尔/数值通路的构造用；**判定语义不依赖它**，
#: 仅用于"造出条件为真"的档案）。新增条件形态时按需扩展。
_CONDITION_CANDIDATES = ("lead_acid", "lithium_ion", "true", "false", "1", "0")

#: "与限值不同"的哨兵值：不可解析为数值、且不等于任何枚举 token。
#: 用于 ``!=`` / ``in`` / ``not_in`` / 无量纲 ``==`` 的"另一侧"构造。
PROBE_OTHER = "__probe_other__"

_DIMENSIONLESS = ("", "none", "text", "bool")


def _field(rule: Any, name: str, default: Any = None) -> Any:
    """取规则字段 —— 同时接受 :class:`engine.rules.Rule` 与原始规则字典。

    基准/测试两侧都在用本模块：服务层拿到的是已解析的 ``Rule``，数据层对账拿到的是
    原始 JSON 字典；两种形态都要能推导端点，否则"规则驱动"就只是半边驱动。
    """
    if isinstance(rule, dict):
        return rule.get(name, default)
    return getattr(rule, name, default)


def _unit_of(rule) -> str:
    return (_field(rule, "unit", "") or "").strip()


def _is_dimensionless(rule) -> bool:
    return _unit_of(rule).lower() in _DIMENSIONLESS


def _as_value(raw: Any) -> Any:
    """构造值转成档案可承载的形态：布尔原样，其余字符串承载（禁用 float）。"""
    if isinstance(raw, bool):
        return raw
    return str(raw)


def probe_values(rule) -> List[Tuple[Any, str]]:
    """由规则本身推导 ``[(构造值, 期望结论)]`` —— 覆盖该 ``op`` 的两侧端点。

    语义（[plan/04](../../../plan/04-模块详设.md) §4.2）：

    ``<=`` 限值处符合 / 高一个最小计量单位不符合；
    ``>=`` 限值处符合 / 低一个最小计量单位不符合；
    ``<``  低一个最小计量单位符合 / 限值处不符合（上界开区间）；
    ``>``  高一个最小计量单位符合 / 限值处不符合；
    ``==`` 等于限值符合 / 另一侧不符合（布尔、枚举、数值三通路）；
    ``!=`` 不等于限值符合 / 等于限值不符合；
    ``in`` 白名单成员符合 / 哨兵不符合；
    ``not_in`` 哨兵符合 / 白名单成员不符合；
    ``range`` 下界符合 / 上界越限一个最小计量单位不符合。
    """
    op = _field(rule, "op")
    unit = _unit_of(rule)
    value = _field(rule, "value")

    if op in ("<=", ">=", "<", ">"):
        base = Decimal(str(value))
        step = epsilon_for(unit)
        if op == "<=":
            return [(_as_value(base), COMPLIANT), (_as_value(base + step), NON_COMPLIANT)]
        if op == ">=":
            return [(_as_value(base), COMPLIANT), (_as_value(base - step), NON_COMPLIANT)]
        if op == "<":
            return [(_as_value(base - step), COMPLIANT), (_as_value(base), NON_COMPLIANT)]
        return [(_as_value(base + step), COMPLIANT), (_as_value(base), NON_COMPLIANT)]

    if op == "==":
        token = str(value)
        if token in ("true", "false"):
            return [(token == "true", COMPLIANT), (token != "true", NON_COMPLIANT)]
        if _is_dimensionless(rule):
            return [(_as_value(value), COMPLIANT), (PROBE_OTHER, NON_COMPLIANT)]
        base = Decimal(str(value))
        step = epsilon_for(unit)
        return [(_as_value(base), COMPLIANT), (_as_value(base + step), NON_COMPLIANT)]

    if op == "!=":
        if _is_dimensionless(rule):
            return [(PROBE_OTHER, COMPLIANT), (_as_value(value), NON_COMPLIANT)]
        base = Decimal(str(value))
        step = epsilon_for(unit)
        return [(_as_value(base + step), COMPLIANT), (_as_value(base), NON_COMPLIANT)]

    if op in ("in", "not_in"):
        pool = list(value) if isinstance(value, (list, tuple)) else [value]
        if not pool:
            return []
        if op == "in":
            return [(_as_value(pool[0]), COMPLIANT), (PROBE_OTHER, NON_COMPLIANT)]
        return [(PROBE_OTHER, COMPLIANT), (_as_value(pool[0]), NON_COMPLIANT)]

    if op == "range":
        low, high = value[0], value[1]
        step = epsilon_for(unit)
        return [
            (_as_value(low), COMPLIANT),
            (_as_value(Decimal(str(high)) + step), NON_COMPLIANT),
        ]

    return []


def _collect_condition_params(expr: Any, out: List[str]) -> None:
    if not isinstance(expr, dict):
        return
    if "param" in expr:
        if expr["param"] not in out:
            out.append(expr["param"])
        return
    for key in ("all", "any"):
        for item in expr.get(key, []) or []:
            _collect_condition_params(item, out)
    if "not" in expr:
        _collect_condition_params(expr["not"], out)


def satisfying_condition_params(applies_if: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """求一组使 ``applies_if`` 为真的档案参数（小候选空间穷举）。

    条件规则必须构造出**条件为真**的档案，否则断言打在 ``not_applicable`` 上
    （如"非铅蓄电池车型"条件固定给 ``lead_acid`` 必不适用）。从 ``applies_if``
    引用的参数出发逐个候选值试解 —— **不针对具体规则 id 写死**。
    """
    if applies_if is None:
        return {}
    names: List[str] = []
    _collect_condition_params(applies_if, names)
    assignment: Dict[str, Any] = {}
    for name in names:
        for candidate in _CONDITION_CANDIDATES:
            trial = dict(assignment)
            trial[name] = {"value": candidate, "unit": ""}
            if eval_applies_if(applies_if, trial) is True:
                assignment = trial
                break
    return assignment


def compliant_params(rules) -> Dict[str, Any]:
    """由一组规则推导一份**全参数合规**的档案参数表（不硬编码取值）。

    每个参数取其规则推出的"符合侧"构造值；条件参数取使条件为真的构造。
    同一参数多条互斥条件规则时以先到者为准（另一条会判 ``not_applicable``，
    不影响"全参数合规"这一目标）。
    """
    params: Dict[str, Any] = {}
    for rule in rules:
        for name, item in satisfying_condition_params(_field(rule, "applies_if")).items():
            params.setdefault(name, item)
        target = _field(rule, "param")
        if target in params:
            continue
        good = [value for value, state in probe_values(rule) if state == COMPLIANT]
        if good:
            params[target] = {"value": _as_value(good[0]), "unit": _unit_of(rule)}
    return params


def params_for_rule_probe(rule, value: Any) -> Dict[str, Any]:
    """构造"只改这一条规则目标参数"的档案参数（其余走合规构造）。"""
    params = satisfying_condition_params(_field(rule, "applies_if"))
    params[_field(rule, "param")] = {"value": _as_value(value), "unit": _unit_of(rule)}
    return params
