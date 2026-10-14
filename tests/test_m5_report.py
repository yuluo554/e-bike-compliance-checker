"""M5-1 报告导出测试：单一渲染源 / 两格式对等 / 逐字节可复现 / 无外链。

口径来源：plan/04 §7 与 HANDOFF-M5 §二 M5-1 的完成判据。
"""

from __future__ import annotations

import json
import os
import re
import zipfile

import pytest

from conftest import DATA, ROOT, param

from ebikecheck.report.markdown import render_markdown
from ebikecheck.report.sections import (
    KIND_PARAGRAPH,
    KIND_TABLE,
    Section,
    assert_no_external_links,
    report_payload_sha256,
    report_sections,
)
from ebikecheck.report.xlsx import ZIP_COMPRESSION, ZIP_DATE_TIME, build_xlsx
from ebikecheck.service import (
    check_profile,
    check_profile_dict,
    evidence_chain,
    export_report,
    ruleset_overview,
    version_diff,
)

#: 测试档案固定生成时间（输入侧；绝不取系统时钟）。
GENERATED_AT = "2026-10-14T00:00:00Z"

_URL_LIKE = re.compile(r"(?i)(https?://|www\.)")


@pytest.fixture(scope="module")
def rich_profile_path(tmp_path_factory):
    """一份覆盖四态的档案（符合/不适用/未提供/越限全齐）。"""
    payload = {
        "schema": "ebikecheck.profile/1.0",
        "profile_id": "SYN-EB-REPORT",
        "manufacturer": "示例车业（合成）有限公司",
        "uscc": "90000000SYN0000001X",
        "model_design_date": "2025-10-01",
        "params": {
            "max_design_speed": param("25", "km/h"),
            "vehicle_mass": param("58", "kg"),
            "battery_type": param("lead_acid"),
            "plastic_mass_ratio": param("5.1", "%"),
            "nominal_voltage": param("48", "V"),
            "motor_rated_power": param("350", "W"),
            "over_speed_power_cutoff": param(True),
            "anti_tamper_battery_pack": param(True),
            "anti_tamper_controller": param(True),
            "anti_tamper_speed_limiter": param(True),
            "charger_no_load_output_voltage": param("42.4", "V"),
        },
    }
    path = os.path.join(str(tmp_path_factory.mktemp("report")), "SYN-EB-REPORT.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


@pytest.fixture(scope="module")
def assembled(rich_profile_path):
    """单次核查 → 章节载荷 + 双渲染产物（模块级缓存，测试只读）。"""
    result = check_profile(rich_profile_path, DATA)
    evidence = evidence_chain(result)
    sections = report_sections(
        result=result,
        profile_raw=json.load(open(rich_profile_path, encoding="utf-8")),
        overview=ruleset_overview(DATA),
        evidence=evidence,
        diff_payload=version_diff(DATA),
        generated_at=GENERATED_AT,
    )
    title = "电动自行车合规核查报告 — {0}（{1}）".format(
        result.profile_id, result.version_key
    )
    return {
        "result": result,
        "evidence": evidence,
        "sections": sections,
        "markdown": render_markdown(title, sections),
        "xlsx": build_xlsx(title, sections),
    }


# ---- 单一渲染源与章节纪律 ----


def test_sections_cover_nine_fixed_chapters(assembled):
    ids = [section.section_id for section in assembled["sections"]]
    assert ids == ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9"]


def test_sections_are_deterministic(rich_profile_path, assembled):
    """同输入两次装配 → 章节载荷逐项一致（无系统时钟/随机源参与）。"""
    result = check_profile(rich_profile_path, DATA)
    again = report_sections(
        result=result,
        profile_raw=json.load(open(rich_profile_path, encoding="utf-8")),
        overview=ruleset_overview(DATA),
        evidence=evidence_chain(result),
        diff_payload=version_diff(DATA),
        generated_at=GENERATED_AT,
    )
    assert report_payload_sha256(again) == report_payload_sha256(assembled["sections"])


def test_source_urls_never_enter_section_text(assembled):
    """§3 来源块渲染成"来源编号"——URL 只留在数据侧，不进章节文本。"""
    for section in assembled["sections"]:
        texts = [section.title, *section.columns, *section.lines]
        for row in section.rows:
            texts.extend(row)
        for text in texts:
            assert not _URL_LIKE.search(text), "章节 {0} 出现 URL: {1}".format(
                section.section_id, text
            )


def test_source_blocks_section_carries_clause_and_retrieval(assembled):
    s3 = next(s for s in assembled["sections"] if s.section_id == "s3")
    assert s3.kind == KIND_TABLE
    header = s3.columns
    for expected in ("标准号", "条款号", "来源编号", "抓取日期"):
        assert expected in header
    assert s3.rows, "来源块表不得为空（每个生效规则都有来源）"


def test_disclaimer_is_fixed_text(assembled):
    s9 = next(s for s in assembled["sections"] if s.section_id == "s9")
    assert s9.kind == KIND_PARAGRAPH
    assert any("不构成产品合格判定" in line for line in s9.lines)


def test_not_provided_listed_explicitly(assembled):
    """§6 显式列出未提供（绝不悄悄当符合）。"""
    s6 = next(s for s in assembled["sections"] if s.section_id == "s6")
    joined = "\n".join(s6.lines)
    assert "未提供" in joined
    assert "不参与统一结论聚合" in joined


# ---- 无外链硬断言 ----


def test_no_external_links_assertion_passes_on_real_report(assembled):
    assert_no_external_links(assembled["sections"])


def test_no_external_links_assertion_rejects_url():
    bad = [Section("x", "t", KIND_PARAGRAPH, lines=["见 https://example.org 说明"])]
    with pytest.raises(ValueError):
        assert_no_external_links(bad)


def test_markdown_product_has_no_external_link(assembled):
    assert not _URL_LIKE.search(assembled["markdown"])


def test_xlsx_product_no_external_links_outside_schema_namespaces(assembled):
    """XLSX 单元格与自定义 rels 里无外链。

    OOXML 规范要求的固定 schema 命名空间串（spreadsheetml/content-types 等）
    是**格式自身的 URL，不是报告外链**——它们出现在每个正常 xlsx 文件里，
    判定只针对单元格文本与 worksheet/核心属性内容。
    """
    import io

    archive = zipfile.ZipFile(io.BytesIO(bytes(assembled["xlsx"])))
    for info in archive.infolist():
        text = archive.read(info.filename).decode("utf-8")
        if info.filename.endswith(".xml") or info.filename.endswith(".rels"):
            # 去掉 XML 命名空间声明与 OOXML 关系 Type/TargetMode 的**规范固定 URI**
            # （它们是格式自身的标识，不是报告外链；出现在每个正常 xlsx 里）。
            stripped = re.sub(r'xmlns(:\w+)?="[^"]*"', "", text)
            stripped = re.sub(r'Type="http://schemas\.openxmlformats\.org/[^"]*"', "", stripped)
            assert not _URL_LIKE.search(stripped), "成员 {0} 出现外链".format(info.filename)


# ---- 逐字节可复现 ----


def test_markdown_render_is_byte_reproducible(assembled):
    again = render_markdown(
        "电动自行车合规核查报告 — {0}（{1}）".format(
            assembled["result"].profile_id, assembled["result"].version_key
        ),
        assembled["sections"],
    )
    assert again == assembled["markdown"]


def test_markdown_has_no_timestamp_and_uses_lf(assembled):
    assert "\r" not in assembled["markdown"]
    assert GENERATED_AT in assembled["markdown"]  # 输入侧时间在位


def test_renderers_import_no_clock_or_random():
    """渲染器不得 import 时间/随机模块（逐字节复现的结构性来源）。"""
    import ast

    for name in ("markdown.py", "xlsx.py", "sections.py"):
        path = os.path.join(ROOT, "src", "ebikecheck", "report", name)
        with open(path, "r", encoding="utf-8", newline="") as handle:
            tree = ast.parse(handle.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in ("time", "datetime", "random"), name
            elif isinstance(node, ast.ImportFrom):
                top = (node.module or "").split(".")[0]
                assert top not in ("time", "datetime", "random"), name


def test_xlsx_zip_members_are_frozen(assembled):
    import io

    archive = zipfile.ZipFile(io.BytesIO(assembled["xlsx"]))
    for info in archive.infolist():
        assert info.date_time == ZIP_DATE_TIME
        assert info.compress_type == ZIP_COMPRESSION
        assert info.create_system == 0


def test_xlsx_build_is_byte_reproducible(assembled):
    again = build_xlsx(
        "电动自行车合规核查报告 — {0}（{1}）".format(
            assembled["result"].profile_id, assembled["result"].version_key
        ),
        assembled["sections"],
    )
    assert again == assembled["xlsx"]


def test_xlsx_is_valid_zip_with_ten_sheets(assembled):
    import io

    archive = zipfile.ZipFile(io.BytesIO(assembled["xlsx"]))
    assert archive.testzip() is None
    names = [info.filename for info in archive.infolist()]
    sheets = [name for name in names if name.startswith("xl/worksheets/sheet")]
    assert len(sheets) == 10  # 目录 + 九章节


# ---- 两格式内容逐项对等 ----


def _md_section_bodies(markdown_text):
    bodies = {}
    chunks = re.split(r"^## ", markdown_text, flags=re.M)[1:]
    for chunk in chunks:
        lines = chunk.splitlines()
        number_title = lines[0]
        number = number_title.split(".", 1)[0].strip()
        bodies[number] = lines[1:]
    return bodies


def _xlsx_sheet_cells(xlsx_bytes):
    """从 worksheet XML 抽出每行文本（inlineStr 单一形态，无需完整解析器）。"""
    import io
    import xml.etree.ElementTree as ET

    archive = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    sheets = {}
    for name in sorted(
        n.filename for n in archive.infolist() if n.filename.startswith("xl/worksheets/sheet")
    ):
        root = ET.fromstring(archive.read(name))
        rows = []
        for row in root.findall(".//m:row", ns):
            cells = [
                "".join(t.text or "" for t in cell.findall(".//m:t", ns))
                for cell in row.findall("m:c", ns)
            ]
            rows.append(cells)
        sheets[name] = rows
    return sheets


def test_markdown_and_xlsx_sections_are_equivalent(assembled):
    """对等断言：MD 每章节标题 + 表格行/键值 在 XLSX 中逐项可回查。"""
    md_bodies = _md_section_bodies(assembled["markdown"])
    assert len(md_bodies) == 9
    sheets = _xlsx_sheet_cells(assembled["xlsx"])
    sheet_texts = {}
    for name, rows in sheets.items():
        texts = []
        for row in rows:
            texts.extend(cell for cell in row if cell)
        sheet_texts[name] = texts
    for index, section in enumerate(assembled["sections"], start=1):
        # 章节标题两格式都在（XLSX 目录 sheet + 章节 sheet 名）。
        assert str(section.title) in assembled["markdown"]
        title_found = any(
            section.title in " ".join(texts) for texts in sheet_texts.values()
        )
        assert title_found, "章节 {0} 标题在 XLSX 中缺失".format(section.section_id)
        # 表格行逐行进 XLSX。
        for row in section.rows:
            joined = " | ".join(str(value) for value in row)
            found = any(
                all(str(value) in texts for value in row if str(value))
                for texts in sheet_texts.values()
            )
            assert found, "章节 {0} 的行在 XLSX 中缺失: {1}".format(section.section_id, joined)
        # 键值/段落行逐行进 XLSX。
        for line in section.lines:
            probe = line[4:] if line.startswith("  - ") else line
            if not probe:
                continue
            found = any(probe in " ".join(texts) for texts in sheet_texts.values())
            assert found, "章节 {0} 的行在 XLSX 中缺失: {1}".format(section.section_id, probe)


# ---- service.export_report 端到端 ----


def test_export_report_writes_both_files_and_returns_hashes(rich_profile_path, tmp_path):
    out_dir = os.path.join(str(tmp_path), "out")
    payload = export_report(
        rich_profile_path, out_dir, DATA, generated_at=GENERATED_AT
    )
    assert os.path.isfile(payload["markdown_path"])
    assert os.path.isfile(payload["xlsx_path"])
    with open(payload["markdown_path"], "rb") as handle:
        assert payload["markdown_sha256"] == _sha256_of(handle.read())
    with open(payload["xlsx_path"], "rb") as handle:
        assert payload["xlsx_sha256"] == _sha256_of(handle.read())
    assert payload["evidence"]["traceability"] == "ok"


def test_export_report_is_byte_reproducible(rich_profile_path, tmp_path):
    first = export_report(rich_profile_path, str(tmp_path / "a"), DATA, generated_at=GENERATED_AT)
    second = export_report(rich_profile_path, str(tmp_path / "b"), DATA, generated_at=GENERATED_AT)
    assert first["markdown_sha256"] == second["markdown_sha256"]
    assert first["xlsx_sha256"] == second["xlsx_sha256"]


def test_export_report_refuses_untraceable_result(tmp_path):
    """溯源断言失败 → 拒绝导出（evidence_chain 硬门前置）。"""
    from ebikecheck.engine.findings import ProfileCheckResult
    from ebikecheck.service import TraceabilityError

    # 内存通路核查（与 CLI 同一装配）会因缺日期被拒；此处直接给显式版本键。
    raw = {
        "schema": "ebikecheck.profile/1.0",
        "profile_id": "SYN-EB-NOHASH",
        "model_design_date": "2025-10-01",
        "params": {"max_design_speed": param("25", "km/h")},
    }
    result = check_profile_dict(raw, DATA)
    broken = ProfileCheckResult(
        profile_id=result.profile_id,
        profile_sha256="",
        version_key=result.version_key,
        version_anchor=dict(result.version_anchor),
        dimensions=result.dimensions,
    )
    with pytest.raises(TraceabilityError):
        evidence_chain(broken)


def test_export_report_generated_at_defaults_to_blank_not_clock(rich_profile_path, tmp_path):
    """不显式给生成时间 → 记"（未提供）"，绝不取系统时钟。"""
    payload = export_report(rich_profile_path, str(tmp_path), DATA)
    assert payload["generated_at"] == ""
    with open(payload["markdown_path"], "r", encoding="utf-8") as handle:
        text = handle.read()
    assert "（未提供）" in text


def test_cli_export_subcommand_smoke(rich_profile_path, tmp_path, capsys):
    from ebikecheck.cli import main

    out_dir = str(tmp_path / "cli-out")
    code = main(
        [
            "export",
            rich_profile_path,
            "--out-dir",
            out_dir,
            "--generated-at",
            GENERATED_AT,
            "--json",
        ]
    )
    assert code in (0, 1)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert os.path.isfile(payload["markdown_path"])
    assert os.path.isfile(payload["xlsx_path"])


def _sha256_of(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()
