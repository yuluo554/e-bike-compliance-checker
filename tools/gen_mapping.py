#!/usr/bin/env python
"""字段映射表生成器 —— ``data/mapping/`` 的**唯一写入者**。

纪律（[plan/05](../plan/05-数据计划与里程碑.md) §2.1/§2.3，与其余生成器一致）：

- 禁 stdlib ``random``、禁 ``set`` 迭代序、禁系统时钟 → 产物**无时间戳**；
- 输出 ``ensure_ascii=False`` / ``indent=2`` / ``\\n`` 行尾 / UTF-8 无 BOM；
- ``--check`` 重新生成并与磁盘**逐字节比对**（守门测试调用）。

**本脚本不得内联任何限值数值** —— 映射表只承载"列名/单位别名"标识。

覆盖口径：**必须覆盖规则包里的全部标准参数**（含 pending 条目，否则 M3 的映射
引擎会遇到"规则有、映射无"的参数）。生成时会与规则包对账，缺一即报错退出。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from ebikecheck.io_utils import (  # noqa: E402
    _ensure_utf8_stdio,
    dumps_json,
    read_json,
    write_text,
)

SOURCE_PATH = os.path.join(_HERE, "sources", "mapping_source.json")
OUT_DIR = os.path.join(_ROOT, "data", "mapping")
RULES_DIR = os.path.join(_ROOT, "data", "rules")
GENERATOR_VERSION = "1.0.0"

PARAM_KEY_ORDER = (
    "param",
    "scope",
    "canonical",
    "unit",
    "variants",
    "ambiguous_variants",
    "notes",
)


def _ordered_param(item):
    ordered = {}
    for key in PARAM_KEY_ORDER:
        if key in item:
            ordered[key] = item[key]
    for key in sorted(item):
        if key not in ordered:
            ordered[key] = item[key]
    return ordered


def _ruleset_params():
    """规则包里出现过的全部标准参数（含 pending 条目）。"""
    params = []
    for name in sorted(os.listdir(RULES_DIR)):
        if not name.endswith(".json") or name == "manifest.json":
            continue
        raw = read_json(os.path.join(RULES_DIR, name))
        for rule in raw.get("rules", []):
            param = rule.get("param")
            if param and param not in params:
                params.append(param)
    return params


def build_mapping(source):
    """展开映射表（纯函数，无 IO 副作用）。"""
    params = [_ordered_param(item) for item in source["parameters"]]
    declared = [item["param"] for item in params]

    # 覆盖对账：规则包的每个参数都必须在映射表中登记。
    missing = [name for name in _ruleset_params() if name not in declared]
    if missing:
        raise SystemExit(
            "映射表未覆盖规则包参数（M3 会遇『规则有、映射无』）: {0}".format(", ".join(missing))
        )
    duplicated = [name for name in declared if declared.count(name) > 1]
    if duplicated:
        raise SystemExit("映射表参数重复登记: {0}".format(", ".join(sorted(set(duplicated)))))

    # 列名变体不得碰撞：同一列名只能映射到一个参数（否则 M3 必然歧义）。
    seen = {}
    for item in params:
        for variant in item["variants"]:
            if variant in seen and seen[variant] != item["param"]:
                raise SystemExit(
                    "列名变体 {0!r} 同时映射到 {1} 与 {2}".format(
                        variant, seen[variant], item["param"]
                    )
                )
            seen[variant] = item["param"]
        for variant in item["ambiguous_variants"]:
            if variant in seen and seen[variant] != item["param"]:
                raise SystemExit(
                    "歧义列名 {0!r} 已作为确定变体登记于 {1}".format(variant, seen[variant])
                )

    aliases = {}
    for unit in sorted(source["unit_aliases"]):
        seen_alias = []
        for alias in source["unit_aliases"][unit]:
            if alias not in seen_alias:
                seen_alias.append(alias)
        aliases[unit] = seen_alias

    return {
        "schema_version": "1.0",
        "generated_by": "tools/gen_mapping.py",
        "generator_version": GENERATOR_VERSION,
        "param_count": len(params),
        "parameters": params,
        "unit_aliases": aliases,
    }


def render(source):
    return {"mapping.json": dumps_json(build_mapping(source))}


def cmd_generate(source):
    rendered = render(source)
    for name in sorted(rendered):
        write_text(os.path.join(OUT_DIR, name), rendered[name])
    return rendered


def cmd_check(source):
    rendered = render(source)
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
        print("映射表与生成器不一致（禁手改；请用生成器整目录重生成）: {0}".format(", ".join(drift)))
        return 1
    print("MAPPING_FROZEN_OK ({0} 份)".format(len(rendered)))
    return 0


def main(argv=None):
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="字段映射表生成器（data/mapping/ 唯一写入者）")
    parser.add_argument("--check", action="store_true", help="与磁盘逐字节比对")
    args = parser.parse_args(argv)

    with open(SOURCE_PATH, "r", encoding="utf-8", newline="") as handle:
        source = json.loads(handle.read())

    if args.check:
        return cmd_check(source)
    rendered = cmd_generate(source)
    print("已生成 {0} 份到 {1}".format(len(rendered), OUT_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
