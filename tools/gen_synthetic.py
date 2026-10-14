#!/usr/bin/env python
"""合成车型档案 + 真值库生成器 —— ``data/truth/`` 的**唯一写入者**。

纪律（[plan/05](../plan/05-数据计划与里程碑.md) §2.2）：

- **禁 stdlib ``random``**（不承诺跨版本序列一致）→ 自研 splitmix64；
- 产物**无时间戳**、``\\n`` 行尾、UTF-8 无 BOM；
- ``--check`` 重新生成并与磁盘**逐字节比对**（守门测试调用）；
- **数据纪律**：虚构企业名 + 测试号段（统一社会信用代码 ``90000000…SYN``）、
  车型代号 ``SYN-…``；**不含任何真实企业或产品信息**。

真值语义：``expect.findings`` 是主期望，``also_expect`` 是同构造隐含的其余结论，
``expect_findings: []`` 显式声明"应零命中"，``expect_severity_warning`` 声明"应降级"。
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from ebikecheck.io_utils import (  # noqa: E402
    _ensure_utf8_stdio,
    dumps_json,
    write_text,
)

OUT_DIR = os.path.join(_ROOT, "data", "truth", "cases")
GENERATOR_VERSION = "1.0.0"
SEED = 20261014
SYNTHETIC_TAG = "SYN"
FAKE_MANUFACTURER = "示例车业（合成）有限公司"

#: 参数名（与规则包 param 对齐；不在此处写任何限值数值）。
P_SPEED = "max_design_speed"
P_MASS = "vehicle_mass"
P_BATTERY = "battery_type"
P_PLASTIC = "plastic_mass_ratio"
P_CUTOFF = "over_speed_power_cutoff"
P_AT_BATTERY = "anti_tamper_battery_pack"
P_AT_CONTROLLER = "anti_tamper_controller"
P_AT_LIMITER = "anti_tamper_speed_limiter"


def splitmix64(seed):
    """确定性 RNG（splitmix64）。返回可反复调用的取值函数。"""
    state = [seed & 0xFFFFFFFFFFFFFFFF]

    def next_u64():
        state[0] = (state[0] + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = state[0]
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    return next_u64


#: 边界值**以"限值 ± 最小计量单位"的表达方式**给出：真正的数值由规则包决定，
#: 这里只描述"恰好等于 / 高一个计量单位 / 低一个计量单位"的构造意图。
#: 为避免把限值抄进生成器（零字面量门禁的另一面），边界数值由基准层按规则包推导，
#: 生成器只产出"构造意图 + 参数组合"。
KIND_BOUNDARY_AT = "boundary_at_limit"
KIND_BOUNDARY_OVER = "boundary_over_limit"
KIND_BOUNDARY_UNDER = "boundary_under_limit"
KIND_CLEAN = "clean"
KIND_MISSING = "missing_param"
KIND_UNIT_CONVERT = "unit_convert"

#: 跨版本差异构造：同一档案在两版下的期望结论不同。
KIND_VERSION_DIFF = "version_diff"


def _profile(seq, design_date, params, market_date=None):
    """构造一份合成档案。"""
    profile = {
        "schema": "ebikecheck.profile/1.0",
        "profile_id": "SYN-EB-{0:03d}".format(seq),
        "manufacturer": FAKE_MANUFACTURER,
        "uscc": "90000000SYN0000{0:03d}X".format(seq),
        "model_design_date": design_date,
        "params": params,
    }
    if market_date:
        profile["market_date"] = market_date
    return profile


def _p(value, unit):
    return {"value": value, "unit": unit}


#: 布尔/枚举通路的合规取值（``op == "=="`` 时规则自身的 value 即合规值）。
_BOOL_TOKENS = {"true": True, "false": False}


def _compliant_value(op, limit):
    """由规则的 op 与限值推出一个**合规**的档案取值（不硬编码限值）。"""
    if op == "==":
        token = str(limit["value"])
        if token in _BOOL_TOKENS:
            return _BOOL_TOKENS[token], ""
        return token, limit["unit"]
    if op == ">=":
        return _over(limit), limit["unit"]
    # 默认按上界处理（"<=" 与 "<"）。
    return _under(limit), limit["unit"]


def _fill_compliant(params, view, exclude=()):
    """把该版本**全部已核对参数**补成合规值（保持"干净档案真的干净"）。

    规则包随里程碑增长（M1 新增标称电压、额定功率等），若不补齐，"全参数达标"
    的档案会因新参数缺失被判 ``not_provided`` —— 那是**用例过期**而非引擎缺陷。
    ``exclude`` 供"故意缺参数"的用例声明其省略项。
    """
    filled = dict(params)
    for param_name, limit in view.items():
        if param_name in filled or param_name in exclude:
            continue
        if limit.get("value") is None:
            continue
        value, unit = _compliant_value(limit.get("op", "<="), limit)
        filled[param_name] = _p(value, unit)
    return filled


def build_cases(rulesets):
    """构造全部用例。

    ``rulesets`` 是 ``{version_key: {param: {"op","value","unit"}}}`` 的规则视图，
    由基准层从规则包提取后传入 —— **生成器不硬编码限值**。
    """
    cases = []
    seq = 0

    limb = rulesets.get("GB17761-2024", {})
    old = rulesets.get("GB17761-2018", {})

    speed_limit = limb.get(P_SPEED)
    plastic_limit = limb.get(P_PLASTIC)

    # ---- 边界：恰好等于限值 ----
    if speed_limit:
        seq += 1
        cases.append(
            {
                "case_id": "SYN-CASE-{0:03d}".format(seq),
                "kind": KIND_BOUNDARY_AT,
                "target_param": P_SPEED,
                "profile": _profile(
                    seq,
                    "2025-10-01",
                    {
                        P_SPEED: _p(_at(speed_limit), speed_limit["unit"]),
                        P_BATTERY: _p("lead_acid", ""),
                        P_CUTOFF: _p(True, ""),
                        P_AT_BATTERY: _p(True, ""),
                        P_AT_CONTROLLER: _p(True, ""),
                        P_AT_LIMITER: _p(True, ""),
                    },
                ),
                "expect": {"findings": {P_SPEED: "compliant"}},
                "notes": "车速恰好等于限值 → 符合（上界闭区间）。",
            }
        )
    # ---- 边界：高一个最小计量单位 ----
    if speed_limit:
        seq += 1
        cases.append(
            {
                "case_id": "SYN-CASE-{0:03d}".format(seq),
                "kind": KIND_BOUNDARY_OVER,
                "target_param": P_SPEED,
                "profile": _profile(
                    seq,
                    "2025-10-01",
                    {
                        P_SPEED: _p(_over(speed_limit), speed_limit["unit"]),
                        P_BATTERY: _p("lead_acid", ""),
                        P_CUTOFF: _p(True, ""),
                        P_AT_BATTERY: _p(True, ""),
                        P_AT_CONTROLLER: _p(True, ""),
                        P_AT_LIMITER: _p(True, ""),
                    },
                ),
                "expect": {"findings": {P_SPEED: "non_compliant"}},
                "expect_overall": "non_compliant",
                "notes": "车速高一个最小计量单位 → 不符合。",
            }
        )
    # ---- 边界：低一个最小计量单位 ----
    if speed_limit:
        seq += 1
        cases.append(
            {
                "case_id": "SYN-CASE-{0:03d}".format(seq),
                "kind": KIND_BOUNDARY_UNDER,
                "target_param": P_SPEED,
                "profile": _profile(
                    seq,
                    "2025-10-01",
                    {
                        P_SPEED: _p(_under(speed_limit), speed_limit["unit"]),
                        P_BATTERY: _p("lead_acid", ""),
                        P_CUTOFF: _p(True, ""),
                        P_AT_BATTERY: _p(True, ""),
                        P_AT_CONTROLLER: _p(True, ""),
                        P_AT_LIMITER: _p(True, ""),
                    },
                ),
                "expect": {"findings": {P_SPEED: "compliant"}},
                "notes": "车速低一个最小计量单位 → 符合。",
            }
        )
    # ---- 塑料占比：恰好等于限值 → 符合 ----
    if plastic_limit:
        seq += 1
        cases.append(
            {
                "case_id": "SYN-CASE-{0:03d}".format(seq),
                "kind": KIND_BOUNDARY_AT,
                "target_param": P_PLASTIC,
                "profile": _profile(
                    seq,
                    "2025-10-01",
                    {
                        P_PLASTIC: _p(_at(plastic_limit), plastic_limit["unit"]),
                        P_BATTERY: _p("lead_acid", ""),
                        P_CUTOFF: _p(True, ""),
                        P_AT_BATTERY: _p(True, ""),
                        P_AT_CONTROLLER: _p(True, ""),
                        P_AT_LIMITER: _p(True, ""),
                    },
                ),
                "expect": {"findings": {P_PLASTIC: "compliant"}},
                "notes": "塑料占比恰好等于限值 → 符合。",
            }
        )
    # ---- 塑料占比：高一个最小计量单位 → 不符合（题面举例 6.2% 类型）----
    if plastic_limit:
        seq += 1
        cases.append(
            {
                "case_id": "SYN-CASE-{0:03d}".format(seq),
                "kind": KIND_BOUNDARY_OVER,
                "target_param": P_PLASTIC,
                "profile": _profile(
                    seq,
                    "2025-10-01",
                    {
                        P_PLASTIC: _p(_over(plastic_limit), plastic_limit["unit"]),
                        P_BATTERY: _p("lead_acid", ""),
                        P_CUTOFF: _p(True, ""),
                        P_AT_BATTERY: _p(True, ""),
                        P_AT_CONTROLLER: _p(True, ""),
                        P_AT_LIMITER: _p(True, ""),
                    },
                ),
                "expect": {"findings": {P_PLASTIC: "non_compliant"}},
                "expect_overall": "non_compliant",
                "notes": "塑料占比越限 → 不符合。",
            }
        )

    # ---- 铅蓄电池车型整车质量：62 / 63 / 64 kg（题面举例）----
    lead = limb.get(P_MASS)
    if lead:
        for label, delta, expected_state in (
            ("at", 0, "compliant"),
            ("under", -1, "compliant"),
            ("over", 1, "non_compliant"),
        ):
            seq += 1
            value = _shift(lead, delta, label)
            entry = {
                "case_id": "SYN-CASE-{0:03d}".format(seq),
                "kind": KIND_BOUNDARY_AT if label == "at" else KIND_BOUNDARY_UNDER
                if label == "under"
                else KIND_BOUNDARY_OVER,
                "target_param": P_MASS,
                "profile": _profile(
                    seq,
                    "2025-10-01",
                    {
                        P_MASS: _p(value, lead["unit"]),
                        P_BATTERY: _p("lead_acid", ""),
                        P_SPEED: _p(_under(speed_limit) if speed_limit else "20", "km/h"),
                        P_PLASTIC: _p(_under(plastic_limit) if plastic_limit else "1.0", "%"),
                        P_CUTOFF: _p(True, ""),
                        P_AT_BATTERY: _p(True, ""),
                        P_AT_CONTROLLER: _p(True, ""),
                        P_AT_LIMITER: _p(True, ""),
                    },
                ),
                "expect": {"findings": {P_MASS: expected_state}},
                "expect_overall": "non_compliant" if expected_state == "non_compliant" else None,
                "notes": "铅蓄电池车型整车质量 {0} 限值（{1}）。".format(label, expected_state),
            }
            if entry["expect_overall"] is None:
                del entry["expect_overall"]
            cases.append(entry)

    # ---- 缺参数：缺塑料占比 → 未提供，绝不判符合 ----
    seq += 1
    cases.append(
        {
            "case_id": "SYN-CASE-{0:03d}".format(seq),
            "kind": KIND_MISSING,
            "target_param": P_PLASTIC,
            "profile": _profile(
                seq,
                "2025-10-01",
                {
                    P_SPEED: _p(_under(speed_limit) if speed_limit else "20", "km/h"),
                    P_BATTERY: _p("lead_acid", ""),
                    P_CUTOFF: _p(True, ""),
                    P_AT_BATTERY: _p(True, ""),
                    P_AT_CONTROLLER: _p(True, ""),
                    P_AT_LIMITER: _p(True, ""),
                },
            ),
            "expect": {"findings": {P_PLASTIC: "not_provided"}},
            "notes": "未提供塑料占比 → 未提供（绝不判为符合）。",
        }
    )

    # ---- 单位换算：质量用 g 提供 → 换算后判定并降级 warning ----
    if lead:
        seq += 1
        grams = _to_grams(lead)
        cases.append(
            {
                "case_id": "SYN-CASE-{0:03d}".format(seq),
                "kind": KIND_UNIT_CONVERT,
                "target_param": P_MASS,
                "profile": _profile(
                    seq,
                    "2025-10-01",
                    {
                        P_MASS: _p(grams, "g"),
                        P_BATTERY: _p("lead_acid", ""),
                        P_SPEED: _p(_under(speed_limit) if speed_limit else "20", "km/h"),
                        P_PLASTIC: _p(_under(plastic_limit) if plastic_limit else "1.0", "%"),
                        P_CUTOFF: _p(True, ""),
                        P_AT_BATTERY: _p(True, ""),
                        P_AT_CONTROLLER: _p(True, ""),
                        P_AT_LIMITER: _p(True, ""),
                    },
                ),
                "expect": {"findings": {P_MASS: "compliant"}},
                "expect_severity_warning": True,
                "notes": "质量以 g 提供、限值以 kg 计 → 显式换算后判定，只报 warning。",
            }
        )

    # ---- 干净档案：全参数达标 → 应零命中 ----
    seq += 1
    clean_params = _fill_compliant(
        {
            P_BATTERY: _p("lead_acid", ""),
        },
        {key: value for key, value in limb.items() if key != P_BATTERY},
    )
    cases.append(
        {
            "case_id": "SYN-CASE-{0:03d}".format(seq),
            "kind": KIND_CLEAN,
            "profile": _profile(seq, "2025-10-01", clean_params),
            "expect": {"findings": {}},
            "expect_findings": [],
            "expect_overall": "compliant",
            "notes": "全参数达标 → 检出越限数必须为 0（误报对照集；参数集随规则包增长自动补齐）。",
        }
    )

    # ---- 版本差异：同一铅蓄电池车型质量（2018 版越限、2024 版符合）----
    if lead and old.get(P_MASS):
        old_mass = old[P_MASS]
        # 取一个"落在两版限值之间"的值：旧版之上、新版之下。
        between = _between(old_mass, lead)
        if between is not None:
            seq += 1
            cases.append(
                {
                    "case_id": "SYN-CASE-{0:03d}".format(seq),
                    "kind": KIND_VERSION_DIFF,
                    "target_param": P_MASS,
                    "profile": _profile(
                        seq,
                        "2025-10-01",
                        {
                            P_MASS: _p(between, lead["unit"]),
                            P_BATTERY: _p("lead_acid", ""),
                            P_SPEED: _p(_under(speed_limit) if speed_limit else "20", "km/h"),
                            P_PLASTIC: _p(_under(plastic_limit) if plastic_limit else "1.0", "%"),
                            P_CUTOFF: _p(True, ""),
                            P_AT_BATTERY: _p(True, ""),
                            P_AT_CONTROLLER: _p(True, ""),
                            P_AT_LIMITER: _p(True, ""),
                        },
                    ),
                    "expect": {"findings": {P_MASS: "compliant"}},
                    "expect_by_version": {
                        "GB17761-2024": {P_MASS: "compliant"},
                        "GB17761-2018": {P_MASS: "non_compliant"},
                    },
                    "notes": "质量落在旧版限值之上、新版限值之下 → 换版即改判，验证版本切换。",
                }
            )

    return cases


# ---- 限值派生助手（**不硬编码数值**，全部由规则包的 value 推出）----


def _epsilon(unit):
    sys.path.insert(0, os.path.join(_ROOT, "src"))
    from ebikecheck.engine.values import epsilon_for

    return epsilon_for(unit)


def _at(limit):
    """恰好等于限值。"""
    return str(limit["value"])


def _over(limit):
    from decimal import Decimal

    return str(Decimal(str(limit["value"])) + _epsilon(limit["unit"]))


def _under(limit):
    from decimal import Decimal

    return str(Decimal(str(limit["value"])) - _epsilon(limit["unit"]))


def _shift(limit, steps, label):
    from decimal import Decimal

    factor = Decimal(steps) * _epsilon(limit["unit"])
    return str(Decimal(str(limit["value"])) + factor)


def _to_grams(limit):
    """把 kg 限值转成 g，且**仍在限值之内**（取限值本身 → 换算后恰好等于）。"""
    from decimal import Decimal

    return str(Decimal(str(limit["value"])) * Decimal("1000"))


def _between(old_limit, new_limit):
    """取一个旧版越限、新版符合的值；两限值相等或无区间时返回 ``None``。"""
    from decimal import Decimal

    low = Decimal(str(old_limit["value"]))
    high = Decimal(str(new_limit["value"]))
    if high <= low:
        return None
    mid = (low + high) / Decimal("2")
    # 归到该单位的最小计量单位网格上，避免出现"半个计量单位"的伪值。
    step = _epsilon(new_limit["unit"])
    return str((mid / step).to_integral_value() * step)


def ruleset_view(data_dir):
    """从规则包提取 ``{version_key: {param: {"op","value","unit"}}}``（只取 verified）。"""
    from ebikecheck.engine import rules as rules_mod

    manifest = rules_mod.load_manifest(data_dir)
    view = {}
    for entry in manifest.rulesets:
        ruleset = rules_mod.load_ruleset_file(os.path.join(data_dir, "rules", entry["file"]))
        params = {}
        for rule in ruleset.rules:
            params.setdefault(rule.param, {"op": rule.op, "value": rule.value, "unit": rule.unit})
        view[entry["version_key"]] = params
    return view


def render_cases(data_dir):
    """产出 ``{文件名: 文本}``。"""
    view = ruleset_view(data_dir)
    cases = build_cases(view)
    rendered = {}
    for case in cases:
        rendered["{0}.json".format(case["case_id"])] = dumps_json(case)
    rendered["index.json"] = dumps_json(
        {
            "schema": "ebikecheck.truth/1.0",
            "generated_by": "tools/gen_synthetic.py",
            "generator_version": GENERATOR_VERSION,
            "seed": SEED,
            "synthetic_tag": SYNTHETIC_TAG,
            "fake_manufacturer": FAKE_MANUFACTURER,
            "case_count": len(cases),
            "cases": [
                {"case_id": case["case_id"], "kind": case["kind"], "file": "{0}.json".format(case["case_id"])}
                for case in cases
            ],
        }
    )
    return rendered


def cmd_generate(data_dir):
    rendered = render_cases(data_dir)
    for name in sorted(rendered):
        write_text(os.path.join(OUT_DIR, name), rendered[name])
    return rendered


def cmd_check(data_dir):
    rendered = render_cases(data_dir)
    drift = []
    for name in sorted(rendered):
        path = os.path.join(OUT_DIR, name)
        actual = None
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", newline="") as handle:
                actual = handle.read()
        if actual != rendered[name]:
            drift.append(name)
    if drift:
        print("真值库与生成器不一致（禁手改）: {0}".format(", ".join(drift)))
        return 1
    print("SYNTHETIC_FROZEN_OK ({0} 份)".format(len(rendered)))
    return 0


def main(argv=None):
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="合成车型档案 + 真值库生成器")
    parser.add_argument("--check", action="store_true", help="与磁盘逐字节比对")
    parser.add_argument("--data-dir", default=None, help="数据目录（默认自动定位）")
    args = parser.parse_args(argv)

    if args.data_dir:
        data_dir = os.path.abspath(args.data_dir)
    else:
        data_dir = os.path.join(_ROOT, "data")

    if args.check:
        return cmd_check(data_dir)
    rendered = cmd_generate(data_dir)
    print("已生成 {0} 份到 {1}".format(len(rendered), OUT_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
