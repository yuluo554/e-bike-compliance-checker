# HANDOFF-M3 —— M2 收尾 → M3（字段映射与对账）交接

**用法**：新对话开头写 `/goal 读取 "plan/HANDOFF-M3.md" 继续完成任务`
（**入库文件内一律用相对路径**；绝对路径只在你的启动命令里拼，否则每份 HANDOFF 都带本机盘符、发布期脱敏扫描必中）。

**交接生成时间**：2026-10-14（M2 收尾落盘）
**上一棒**：M2 限值矩阵引擎完整 —— ✅ 完成（DoD 5/5，见 [05 §四 M2](05-数据计划与里程碑.md)）
**本棒目标**：M3 字段映射与对账 —— 把"三维判定已完整"推进到"厂家参数表列名能自动映射、整批清单能扫、跨轮整改能对账、结论能带指纹交出去"

---

## 一、当前进度（M2 末态实测）

### 1.1 已建成且可跑的

| 层 | 文件 | 状态 |
|---|---|---|
| 基础 | `io_utils.py`、`paths.py` | ✅ |
| 引擎 | `engine/findings.py`（**四态 + 单维度 `CheckResult` + 三维 `ProfileCheckResult` + `aggregate_overall`**）、`values.py`（单位换算 + **别名归一 `unit_alias_index`/`resolve_unit`** + Decimal）、`rules.py`（schema + 门控 + `applies_if` 三值逻辑）、`matrix.py`（判定序）、`version.py` | ✅ |
| 服务 | `service.py`（`selfcheck` / **`check_profile`（三维装配）** / **`check_profile_obj`/`check_profile_dict`（内存通路）** / `check_profile_all_versions` / `ruleset_overview`） | ✅ |
| 表现 | `cli.py`（`selfcheck` / `check`（**维度分组输出 + 统一结论**） / `rules` / `bench` / `version`） | ✅ |
| 基准 | `benchmark_runner.py`（**六套件** + 门槛读 manifest + 探活）、**`benchmark/probes.py`（规则驱动探针：全运算符端点推导 + 条件构造求解）**、`benchmark/cases.py`（对账语义单一源） | ✅ |
| 数据 | `data/rules/`（4 册 + manifest 冻结）、`data/truth/cases/`（13 例 + index 冻结）、`data/mapping/mapping.json`（14 参数 + **11 类单位别名**）、`data/knowledge/clauses.json` + `raw/` 6 份官方快照 | ✅ |
| 工具 | `tools/gen_rulesets.py`、`gen_synthetic.py`、`gen_mapping.py`、`gen_knowledge.py`、`check_zero_literals.py`、`audit_desensitize.py` | ✅ |
| 测试 | `tests/`（**133 项**，3.8/3.12 双绿；新增 `test_m2_dimensions.py` 15 项 + `test_m2_probes_and_units.py` 24 项） | ✅ |
| CI | `.github/workflows/ci.yml`（windows×{3.8,3.12} + ubuntu×3.12） | ✅ 就位，**未接远端未跑** |

### 1.2 关键实测数字（写文档/报告时直接引用）

```
规则库: 4 册 + manifest；verified=13 / pending=4；条款号 verified=11 / pending=6
  gb17761-2024.json  vehicle  verified=10  pending=0
  gb17761-2018.json  vehicle  verified=2   pending=0
  gb43854-2024.json  battery  verified=0   pending=2   （首期不参数化 → 维度零生效规则）
  gb42296-2022.json  charger  verified=1   pending=2
真值库: 13 例 + index.json（"干净档案"用例参数集改为跨三维全册推导）
映射表: 14 参数 + 11 类单位别名（M2 补 ‰）
依据索引: 逐条挂条款 + 6 份官方快照（逐份 sha256）
基准:   rules 17/17, boundary 26/26, rule_driven 26/26, dimensions 4/4,
        synthetic 12/12, version 1/1；耗时 0.063s（上限 1.0s）
测试:   133 项（py -3.8 与 py -3.12 双绿）
门禁:   零字面量 7 禁用 token 零命中；脱敏审计三模式 HARD=0
CI:     workflow 就位；**未接远端 → 未跑 CI**（不记"CI 绿"）
```

### 1.3 M2 已核到的条款号（**M3 直接引用，勿重复核对**）

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

### 1.4 M2 收尾已做的验证（留档，避免下一棒重复劳动）

| 验证 | 命令 | 结果 |
|---|---|---|
| 确定性冻结（规则包） | `tools/gen_rulesets.py --check` | `RULESETS_FROZEN_OK (5 份)` |
| 确定性冻结（真值库） | `tools/gen_synthetic.py --check` | `SYNTHETIC_FROZEN_OK (13 份)` |
| 确定性冻结（映射表） | `tools/gen_mapping.py --check` | `MAPPING_FROZEN_OK (1 份)` |
| 确定性冻结（依据索引） | `tools/gen_knowledge.py --check` | `KNOWLEDGE_FROZEN_OK (1 份)` |
| 零字面量门禁（探活） | `tools/check_zero_literals.py --selftest` | `ZERO_LITERALS_SELFTEST_OK`（7 个禁用 token） |
| 脱敏审计三模式 | `tools/audit_desensitize.py --mode all` | `DESSENSITIZE_AUDIT_OK`（HARD=0） |
| 六套件探活 | `benchmark_runner.probe_falsifiable(data, s)` 逐个 | **六套件全部 `True`**（注入缺陷即报未达标） |
| 台账 sha256 对账 | 逐条比对 `data/README.md` §一·一 vs 产物实际 | 8/8 `OK`（**映射表 sha256 已随 M2 更新**） |
| 提交元数据邮箱 | `git config user.email` | 仓库级 `yuluo554@users.noreply.github.com`（**勿动全局 `git config user.email`**） |

> **重要**：下一棒若改动源码后重新提交，**务必保持仓库级 `user.email` 为 noreply**（`git config user.email` 查一下）；用 `--amend` 时也要显式带 `GIT_COMMITTER_EMAIL`，否则 committer 会回落全局真实邮箱（M0 实测过的坑）。

---

## 二、下一里程碑待办（M3）

| # | 任务 | 为什么 | 完成判据 |
|---|---|---|---|
| M3-1 | **字段映射引擎**（`engine/mapping.py`） | M1 已把**数据**备好（`data/mapping/mapping.json`：14 参数 + 列名变体 + 歧义列名 + 11 类单位别名），但**引擎还没消费它** —— 现在档案必须写标准参数名 | 厂家参数表的列名（「最高车速」）能映射到标准参数名（`max_design_speed`）；歧义列名（「车速」「电压」）→ `not_provided(mapping_uncertain)`；未登记列名 → `not_provided` |
| M3-2 | **批量扫描 + 失败件隔离** | FR-09：整批几百款车型，单件坏格式不得中断整批 | `scan` 子命令：单件异常单列原因码、**不改变退出码语义**（0/1/2 三语义）；失败件与越限件分列 |
| M3-3 | **跨轮对账三集合** | FR-10：整改是循环的，"这轮比上轮好了没" | 新增越限 / 已整改 / 持续越限三集合；**配对主键 = 稳定身份键**（非内容指纹）；口径单一实现源（测试与基准共用 `benchmark/cases.py::observed_nonpass`） |
| M3-4 | **证据链（双 sha256）** | FR-11：结论要能交出去、能检改动 | 档案 + 报告各挂 sha256；**溯源完整性断言**（明细行数 == 溯源行数，每条引用 id 可解析） |

### M3 特别提醒

- **改规则包必须走生成器**：改 `tools/sources/rules_source.json` → `py -3.12 tools/gen_rulesets.py` → `--check` 确认。**直接手改 `data/rules/*.json` 会被 `tests/test_gates.py::test_rulesets_regenerate_byte_identically` 当场拦下。**
- **改完必须四联动**：规则包重生成 + `manifest.json` sha256 自动更新（生成器做）+ `data/mapping/mapping.json` 若参数集变化须重生成（`gen_mapping --check` 会报覆盖缺口）+ `data/knowledge/clauses.json` 须重生成 + 台账 sha256 同步（手工做）。
- **加数值就过门禁**：新 `verified` 值会自动进零字面量禁用 token 集；若源码/docstring 里写过它（比如注释举例），门禁会拦——**改源码，别放宽门禁**。
- **M2 新增的"维度参与度"别回退**：`CheckResult.participates()` 是既定口径（D-43）—— 零生效规则、或标准未生效的维度**不参与聚合**。M3 批量扫描时若把"该维度无可判项"当成"未评估"混进越限统计，会把干净车型误报成待整改。
- **M3 映射引擎要复用 M2 的别名通路**：`engine/values.py::unit_alias_index` 已把 `unit_aliases` 读进来；映射引擎解析"列名 + 单位"时应走**同一张表**，别另建第二份口径（否则"列名能映射但单位换算不上"）。
- **`data/mapping/mapping.json` 已登记 `ambiguous_variants`**（如「车速」可指最高车速或设计车速）—— 映射引擎遇之必须判 `mapping_uncertain`（FR-08 判据），**绝不猜**。
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
| O-13 | **`not_applicable` 不参与结论聚合**：剔除后再聚合，仅全不适用才 `not_assessed` | D-38（M1） | `boundary` 基准 + `test_observed_states_takes_weakest_conclusion` |
| O-14 | **边界基准按 `applies_if` 引用参数求解满足条件的构造**（不写死规则 id） | D-39（M1） | `boundary`/`rule_driven` 基准 |
| O-15 | **真值"干净档案"参数集随规则包实时推导**（不硬编码） | D-40（M1）/ **M2 扩至跨三维全册** | `gen_synthetic --check` + `synthetic` 基准 |
| O-16 | **条款号核不到一律 `pending` + `clause: null`**；已废止标准官方不提供全文即如实 pending | D-36（M1） | `test_knowledge_covers_every_rule_and_flags_pending_clauses` |
| O-17 | **映射表必须覆盖规则包全部参数**（含 pending）；同一列名变体不得映射到两个参数 | M1-4 | `test_mapping_covers_every_rule_package_param` + `gen_mapping --check` |
| O-18 | **官方标准全文页图不落库**，只登记查看器 URL + 页数 + 逐页 sha256 摘要 | D-41（M1） | `data/knowledge/clauses.json::fulltext_retrieval` |
| **O-19** | **维度参与度决定是否进统一结论**：零生效规则 / 标准未生效 → 不参与聚合 | **D-43（M2 新增）** | `dimensions` 基准 + `test_aggregate_overall_ignores_non_participating_dimensions` |
| **O-20** | **换算系数内置 / 别名表落库**：系数在 `engine/values.py`，别名来自 `data/mapping/mapping.json::unit_aliases` | **D-44（M2 新增）** | `test_unit_alias_table_covers_every_factor_unit` |
| **O-21** | **三维结果固定序** 整车 → 电池 → 充电器（`DIMENSION_ORDER`）；并集视图保持旧取数姿势 | M2 | `test_check_returns_three_dimensions_each_with_own_standard` + 确定性序列化测试 |
| **O-22** | **规则驱动基准不读真值库**：端点全由 `op`/`value`/`unit` 推出，新增规则自动进枚举 | M2-3/M2-4 | `boundary`/`rule_driven`/`dimensions` 三套件 + 探活 |

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
| openstd 全文通道的会话坑 | 同一 cookie 会话连续请求 `viewGbImg` **只有第一个成功**（后续 0 字节） | **每张精灵图新建独立会话**（重走 newGbInfo→showGb→viewGbImg）；详见 [05 §2.6](05-数据计划与里程碑.md) |
| pytest 3.8 偶发 teardown 崩 | 单次运行尾部抛异常栈但 0 失败；重跑即绿 | 重跑确认；非测试缺陷（疑 3.8 上 pytest 8.3.5 的间歇问题） |
| **`check_profile` 返回值类型在 M2 变了** | 由 `CheckResult`（单维度）变为 `ProfileCheckResult`（三维容器）；`.findings`/`.counts()`/`.overall()` 仍是**跨维度并集视图**（旧姿势可用），但 `.ruleset_file`/`.ruleset_sha256` 已下移到 `dimensions[i]` | 取分册坐标走 `result.dimensions`；`test_result_carries_source_blocks` 等旧测试已同步验证并集视图 |
| **基准层喂档案不要落盘** | 用 `service.check_profile_dict(profile_dict, data_dir, version_key)` 走内存通路（与 CLI 同一装配），避免临时文件与 `/tmp` 坑 | `benchmark_runner._check_profile_dict` 已封装 |

---

## 五、M2 DoD 复核（5/5 ✅）

逐项证据见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §四 M2 完成记录表。

**需读者注意的三点**：
1. **三维不是"三册合并"**：电池/充电器是独立标准，各成维度、各挂自身条款号；统一结论由 `aggregate_overall` 聚合（FR-02/FR-04）。
2. **"不参与聚合"有两种，都显式记录理由**：标准未生效（D-43 情形①）、该标准零可判项（情形②）。**"该标准管不到 / 无可判项"必须与"查了没问题"区分开**（02 §5.2 同一纪律的延伸）。
3. **`boundary` 从 18/18 到 26/26 不是"放宽门槛"**：是枚举面**扩大**到全运算符与布尔/无量纲条目（旧版跳过 `==`/`!=`/`in`/`range` 与 `unit=""` 的条目），门槛仍是 `1.0`（manifest 下发）。

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
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck check <档案.json>     # 三维 + 统一结论
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck bench
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck bench --only rule_driven
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck bench --only dimensions

# 六套件探活（每个都必须 True）
PYTHONPATH=src py -3.12 -X utf8 -c "
from ebikecheck import benchmark_runner as br
for s in br.SUITE_NAMES:
    print(s, br.probe_falsifiable('data', s))
"
```

**取档案做 check 的姿势**（真值库文件是带 `expect` 包装的记录，**不能直接喂**）：

```bash
py -3.12 -c "import json;c=json.load(open('data/truth/cases/SYN-CASE-002.json',encoding='utf-8'));json.dump(c['profile'],open('.tmp/p.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)"
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck check .tmp/p.json --data-dir data
```

---

## 七、本棒的已知未决项

| 项 | 状态 |
|---|---|
| 字段映射**引擎**（`engine/mapping.py`） | ⬜ **M3-1 主线**（数据已备好，引擎未建） |
| 批量扫描 / 跨轮对账 / 证据链 | ⬜ **M3-2/M3-3/M3-4**（`service.py` 已预留位） |
| GB 17761—2018 条款号 | ⬜ 官方不提供全文，如实 `pending`（D-36，作为已知边界保留） |
| GB 43854 / GB 42296 首期不参数化条目 | ⬜ `pending` + 理由入 `notes`（D-37，扩展位预留；M2 起该维度"零生效规则不参与聚合"） |
| CI 真实运行 | ⬜ 未接远端；建仓后首推即首次 CI（D-31） |
| 报告导出（MD/XLSX，单一渲染源） | ⬜ M5（M3 只做证据链数据侧） |
| 版本差异对照报告（从两版规则包 diff 生成） | ⬜ M4（`check_profile_all_versions` 已返回三维结果） |

---

## 八、新对话启动提示词

```
/goal 读取 "<仓库绝对路径>\plan\HANDOFF-M3.md" 继续完成任务
```

（入库的本文档内一律用相对路径；绝对路径只由你在启动命令里拼。）
