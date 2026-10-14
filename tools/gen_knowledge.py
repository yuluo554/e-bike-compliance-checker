#!/usr/bin/env python
"""依据索引生成器 —— ``data/knowledge/clauses.json`` 的**唯一写入者**。

用途（[plan/05](../plan/05-数据计划与里程碑.md) §1.1、[plan/04](../plan/04-模块详设.md) §5.4）：
让读者**不开仓库也能核证**"这个限值哪来的、条款号是几"——
每条规则挂发布机关/标准号/条款号/条款状态/官方 URL/抓取日期；
每份官方快照挂 sha256；标准全文的逐页摘要单独登记为审计线索。

纪律（与其余生成器一致）：

- 禁 stdlib ``random``、禁 ``set`` 迭代序、禁系统时钟 → 产物**无时间戳**；
- ``--check`` 重新生成并与磁盘**逐字节比对**；
- **快照 sha256 现算**（在 ``data/knowledge/raw/`` 上读文件算），避免手工登记漂移。
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
    sha256_file,
    write_text,
)

SOURCE_PATH = os.path.join(_HERE, "sources", "knowledge_source.json")
RULES_SOURCE_PATH = os.path.join(_HERE, "sources", "rules_source.json")
RULES_DIR = os.path.join(_ROOT, "data", "rules")
RAW_DIR = os.path.join(_ROOT, "data", "knowledge", "raw")
OUT_PATH = os.path.join(_ROOT, "data", "knowledge", "clauses.json")
GENERATOR_VERSION = "1.0.0"


def _clause_key(rule):
    return (rule.get("clause") or "", rule.get("standard", ""))


def build_knowledge(source, rules_source):
    """把规则包逐条挂上依据（纯函数，无 IO 副作用）。"""
    authorities = source["authorities"]

    snapshots = []
    for item in source["snapshots"]:
        path = os.path.join(RAW_DIR, item["file"])
        if not os.path.isfile(path):
            raise SystemExit("依据索引登记的快照文件缺失: {0}".format(item["file"]))
        snapshots.append(
            {
                "file": item["file"],
                "kind": item["kind"],
                "standard": item["standard"],
                "authority": item["authority"],
                "authority_name": authorities[item["authority"]]["name"],
                "url": item["url"],
                "retrieved_on": item["retrieved_on"],
                "sha256": sha256_file(path),
                "supports": item.get("supports", ""),
            }
        )

    # 逐条限值 → 依据条目（条款号 / 条款状态 / 来源 URL / 抓取日期）。
    clauses = []
    for name in sorted(os.listdir(RULES_DIR)):
        if not name.endswith(".json") or name == "manifest.json":
            continue
        raw = read_json(os.path.join(RULES_DIR, name))
        standard_code = raw["standard"]["code"]
        for rule in raw["rules"]:
            # 规则包内的 source 块已由 gen_rulesets 从 rules_source 展开，
            # 这里直接采用，避免二次回查造成口径漂移。
            clauses.append(
                {
                    "rule_id": rule["id"],
                    "param": rule["param"],
                    "standard": standard_code,
                    "standard_title": raw["standard"]["title"],
                    "scope": raw["scope"],
                    "clause": rule.get("clause"),
                    "clause_status": rule.get("clause_status"),
                    "status": rule.get("status"),
                    "limit": rule.get("value"),
                    "unit": rule.get("unit", ""),
                    "clause_excerpt": rule.get("clause_excerpt", ""),
                    "source_kind": rule["source"].get("kind", ""),
                    "source_title": rule["source"].get("title", ""),
                    "source_issuer": rule["source"].get("issuer", ""),
                    "source_url": rule["source"].get("url", ""),
                    "retrieved_on": rule["source"].get("retrieved_on", ""),
                    "verified_on": rule.get("verified_on", ""),
                    "notes": rule.get("notes", ""),
                }
            )

    fulltext = []
    for item in source["fulltext_retrieval"]:
        fulltext.append(
            {
                "standard": item["standard"],
                "channel": item["channel"],
                "viewer_url": item["viewer_url"],
                "page_count": item["page_count"],
                "page_sha256_digest": item["page_sha256_digest"],
                "retrieved_on": item["retrieved_on"],
                "notes": item.get("notes", ""),
            }
        )

    clause_verified = sum(1 for item in clauses if item["clause_status"] == "verified")
    return {
        "schema_version": "1.0",
        "generated_by": "tools/gen_knowledge.py",
        "generator_version": GENERATOR_VERSION,
        "authorities": [dict(authorities[key], key=key) for key in sorted(authorities)],
        "fulltext_retrieval": fulltext,
        "snapshots": snapshots,
        "clauses": clauses,
        "clause_verified_count": clause_verified,
        "clause_pending_count": len(clauses) - clause_verified,
    }


def render(source, rules_source):
    return dumps_json(build_knowledge(source, rules_source))


def cmd_generate(source, rules_source):
    write_text(OUT_PATH, render(source, rules_source))
    return render(source, rules_source)


def cmd_check(source, rules_source):
    rendered = render(source, rules_source)
    actual = None
    if os.path.isfile(OUT_PATH):
        with open(OUT_PATH, "r", encoding="utf-8", newline="") as handle:
            actual = handle.read()
    if actual != rendered:
        print("依据索引与生成器不一致（禁手改；请重生成）: data/knowledge/clauses.json")
        return 1
    print("KNOWLEDGE_FROZEN_OK (1 份)")
    return 0


def main(argv=None):
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="依据索引生成器（data/knowledge/clauses.json 唯一写入者）")
    parser.add_argument("--check", action="store_true", help="与磁盘逐字节比对")
    args = parser.parse_args(argv)

    with open(SOURCE_PATH, "r", encoding="utf-8", newline="") as handle:
        source = json.loads(handle.read())
    with open(RULES_SOURCE_PATH, "r", encoding="utf-8", newline="") as handle:
        rules_source = json.loads(handle.read())

    if args.check:
        return cmd_check(source, rules_source)
    cmd_generate(source, rules_source)
    print("已生成依据索引到 {0}".format(OUT_PATH))
    return 0


if __name__ == "__main__":
    sys.exit(main())
