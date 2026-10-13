#!/usr/bin/env python
"""规则包生成器 —— ``data/rules/`` 的**唯一写入者**。

纪律（[plan/05](../plan/05-数据计划与里程碑.md) §2.1）：

- 禁 stdlib ``random``、禁 ``set`` 迭代序、禁系统时钟 → 产物**无时间戳**；
- 输出 ``ensure_ascii=False`` / ``indent=2`` / ``\\n`` 行尾 / UTF-8 无 BOM；
- 写盘走显式 ``open(..., newline="\\n")``（3.8 的 ``Path.write_text`` 无 ``newline`` 参数）；
- ``--check`` 重新生成到内存并与磁盘逐字节比对，不一致即 exit 1（守门测试调用它）。

**本脚本不得内联任何限值数值** —— 数值只允许出现在 ``tools/sources/*.json``。
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
    sha256_bytes,
    write_text,
)

SOURCE_PATH = os.path.join(_HERE, "sources", "rules_source.json")
OUT_DIR = os.path.join(_ROOT, "data", "rules")
GENERATOR_VERSION = "1.0.0"

RULE_KEY_ORDER = (
    "id",
    "param",
    "op",
    "value",
    "unit",
    "clause",
    "clause_status",
    "applies_if",
    "source",
    "status",
    "verified_on",
    "clause_excerpt",
    "notes",
)


def _ordered_rule(rule):
    """按固定键序输出规则，保证同输入逐字节一致。"""
    ordered = {}
    for key in RULE_KEY_ORDER:
        if key in rule:
            ordered[key] = rule[key]
    for key in sorted(rule):
        if key not in ordered:
            ordered[key] = rule[key]
    return ordered


def _source_block(source_key, sources):
    block = sources[source_key]
    return {
        "kind": block["kind"],
        "url": block.get("url", ""),
        "retrieved_on": block.get("retrieved_on", ""),
        "title": block.get("title", ""),
        "issuer": block.get("issuer", ""),
    }


def build_rulesets(source):
    """把来源登记展开成 ``{文件名: 分册字典}``（纯函数，无 IO 副作用）。"""
    sources = source["sources"]
    standards = source["standards"]

    # 先按 standard 分组；用列表保持声明序（不用 set/dict 迭代序）。
    grouped = []
    for rule in source["rules"]:
        key = rule["standard"]
        bucket = None
        for item in grouped:
            if item[0] == key:
                bucket = item[1]
                break
        if bucket is None:
            bucket = []
            grouped.append((key, bucket))
        bucket.append(rule)

    # 按标准声明序输出分册（standards 的插入序即人工维护序）。
    files = {}
    order = list(standards.keys())
    for standard_key in order:
        meta = standards[standard_key]
        rules = []
        for key, bucket in grouped:
            if key != standard_key:
                continue
            for rule in bucket:
                item = {k: v for k, v in rule.items() if k != "standard"}
                item["source"] = _source_block(rule["source"], sources)
                rules.append(_ordered_rule(item))
        # 未被任何标准引用的分组 → 显式报错（防来源登记与标准表脱钩）。
        files[standard_key] = {
            "schema_version": "1.0",
            "standard": {
                "code": meta["code"],
                "title": meta["title"],
                "issuer": meta["issuer"],
                "published": meta["published"],
                "effective": meta["effective"],
                "status": meta["status"],
                "supersedes": meta["supersedes"],
                "mandatory": meta["mandatory"],
            },
            "scope": meta["scope"],
            "rules": rules,
        }

    for key, _bucket in grouped:
        if key not in standards:
            raise SystemExit("来源登记引用了未定义的标准键: {0}".format(key))
    return files


def build_manifest(source, files):
    """由分册内容算 sha256，产出 manifest（含版本锚点与门槛）。"""
    entries = []
    for standard_key in source["standards"]:
        meta = source["standards"][standard_key]
        file_name = "{0}.json".format(standard_key.lower())
        payload = dumps_json(files[standard_key]).encode("utf-8")
        entries.append(
            {
                "file": file_name,
                "standard": meta["code"],
                "scope": meta["scope"],
                "version_key": meta["version_key"],
                "effective_from": meta["effective"],
                "sha256": sha256_bytes(payload),
            }
        )
    return {
        "schema_version": "1.0",
        "generated_by": "tools/gen_rulesets.py",
        "generator_version": GENERATOR_VERSION,
        "rulesets": entries,
        "version_anchors": source["version_anchors"],
        "thresholds": source["thresholds"],
    }


def file_name_for(standard_key):
    return "{0}.json".format(standard_key.lower())


def _render_all(source):
    files = build_rulesets(source)
    manifest = build_manifest(source, files)
    rendered = {}
    for standard_key, payload in files.items():
        rendered[file_name_for(standard_key)] = dumps_json(payload)
    rendered["manifest.json"] = dumps_json(manifest)
    return rendered


def _read_disk(rendered):
    actual = {}
    for name in rendered:
        path = os.path.join(OUT_DIR, name)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", newline="") as handle:
                actual[name] = handle.read()
        else:
            actual[name] = None
    return actual


def cmd_generate(source):
    rendered = _render_all(source)
    for name in sorted(rendered):
        write_text(os.path.join(OUT_DIR, name), rendered[name])
    return rendered


def cmd_check(source):
    rendered = _render_all(source)
    actual = _read_disk(rendered)
    drift = []
    for name in sorted(rendered):
        if actual.get(name) != rendered[name]:
            drift.append(name)
    if drift:
        print("规则包与生成器不一致（禁手改；请用生成器整目录重生成）:")
        for name in drift:
            print("  - {0}".format(name))
        return 1
    print("RULESETS_FROZEN_OK ({0} 份)".format(len(rendered)))
    return 0


def main(argv=None):
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="规则包生成器（data/rules/ 唯一写入者）")
    parser.add_argument(
        "--check",
        action="store_true",
        help="重新生成并与磁盘逐字节比对（不一致 exit 1）",
    )
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
