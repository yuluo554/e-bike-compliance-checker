# HANDOFF-M4 —— M3 收尾 → M4（基准完整与版本对照）交接

**用法**：新对话开头写 `/goal 读取 "plan/HANDOFF-M4.md" 继续完成任务`
（**入库文件内一律用相对路径**；绝对路径只在你的启动命令里拼，否则每份 HANDOFF 都带本机盘符、发布期脱敏扫描必中）。

**交接生成时间**：2026-10-14（M3 收尾落盘）
**上一棒**：M3 字段映射与对账 —— ✅ 完成（DoD 3/3，见 [05 §四 M3](05-数据计划与里程碑.md)）
**本棒目标**：M4 基准完整 —— 把"八套件全绿"推进到"指标进 README、版本差异对照报告从两版规则包 diff 生成"

---

## 一、当前进度（M3 末态实测）

### 1.1 已建成且可跑的

| 层 | 文件 | 状态 |
|---|---|---|
| 基础 | `io_utils.py`、`paths.py` | ✅ |
| 引擎 | `engine/findings.py`（四态 + 三维 + 聚合）、`values.py`（单位换算 + 别名归一）、`rules.py`、`matrix.py`（判定序 + **映射不确定短路**）、`version.py`、**`mapping.py`（M3 新增：列名映射）**、**`reconcile.py`（M3 新增：三集合对账）** | ✅ |
| 服务 | `service.py`（`selfcheck` / `check_profile*` 三通路 / `ruleset_overview` / **`scan_dir`（M3）** / **`compare_rounds`（M3）** / **`assert_traceability` + `evidence_chain`（M3）**） | ✅ |
| 表现 | `cli.py`（`selfcheck` / `check` / `rules` / **`scan`（M3）** / **`compare`（M3）** / `bench` / `version`） | ✅ |
| 基准 | `benchmark_runner.py`（**八套件** + 门槛读 manifest + 探活）、`benchmark/probes.py`、`benchmark/cases.py`（对账语义单一源，M3 起 `observed_nonpass` 同时是对账口径源） | ✅ |
| 数据 | `data/rules/`（4 册 + manifest 冻结）、`data/truth/cases/`（13 例 + index 冻结）、`data/mapping/mapping.json`（14 参数 + 11 类单位别名）、`data/knowledge/clauses.json` + `raw/` 6 份官方快照 | ✅ |
| 工具 | `tools/gen_rulesets.py`、`gen_synthetic.py`、`gen_mapping.py`、`gen_knowledge.py`、`check_zero_literals.py`、`audit_desensitize.py` | ✅ |
| 测试 | `tests/`（**162 项**，3.8/3.12 双绿；M3 新增 `test_m3_mapping_scan_reconcile.py` 28 项） | ✅ |
| CI | `.github/workflows/ci.yml`（windows×{3.8,3.12} + ubuntu×3.12） | ✅ 就位，**未接远端未跑** |

### 1.2 关键实测数字（写文档/报告时直接引用）

```
规则库: 4 册 + manifest；verified=13 / pending=4；条款号 verified=11 / pending=6
  gb17761-2024.json  vehicle  verified=10  pending=0
  gb17761-2018.json  vehicle  verified=2   pending=0
  gb43854-2024.json  battery  verified=0   pending=2   （首期不参数化 → 维度零生效规则）
  gb42296-2022.json  charger  verified=1   pending=2
真值库: 13 例 + index.json
映射表: 14 参数 + 11 类单位别名
依据索引: 逐条挂条款 + 6 份官方快照（逐份 sha256）
基准:   rules 17/17, boundary 26/26, rule_driven 26/26, dimensions 4/4,
        synthetic 12/12, version 1/1, mapping 84/84（门槛 0.98）, reconcile 3/3（门槛 1.0）；
        耗时 0.07s（上限 1.0s）；**八套件探活全部 True**
测试:   162 项（py -3.8 与 py -3.12 双绿）
门禁:   零字面量 7 禁用 token 零命中；脱敏审计三模式 HARD=0
CI:     workflow 就位；**未接远端 → 未跑 CI**（不记"CI 绿"）
```

### 1.3 M3 新口径（**动了会打挂 M3 测试**）

| # | 口径 | 决策 | 联动测试 |
|---|---|---|---|
| N-1 | **歧义列名绝不猜**：`ambiguous_variants` 命中 → 对全部候选参数注入 `{"value": null, "reason": "mapping_uncertain"}`，判定序短路出 `not_provided(mapping_uncertain)` | FR-08 | `test_ambiguous_column_yields_mapping_uncertain_finding` |
| N-2 | **未登记列名直接丢弃**（不走第二套原因码）：判定层自然落 `not_provided(missing)`，与参数缺失同一结论路径 | M3 实现 | `test_normalize_params_maps_and_drops_unmapped` |
| N-3 | **映射表文件缺失显式报错**（`MappingError`）——映射是功能前提，不像单位别名可退化为按原样比对 | M3 实现 | `test_mapping_missing_table_raises` |
| N-4 | **params 条目允许标量**（列名映射通路的输入形状）；数组等其余类型仍拒 | M3 登记 | `test_profile_accepts_scalar_param_for_mapping_channel` + 收窄后的 `test_profile_rejects_non_object_param` |
| N-5 | **本轮缺失件不得计入已整改**：三集合配对只在两轮都出现的 `profile_id` 间进行；仅本轮出现的档案 → 新增越限 | FR-10 | `test_reconcile_missing_profile_is_not_resolved` + `reconcile` 套件场景三 |
| N-6 | **对账口径单一实现源** = `benchmark.cases.observed_nonpass`（`non_compliant` ∪ `not_provided`），三集合只消费它 | O-12 落点 | `test_reconcile_uses_single_source_semantics` |
| N-7 | **溯源断言失败即拒交出**：`TraceabilityError` 不降级为警告；断言内容 = 每条 finding 按 `(param, standard)` 必有来源块 + 档案指纹在位 | FR-11/NFR-10 | `test_traceability_rejects_*` 两项 |
| N-8 | **报告指纹 = 结果载荷规范 JSON 的 sha256**（`sort_keys` + 紧凑分隔符）；档案另挂文件级 + 内容级双指纹 | M3 实现 | `test_report_sha256_detects_tampering` |

### 1.4 M3 收尾已做的验证（留档，避免下一棒重复劳动）

| 验证 | 命令 | 结果 |
|---|---|---|
| 确定性冻结（规则包） | `tools/gen_rulesets.py --check` | `RULESETS_FROZEN_OK (5 份)` |
| 确定性冻结（真值库） | `tools/gen_synthetic.py --check` | `SYNTHETIC_FROZEN_OK (13 份)` |
| 确定性冻结（映射表） | `tools/gen_mapping.py --check` | `MAPPING_FROZEN_OK (1 份)` |
| 确定性冻结（依据索引） | `tools/gen_knowledge.py --check` | `KNOWLEDGE_FROZEN_OK (1 份)` |
| 零字面量门禁 | `tools/check_zero_literals.py` | `ZERO_LITERALS_OK`（7 token） |
| 脱敏审计三模式 | `tools/audit_desensitize.py --mode all` | `DESSENSITIZE_AUDIT_OK`（HARD=0） |
| 八套件探活 | `benchmark_runner.probe_falsifiable('data', s)` 逐个 | **八套件全部 `True`** |
| 双版本回归 | `py -3.8/-3.12 -m pytest` | **162/162 双绿** |

> **重要**：若改动源码后重新提交，**务必保持仓库级 `user.email` 为 noreply**（`git config user.email` 查一下）；用 `--amend` 时也要显式带 `GIT_COMMITTER_EMAIL`，否则 committer 会回落全局真实邮箱。

---

## 二、下一里程碑待办（M4）

| # | 任务 | 为什么 | 完成判据 |
|---|---|---|---|
| M4-1 | **README 评测表** | 八套件指标现在只在 bench 输出里，README 该有固化快照 | README 新增评测表：八套件 passed/total + 门槛 + 探活结果；数字与 `bench` 实测一致 |
| M4-2 | **版本差异对照报告** | FR-07：`check_profile_all_versions` 已能返回同档案两版三维结果，但差异表还没有 | 差异表**从两版规则包 diff 生成**（非手写，见 plan/04 §6.3）：逐参数比对两版 `op`/`value`/`status`/`clause`，差异类型 ∈ {新增/数值变化/强化/废止}；CLI `diff` 子命令或 `report` 预留位 |
| M4-3 | **基准耗时与稳定性复核** | 八套件后总耗时 0.07s，富余大；确认 CI 上也无超时风险 | `bench` 全达标 + 耗时 < 上限（manifest `bench_max_seconds`） |

### M4 特别提醒

- **改规则包必须走生成器**（同 M2/M3 警告）；四联动：规则包重生成 + manifest sha256 自动更新 + 映射表重生成 + 依据索引重生成 + 台账 sha256 手工同步。
- **`mapping_accuracy_min=0.98` 与 `reconcile_consistency_min=1.0` 在 manifest 里**（数据非代码）；`mapping` 套件的考题完全由映射表条目推导——**新增参数/变体/歧义列名自动进枚举**，不需要改 `suite_mapping`。
- **`suite_reconcile` 场景二**的真值构造：整改件以同 `profile_id` 把越限参数换成真值库第三例的 donor 值；若改真值库前 3 例内容，注意场景仍须能同时产出三集合（探活依赖它）。
- **探活偷换映射表走 `_MAPPING_CACHE`**：`probe_falsifiable('mapping')` 同时劫持缓存条目与 `load_param_mapping`；若改 `engine/mapping.py` 的缓存结构，探活要同步。
- **维度参与度不回退**（D-43/O-19）：批量扫描的 nonpass 统计用 `observed_nonpass`，零生效规则维度天然不产出 finding，不会把干净车型误报成待整改。
- **新增 tools 脚本必须带 `_ensure_utf8_stdio()`**；CLI 顶层不得 import `gui`/`PySide6`（AST 门禁）。
- **`scan`/`compare` 的退出码语义**：只看"判出不符合"（O-5）；失败件/未提供不改退出码。`compare` 有新增或持续越限 → 1，全部整改完毕 → 0。

---

## 三、既定口径清单

M2 交接口径 O-1～O-22 全部有效（见 [HANDOFF-M3.md](HANDOFF-M3.md) §三），M3 新增 N-1～N-8（本文件 §1.3）。两表合并即当前全量口径；**动了会打挂基准与测试**。

---

## 四、本机环境坑

M2/M3 交接的坑全部仍有效（`py -3.12`/`py -3.8`、`/tmp` 不通、`-X utf8`、3.8 teardown 偶发崩、`check_profile` 返回三维容器、基准层不落盘等），见 [HANDOFF-M3.md](HANDOFF-M3.md) §四。M3 追加一条：

| 坑 | 实测现象 | 处置 |
|---|---|---|
| 映射表缓存路径键是**原样拼接**的 | `load_param_mapping('data')` 的缓存键是 `data/mapping/mapping.json`（相对），传绝对路径会 miss 重读 | 测试/探活统一传 `'data'`（或统一绝对路径）；别混用两种写法 |

---

## 五、M3 DoD 复核（3/3 ✅）

逐项证据见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §四 M3 完成记录表。

**需读者注意的三点**：
1. **映射是"列名 → 参数"的一步**，不做值猜测：歧义列名（「车速」）对全部候选参数注入不确定标记，由判定层显式出 `not_provided(mapping_uncertain)`；这与"参数缺失"（`missing`）是**两种原因码**，报告里要分开写。
2. **"本轮缺失件" ≠ "已整改"**：整改成效只能从"两轮都出现的档案"里算——这是防"把文件删了当整改完"的口径硬约束（N-5）。
3. **证据链断言是硬门**：`evidence_chain` 调用前先跑 `assert_traceability`，任何 finding 溯源不到来源块、或档案指纹缺失，直接抛 `TraceabilityError` 拒绝装配（NFR-10 的"不满足即拒导"在数据侧的落点）。

---

## 六、关键命令速查

```bash
cd <仓库根>

# 测试（双版本）
py -3.8  -m pytest -q
py -3.12 -m pytest -q

# 四个生成器（--check 守门）
py -3.12 -X utf8 tools/gen_rulesets.py --check
py -3.12 -X utf8 tools/gen_synthetic.py --check
py -3.12 -X utf8 tools/gen_mapping.py --check
py -3.12 -X utf8 tools/gen_knowledge.py --check

# 门禁
py -3.12 -X utf8 tools/check_zero_literals.py
py -3.12 -X utf8 tools/audit_desensitize.py --mode all

# CLI（需 PYTHONPATH=src）
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck selfcheck
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck check <档案.json>
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck scan <目录>          # M3：批量扫描
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck compare <上轮目录> <本轮目录>  # M3：三集合对账
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck bench
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck bench --only mapping
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck bench --only reconcile

# 八套件探活（每个都必须 True）
PYTHONPATH=src py -3.12 -X utf8 -c "
from ebikecheck import benchmark_runner as br
for s in br.SUITE_NAMES:
    print(s, br.probe_falsifiable('data', s))
"
```

**列名映射通路的取数姿势**（厂家参数表 → 标准档案）：

```bash
PYTHONPATH=src py -3.12 -X utf8 -c "
from ebikecheck.engine.mapping import load_param_mapping, normalize_params
table = load_param_mapping('data')
params = normalize_params({'最高车速': {'value': '24.5', 'unit': 'km/h'}, '车速': {'value': '20'}}, table)
# 歧义列名「车速」→ max_design_speed 等候选参数带 mapping_uncertain 标记
from ebikecheck import service
print(service.check_profile_dict({'profile_id': 'X', 'model_design_date': '2025-10-01', 'params': params}, 'data', 'GB17761-2024').overall())
"
```

---

## 七、本棒的已知未决项

| 项 | 状态 |
|---|---|
| README 评测表 | ⬜ **M4-1**（八套件数字见 §1.2，直接抄） |
| 版本差异对照报告 | ⬜ **M4-2**（`check_profile_all_versions` 已备好数据侧） |
| GB 17761—2018 条款号 | ⬜ 官方不提供全文，如实 `pending`（D-36，保留） |
| GB 43854 / GB 42296 首期不参数化条目 | ⬜ `pending` + 理由入 `notes`（D-37） |
| CI 真实运行 | ⬜ 未接远端；建仓后首推即首次 CI（D-31） |
| 报告导出（MD/XLSX，单一渲染源） | ⬜ M5（M3 证据链数据侧已备好：`evidence_chain` + `source_blocks`） |
| GUI（PySide6） | ⬜ M5（服务层 `scan_dir`/`compare_rounds` 已是界面可直接消费的形态） |

---

## 八、新对话启动提示词

```
/goal 读取 "<仓库绝对路径>\plan\HANDOFF-M4.md" 继续完成任务
```

（入库的本文档内一律用相对路径；绝对路径只由你在启动命令里拼。）
