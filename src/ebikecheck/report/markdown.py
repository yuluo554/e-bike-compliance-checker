"""Markdown 渲染器（M5-1）：**只消费** :mod:`ebikecheck.report.sections`。

确定性纪律（plan/04 §7.3）：

- ``\\n`` 行尾、UTF-8 无 BOM（由调用方 :func:`service.export_report` 统一落盘）；
- 无时间戳、无外链 —— 内容全部来自章节载荷；
- 同输入两次渲染逐字节一致（不触随机源、不触系统时钟）。
"""

from __future__ import annotations

from typing import List

from .sections import (
    KIND_KEYVALUES,
    KIND_TABLE,
    Section,
)

#: Markdown 表格转义字符（管道符会破坏表格结构，必须转义）。
_MD_TABLE_ESCAPE = (
    ("|", "\\|"),
    ("\n", " "),
)


def _cell(text: str) -> str:
    for old, new in _MD_TABLE_ESCAPE:
        text = text.replace(old, new)
    return text


def render_markdown(title: str, sections: List[Section]) -> str:
    """章节列表 → Markdown 文本（含首行标题与章节序号）。"""
    out: List[str] = ["# {0}".format(title), ""]
    for index, section in enumerate(sections, start=1):
        out.append("## {0}. {1}".format(index, section.title))
        out.append("")
        out.extend(_render_body(section))
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def _render_body(section: Section) -> List[str]:
    if section.kind == KIND_TABLE:
        return _render_table(section)
    lines: List[str] = []
    for line in section.lines:
        if line.startswith("  - "):
            # 列表行（_section_not_assessed 已带缩进前缀）→ Markdown 列表项。
            lines.append("- {0}".format(line[4:]))
        elif section.kind == KIND_KEYVALUES and _split_kv(line):
            key, value = _split_kv(line)
            lines.append("- **{0}**: {1}".format(key, _cell(value)))
        else:
            lines.append(line)
    return lines


def _split_kv(line: str):
    """键值行拆分：第一个 ``=``（半角/全角）左侧为键；无等号返回 ``None``。"""
    half = line.find("=")
    full = line.find("＝")
    positions = [p for p in (half, full) if p >= 0]
    if not positions:
        return None
    cut = min(positions)
    key = line[:cut].strip()
    if not key:
        return None
    return key, line[cut + 1:].strip()


def _render_table(section: Section) -> List[str]:
    out: List[str] = []
    for line in section.lines:
        if line.startswith("  - "):
            out.append("- {0}".format(line[4:]))
        else:
            out.append(line)
    if section.columns:
        out.append("| " + " | ".join(_cell(c) for c in section.columns) + " |")
        out.append("|" + "|".join([" --- " for _ in section.columns]) + "|")
        for row in section.rows:
            cells = [_cell(str(value)) for value in row]
            out.append("| " + " | ".join(cells) + " |")
    if not section.rows:
        out.append("（无）")
    return out
