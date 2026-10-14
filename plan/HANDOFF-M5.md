# HANDOFF-M5 —— M4 基准完整 → M5（桌面交付）交接

**用法**：新对话开头写 `/goal 读取 "plan/HANDOFF-M5.md" 继续完成任务`
（**入库文件内一律用相对路径**；绝对路径只在你的启动命令里拼，否则每份 HANDOFF 都带本机盘符、发布期脱敏扫描必中）。

**交接生成时间**：2026-10-14（M4 收尾落盘）
**上一棒**：M4 基准完整 —— ✅ 完成（DoD 3/3，见 [05 §四 M4](05-数据计划与里程碑.md)）
**本棒目标**：M5 桌面交付 —— PySide6 界面 + 报告导出（MD/XLSX 单一渲染源）+ PyInstaller 打包 + 技术报告

---

## 一、当前进度（M4 末态实测）

### 1.1 已建成且可跑的

| 层 | 文件 | 状态 |
|---|---|---|
| 基础 | `io_utils.py`、`paths.py` | ✅ |
| 引擎 | `engine/findings.py`（四态 + 三维 + 聚合）、`values.py`、`rules.py`、`matrix.py`、`version.py`、`mapping.py`（M3）、`reconcile.py`（M3）、**`version_diff.py`（M4 新增：两版规则包 diff）** | ✅ |
| 服务 | `service.py`（`selfcheck` / `check_profile*` 三通路 / `ruleset_overview` / `scan_dir` / `compare_rounds` / `assert_traceability` + `evidence_chain`（M3）/ **`version_diff` + `version_diff_profile`（M4）**） | ✅ |
| 表现 | `cli.py`（`selfcheck` / `check` / `rules` / `scan` / `compare` / **`diff` + `diff-profile`（M4）** / `bench` / `version`） | ✅ |
| 基准 | `benchmark_runner.py`（八套件 + 门槛读 manifest + 探活）、`benchmark/probes.py`、`benchmark/cases.py` | ✅ |
| 数据 | `data/rules/`（4 册 + manifest 冻结）、`data/truth/cases/`（13 例 + index 冻结）、`data/mapping/mapping.json`、`data/knowledge/` | ✅ |
| 工具 | `tools/` 生成器 + 门禁 + 审计器六件 | ✅ |
| 测试 | `tests/`（**192 项**，3.8/3.12 双绿；M4 新增 `test_m4_version_diff.py` 30 项） | ✅ |
| CI | `.github/workflows/ci.yml` | ✅ 就位，**未接远端未跑** |

### 1.2 关键实测数字（写文档/报告时直接引用）

```
规则库: 4 册 + manifest；verified=13 / pending=4；条款号 verified=11 / pending=6
  gb17761-2024.json  vehicle  verified=10  pending=0
  gb17761-2018.json  vehicle  verified=2   pending=0   （clause 全 pending，D-36）
  gb43854-2024.json  battery  verified=0   pending=2   （首期不参数化 → 维度零生效规则）
  gb42296-2022.json  charger  verified=1   pending=2
真值库: 13 例 + index.json
映射表: 14 参数 + 11 类单位别名
依据索引: 逐条挂条款 + 6 份官方快照（逐份 sha256）
基准:   rules 17/17, boundary 26/26, rule_driven 26/26, dimensions 4/4,
        synthetic 12/12, version 1/1, mapping 84/84（门槛 0.98）, reconcile 3/3（门槛 1.0）；
        耗时 0.061s（上限 1.0s）；八套件探活全部 True
测试:   192 项（py -3.8 与 py -3.12 双绿）
门禁:   零字面量 7 禁用 token 零命中；脱敏审计三模式 HARD=0
版本差异（2018→2024）: 新增 7 + 铅酸质量分支放宽 1 + 不变 2（max_design_speed + 其他电池分支）
CI:     workflow 就位；未接远端 → 未跑 CI（不记"CI 绿"）
```

### 1.3 M4 新口径（**动了会打挂 M4 测试**）

| # | 口径 | 决策 | 联动测试 |
|---|---|---|---|
| P-1 | **差异表只从规则包 diff 生成**（非手写）：`engine/version_diff.py` 纯函数消费 `Rule` 列表，服务层喂 `effective_rules()`；真值库/手写表零参与 | plan/04 §6.3 | `test_real_ruleset_diff_matches_expected_shape` |
| P-2 | **逐参数按 `applies_if` 配对，多分支行不折叠**："旧版无条件 vs 新版条件拆分"逐分支各配一对，每行带 `pairing` 配对依据 | M4 实现 | `test_unconditional_old_pairs_with_split_new_branches` |
| P-3 | **收紧/放宽只对同向阈值运算符成立**：`<=`/`<` 新值更大 = 放宽；`>=`/`>` 新值更大 = 收紧；`==`/`!=` 目标变化与跨运算符 value 变化如实记 `value_changed`，**不硬套方向**；同 value 跨 op 记 `operator_changed` | M4 实现 | `test_threshold_upper_relaxed_when_value_grows` 等 6 项 |
| P-4 | **旧→新方向 = 分册 `standard.published`（发布日）排序**，不依赖 manifest 锚点表顺序（锚点表顺序不承诺时间序；实测锚点表 2024 在前，按锚点序会方向颠倒） | M4 实现修正 | `test_old_to_new_by_publication_date` |
| P-5 | **diff 只消费生效规则**：`pending` 零参与（门控纪律在 diff 路径同样成立）；`version_diff` 服务层喂 `effective_rules()` | M4 登记 | `TestServiceVersionDiff` 全类 |
| P-6 | **动态半边（同档案两版结论对照）逐作用域取维度**：`version_diff_profile` 按 scope 抽两版 `CheckResult` 各自逐参数取"最弱结论"，只列结论变化的参数 | FR-07 | `test_direction_and_scope_split` |

### 1.4 M4 收尾已做的验证（留档，避免下一棒重复劳动）

| 验证 | 命令 | 结果 |
|---|---|---|
| 确定性冻结（规则包） | `tools/gen_rulesets.py --check` | `RULESETS_FROZEN_OK (5 份)` |
| 确定性冻结（真值库） | `tools/gen_synthetic.py --check` | `SYNTHETIC_FROZEN_OK (13 份)` |
| 确定性冻结（映射表） | `tools/gen_mapping.py --check` | `MAPPING_FROZEN_OK (1 份)` |
| 确定性冻结（依据索引） | `tools/gen_knowledge.py --check` | `KNOWLEDGE_FROZEN_OK (1 份)` |
| 零字面量门禁 | `tools/check_zero_literals.py` | `ZERO_LITERALS_OK`（7 token；**新源码含 docstring 全部零字面量**——写 M5 代码同样注意） |
| 脱敏审计三模式 | `tools/audit_desensitize.py --mode all` | `DESSENSITIZE_AUDIT_OK`（HARD=0） |
| 八套件探活 | `benchmark_runner.probe_falsifiable('data', s)` 逐个 | **八套件全部 `True`** |
| 双版本回归 | `py -3.8/-3.12 -m pytest` | **192/192 双绿** |

> **重要**（M3 起持续有效）：若改动源码后重新提交，**务必保持仓库级 `user.email` 为 noreply**
> （`git config user.email` 查一下）；用 `--amend` 时也要显式带 `GIT_COMMITTER_EMAIL`，
> 否则 committer 会回落全局真实邮箱。

---

## 二、下一里程碑待办（M5）

| # | 任务 | 为什么 | 完成判据 |
|---|---|---|---|
| M5-1 | **报告导出（MD/XLSX，单一渲染源）** | plan/04 §7：`report/sections.py` 单一渲染源 + 两个渲染器只消费它 | `report_sections()` 返回结构化章节；MD/XLSX 两产物逐项对等断言；逐字节可复现（MD 无时间戳；XLSX `ZIP_STORED` + 固定 `date_time`）；**无外链硬断言**；§3 参数来源块 + §8 证据指纹（M3 `evidence_chain` 数据侧已备好，直接消费） |
| M5-2 | **PySide6 GUI** | 服务层 `scan_dir`/`compare_rounds`/`version_diff*` 已是界面可直接消费的形态 | 界面只调 `service`（零判定逻辑）；AST 三条门禁（CLI 顶层不 import gui / gui 不含判定 / 引擎零第三方依赖）；三维页签 + 批量扫描页 + 对账页 |
| M5-3 | **PyInstaller 打包 + 中立目录自检** | 冻结态数据随包走 | onedir 双 exe（GUI ≥6）；冻结态自检：数据目录落在 exe 目录内（`selfcheck.frozen` + `data_dir_within_exe_dir` 已备好） |
| M5-4 | **技术报告** | 交付物 | `docs/技术报告.md`（M1-M5 实测数字直接抄各 HANDOFF §1.2） |
| M5-5 | **演示素材程序化产出** | plan/05 §四 M5 | PNG + GIF 固定帧序/尺寸/调色板，两次生成 sha256 一致 |

### M5 特别提醒

- **新依赖只进 extras**：`PySide6`/`pyinstaller` 进 `[project.optional-dependencies]` 对应层（plan/05 §五 分层），**引擎层零第三方依赖**的红线不动；GUI 包不进核心测试路径（CI 装核心 extras 即可跑全测试）。
- **报告无外链硬断言**：MD 正文与 XLSX 单元格/rels 内不得出现 `http(s)://`（来源 URL 是**数据侧** `source.url`，渲染成"来源编号"而非超链接——报告离线可审计、导出不外发）。
- **逐字节可复现**：报告生成时间取**输入侧**（档案字段或显式参数），不用系统时钟；写完必配"两次生成 sha256 一致"的测试。
- **`evidence_chain` 是导出前置硬门**（N-7）：报告 §8 的双指纹直接消费 `service.evidence_chain(result)`，它内部先跑 `assert_traceability`，断言失败抛 `TraceabilityError` —— 不要绕过它自己拼指纹。
- **新 tools 脚本必须带 `_ensure_utf8_stdio()`**；CLI 顶层不得 import `gui`/`PySide6`（AST 门禁已有，M5 加 GUI 后会被真正触发，别删）。
- **`diff` 子命令已是 M5 报告 §"版本坐标"的数据来源**：`service.version_diff()` 载荷含两版分册 file+sha256+逐参数差异，直接进报告，不另写第二份 diff 逻辑。

---

## 三、既定口径清单

M2 口径 O-1～O-22（[HANDOFF-M3.md](HANDOFF-M3.md) §三）+ M3 口径 N-1～N-8（[HANDOFF-M4.md](HANDOFF-M4.md) §1.3）+ M4 口径 P-1～P-6（本文件 §1.3），三表合并即当前全量口径；**动了会打挂基准与测试**。

---

## 四、本机环境坑

M2/M3/M4 交接的坑全部仍有效（`py -3.12`/`py -3.8`、`/tmp` 不通、`-X utf8`、3.8 teardown 偶发崩、`check_profile` 返回三维容器、基准层不落盘、映射表缓存键原样拼接），见 [HANDOFF-M4.md](HANDOFF-M4.md) §四。无新增。

---

## 五、M4 DoD 复核（3/3 ✅）

逐项证据见 [05-数据计划与里程碑.md](05-数据计划与里程碑.md) §四 M4 完成记录表。

**需读者注意的三点**：
1. **差异表是"生成"的，不是"写"的**：规则包未来更新（如补 GB 42296 参数化条目），`diff` 输出自动跟进；手工维护的对照表在这里是缺陷不是功能。
2. **方向语义有边界**：收紧/放宽只对同向阈值运算符有意义；`==` 目标变化（如布尔要求项）不带方向，如实记 `value_changed`——宁可少分类也不错分类。
3. **锚点表顺序 ≠ 时间序**：manifest.version_anchors 里 2024 排在 2018 前面（按"当前生效优先"登记），旧→新方向必须按分册发布日排序（P-4）——这是实现中真踩过的坑，不是理论提醒。

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
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck scan <目录>
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck compare <上轮目录> <本轮目录>
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck diff                    # M4：两版规则包差异
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck diff --old GB17761-2024 --new GB17761-2018
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck diff-profile <档案.json>  # M4：同档案两版结论对照
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck bench
PYTHONPATH=src py -3.12 -X utf8 -m ebikecheck bench --only mapping

# 八套件探活（每个都必须 True）
PYTHONPATH=src py -3.12 -X utf8 -c "
from ebikecheck import benchmark_runner as br
for s in br.SUITE_NAMES:
    print(s, br.probe_falsifiable('data', s))
"
```

---

## 七、本棒的已知未决项

| 项 | 状态 |
|---|---|
| 报告导出（MD/XLSX，单一渲染源） | ⬜ **M5-1**（`evidence_chain` + `source_blocks` + `version_diff` 数据侧全部备好） |
| GUI（PySide6） | ⬜ **M5-2**（服务层已全面就位） |
| PyInstaller 打包 + 中立目录自检 | ⬜ M5-3 |
| 技术报告 | ⬜ M5-4 |
| 演示素材程序化产出 | ⬜ M5-5 |
| GB 17761—2018 条款号 | ⬜ 官方不提供全文，如实 `pending`（D-36，保留） |
| GB 43854 / GB 42296 首期不参数化条目 | ⬜ `pending` + 理由入 `notes`（D-37） |
| CI 真实运行 | ⬜ 未接远端；建仓后首推即首次 CI（D-31） |

---

## 八、新对话启动提示词

```
/goal 读取 "<仓库绝对路径>\plan\HANDOFF-M5.md" 继续完成任务
```

（入库的本文档内一律用相对路径；绝对路径只由你在启动命令里拼。）
