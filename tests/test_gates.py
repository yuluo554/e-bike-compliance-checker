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
    "examples",
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


def test_mapping_regenerate_byte_identically():
    """字段映射表同样是生成器冻结产物：禁手改，再生成必须逐字节一致。"""
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "gen_mapping.py"), "--check"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, output
    assert "MAPPING_FROZEN_OK" in output


def test_mapping_covers_every_rule_package_param():
    """映射表必须覆盖规则包里的**全部**标准参数（含 pending 条目）。

    否则 M3 会遇"规则有、映射无"的参数 —— 那种缺口只有在批量扫描时才暴露，
    故在数据层先守住。
    """
    from ebikecheck.io_utils import read_json

    mapping = read_json(os.path.join(DATA, "mapping", "mapping.json"))
    mapped = {item["param"] for item in mapping["parameters"]}
    declared = set()
    for name in sorted(os.listdir(RULES_DIR)):
        if not name.endswith(".json") or name == "manifest.json":
            continue
        raw = read_json(os.path.join(RULES_DIR, name))
        for rule in raw.get("rules", []):
            declared.add(rule["param"])
    assert declared, "规则包未读到任何参数（夹具失效）"
    assert declared <= mapped, "映射表缺以下参数: {0}".format(sorted(declared - mapped))


def test_knowledge_regenerate_byte_identically():
    """依据索引同样是生成器冻结产物：禁手改，再生成必须逐字节一致。"""
    proc = subprocess.run(
        [sys.executable, os.path.join(TOOLS, "gen_knowledge.py"), "--check"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, output
    assert "KNOWLEDGE_FROZEN_OK" in output


def test_knowledge_snapshot_sha256_matches_files():
    """依据索引登记的快照 sha256 必须与磁盘实际一致（登记不脱钩）。"""
    from ebikecheck.io_utils import read_json, sha256_file

    payload = read_json(os.path.join(DATA, "knowledge", "clauses.json"))
    assert payload["snapshots"], "依据索引未登记任何官方快照"
    for item in payload["snapshots"]:
        path = os.path.join(DATA, "knowledge", "raw", item["file"])
        assert os.path.isfile(path), "快照文件缺失: {0}".format(item["file"])
        assert sha256_file(path) == item["sha256"], item["file"]


def test_knowledge_covers_every_rule_and_flags_pending_clauses():
    """依据索引必须逐条覆盖规则包；条款状态必须与规则包一致。

    条款号一旦 ``verified`` 就必须非空（不编造纪律的反面：也不许空标 verified）。
    """
    from ebikecheck.io_utils import read_json

    payload = read_json(os.path.join(DATA, "knowledge", "clauses.json"))
    by_id = {item["rule_id"]: item for item in payload["clauses"]}

    rule_ids = []
    for name in sorted(os.listdir(RULES_DIR)):
        if not name.endswith(".json") or name == "manifest.json":
            continue
        raw = read_json(os.path.join(RULES_DIR, name))
        for rule in raw["rules"]:
            rule_ids.append(rule["id"])
            entry = by_id.get(rule["id"])
            assert entry is not None, "依据索引缺规则: {0}".format(rule["id"])
            assert entry["clause_status"] == rule["clause_status"], rule["id"]
            assert entry["param"] == rule["param"], rule["id"]
            if rule["clause_status"] == "verified":
                assert rule["clause"], "{0}: clause_status=verified 但条款号为空".format(rule["id"])
    assert len(rule_ids) == len(by_id), "依据索引条目数与规则包不一致"


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


def test_desensitize_dist_scan_is_clean():
    """构建产物本体扫描：当前 ``dist/`` 必须无 HARD 命中。

    上游固有元数据（CPython/OpenSSL/bzip2 维护者邮箱、Qt 构建机路径、厂商串）
    由 ``tools/dist_allowlist.py`` 精确值豁免并单列；豁免清单**不是**"全部豁免"，
    未登记的 HARD 仍会让命令以退出码 1 结束。
    """
    dist = os.path.join(ROOT, "dist")
    if not os.path.isdir(dist):
        pytest.skip("dist/ 不存在（未构建产物）→ 跳过本体扫描")
    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(TOOLS, "audit_desensitize.py"),
            "--mode",
            "dist",
            "--dist-dir",
            dist,
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, output
    assert "DESSENSITIZE_AUDIT_OK" in output
    assert "[HARD] 0 处" in output


def test_desensitize_dist_scan_has_positive_detection(tmp_path):
    """探活：dist 模式对合成泄露目录必须非 0 退出（防"模式永远绿"）。"""
    leak = tmp_path / "artifact.bin"
    leak.write_bytes(b"\x00\x01 leak " + b"someone" + b"@" + b"example.com \x00")
    proc = subprocess.run(
        [
            sys.executable,
            os.path.join(TOOLS, "audit_desensitize.py"),
            "--mode",
            "dist",
            "--dist-dir",
            str(tmp_path),
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 1, output
    assert "DESSENSITIZE_AUDIT_FAIL" in output


def test_ci_runs_full_desensitize_audit():
    """接线：CI 必须常驻全模式脱敏审计（公开仓库的历史不可撤回风险）。"""
    path = os.path.join(ROOT, ".github", "workflows", "ci.yml")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    assert "audit_desensitize.py --mode all" in text, "CI 未常驻 --mode all 脱敏审计"
    # 浅克隆会让 history 扫描静默空跑 —— 全量历史断言由
    # test_every_checkout_step_uses_full_history 覆盖。这里确认脚本真被调用。
    assert "audit_desensitize.py --selftest" in text, "CI 丢了脱敏 selftest 正负对照"


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


# ---- README/技术报告可运行示例（接线断言） ----


def _readme_paths(text):
    """抽取文档里出现的仓内相对路径（``examples/...``）。

    只认带扩展名的形态，避免把命令名当路径；``$TEMP``/``<目录>`` 等占位符天然不命中。
    """
    import re

    return sorted(set(re.findall(r"examples/[A-Za-z0-9._/-]+\.json", text)))


def test_sample_profile_exists_and_loads():
    """仓内必须有可直接 ``check`` 的示例档案（README 命令的输入）。"""
    from ebikecheck.profile import load_profile

    path = os.path.join(ROOT, "examples", "sample-profile.json")
    assert os.path.isfile(path), "缺少 examples/sample-profile.json"
    profile = load_profile(path)
    assert profile.profile_id, "示例档案缺少 profile_id"
    assert profile.params, "示例档案缺少 params"


def test_sample_profile_is_clean_and_check_exits_zero():
    """示例必须是干净件：README 的示例命令若检出越限，陌生人会以为工具坏了。

    示例档案取自真值库 ``SYN-CASE-001`` 的 ``profile`` 对象（只覆盖 6 个参数），
    因此整体结论是「未提供」而不是「符合」——**未提供不改退出码**，这里断言的是
    「无不符合项 + 退出码 0」，而不是硬编码某个结论标签。
    """
    path = os.path.join(ROOT, "examples", "sample-profile.json")
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC
    proc = subprocess.run(
        [sys.executable, "-m", "ebikecheck", "check", path],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    output = proc.stdout.decode("utf-8", "replace")
    assert proc.returncode == 0, output
    assert "不符合 0" in output, output
    assert "统一结论: 不符合" not in output, output


def test_documented_example_paths_exist():
    """README 与技术报告里出现的 ``examples/*.json`` 必须真实存在（防文档漂移）。"""
    missing = []
    for relative in ("README.md", os.path.join("docs", "技术报告.md")):
        with open(os.path.join(ROOT, relative), "r", encoding="utf-8", newline="") as handle:
            text = handle.read()
        for item in _readme_paths(text):
            if not os.path.isfile(os.path.join(ROOT, item)):
                missing.append("{0} -> {1}".format(relative, item))
    assert not missing, "文档引用了不存在的示例路径: {0}".format(missing)


def test_readme_commands_use_example_profile():
    """README 的 check/diff-profile/export 三条命令必须指向仓内示例档案。"""
    with open(os.path.join(ROOT, "README.md"), "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    for command in ("ebikecheck check", "ebikecheck diff-profile", "ebikecheck export"):
        matching = [line for line in text.splitlines() if line.strip().startswith(command)]
        assert matching, "README 缺少命令: {0}".format(command)
        assert any("examples/sample-profile.json" in line for line in matching), (
            "README 的 {0} 未指向 examples/sample-profile.json: {1}".format(command, matching)
        )


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
    """CI 矩阵必须与 ``requires-python`` 口径一致。

    规格变更（2026-10-19，D-45）：Python 3.8 于 2024-10-07 EOL，floor 抬到 3.12，
    故 3.8 作业被**移除**，此断言随之从"含 3.8"改为"不含 3.8"（不是放宽口径）。
    """
    yaml = pytest.importorskip("yaml")
    path = os.path.join(ROOT, ".github", "workflows", "ci.yml")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        payload = yaml.safe_load(handle.read())
    job = payload["jobs"]["test"]
    matrix = job["strategy"]["matrix"]["include"]
    combos = {(item["os"], str(item["python"])) for item in matrix}
    assert ("windows-latest", "3.12") in combos
    assert ("ubuntu-latest", "3.12") in combos
    assert not any(python.startswith("3.8") for _, python in combos), (
        "CI 仍保留已 EOL 的 3.8 作业: {0}".format(sorted(combos))
    )


def test_runtime_floor_is_declared_consistently():
    """pyproject / README 的运行时下限必须一致（防三处口径漂移）。"""
    import re

    with open(os.path.join(ROOT, "pyproject.toml"), "r", encoding="utf-8", newline="") as handle:
        pyproject = handle.read()
    with open(os.path.join(ROOT, "README.md"), "r", encoding="utf-8", newline="") as handle:
        readme = handle.read()
    match = re.search(r'requires-python\s*=\s*">=(\d+)\.(\d+)"', pyproject)
    assert match, "pyproject 缺少 requires-python"
    floor = "{0}.{1}".format(match.group(1), match.group(2))
    assert floor == "3.12", "本迭代（D-45）口径为 3.12，实际 {0}".format(floor)
    assert "Python {0}+".format(floor) in readme, "README 未标注 Python {0}+".format(floor)
    # 依赖上界也必须落进 pyproject（gui / build extras）。
    assert "PySide6>=6.12,<7" in pyproject.replace(" ", "")
    assert "pyinstaller>=6.22,<7" in pyproject.replace(" ", "")


def test_ci_installs_dev_extra():
    """CI 必须装 dev extra：pytest 本身住在 dev，"core-only 跑测试"会整批 ImportError。"""
    path = os.path.join(ROOT, ".github", "workflows", "ci.yml")
    with open(path, "r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    assert "[dev]" in text
