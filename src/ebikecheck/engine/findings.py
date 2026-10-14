"""结论模型与四态/原因码常量。

四态语义见 [plan/04](../../../plan/04-模块详设.md) §2.2 与 §5.2：

- ``compliant``      符合
- ``non_compliant``  不符合（**唯一的"检出问题"**）
- ``not_applicable`` 不适用（``applies_if`` 判定为假）
- ``not_provided``   未提供（不可判定）

**硬约束**：``not_provided`` 与 ``not_applicable`` 都不是"通过"；
一条规则都不适用时整体记 ``not_assessed``，**绝不输出 ``compliant``**。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---- 四态 ----
COMPLIANT = "compliant"
NON_COMPLIANT = "non_compliant"
NOT_APPLICABLE = "not_applicable"
NOT_PROVIDED = "not_provided"
NOT_ASSESSED = "not_assessed"  # 仅用于整体结论，不是单条 finding 的状态

ALL_STATES = (COMPLIANT, NON_COMPLIANT, NOT_APPLICABLE, NOT_PROVIDED)

# ---- 未提供的原因码 ----
REASON_MISSING = "missing"
REASON_NULL_VALUE = "null_value"
REASON_UNPARSABLE = "unparsable"
REASON_UNIT_UNKNOWN = "unit_unknown"
REASON_UNIT_INCOMPATIBLE = "unit_incompatible"
REASON_MAPPING_UNCERTAIN = "mapping_uncertain"
REASON_CONDITION_UNKNOWN = "condition_unknown"
REASON_NO_RULE_FOR_PARAM = "no_rule_for_param"

ALL_REASONS = (
    REASON_MISSING,
    REASON_NULL_VALUE,
    REASON_UNPARSABLE,
    REASON_UNIT_UNKNOWN,
    REASON_UNIT_INCOMPATIBLE,
    REASON_MAPPING_UNCERTAIN,
    REASON_CONDITION_UNKNOWN,
    REASON_NO_RULE_FOR_PARAM,
)

# ---- 严重级（"只报不阻断"用 warning） ----
SEVERITY_NORMAL = "normal"
SEVERITY_WARNING = "warning"

#: 整体结论的"最弱优先"聚合序（越靠前越优先输出）。
OVERALL_PRECEDENCE = (NON_COMPLIANT, NOT_PROVIDED, NOT_ASSESSED, COMPLIANT)

#: 三维（作用域）展示与聚合的固定顺序：整车 → 电池 → 充电器。
DIMENSION_ORDER = ("vehicle", "battery", "charger")


@dataclass
class Finding:
    """一条 (车型档案 × 规则) 的判定结果。"""

    rule_id: str
    param: str
    standard: str
    clause: Optional[str]
    clause_status: str
    op: str
    limit: Any
    unit: str
    observed: Any
    state: str
    reason: Optional[str] = None
    severity: str = SEVERITY_NORMAL
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "param": self.param,
            "standard": self.standard,
            "clause": self.clause,
            "clause_status": self.clause_status,
            "op": self.op,
            "limit": self.limit,
            "unit": self.unit,
            "observed": self.observed,
            "state": self.state,
            "reason": self.reason,
            "severity": self.severity,
            "notes": self.notes,
        }


@dataclass
class ExcludedRule:
    """被 ``status`` 门控排除、**零参与核查**的规则。"""

    rule_id: str
    param: str
    status: str
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "param": self.param,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass
class CheckResult:
    """一次**单维度**核查的完整结果（整车册 / 电池册 / 充电器册各一份）。"""

    profile_id: str
    ruleset_file: str
    ruleset_sha256: str
    version_key: str
    version_anchor: Dict[str, Any]
    findings: List[Finding] = field(default_factory=list)
    excluded_rules: List[ExcludedRule] = field(default_factory=list)
    profile_sha256: str = ""
    source_blocks: List[Dict[str, Any]] = field(default_factory=list)
    #: 维度标识（``vehicle`` / ``battery`` / ``charger``）与该维度的标准号。
    scope: str = ""
    standard: str = ""
    #: 进入该维度核查路径的规则条数（``status=verified``）。0 表示"该标准首期
    #: 无可参数化限值"——这种维度**不参与统一结论聚合**（否则一个没有数值限值的
    #: 标准会把整体结论无谓地拉成"未评估"，见 D-43）。
    effective_rule_count: int = 0
    #: 维度适用性（按标准生效日 vs 档案锚定日判定；见 D-43）。
    applicability: Dict[str, Any] = field(
        default_factory=lambda: {"applicable": True, "reason": ""}
    )

    def counts(self) -> Dict[str, int]:
        """四态计数。"""
        tally = {state: 0 for state in ALL_STATES}
        for item in self.findings:
            tally[item.state] = tally.get(item.state, 0) + 1
        return tally

    def overall(self) -> str:
        """整体结论：按"最弱优先"聚合；``not_applicable`` 不作结论参与。

        ``not_applicable`` 只表示"该规则对本档案不适用"，**不是**对本参数的结论。
        同一参数常有多条互斥条件规则（如铅酸蓄电池车型与其他电池车型各有整车质量
        限值），其中一条不适用、另一条给出结论时，结论必须由适用的那条决定；
        只有**全部**规则都不适用才记 ``not_assessed``，且绝不输出 ``compliant``。
        """
        states = {item.state for item in self.findings}
        if NON_COMPLIANT in states:
            return NON_COMPLIANT
        if NOT_PROVIDED in states:
            return NOT_PROVIDED
        relevant = states - {NOT_APPLICABLE}
        if not relevant:
            return NOT_ASSESSED
        if relevant <= {COMPLIANT}:
            return COMPLIANT
        return NOT_ASSESSED

    def participates(self) -> bool:
        """该维度是否参与统一结论聚合。

        两种"不参与"：① 标准生效日晚于档案锚定日（该标准对本车型不适用）；
        ② 该标准首期无可参数化限值（零生效规则）。两者都不是"查了没问题"，
        故都必须显式记录理由，而不是悄悄算成 ``compliant``。
        """
        if not self.applicability.get("applicable", True):
            return False
        return self.effective_rule_count > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "ebikecheck.result/1.0",
            "profile_id": self.profile_id,
            "scope": self.scope,
            "standard": self.standard,
            "ruleset": {"file": self.ruleset_file, "sha256": self.ruleset_sha256},
            "version_key": self.version_key,
            "version_anchor": self.version_anchor,
            "counts": self.counts(),
            "overall": self.overall(),
            "applicability": dict(self.applicability),
            "effective_rule_count": self.effective_rule_count,
            "findings": [item.to_dict() for item in self.findings],
            "excluded_rules": [item.to_dict() for item in self.excluded_rules],
            "profile_sha256": self.profile_sha256,
            "source_blocks": self.source_blocks,
        }


def aggregate_overall(results: List[CheckResult]) -> str:
    """跨维度统一结论：对**参与聚合**的维度按"最弱优先"取结论。

    次序与单维度一致：``non_compliant`` > ``not_provided`` > ``not_assessed`` >
    ``compliant``（D-43）。零个维度参与 → ``not_assessed``，**绝不输出 compliant**。
    """
    states = [item.overall() for item in results if item.participates()]
    if not states:
        return NOT_ASSESSED
    for candidate in OVERALL_PRECEDENCE:
        if candidate in states:
            return candidate
    return NOT_ASSESSED


@dataclass
class ProfileCheckResult:
    """一份车型档案的**三维（整车/电池/充电器）**核查结果。

    维度顺序固定为整车 → 电池 → 充电器（``DIMENSION_ORDER``），
    使"同一档案两次核查输出逐字节一致"成为结构性质。

    ``findings`` / ``excluded_rules`` / ``counts`` / ``source_blocks`` 是**跨维度并集**的
    只读视图（保持 CLI 与既有调用方的取数姿势不变）；逐维度细节走 ``dimensions``。
    """

    profile_id: str
    profile_sha256: str
    version_key: str
    version_anchor: Dict[str, Any]
    dimensions: List[CheckResult] = field(default_factory=list)

    @property
    def findings(self) -> List[Finding]:
        out: List[Finding] = []
        for dimension in self.dimensions:
            out.extend(dimension.findings)
        return out

    @property
    def excluded_rules(self) -> List[ExcludedRule]:
        out: List[ExcludedRule] = []
        for dimension in self.dimensions:
            out.extend(dimension.excluded_rules)
        return out

    @property
    def source_blocks(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for dimension in self.dimensions:
            out.extend(dimension.source_blocks)
        return out

    def dimension(self, scope: str) -> Optional[CheckResult]:
        for item in self.dimensions:
            if item.scope == scope:
                return item
        return None

    def counts(self) -> Dict[str, int]:
        tally = {state: 0 for state in ALL_STATES}
        for finding in self.findings:
            tally[finding.state] = tally.get(finding.state, 0) + 1
        return tally

    def overall(self) -> str:
        """跨标准统一结论。"""
        return aggregate_overall(self.dimensions)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "ebikecheck.result/2.0",
            "profile_id": self.profile_id,
            "profile_sha256": self.profile_sha256,
            "version_key": self.version_key,
            "version_anchor": self.version_anchor,
            "counts": self.counts(),
            "overall": self.overall(),
            "dimensions": [item.to_dict() for item in self.dimensions],
        }
