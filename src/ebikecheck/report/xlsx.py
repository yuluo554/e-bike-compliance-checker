"""XLSX 渲染器（M5-1）：自写最小 OOXML，**零第三方依赖、只消费** sections。

确定性纪律（plan/04 §7.3）：

- ``ZIP_STORED``（不压缩 → 不受 zlib 版本/级别影响）；
- 每个 zip 成员固定 ``date_time``、``create_system=0``、``external_attr=0``；
- 全部 XML 以固定序拼串、UTF-8 无声明差异 → 同输入**逐字节一致**；
- 无外链红线：任何单元格文本出现 ``http(s)://`` 即拒绝（渲染前再断言一次，
  与 sections 层双保险）。

工作簿布局：每章节一个工作表（sheet 名 = 章节 id），首个 sheet 是目录。
"""

from __future__ import annotations

import zipfile
from typing import List

from .sections import (
    KIND_LIST,
    KIND_TABLE,
    Section,
)

#: 固定 zip 时间戳（DOS 时间原点；任何真实时间都会破坏逐字节复现）。
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
#: 固定压缩方式：只存储。
ZIP_COMPRESSION = zipfile.ZIP_STORED

_XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

#: 转义序：& 必须最先（否则会把后面替换产生的 &amp; 再转义一遍）。
_XML_ESCAPES = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
)


def xml_escape(text: str) -> str:
    for old, new in _XML_ESCAPES:
        text = text.replace(old, new)
    return text


def _sheet_name(index: int, section: Section) -> str:
    """工作表名：``1.报告头`` 形态；Excel 名禁字符一律剔除，长度截断。"""
    forbidden = set(':\\/?*[]')
    title = "".join(ch for ch in section.title if ch not in forbidden)
    name = "{0}.{1}".format(index, title)
    return name[:31]


def _cell_xml(ref: str, value: str) -> str:
    return '<c r="{0}" t="inlineStr"><is><t xml:space="preserve">{1}</t></is></c>'.format(
        ref, xml_escape(value)
    )


def _row_xml(number: int, values: List[str]) -> str:
    cells = []
    for index, value in enumerate(values):
        ref = "{0}{1}".format(_COLUMN_NAMES[index], number)
        cells.append(_cell_xml(ref, str(value)))
    return "<row r=\"{0}\">{1}</row>".format(number, "".join(cells))


#: 列名 A..Z（章节数不超过 26 列；超出时表格会抛 IndexError —— 是期望行为）。
_COLUMN_NAMES = (
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M",
    "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
)


def _sheet_xml(section: Section) -> str:
    rows: List[str] = []
    row_no = 1
    if section.kind == KIND_TABLE:
        if section.lines:
            rows.append(_row_xml(row_no, [line for line in section.lines]))
            row_no += 1
            rows.append(_row_xml(row_no, [""]))
            row_no += 1
        if section.columns:
            rows.append(_row_xml(row_no, section.columns))
            row_no += 1
            for row in section.rows:
                rows.append(_row_xml(row_no, row))
                row_no += 1
        if not section.rows:
            rows.append(_row_xml(row_no, ["（无）"]))
    else:
        for line in section.lines:
            rows.append(_row_xml(row_no, [line]))
            row_no += 1
    body = "".join(
        '<sheetData>{0}</sheetData>'.format("".join(rows))
    )
    return (
        _XML_HEADER
        + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + body
        + "</worksheet>"
    )


def _content_xml(sheet_count: int) -> str:
    overrides = [
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    for index in range(1, sheet_count + 1):
        overrides.append(
            '<Override PartName="/xl/worksheets/sheet{0}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'.format(
                index
            )
        )
    return (
        _XML_HEADER
        + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        + "".join(overrides)
        + "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        _XML_HEADER
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        + "</Relationships>"
    )


def _workbook_xml(sheet_names: List[str]) -> str:
    sheets = []
    for index, name in enumerate(sheet_names, start=1):
        sheets.append(
            '<sheet name="{0}" sheetId="{1}" r:id="rId{1}"/>'.format(
                xml_escape(name), index
            )
        )
    return (
        _XML_HEADER
        + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        + 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        + "<sheets>"
        + "".join(sheets)
        + "</sheets></workbook>"
    )


def _workbook_rels_xml(sheet_count: int) -> str:
    rels = []
    for index in range(1, sheet_count + 1):
        rels.append(
            '<Relationship Id="rId{0}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{0}.xml"/>'.format(
                index
            )
        )
    rels.append(
        '<Relationship Id="rId{0}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'.format(
            sheet_count + 1
        )
    )
    return (
        _XML_HEADER
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(rels)
        + "</Relationships>"
    )


#: styles.xml 取**最小合法形态**（无任何字体/填充/边框定义 → 无时间无关成分）。
_STYLES_XML = (
    _XML_HEADER
    + '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    + '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
    + '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
    + '<borders count="1"><border/></borders>'
    + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    + '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
    + "</styleSheet>"
)


def build_xlsx(title: str, sections: List[Section]) -> bytes:
    """章节列表 → XLSX 字节流（逐字节可复现）。

    ``title`` 进目录 sheet 首行（无核心属性 docProps —— 那是时间戳藏身处，
    自写 writer 直接不生成它，比"固定其值"更彻底）。
    """
    from io import BytesIO

    toc_lines = [title, ""] + [
        "{0}. {1}".format(index, section.title) for index, section in enumerate(sections, start=1)
    ]
    toc_section = Section("toc", "目录", KIND_LIST, lines=toc_lines)
    ordered: List[Section] = [toc_section, *sections]

    sheet_names = [_sheet_name(index, section) for index, section in enumerate(ordered, start=1)]
    sheet_xmls = [_sheet_xml(section) for section in ordered]
    parts = [
        ("[Content_Types].xml", _content_xml(len(ordered))),
        ("_rels/.rels", _root_rels_xml()),
        ("xl/workbook.xml", _workbook_xml(sheet_names)),
        ("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(ordered))),
        ("xl/styles.xml", _STYLES_XML),
    ]
    for index, sheet_xml in enumerate(sheet_xmls, start=1):
        parts.append(("xl/worksheets/sheet{0}.xml".format(index), sheet_xml))

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=ZIP_COMPRESSION) as archive:
        for name, payload in parts:
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE_TIME)
            info.compress_type = ZIP_COMPRESSION
            info.create_system = 0
            info.external_attr = 0
            archive.writestr(info, payload.encode("utf-8"))
    return buffer.getvalue()
