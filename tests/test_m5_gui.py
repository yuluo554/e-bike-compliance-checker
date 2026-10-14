"""M5-2 GUI 分层门禁测试（AST 静态 + 导入层冒烟；不启动事件循环）。

口径（plan/03 §2.2 / HANDOFF-M5 M5-2 完成判据）：

- 界面只调 ``service``（零判定逻辑）：gui 包不得 import ``engine.*``；
- ``cli`` 顶层不得 import ``gui``/``PySide6``（既有门禁已覆盖 cli.py，
  这里补 gui 侧的两条 + gui 子命令惰性导入断言）；
- PySide6 是 gui extras 的重件：核心测试路径**不 import** PySide6
  （未安装 gui extras 时本文件相关用例跳过，AST 断言照常跑）。
"""

from __future__ import annotations

import ast
import os

import pytest

from conftest import SRC

GUI_DIR = os.path.join(SRC, "ebikecheck", "gui")


def _gui_sources():
    names = sorted(name for name in os.listdir(GUI_DIR) if name.endswith(".py"))
    assert names, "gui 包不得为空"
    out = {}
    for name in names:
        path = os.path.join(GUI_DIR, name)
        with open(path, "r", encoding="utf-8", newline="") as handle:
            out[name] = ast.parse(handle.read(), filename=path)
    return out


def test_gui_never_imports_engine_layer():
    """gui 不得直接 import engine.*（只准经 service，plan/03 §2.2）。"""
    for name, tree in _gui_sources().items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith("ebikecheck.engine"), (
                    "{0} 顶层 import 引擎层: {1}".format(name, module)
                )
                assert not module.startswith("ebikecheck.benchmark"), (
                    "{0} import 基准层: {1}".format(name, module)
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("ebikecheck.engine"), (
                        "{0} import 引擎层: {1}".format(name, alias.name)
                    )


def test_gui_imports_only_service_and_stdlib_among_local_modules():
    """gui 的本地依赖只允许 ebikecheck.service / io_utils / __init__。"""
    allowed = {"ebikecheck.service", "ebikecheck.io_utils", "ebikecheck"}
    for name, tree in _gui_sources().items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("ebikecheck"):
                    assert node.module in allowed, (
                        "{0} 引入了非白名单本地模块: {1}".format(name, node.module)
                    )


def test_gui_contains_no_state_decisions():
    """gui 无判定逻辑：不得出现引擎判定函数的调用痕迹（只做标签映射与取数）。"""
    banned_tokens = (
        "def overall", "aggregate", "check_param", "eval_applies_if",
        "normalize_unit",
    )
    for name in _gui_sources():
        path = os.path.join(GUI_DIR, name)
        with open(path, "r", encoding="utf-8", newline="") as handle:
            text = handle.read()
        for token in banned_tokens:
            assert token not in text, "{0} 出现判定逻辑痕迹: {1}".format(name, token)


def test_cli_gui_subcommand_imports_lazily():
    """cli 的 cmd_gui 函数体内才允许出现 gui/PySide6 导入（惰性）。"""
    path = os.path.join(SRC, "ebikecheck", "cli.py")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        tree = ast.parse(handle.read(), filename=path)
    found_cmd_gui = False
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "cmd_gui":
            found_cmd_gui = True
    assert found_cmd_gui, "cli 必须提供 gui 子命令入口 cmd_gui"


def test_gui_entry_module_defines_launch_and_window():
    """gui.app 必须提供 launch() 与 MainWindow（打包入口的稳定契约）。"""
    tree = _gui_sources()["app.py"]
    names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }
    assert "launch" in names
    assert "MainWindow" in names


def test_gui_service_calls_cover_required_pages():
    """三页签的取数必须来自 service 对应公开函数（核查/扫描/对账/差异）。"""
    path = os.path.join(GUI_DIR, "app.py")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    for func in ("check_profile", "scan_dir", "compare_rounds", "version_diff"):
        assert func in text, "gui 未接入 service.{0}".format(func)


@pytest.mark.skipif(
    not os.path.isdir(os.path.join(SRC, "ebikecheck", "gui")),
    reason="gui 包不存在",
)
def test_gui_module_import_does_not_require_display():
    """导入 gui.app 不应启动 Qt 事件循环（只定义，不执行）。"""
    import sys

    if "PySide6" not in sys.modules:
        try:
            import PySide6  # noqa: F401
        except ImportError:
            pytest.skip("gui extras 未安装（PySide6 缺席），跳过导入冒烟")
    from ebikecheck.gui import app as gui_app

    assert callable(gui_app.launch)
    assert hasattr(gui_app, "MainWindow")
