"""冻结态 GUI 入口（PyInstaller 用）：解析数据目录 → 启动主窗口。

独立小入口而非 ``ebikecheck.cli``：GUI exe 不需要 argparse 分发，
只需要 paths 定位 + gui.app（cli 模块保留给 cli exe 复用）。
"""

import sys

from ebikecheck.io_utils import _ensure_utf8_stdio
from ebikecheck.paths import find_data_dir


def main() -> int:
    _ensure_utf8_stdio()
    data_dir = find_data_dir()
    if data_dir is None:
        print(
            "错误: 找不到随包数据目录（rules/manifest.json）。\n"
            "请保持 ebikecheck-gui.exe 与 _internal/data 的相对布局不变。",
            file=sys.stderr,
        )
        return 2
    from ebikecheck.gui.app import launch

    return launch()


if __name__ == "__main__":
    sys.exit(main())
