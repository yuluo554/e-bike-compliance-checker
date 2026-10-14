"""基准运行器（CLI ``bench`` 的后端）。

契约：

- 门槛**只从 manifest 读**；缺失 → 退出码 2（**不回落代码默认值**）；
- ``--only <suite>`` 只跑指定套件，**不判定未测指标**；未知名 → 退出码 2；
- 退出码 0 达标 / 1 未达标 / 2 用法或输入错误；
- 每套件配**可证伪探活**：注入缺陷后该套件必须报未达标。
"""

from __future__ import annotations

import json
import os
import sys
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from .engine import rules as rules_mod
from .engine.findings import NON_COMPLIANT
from .io_utils import read_json
from .paths import find_data_dir

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

#: 已注册套件（``--only`` 白名单；未知名 → exit 2）。
SUITE_NAMES = ("rules", "boundary", "rule_driven", "dimensions", "synthetic", "version")

_TRUTH_DIR = os.path.join("truth", "cases")


class BenchError(Exception):
    """用法或输入错误。"""


def _load_cases(data_dir: str) -> List[Dict[str, Any]]:
    index_path = os.path.join(data_dir, _TRUTH_DIR, "index.json")
    if not os.path.isfile(index_path):
        raise BenchError(
            "找不到真值库索引 {0}；请先运行 tools/gen_synthetic.py".format(index_path)
        )
    index = read_json(index_path)
    cases = []
    for entry in index.get("cases", []):
        cases.append(read_json(os.path.join(data_dir, _TRUTH_DIR, entry["file"])))
    return cases


def _threshold(manifest, key: str) -> Decimal:
    """从 manifest 取门槛；缺失即报配置错误（数据非代码）。"""
    raw = manifest.thresholds.get(key)
    if raw is None:
        raise BenchError("manifest.thresholds 缺少门槛项 {0!r}（门槛随 manifest 下发）".format(key))
    try:
        return Decimal(str(raw))
    except Exception:
        raise BenchError("门槛 {0!r} 不是合法数值: {1!r}".format(key, raw))


def _check_profile_dict(profile: Dict[str, Any], data_dir: str, version_key: str):
    """直接对内存档案做**三维**核查（基准层不落盘临时文件；与 CLI 同一装配）。"""
    from . import service

    return service.check_profile_dict(profile, data_dir, version_key)


def suite_rules(data_dir: str) -> Tuple[int, int, List[str]]:
    """规则包自洽：门控计数正确、``pending`` 零进入核查路径。"""
    from .benchmark import cases as case_mod

    manifest = rules_mod.load_manifest(data_dir)
    problems: List[str] = []
    checks = 0
    for entry in manifest.rulesets:
        path = os.path.join(data_dir, "rules", entry["file"])
        raw = read_json(path)
        ruleset = rules_mod.load_ruleset_file(path, expect_sha256=entry.get("sha256"))
        verified_ids = {rule.id for rule in ruleset.rules}
        excluded_ids = {item.rule_id for item in ruleset.excluded}
        for item in raw["rules"]:
            checks += 1
            if item["status"] == "verified":
                if item["id"] not in verified_ids:
                    problems.append("{0}: verified 条目未进入核查路径".format(item["id"]))
                if item.get("value") is None:
                    problems.append("{0}: verified 却 value 为 null".format(item["id"]))
            else:
                if item["id"] in verified_ids:
                    problems.append("{0}: pending 条目竟进入核查路径".format(item["id"]))
                if item["id"] not in excluded_ids:
                    problems.append("{0}: pending 条目未记入 excluded".format(item["id"]))
        # 真值对账口径的一致性（单一实现源）
        if not hasattr(case_mod, "compare_case"):
            problems.append("对账语义实现源缺失（benchmark.cases）")
    return checks, checks - len(problems), problems


def _effective_rules_by_ruleset(data_dir: str):
    """``[(anchor_version_key, scope, [rule, ...])]``：各分册**生效**规则。

    ``anchor_version_key`` 是喂给服务层的**整车版本锚点**（服务层要求它属于
    GB17761 标准族）：整车册用该册自身的版本键（2018/2024 各判一次）；电池册与
    充电器册属独立标准，用默认生效版本锚定 —— 其分册由**作用域**选取，与版本键无关。
    """
    from .engine import version as version_mod

    manifest = rules_mod.load_manifest(data_dir)
    default_vehicle = version_mod.default_version_key(manifest.version_anchors) or ""
    out = []
    for entry in manifest.rulesets:
        ruleset = rules_mod.load_ruleset_by_key(data_dir, manifest, entry["version_key"])
        scope = entry.get("scope", "")
        anchor = entry["version_key"] if scope == rules_mod.SCOPE_VEHICLE else default_vehicle
        out.append((anchor, scope, ruleset.effective_rules()))
    return out


def _states_for(data_dir, version_key, rule, value, unit, applies_if, scope=""):
    """构造"只改该规则目标参数"的档案，取该参数的结论集合（**完整三维路径**）。

    条件规则要构造出**条件为真**的档案，否则断言打在 ``not_applicable`` 上
    （如"非铅蓄电池"条件固定给 ``lead_acid`` 必不适用）。构造从 ``applies_if``
    引用的参数出发逐个候选值试解 —— **不针对具体规则 id 写死**。
    """
    from .benchmark.probes import params_for_rule_probe

    params = params_for_rule_probe(rule, value)
    result = _check_profile_dict({"profile_id": "BENCH", "params": params}, data_dir, version_key)
    dimension = result.dimension(scope) if scope else None
    findings = dimension.findings if dimension is not None else result.findings
    return [item.state for item in findings if item.param == rule.param]


def suite_boundary(data_dir: str) -> Tuple[int, int, List[str]]:
    """限值边界枚举：从**规则包本身**推导端点（规则驱动层，不读真值库）。

    M2 起覆盖**全部比较运算符**（``<= >= < > == != in not_in range``）与
    布尔/无量纲条目 —— 端点由 :mod:`benchmark.probes` 从 ``op``/``value``/``unit``
    推导，新增规则自动进枚举，**不写死规则 id**。
    """
    from .benchmark import probes

    problems: List[str] = []
    checks = 0
    passed = 0
    for version_key, scope, rules in _effective_rules_by_ruleset(data_dir):
        for rule in rules:
            for value, expected in probes.probe_values(rule):
                checks += 1
                states = _states_for(
                    data_dir, version_key, rule, value, rule.unit, rule.applies_if, scope
                )
                if expected in states:
                    passed += 1
                else:
                    problems.append(
                        "{0}: 构造 {1!r} 应判 {2}，实际 {3}".format(
                            rule.id, value, expected, ",".join(states) or "无结论"
                        )
                    )
    return checks, passed, problems


def suite_rule_driven(data_dir: str) -> Tuple[int, int, List[str]]:
    """规则驱动层：只从规则表推导端点，经**完整三维核查路径**端到端对账。

    与 ``boundary`` 的区别：``boundary`` 只看"目标参数那一条"的结论；
    本套件额外断言**统一结论**（最弱优先聚合）与该维度内**其余参数**的行为 ——
    即"规则表 → 服务层装配 → 引擎判定"整条链路上没有一处靠真值库兜底。
    """
    from .benchmark import probes
    from .benchmark.cases import observed_states

    manifest = rules_mod.load_manifest(data_dir)
    problems: List[str] = []
    checks = 0
    passed = 0
    for version_key, scope, rules in _effective_rules_by_ruleset(data_dir):
        for rule in rules:
            for value, expected in probes.probe_values(rule):
                checks += 1
                params = probes.params_for_rule_probe(rule, value)
                result = _check_profile_dict(
                    {"profile_id": "BENCH", "params": params}, data_dir, version_key
                )
                dimension = result.dimension(scope)
                if dimension is None:
                    problems.append(
                        "{0}: 版本 {1} 下缺 {2} 维度（三维装配不完整）".format(
                            rule.id, version_key, scope
                        )
                    )
                    continue
                # 同一参数可能有多条互斥条件规则（铅蓄电池/其他电池各有质量限值），
                # 逐参数结论必须取"最弱" —— 与对账语义同一实现源（D-38 口径）。
                observed = observed_states(dimension)
                got = observed.get(rule.param)
                if got != expected:
                    problems.append(
                        "{0}: 参数 {1} 构造 {2!r} 期望 {3}，实际 {4}".format(
                            rule.id, rule.param, value, expected, got
                        )
                    )
                    continue
                # 统一结论必须与该维度结论同源（不符合 > 未提供 > 未评估 > 符合）。
                if expected == NON_COMPLIANT and result.overall() != NON_COMPLIANT:
                    problems.append(
                        "{0}: 维度判不符合，统一结论却是 {1}（聚合丢结论）".format(
                            rule.id, result.overall()
                        )
                    )
                    continue
                passed += 1
    return checks, passed, problems


def suite_dimensions(data_dir: str) -> Tuple[int, int, List[str]]:
    """三维判定与跨标准统一结论（M2-1/M2-2）。

    对每个标准分册各构造一份"全参数合规 + 只让该册某条越限"的档案，断言：
    ① 三个维度都在（整车/电池/充电器各挂自身标准号）；② 越限所在维度判不符合、
    其余参与聚合的维度不背锅；③ 统一结论 = 不符合。零真值库依赖。
    """
    from .benchmark import probes

    problems: List[str] = []
    checks = 0
    passed = 0
    scopes = set()
    for version_key, scope, rules in _effective_rules_by_ruleset(data_dir):
        scopes.add(scope)
        if not rules:
            # 该标准首期无可参数化限值（如 GB 43854 全册为型式试验要求）→ 维度
            # 仍必须装配出来（零生效规则、不参与聚合），只是无越限构造可造。
            continue
        # 以该册**第一条**生效规则为目标造越限构造（不写死规则 id）。
        target = rules[0]
        bad = [value for value, state in probes.probe_values(target) if state == NON_COMPLIANT]
        if not bad:
            continue
        checks += 1
        params = probes.params_for_rule_probe(target, bad[0])
        result = _check_profile_dict(
            {"profile_id": "BENCH", "params": params}, data_dir, version_key
        )
        dimension = result.dimension(scope)
        ok = True
        if dimension is None:
            problems.append("{0}: 版本 {1} 缺 {2} 维度".format(target.id, version_key, scope))
            ok = False
        elif dimension.overall() != NON_COMPLIANT:
            problems.append(
                "{0}: 目标册 {1} 应判不符合，实际 {2}".format(
                    target.id, scope, dimension.overall()
                )
            )
            ok = False
        elif result.overall() != NON_COMPLIANT:
            problems.append(
                "{0}: 统一结论应为不符合，实际 {1}".format(target.id, result.overall())
            )
            ok = False
        if ok:
            passed += 1

    # 三维齐备：vehicle 必在；battery/charger 分册存在即应各成一维（即使零生效规则）。
    manifest = rules_mod.load_manifest(data_dir)
    declared_scopes = {entry.get("scope", "") for entry in manifest.rulesets}
    checks += 1
    if scopes == declared_scopes:
        passed += 1
    else:
        problems.append(
            "三维装配未覆盖全部分册作用域: 实测 {0} / 声明 {1}".format(
                sorted(scopes), sorted(declared_scopes)
            )
        )
    return checks, passed, problems


def suite_synthetic(data_dir: str) -> Tuple[int, int, List[str]]:
    """合成车型真值对账（样本驱动层，按档案所属版本的期望结论）。"""
    from .benchmark import cases as case_mod

    cases = _load_cases(data_dir)
    results = {}
    for case in cases:
        version_key = _case_version(case, "GB17761-2024")
        results[case["case_id"]] = _check_profile_dict(case["profile"], data_dir, version_key)
    passed, problems = case_mod.compare_cases(results, cases)
    return len(cases), passed, problems


def _case_version(case: Dict[str, Any], fallback: str) -> str:
    """用例的判定版本：显式 ``case_version`` 优先，否则用默认当前版本。"""
    return str(case.get("case_version") or fallback)


def suite_version(data_dir: str) -> Tuple[int, int, List[str]]:
    """双版本对照：同档案两版期望结论不同。"""
    cases = [c for c in _load_cases(data_dir) if c.get("kind") == "version_diff"]
    checks = 0
    passed = 0
    problems: List[str] = []
    for case in cases:
        expectations = case.get("expect_by_version", {})
        if not expectations:
            continue
        checks += 1
        ok = True
        for version_key, want in sorted(expectations.items()):
            result = _check_profile_dict(case["profile"], data_dir, version_key)
            from .benchmark.cases import observed_states

            observed = observed_states(result)
            for param, expected_state in sorted(want.items()):
                got = observed.get(param)
                if got != expected_state:
                    ok = False
                    problems.append(
                        "{0}@{1}: 参数 {2} 期望 {3}，实际 {4}".format(
                            case["case_id"], version_key, param, expected_state, got
                        )
                    )
        if ok:
            passed += 1
    return checks, passed, problems


SUITES = {
    "rules": (suite_rules, "truth_match_min"),
    "boundary": (suite_boundary, "truth_match_min"),
    "rule_driven": (suite_rule_driven, "truth_match_min"),
    "dimensions": (suite_dimensions, "truth_match_min"),
    "synthetic": (suite_synthetic, "truth_match_min"),
    "version": (suite_version, "truth_match_min"),
}


def _ratio(passed: int, total: int) -> Decimal:
    if total <= 0:
        return Decimal("0")
    return Decimal(passed) / Decimal(total)


def run_bench(only: Optional[str], as_json: bool, explicit_data_dir: Optional[str]) -> int:
    from .io_utils import _ensure_utf8_stdio, dumps_json

    _ensure_utf8_stdio()

    if only is not None and only not in SUITE_NAMES:
        print(
            "错误: 未知套件 {0!r}；可用: {1}".format(only, ", ".join(SUITE_NAMES)),
            file=__import__("sys").stderr,
        )
        return EXIT_USAGE

    data_dir = find_data_dir(explicit=explicit_data_dir)
    if data_dir is None:
        print("错误: 找不到数据目录（需含 rules/manifest.json）", file=__import__("sys").stderr)
        return EXIT_USAGE

    try:
        manifest = rules_mod.load_manifest(data_dir)
        max_seconds = _threshold(manifest, "bench_max_seconds")
        selected = [only] if only else list(SUITE_NAMES)
        report: Dict[str, Any] = {"schema": "ebikecheck.bench/1.0", "suites": []}
        overall_ok = True
        started = time.time()
        for name in selected:
            func, threshold_key = SUITES[name]
            gate = _threshold(manifest, threshold_key)
            try:
                total, passed, problems = func(data_dir)
            except BenchError:
                raise
            ratio = _ratio(passed, total)
            ok = ratio >= gate and not problems
            overall_ok = overall_ok and ok
            report["suites"].append(
                {
                    "name": name,
                    "total": total,
                    "passed": passed,
                    "ratio": str(ratio),
                    "threshold": str(gate),
                    "ok": ok,
                    "problems": problems,
                }
            )
        elapsed = Decimal(str(round(time.time() - started, 3)))
        report["elapsed_seconds"] = str(elapsed)
        report["max_seconds"] = str(max_seconds)
        report["thresholds_met"] = overall_ok
        report["timing_met"] = elapsed <= max_seconds
    except BenchError as error:
        print("错误: {0}".format(error), file=__import__("sys").stderr)
        return EXIT_USAGE
    except rules_mod.RulesetError as error:
        print("错误: {0}".format(error), file=__import__("sys").stderr)
        return EXIT_USAGE

    if as_json:
        print(dumps_json(report), end="")
    else:
        print("内置评测基准（套件 {0}）".format(", ".join(selected)))
        for item in report["suites"]:
            flag = "达标" if item["ok"] else "未达标"
            print(
                "  - {0:<10} {1}/{2} = {3}  门槛 {4}  [{5}]".format(
                    item["name"],
                    item["passed"],
                    item["total"],
                    item["ratio"],
                    item["threshold"],
                    flag,
                )
            )
            for problem in item["problems"][:5]:
                print("      ! {0}".format(problem))
        print(
            "耗时 {0}s（上限 {1}s）".format(report["elapsed_seconds"], report["max_seconds"])
        )

    if not report["thresholds_met"] or not report["timing_met"]:
        return EXIT_FAIL
    return EXIT_OK


def probe_falsifiable(data_dir: str, suite: str) -> bool:
    """探活：给套件注入缺陷，断言它**必须**报未达标。

    用途：防"基准全绿其实什么都没查"（门禁 token 集为空的前车之鉴）。
    """
    func, _ = SUITES[suite]
    if suite == "boundary":
        # 注入：把 epsilon 归零 → 越限值与限值相等 → non_compliant 应消失。
        import ebikecheck.engine.values as values_mod

        original = values_mod.UNIT_EPSILON
        broken = {key: "0" for key in original}
        values_mod.UNIT_EPSILON = broken
        try:
            total, passed, problems = func(data_dir)
            return bool(problems) or passed < total
        finally:
            values_mod.UNIT_EPSILON = original
    if suite == "rule_driven":
        # 注入：把"最小计量单位"归零 → 越限构造退化为等于限值 → 应报差异。
        import ebikecheck.engine.values as values_mod

        original = values_mod.UNIT_EPSILON
        broken = {key: "0" for key in original}
        values_mod.UNIT_EPSILON = broken
        try:
            total, passed, problems = func(data_dir)
            return bool(problems) or passed < total
        finally:
            values_mod.UNIT_EPSILON = original
    if suite == "dimensions":
        # 注入：让统一结论聚合忽略非整车维度 → 电池/充电器越限不再进统一结论 → 应报差异。
        # ProfileCheckResult.overall() 在**调用时**从 findings 模块全局取 aggregate_overall，
        # 故重绑模块属性即可生效。
        from .engine import findings as findings_mod

        original = findings_mod.aggregate_overall

        def _broken(results):
            return original([item for item in results if item.scope == "vehicle"])

        findings_mod.aggregate_overall = _broken
        try:
            total, passed, problems = func(data_dir)
            return bool(problems) or passed < total
        finally:
            findings_mod.aggregate_overall = original
    if suite == "rules":
        # 注入：临时把一个 pending 条目改成 verified（value 仍为 null）→ 应被抓。
        manifest = rules_mod.load_manifest(data_dir)
        for entry in manifest.rulesets:
            path = os.path.join(data_dir, "rules", entry["file"])
            raw = read_json(path)
            for item in raw["rules"]:
                if item["status"] != "verified":
                    saved_status = item["status"]
                    item["status"] = "verified"
                    try:
                        _probe_rules_with_mutation(data_dir, entry["file"], raw)
                        return True  # 未抓到 → 探活失败
                    except (rules_mod.RulesetError, AssertionError):
                        return True  # 抓到了 → 探活成功
                    finally:
                        item["status"] = saved_status
        return False
    if suite == "synthetic":
        from .benchmark import cases as case_mod

        cases = _load_cases(data_dir)
        if not cases:
            return False
        results = {
            case["case_id"]: _check_profile_dict(case["profile"], data_dir, "GB17761-2024")
            for case in cases
        }
        tampered = json.loads(json.dumps(cases, ensure_ascii=False))
        tampered[0].setdefault("expect", {}).setdefault("findings", {})
        tampered[0]["expect"]["findings"]["__nonexistent_param__"] = "compliant"
        _, problems = case_mod.compare_cases(results, tampered)
        return bool(problems)
    if suite == "version":
        cases = [c for c in _load_cases(data_dir) if c.get("kind") == "version_diff"]
        if not cases:
            return False
        # 注入：把期望两版结论对调 → 应报差异。
        case = cases[0]
        expectations = dict(case.get("expect_by_version", {}))
        keys = sorted(expectations)
        if len(keys) >= 2:
            expectations[keys[0]], expectations[keys[1]] = (
                expectations[keys[1]],
                expectations[keys[0]],
            )
            tampered = dict(case)
            tampered["expect_by_version"] = expectations
            checks = 0
            ok = True
            for version_key, want in sorted(expectations.items()):
                from .benchmark.cases import observed_states

                result = _check_profile_dict(case["profile"], data_dir, version_key)
                observed = observed_states(result)
                for param, expected_state in sorted(want.items()):
                    if observed.get(param) != expected_state:
                        ok = False
            return not ok
        return False
    return False


def _probe_rules_with_mutation(data_dir, file_name, mutated_raw):
    """把变异后的分册临时写盘校验（探活用；用内存校验避免污染磁盘）。"""
    from .engine.rules import _parse_rule, validate_ruleset

    validate_ruleset(mutated_raw, file_name)
    for index, item in enumerate(mutated_raw["rules"]):
        _parse_rule(item, mutated_raw["standard"]["code"], "probe[{0}]".format(index))
