# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec（M5-3）：onedir 双 exe —— ebikecheck-gui（主）+ ebikecheck-cli。

纪律（plan/05 §四 M5）：

- **onedir**（GUI 必须 ≥6：5.x 扫 PySide6 字节码确定性崩）；
- 冻结态数据随包走：``data/`` 整目录进包（paths.py 冻结分支按
  ``exe 目录/_internal/data`` 探测，PyInstaller ≥6 的 onedir 布局即此）；
- 打包根 = 仓库根；产物在 ``dist/ebikecheck-desktop/``。
"""

import os

ROOT = os.path.dirname(SPECPATH)

datas = [
    (os.path.join(ROOT, "data"), "data"),
]

hiddenimports = [
    "ebikecheck.gui.app",
]

a = Analysis(
    [os.path.join(ROOT, "tools", "freeze_gui_entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "setuptools"],
    noarchive=False,
)
a_cli = Analysis(
    [os.path.join(ROOT, "tools", "freeze_cli_entry.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "setuptools"],
    noarchive=False,
)
pyz = PYZ(a.pure)
pyz_cli = PYZ(a_cli.pure)

exe_gui = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ebikecheck-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="ebikecheck-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe_gui,
    exe_cli,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ebikecheck-desktop",
)
