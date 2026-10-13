"""UTF-8 输出守卫与确定性文件读写工具。

两条纪律：
1. **非 ASCII 输出在窄编码管道不崩**：CI 的 Windows 管道是 cp1252，
   ``print`` 中文会抛 ``UnicodeEncodeError``。入口按 ``stream.encoding``
   探针决定是否 reconfigure（中文控制台 cp936 保持不动）。
2. **落盘确定性**：一律 ``\\n`` 行尾、UTF-8 无 BOM。3.8 上 ``Path.write_text``
   没有 ``newline`` 参数，故统一走显式 ``open``。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from decimal import Decimal
from typing import Any, Iterable, Optional

#: 允许的窄编码集合：探针命中即 reconfigure。
_NARROW_ENCODINGS = {"cp1252", "cp1251", "latin-1", "iso-8859-1", "ascii"}


def _ensure_utf8_stdio() -> None:
    """把 stdout/stderr 切到 UTF-8，仅当当前编码装不下中文时。

    设计要点：不无条件 reconfigure —— 中文控制台（cp936/gbk）本就能打印中文，
    强行切换反而会改变用户终端的既有行为。
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        encoding = (getattr(stream, "encoding", None) or "").lower()
        if encoding in _NARROW_ENCODINGS:
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
            except (AttributeError, ValueError, io.UnsupportedOperation):
                # 非 TextIOWrapper（如被重定向到 BytesIO 的桩）→ 放弃重配，不阻断。
                pass


def sha256_bytes(payload: bytes) -> str:
    """内容的 sha256 十六进制串。"""
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str) -> str:
    """文件内容的 sha256（分块读，容忍大文件）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: str) -> str:
    """读文本，统一把 CRLF/CR 归一到 LF。

    归一在**读入侧**：产物比对的是语义内容，行尾差异不该被误判为内容差异。
    """
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read().replace("\r\n", "\n").replace("\r", "\n")


def write_text(path: str, text: str) -> None:
    """写文本：``\\n`` 行尾、UTF-8 无 BOM、目录自动创建。"""
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_bytes(path: str, payload: bytes) -> None:
    """写字节：目录自动创建。"""
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)


def dumps_json(obj: Any) -> str:
    """确定性 JSON 文本：2 空格缩进、键序保持插入序、非 ASCII 原样保留。"""
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def write_json(path: str, obj: Any) -> None:
    """写确定性 JSON 文件。"""
    write_text(path, dumps_json(obj))


def loads_json(text: str) -> Any:
    """解析 JSON，数值一律走 ``Decimal``。

    判定链路要检出"1 个最小计量单位"的差异（如塑料占比限值与其相邻刻度），
    float 的二进制表示会引入尾差 → 全链路 Decimal（具体限值数值见规则包，
    源码内不得出现，由 ``tools/check_zero_literals.py`` 门禁守门）。
    """
    return json.loads(text, parse_float=Decimal)


def read_json(path: str) -> Any:
    """读并解析 JSON（Decimal 模式）。"""
    return loads_json(read_text(path))


def decode_decimal(value: Any) -> Optional[Decimal]:
    """把标量转成 ``Decimal``；不可解析返回 ``None``（调用方据此判 ``not_provided``）。

    数字与数字串都接受（规则包用字符串承载，档案也允许字符串），
    但**不接受** bool —— ``True`` 在 Python 里是 ``int``，静默当数字会掩盖数据错误。
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except Exception:
            return None
    return None


def iter_text_files(root: str, suffixes: Iterable[str]) -> Iterable[str]:
    """递归枚举指定后缀的文本文件（跳过 ``__pycache__`` 与隐藏目录）。"""
    wanted = tuple(suffixes)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]
        for name in sorted(filenames):
            if name.endswith(wanted):
                yield os.path.join(dirpath, name)
