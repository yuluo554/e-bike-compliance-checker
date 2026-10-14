"""参数 × 限值判定矩阵（四态）。

判定序严格按 [plan/04](../../../plan/04-模块详设.md) §4.1，先短路：

1. ``applies_if`` 为假 → ``not_applicable``；为 unknown → ``not_provided(condition_unknown)``
2. 参数缺失/为空 → ``not_provided(missing|null_value)``
3. 值不可解析 → ``not_provided(unparsable)``
4. 单位不可用 → ``not_provided(unit_unknown|unit_incompatible)``
5. 比较 → ``compliant`` / ``non_compliant``（发生换算则降级 ``warning``）

**"未提供参数"绝不判为符合**——这是本项目最容易被攻击的假合规点。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .findings import (
    COMPLIANT,
    NON_COMPLIANT,
    NOT_APPLICABLE,
    NOT_PROVIDED,
    REASON_CONDITION_UNKNOWN,
    REASON_MAPPING_UNCERTAIN,
    REASON_MISSING,
    REASON_NULL_VALUE,
    REASON_UNIT_INCOMPATIBLE,
    REASON_UNIT_UNKNOWN,
    REASON_UNPARSABLE,
    SEVERITY_NORMAL,
    SEVERITY_WARNING,
    Finding,
)
from .rules import Rule, eval_applies_if
from .values import UnitError, compare, normalize_unit


def _observed_text(value: Any) -> Optional[str]:
    """把观测值转成可输出文本；``None`` 表示"未提供"。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def check_param(rule: Rule, params: Dict[str, Any]) -> Finding:
    """对单条规则判定一个车型档案参数。"""
    base = {
        "rule_id": rule.id,
        "param": rule.param,
        "standard": rule.standard_code,
        "clause": rule.clause,
        "clause_status": rule.clause_status,
        "op": rule.op,
        "limit": rule.value,
        "unit": rule.unit,
    }

    condition = eval_applies_if(rule.applies_if, params)
    if condition is False:
        return Finding(observed=None, state=NOT_APPLICABLE, **base)
    if condition is None:
        return Finding(
            observed=None,
            state=NOT_PROVIDED,
            reason=REASON_CONDITION_UNKNOWN,
            **base
        )

    provided = params.get(rule.param)
    if not isinstance(provided, dict):
        return Finding(observed=None, state=NOT_PROVIDED, reason=REASON_MISSING, **base)
    if provided.get("reason") == REASON_MAPPING_UNCERTAIN:
        # 字段映射层的"歧义列名"标记（engine.mapping.normalize_params 注入）：
        # 列名能对上参数但语义有歧义（如「车速」）→ 显式未提供，绝不猜值。
        return Finding(observed=None, state=NOT_PROVIDED, reason=REASON_MAPPING_UNCERTAIN, **base)
    raw_value = provided.get("value")
    if raw_value is None:
        return Finding(observed=None, state=NOT_PROVIDED, reason=REASON_NULL_VALUE, **base)

    unit_target = rule.unit or ""
    if unit_target.strip() == "" or unit_target.lower() in ("none", "text", "bool"):
        # 无量纲/枚举通路：直接比较原值。
        try:
            ok = compare(raw_value, rule.op, rule.value)
        except (ValueError, TypeError):
            return Finding(
                observed=_observed_text(raw_value),
                state=NOT_PROVIDED,
                reason=REASON_UNPARSABLE,
                **base
            )
        return Finding(
            observed=_observed_text(raw_value),
            state=COMPLIANT if ok else NON_COMPLIANT,
            **base
        )

    try:
        number, downgraded = normalize_unit(raw_value, provided.get("unit", ""), unit_target)
    except UnitError as error:
        reason = (
            REASON_UNIT_UNKNOWN
            if error.reason == "unit_unknown"
            else REASON_UNIT_INCOMPATIBLE
            if error.reason == "unit_incompatible"
            else REASON_UNPARSABLE
        )
        return Finding(
            observed=_observed_text(raw_value),
            state=NOT_PROVIDED,
            reason=reason,
            notes=str(error),
            **base
        )

    ok = compare(number, rule.op, rule.value)
    return Finding(
        observed=str(number),
        state=COMPLIANT if ok else NON_COMPLIANT,
        severity=SEVERITY_WARNING if downgraded else SEVERITY_NORMAL,
        notes="单位已由 {0} 换算为 {1}".format(provided.get("unit", ""), unit_target)
        if downgraded
        else "",
        **base
    )


def check_params(rules: List[Rule], params: Dict[str, Any]) -> List[Finding]:
    """对一组规则判定同一档案的全部参数。"""
    return [check_param(rule, params) for rule in rules]


def collect_source_blocks(rules: List[Rule]) -> List[Dict[str, Any]]:
    """汇总"参数来源块"（报告 §3，NFR-09）。

    使读者**不开仓库也能核证**"这个数值哪来的"。
    """
    blocks: List[Dict[str, Any]] = []
    for rule in rules:
        blocks.append(
            {
                "param": rule.param,
                "standard": rule.standard_code,
                "clause": rule.clause,
                "clause_status": rule.clause_status,
                "limit": rule.value,
                "unit": rule.unit,
                "source_kind": rule.source.get("kind"),
                "source_url": rule.source.get("url", ""),
                "retrieved_on": rule.source.get("retrieved_on", ""),
            }
        )
    return blocks
