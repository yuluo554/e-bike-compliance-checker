"""版本差异对照（FR-07，M4）：两版规则包 diff → 差异表。

差异表**从两版规则包本身 diff 生成**（plan/04 §6.3 的硬要求），不手写、不读
真值库 —— 规则包更新后差异表自动跟着变，"报告与规则包一致"成为结构性质。

配对语义（逐参数）：

- 同一参数在两版各有规则 → 按 ``applies_if`` 归组比较（同条件比同条件；
  一侧无条件、另一侧条件拆分时，以"对应条件缺失"侧的无条件规则与拆分后
  **每个条件分支**分别配对 —— 例：旧版整车质量限值无条件、新版按电池类型
  拆成两条，则与铅酸分支配对比出"放宽"、与其他电池分支配对比出"不变"）；
- 仅新版有 → ``added``（新增）；
- 仅旧版有 → ``removed``（废止）；
- 两版都有且 ``value`` 不同 → 数值变化，按"严格程度"细分为
  ``tightened``（收紧）/ ``relaxed``（放宽）—— 比较只对**同向**的
  阈值类运算符（``<=`` 降 / ``>=`` 升 / ``in`` 收缩 / ``not_in`` 扩张）有意义；
  ``==``/``!=`` 与跨运算符的 ``value`` 变化如实记 ``value_changed``，不硬套方向；
- 两版都有且 ``op`` 不同但 ``value`` 相同 → ``operator_changed``。

纪律：本模块是**纯函数 diff**——只消费 :class:`engine.rules.Rule`，不碰文件
系统、不做判定；服务层负责加载两版分册并传入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .findings import Finding
from .rules import Rule

#: 差异类型。
DIFF_ADDED = "added"                  # 新增：仅新版有
DIFF_REMOVED = "removed"              # 废止：仅旧版有
DIFF_TIGHTENED = "tightened"          # 强化：同向阈值收紧
DIFF_RELAXED = "relaxed"              # 放宽：同向阈值放宽
DIFF_VALUE_CHANGED = "value_changed"  # 数值变化（方向不适用，如 == 目标改变）
DIFF_OPERATOR_CHANGED = "operator_changed"  # 运算符变化（value 相同）
DIFF_UNCHANGED = "unchanged"          # 无实质差异（op 与 value 均一致）

#: 携带"程度方向"语义的阈值运算符（可判收紧/放宽）。
_THR_OPS = ("<=", "<", ">", ">=")

#: 参数级"最弱结论"的优先序（与 ``benchmark.cases.observed_states`` 同源同序）。
_STATE_ORDER = {"non_compliant": 0, "not_provided": 1, "compliant": 2}


@dataclass
class ParamDiff:
    """一个参数在两版规则包之间的差异（含配对依据）。"""

    param: str
    kind: str
    #: 旧版配对规则 id / 新版配对规则 id（单侧缺失时为 None）。
    old_rule_id: Optional[str] = None
    new_rule_id: Optional[str] = None
    #: 两侧的判定骨架（op/value/unit/clause/applies_if），供报告直接渲染。
    old_side: Optional[Dict[str, Any]] = None
    new_side: Optional[Dict[str, Any]] = None
    #: 配对依据说明（如"旧版无条件规则对应新版铅蓄电池条件分支"）。
    pairing: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "param": self.param,
            "kind": self.kind,
            "old_rule_id": self.old_rule_id,
            "new_rule_id": self.new_rule_id,
            "old_side": self.old_side,
            "new_side": self.new_side,
            "pairing": self.pairing,
        }


@dataclass
class VersionDiff:
    """两版规则包的参数级差异表（同标准族内比较）。"""

    standard_family: str
    old_version_key: str
    new_version_key: str
    entries: List[ParamDiff] = field(default_factory=list)

    def substantive(self) -> List[ParamDiff]:
        """实质差异条目（排除 unchanged —— 报告差异表只列有变化的）。"""
        return [item for item in self.entries if item.kind != DIFF_UNCHANGED]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "ebikecheck.version_diff/1.0",
            "standard_family": self.standard_family,
            "old_version_key": self.old_version_key,
            "new_version_key": self.new_version_key,
            "entries": [item.to_dict() for item in self.entries],
            "counts": self.counts(),
        }

    def counts(self) -> Dict[str, int]:
        tally: Dict[str, int] = {}
        for item in self.entries:
            tally[item.kind] = tally.get(item.kind, 0) + 1
        return tally


def _side(rule: Rule) -> Dict[str, Any]:
    return {
        "op": rule.op,
        "value": rule.value,
        "unit": rule.unit,
        "clause": rule.clause,
        "clause_status": rule.clause_status,
        "applies_if": rule.applies_if_raw,
    }


def _cond_key(applies_if_raw: Optional[Dict[str, Any]]) -> str:
    """条件归组键：无 null 条件（无条件）与各条件串各归一组。"""
    import json

    if applies_if_raw is None:
        return ""
    return json.dumps(applies_if_raw, sort_keys=True, ensure_ascii=False)


def _pair_rules(old_rules: List[Rule], new_rules: List[Rule]) -> List[Tuple[Optional[Rule], Optional[Rule], str]]:
    """同参数内两版规则的**配对**（返回 ``(旧, 新, 配对依据)`` 序列）。

    优先同条件直配；一侧无条件而另一侧为条件拆分时，无条件规则与**每个条件
    分支**各配一对（配对依据注明）——保证"旧版无条件 vs 新版条件拆分"能
    逐分支比出"放宽/不变"，而不是误报成整体新增。
    """
    old_by_cond = {_cond_key(r.applies_if_raw): r for r in old_rules}
    new_by_cond = {_cond_key(r.applies_if_raw): r for r in new_rules}
    pairs: List[Tuple[Optional[Rule], Optional[Rule], str]] = []
    used_old = set()

    for cond, new_rule in new_by_cond.items():
        old_rule = old_by_cond.get(cond)
        if old_rule is not None:
            used_old.add(cond)
            pairs.append((old_rule, new_rule, "同条件直配" if cond else "双方均无条件"))
            continue
        # 新版条件分支在旧版无同条件规则：找旧版无条件规则配对。
        fallback = old_by_cond.get("")
        if cond and fallback is not None:
            used_old.add("")
            pairs.append(
                (
                    fallback,
                    new_rule,
                    "旧版无条件规则 vs 新版条件分支（{0}）".format(_cond_text(new_rule)),
                )
            )
            continue
        pairs.append((None, new_rule, "旧版无对应规则"))

    for cond, old_rule in old_by_cond.items():
        if cond in used_old:
            continue
        fallback = new_by_cond.get("")
        if cond and fallback is not None:
            pairs.append(
                (
                    old_rule,
                    fallback,
                    "旧版条件分支（{0}）vs 新版无条件规则".format(_cond_text(old_rule)),
                )
            )
            continue
        pairs.append((old_rule, None, "新版无对应规则"))
    return pairs


def _cond_text(rule: Rule) -> str:
    expr = rule.applies_if_raw
    if not expr:
        return "无条件"
    if "param" in expr:
        neg = "非" if "not" in expr else ""
        return "{0}{1}={2}".format(neg, expr["param"], expr.get("value"))
    if "not" in expr and isinstance(expr["not"], dict) and "param" in expr["not"]:
        inner = expr["not"]
        return "{0}!={1}".format(inner["param"], inner.get("value"))
    return "复合条件"


def _classify(old: Rule, new: Rule) -> str:
    """同条件配对后的实质分类。"""
    if old.op == new.op:
        if old.value == new.value:
            return DIFF_UNCHANGED
        if old.op == "<=" or old.op == "<":
            # 阈值上限：变大 = 放宽。
            return DIFF_RELAXED if new.value > old.value else DIFF_TIGHTENED
        if old.op == ">=" or old.op == ">":
            # 阈值下限：变大 = 收紧。
            return DIFF_TIGHTENED if new.value > old.value else DIFF_RELAXED
        if old.op == "range" and isinstance(old.value, list) and isinstance(new.value, list):
            if new.value[0] < old.value[0] or new.value[1] < old.value[1]:
                return DIFF_TIGHTENED
            if new.value[0] > old.value[0] or new.value[1] > old.value[1]:
                return DIFF_RELAXED
            return DIFF_VALUE_CHANGED
        return DIFF_VALUE_CHANGED
    if old.value == new.value:
        return DIFF_OPERATOR_CHANGED
    return DIFF_VALUE_CHANGED


def diff_rulesets(
    standard_family: str,
    old_version_key: str,
    old_rules: List[Rule],
    new_version_key: str,
    new_rules: List[Rule],
) -> VersionDiff:
    """两版分册的**生效规则**做参数级 diff（同参数内按 ``applies_if`` 配对）。

    输入是已过门控的 ``Rule`` 列表（``Ruleset.effective_rules()``）——
    ``pending`` 条目零参与（M2 门控纪律在 diff 路径同样成立）。
    """
    params = sorted({rule.param for rule in old_rules} | {rule.param for rule in new_rules})
    old_by_param: Dict[str, List[Rule]] = {}
    new_by_param: Dict[str, List[Rule]] = {}
    for rule in old_rules:
        old_by_param.setdefault(rule.param, []).append(rule)
    for rule in new_rules:
        new_by_param.setdefault(rule.param, []).append(rule)

    out = VersionDiff(standard_family, old_version_key, new_version_key)
    for param in params:
        olds = old_by_param.get(param) or []
        news = new_by_param.get(param) or []
        if olds and not news:
            for rule in olds:
                out.entries.append(
                    ParamDiff(
                        param=param,
                        kind=DIFF_REMOVED,
                        old_rule_id=rule.id,
                        old_side=_side(rule),
                        pairing="仅旧版要求（新版废止该参数限值）",
                    )
                )
            continue
        if news and not olds:
            for rule in news:
                out.entries.append(
                    ParamDiff(
                        param=param,
                        kind=DIFF_ADDED,
                        new_rule_id=rule.id,
                        new_side=_side(rule),
                        pairing="仅新版要求（旧版无此参数限值）",
                    )
                )
            continue
        for old_rule, new_rule, pairing in _pair_rules(olds, news):
            if old_rule is None:
                out.entries.append(
                    ParamDiff(
                        param=param,
                        kind=DIFF_ADDED,
                        new_rule_id=new_rule.id,
                        new_side=_side(new_rule),
                        pairing=pairing,
                    )
                )
            elif new_rule is None:
                out.entries.append(
                    ParamDiff(
                        param=param,
                        kind=DIFF_REMOVED,
                        old_rule_id=old_rule.id,
                        old_side=_side(old_rule),
                        pairing=pairing,
                    )
                )
            else:
                out.entries.append(
                    ParamDiff(
                        param=param,
                        kind=_classify(old_rule, new_rule),
                        old_rule_id=old_rule.id,
                        new_rule_id=new_rule.id,
                        old_side=_side(old_rule),
                        new_side=_side(new_rule),
                        pairing=pairing,
                    )
                )
    return out


def diff_from_findings(
    old_dimension: "Any", new_dimension: "Any", profile_sha256: str = ""
) -> List[Dict[str, Any]]:
    """同档案两版判定结果的参数级结论对照（FR-07 报告的"实际差异"半边）。

    输入为两版装配下的**同作用域维度** :class:`engine.findings.CheckResult`；
    输出逐参数 ``[(param, old_state, new_state)]`` 且结论不同的行。
    与 :func:`diff_rulesets` 的关系：那边是"规则表怎么变"（静态），这边是
    "同一档案在两版下结论怎么变"（动态）——报告两半都要，且都不手写。
    """
    def _states(dimension) -> Dict[str, str]:
        tally: Dict[str, str] = {}
        for finding in dimension.findings:
            current = tally.get(finding.param)
            if current is None or _STATE_ORDER.get(finding.state, 9) < _STATE_ORDER.get(current, 9):
                tally[finding.param] = finding.state
        return tally

    old_states = _states(old_dimension)
    new_states = _states(new_dimension)
    rows: List[Dict[str, Any]] = []
    for param in sorted(set(old_states) | set(new_states)):
        old_state = old_states.get(param)
        new_state = new_states.get(param)
        if old_state != new_state:
            rows.append(
                {
                    "param": param,
                    "old_state": old_state,
                    "new_state": new_state,
                }
            )
    return rows


def findings_by_param(findings: List[Finding]) -> Dict[str, List[Finding]]:
    """``{param: [finding, ...]}``（差异表渲染侧的辅助视图）。"""
    out: Dict[str, List[Finding]] = {}
    for finding in findings:
        out.setdefault(finding.param, []).append(finding)
    return out
