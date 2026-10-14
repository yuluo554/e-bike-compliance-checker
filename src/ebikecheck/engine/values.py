"""参数量值的单位归一与比较（全链路 ``Decimal``）。

纪律（[plan/04](../../../plan/04-模块详设.md) §4.2/§4.3）：

- **禁用 float**：边界扫描要检出 1 个最小计量单位的差异，float 尾差会把边界判错。
- 单位可**显式无损换算**（kg↔g、km↔m、%↔‰）→ 换算后判定并降级为 ``warning``；
  **不可换算一律 ``not_provided``**，绝不臆测。
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from ..io_utils import decode_decimal

#: 单位换算表：``目标单位 -> {源单位: 乘数}``。
#: 只登记**显式无损**的十进换算；英里、市斤等未登记即视为不可换算。
#:
#: 口径（M2-5 决策 D-42）：**换算系数留在引擎内**（它是数学常量，不是领域限值，
#: 引擎层因此保持零数据文件依赖）；**单位别名表来自 ``data/mapping/mapping.json``**
#: （``unit_aliases``，数据侧唯一来源），经 :func:`unit_alias_index` 反转后由
#: :func:`resolve_unit` 把档案里写的中文/大小写变体（``公里/小时``、``KM/H``）
#: 归一到本表的规范单位。两表由 ``test_unit_alias_table_covers_factor_units`` 对账。
UNIT_FACTORS: Dict[str, Dict[str, str]] = {
    "kg": {"kg": "1", "g": "0.001", "t": "1000"},
    "g": {"g": "1", "kg": "1000", "mg": "0.001"},
    "km/h": {"km/h": "1", "m/s": "3.6", "km/s": "3600"},
    "m/s": {"m/s": "1", "km/h": "0.2777777777777777777777777778"},
    "km": {"km": "1", "m": "0.001"},
    "m": {"m": "1", "km": "1000", "mm": "0.001"},
    "%": {"%": "1", "‰": "0.1"},
    "‰": {"‰": "1", "%": "10"},
    "V": {"V": "1", "mV": "0.001"},
    "W": {"W": "1", "kW": "1000"},
    # 只登记同一性换算（无跨单位换算需求）；登记在册是为了让"单位别名表里的
    # 规范单位都确实被引擎认识"，未登记的跨单位换算仍一律 not_provided。
    "Ah": {"Ah": "1"},
    # 无量纲/枚举参数用空串占位，比较不走数值通路。
    "": {"": "1"},
}

#: 视为"无量纲"的单位标记（枚举、布尔、文本参数）。
DIMENSIONLESS_UNITS = frozenset({"", "none", "text", "bool"})

#: 单位别名索引缓存（``data/mapping/mapping.json::unit_aliases`` 反转）。
_UNIT_ALIAS_CACHE: Dict[str, Any] = {"path": None, "index": {}}


def unit_alias_index(data_dir: Optional[str] = None) -> Dict[str, str]:
    """``{别名: 规范单位}`` —— 来自 ``data/mapping/mapping.json``（数据侧唯一来源）。

    无数据目录或文件缺失时返回空表（**不报错**）：别名归一属"锦上添花"，
    缺它只该退化为"按原样比对"，不该让整条核查路径崩掉。
    """
    if data_dir is None:
        from ..paths import find_data_dir

        data_dir = find_data_dir()
    if not data_dir:
        return {}
    path = os.path.join(data_dir, "mapping", "mapping.json")
    if _UNIT_ALIAS_CACHE["path"] == path and _UNIT_ALIAS_CACHE["index"]:
        return dict(_UNIT_ALIAS_CACHE["index"])
    if not os.path.isfile(path):
        return {}
    try:
        from ..io_utils import read_json

        raw = read_json(path)
    except Exception:
        return {}
    index: Dict[str, str] = {}
    for canonical, aliases in sorted((raw.get("unit_aliases") or {}).items()):
        for alias in aliases or []:
            index.setdefault(str(alias), str(canonical))
    _UNIT_ALIAS_CACHE["path"] = path
    _UNIT_ALIAS_CACHE["index"] = index
    return dict(index)


def resolve_unit(token: str, aliases: Optional[Dict[str, str]] = None) -> str:
    """把单位书写变体归一到规范单位（``公里/小时`` → ``km/h``、``KM/H`` → ``km/h``）。

    已在换算表中的规范单位原样返回；别名表未登记的**保持原样**（于是仍然
    "不可换算"，落到 ``not_provided(unit_incompatible)``，绝不臆测）。
    """
    text = (token or "").strip()
    if text in DIMENSIONLESS_UNITS:
        return text
    if text in UNIT_FACTORS:
        return text
    table = aliases if aliases is not None else unit_alias_index()
    return table.get(text, text)

#: 各单位的"最小计量单位"（边界枚举用）。未登记者按 0.1 处理。
UNIT_EPSILON: Dict[str, str] = {
    "km/h": "0.1",
    "m/s": "0.1",
    "kg": "0.1",
    "g": "0.1",
    "%": "0.1",
    "‰": "0.1",
    "km": "0.1",
    "m": "0.1",
    "V": "0.1",
    "W": "1",
    "mV": "1",
    "kW": "0.1",
}


class UnitError(Exception):
    """单位不可用（缺失或不可换算）。``reason`` 供调用方转成原因码。"""

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason


def normalize_unit(
    value: Any, source_unit: str, target_unit: str
) -> Tuple[Optional[Decimal], bool]:
    """把 ``value``（``source_unit``）换算到 ``target_unit``。

    返回 ``(数值, 是否降级)``；无法换算时抛 :class:`UnitError`。
    降级 = 发生了非平凡换算（源单位与目标单位不同），语义上"可判定但需留意"。

    档案侧单位先经 :func:`resolve_unit` 归一别名（``公里/小时`` → ``km/h``），
    故别名书写不再误判为"不可换算"；别名表未登记的写法仍按不可换算处理。
    """
    target = resolve_unit(target_unit)
    source = resolve_unit(source_unit)
    if target in DIMENSIONLESS_UNITS and source in DIMENSIONLESS_UNITS:
        return None, False  # 无量纲参数不走数值通路
    if not source:
        raise UnitError("unit_unknown", "档案未提供单位，无法与限值比较")
    if source == target:
        number = decode_decimal(value)
        if number is None:
            raise UnitError("unparsable", "值不可解析为数值")
        return number, False
    table = UNIT_FACTORS.get(target)
    if not table or source not in table:
        raise UnitError(
            "unit_incompatible",
            "单位 {0!r} 无法换算到 {1!r}（未登记换算）".format(source, target),
        )
    number = decode_decimal(value)
    if number is None:
        raise UnitError("unparsable", "值不可解析为数值")
    return number * Decimal(table[source]), True


def compare(observed: Any, op: str, limit: Any) -> bool:
    """按 ``op`` 比较观测值与限值。

    数值通路用 ``Decimal``；枚举通路用字符串等值。``op`` 已在 schema 层白名单校验。
    """
    if op in ("in", "not_in"):
        pool = limit if isinstance(limit, (list, tuple)) else [limit]
        member = observed in pool
        return member if op == "in" else not member
    if op == "range":
        low, high = limit[0], limit[1]
        return _coerce(low) <= _coerce(observed) <= _coerce(high)
    left = _coerce(observed)
    right = _coerce(limit)
    if op == "<=":
        return left <= right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == ">":
        return left > right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    raise ValueError("未知比较运算符: {0!r}".format(op))


def _coerce(value: Any) -> Any:
    """数值优先，退化为字符串（枚举比较用）。

    **布尔先归一到** ``"true"``/``"false"`` **字符串**：档案是 JSON，布尔项会写成
    字面 ``true``，而规则包统一用字符串承载值；不归一会让"已达标"被误判成不符合。
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    number = decode_decimal(value)
    if number is not None:
        return number
    if isinstance(value, str):
        return value
    return str(value)


def epsilon_for(unit: str) -> Decimal:
    """取该单位的最小计量单位（边界枚举用）。"""
    return Decimal(UNIT_EPSILON.get((unit or "").strip(), "0.1"))
