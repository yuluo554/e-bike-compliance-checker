#!/usr/bin/env python
"""脱敏审计器（入仓可复跑）：tracked / history / messages / dist 四模式 + selftest。

**输出一律不回显敏感原文**（只报 ``文件:行号 [类别] xN``），因此审计报告可随仓留档。

命中分级：

- ``HARD``      → 退出码 1（真实泄露形态：个人邮箱、手机号、用户目录路径、密钥）
- ``REVIEW``    → 只提示（系统目录、其他盘符路径等需人工豁免留档）
- ``advisory``  → 只报不阻断（长 hex 串：**本项目的 sha256 指纹是文档化功能**）

模式：

- ``tracked`` / ``history`` / ``messages`` —— 源码树、git 历史、提交信息；
- ``dist`` —— 构建产物本体（默认 ``dist/``）：文本按行扫、二进制按字节解码后扫；
  上游官方发行件固有元数据（CPython/OpenSSL/bzip2 维护者邮箱、Qt 构建机路径、
  厂商串）由 :mod:`dist_allowlist` **精确值**豁免并单列，其余命中照常判级。

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
for _candidate in (_HERE, os.path.join(_ROOT, "src")):
    if _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from ebikecheck.io_utils import _ensure_utf8_stdio, iter_text_files, read_text  # noqa: E402

import dist_allowlist  # noqa: E402  （同目录；上游固有元数据豁免清单，片段拼接）

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
    def __init__(self, path, line_no, category, level, count=1, note="", value=""):
        self.path = path
        self.line_no = line_no
        self.category = category
        self.level = level
        self.count = count
        self.note = note
        #: 命中的**精确值**（仅扫描期内部使用，输出不回显）。
        self.value = value

    def __str__(self):
        return "  {0}:{1} [{2}] x{3}{4}".format(
            self.path, self.line_no, self.category, self.count,
            " ({0})".format(self.note) if self.note else "",
        )


#: 常见通用顶级域（缺省集；加任意两字母小写国别域 —— 即"像域名"才判 HARD）。
_COMMON_GTLDS = frozenset(
    (
        "com", "org", "net", "edu", "gov", "mil", "int", "info", "biz", "name", "pro",
        "mobi", "asia", "jobs", "tel", "travel", "museum", "aero", "coop", "io", "co",
        "ai", "dev", "app", "tech", "cloud", "online", "site", "xyz", "me", "tv", "cc",
    )
)


def _email_tld_plausible(value):
    """二进制里"像邮箱"才判 HARD。

    实测坑：二进制字节流会随机拼出形如 ``x@y.z``（单字母顶级域）或宿主名式
    ``user@hostidentifier`` 的形态。规则 = 顶级域是**任意两字母小写国别域**或
    **常见通用域**；不满足的降为 ``REVIEW``（**仍然报出**，只是不阻断）——
    既不静默丢，也不让噪声卡住门禁。
    """
    tld = value.rsplit(".", 1)[-1]
    if len(tld) == 2 and tld.isalpha() and tld.islower():
        return True
    return tld.lower() in _COMMON_GTLDS


def _classify_email(value, binary=False):
    if NOREPLY_RE.match(value) or TRANSPORT_RE.match(value):
        return None
    if binary and not _email_tld_plausible(value):
        return ("email-suspect", "REVIEW")
    return ("email", "HARD")


def scan_text(text, path, line_offset=0, binary=False):
    """扫描一段文本；返回命中列表。

    ``binary=True``（构建产物本体）时，随机字节拼出的"邮箱形态"降为 REVIEW，
    避免噪声卡住门禁；真实形态的正负对照由 ``--selftest`` 守住。
    """
    hits = []
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        if MARKER in line:
            continue
        line_no = index + line_offset
        emails = EMAIL_RE.findall(line)
        for value in emails:
            verdict = _classify_email(value, binary=binary)
            if verdict:
                note = (
                    "二进制度量：不像真实邮箱，需人工确认"
                    if verdict[1] == "REVIEW"
                    else ""
                )
                hits.append(
                    Hit(path, line_no, verdict[0], verdict[1], note=note, value=value)
                )
        # 排除邮箱局部与 GitHub URL 之后再判手机号/身份证，降噪。
        scrubbed = EMAIL_RE.sub(" ", line)
        scrubbed = GITHUB_URL_RE.sub(" ", scrubbed)
        phone = PHONE_RE.search(scrubbed)
        if phone:
            hits.append(
                Hit(path, line_no, "phone-like", "HARD", value=phone.group(0))
            )
        idcard = IDCARD_RE.search(scrubbed)
        if idcard:
            hits.append(
                Hit(path, line_no, "idcard-like", "HARD", value=idcard.group(0))
            )
        key = KEY_RE.search(scrubbed)
        if key:
            hits.append(
                Hit(path, line_no, "secret-key", "HARD", value=key.group(0))
            )
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


def _suppress_upstream(text):
    """把上游固有元数据（精确值）替换为等长占位，返回 (text, 计数表)。

    计数表键为 :data:`dist_allowlist.ENTRIES` 的下标 —— 输出只报出处，不回显值。
    """
    counts = {}
    for index, entry in enumerate(dist_allowlist.ENTRIES):
        value = entry["value"]
        found = text.count(value)
        if found:
            counts[index] = found
            text = text.replace(value, "\x00" * len(value))
    return text, counts


def mode_dist(dist_dir=None):
    """构建产物本体扫描：``dist/``（或 ``--dist-dir``）下全部文件。

    文本类按 UTF-8 解码逐行扫，二进制按 latin-1 解码后扫（等价于字节子串扫，
    且保留行号语义）；上游固有元数据先精确替换再扫。
    """
    root = os.path.abspath(dist_dir or os.path.join(_ROOT, "dist"))
    if not os.path.isdir(root):
        return None, "missing:{0}".format(root)

    hits = []
    suppressed = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name != "__pycache__")
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            try:
                # 报告用：尽量给仓库相对路径；扫描根在别的盘符（如 selftest 的
                # 临时目录）时 relpath 会抛 ValueError，回落到扫描根相对路径。
                relative = os.path.relpath(path, _ROOT)
            except ValueError:
                relative = os.path.relpath(path, root)
            try:
                with open(path, "rb") as handle:
                    payload = handle.read()
            except OSError:
                continue
            is_text = name.endswith(TEXT_SUFFIXES)
            text = payload.decode("utf-8", "replace") if is_text else payload.decode("latin-1")
            text, counts = _suppress_upstream(text)
            for index, found in sorted(counts.items()):
                entry = dist_allowlist.ENTRIES[index]
                suppressed.append((entry["kind"], entry["source"], relative, found))
            hits.extend(scan_text(text, relative, binary=not is_text))
            # 本机用户名裸串（上游厂商串已被豁免替换，不会互相误伤）。
            user_hint = _local_user_hint()
            if user_hint and len(user_hint) >= 3 and user_hint in text:
                hits.append(Hit(relative, 0, "local-username", "HARD", value=user_hint))
    return (hits, suppressed), "ok"


def summarize(hits, modes, suppressed=None):
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
    if suppressed is not None:
        print("上游固有元数据豁免（精确值，不计入 HARD/REVIEW）: {0} 处".format(len(suppressed)))
        for kind, source, relative, found in suppressed[:40]:
            print("  [豁免] {0} ×{1} ({2}) | {3}".format(source, found, kind, relative))
        if len(suppressed) > 40:
            print("  … 其余 {0} 处略".format(len(suppressed) - 40))
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

    # 阳性：二进制模式里真实形态邮箱仍须 HARD（不能因为 binary 就整体降级）。
    bin_pos = [hit for hit in scan_text("mail {0}".format(synthetic_email), "selftest-bin", binary=True) if hit.level == "HARD"]
    if not bin_pos:
        problems.append("阳性对照失败：二进制模式未判出真实形态邮箱")

    # 阴性：二进制随机字节拼出的"邮箱形态"应降为 REVIEW，不得卡门禁。
    # 词面片段拼接：本文件会被 --mode tracked 扫描，逐字写形态会自命中。
    noise_one = "y" + "@" + "yMyQydy" + "." + "zP"
    noise_two = "z" + "@" + "D" + "." + "setdefault"
    noise_three = "ks_in" + "@" + "devanagari" + "." + "utf"
    binary_noise = "\n".join([noise_one, noise_two, noise_three])
    noise_hard = [hit for hit in scan_text(binary_noise, "selftest-bin-noise", binary=True) if hit.level == "HARD"]
    if noise_hard:
        problems.append("阴性对照失败：二进制噪声被判 HARD（{0}）".format(noise_hard[0].category))

    # 阳性：上游豁免清单必须真的能消掉登记值（防"清单写了但没接上"）。
    upstream_value = dist_allowlist.ENTRIES[0]["value"]
    filtered, counts = _suppress_upstream("contact {0} end".format(upstream_value))
    if not counts:
        problems.append("阳性对照失败：上游豁免清单未命中登记值（清单与扫描器脱钩）")
    if [hit for hit in scan_text(filtered, "selftest-upstream") if hit.level == "HARD"]:
        problems.append("阳性对照失败：上游豁免后仍判 HARD")

    if problems:
        print("DESSENSITIZE_SELFTEST_FAIL")
        for problem in problems:
            print("  ! {0}".format(problem))
        return 1
    print("DESSENSITIZE_SELFTEST_OK")
    return 0


def main(argv=None):
    _ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="脱敏审计器（tracked/history/messages/dist + selftest）")
    parser.add_argument(
        "--mode",
        choices=("tracked", "history", "messages", "dist", "all"),
        default="all",
    )
    parser.add_argument(
        "--dist-dir",
        default=None,
        help="--mode dist 的扫描根（缺省 dist/）",
    )
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if args.mode == "dist":
        result, status = mode_dist(args.dist_dir)
        if status.startswith("missing:"):
            print("DESSENSITIZE_AUDIT_FAIL: 目录不存在 {0}".format(status.split(":", 1)[1]))
            return 1
        hits, suppressed = result
        return summarize(hits, ["dist"], suppressed)

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
