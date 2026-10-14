"""跨轮对账三集合（FR-10）：新增越限 / 已整改 / 持续越限。

配对主键 = **稳定身份键** ``profile_id``（整改循环里车型不变，内容指纹会因
参数修订而变，不能做主键）。参数级"非通过"口径的**单一实现源**是
:func:`benchmark.cases.observed_nonpass` —— 本模块消费它，不另立口径。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ..engine.findings import CheckResult
from ..benchmark.cases import observed_nonpass

NEW_VIOLATION = "new_violation"        # 本轮非通过、上轮通过（或上轮没有该件）
RESOLVED = "resolved"                  # 上轮非通过、本轮已通过
PERSISTENT = "persistent"              # 两轮都非通过（含状态变化，如 越限→未提供）

#: 参数级"非通过"集合的元素类型：``(profile_id, param, state)``。
NonPassEntry = Tuple[str, str, str]


@dataclass
class Reconciliation:
    """一轮对账的三集合结果。"""

    new_violations: List[NonPassEntry] = field(default_factory=list)
    resolved: List[NonPassEntry] = field(default_factory=list)
    persistent: List[NonPassEntry] = field(default_factory=list)
    #: 配对主键说明（进报告，供读者核对"不是内容指纹"）。
    key_basis: str = "profile_id"

    def counts(self) -> Dict[str, int]:
        return {
            NEW_VIOLATION: len(self.new_violations),
            RESOLVED: len(self.resolved),
            PERSISTENT: len(self.persistent),
        }

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema": "ebikecheck.reconciliation/1.0",
            "key_basis": self.key_basis,
            "counts": self.counts(),
            "new_violations": [list(item) for item in self.new_violations],
            "resolved": [list(item) for item in self.resolved],
            "persistent": [list(item) for item in self.persistent],
        }


def _nonpass_by_profile(results: List[CheckResult]) -> Dict[str, List[Tuple[str, str]]]:
    """``{profile_id: [(param, state), ...]}``（参数级非通过集合）。"""
    out: Dict[str, List[Tuple[str, str]]] = {}
    for result in results:
        out[result.profile_id] = observed_nonpass(result)
    return out


def reconcile_rounds(
    baseline: List[CheckResult], current: List[CheckResult]
) -> Reconciliation:
    """对账两轮结果（``baseline`` = 上轮，``current`` = 本轮）。
    元素为 ``(profile_id, param, state)``；``state`` 取"最弱结论"（单一实现源
    ``observed_nonpass``）。配对纪律：

    - **已整改 / 持续越限只在两轮都出现的档案间配对** —— 上轮的档案本轮
      没被扫描（文件被移走/改名）不等于"已整改"，绝不能把它算成整改成效；
    - 仅本轮出现的档案，其非通过项全部算"新增越限"（新送检件）；
    - 上轮非通过、本轮该参数不再非通过（改值判合规、或补齐后状态消失）
      算"已整改" —— 整改动作既包括改值也包括补齐缺失参数。
    """
    before = _nonpass_by_profile(baseline)
    after = _nonpass_by_profile(current)
    out = Reconciliation()

    for profile_id in sorted(set(before) & set(after)):
        prev = dict(before[profile_id])
        curr = dict(after[profile_id])
        for param in sorted(set(prev) | set(curr)):
            was = prev.get(param)
            now = curr.get(param)
            if was is not None and now is None:
                out.resolved.append((profile_id, param, was))
            elif was is None and now is not None:
                out.new_violations.append((profile_id, param, now))
            else:
                out.persistent.append((profile_id, param, now))
    for profile_id in sorted(set(after) - set(before)):
        for param, state in after[profile_id]:
            out.new_violations.append((profile_id, param, state))
    return out
