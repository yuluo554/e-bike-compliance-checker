"""命令行入口。

**退出码三语义**（锁进测试，[plan/03](../plan/03-架构与技术选型.md) §5.1）::

    0  通过（无 non_compliant / 基准全达标 / 成功）
    1  检出不符合或未达标
    2  用法或输入错误（参数错、文件不存在、schema 非法、未知名、门槛缺失）

**``not_provided`` 与批量失败件都不改退出码** —— "没判定"与"判出违规"混在一个码里
会让 CI 误判。

本模块顶层**不得** import ``gui``/``PySide6``（AST 静态门禁守门）。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import __version__
from .engine.findings import NON_COMPLIANT
from .engine.rules import RulesetError
from .io_utils import _ensure_utf8_stdio, dumps_json
from .profile import ProfileError
from .service import (
    DataDirError,
    ServiceError,
    check_profile,
    resolve_data_dir,
    ruleset_overview,
    selfcheck as service_selfcheck,
)

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

#: 状态中文标签（仅展示层用；判定语义在引擎层）。
_STATE_LABELS = {
    "compliant": "符合",
    "non_compliant": "不符合",
    "not_applicable": "不适用",
    "not_provided": "未提供",
    "not_assessed": "未评估",
}

#: 维度中文名（展示层）。
_SCOPE_LABELS = {
    "vehicle": "整车",
    "battery": "电池",
    "charger": "充电器",
}


def _emit(payload, as_json: bool, human_lines: List[str]) -> None:
    if as_json:
        print(dumps_json(payload), end="")
    else:
        for line in human_lines:
            print(line)


def _finding_line(index: int, finding) -> str:
    label = _STATE_LABELS.get(finding.state, finding.state)
    clause = finding.clause or "条款号待核对"
    limit = "" if finding.limit is None else " 限值 {0} {1}".format(finding.limit, finding.unit)
    observed = "—" if finding.observed is None else finding.observed
    reason = "" if not finding.reason else " ({0})".format(finding.reason)
    return "  {0:>2}. [{1}] {2:<28} 观测 {3}{4}  依据 {5} {6}{7}".format(
        index,
        label,
        finding.param,
        observed,
        limit,
        finding.standard,
        clause,
        reason,
    )


def cmd_selfcheck(args) -> int:
    payload = service_selfcheck(args.data_dir)
    lines = [
        "数据目录: {0}".format(payload["data_dir"]),
        "冻结态: {0}".format(payload["frozen"]),
        "数据在 exe 目录内: {0}".format(payload["data_dir_within_exe_dir"]),
        "manifest: {0} (sha256 {1})".format(
            payload["manifest"]["path"], payload["manifest"]["sha256"][:16] + "…"
        ),
        "规则条目: verified={0}  pending={1}".format(
            payload["verified_total"], payload["pending_total"]
        ),
    ]
    for item in payload["rulesets"]:
        lines.append(
            "  - {0:<22} {1:<6} verified={2:<3} pending={3}".format(
                item["file"], item["scope"], item["verified"], item["pending"]
            )
        )
    _emit(payload, args.json, lines)
    return EXIT_OK


def cmd_check(args) -> int:
    result = check_profile(args.profile, args.data_dir, args.version_of)
    payload = result.to_dict()
    lines = [
        "车型: {0}".format(result.profile_id),
        "版本: {0}  (锚定依据: {1} {2})".format(
            result.version_key,
            result.version_anchor.get("basis"),
            result.version_anchor.get("value"),
        ),
        "维度: {0}".format(
            " / ".join(
                "{0}({1})".format(_SCOPE_LABELS.get(item.scope, item.scope), item.standard)
                for item in result.dimensions
            )
        ),
    ]
    counts = result.counts()
    lines.append(
        "计数: 符合 {0} / 不符合 {1} / 不适用 {2} / 未提供 {3}".format(
            counts["compliant"],
            counts["non_compliant"],
            counts["not_applicable"],
            counts["not_provided"],
        )
    )
    lines.append(
        "统一结论: {0}".format(_STATE_LABELS.get(result.overall(), result.overall()))
    )
    for dimension in result.dimensions:
        label = _SCOPE_LABELS.get(dimension.scope, dimension.scope)
        applicable = dimension.applicability.get("applicable", True)
        suffix = "" if applicable else "（本车型不适用：{0}）".format(
            dimension.applicability.get("reason", "")
        )
        lines.append(
            "—— {0}维度 [{1}] 结论 {2}（生效规则 {3} 条）{4}".format(
                label,
                dimension.standard,
                _STATE_LABELS.get(dimension.overall(), dimension.overall()),
                dimension.effective_rule_count,
                suffix,
            )
        )
        if not applicable:
            continue
        for index, finding in enumerate(dimension.findings, start=1):
            lines.append(_finding_line(index, finding))
        if dimension.excluded_rules:
            lines.append(
                "   本次核查未启用 {0} 条规则（待核对，不参与任何判定）:".format(
                    len(dimension.excluded_rules)
                )
            )
            for item in dimension.excluded_rules:
                lines.append("     - {0} ({1})".format(item.rule_id, item.reason))
    _emit(payload, args.json, lines)
    return EXIT_FINDINGS if result.overall() == NON_COMPLIANT else EXIT_OK


def cmd_rules(args) -> int:
    payload = ruleset_overview(args.data_dir)
    lines = ["规则库概览（数据目录 {0}）".format(payload["data_dir"])]
    for item in payload["rulesets"]:
        lines.append(
            "  - {0:<22} {1:<8} 生效 {2:<3} 未启用 {3}".format(
                item["file"], item["scope"], item["effective"], len(item["excluded"])
            )
        )
    _emit(payload, args.json, lines)
    return EXIT_OK


def cmd_bench(args) -> int:
    from .benchmark_runner import run_bench

    return run_bench(args.only, args.json, args.data_dir)


def cmd_version(args) -> int:
    print("ebikecheck {0}".format(__version__))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ebikecheck",
        description="电动自行车合规核查工作台（本地、零上传）",
    )
    parser.add_argument("--version", action="version", version="ebikecheck {0}".format(__version__))
    sub = parser.add_subparsers(dest="command")

    common_data = argparse.ArgumentParser(add_help=False)
    common_data.add_argument("--data-dir", default=None, help="显式指定数据目录")

    p_self = sub.add_parser("selfcheck", parents=[common_data], help="数据目录/规则库/门控自检")
    p_self.add_argument("--json", action="store_true", help="输出机读 JSON")
    p_self.set_defaults(func=cmd_selfcheck)

    p_check = sub.add_parser("check", parents=[common_data], help="单车型参数核查")
    p_check.add_argument("profile", help="车型档案 JSON 路径")
    p_check.add_argument("--json", action="store_true", help="输出机读 JSON")
    p_check.add_argument(
        "--version-of",
        dest="version_of",
        default=None,
        help="显式指定标准版本键（跳过日期锚定）",
    )
    p_check.set_defaults(func=cmd_check)

    p_rules = sub.add_parser("rules", parents=[common_data], help="规则库概览与门控计数")
    p_rules.add_argument("--json", action="store_true", help="输出机读 JSON")
    p_rules.set_defaults(func=cmd_rules)

    p_bench = sub.add_parser("bench", parents=[common_data], help="内置评测基准")
    p_bench.add_argument("--only", default=None, help="只跑指定套件（未知名 → 退出码 2）")
    p_bench.add_argument("--json", action="store_true", help="输出机读 JSON")
    p_bench.set_defaults(func=cmd_bench)

    p_version = sub.add_parser("version", help="版本号")
    p_version.set_defaults(func=cmd_version)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.func(args)
    except (DataDirError, ServiceError, ProfileError, RulesetError) as error:
        print("错误: {0}".format(error), file=sys.stderr)
        return EXIT_USAGE
    except (FileNotFoundError, IsADirectoryError) as error:
        print("错误: 路径不可用: {0}".format(error), file=sys.stderr)
        return EXIT_USAGE
    except json.JSONDecodeError as error:
        print("错误: JSON 解析失败: {0}".format(error), file=sys.stderr)
        return EXIT_USAGE


#: 供需要定位数据根的外部脚本复用。
__all__ = ["main", "build_parser", "resolve_data_dir", "EXIT_OK", "EXIT_FINDINGS", "EXIT_USAGE"]
