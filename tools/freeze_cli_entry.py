"""冻结态 CLI 入口（PyInstaller 用）：直接复用 ebikecheck.cli.main。"""

import sys

from ebikecheck.cli import main


if __name__ == "__main__":
    sys.exit(main())
