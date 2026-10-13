"""对账语义的**单一实现源** —— 测试与基准共用，避免双口径漂移。

真值语义（[plan/05](../../../plan/05-数据计划与里程碑.md) §2.2）：

- ``expect.findings`` 是主期望；``also_expect`` 是同一构造隐含的其余结论；
- 对账按"该档案**全部可判定规则**的结论集合"逐项比对，不只比主期望；
- ``expect_findings: []`` 显式声明"应零命中"；
- ``expect_severity_warning: true`` 显式声明"应降级"。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..engine.findings import CheckResult


def expected_states(case: Dict[str, Any]) -> Dict[str, str]:
    """合并主期望与隐含期望（``also_expect`` 不得与主期望冲突）。"""
    merged: Dict[str, str] = {}
    for source in (case.get("expect", {}).get("findings", {}), case.get("also_expect", {})):
        for param, state in (source or {}).items():
            if param in merged and merged[param] != state:
                raise ValueError(
                    "真值自相矛盾: 参数 {0} 期望 {1} 与 {2} 冲突".format(
                        param, merged[param], state
                    )
                )
            merged[param] = state
    return merged


def observed_states(result: CheckResult) -> Dict[str, str]:
    """档案实际的逐参数结论。

    同一参数可能有多条规则（如 ``vehicle_mass`` 受铅蓄电池/其他两条约束），
    取**最弱结论**（不符合 > 未提供 > 不适用 > 符合），与 ``CheckResult.overall`` 同序。
    """
    order = {"non_compliant": 0, "not_provided": 1, "not_applicable": 2, "compliant": 3}
    tally: Dict[str, str] = {}
    for finding in result.findings:
        current = tally.get(finding.param)
        if current is None or order.get(finding.state, 9) < order.get(current, 9):
            tally[finding.param] = finding.state
    return tally


def compare_case(result: CheckResult, case: Dict[str, Any]) -> List[str]:
    """对账单例；返回差异描述列表（空 = 一致）。"""
    problems: List[str] = []
    expected = expected_states(case)
    observed = observed_states(result)

    for param, want in sorted(expected.items()):
        got = observed.get(param)
        if got is None:
            problems.append("参数 {0}: 期望 {1}，但无对应结论（规则未覆盖）".format(param, want))
        elif got != want:
            problems.append("参数 {0}: 期望 {1}，实际 {2}".format(param, want, got))

    if "expect_overall" in case:
        want_overall = case["expect_overall"]
        got_overall = result.overall()
        if got_overall != want_overall:
            problems.append("整体结论: 期望 {0}，实际 {1}".format(want_overall, got_overall))

    if case.get("expect_findings") is not None and not case["expect_findings"]:
        hits = [f.param for f in result.findings if f.state == "non_compliant"]
        if hits:
            problems.append("声明应零命中，但检出不符合: {0}".format(", ".join(sorted(hits))))

    if case.get("expect_severity_warning"):
        warned = [f.param for f in result.findings if f.severity == "warning"]
        if not warned:
            problems.append("声明应降级为 warning，但无任何降级结论")

    return problems


def compare_cases(
    results: Dict[str, CheckResult], cases: List[Dict[str, Any]]
) -> Tuple[int, List[str]]:
    """对账一组用例；返回 ``(通过数, 问题列表)``。"""
    passed = 0
    problems: List[str] = []
    for case in cases:
        case_id = case["case_id"]
        result = results.get(case_id)
        if result is None:
            problems.append("{0}: 缺少核查结果".format(case_id))
            continue
        issues = compare_case(result, case)
        if issues:
            for issue in issues:
                problems.append("{0}: {1}".format(case_id, issue))
        else:
            passed += 1
    return passed, problems


def observed_nonpass(result: CheckResult) -> List[Tuple[str, str]]:
    """本次核查的"非通过"集合 = ``non_compliant`` ∪ ``not_provided``。

    跨轮对账（M3）与评测共用这一口径：**"没看到"不算"缺失"**，
    但"未提供"是"没检查完"，必须能与"符合"区分开。
    """
    out: List[Tuple[str, str]] = []
    for finding in result.findings:
        if finding.state in ("non_compliant", "not_provided"):
            out.append((finding.param, finding.state))
    return sorted(out)


def overall_of(results: List[CheckResult]) -> Optional[str]:
    """一组结果的整体结论（批量扫描用；空集合返回 ``None``）。"""
    if not results:
        return None
    from ..engine.findings import OVERALL_PRECEDENCE

    states = {item.overall() for item in results}
    for candidate in OVERALL_PRECEDENCE:
        if candidate in states:
            return candidate
    return None
