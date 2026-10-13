"""版本锚定：设计/上市日期 → 规则集版本键。

锚点来自 ``manifest.version_anchors``（**不硬编码日期**）；
无日期不猜，返回 ``AMBIGUOUS`` 要求调用方显式指定（见 plan/06 D-06/D-07）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

#: 锚定失败：档案未提供可用于锚定的日期。
AMBIGUOUS = "ambiguous"


class VersionError(Exception):
    """版本锚定不可用（窗口缺失 / 日期格式非法）。"""


def _date_key(text: str) -> Tuple[int, int, int]:
    """``YYYY-MM-DD`` → 可比较元组。日期即字典序可比较，但仍显式解析以便报错。"""
    if not isinstance(text, str):
        raise VersionError("日期必须是字符串: {0!r}".format(text))
    parts = text.split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise VersionError("日期格式应为 YYYY-MM-DD: {0!r}".format(text))
    return int(parts[0]), int(parts[1]), int(parts[2])


def anchor_version(
    profile: Dict[str, Any],
    version_anchors: List[Dict[str, Any]],
    standard_family: str = "GB17761",
) -> Tuple[str, Dict[str, Any]]:
    """返回 ``(version_key, anchor_info)``。

    ``anchor_info`` 记录锚定依据与所命中的窗口，供报告 §7 使用。
    """
    design_date = profile.get("model_design_date")
    market_date = profile.get("market_date")
    basis_name = ""
    basis_value = ""
    if design_date:
        basis_name, basis_value = "model_design_date", design_date
    elif market_date:
        basis_name, basis_value = "market_date", market_date
    else:
        return AMBIGUOUS, {
            "basis": None,
            "value": None,
            "rule": "no_date",
            "note": "档案未提供 model_design_date 或 market_date，无法锚定版本",
        }

    point = _date_key(basis_value)
    windows = [item for item in version_anchors if item.get("standard_family") == standard_family]
    if not windows:
        raise VersionError("manifest 缺少 {0} 的 version_anchors".format(standard_family))

    for window in windows:
        start = window.get("applies_from")
        until = window.get("applies_until")
        if start and point < _date_key(start):
            continue
        if until and point >= _date_key(until):
            continue
        return str(window["version_key"]), {
            "basis": basis_name,
            "value": basis_value,
            "rule": _window_rule_text(window),
            "note": window.get("note", ""),
        }
    raise VersionError(
        "日期 {0} 未命中任何版本窗口（manifest.version_anchors 不完整）".format(basis_value)
    )


def _window_rule_text(window: Dict[str, Any]) -> str:
    pieces = []
    if window.get("applies_from"):
        pieces.append(">={0}".format(window["applies_from"]))
    if window.get("applies_until"):
        pieces.append("<{0}".format(window["applies_until"]))
    return " ".join(pieces) if pieces else "always"


def available_version_keys(
    version_anchors: List[Dict[str, Any]], standard_family: str = "GB17761"
) -> List[str]:
    """该标准族下全部版本键（CLI ``--version-of`` 校验用）。"""
    keys: List[str] = []
    for window in version_anchors:
        if window.get("standard_family") == standard_family:
            key = str(window["version_key"])
            if key not in keys:
                keys.append(key)
    return keys


def default_version_key(version_anchors: List[Dict[str, Any]]) -> Optional[str]:
    """当前生效版本（窗口无 ``applies_until`` 的那个）。"""
    for window in version_anchors:
        if not window.get("applies_until"):
            return str(window.get("version_key"))
    return None
