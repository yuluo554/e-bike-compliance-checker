"""车型档案加载与校验。

档案是**输入契约**：参数值一律字符串承载（避免 JSON float 精度损失），
加载时不做任何数值转换——转换发生在判定层，且缺失/不可解析要在结论里
显式体现为 ``not_provided``，**不能在加载阶段就被悄悄丢掉**。
"""

from __future__ import annotations

import json
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
    return profile_from_dict(raw, path=path, sha256=sha256_file(path))


def profile_from_dict(raw: Any, path: str = "", sha256: str = "") -> Profile:
    """从内存字典构建档案（基准层与测试用；不落盘）。

    与 :func:`load_profile` 走**同一套结构校验** —— 否则基准层会放行
    落盘通路会拒的档案，"基准全绿"就证明不了输入契约。

    ``params`` 条目允许为对象或**标量**：标量即列名映射通路
    （:mod:`engine.mapping`）的输入形状，此处不做形状改写 —— 判定层把
    非对象条目按"缺 value"处理，映射通路在喂入前先归一。
    """
    if not isinstance(raw, dict):
        raise ProfileError("档案顶层必须是对象: {0}".format(path or "<内存>"))
    profile_id = raw.get("profile_id")
    if not profile_id or not isinstance(profile_id, str):
        raise ProfileError("档案缺少 profile_id（string）: {0}".format(path or "<内存>"))
    params = raw.get("params")
    if params is None:
        raise ProfileError("档案缺少 params 对象: {0}".format(path or "<内存>"))
    if not isinstance(params, dict):
        raise ProfileError("档案 params 必须是对象: {0}".format(path or "<内存>"))
    for name, item in params.items():
        if isinstance(item, dict):
            if "value" not in item:
                raise ProfileError("参数 {0} 缺少 value 字段: {1}".format(name, path or "<内存>"))
        elif item is None or isinstance(item, (str, int, float, bool)):
            continue  # 标量列（列名映射通路的输入形状；value 取原样）
        else:
            raise ProfileError(
                "参数 {0} 必须是对象（含 value/unit）或标量: {1}".format(name, path or "<内存>")
            )
    return Profile(path=path, sha256=sha256, profile_id=profile_id, raw=raw)


def profile_sha256_of_content(raw: Dict[str, Any]) -> str:
    """档案**内容**指纹（FR-11）：与文件路径无关，同内容 → 同指纹。

    规范化序列化（``sort_keys`` + 固定分隔符）后取 sha256，使"同一份档案
    在不同文件名/空白格式下"指纹一致；文件级指纹（``Profile.sha256``）保留
    原始字节口径，两者用途分开登记。
    """
    from .io_utils import sha256_bytes

    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(canonical.encode("utf-8"))
