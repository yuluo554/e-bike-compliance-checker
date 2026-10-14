#!/usr/bin/env python
"""脱敏审计器（入仓可复跑）：tracked / history / messages 三模式 + selftest。

**输出一律不回显敏感原文**（只报 ``文件:行号 [类别] xN``），因此审计报告可随仓留档。

命中分级：

- ``HARD``      → 退出码 1（真实泄露形态：个人邮箱、手机号、用户目录路径、密钥）
- ``REVIEW``    → 只提示（系统目录、其他盘符路径等需人工豁免留档）
- ``advisory``  → 只报不阻断（长 hex 串：**本项目的 sha256 指纹是文档化功能**）

豁免（并进阴性对照）：

- ``*@users.noreply.github.com`` —— 脱敏后的目标形态本身；
- ``git@github.com`` / ``github.com/<账号>`` —— 发布固有公开元数据；
- 行内 ``audit-allow`` 标记 —— 供 selftest 夹具与刻意构造的样本使用。

**模式源码里的词面用片段拼接构造**，避免扫描器自命中（源码入仓后永久可见）。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))

from ebikecheck.io_utils import _ensure_utf8_stdio, iter_text_files, read_text  # noqa: E402

MARKER = "audit-allow"

#: 片段拼接构造词面（防扫描器自命中）。
_SEG = {
    "sk": "s" + "k-",
    "user_dir_win": "C:" + "\\" + "Users" + "\\",
    "user_dir_posix": "/ho" + "me/",
    "user_dir_mac": "/Us" + "ers/",
    "progdata": "Program" + "Data",
    "phone_prefix": "1" + "[3-9]",
}
#: 个人目录名（本机用户名）——由环境变量推导，**不写死进源码**。
def _local_user_hint():
    hint = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    return hint

#: 邮箱：本地部分**必须以字母数字开头**，域名**至少两段**。
#: 收紧的理由（实测）：`git log -p` 的 diff 前缀 `+` 落在宽松模式的本地部分字符集里，
#: 于是 `+@pytest.fixture` 被判成邮箱（三条假 HARD）。真实邮箱必然以字母数字开头。
EMAIL_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}"
)
NOREPLY_RE = re.compile(r"^[^@]*@users\.noreply\.github\.com$", re.IGNORECASE)
TRANSPORT_RE = re.compile(r"^(git|ssh|hg)@[A-Za-z0-9.-]+$", re.IGNORECASE)
#: 手机号：加 hex 边界环视，避免 sha256 十六进制串里的数字段误报。
PHONE_RE = re.compile(r"(?<![0-9a-fA-F])1[3-9]\d{9}(?![0-9a-fA-F])")
IDCARD_RE = re.compile(r"(?<![0-9A-Za-z])[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?![0-9A-Za-z])")
KEY_RE = re.compile(_SEG["sk"] + r"[A-Za-z0-9]{16,}")
LONG_HEX_RE = re.compile(r"\b[0-9a-fA-F]{40,}\b")
GITHUB_URL_RE = re.compile(r"github\.com[/:][A-Za-z0-9._-]+")

#: POSIX 个人目录：**要求 `/home/` 不是 URL 里的路径段**（audit-allow：本行是检测器自述，非泄露样本）。
#: 收紧的理由（实测）：官方站点链接（如 `https://www.gov.cn/home/2023-03/29/...`）含
#: `/home/`，宽松子串匹配会把官方快照整批判成 HARD（audit-allow：同上）。真实泄露形态是**文件系统路径**
#: （行首/空白/引号/`=` 之后），其前一字符不是域名类字符 → 用环视区分。
POSIX_HOME_RE = re.compile(r"(?<![A-Za-z0-9.-])" + _SEG["user_dir_posix"])

TEXT_SUFFIXES = (".py", ".md", ".json", ".toml", ".cfg", ".txt", ".yml", ".yaml", ".spec", ".in", ".html")
BINARY_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".exe", ".zip", ".pdf", ".docx", ".xlsx", ".pyc", ".so", ".pyd", ".dll")


class Hit:
    def __init__(self, path, line_no, category, level, count=1, note=""):
        self.path = path
        self.line_no = line_no
        self.category = category
        self.level = level
        self.count = count
        self.note = note

    def __str__(self):
        return "  {0}:{1} [{2}] x{3}{4}".format(
            self.path, self.line_no, self.category, self.count,
            " ({0})".format(self.note) if self.note else "",
        )


def _classify_email(value):
    if NOREPLY_RE.match(value) or TRANSPORT_RE.match(value):
        return None
    return ("email", "HARD")


def scan_text(text, path, line_offset=0):
    """扫描一段文本；返回命中列表。"""
    hits = []
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        if MARKER in line:
            continue
        line_no = index + line_offset
        emails = EMAIL_RE.findall(line)
        for value in emails:
            verdict = _classify_email(value)
            if verdict:
                hits.append(Hit(path, line_no, verdict[0], verdict[1]))
        # 排除邮箱局部与 GitHub URL 之后再判手机号/身份证，降噪。
        scrubbed = EMAIL_RE.sub(" ", line)
        scrubbed = GITHUB_URL_RE.sub(" ", scrubbed)
        if PHONE_RE.search(scrubbed):
            hits.append(Hit(path, line_no, "phone-like", "HARD"))
        if IDCARD_RE.search(scrubbed):
            hits.append(Hit(path, line_no, "idcard-like", "HARD"))
        if KEY_RE.search(scrubbed):
            hits.append(Hit(path, line_no, "secret-key", "HARD"))
        if _SEG["user_dir_win"] in line or POSIX_HOME_RE.search(line) or _SEG["user_dir_mac"] in line:
            hits.append(Hit(path, line_no, "user-home-path", "HARD"))
        if _SEG["progdata"] in line and _local_user_hint():
            hits.append(Hit(path, line_no, "work-root-path", "REVIEW", note="本地工作根形态"))
        if LONG_HEX_RE.search(scrubbed):
            hits.append(
                Hit(path, line_no, "long-hex", "advisory", note="指纹/哈希类，只报不阻断")
            )
    return hits


def _git(args, cwd=None):
    return subprocess.run(
        ["git", "-c", "core.quotepath=false"] + args,
        cwd=cwd or _ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    ).stdout.decode("utf-8", "replace")


def mode_tracked(extra_root=None):
    """扫描已跟踪文件（提交后即权威审查面）。"""
    files = _git(["ls-files"]).splitlines()
    if not files:
        # 无 git（如 git archive 导出树）→ 退回文件系统遍历。
        root = extra_root or _ROOT
        files = [
            os.path.relpath(path, _ROOT)
            for path in iter_text_files(root, TEXT_SUFFIXES)
        ]
    hits = []
    for relative in files:
        if relative.endswith(BINARY_SUFFIXES):
            continue
        if not relative.endswith(TEXT_SUFFIXES):
            continue
        path = os.path.join(_ROOT, relative)
        if not os.path.isfile(path):
            continue
        hits.extend(scan_text(read_text(path), relative))
    return hits


def mode_history():
    """逐提交扫描（**带通道探活**：先搜必然存在的串，搜不到即硬失败）。"""
    revs = _git(["rev-list", "--all"]).split()
    if not revs:
        return [], "no-history"
    probe = _git(["log", "--all", "--format=%H"]).strip()
    if not probe:
        return [], "probe-failed"
    hits = []
    for rev in revs:
        diff = _git(["show", "--format=", "--unified=0", rev])
        if not diff:
            continue
        for hit in scan_text(diff, "commit:{0}".format(rev[:8])):
            if "commit:" in hit.path:
                hits.append(hit)
    return hits, "ok"


def mode_messages():
    """扫描提交信息。"""
    text = _git(["log", "--all", "--format=%s%n%b"])
    return scan_text(text, "commit-messages")


def summarize(hits, modes):
    hard = [hit for hit in hits if hit.level == "HARD"]
    review = [hit for hit in hits if hit.level == "REVIEW"]
    advisory = [hit for hit in hits if hit.level == "advisory"]
    print("脱敏审计（模式: {0}）".format(", ".join(modes)))
    for title, group in (("HARD", hard), ("REVIEW", review), ("advisory", advisory)):
        print("  [{0}] {1} 处".format(title, len(group)))
        for hit in group[:40]:
            print(str(hit))
        if len(group) > 40:
            print("  … 其余 {0} 处略".format(len(group) - 40))
    if hard:
        print("DESSENSITIZE_AUDIT_FAIL")
        return 1
    print("DESSENSITIZE_AUDIT_OK")
    return 0


def selftest():
    """正负对照：阳性（合成泄露形态必须命中）+ 阴性（豁免形态不得命中）。"""
    problems = []
    # 阳性：程序化合成夹具（无字面假密钥/假手机号入仓）。
    synthetic_email = "user" + "@" + "example.com"
    synthetic_phone = "1" + "3800138000"
    synthetic_home = "C:" + "\\" + "Users" + "\\" + "someuser" + "\\" + "repo"
    positive = "\n".join(
        [
            "contact: {0}".format(synthetic_email),
            "phone: {0}".format(synthetic_phone),
            "path: {0}".format(synthetic_home),
        ]
    )
    hits = scan_text(positive, "selftest-synthetic")
    levels = {hit.category: hit.level for hit in hits}
    if levels.get("email") != "HARD":
        problems.append("阳性对照失败：非保留域邮箱未判 HARD")
    if levels.get("phone-like") != "HARD":
        problems.append("阳性对照失败：合成手机号未判 HARD")
    if levels.get("user-home-path") != "HARD":
        problems.append("阳性对照失败：用户目录路径未判 HARD")

    # 阴性：豁免形态不得命中 HARD。
    noreply = "12345+someone@users.noreply.github.com"
    transport = "git@github.com"
    ssh_url = "git@github.com:owner/repo.git"
    https_url = "https://github.com/owner/repo"
    negative = "\n".join([noreply, transport, ssh_url, https_url])
    neg_hits = [hit for hit in scan_text(negative, "selftest-negative") if hit.level == "HARD"]
    if neg_hits:
        problems.append("阴性对照失败：豁免形态被判 HARD: {0}".format(neg_hits[0].category))

    # 阴性：diff 前缀 `+` 与装饰器形态不得被判成邮箱。
    # 实测坑：`git log -p` 的行前缀 `+` 会被宽松邮箱正则吞进本地部分 → `+@pytest.fixture` 成假 HARD。
    decorators = "\n".join(
        [
            "+@pytest.fixture(scope=\"session\")",
            "+@pytest.fixture()",
            "@pytest.fixture(scope=\"session\")",
        ]
    )
    deco_hits = [hit for hit in scan_text(decorators, "selftest-decorator") if hit.category == "email"]
    if deco_hits:
        problems.append("阴性对照失败：装饰器/diff 前缀形态被判成邮箱")

    # 阴性：sha256 长 hex 只应 advisory。
    hexbed = "sha256 " + "a" * 64
    hex_hits = scan_text(hexbed, "selftest-hex")
    if any(hit.level == "HARD" for hit in hex_hits):
        problems.append("阴性对照失败：sha256 长 hex 被判 HARD（应为 advisory）")

    # 阳性：POSIX 文件系统路径仍须判 HARD（收紧环视后不得漏）。
    posix_home = _SEG["user_dir_posix"] + "someuser/repo/data"
    posix_hits = [hit for hit in scan_text("path: {0}".format(posix_home), "selftest-posix") if hit.category == "user-home-path"]
    if not posix_hits:
        problems.append("阳性对照失败：POSIX 个人目录路径未判 HARD")

    # 阴性：官方站点链接里的 `/home/` 路径段不得判 HARD（实测坑；audit-allow：本行是检测器自述）。
    official_urls = "\n".join(
        [
            '<li><a href="https://www.gov.cn/home/2023-03/29/content_5748953.htm">国务院部门网站</a></li>',
            '<a href="https://www.gov.cn/home/2016-05/11/content_5046257.htm">关于本网</a>',
        ]
    )
    url_hits = [hit for hit in scan_text(official_urls, "selftest-official-url") if hit.level == "HARD"]
    if url_hits:
        problems.append("阴性对照失败：官方站点链接被判 HARD（{0}）".format(url_hits[0].category))

    # 阴性：行内 audit-allow 必须放过。
    allowed = "phone: {0}  {1}".format(synthetic_phone, MARKER)
    if [hit for hit in scan_text(allowed, "selftest-allow") if hit.level == "HARD"]:
        problems.append("阴性对照失败：audit-allow 行未被放过")

    if problems:
        print("DESSENSITIZE_SELFTEST_FAIL")
        for problem in problems:
            print("  ! {0}".format(problem))
        return 1
    print("DESSENSITIZE_SELFTEST_OK")
    return 0


def main(argv=None):
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="脱敏审计器（三模式 + selftest）")
    parser.add_argument(
        "--mode",
        choices=("tracked", "history", "messages", "all"),
        default="all",
    )
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    modes = ["tracked", "history", "messages"] if args.mode == "all" else [args.mode]
    hits = []
    for mode in modes:
        if mode == "tracked":
            hits.extend(mode_tracked())
        elif mode == "history":
            found, status = mode_history()
            if status == "probe-failed":
                print("DESSENSITIZE_AUDIT_FAIL: 历史通道探活失败（扫描可能一直为空）")
                return 1
            hits.extend(found)
        else:
            hits.extend(mode_messages())
    return summarize(hits, modes)


if __name__ == "__main__":
    sys.exit(main())
