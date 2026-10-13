"""仓库守门测试：确定性冻结、EOL/CR、编码守卫、门禁工具、分层约束、CI 配置。

这些测试的作用不是验业务逻辑，而是**守住"跨机器可复现"与"纪律不被绕过"**。
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys

import pytest
from conftest import DATA, ROOT, SRC, TOOLS

RULES_DIR = os.path.join(DATA, "rules")
TRUTH_DIR = os.path.join(DATA, "truth", "cases")

#: 需要保证 LF 行尾的路径（源码 + 冻结产物 + 文档）。
LF_REQUIRED_DIRS = (
    os.path.join("src", "ebikecheck"),
    "tools",
    "tests",
    "data",
    "plan",
    ".github",
)
LF_REQUIRED_FILES = ("README.md", "pyproject.toml", ".gitattributes", ".gitignore", "LICENSE")


def _iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git", ".venv")]
        for name in filenames:
            yield os.path.join(dirpath, name)


# ---- 确定性冻结 ----


def test_rulesets_regenerate_byte_identically():
    """规则包是生成器冻结产物：禁手改，再生成必须逐字节一致。"""
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "gen_rulesets.py"), "--check"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, output
    assert "RULESETS_FROZEN_OK" in output


def test_synthetic_truth_regenerate_byte_identically():
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "gen_synthetic.py"), "--check"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, output
    assert "SYNTHETIC_FROZEN_OK" in output


def test_manifest_sha256_matches_files():
    """manifest 登记的分册 sha256 必须与磁盘实际一致（产物与登记不脱钩）。"""
    from ebikecheck.engine import rules as rules_mod

    manifest = rules_mod.load_manifest(DATA)
    for entry in manifest.rulesets:
        path = os.path.join(RULES_DIR, entry["file"])
        assert rules_mod.sha256_file(path) == entry["sha256"], entry["file"]


def test_frozen_artifacts_contain_no_timestamp_like_rebuild_instability():
    """冻结产物不得带生成时间戳（否则"再生成逐字节一致"不成立）。"""
    for path in _iter_files(RULES_DIR):
        with open(path, "r", encoding="utf-8", newline="") as handle:
            text = handle.read()
        for marker in ("generated_at", "timestamp", "created_at", "生成时间\":"):
            assert marker not in text, "{0} 含时间戳字段 {1}".format(path, marker)


# ---- EOL / CR 门 ----


def test_no_carriage_returns_in_tracked_text():
    """Windows 开发机的 core.autocrlf 会把 LF 重写为 CRLF，破坏字节冻结。

    ``.gitattributes`` 只管检出/提交；本守门管**写入**——脚本默认 write_text
    会把 ``\\n`` 翻成 ``\\r\\n``，冻结件立刻带 CR。
    """
    offenders = []
    for relative in LF_REQUIRED_DIRS:
        root = os.path.join(ROOT, relative)
        if not os.path.isdir(root):
            continue
        for path in _iter_files(root):
            if path.endswith((".png", ".gif", ".jpg", ".ico", ".exe", ".zip", ".pyc")):
                continue
            with open(path, "rb") as handle:
                payload = handle.read()
            if b"\r\n" in payload or (b"\r" in payload and b"\n" not in payload):
                offenders.append(os.path.relpath(path, ROOT))
    for name in LF_REQUIRED_FILES:
        path = os.path.join(ROOT, name)
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as handle:
            if b"\r\n" in handle.read():
                offenders.append(name)
    assert not offenders, "以下文件含 CRLF（应统一 LF）:\n  " + "\n  ".join(offenders)


def test_gitattributes_pins_lf():
    path = os.path.join(ROOT, ".gitattributes")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    assert "text=auto" in text and "eol=lf" in text
    assert "binary" in text


# ---- 零字面量门禁 ----


def test_zero_literals_gate_passes():
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "check_zero_literals.py")],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, output
    assert "ZERO_LITERALS_OK" in output


def test_zero_literals_gate_selftest():
    """阳性对照：门禁必须真的会抓（防"token 集为空导致全绿假象"）。"""
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "check_zero_literals.py"), "--selftest"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, output
    assert "ZERO_LITERALS_SELFTEST_OK" in output


def test_zero_literals_token_set_is_not_empty():
    """空 token 集 = 门禁什么都没查（"全绿假象"）→ 必须非空。"""
    sys.path.insert(0, TOOLS)
    import check_zero_literals as gate

    banned = gate._collect_banned(DATA)
    assert len(banned) >= 3, "禁用 token 集过小，门禁可能未生效: {0}".format(sorted(banned))


# ---- 脱敏审计器 ----


def test_desensitize_selftest():
    """正负对照：合成泄露形态必须命中，豁免形态不得命中。"""
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "audit_desensitize.py"), "--selftest"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, output
    assert "DESSENSITIZE_SELFTEST_OK" in output


def test_desensitize_tracked_scan_is_clean():
    """常驻闸门：已跟踪树的脱敏扫描必须无 HARD 命中。

    HARD 命中即真实泄露形态（个人邮箱/手机号/用户目录路径/密钥）；
    advisory（sha256 长 hex）是本项目**文档化功能**，只报不阻断。
    """
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "audit_desensitize.py"), "--mode", "tracked"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, output
    assert "DESSENSITIZE_AUDIT_OK" in output


def test_desensitize_audit_has_positive_detection():
    """探活：审计器不是"永远绿"——合成泄露必须被扫出来。"""
    sys.path.insert(0, TOOLS)
    import audit_desensitize as audit

    synthetic = "mail " + "someone" + "@" + "example.com"
    hits = [hit for hit in audit.scan_text(synthetic, "probe") if hit.level == "HARD"]
    assert hits, "审计器对合成邮箱无反应 → 扫描可能失效"


# ---- 品牌隔离（D-30） ----


def test_sister_projects_are_masked_in_plan_overview():
    """品牌隔离纪律：前作名称与业务领域不入公开仓，plan 总览须显式掩码。

    这条断言的是"纪律被执行"（掩码表述存在），而不是扫未知词表 ——
    扫词表会命中规则自身与"不参赛"这类**正当的项目定位表述**（假阳性）。
    """
    path = os.path.join(ROOT, "plan", "00-README总览.md")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    assert "脱敏" in text and "不入公开仓" in text, "plan 总览缺少品牌隔离掩码表述"
    assert "品牌隔离" in text, "plan 总览缺少品牌隔离条目"


def test_readme_states_data_discipline():
    """README 必须写明合成数据纪律（虚构企业/测试号段），防真实数据混入。"""
    path = os.path.join(ROOT, "README.md")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    assert "合成" in text
    assert "SYN" in text


# ---- 编码守卫（所有会打印的入口） ----


def _calls_utf8_guard(path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        tree = ast.parse(handle.read(), filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "_ensure_utf8_stdio":
                return True
    return False


def test_cli_has_utf8_stdio_guard():
    assert _calls_utf8_guard(os.path.join(SRC, "ebikecheck", "cli.py"))


def test_all_printing_tools_have_utf8_stdio_guard():
    """**入口集合随里程碑增长** —— 每个 tools/ 脚本（含后期新增）都要守。

    Windows CI 管道是 cp1252，脚本 print 中文未守会直接崩，而开发机
    ``py -X utf8`` 会掩盖这一点（本机全绿证明不了跨环境）。
    """
    missing = []
    for name in sorted(os.listdir(TOOLS)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(TOOLS, name)
        with open(path, "r", encoding="utf-8", newline="") as handle:
            text = handle.read()
        if "print(" not in text:
            continue
        if not _calls_utf8_guard(path):
            missing.append(name)
    assert not missing, "以下脚本会打印但缺 _ensure_utf8_stdio 守卫: {0}".format(missing)


def test_utf8_guard_reconfigures_narrow_encoding():
    """窄编码管道应被 reconfigure；中文控制台编码应保持不动。"""
    import io

    from ebikecheck.io_utils import _ensure_utf8_stdio

    original = sys.stdout
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    try:
        sys.stdout = stream
        _ensure_utf8_stdio()
        assert "utf-8" in (stream.encoding or "").lower()
    finally:
        sys.stdout = original
        stream.detach()


def test_utf8_guard_leaves_cp936_alone():
    import io

    from ebikecheck.io_utils import _ensure_utf8_stdio

    original = sys.stdout
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp936", errors="strict")
    try:
        sys.stdout = stream
        _ensure_utf8_stdio()
        assert "cp936" in (stream.encoding or "").lower()
    finally:
        sys.stdout = original
        stream.detach()


# ---- 分层约束（AST 静态守门） ----


def test_cli_does_not_import_gui_at_module_level():
    """CLI 顶层不得 import GUI/PySide6（重件只许函数体内惰性导入）。"""
    path = os.path.join(SRC, "ebikecheck", "cli.py")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        tree = ast.parse(handle.read(), filename=path)
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            names = [alias.name for alias in node.names]
            assert "PySide6" not in module and "gui" not in module.split("."), (
                "cli.py 顶层不得 import GUI 重件: {0} {1}".format(module, names)
            )
            for name in names:
                assert not name.startswith("PySide6")


def _stdlib_top_levels():
    """标准库顶层模块名集合。

    ``sys.stdlib_module_names`` 是 3.10+ 才有 —— 3.8 上直接用它会让集合为空，
    于是**每个** import 都被判成第三方（假阳性）。故 3.8 回落到
    "从 ``sysconfig`` 标准库路径枚举 + 内置模块名"。
    """
    names = set(getattr(sys, "stdlib_module_names", ()))
    names.update(sys.builtin_module_names)
    names.add("__future__")
    try:
        import sysconfig

        stdlib_dir = sysconfig.get_paths().get("stdlib")
    except Exception:
        stdlib_dir = None
    if stdlib_dir and os.path.isdir(stdlib_dir):
        for entry in os.listdir(stdlib_dir):
            if entry.endswith(".py"):
                names.add(entry[:-3])
            elif os.path.isdir(os.path.join(stdlib_dir, entry)) and os.path.isfile(
                os.path.join(stdlib_dir, entry, "__init__.py")
            ):
                names.add(entry)
    return names


def test_engine_layer_imports_no_third_party():
    """核心层零第三方依赖：引擎模块不得 import 非标准库包。"""
    allowed_local = {"ebikecheck"}
    stdlib = _stdlib_top_levels()
    engine_dir = os.path.join(SRC, "ebikecheck", "engine")
    offenders = []
    for name in sorted(os.listdir(engine_dir)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(engine_dir, name)
        with open(path, "r", encoding="utf-8", newline="") as handle:
            tree = ast.parse(handle.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in stdlib and top not in allowed_local:
                        offenders.append("{0}: import {1}".format(name, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue
                top = (node.module or "").split(".")[0]
                if top and top not in stdlib and top not in allowed_local:
                    offenders.append("{0}: from {1}".format(name, node.module))
    assert not offenders, "引擎层出现第三方依赖: {0}".format(offenders)


# ---- CI 配置守门 ----


def test_workflow_files_are_parseable():
    """workflow YAML 必须可解析。

    隐蔽点：step 名是不带引号的纯量且含「冒号+空格」→ 整份 workflow 非法 →
    GitHub 不建任何 job（run 0 秒失败、jobs=0），而文件字节看着是干净的。
    """
    yaml = pytest.importorskip("yaml")
    wf_dir = os.path.join(ROOT, ".github", "workflows")
    assert os.path.isdir(wf_dir), "缺少 .github/workflows"
    files = [name for name in os.listdir(wf_dir) if name.endswith((".yml", ".yaml"))]
    assert files, "workflows 目录为空"
    for name in files:
        path = os.path.join(wf_dir, name)
        with open(path, "r", encoding="utf-8", newline="") as handle:
            payload = yaml.safe_load(handle.read())
        assert isinstance(payload, dict), "{0} 顶层必须是映射".format(name)
        assert "jobs" in payload and payload["jobs"], "{0} 缺少 jobs".format(name)
        for job_name, job in payload["jobs"].items():
            assert "runs-on" in job, "{0}/{1} 缺少 runs-on".format(name, job_name)
            assert job.get("steps"), "{0}/{1} 缺少 steps".format(name, job_name)


def test_every_checkout_step_uses_full_history():
    """历史扫描类守门依赖 git 历史；checkout 默认 fetch-depth: 1 会静默空验。"""
    yaml = pytest.importorskip("yaml")
    wf_dir = os.path.join(ROOT, ".github", "workflows")
    for name in sorted(os.listdir(wf_dir)):
        if not name.endswith((".yml", ".yaml")):
            continue
        with open(os.path.join(wf_dir, name), "r", encoding="utf-8", newline="") as handle:
            payload = yaml.safe_load(handle.read())
        for job_name, job in payload["jobs"].items():
            for step in job.get("steps", []):
                uses = str(step.get("uses", ""))
                if uses.startswith("actions/checkout"):
                    depth = (step.get("with") or {}).get("fetch-depth")
                    assert depth == 0, (
                        "{0}/{1} 的 checkout 未取全量历史（fetch-depth={2}）".format(
                            name, job_name, depth
                        )
                    )


def test_ci_matrix_covers_declared_targets():
    yaml = pytest.importorskip("yaml")
    path = os.path.join(ROOT, ".github", "workflows", "ci.yml")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        payload = yaml.safe_load(handle.read())
    job = payload["jobs"]["test"]
    matrix = job["strategy"]["matrix"]["include"]
    combos = {(item["os"], str(item["python"])) for item in matrix}
    assert ("windows-latest", "3.8") in combos
    assert ("windows-latest", "3.12") in combos
    assert ("ubuntu-latest", "3.12") in combos


def test_ci_installs_dev_extra():
    """CI 必须装 dev extra：pytest 本身住在 dev，"core-only 跑测试"会整批 ImportError。"""
    path = os.path.join(ROOT, ".github", "workflows", "ci.yml")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    assert "[dev]" in text
