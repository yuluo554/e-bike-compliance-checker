"""字段映射引擎（FR-08）：厂家参数表列名 → 标准参数名。

数据侧唯一来源是 ``data/mapping/mapping.json``（M1 备好，M3 由本模块消费）：

- ``parameters[].variants``   —— 已登记的列名变体（如「最高车速」→ ``max_design_speed``）；
- ``parameters[].ambiguous_variants`` —— **歧义列名**（如「车速」既可指最高车速也可指
  设计车速），命中即判 ``mapping_uncertain``，**绝不猜**；
- ``unit_aliases`` —— 单位别名表，经 :func:`engine.values.unit_alias_index` 反转后
  由 :func:`engine.values.resolve_unit` 消费；映射引擎解析"列名 + 单位"时走
  **同一张表**（D-44），不另建第二份口径。

纪律：未登记列名 → ``not_provided(missing)``（不臆测）；同一变体登记到两个参数
由 ``gen_mapping.py`` 与 ``test_mapping_covers_every_rule_package_param`` 守门，
本模块加载时同样断言（防御性，不信任数据侧）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

from .findings import REASON_MAPPING_UNCERTAIN

#: 映射判定三态（与结论四态解耦：映射层只负责"列名 → 参数"这一步）。
MAPPED = "mapped"                      # 精确命中已登记变体
UNCERTAIN = "uncertain"                # 命中歧义列名（mapping_uncertain，绝不猜）
UNMAPPED = "unmapped"                  # 未登记（missing；调用方按 not_provided 处理）

_MAPPING_CACHE: Dict[str, Any] = {"path": None, "table": None}


class MappingError(Exception):
    """映射表不可用或自相矛盾（同一变体映射到两个参数）。"""


class ParamMapping:
    """一份映射表的内存态（加载时一次校验，之后零成本查询）。"""

    def __init__(self, raw: Dict[str, Any]) -> None:
        self.variants: Dict[str, str] = {}
        self.ambiguous: Dict[str, List[str]] = {}
        self.units: Dict[str, str] = {}
        self.param_count = 0
        for item in raw.get("parameters") or []:
            param = str(item.get("param", ""))
            if not param:
                raise MappingError("映射表存在缺 param 的条目")
            self.param_count += 1
            unit = str(item.get("unit", ""))
            if unit:
                self.units[param] = unit
            for variant in item.get("variants") or []:
                token = str(variant)
                owner = self.variants.get(token)
                if owner is not None and owner != param:
                    raise MappingError(
                        "列名变体 {0!r} 同时映射到 {1} 与 {2}（歧义必须登记进 ambiguous_variants）".format(
                            token, owner, param
                        )
                    )
                self.variants[token] = param
            for variant in item.get("ambiguous_variants") or []:
                token = str(variant)
                self.ambiguous.setdefault(token, []).append(param)

    def resolve(self, column: str) -> Tuple[str, Optional[str]]:
        """列名 → ``(判定, 参数名或 None)``。

        顺序：精确变体优先（确定性），其次歧义表；都未命中 → ``unmapped``。
        """
        token = (column or "").strip()
        if not token:
            return UNMAPPED, None
        owner = self.variants.get(token)
        if owner is not None:
            return MAPPED, owner
        candidates = self.ambiguous.get(token)
        if candidates:
            return UNCERTAIN, None
        return UNMAPPED, None

    def target_unit(self, param: str) -> Optional[str]:
        """参数的规范单位（无量纲/枚举参数无单位 → ``None``）。"""
        return self.units.get(param)


def load_param_mapping(data_dir: Optional[str] = None) -> ParamMapping:
    """加载映射表；文件缺失时**显式报错**（映射是功能前提，不像单位别名可退化）。

    与 :func:`engine.values.unit_alias_index` 同读 ``data/mapping/mapping.json``
    一个文件，但语义不同：单位别名缺失可退化为"按原样比对"，而字段映射缺失
    会让"列名映射"这个功能整体不可用 —— 必须显式失败而不是静默空表。
    """
    if data_dir is None:
        from ..paths import find_data_dir

        data_dir = find_data_dir()
    path = os.path.join(data_dir or "", "mapping", "mapping.json")
    if _MAPPING_CACHE["path"] == path and _MAPPING_CACHE["table"] is not None:
        return _MAPPING_CACHE["table"]
    if not os.path.isfile(path):
        raise MappingError("找不到映射表 {0}（请先运行 tools/gen_mapping.py）".format(path))
    from ..io_utils import read_json

    table = ParamMapping(read_json(path))
    _MAPPING_CACHE["path"] = path
    _MAPPING_CACHE["table"] = table
    return table


def normalize_params(
    columns: Dict[str, Any],
    table: Optional[ParamMapping] = None,
    data_dir: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """把"厂家列名参数表"归一成"标准参数名参数表"（进入 ``Profile.params`` 的形状）。

    输入 ``columns``: ``{列名: {"value": ..., "unit": ...} 或 标量}``；
    输出只含**能确定的**参数：

    - 精确命中 → 以标准参数名收编（单位走别名表归一，与判定层同一通路）；
    - 歧义列名 → 对其全部候选参数注入 ``{"value": null, "reason": "mapping_uncertain"}``
      标记（判定层见标记即出 ``not_provided(mapping_uncertain)``，绝不猜）；
    - 未登记列名 → 丢弃（判定层对其自然落到 ``not_provided(missing)``，
      与"参数缺失"同一结论路径，不新增判定语义）。
    """
    if table is None:
        table = load_param_mapping(data_dir)
    out: Dict[str, Dict[str, Any]] = {}
    uncertain: List[str] = []
    unmapped: List[str] = []
    for column in sorted(columns):
        verdict, param = table.resolve(column)
        if verdict == UNCERTAIN:
            uncertain.append(column)
            continue
        if verdict == UNMAPPED:
            unmapped.append(column)
            continue
        entry = columns[column]
        if not isinstance(entry, dict):
            entry = {"value": entry}
        item: Dict[str, Any] = dict(entry)
        unit = table.target_unit(param)
        if unit and not item.get("unit"):
            # 列定义带规范单位而条目缺单位：补目标单位，让"列名能映射"不因
            # 表头省略单位而退化为 unit_unknown（档案仍可显式覆盖）。
            item.setdefault("unit", unit)
        out[param] = item
    for column in uncertain:
        # 歧义列名：对它可能指到的每个候选参数注入"映射不确定"标记 —— 判定层
        # 见标记即出 ``not_provided(mapping_uncertain)``，绝不猜具体取值。
        for candidate in table.ambiguous.get(column, []):
            if candidate not in out:
                item = {"value": None, "reason": REASON_MAPPING_UNCERTAIN}
                unit = table.target_unit(candidate)
                if unit:
                    item["unit"] = unit
                out[candidate] = item
    return out


def mapping_report(
    columns: Dict[str, Any],
    table: Optional[ParamMapping] = None,
    data_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """映射过程报告（机读；FR-08 验收与报告"输入事实"节的数据来源）。"""
    if table is None:
        table = load_param_mapping(data_dir)
    mapped: List[Dict[str, Any]] = []
    uncertain: List[Dict[str, Any]] = []
    unmapped: List[str] = []
    for column in sorted(columns):
        verdict, param = table.resolve(column)
        if verdict == MAPPED:
            mapped.append({"column": column, "param": param})
        elif verdict == UNCERTAIN:
            uncertain.append({"column": column, "reason": REASON_MAPPING_UNCERTAIN})
        else:
            unmapped.append(column)
    return {
        "schema": "ebikecheck.mapping/1.0",
        "mapped": mapped,
        "uncertain": uncertain,
        "unmapped": unmapped,
        "param_count": table.param_count,
    }
