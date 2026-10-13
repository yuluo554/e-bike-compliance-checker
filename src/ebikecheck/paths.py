"""数据目录定位（``find_data_dir``）与仓库根定位。

查找优先级（[plan/03](../../plan/03-架构与技术选型.md) §六，改动会打挂测试）：

1. 显式 ``explicit`` 参数
2. 环境变量 ``EBIKECHECK_DATA_DIR``
3. 冻结态（PyInstaller）：``sys._MEIPASS/data`` → ``exe 目录/_internal/data``
   → ``exe 目录/data``（5.x 平铺布局）
4. 源码态：包内上溯 ``../../data`` → CWD 上溯
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

ENV_DATA_DIR = "EBIKECHECK_DATA_DIR"
_MARKER = os.path.join("rules", "manifest.json")


def is_frozen() -> bool:
    """是否运行在 PyInstaller 冻结态。"""
    return bool(getattr(sys, "frozen", False))


def _has_marker(path: str) -> bool:
    """目录是否是一个有效数据根（含 ``rules/manifest.json``）。"""
    return bool(path) and os.path.isfile(os.path.join(path, _MARKER))


def _frozen_candidates() -> List[str]:
    """冻结态候选目录。"""
    candidates: List[str] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "data"))
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidates.append(os.path.join(exe_dir, "_internal", "data"))
    candidates.append(os.path.join(exe_dir, "data"))
    return candidates


def _source_candidates(anchor: Optional[str]) -> List[str]:
    """源码态候选目录：从给定锚点逐级上溯找 ``data/``。"""
    base = os.path.abspath(anchor or os.getcwd())
    candidates: List[str] = []
    current = base
    for _ in range(6):
        candidates.append(os.path.join(current, "data"))
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return candidates


def data_dir_candidates(explicit: Optional[str] = None, anchor: Optional[str] = None) -> List[str]:
    """按优先级返回候选数据目录（供诊断输出）。"""
    ordered: List[str] = []
    if explicit:
        ordered.append(os.path.abspath(explicit))
    env_value = os.environ.get(ENV_DATA_DIR)
    if env_value:
        ordered.append(os.path.abspath(env_value))
    if is_frozen():
        ordered.extend(_frozen_candidates())
        # 冻结态仍允许源码树兜底（开发期直接跑脚本构建产物）。
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        ordered.extend(_source_candidates(os.path.join(pkg_dir, "..", "..")))
    else:
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        ordered.extend(_source_candidates(os.path.join(pkg_dir, "..", "..")))
        ordered.extend(_source_candidates(anchor))
    # 去重且保持顺序
    seen = set()
    unique: List[str] = []
    for item in ordered:
        normalized = os.path.normpath(item)
        if normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique


def find_data_dir(explicit: Optional[str] = None, anchor: Optional[str] = None) -> Optional[str]:
    """定位数据根；找不到返回 ``None``（由调用方决定退出码）。

    **显式参数是用户指令，不留退路**：一旦显式给了 ``data_dir`` 而它不含
    ``rules/manifest.json``，立即返回 ``None`` —— 若在此处静默回落到其他候选，
    就会出现"用户以为在测 A、实际测了 B"的假绿（测错对象家族）。
    """
    if explicit:
        candidate = os.path.abspath(explicit)
        return candidate if _has_marker(candidate) else None
    for candidate in data_dir_candidates(explicit, anchor):
        if _has_marker(candidate):
            return candidate
    return None


def within(child: str, parent: str) -> bool:
    """``child`` 是否落在 ``parent`` 之内（冻结态自检用）。"""
    try:
        child_abs = os.path.abspath(child)
        parent_abs = os.path.abspath(parent)
        return os.path.commonpath([child_abs, parent_abs]) == parent_abs
    except ValueError:
        # 跨盘符（C: 与 D:）→ commonpath 抛 ValueError，视为不在其内。
        return False


def exe_dir() -> str:
    """当前解释器/可执行文件所在目录。"""
    return os.path.dirname(os.path.abspath(sys.executable))
