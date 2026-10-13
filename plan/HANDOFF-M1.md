# HANDOFF-M1 —— M0 收尾 → M1（数据先行）交接

**用法**：新对话开头写 `/goal 读取 "plan/HANDOFF-M1.md" 继续完成任务`
（**入库文件内一律用相对路径**；绝对路径只在你的启动命令里拼，否则每份 HANDOFF 都带本机盘符、发布期脱敏扫描必中）。

**交接生成时间**：2026-10-14（M0 收尾落盘）
**上一棒**：M0 计划定稿 + 可运行骨架 —— ✅ 完成（DoD 18/18，见 [05 §四](05-数据计划与里程碑.md)）
**本棒目标**：M1 数据先行 —— 把规则库从"骨架 + 9 条 verified"推进到"条款号逐条核对 + 三标准可参数化条款完整"

---

## 一、当前进度（M0 末态实测）

### 1.1 已建成且可跑的

| 层 | 文件 | 状态 |
|---|---|---|
| 基础 | `src/ebikecheck/io_utils.py`（UTF-8 守卫 / Decimal JSON / sha256）、`paths.py`（数据目录定位，含冻结分支） | ✅ |
| 引擎 | `engine/findings.py`（四态/原因码/CheckResult）、`values.py`（单位换算 + Decimal 比较）、`rules.py`（schema + 门控 + `applies_if` 三值逻辑）、`matrix.py`（判定序）、`version.py`（版本锚定） | ✅ |
| 服务 | `service.py`（`selfcheck` / `check_profile` / `check_profile_all_versions` / `ruleset_overview`） | ✅ |
| 表现 | `cli.py`（`selfcheck` / `check` / `rules` / `bench` / `version`） | ✅ |
| 基准 | `benchmark_runner.py`（四套件 + 门槛读 manifest + 探活）、`benchmark/cases.py`（对账语义单一源） | ✅ |
| 数据 | `data/rules/`（4 册 + manifest 冻结）、`data/truth/cases/`（12 例 + index 冻结） | ✅ |
| 工具 | `tools/gen_rulesets.py`、`tools/gen_synthetic.py`、`tools/check_zero_literals.py`、`tools/audit_desensitize.py` | ✅ |
| 测试 | `tests/`（87 项，3.8/3.12 双绿） | ✅ |
| CI | `.github/workflows/ci.yml`（windows×{3.8,3.12} + ubuntu×3.12） | ✅ 就位，**未接远端未跑** |

### 1.2 关键实测数字（写文档/报告时直接引用）

```
规则库: 4 册 + manifest；verified=9 / pending=7
  gb17761-2024.json  vehicle  verified=7  pending=3
  gb17761-2018.json  vehicle  verified=2  pending=0
  gb43854-2024.json  battery  verified=0  pending=2
  gb42296-2022.json  charger  verified=0  pending=2
真值库: 12 例 + index.json
基准:   rules 16/16, boundary 10/10, synthetic 12/12, version 1/1；耗时 0.012~0.018s（上限 1.0s）
测试:   87 项（py -3.8 与 py -3.12 双绿）
门禁:   零字面量 4 禁用 token 零命中；脱敏审计三模式全清（tracked/history/messages HARD=0）
CI:     workflow 就位；**未接远端 → 未跑 CI**（不记"CI 绿"）
```

### 1.3 M0 收尾已做的验证（留档，避免下一棒重复劳动）

| 验证 | 命令 | 结果 |
|---|---|---|
| 确定性冻结（规则包） | `tools/gen_rulesets.py --check` | `RULESETS_FROZEN_OK (5 份)` |
| 确定性冻结（真值库） | `tools/gen_synthetic.py --check` | `SYNTHETIC_FROZEN_OK (13 份)` |
| 手改会被拦（探活） | 手改 `data/rules/gb17761-2024.json` 里一个值 → `--check` | exit 1（守门有效） |
| 零字面量门禁（探活） | 向 `engine/matrix.py` 注入 `63` → 门禁 | exit 1 并定位到 `matrix.py:46`（有效；注入后已还原） |
| 脱敏审计三模式 | `tools/audit_desensitize.py --mode all` | `DESSENSITIZE_AUDIT_OK`（HARD=0；advisory=4，均为 manifest 的 sha256，属文档化功能） |
| 提交元数据邮箱 | `git log --format="%ae %ce" --all` | 全历史仅 `yuluo554@users.noreply.github.com`（**用户级 `git config user.email` 是真实邮箱，已在仓库级改为 noreply，全局未动**） |
| 干净环境验证 | `git archive HEAD` 导出树 + 树外全新 venv + `pip install -e ".[dev]"` | 87 收集数 = dev 87；`selfcheck`/`bench`/两个 `--check` 全过；导出树无 `.git` 时审计**文件系统兜底**生效（advisory=4 证明扫描非空）|

> **重要**：下一棒若改动源码后重新提交，**务必保持仓库级 `user.email` 为 noreply**（`git config user.email` 查一下）；用 `--amend` 时也要显式带 `GIT_COMMITTER_EMAIL`，否则 committer 会回落全局真实邮箱（M0 实测过的坑）。

---

## 二、下一里程碑待办（M1）

| # | 任务 | 为什么 | 完成判据 |
|---|---|---|---|
| M1-1 | **以正式标准文本逐条补 `clause` 并置 `clause_status=verified`** | 首版条款号**全部 `pending`**：两个可直连来源（openstd 元数据 + gov.cn 问答）**都不含条款号**，openstd 全文页是 JS 增强、取不到可解析载荷。**绝不编造条款号**是本项目的硬纪律 | `data/rules/*.json` 中 `clause` 非空且 `clause_status=verified` 的条目数上升；报告不再打印"条款号待核对" |
| M1-2 | 补齐 GB 17761—2024 剩余可参数化条款 | 现 3 条 pending：`vehicle_mass-other`（非铅蓄电池质量限值）、`nominal_voltage`、`motor_rated_power`；后两项问答明确未列明 | 三条转 verified（有原文）或确认保持 pending 并写明理由 |
| M1-3 | GB 43854—2024 / GB 42296—2022 可参数化条款入库 | 现各 2 条 pending、`value: null` | 各册 verified 条目 ≥ 1，或确认首期不参数化（写进 `notes` + 决策记录） |
| M1-4 | `data/mapping/` 字段映射表 + 列名变体 | FR-08 的前置；M3 要用 | `data/mapping/` 生成器产出，覆盖全部标准参数 |
| M1-5 | `data/knowledge/clauses.json` 依据索引 + 官方快照 + sha256 台账 | 报告 §3 参数来源块的数据源 | 每条限值挂发布机关/标准号/条款（或待核对标注）/URL/抓取日期 |
| M1-6 | 数据台账登记 M1 产物 sha256 | `data/README.md` 台账纪律 | 台账与产物实际 sha256 一致 |
| M1-7 | CCC 实施公告（`P-02`）经官方渠道核对 | 缓议项 | 核到 → 写入依据索引；核不到 → 保持"待核对"并记录已查渠道 |

### M1 特别提醒

- **改规则包必须走生成器**：改 `tools/sources/rules_source.json` → `py -3.12 tools/gen_rulesets.py` → `--check` 确认。**直接手改 `data/rules/*.json` 会被 `tests/test_gates.py::test_rulesets_regenerate_byte_identically` 当场拦下。**
- **改完必须三联动**：产物重生成 + `manifest.json` 里的 sha256 自动更新（生成器做）+ 台账 sha256 同步（手工做）。
- **加数值就过门禁**：新 `verified` 值会自动进零字面量禁用 token 集；若源码/docstring 里写过它（比如注释举例），门禁会拦——**改源码，别放宽门禁**。
- **真值库可能需重生成**：`tools/gen_synthetic.py` 的用例从规则包**实时推导**限值（不硬编码），所以补完规则后 `--check` 大概率报漂移 → 重生成即可，但要**确认期望结论仍正确**（尤其新补的 `vehicle_mass-other` 会改变"非铅蓄电池车型"的期望集合）。
- **schema 门会拦不一致的登记**：`status=pending` 配非 null `value`、或 `clause_status=pending` 配非空 `clause`，都会在加载时抛 `RulesetError`（M0 实测拦过两次）。

---

## 三、既定口径清单（**动了会打挂基准与测试**）

| # | 口径 | 决策 | 联动测试 |
|---|---|---|---|
| O-1 | **双门控拆分**：`status` 管数值、`clause_status` 管条款号，**不耦合** | D-04/D-05 | `test_engine.py` schema 组 + `rules` 基准 |
| O-2 | 版本锚定主键 `model_design_date`（次键 `market_date`）；无日期 → 报错要求 `--version-of`，**不猜** | D-06 | `test_version_anchor_*` |
| O-3 | 锚定窗口：`< 2025-09-01` → 2018 版；`>= 2025-09-01` → 2024 版；**一次核查只用一个版本** | D-07/D-08 | `version` 基准 + `test_same_profile_different_verdict_across_versions` |
| O-4 | 数值一律字符串承载 + 全链路 `Decimal`，**禁用 float** | D-11 | `test_boundary_over_limit_is_non_compliant_using_decimal` |
| O-5 | 退出码 0/1/2；**`not_provided` 与失败件不改退出码** | D-16 | `test_not_provided_does_not_change_exit_code` |
| O-6 | 数据目录优先级：显式 > 环境变量 > 冻结态 > 源码态；**显式给了但不含 manifest → 直接失败，不回落** | D-19 | `test_explicit_data_dir_is_authoritative` |
| O-7 | 生成器禁 `random`/`set` 迭代序/系统时钟；产物 `\n` 行尾、无时间戳；`--check` 逐字节一致 | D-21 | `test_gates.py` 确定性组 |
| O-8 | 门槛**只从 manifest 读**（数据非代码），缺失 → exit 2 | FR-13 | `bench` 测试 |
| O-9 | 所有会打印的入口（CLI + 每个 `tools/` 脚本）都要带 `_ensure_utf8_stdio()` | D-26 | `test_all_printing_tools_have_utf8_stdio_guard`（**新增 tools 脚本必被这条拦**） |
| O-10 | 每个 checkout step 必须 `fetch-depth: 0` | D-25 | `test_every_checkout_step_uses_full_history` |
| O-11 | 引擎层零第三方依赖 | NFR-02 | `test_engine_layer_imports_no_third_party` |
| O-12 | 真值对账语义**单一实现源** = `benchmark/cases.py`；**不许改真值凑引擎** | — | `synthetic`/`version` 基准共用它 |

---

## 四、本机环境坑（**只写实测过的**）

| 坑 | 实测现象 | 处置 |
|---|---|---|
| `python` 是商店占位符 | `python --version` 无输出、exit 49 | 一律用 `py -3.12` / `py -3.8` |
| 本机有两条 Python 通道 | `py -0p` → **3.8.8-64 与 3.12.10-64** | 双跑验兼容；3.12 装了 pytest 9.1.1 / 3.8 装 pytest 8.3.5 |
| Git Bash 的 `/tmp` 与 Windows Python 不通 | `py -3.12 -m ebikecheck check /tmp/x.json` 报"档案文件不存在"——MSYS 的 `/tmp` 被解析到用户的**临时目录**，不是仓库内路径 | 临时文件用**工作区相对路径**（如 `.tmp/`），别用 `/tmp` |
| 中文控制台编码 | 需 `-X utf8` | 命令行统一 `py -3.12 -X utf8 ...`；但**代码里的守卫仍必需**（CI 管道是 cp1252，`-X utf8` 掩盖不了） |
| 3.8 无 `sys.stdlib_module_names` | 用它判"第三方依赖"会让**每个** import 都成疑似第三方 | `test_gates.py` 已回落 `sysconfig` 枚举 + `builtin_module_names` |
| `Path.write_text` 在 3.8 无 `newline` 参数 | — | 统一用 `open(..., newline="\n")` 或 `write_bytes`（`io_utils.py` 已封装） |
| PySide6 只在 3.12 可用 | `py -3.8 -c "import PySide6"` 失败；3.12 成功 | M5 GUI 开发走 3.12；首期核心功能零依赖不受影响 |

---

## 五、M0 DoD 复核（18/18 ✅）

逐项证据见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §四 M0 DoD 表。
**唯一需读者注意的偏差说明**：M0-16 的 CI 项只记"**workflow 就位 + 本地等价校验通过**"——
**本地无远端、未推送 = 未跑过 CI**，如实不记"CI 绿"（这是项目纪律，不是遗漏）。

---

## 六、关键命令速查

```bash
cd <仓库根>

# 测试（双版本）
py -3.8  -m pytest -q
py -3.12 -m pytest -q

# 规则包：改 tools/sources/rules_source.json 后必须重生成
py -3.12 -X utf8 tools/gen_rulesets.py
py -3.12 -X utf8 tools/gen_rulesets.py --check    # 期望 RULESETS_FROZEN_OK (5 份)

# 合成真值库（规则变更后通常需重生成）
py -3.12 -X utf8 tools/gen_synthetic.py
py -3.12 -X utf8 tools/gen_synthetic.py --check   # 期望 SYNTHETIC_FROZEN_OK (13 份)

# 门禁
py -3.12 -X utf8 tools/check_zero_literals.py            # 期望 ZERO_LITERALS_OK
py -3.12 -X utf8 tools/check_zero_literals.py --selftest
py -3.12 -X utf8 tools/audit_desensitize.py --selftest
py -3.12 -X utf8 tools/check_zero_literals.py --list-tokens   # 看当前禁用 token 集

# CLI（需 PYTHONPATH=src，或 pip install -e . 后用 ebikecheck）
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck selfcheck
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck rules
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck check <档案.json>
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck bench
```

**取档案做 check 的姿势**（真值库文件是带 `expect` 包装的记录，**不能直接喂**）：

```bash
py -3.12 -c "import json;c=json.load(open('data/truth/cases/SYN-CASE-002.json',encoding='utf-8'));json.dump(c['profile'],open('.tmp/p.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)"
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck check .tmp/p.json
```

---

## 七、本棒的已知未决项

| 项 | 状态 |
|---|---|
| 规则条款号 | ⬜ **全部 pending**（M1-1 是下一棒主线）|
| GB 43854/42296 可参数化条款 | ⬜ 各 2 条 pending、`value: null` |
| CCC 实施公告号/日期 | ⬜ 待核对（缓议 P-02）|
| 字段映射表 | ⬜ M1-4 |
| 依据索引 + 快照 | ⬜ M1-5 |
| CI 真实运行 | ⬜ 未接远端；建仓后首推即首次 CI（见决策 D-31：倾向 M0 后即建私有仓）|
| 真实标准全文载荷 | ⬜ openstd 全文页为 JS 增强，未取得可直连可解析载荷 |

---

## 八、新对话启动提示词

```
/goal 读取 "<仓库绝对路径>\plan\HANDOFF-M1.md" 继续完成任务
```

（入库的本文档内一律用相对路径；绝对路径只由你在启动命令里拼。）
