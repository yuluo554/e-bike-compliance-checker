"""规则包加载、schema 校验与 ``status`` 门控。

**门控是本项目的核心纪律**（[plan/04](../../../plan/04-模块详设.md) §3、§5）：
``status != verified`` 的条目**零参与核查路径**，只进 ``excluded`` 集合，
并在输出与报告中显式列出——"没查"与"查了没问题"必须可区分。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..io_utils import decode_decimal, read_json, sha256_file
from .findings import ExcludedRule

#: 比较运算符白名单（schema 校验用）。
ALLOWED_OPS = ("<=", ">=", "<", ">", "==", "!=", "in", "not_in", "range")

#: 规则状态。
STATUS_VERIFIED = "verified"
STATUS_PENDING = "pending"

#: 条款号核对状态（与规则状态**分开跟踪**，见 plan/06 D-05）。
CLAUSE_VERIFIED = "verified"
CLAUSE_PENDING = "pending"

#: 作用域。
SCOPE_VEHICLE = "vehicle"
SCOPE_BATTERY = "battery"
SCOPE_CHARGER = "charger"
ALLOWED_SCOPES = (SCOPE_VEHICLE, SCOPE_BATTERY, SCOPE_CHARGER)

#: 标准状态。
STANDARD_STATUSES = ("current", "superseded", "abolished")

#: 来源类别。
ALLOWED_SOURCE_KINDS = ("standard_meta", "gov_qna", "standard_text", "to_verify")


class RulesetError(Exception):
    """规则包不可用（schema 非法 / 缺失 / 校验失败）→ 调用方退出码 2。"""


@dataclass
class Rule:
    """一条可参数化限值规则。"""

    id: str
    param: str
    op: str
    value: Any
    unit: str
    clause: Optional[str]
    clause_status: str
    source: Dict[str, Any]
    status: str
    applies_if: Optional[Dict[str, Any]] = None
    applies_if_raw: Optional[Dict[str, Any]] = None
    clause_excerpt: str = ""
    notes: str = ""
    verified_on: str = ""
    standard_code: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "param": self.param,
            "op": self.op,
            "value": self.value,
            "unit": self.unit,
            "clause": self.clause,
            "clause_status": self.clause_status,
            "source": dict(self.source),
            "status": self.status,
            "applies_if": self.applies_if_raw,
            "clause_excerpt": self.clause_excerpt,
            "notes": self.notes,
            "verified_on": self.verified_on,
        }


@dataclass
class Ruleset:
    """一个 ``标准 × 版本`` 的规则集（已过 schema 校验）。"""

    file_name: str
    path: str
    sha256: str
    standard: Dict[str, Any]
    scope: str
    rules: List[Rule] = field(default_factory=list)
    excluded: List[ExcludedRule] = field(default_factory=list)

    @property
    def code(self) -> str:
        return str(self.standard.get("code", ""))

    def effective_rules(self) -> List[Rule]:
        """进入核查路径的规则（已过滤 ``status``）。"""
        return list(self.rules)


def _require(mapping: Dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise RulesetError("{0} 缺少必填字段: {1}".format(where, key))
    return mapping[key]


def _check_date(text: Any, where: str) -> str:
    if not isinstance(text, str) or len(text) != 10 or text[4] != "-" or text[7] != "-":
        raise RulesetError("{0} 日期格式应为 YYYY-MM-DD，实际: {1!r}".format(where, text))
    return text


def validate_applies_if(expr: Any, where: str) -> Optional[Dict[str, Any]]:
    """校验 ``applies_if`` 文法（白名单小语言，不用 eval）。"""
    if expr is None:
        return None
    if not isinstance(expr, dict):
        raise RulesetError("{0} 的 applies_if 必须是对象或 null".format(where))
    keys = set(expr)
    if keys == {"param", "op", "value"}:
        if not isinstance(expr["param"], str) or not expr["param"]:
            raise RulesetError("{0} 的 applies_if.param 必须是非空字符串".format(where))
        if expr["op"] not in ALLOWED_OPS:
            raise RulesetError(
                "{0} 的 applies_if.op 越白名单: {1!r}".format(where, expr["op"])
            )
        return dict(expr)
    if keys == {"all"} or keys == {"any"}:
        key = "all" if "all" in keys else "any"
        items = expr[key]
        if not isinstance(items, list) or not items:
            raise RulesetError("{0} 的 applies_if.{1} 必须是非空数组".format(where, key))
        return {key: [validate_applies_if(item, where) for item in items]}
    if keys == {"not"}:
        return {"not": validate_applies_if(expr["not"], where)}
    raise RulesetError(
        "{0} 的 applies_if 结构非法（只允许 param/op/value、all、any、not）: {1!r}".format(
            where, sorted(keys)
        )
    )


def _parse_rule(raw: Dict[str, Any], standard_code: str, where: str) -> Rule:
    rule_id = _require(raw, "id", where)
    if not isinstance(rule_id, str) or not rule_id:
        raise RulesetError("{0} 的 id 必须是非空字符串".format(where))
    op = _require(raw, "op", where)
    if op not in ALLOWED_OPS:
        raise RulesetError("{0} 的 op 越白名单: {1!r}".format(where, op))
    status = _require(raw, "status", where)
    if status not in (STATUS_VERIFIED, STATUS_PENDING):
        raise RulesetError("{0} 的 status 非法: {1!r}".format(where, status))
    clause_status = raw.get("clause_status", CLAUSE_PENDING)
    if clause_status not in (CLAUSE_VERIFIED, CLAUSE_PENDING):
        raise RulesetError("{0} 的 clause_status 非法: {1!r}".format(where, clause_status))
    clause = raw.get("clause")
    if clause_status == CLAUSE_VERIFIED:
        if not clause or not str(clause).strip():
            raise RulesetError(
                "{0} 声明 clause_status=verified 但 clause 为空（不编造条款号纪律）".format(where)
            )
    elif clause:
        raise RulesetError(
            "{0} 的 clause_status=pending 时 clause 必须为 null（不得预填未核对条款号）".format(where)
        )

    value = raw.get("value")
    if status == STATUS_VERIFIED:
        if value is None:
            raise RulesetError(
                "{0} 声明 status=verified 但 value 为 null（未核对不得生效）".format(where)
            )
        if op in ("in", "not_in"):
            if not isinstance(value, list) or not value:
                raise RulesetError("{0} 的 in/not_in 需要非空数组 value".format(where))
        elif op == "range":
            if not isinstance(value, list) or len(value) != 2:
                raise RulesetError("{0} 的 range 需要 [lo, hi] 两元素 value".format(where))
            if decode_decimal(value[0]) is None or decode_decimal(value[1]) is None:
                raise RulesetError("{0} 的 range 边界不可解析为数值".format(where))
        elif decode_decimal(value) is None and not isinstance(value, str):
            raise RulesetError("{0} 的 value 不可解析为数值或字符串: {1!r}".format(where, value))
    else:
        if value is not None:
            raise RulesetError(
                "{0} 声明 status=pending 但 value 非 null（待核对不得预填数值）".format(where)
            )

    source = _require(raw, "source", where)
    if not isinstance(source, dict):
        raise RulesetError("{0} 的 source 必须是对象".format(where))
    kind = source.get("kind")
    if kind not in ALLOWED_SOURCE_KINDS:
        raise RulesetError("{0} 的 source.kind 非法: {1!r}".format(where, kind))
    if kind != "to_verify" and not source.get("url"):
        raise RulesetError("{0} 的 source.kind={1} 必须提供 url".format(where, kind))
    if not source.get("retrieved_on"):
        raise RulesetError("{0} 的 source.retrieved_on 必填".format(where))

    param = _require(raw, "param", where)
    if not isinstance(param, str) or not param:
        raise RulesetError("{0} 的 param 必须是非空字符串".format(where))
    unit = raw.get("unit", "")
    if not isinstance(unit, str):
        raise RulesetError("{0} 的 unit 必须是字符串".format(where))

    return Rule(
        id=rule_id,
        param=param,
        op=op,
        value=value,
        unit=unit,
        clause=clause,
        clause_status=clause_status,
        source=dict(source),
        status=status,
        applies_if=validate_applies_if(raw.get("applies_if"), where),
        applies_if_raw=raw.get("applies_if"),
        clause_excerpt=raw.get("clause_excerpt", "") or "",
        notes=raw.get("notes", "") or "",
        verified_on=raw.get("verified_on", "") or "",
        standard_code=standard_code,
    )


def validate_ruleset(raw: Any, file_name: str) -> Dict[str, Any]:
    """校验分册顶层结构；通过返回规范化后的字典。"""
    if not isinstance(raw, dict):
        raise RulesetError("{0} 顶层必须是对象".format(file_name))
    _require(raw, "schema_version", file_name)
    standard = _require(raw, "standard", file_name)
    if not isinstance(standard, dict):
        raise RulesetError("{0}.standard 必须是对象".format(file_name))
    for key in ("code", "title", "published", "effective", "status"):
        _require(standard, key, "{0}.standard".format(file_name))
    _check_date(standard["published"], "{0}.standard.published".format(file_name))
    _check_date(standard["effective"], "{0}.standard.effective".format(file_name))
    if standard["status"] not in STANDARD_STATUSES:
        raise RulesetError(
            "{0}.standard.status 非法: {1!r}".format(file_name, standard["status"])
        )
    scope = _require(raw, "scope", file_name)
    if scope not in ALLOWED_SCOPES:
        raise RulesetError("{0}.scope 非法: {1!r}".format(file_name, scope))
    rules_raw = _require(raw, "rules", file_name)
    if not isinstance(rules_raw, list):
        raise RulesetError("{0}.rules 必须是数组".format(file_name))
    if not rules_raw:
        raise RulesetError("{0}.rules 为空（分册至少要有一条登记条目）".format(file_name))
    # 逐条校验（schema 入口必须把规则本身也验到，否则"校验通过"是假的）。
    standard_code_value = standard["code"]
    for index, item in enumerate(rules_raw):
        where = "{0}.rules[{1}]".format(file_name, index)
        if not isinstance(item, dict):
            raise RulesetError("{0} 必须是对象".format(where))
        _parse_rule(item, standard_code_value, where)
    return raw


def load_ruleset_file(
    path: str,
    expect_sha256: Optional[str] = None,
    scope: Optional[str] = None,
    standard_code: Optional[str] = None,
) -> Ruleset:
    """加载并校验单个分册；``expect_sha256`` 提供时做一致性比对。"""
    if not os.path.isfile(path):
        raise RulesetError("规则包文件不存在: {0}".format(path))
    actual_sha = sha256_file(path)
    if expect_sha256 and expect_sha256 != actual_sha:
        raise RulesetError(
            "规则包 {0} 的 sha256 与 manifest 登记值不符（产物与登记脱钩）".format(
                os.path.basename(path)
            )
        )
    raw = read_json(path)
    return _build_ruleset(
        raw,
        os.path.basename(path),
        actual_sha,
        scope=scope,
        standard_code=standard_code,
        path=path,
    )


def load_ruleset_file_from_dict(
    raw: Any, file_name: str, sha256: str = ""
) -> Ruleset:
    """从内存字典构建规则集（测试与基准探活用；不落盘）。"""
    return _build_ruleset(raw, file_name, sha256)


def _build_ruleset(
    raw: Any,
    file_name: str,
    actual_sha: str,
    scope: Optional[str] = None,
    standard_code: Optional[str] = None,
    path: str = "",
) -> Ruleset:
    """校验并构建规则集（``load_ruleset_file`` 与内存通路共用）。"""
    validate_ruleset(raw, file_name)
    if scope and raw["scope"] != scope:
        raise RulesetError(
            "{0}.scope={1} 与期望 {2} 不符".format(file_name, raw["scope"], scope)
        )
    if standard_code and raw["standard"]["code"] != standard_code:
        raise RulesetError(
            "{0}.standard.code={1} 与期望 {2} 不符".format(
                file_name, raw["standard"]["code"], standard_code
            )
        )

    standard_code_value = raw["standard"]["code"]
    effective: List[Rule] = []
    excluded: List[ExcludedRule] = []
    seen_ids = set()
    seen_keys = set()
    for index, item in enumerate(raw["rules"]):
        where = "{0}.rules[{1}]".format(file_name, index)
        if not isinstance(item, dict):
            raise RulesetError("{0} 必须是对象".format(where))
        rule = _parse_rule(item, standard_code_value, where)
        if rule.id in seen_ids:
            raise RulesetError("{0} 的 id 重复: {1}".format(where, rule.id))
        seen_ids.add(rule.id)
        # 同目标去重：同一 (参数, 条款, 适用条件) 才算重复。
        # 同一参数配不同 applies_if 是正常形态（如铅蓄电池/其他电池各有质量限值），
        # 不能被去重误伤；而"同条款同一条件建两遍"才是双份结论的来源。
        dedup_key = (
            rule.param,
            rule.clause or "",
            json.dumps(rule.applies_if_raw, sort_keys=True, ensure_ascii=False),
        )
        if dedup_key in seen_keys:
            raise RulesetError(
                "{0} 的 (param, clause, applies_if) 重复: {1!r}（同目标去重纪律）".format(
                    where, dedup_key
                )
            )
        seen_keys.add(dedup_key)
        if rule.status == STATUS_VERIFIED:
            effective.append(rule)
        else:
            excluded.append(
                ExcludedRule(
                    rule_id=rule.id,
                    param=rule.param,
                    status=rule.status,
                    reason="not_verified",
                )
            )

    return Ruleset(
        file_name=file_name,
        path=path,
        sha256=actual_sha,
        standard=dict(raw["standard"]),
        scope=raw["scope"],
        rules=effective,
        excluded=excluded,
    )


@dataclass
class Manifest:
    """``data/rules/manifest.json`` 的内存视图。"""

    path: str
    sha256: str
    generated_by: str
    generator_version: str
    rulesets: List[Dict[str, Any]] = field(default_factory=list)
    version_anchors: List[Dict[str, Any]] = field(default_factory=list)
    thresholds: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def ruleset_entry(self, version_key: str) -> Optional[Dict[str, Any]]:
        for entry in self.rulesets:
            if entry.get("version_key") == version_key:
                return entry
        return None


def load_manifest(data_dir: str) -> Manifest:
    """加载并校验 manifest。"""
    path = os.path.join(data_dir, "rules", "manifest.json")
    if not os.path.isfile(path):
        raise RulesetError("找不到规则库 manifest: {0}".format(path))
    raw = read_json(path)
    if not isinstance(raw, dict):
        raise RulesetError("manifest.json 顶层必须是对象")
    for key in ("schema_version", "generated_by", "rulesets", "thresholds"):
        if key not in raw:
            raise RulesetError("manifest.json 缺少必填字段: {0}".format(key))
    if not isinstance(raw["rulesets"], list) or not raw["rulesets"]:
        raise RulesetError("manifest.rulesets 必须是非空数组")
    if not isinstance(raw["thresholds"], dict) or not raw["thresholds"]:
        raise RulesetError("manifest.thresholds 必须是非空对象（门槛随 manifest 下发）")
    for entry in raw["rulesets"]:
        for key in ("file", "standard", "scope", "version_key", "sha256"):
            if key not in entry:
                raise RulesetError("manifest.rulesets 条目缺少 {0}".format(key))
    return Manifest(
        path=path,
        sha256=sha256_file(path),
        generated_by=raw["generated_by"],
        generator_version=raw.get("generator_version", ""),
        rulesets=list(raw["rulesets"]),
        version_anchors=list(raw.get("version_anchors", [])),
        thresholds=dict(raw["thresholds"]),
        raw=raw,
    )


def load_ruleset_by_key(data_dir: str, manifest: Manifest, version_key: str) -> Ruleset:
    """按 ``version_key`` 加载分册（带 manifest 登记的 sha256 校验）。"""
    entry = manifest.ruleset_entry(version_key)
    if entry is None:
        raise RulesetError("manifest 中不存在 version_key: {0}".format(version_key))
    path = os.path.join(data_dir, "rules", entry["file"])
    return load_ruleset_file(
        path,
        expect_sha256=entry.get("sha256"),
        scope=entry.get("scope"),
        standard_code=entry.get("standard"),
    )


def eval_applies_if(expr: Optional[Dict[str, Any]], params: Dict[str, Any]) -> Optional[bool]:
    """三值逻辑求值：``True`` / ``False`` / ``None``（unknown）。

    引用参数未提供或不可解析 → ``None``；调用方据此判 ``not_provided``
    （**"不知道是否适用" ≠ "不适用"**）。
    """
    if expr is None:
        return True
    if "param" in expr:
        provided = params.get(expr["param"])
        if not isinstance(provided, dict):
            return None
        number = decode_decimal(provided.get("value"))
        target = expr["value"]
        if number is None:
            # 值不可解析：若比较是字符串等值，仍尝试文本比较；否则 unknown。
            raw_value = provided.get("value")
            if isinstance(raw_value, str) and expr["op"] in ("==", "!="):
                hit = raw_value == target
                return hit if expr["op"] == "==" else not hit
            return None
        from .values import compare  # 局部导入避免循环依赖

        try:
            return bool(compare(number, expr["op"], target))
        except (ValueError, TypeError):
            return None
    if "all" in expr:
        results = [eval_applies_if(item, params) for item in expr["all"]]
        if any(item is False for item in results):
            return False
        if any(item is None for item in results):
            return None
        return True
    if "any" in expr:
        results = [eval_applies_if(item, params) for item in expr["any"]]
        if any(item is True for item in results):
            return True
        if any(item is None for item in results):
            return None
        return False
    if "not" in expr:
        inner = eval_applies_if(expr["not"], params)
        if inner is None:
            return None
        return not inner
    return None


def count_status(manifest_entries: List[Dict[str, Any]], data_dir: str) -> Tuple[int, int]:
    """统计全库 ``verified`` / ``pending`` 条目数（``selfcheck`` 与报告用）。"""
    verified = 0
    pending = 0
    for entry in manifest_entries:
        path = os.path.join(data_dir, "rules", entry["file"])
        raw = read_json(path)
        for item in raw.get("rules", []):
            if item.get("status") == STATUS_VERIFIED:
                verified += 1
            else:
                pending += 1
    return verified, pending
