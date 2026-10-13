"""内置评测基准（零 API 依赖、离线可跑）。

门槛**只从 manifest 读**（数据非代码）；``--only`` 未知名 → 退出码 2；
每个套件配**可证伪探活**（注入缺陷后基准必须报未达标）。
"""

from __future__ import annotations

__all__ = ["cases"]
