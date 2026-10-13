#!/usr/bin/env python
"""零字面量门禁 —— 限值数值**只许来自规则包**，源码里出现即为缺陷。

原理：把规则包（``data/rules/*.json``）与来源登记（``tools/sources/*.json``）里的
全部数值收编为**禁用 token**，对引擎/基准/工具源码做词边界扫描（**含 docstring 与注释**）。

豁免口径（写死并进 ``--selftest`` 正负对照）：

- ``< 10`` 的小整数（精度约定、循环计数、版本号段）；
- 标准号本身（``17761`` 等）在源码中出现属**引用标识**而非限值 —— 但**限值数值**
  （如 25、63、5.5）无豁免；
- 单位串（``km/h``/``kg``/``%``）与参数名（``max_design_speed``）是标识不是限值；
- 本脚本自身与其 ``--selftest`` 夹具。

退出码：0 无命中 / 1 有命中 / 2 用法错误。
"""

from __future__ import annotations

import argparse
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from ebikecheck.io_utils import _ensure_utf8_stdio, iter_text_files, read_text  # noqa: E402

#: 扫描面（引擎 + 基准 + 工具脚本）。
SCAN_GLOBS = (
    os.path.join("src", "ebikecheck"),
    "benchmark",
    "tools",
)

#: 扫描面里**豁免**的文件（门禁自身与生成器需要读来源登记）。
EXEMPT_FILES = {
    "check_zero_literals.py",
    "gen_rulesets.py",
    "gen_synthetic.py",
    "audit_desensitize.py",
}

#: 不参与禁用 token 收集的键（这些字段承载"标识"而非"限值"）。
IDENTITY_KEYS = {
    "id",
    "param",
    "op",
    "unit",
    "clause",
    "clause_status",
    "code",
    "title",
    "issuer",
    "published",
    "effective",
    "status",
    "scope",
    "version_key",
    "file",
    "sha256",
    "schema_version",
    "generated_by",
    "generator_version",
    "effective_from",
    "standard",
    "supersedes",
    "mandatory",
    "url",
    "retrieved_on",
    "verified_on",
    "standard_family",
    "meta_source",
    "applies_from",
    "applies_until",
    "kind",
    "notes",
    "_comment",
}

#: 显式豁免的数值（版本号段与阈值——它们不是产品限值）。
EXEMPT_NUMBERS = {
    "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "0", "10", "100", "1000",
    "0.1", "0.001", "0.01", "0.98", "1.0", "3.6", "3600", "0.2777777777777777777777777778",
    "6", "12", "64", "65536",
}

#: 标准号片段（GB 17761 / 43854 / 42296 及其年份）——引用标识，非限值。
STANDARD_CODE_NUMBERS = {"17761", "43854", "42296", "1999", "2018", "2022", "2024", "2025", "2026"}


class GateError(Exception):
    """用法错误。"""


def _collect_banned(data_dir: str) -> dict:
    """从规则包收集禁用数值 token：``{token: 出处}``。"""
    from ebikecheck.io_utils import read_json

    banned = {}

    def visit(value, key, path):
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                visit(sub_value, sub_key, path)
            return
        if isinstance(value, list):
            for item in value:
                visit(item, key, path)
            return
        if key in IDENTITY_KEYS:
            return
        if isinstance(value, bool) or value is None:
            return
        token = str(value).strip()
        if not token:
            return
        if not re.fullmatch(r"-?\d+(\.\d+)?", token):
            return
        if token in EXEMPT_NUMBERS:
            return
        if token in STANDARD_CODE_NUMBERS:
            return
        # 负数取绝对值形态也纳入（如 -25）。
        banned.setdefault(token, path)
        if token.startswith("-"):
            banned.setdefault(token.lstrip("-"), path)

    rules_dir = os.path.join(data_dir, "rules")
    for name in sorted(os.listdir(rules_dir)):
        if not name.endswith(".json") or name == "manifest.json":
            continue
        visit(read_json(os.path.join(rules_dir, name)), "", name)
    return banned


def _iter_scan_files():
    for relative in SCAN_GLOBS:
        root = os.path.join(_ROOT, relative)
        if not os.path.isdir(root):
            continue
        for path in iter_text_files(root, (".py",)):
            if os.path.basename(path) in EXEMPT_FILES:
                continue
            yield path


def _line_of(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def scan(banned: dict, audit_allow_marker: str = "audit-allow") -> list:
    """扫描源码；返回命中列表 ``[(路径, 行号, token, 出处)]``。"""
    hits = []
    for path in sorted(_iter_scan_files()):
        text = read_text(path)
        for token in sorted(banned):
            pattern = re.compile(r"(?<![\w.])" + re.escape(token) + r"(?![\w.])")
            for match in pattern.finditer(text):
                line_no = _line_of(text, match.start())
                line = text.splitlines()[line_no - 1] if line_no - 1 < len(text.splitlines()) else ""
                if audit_allow_marker in line:
                    continue
                hits.append((path, line_no, token, banned[token]))
    return hits


def selftest() -> int:
    """正负对照：阳性（人造含限值的文件必须被抓）+ 阴性（标识不得误报）。"""
    import tempfile

    problems = []
    # 阳性对照：规则包数值必须能被抓出。
    banned = {"__pos__": "selftest"}
    probe_dir = tempfile.mkdtemp(prefix="ebc-zero-lit-")
    probe = os.path.join(probe_dir, "probe.py")
    with open(probe, "w", encoding="utf-8", newline="\n") as handle:
        handle.write("LIMIT = __pos__\n")
    original = SCAN_GLOBS
    try:
        globals()["SCAN_GLOBS"] = (probe_dir,)
        globals()["EXEMPT_FILES"] = set()
        hits = scan(banned)
        if not hits:
            problems.append("阳性对照失败：人造含限值文件未被抓出")
    finally:
        globals()["SCAN_GLOBS"] = original
        globals()["EXEMPT_FILES"] = {
            "check_zero_literals.py",
            "gen_rulesets.py",
            "gen_synthetic.py",
            "audit_desensitize.py",
        }
        try:
            os.remove(probe)
            os.rmdir(probe_dir)
        except OSError:
            pass

    # 阴性对照：单位串与参数名不得被收编为禁用 token。
    for identity in ("km/h", "kg", "%", "max_design_speed", "vehicle_mass"):
        if identity in _collect_banned(os.path.join(_ROOT, "data")):
            problems.append("阴性对照失败：标识 {0!r} 被误收为禁用 token".format(identity))

    # 阴性对照：小整数与标准号年份不得被收编。
    banned_real = _collect_banned(os.path.join(_ROOT, "data"))
    for allowed in ("10", "100", "2024", "2025", "17761"):
        if allowed in banned_real:
            problems.append("阴性对照失败：{0!r} 不应进禁用集".format(allowed))

    if problems:
        print("ZERO_LITERALS_SELFTEST_FAIL")
        for problem in problems:
            print("  ! {0}".format(problem))
        return 1
    print("ZERO_LITERALS_SELFTEST_OK")
    return 0


def main(argv=None):
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="零字面量门禁（限值只能来自规则包）")
    parser.add_argument("--data-dir", default=os.path.join(_ROOT, "data"))
    parser.add_argument("--selftest", action="store_true", help="正负对照自检")
    parser.add_argument("--list-tokens", action="store_true", help="打印收编的禁用 token")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    banned = _collect_banned(args.data_dir)
    if args.list_tokens:
        for token in sorted(banned, key=lambda item: (len(item), item)):
            print("{0:<12} <- {1}".format(token, banned[token]))
        return 0
    if not banned:
        # 空 token 集 = 门禁什么都没查（"全绿假象"）→ 硬失败。
        print("ZERO_LITERALS_FAIL: 禁用 token 集为空（门禁未生效）")
        return 1

    hits = scan(banned)
    if hits:
        print("ZERO_LITERALS_FAIL: 源码内出现限值数值（{0} 处）".format(len(hits)))
        for path, line_no, token, origin in hits[:50]:
            print(
                "  {0}:{1} [限值 {2}] <- {3}".format(
                    os.path.relpath(path, _ROOT), line_no, token, origin
                )
            )
        return 1
    print("ZERO_LITERALS_OK ({0} 个禁用 token 扫描面零命中)".format(len(banned)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
