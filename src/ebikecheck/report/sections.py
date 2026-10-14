"""报告单一渲染源（M5-1，plan/04 §7）。

``report_sections()`` 是报告内容的**唯一事实源**：Markdown 与 XLSX 两个渲染器
都只消费它，"两格式内容一致"由此成为结构性质——渲染器自己不挑数、不补数。

章节纪律（plan/04 §7.2）：

- **§3 参数来源块**渲染成"来源编号"而非超链接（无外链红线：报告离线可审计，
  导出不外发）；URL 本身留在数据侧 ``source_blocks``，不进报告文本；
- **§8 证据指纹**直接消费 :func:`service.evidence_chain` 的载荷（其内部先跑
  :func:`service.assert_traceability`，断言失败抛 ``TraceabilityError`` 拒导出）；
- **生成时间取输入侧**（``generated_at`` 显式参数），不用系统时钟 →
  同输入两次装配的章节载荷逐字节一致。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..engine.findings import (
    NON_COMPLIANT,
    NOT_APPLICABLE,
    NOT_PROVIDED,
    ProfileCheckResult,
)
from ..io_utils import dumps_json, sha256_bytes

#: 章节种类：段落 / 键值表 / 表格 / 列表（渲染器只认这四种）。
KIND_PARAGRAPH = "paragraph"
KIND_KEYVALUES = "keyvalues"
KIND_TABLE = "table"
KIND_LIST = "list"

#: 整改建议文案的单一实现源（§5：建议可执行、按参数分组生成）。
REMEDY_TEXT = (
    "按限值整改后复检：调整该参数至限值允许范围内并保留整改记录，"
    "再以同一档案重新核查确认。"
)


class Section:
    """一个结构化章节：``id``/``title``/``kind`` + 对应载荷。

    ``rows`` 与 ``columns`` 只在表格类章节有意义；``lines`` 承载段落/键值
    （``键 = 值`` 文本对，两渲染器同序消费）与列表载荷。
    """

    def __init__(
        self,
        section_id: str,
        title: str,
        kind: str,
        rows: Optional[List[List[str]]] = None,
        columns: Optional[List[str]] = None,
        lines: Optional[List[str]] = None,
    ):
        self.section_id = section_id
        self.title = title
        self.kind = kind
        self.rows = rows or []
        self.columns = columns or []
        self.lines = lines or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.section_id,
            "title": self.title,
            "kind": self.kind,
            "columns": list(self.columns),
            "rows": [list(row) for row in self.rows],
            "lines": list(self.lines),
        }


#: 结论/维度/条款状态的中文标签（仅展示层用；判定语义在引擎层）。
STATE_LABELS = {
    "compliant": "符合",
    NON_COMPLIANT: "不符合",
    NOT_APPLICABLE: "不适用",
    NOT_PROVIDED: "未提供",
    "not_assessed": "未评估",
}
SCOPE_LABELS = {"vehicle": "整车", "battery": "电池", "charger": "充电器"}
CLAUSE_PENDING_TEXT = "待核对"
SOURCE_KIND_LABELS = {
    "standard_meta": "标准元数据",
    "gov_qna": "官方问答",
    "standard_text": "标准全文",
    "to_verify": "待核对",
}

#: §9 免责声明固定文本（plan/01 §六 口径；改这里即改三处渲染）。
DISCLAIMER_TEXT = (
    "本报告为基于公开标准限值的合规检查发现，不构成产品合格判定、检测结论或行政认定；"
    "正式结论以具备资质的检验检测机构报告与市场监管部门口径为准。"
    "本工具全本地处理存储、零上传；规则包未挂原文核对（pending）的条目不进入核查路径，"
    "并在报告中显式列出。"
)


def _clause_text(block: Dict[str, Any]) -> str:
    if block.get("clause"):
        return str(block["clause"])
    return CLAUSE_PENDING_TEXT


def _source_index(result: ProfileCheckResult) -> Dict[str, str]:
    """把来源 URL 收编成"来源 S1/S2/…"编号表（无外链渲染的单一实现源）。"""
    index: Dict[str, str] = {}
    for dimension in result.dimensions:
        for block in dimension.source_blocks:
            url = str(block.get("source_url", "") or "")
            if url and url not in index:
                index[url] = "S{0}".format(len(index) + 1)
    return index


def _limit_text(block: Dict[str, Any]) -> str:
    limit = block.get("limit")
    if limit is None:
        return "（待核对，未进入核查路径）"
    unit = str(block.get("unit", "") or "")
    text = str(limit)
    return "{0} {1}".format(text, unit) if unit else text


def _state_text(state: str) -> str:
    return STATE_LABELS.get(state, state)


def _observed_text(finding_dict: Dict[str, Any]) -> str:
    observed = finding_dict.get("observed")
    if observed is None:
        return "—"
    return str(observed)


def report_payload_sha256(sections: List[Section]) -> str:
    """章节载荷的规范 JSON sha256（报告指纹的"章节侧"口径）。"""
    payload = [section.to_dict() for section in sections]
    canonical = dumps_json(payload)
    return sha256_bytes(canonical.encode("utf-8"))


def assert_no_external_links(sections: List[Section]) -> None:
    """无外链硬断言：任何章节文本出现 ``http(s)://`` 即拒绝渲染。"""
    for section in sections:
        texts = [section.title, *section.columns, *section.lines]
        for row in section.rows:
            texts.extend(row)
        for text in texts:
            low = text.lower()
            if ("http" in low and "://" in low) or ("www." in low):
                raise ValueError(
                    "报告出现外链（章节 {0}）: {1}".format(section.section_id, text)
                )


# ---- 九章节装配（plan/04 §7.2） ----


def _section_header(
    result: ProfileCheckResult,
    overview: Dict[str, Any],
    evidence: Dict[str, Any],
    generated_at: str,
) -> Section:
    """§1 报告头：规则包坐标 + 工具版本 + 生成时间（输入侧）。"""
    lines = [
        "工具版本 = ebikecheck {0}".format(_tool_version()),
        "报告生成时间（输入侧）= {0}".format(generated_at or "（未提供）"),
        "manifest sha256 = {0}".format(overview["manifest"]["sha256"]),
        "manifest 生成器 = {0} {1}".format(
            overview["manifest"]["generated_by"],
            overview["manifest"]["generator_version"],
        ),
    ]
    for entry in overview["rulesets"]:
        lines.append(
            "规则分册 = {0}（{1}，{2}，生效 {3} 条 / 未启用 {4} 条，sha256 {5}）".format(
                entry["file"],
                entry["standard"],
                SCOPE_LABELS.get(entry["scope"], entry["scope"]),
                entry["effective"],
                len(entry["excluded"]),
                _ruleset_sha256(result, entry),
            )
        )
    lines.append("档案 sha256 = {0}".format(evidence["profile_sha256"]))
    return Section("s1", "报告头（规则包坐标）", KIND_KEYVALUES, lines=lines)


def _ruleset_sha256(result: ProfileCheckResult, entry: Dict[str, Any]) -> str:
    """分册指纹以**本次核查结果**里挂的 sha256 为准（证据链同源）。"""
    for dimension in result.dimensions:
        if dimension.ruleset_file == entry["file"]:
            return dimension.ruleset_sha256
    return "（本次核查未用到该分册）"


def _tool_version() -> str:
    from .. import __version__

    return __version__


def _section_input_facts(
    result: ProfileCheckResult, profile_raw: Dict[str, Any]
) -> Section:
    """§2 输入事实：车型标识 + 锚定 + 参数表（未提供显式列出，不改写输入）。"""
    anchor = result.version_anchor or {}
    lines = [
        "车型编号 = {0}".format(result.profile_id),
        "档案 sha256 = {0}".format(result.profile_sha256),
    ]
    for key, label in (
        ("manufacturer", "制造商"),
        ("uscc", "统一社会信用代码"),
        ("model_design_date", "设计定型日"),
        ("market_date", "上市日"),
    ):
        value = profile_raw.get(key)
        if value:
            lines.append("{0} = {1}".format(label, value))
    lines.append(
        "版本锚定 = {0}（依据 {1} {2}）".format(
            result.version_key,
            anchor.get("basis", ""),
            anchor.get("value", ""),
        )
    )
    rows: List[List[str]] = []
    raw_params = profile_raw.get("params", {}) or {}
    for name in sorted(raw_params):
        item = raw_params[name]
        if isinstance(item, dict):
            value = item.get("value")
            unit = str(item.get("unit", "") or "")
        else:
            value, unit = item, ""
        if value is None:
            shown = "（未提供）"
        elif isinstance(value, bool):
            shown = "true" if value else "false"
        else:
            shown = str(value)
        rows.append([name, shown, unit])
    return Section(
        "s2",
        "输入事实（车型参数，原样列出）",
        KIND_TABLE,
        rows=rows,
        columns=["参数名", "档案值", "单位"],
        lines=lines,
    )


def _section_source_blocks(
    result: ProfileCheckResult, source_index: Dict[str, str]
) -> Section:
    """§3 参数来源块：发布机关/标准号/条款/抓取日期 → 来源编号（**非超链接**）。"""
    rows: List[List[str]] = []
    for dimension in result.dimensions:
        for block in dimension.source_blocks:
            url = str(block.get("source_url", "") or "")
            kind = str(block.get("source_kind", "") or "")
            rows.append(
                [
                    str(block.get("param", "")),
                    SOURCE_KIND_LABELS.get(kind, kind or "（未登记）"),
                    str(block.get("standard", "")),
                    _clause_text(block),
                    _limit_text(block),
                    _source_ref(url, source_index),
                    str(block.get("retrieved_on", "") or "（未登记）"),
                ]
            )
    return Section(
        "s3",
        "参数来源块（数值依据，读者可据此核证）",
        KIND_TABLE,
        rows=rows,
        columns=["参数名", "来源类别", "标准号", "条款号", "限值", "来源编号", "抓取日期"],
    )


def _source_ref(url: str, source_index: Dict[str, str]) -> str:
    """来源 URL → 展示引用（"来源 S#，抓取日期见登记"），绝不渲染 URL 本身。"""
    if url and url in source_index:
        return "来源 {0}（原始链接见随包依据索引，报告不外发链接）".format(source_index[url])
    return "来源未登记"


def _section_findings(result: ProfileCheckResult) -> Section:
    """§4 逐项结论：逐参数四态 + 观测值 + 限值 + 条款依据。"""
    rows: List[List[str]] = []
    for dimension in result.dimensions:
        scope_label = SCOPE_LABELS.get(dimension.scope, dimension.scope)
        applicable = dimension.applicability.get("applicable", True)
        if not applicable:
            rows.append(
                [
                    scope_label,
                    dimension.standard,
                    "—（维度整体不适用）",
                    "—",
                    "—",
                    dimension.applicability.get("reason", ""),
                    "—",
                ]
            )
            continue
        for finding in dimension.findings:
            item = finding.to_dict()
            rows.append(
                [
                    scope_label,
                    str(item.get("standard", "")),
                    str(item.get("param", "")),
                    _state_text(str(item.get("state", ""))),
                    _observed_text(item),
                    _finding_limit(item),
                    _finding_clause(item),
                ]
            )
    return Section(
        "s4",
        "逐项结论（四态）",
        KIND_TABLE,
        rows=rows,
        columns=["维度", "标准号", "参数名", "结论", "观测值", "限值", "条款依据"],
    )


def _finding_limit(item: Dict[str, Any]) -> str:
    limit = item.get("limit")
    if limit is None:
        return "（待核对）"
    unit = str(item.get("unit", "") or "")
    text = "{0} {1}".format(item.get("op", ""), limit)
    return "{0} {1}".format(text, unit) if unit else text


def _finding_clause(item: Dict[str, Any]) -> str:
    clause = item.get("clause")
    if clause:
        return str(clause)
    return CLAUSE_PENDING_TEXT


def _section_violations(result: ProfileCheckResult) -> Section:
    """§5 越限项与整改建议（仅 non_compliant；无则显式写"无"）。"""
    rows: List[List[str]] = []
    for dimension in result.dimensions:
        for finding in dimension.findings:
            if finding.state != NON_COMPLIANT:
                continue
            rows.append(
                [
                    str(finding.param),
                    str(finding.standard),
                    _finding_clause(finding.to_dict()),
                    _finding_limit(finding.to_dict()),
                    _observed_text(finding.to_dict()),
                    REMEDY_TEXT,
                ]
            )
    return Section(
        "s5",
        "越限项与整改建议",
        KIND_TABLE,
        rows=rows,
        columns=["参数名", "标准号", "条款号", "限值", "观测值", "整改建议"],
        lines=["越限 {0} 项。".format(len(rows))],
    )


def _section_not_assessed(result: ProfileCheckResult) -> Section:
    """§6 未评估与未提供 + 被门控排除的规则清单（显式写出，不留空）。"""
    lines: List[str] = []
    not_provided: List[str] = []
    not_applicable: List[str] = []
    for dimension in result.dimensions:
        scope_label = SCOPE_LABELS.get(dimension.scope, dimension.scope)
        for finding in dimension.findings:
            if finding.state == NOT_PROVIDED:
                reason = finding.reason or ""
                not_provided.append(
                    "{0} / {1}（原因 {2}）".format(scope_label, finding.param, reason)
                )
            elif finding.state == NOT_APPLICABLE:
                not_applicable.append(
                    "{0} / {1}（条件不满足，该条对本车型不适用）".format(
                        scope_label, finding.param
                    )
                )
        if not dimension.participates():
            lines.append(
                "{0}维度不参与统一结论聚合：{1}".format(
                    scope_label,
                    dimension.applicability.get("reason", "")
                    or "该标准首期无可参数化限值（零生效规则）",
                )
            )
    lines.append("未提供（不可判定，绝不当作符合）{0} 项：".format(len(not_provided)))
    if not_provided:
        lines.extend("  - {0}".format(item) for item in not_provided)
    else:
        lines.append("  - （无）")
    lines.append("不适用（该条规则对本车型不生效）{0} 项：".format(len(not_applicable)))
    if not_applicable:
        lines.extend("  - {0}".format(item) for item in not_applicable)
    else:
        lines.append("  - （无）")
    excluded_rows: List[List[str]] = []
    for dimension in result.dimensions:
        for item in dimension.excluded_rules:
            excluded_rows.append(
                [
                    SCOPE_LABELS.get(dimension.scope, dimension.scope),
                    item.rule_id,
                    str(item.param),
                    str(item.status),
                    str(item.reason),
                ]
            )
    lines.append("被门控排除、本次核查未启用的规则 {0} 条（不参与任何判定）：".format(len(excluded_rows)))
    return Section(
        "s6",
        "未评估、未提供与门控排除清单",
        KIND_TABLE,
        rows=excluded_rows,
        columns=["维度", "规则 id", "参数名", "状态", "排除原因"],
        lines=lines,
    )


def _section_version_anchor(result: ProfileCheckResult, diff_payload: Dict[str, Any]) -> Section:
    """§7 版本坐标：锚定依据/窗口 + 两版规则包 diff（消费 service.version_diff）。"""
    anchor = result.version_anchor or {}
    lines = [
        "本次核查版本键 = {0}".format(result.version_key),
        "锚定依据 = {0} {1}（{2}）".format(
            anchor.get("basis", ""), anchor.get("value", ""), anchor.get("rule", "")
        ),
        "锚定说明 = {0}".format(anchor.get("note", "") or "—"),
    ]
    old_rs = diff_payload.get("rulesets", {}).get("old", {})
    new_rs = diff_payload.get("rulesets", {}).get("new", {})
    lines.append(
        "版本对照 = {0} → {1}（{2} → {3}）".format(
            diff_payload.get("old_version_key", ""),
            diff_payload.get("new_version_key", ""),
            old_rs.get("file", ""),
            new_rs.get("file", ""),
        )
    )
    counts = diff_payload.get("counts", {})
    lines.append(
        "差异计数 = 新增 {0} / 收紧 {1} / 放宽 {2} / 数值变化 {3} / 判定方式变化 {4} / 废止 {5}".format(
            counts.get("added", 0),
            counts.get("tightened", 0),
            counts.get("relaxed", 0),
            counts.get("value_changed", 0),
            counts.get("operator_changed", 0),
            counts.get("removed", 0),
        )
    )
    rows: List[List[str]] = []
    for entry in diff_payload.get("entries", []):
        if entry.get("kind") == "unchanged":
            continue
        rows.append(
            [
                str(entry.get("param", "")),
                _DIFF_KIND_TEXT.get(entry.get("kind", ""), str(entry.get("kind", ""))),
                _diff_side_text(entry.get("old_side")),
                _diff_side_text(entry.get("new_side")),
                str(entry.get("pairing", "")),
            ]
        )
    return Section(
        "s7",
        "版本坐标与两版差异对照",
        KIND_TABLE,
        rows=rows,
        columns=["参数名", "差异类型", "旧版", "新版", "配对依据"],
        lines=lines,
    )


_DIFF_KIND_TEXT = {
    "added": "新增",
    "removed": "废止",
    "tightened": "收紧",
    "relaxed": "放宽",
    "value_changed": "数值变化",
    "operator_changed": "判定方式变化",
    "unchanged": "不变",
}


def _diff_side_text(side: Any) -> str:
    if not side:
        return "（无要求）"
    unit = str(side.get("unit", "") or "")
    text = "{0} {1}".format(side.get("op", ""), side.get("value", ""))
    if unit:
        text = "{0} {1}".format(text, unit)
    clause = side.get("clause")
    if clause:
        text = "{0}（条款 {1}）".format(text, clause)
    applies_if = side.get("applies_if")
    if applies_if:
        text = "{0}〔条件适用〕".format(text)
    return text


def _section_evidence(
    result: ProfileCheckResult, evidence: Dict[str, Any], sections_so_far: List[Section]
) -> Section:
    """§8 证据指纹：档案 + 报告双 sha256 + 规则包坐标（FR-11）。"""
    lines = [
        "档案 sha256 = {0}".format(evidence["profile_sha256"]),
        "核查结果载荷 sha256 = {0}".format(evidence["report_sha256"]),
        "溯源断言 = {0}".format(evidence["traceability"]),
    ]
    for item in evidence["rulesets"]:
        lines.append(
            "规则分册指纹 = {0}（{1}，{2}）sha256 {3}".format(
                item["file"], item["standard"],
                SCOPE_LABELS.get(item["scope"], item["scope"]), item["sha256"],
            )
        )
    lines.append("章节载荷 sha256 = {0}".format(report_payload_sha256(sections_so_far)))
    return Section("s8", "证据指纹", KIND_KEYVALUES, lines=lines)


def _section_disclaimer() -> Section:
    """§9 免责声明（固定文本，plan/01 §六）。"""
    return Section("s9", "免责声明", KIND_PARAGRAPH, lines=[DISCLAIMER_TEXT])


def report_sections(
    result: ProfileCheckResult,
    profile_raw: Dict[str, Any],
    overview: Dict[str, Any],
    evidence: Dict[str, Any],
    diff_payload: Dict[str, Any],
    generated_at: str = "",
) -> List[Section]:
    """装配报告九章节（内容**单一事实源**；两渲染器只消费本函数输出）。

    参数约定：

    - ``result``：三维核查结果（:class:`service.check_profile` 产物）；
    - ``profile_raw``：**原始档案字典**（§2 不改写输入）；
    - ``overview``：:func:`service.ruleset_overview` 载荷（§1 规则包坐标）；
    - ``evidence``：:func:`service.evidence_chain` 载荷（§8；其内部已先跑
      溯源硬断言，失败即 ``TraceabilityError`` —— 拒绝导出）；
    - ``diff_payload``：:func:`service.version_diff` 载荷（§7 版本对照；
      ``diff`` 子命令同一数据来源，不另写第二份 diff 逻辑）；
    - ``generated_at``：**输入侧**生成时间（档案字段或显式参数），
      不取系统时钟 —— 同输入两次装配逐字节一致。
    """
    source_index = _source_index(result)
    sections: List[Section] = [
        _section_header(result, overview, evidence, generated_at),
        _section_input_facts(result, profile_raw),
        _section_source_blocks(result, source_index),
        _section_findings(result),
        _section_violations(result),
        _section_not_assessed(result),
        _section_version_anchor(result, diff_payload),
    ]
    sections.append(_section_evidence(result, evidence, sections))
    sections.append(_section_disclaimer())
    return sections
