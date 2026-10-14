"""演示素材程序化产出（M5-5，plan/05 §四 M5）：PNG + GIF。

确定性纪律：

- 固定帧序/尺寸/调色板，全部像素由**显式函数** ``_frame_pixels`` 给出
  （不触系统时钟/随机源）；
- PNG：自写最小编码器（索引色 + 固定 zlib level → 逐字节确定）；
- GIF：Pillow 编码（LZW 手写实现与 GIF 规范的码长/表满边界对不齐，见
  M5 收尾记录；Pillow 编码完全确定 → 同样满足"两次生成 sha256 一致"）；
- 两次生成 sha256 一致（测试守门）。

内容：三帧"工作台画面"示意——单车核查（三维页签结论分布条）、批量扫描
（结论分布柱状）、版本差异（差异类型计数条）。这是**程序生成的示意图**
（尺寸 640×360，16 色调色板），不是界面截图。
"""

from __future__ import annotations

import io
import struct
import zlib
from typing import List

WIDTH = 640
HEIGHT = 360
FRAME_COUNT = 3
FRAME_DELAY_CSEC = 100  # 每帧 1 秒（百分秒）

#: 16 色固定调色板（RGB；索引 0 = 背景米白，1 = 墨色文字，2..= 语义色）。
PALETTE = (
    (245, 243, 238),  # 0 背景
    (40, 42, 46),     # 1 文字/边框
    (208, 49, 47),    # 2 不符合（红）
    (232, 135, 39),   # 3 未提供（橙）
    (120, 124, 130),  # 4 不适用（灰）
    (46, 125, 92),    # 5 符合（绿）
    (36, 84, 156),    # 6 主色（蓝）
    (255, 255, 255),  # 7 白
    (222, 226, 230),  # 8 浅灰
    (24, 62, 120),    # 9 深蓝
    (0, 0, 0),        # 10 黑
    (252, 200, 90),   # 11 强调黄
    (94, 168, 140),   # 12 淡绿
    (170, 190, 220),  # 13 淡蓝
    (240, 205, 200),  # 14 淡红
    (128, 96, 160),   # 15 紫
)

STATE_BARS = {
    "frame0": [(2, 90 + 6), (3, 40 + 8), (4, 20 + 4), (5, 280)],   # 单车核查：三维四态条
    "frame1": [(5, 210), (2, 72), (3, 36), (4, 18)],   # 批量扫描：结论分布
    "frame2": [(6, 150), (2, 60), (5, 120)],           # 版本差异：类型计数
}

FRAME_TITLES = (
    "dan-che-he-cha / single profile check",
    "pi-liang-sao-miao / batch scan",
    "ban-ben-cha-yi / version diff",
)

FRAME_SUBTITLES = (
    "3D matrix: vehicle + battery + charger",
    "failures isolated, exit code semantics kept",
    "generated from ruleset diff, not hand-written",
)


def _frame_pixels(frame_index: int) -> List[List[int]]:
    """一帧的索引色像素（行优先；显式几何，无随机/时钟）。"""
    grid = [[0] * WIDTH for _ in range(HEIGHT)]
    _rect(grid, 0, 0, WIDTH, HEIGHT, 0)
    # 顶栏
    _rect(grid, 0, 0, WIDTH, 40, 6)
    _text_blocks(grid, 12, 12, FRAME_TITLES[frame_index], 1, 7)
    # 副标题
    _text_blocks(grid, 12, 52, FRAME_SUBTITLES[frame_index], 1, 8)
    # 结论条：等高横条，宽度按固定值
    bars = STATE_BARS["frame{0}".format(frame_index)]
    y = 96
    for color, length in bars:
        _rect(grid, 40, y, length, 32, color)
        _rect(grid, 40, y, 2, 32, 1)
        y += 40 + 8
    # 底部页脚：帧号块
    _rect(grid, 0, HEIGHT - 28, WIDTH, 28, 8)
    for i in range(FRAME_COUNT):
        _rect(grid, 12 + i * 24, HEIGHT - 22, 16, 16, 6 if i == frame_index else 13)
    return grid


def _rect(grid, x0, y0, w, h, color):
    for y in range(y0, min(y0 + h, HEIGHT)):
        row = grid[y]
        for x in range(x0, min(x0 + w, WIDTH)):
            row[x] = color


def _text_blocks(grid, x0, y0, text, color, bg):
    """伪文字：每个字符一个 8×14 色块（不渲染真实字形 —— 素材是示意图）。"""
    x = x0
    for _ in text:
        _rect(grid, x, y0, 6, 12, color)
        _rect(grid, x + 6, y0, 2, 12, bg)
        x += 8


# ---- PNG 编码（最小：8-bit 索引色 + 固定 zlib） ----


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def encode_png(pixels: List[List[int]]) -> bytes:
    """索引色 PNG（PLTE + IDAT，zlib level 固定 → 逐字节确定）。"""
    raw = b"".join(
        b"\x00" + bytes(row) for row in pixels  # 滤波 0（None）逐行
    )
    ihdr = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 3, 0, 0, 0)
    plte = b"".join(bytes(entry) for entry in PALETTE)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"PLTE", plte)
        + _png_chunk(b"IDAT", zlib.compress(raw, 6))
        + _png_chunk(b"IEND", b"")
    )


# ---- GIF 编码（最小：87a 逻辑 + 全局调色板 + LZW） ----


def build_png_assets() -> List[bytes]:
    """三帧各自成 PNG（截图素材）。"""
    return [encode_png(_frame_pixels(index)) for index in range(FRAME_COUNT)]


def build_gif_asset() -> bytes:
    """三帧合成一个 GIF（动图素材；Pillow 编码，确定性见模块 docstring）。"""
    from PIL import Image

    frames: List[Image.Image] = []
    for index in range(FRAME_COUNT):
        pixels = _frame_pixels(index)
        flat = bytes(value for row in pixels for value in row)
        image = Image.frombytes("P", (WIDTH, HEIGHT), flat)
        image.putpalette([component for entry in PALETTE for component in entry])
        frames.append(image)
    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DELAY_CSEC * 10,
        loop=0,
        optimize=False,
    )
    return buffer.getvalue()


def write_assets(out_dir: str) -> List[str]:
    """落盘全部素材（PNG 逐帧 + GIF 动图），返回写出的路径清单。"""
    import os
    import sys

    _HERE = os.path.dirname(os.path.abspath(__file__))
    _ROOT = os.path.dirname(_HERE)
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    if os.path.join(_ROOT, "src") not in sys.path:
        sys.path.insert(0, os.path.join(_ROOT, "src"))
    from ebikecheck.io_utils import write_bytes

    paths = []
    for index, png in enumerate(build_png_assets()):
        path = os.path.join(out_dir, "demo-frame{0}.png".format(index))
        write_bytes(path, png)
        paths.append(path)
    gif_path = os.path.join(out_dir, "demo-overview.gif")
    write_bytes(gif_path, build_gif_asset())
    paths.append(gif_path)
    return paths


def main(argv=None) -> int:
    import argparse
    import hashlib
    import os
    import sys

    _HERE = os.path.dirname(os.path.abspath(__file__))
    _ROOT = os.path.dirname(_HERE)
    for candidate in (_ROOT, os.path.join(_ROOT, "src")):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    from ebikecheck.io_utils import _ensure_utf8_stdio

    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="程序化产出演示素材（PNG + GIF）")
    parser.add_argument("--out-dir", default=os.path.join("docs", "assets"))
    args = parser.parse_args(argv)

    paths = write_assets(args.out_dir)
    for path in paths:
        with open(path, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        print("{0}  {1}".format(digest, path))
    print("DEMO_ASSETS_OK ({0} 件)".format(len(paths)))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
