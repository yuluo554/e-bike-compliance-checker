"""M5-5 演示素材测试：程序化产出、逐字节可复现、可解码。

完成判据（plan/05 §四 M5）：PNG + GIF 固定帧序/尺寸/调色板，
两次生成 sha256 一致。
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

from conftest import ROOT, TOOLS

_SPEC_PATH = os.path.join(TOOLS, "gen_demo_assets.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("gen_demo_assets", _SPEC_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def demo():
    return _load_module()


def test_demo_assets_are_deterministic(demo):
    """同输入两次构建 → PNG/GIF 逐字节一致（无时钟/随机源）。"""
    png_first = demo.build_png_assets()
    png_second = demo.build_png_assets()
    assert png_first == png_second
    assert demo.build_gif_asset() == demo.build_gif_asset()


def test_demo_assets_fixed_geometry_and_frames(demo):
    assert len(demo.build_png_assets()) == demo.FRAME_COUNT == 3
    for png in demo.build_png_assets():
        # PNG 签名 + IHDR 宽高（大端）与常量一致。
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        width = int.from_bytes(png[16:20], "big")
        height = int.from_bytes(png[20:24], "big")
        assert (width, height) == (demo.WIDTH, demo.HEIGHT)
    gif = demo.build_gif_asset()
    assert gif[:6] == b"GIF89a"
    assert gif[-1:] == b"\x3B"
    width = int.from_bytes(gif[6:8], "little")
    height = int.from_bytes(gif[8:10], "little")
    assert (width, height) == (demo.WIDTH, demo.HEIGHT)
    # 帧数 = 图像描述符（0x2C）计数。
    assert gif.count(b"\x2C") >= demo.FRAME_COUNT


def test_demo_assets_are_png_and_gif_decodable(demo):
    """产物可被标准解码器读回（Pillow 可用即真解码；缺席则跳过）。"""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow 未安装，跳过解码校验")
    for index, png in enumerate(demo.build_png_assets()):
        import io

        image = Image.open(io.BytesIO(png))
        image.load()
        assert image.size == (demo.WIDTH, demo.HEIGHT)
    import io

    gif = Image.open(io.BytesIO(demo.build_gif_asset()))
    assert getattr(gif, "n_frames", 1) == demo.FRAME_COUNT
    for frame in range(demo.FRAME_COUNT):
        gif.seek(frame)
        gif.convert("RGB")


def test_committed_assets_match_generator(tmp_path):
    """docs/assets 里入库的素材与生成器当前输出一致（防手工替换/漂移）。"""
    module = _load_module()
    assets_dir = os.path.join(ROOT, "docs", "assets")
    if not os.path.isdir(assets_dir):
        pytest.skip("docs/assets 未生成")
    from ebikecheck.io_utils import sha256_bytes

    for index, png in enumerate(module.build_png_assets()):
        path = os.path.join(assets_dir, "demo-frame{0}.png".format(index))
        assert os.path.isfile(path)
        with open(path, "rb") as handle:
            assert sha256_bytes(handle.read()) == sha256_bytes(png)
    gif_path = os.path.join(assets_dir, "demo-overview.gif")
    with open(gif_path, "rb") as handle:
        assert sha256_bytes(handle.read()) == sha256_bytes(module.build_gif_asset())


def test_cli_entry_writes_assets(tmp_path, demo):
    """命令行入口能落盘全部素材。"""
    out_dir = str(tmp_path / "assets")
    paths = demo.write_assets(out_dir)
    assert len(paths) == demo.FRAME_COUNT + 1
    for path in paths:
        assert os.path.isfile(path) and os.path.getsize(path) > 0
