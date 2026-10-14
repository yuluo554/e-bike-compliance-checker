# HANDOFF-M2 —— M1 收尾 → M2（限值矩阵引擎完整）交接

**用法**：新对话开头写 `/goal 读取 "plan/HANDOFF-M2.md" 继续完成任务`
（**入库文件内一律用相对路径**；绝对路径只在你的启动命令里拼，否则每份 HANDOFF 都带本机盘符、发布期脱敏扫描必中）。

**交接生成时间**：2026-10-14（M1 收尾落盘）
**上一棒**：M1 数据先行 —— ✅ 完成（DoD 7/7，见 [05 §四](05-数据计划与里程碑.md)）
**本棒目标**：M2 限值矩阵引擎完整 —— 把"骨架已通"推进到"三维（整车/电池/充电器）判定完整、跨标准统一结论、边界枚举与规则驱动基准达标 100%"

---

## 一、当前进度（M1 末态实测）

### 1.1 已建成且可跑的

| 层 | 文件 | 状态 |
|---|---|---|
| 基础 | `src/ebikecheck/io_utils.py`、`paths.py` | ✅ |
| 引擎 | `engine/findings.py`（四态/原因码/CheckResult）、`values.py`（单位换算 + Decimal）、`rules.py`（schema + 门控 + `applies_if` 三值逻辑）、`matrix.py`（判定序）、`version.py`（版本锚定） | ✅ |
| 服务 | `service.py`（`selfcheck` / `check_profile` / `check_profile_all_versions` / `ruleset_overview`） | ✅ |
| 表现 | `cli.py`（`selfcheck` / `check` / `rules` / `bench` / `version`） | ✅ |
| 基准 | `benchmark_runner.py`（四套件 + 门槛读 manifest + 探活）、`benchmark/cases.py`（对账语义单一源） | ✅ |
| 数据 | `data/rules/`（4 册 + manifest 冻结）、`data/truth/cases/`（13 例 + index 冻结）、**`data/mapping/mapping.json`（14 参数 + 10 类单位别名）**、**`data/knowledge/clauses.json` + `raw/` 6 份官方快照** | ✅ |
| 工具 | `tools/gen_rulesets.py`、`tools/gen_synthetic.py`、**`tools/gen_mapping.py`（M1 新增）**、**`tools/gen_knowledge.py`（M1 新增）**、`tools/check_zero_literals.py`、`tools/audit_desensitize.py` | ✅ |
| 测试 | `tests/`（**94 项**，3.8/3.12 双绿） | ✅ |
| CI | `.github/workflows/ci.yml`（windows×{3.8,3.12} + ubuntu×3.12） | ✅ 就位，**未接远端未跑** |

### 1.2 关键实测数字（写文档/报告时直接引用）

```
规则库: 4 册 + manifest；verified=13 / pending=4；条款号 verified=11 / pending=6
  gb17761-2024.json  vehicle  verified=10  pending=0   （条款号全核到）
  gb17761-2018.json  vehicle  verified=2   pending=0   （条款号 2 条 pending：已废止无全文）
  gb43854-2024.json  battery  verified=0   pending=2   （首期不参数化）
  gb42296-2022.json  charger  verified=1   pending=2   （5.5.4 已核；其余不参数化）
真值库: 13 例 + index.json
映射表: 14 参数 + 10 类单位别名（覆盖规则包全部参数）
依据索引: 逐条挂条款 + 6 份官方快照（逐份 sha256）
基准:   rules 17/17, boundary 18/18, synthetic 12/12, version 1/1；耗时 0.015s（上限 1.0s）
测试:   94 项（py -3.8 与 py -3.12 双绿）
门禁:   零字面量 7 禁用 token 零命中；脱敏审计三模式 HARD=0
CI:     workflow 就位；**未接远端 → 未跑 CI**（不记"CI 绿"）
```

### 1.3 M1 已核到的条款号（**M2 直接引用，勿重复核对**）

| 参数 | 标准 | 条款 | 限值 |
|---|---|---|---|
| `max_design_speed` | GB 17761—2024 | **6.1.1.1** | ≤ 25 km/h |
| `over_speed_power_cutoff` | GB 17761—2024 | **6.1.1.1** | == true |
| `vehicle_mass`（铅蓄电池） | GB 17761—2024 | **6.1.3** | ≤ 63 kg |
| `vehicle_mass`（其他类型） | GB 17761—2024 | **6.1.3** | ≤ 55 kg |
| `plastic_mass_ratio` | GB 17761—2024 | **6.5.1** | ≤ 5.5 % |
| `nominal_voltage` | GB 17761—2024 | **6.3.5** | ≤ 48 V |
| `motor_rated_power` | GB 17761—2024 | **6.3.3.1** | ≤ 400 W |
| `anti_tamper_battery_pack` | GB 17761—2024 | **6.8.1.1** | == true |
| `anti_tamper_controller` | GB 17761—2024 | **6.8.2.1** | == true |
| `anti_tamper_speed_limiter` | GB 17761—2024 | **6.8.3** | == true |
| `charger_no_load_output_voltage` | GB 42296—2022 | **5.5.4** | ≤ 42.4 V |

### 1.4 M1 收尾已做的验证（留档，避免下一棒重复劳动）

| 验证 | 命令 | 结果 |
|---|---|---|
| 确定性冻结（规则包） | `tools/gen_rulesets.py --check` | `RULESETS_FROZEN_OK (5 份)` |
| 确定性冻结（真值库） | `tools/gen_synthetic.py --check` | `SYNTHETIC_FROZEN_OK (13 份)` |
| 确定性冻结（映射表） | `tools/gen_mapping.py --check` | `MAPPING_FROZEN_OK (1 份)` |
| 确定性冻结（依据索引） | `tools/gen_knowledge.py --check` | `KNOWLEDGE_FROZEN_OK (1 份)` |
| 零字面量门禁（探活） | `tools/check_zero_literals.py --selftest` | `ZERO_LITERALS_SELFTEST_OK`（**7 个禁用 token**） |
| 脱敏审计三模式 | `tools/audit_desensitize.py --mode all` | `DESSENSITIZE_AUDIT_OK`（HARD=0；advisory=8，均为 manifest/快照 sha256，属文档化功能） |
| 台账 sha256 对账 | 逐条比对 `data/README.md` §一·一 vs 产物实际 | 8/8 `OK` |
| 快照 sha256 对账 | `test_knowledge_snapshot_sha256_matches_files` | 6 份官方快照全部一致 |
| 提交元数据邮箱 | `git log --format="%ae %ce" --all` | 仓库级 `yuluo554@users.noreply.github.com`（**勿动全局 `git config user.email`**） |

> **重要**：下一棒若改动源码后重新提交，**务必保持仓库级 `user.email` 为 noreply**（`git config user.email` 查一下）；用 `--amend` 时也要显式带 `GIT_COMMITTER_EMAIL`，否则 committer 会回落全局真实邮箱（M0 实测过的坑）。

---

## 二、下一里程碑待办（M2）

| # | 任务 | 为什么 | 完成判据 |
|---|---|---|---|
| M2-1 | **三维判定完整**（整车/电池/充电器） | 现 `check` 只按单车版册判定（`GB17761-*`）；电池册（`GB43854-2024`）与充电器册（`GB42296-2022`）**尚未接入单车型核查路径** —— `check_profile` 按 `version_key` 只加载一个分册 | 一份档案能同时得到整车 + 电池 + 充电器三维结论；报告"跨标准统一结论"一节有数据 |
| M2-2 | 跨标准统一结论 | FR-02：电池/充电器是**独立标准**，不能混进整车册；但结论要能合并成"这款车型整体" | `overall` 的聚合跨三维仍守"不符合 > 未提供 > 未评估 > 符合"序；一条不适用不覆盖另一条结论（**M1 已修 D-38，勿回退**） |
| M2-3 | 边界枚举基准完整 | 现 `boundary` 从规则包推导端点（规则驱动），已 18/18；M2 要**枚举全部可参数化限值**（含新增的 V/W/布尔条目） | `bench --only boundary` 100%；新增规则自动进枚举（**不许写死规则 id**） |
| M2-4 | 规则驱动层基准（不读真值库） | 现 `synthetic` 读真值库；M2 要补"只从规则表推导端点"的独立层 | 新增套件或扩 `boundary`，探活可证伪 |
| M2-5 | 单位换算表落库 | M0 内置最小表（`engine/values.py`）；M1 已在 `data/mapping/mapping.json` 登记 `unit_aliases` —— **但 `engine/values.py::UNIT_FACTORS` 仍是代码内表**，两者未打通 | 决策：换算表继续内置（零依赖）还是迁 `data/mapping/units.json`；若迁移须同步门禁与测试 |

### M2 特别提醒

- **改规则包必须走生成器**：改 `tools/sources/rules_source.json` → `py -3.12 tools/gen_rulesets.py` → `--check` 确认。**直接手改 `data/rules/*.json` 会被 `tests/test_gates.py::test_rulesets_regenerate_byte_identically` 当场拦下。**
- **改完必须四联动**（M1 起新增两项）：规则包重生成 + `manifest.json` sha256 自动更新（生成器做）+ **`data/mapping/mapping.json` 若参数集变化须重生成**（`gen_mapping --check` 会报覆盖缺口）+ **`data/knowledge/clauses.json` 须重生成**（条款状态与规则包对账）+ 台账 sha256 同步（手工做）。
- **加数值就过门禁**：新 `verified` 值会自动进零字面量禁用 token 集；若源码/docstring 里写过它（比如注释举例），门禁会拦——**改源码，别放宽门禁**。
- **真值库可能需重生成**：`gen_synthetic.py` 的用例从规则包**实时推导**限值（不硬编码）；"干净档案"用例的**全参数合规取值也是实时推导**（M1 新增 `_fill_compliant`）→ 补完规则后 `--check` 大概率报漂移 → 重生成即可，但要**确认期望结论仍正确**。
- **schema 门会拦不一致的登记**：`status=pending` 配非 null `value`、`clause_status=pending` 配非空 `clause`、`clause_status=verified` 配空 `clause`，都会在加载时抛 `RulesetError`。
- **新增 tools 脚本必须带 `_ensure_utf8_stdio()`**：`test_all_printing_tools_have_utf8_stdio_guard` 会扫 `tools/` 全部 `.py`（含新增）。

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
| O-7 | 生成器禁 `random`/`set` 迭代序/系统时钟；产物 `\n` 行尾、无时间戳；`--check` 逐字节一致 | D-21 | `test_gates.py` 确定性组（**4 个生成器**） |
| O-8 | 门槛**只从 manifest 读**（数据非代码），缺失 → exit 2 | FR-13 | `bench` 测试 |
| O-9 | 所有会打印的入口（CLI + 每个 `tools/` 脚本）都要带 `_ensure_utf8_stdio()` | D-26 | `test_all_printing_tools_have_utf8_stdio_guard` |
| O-10 | 每个 checkout step 必须 `fetch-depth: 0` | D-25 | `test_every_checkout_step_uses_full_history` |
| O-11 | 引擎层零第三方依赖 | NFR-02 | `test_engine_layer_imports_no_third_party` |
| O-12 | 真值对账语义**单一实现源** = `benchmark/cases.py`；**不许改真值凑引擎** | — | `synthetic`/`version` 基准共用它 |
| **O-13** | **`not_applicable` 不参与结论聚合**：剔除后再聚合，仅全不适用才 `not_assessed` | **D-38（M1 新增）** | `boundary` 基准 + `test_observed_states_takes_weakest_conclusion` |
| **O-14** | **边界基准按 `applies_if` 引用参数求解满足条件的构造**（不写死规则 id） | **D-39（M1 新增）** | `boundary` 基准套件 |
| **O-15** | **真值"干净档案"参数集随规则包实时推导**（不硬编码） | **D-40（M1 新增）** | `gen_synthetic --check` + `synthetic` 基准 |
| **O-16** | **条款号核不到一律 `pending` + `clause: null`**；已废止标准官方不提供全文即如实 pending | **D-36（M1 新增）** | `test_knowledge_covers_every_rule_and_flags_pending_clauses` |
| **O-17** | **映射表必须覆盖规则包全部参数**（含 pending）；同一列名变体不得映射到两个参数 | **M1-4** | `test_mapping_covers_every_rule_package_param` + `gen_mapping --check` |
| **O-18** | **官方标准全文页图不落库**，只登记查看器 URL + 页数 + 逐页 sha256 摘要 | **D-41（M1 新增）** | `data/knowledge/clauses.json::fulltext_retrieval` |

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
| **openstd 全文通道的会话坑（M1 新增）** | 同一 cookie 会话连续请求 `viewGbImg` **只有第一个成功**（后续 0 字节） | **每张精灵图新建独立会话**（重走 newGbInfo→showGb→viewGbImg）；详见 [05 §2.6](05-数据计划与里程碑.md) |
| **pytest 3.8 偶发 teardown 崩（M1 观测一次）** | 单次运行尾部抛异常栈但 0 失败；重跑即绿 | 重跑确认；非测试缺陷（疑 3.8 上 pytest 8.3.5 的间歇问题），若复现频繁再深挖 |

---

## 五、M1 DoD 复核（7/7 ✅）

逐项证据见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §四 M1 DoD 表。

**需读者注意的两点**：
1. **M1-7（CCC 公告）已闭环**：核到市场监管总局公告 **2024年第26号**（成文 2024-06-25；2024-10-15 受理、2025-11-01 强制）。
2. **GB 17761—2018 条款号保持 `pending` 是如实登记、不是遗漏**：官方明示"废止标准不提供标准文本阅读服务"，无全文可逐条核对；2024 版前言虽给出条款对应关系，但不足以替代正文核对（D-36）。

---

## 六、关键命令速查

```bash
cd <仓库根>

# 测试（双版本）
py -3.8  -m pytest -q
py -3.12 -m pytest -q

# 四个生成器（改 source 后必须重生成；全部有 --check 守门）
py -3.12 -X utf8 tools/gen_rulesets.py    && py -3.12 -X utf8 tools/gen_rulesets.py --check   # RULESETS_FROZEN_OK (5 份)
py -3.12 -X utf8 tools/gen_synthetic.py   && py -3.12 -X utf8 tools/gen_synthetic.py --check  # SYNTHETIC_FROZEN_OK (13 份)
py -3.12 -X utf8 tools/gen_mapping.py     && py -3.12 -X utf8 tools/gen_mapping.py --check    # MAPPING_FROZEN_OK (1 份)
py -3.12 -X utf8 tools/gen_knowledge.py   && py -3.12 -X utf8 tools/gen_knowledge.py --check  # KNOWLEDGE_FROZEN_OK (1 份)

# 门禁
py -3.12 -X utf8 tools/check_zero_literals.py            # 期望 ZERO_LITERALS_OK（7 token）
py -3.12 -X utf8 tools/check_zero_literals.py --selftest
py -3.12 -X utf8 tools/check_zero_literals.py --list-tokens
py -3.12 -X utf8 tools/audit_desensitize.py --mode all  # 期望 DESSENSITIZE_AUDIT_OK（HARD=0）
py -3.12 -X utf8 tools/audit_desensitize.py --selftest

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
| 电池/充电器分册未接入单车型核查路径 | ⬜ **M2-1 主线**（现 `check` 只按单车版册判定） |
| GB 17761—2018 条款号 | ⬜ 官方不提供全文，如实 `pending`（D-36，作为已知边界保留） |
| GB 43854 / GB 42296 首期不参数化条目 | ⬜ `pending` + 理由入 `notes`（D-37，扩展位预留） |
| 单位换算表落库口径（内置 vs `data/mapping/units.json`） | ⬜ **M2-5** 待定夺 |
| CI 真实运行 | ⬜ 未接远端；建仓后首推即首次 CI（D-31：倾向 M0 后即建私有仓） |
| 字段映射**引擎**（`engine/mapping.py`） | ⬜ M3（M1 已把**数据**备好：`data/mapping/mapping.json`） |

---

## 八、新对话启动提示词

```
/goal 读取 "<仓库绝对路径>\plan\HANDOFF-M2.md" 继续完成任务
```

（入库的本文档内一律用相对路径；绝对路径只由你在启动命令里拼。）
