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
    """一次单车型核查的完整结果。"""

    profile_id: str
    ruleset_file: str
    ruleset_sha256: str
    version_key: str
    version_anchor: Dict[str, Any]
    findings: List[Finding] = field(default_factory=list)
    excluded_rules: List[ExcludedRule] = field(default_factory=list)
    profile_sha256: str = ""
    source_blocks: List[Dict[str, Any]] = field(default_factory=list)

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "ebikecheck.result/1.0",
            "profile_id": self.profile_id,
            "ruleset": {"file": self.ruleset_file, "sha256": self.ruleset_sha256},
            "version_key": self.version_key,
            "version_anchor": self.version_anchor,
            "counts": self.counts(),
            "overall": self.overall(),
            "findings": [item.to_dict() for item in self.findings],
            "excluded_rules": [item.to_dict() for item in self.excluded_rules],
            "profile_sha256": self.profile_sha256,
            "source_blocks": self.source_blocks,
        }
