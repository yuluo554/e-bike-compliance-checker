"""电动自行车合规核查工作台（核心层零第三方依赖）。

本包只承载确定性判定：限值来自随包规则库（``data/rules/``），
源码内不得出现任何限值数值（由 ``tools/check_zero_literals.py`` 门禁守门）。
"""

from __future__ import annotations

__version__ = "0.1.1"
__all__ = ["__version__"]
