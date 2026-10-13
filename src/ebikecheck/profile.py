"""车型档案加载与校验。

档案是**输入契约**：参数值一律字符串承载（避免 JSON float 精度损失），
加载时不做任何数值转换——转换发生在判定层，且缺失/不可解析要在结论里
显式体现为 ``not_provided``，**不能在加载阶段就被悄悄丢掉**。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .io_utils import read_json, sha256_file


class ProfileError(Exception):
    """档案不可用（缺文件 / 结构非法）→ 调用方退出码 2。"""


@dataclass
class Profile:
    """一份车型参数档案。"""

    path: str
    sha256: str
    profile_id: str
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def params(self) -> Dict[str, Any]:
        return dict(self.raw.get("params", {}) or {})

    @property
    def manufacturer(self) -> str:
        return str(self.raw.get("manufacturer", ""))

    @property
    def model_design_date(self) -> Optional[str]:
        return self.raw.get("model_design_date")

    @property
    def market_date(self) -> Optional[str]:
        return self.raw.get("market_date")

    def param_names(self):
        return sorted(self.params)


def load_profile(path: str) -> Profile:
    """加载并校验档案结构。"""
    if not os.path.isfile(path):
        raise ProfileError("档案文件不存在: {0}".format(path))
    raw = read_json(path)
    if not isinstance(raw, dict):
        raise ProfileError("档案顶层必须是对象: {0}".format(path))
    profile_id = raw.get("profile_id")
    if not profile_id or not isinstance(profile_id, str):
        raise ProfileError("档案缺少 profile_id（string）: {0}".format(path))
    params = raw.get("params")
    if params is None:
        raise ProfileError("档案缺少 params 对象: {0}".format(path))
    if not isinstance(params, dict):
        raise ProfileError("档案 params 必须是对象: {0}".format(path))
    for name, item in params.items():
        if not isinstance(item, dict):
            raise ProfileError(
                "参数 {0} 必须是对象（含 value/unit）: {1}".format(name, path)
            )
        if "value" not in item:
            raise ProfileError("参数 {0} 缺少 value 字段: {1}".format(name, path))
    return Profile(path=path, sha256=sha256_file(path), profile_id=profile_id, raw=raw)
