# e-bike-compliance-checker

[![CI](https://github.com/yuluo554/e-bike-compliance-checker/actions/workflows/ci.yml/badge.svg)](https://github.com/yuluo554/e-bike-compliance-checker/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/yuluo554/e-bike-compliance-checker)](https://github.com/yuluo554/e-bike-compliance-checker/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)

电动自行车合规核查工作台 —— 以强制性国家标准 **GB 17761—2024《电动自行车安全技术规范》**（发布 2024-12-31，**实施 2025-09-01**，代替 GB 17761—2018）、**GB 43854—2024《电动自行车用锂离子蓄电池安全技术规范》**、**GB 42296—2022《电动自行车用充电器安全技术要求》** 为规则源，把**整车/蓄电池/充电器三维限值矩阵 + 字段映射 + 双版本对照 + 车型清单批量对账 + 报告导出**做成**逐项挂标准条款与数值依据、可复现、留指纹**的本地工具（桌面 exe + CLI 双形态）。

> 本地目录 `10-14-e-bike-compliance-checker`（`10-14` = 2026-10-14 日期标签）。GitHub 仓库名发布时用纯净名 `e-bike-compliance-checker`，见 [plan/00-README总览.md](plan/00-README总览.md)。

**全本地处理、零上传**：车型参数与供应链信息可能含商业敏感信息，工具默认不联网、不做任何数据外发。

> 状态：✅ **M6 脱敏发布已完成（2026-10-14）**——M5 桌面交付（报告导出 `export`：Markdown + XLSX 单一渲染源、逐字节可复现、无外链、证据指纹；PySide6 界面 `gui`：四页签零判定逻辑；PyInstaller onedir 双 exe）之上，M6 完成：**GitHub 建仓 + CI 三矩阵全绿**（windows py3.8/py3.12 + ubuntu py3.12，push 数 = run 数对账）、**Release v0.1.0**（双 exe 附件，sha256 留档 `docs/release-sha256.md` + 真下载核对一致）、**干净环境验证**（git archive 树 + 全新 venv 按 README 逐字跑通）、**发布物中立目录验证**（自检 frozen=True + bench 达标）。内置评测基准**八套件全绿**，226 项测试 3.8/3.12 双绿。技术报告见 [docs/技术报告.md](docs/技术报告.md)。

---

## 演示

![工作台示意：单车核查 / 批量扫描 / 版本差异三帧](docs/assets/demo-overview.gif)

> 素材由 `tools/gen_demo_assets.py` **程序化产出**（三帧 PNG + GIF，两次生成 sha256 一致，
> `tests/test_m5_demo_assets.py` 守门）——是**示意图**（640×360，16 色调色板），不是界面截图；
> 真实界面以你本机 `ebikecheck gui` 运行结果为准。

## 它解决什么问题

| 痛点 | 本工具的能力 |
|---|---|
| 这款车型的关键参数符不符合新国标？ | 参数 × 限值确定性判定（车速、整车质量、塑料占比、防篡改设计…），挂标准条款 |
| 电池和充电器还有别的强制标准管吗？ | GB 43854—2024 与 GB 42296—2022 分册联动核查，统一结论挂各自条款 |
| 参数表列名五花八门，怎么对得上标准参数？ | 字段映射引擎（列名变体 → 标准参数名）；映射不确定即标 `未提供`，绝不臆测 |
| 2024 版换掉了 2018 版，旧车型怎么算？ | 双版本规则集 + 按车型年份锚定版本 + 版本差异对照 |
| 整批车型清单几百款，哪几款越限？ | 批量扫描 + 越限清单 + 失败件隔离 |
| 整改是循环的，"这轮比上轮好了没" | 跨轮对账：新增越限 / 已整改 / 持续越限 |
| 结论要能交给送检/存档 | 报告导出（Markdown + XLSX）+ 车型档案 sha256 指纹 |

## 规则库版本化与 status 门控（本项目的核心纪律）

规则库按 **`标准 × 版本`** 组织（`data/rules/`），限值编码为可执行规则（JSON）。每条挂标准号与两个**独立**状态：

- `status` —— 数值核对状态。`verified` 才**可进入核查路径**；`pending` **绝不参与任何核查或判定**，且 `value` 必须为 `null`（待核对不许预填数值）。
- `clause_status` —— 条款号核对状态。**M1 已通过 openstd 国家标准全文公开系统**取得 GB 17761—2024 / GB 43854—2024 / GB 42296—2022 三份现行标准全文并**逐条核到条款号**（如车速限值 6.1.1.1、整车质量 6.1.3、标称电压 6.3.5、塑料占比 6.5.1、防篡改 6.8.x），核到即 `verified` 并填 `clause`。**核不到的一律 `pending` + `clause: null`**（如已废止的 GB 17761—2018——官方明示"废止标准不提供标准文本阅读服务"，无全文可核）。**绝不编造条款号**——编造标准内容比缺失更严重。

两个状态**都在产物中显式可见**，不存在"悄悄当作已核对"。

**未挂原文核对的条目不得落库生效**。**"未提供参数"判 `未提供`，绝不判为符合**——"没查到问题"与"没检查过"绝不等同。一条规则都不适用时整体记 `未评估`（`not_assessed`），**不输出"符合"**。

### 零字面量门禁

限值数值**只许来自规则包**：`tools/check_zero_literals.py` 把规则包里的全部数值收编为禁用 token，扫描引擎/基准/工具源码（**含 docstring 与注释**），命中即失败。它同时也扫自己会误报的形态，故配 `--selftest` 正负对照。

## 依据锚点（基准日 2026-10-14 核验）

| 依据 | 编号 | 状态 |
|---|---|---|
| 电动自行车安全技术规范 | **GB 17761—2024** | ✅ 发布 2024-12-31 / **实施 2025-09-01** / 现行 / 强制性（openstd 核对）；**M1 取得全文并逐条核到条款号与限值** |
| 同上（旧版，历史车型对照） | **GB 17761—2018** | ✅ 2018-05-15 发布 / 2019-04-15 实施 / **废止**（官方不提供全文 → 条款号如实标 `pending`） |
| 电动自行车用锂离子蓄电池安全技术规范 | **GB 43854—2024** | ✅ 发布 2024-04-25 / 实施 2024-11-01 / 现行 / 强制性；**M1 取得全文核对**（型式试验类，无可参数化固定数值限值） |
| 电动自行车用充电器安全技术要求 | **GB 42296—2022** | ✅ 发布 2022-12-29 / 实施 2023-07-01 / 现行 / 强制性；**M1 取得全文**，据 5.5.4 建"空载输出电压 ≤42.4 V"条目 |
| 锂电池、充电器实施 CCC 的公告 | **市场监管总局公告 2024年第26号** | ✅ **M1 核到**：成文 2024-06-25；2024-10-15 起受理 CCC、2025-11-01 起强制（gov.cn 国务院部门文件库） |

> **基准日核验**：GB 17761—2024 于 2025-09-01 实施、替代 GB 17761—2018，其生产/销售过渡期已于 2025-11-30 届满（在基准日之前完成切换）；**截至 2026-10-14 未见 GB 17761—2024 的修改单或延期公告**。

## 快速开始（M0 已可跑）

要求 Python 3.12+（核心功能无第三方依赖）。

```bash
python -m venv .venv
# Windows(Git Bash): source .venv/Scripts/activate    Linux/macOS: source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

**已可用**（M0 骨架 + M1 数据 + M2 三维引擎 + M3 映射与对账 + M4 版本差异对照 + M5 报告导出与桌面）：

```bash
ebikecheck selfcheck                 # 数据目录定位 + 规则库加载 + status 门控计数（+ 冻结态自检）
ebikecheck check examples/sample-profile.json   # 单车型三维核查：整车 + 电池 + 充电器 + 统一结论（--json / --version-of）
ebikecheck scan examples             # 批量扫描：失败件单列原因码（不改退出码语义），与越限件分列
# 跨轮对账：构造两轮目录（示例档案同时放入两轮 = 最简可复现输入）
mkdir -p "$TEMP/ebikecheck-round1" "$TEMP/ebikecheck-round2"
cp examples/sample-profile.json "$TEMP/ebikecheck-round1/"
cp examples/sample-profile.json "$TEMP/ebikecheck-round2/"
ebikecheck compare "$TEMP/ebikecheck-round1" "$TEMP/ebikecheck-round2"  # 跨轮对账三集合：新增越限 / 已整改 / 持续越限
#   注意：示例档案只覆盖 6 个参数，对账把 `not_provided` 也计入"持续越限"集合 →
#   本例退出码为 1（现有对账口径，本轮迭代未改）；纯链路验证看上面 check/scan/diff-profile/export 四条
ebikecheck diff                      # 两版规则包差异对照（从规则包 diff 生成；--old/--new 显式指定）
ebikecheck diff-profile examples/sample-profile.json  # 同一档案在两版规则下逐参数结论对照
ebikecheck export examples/sample-profile.json --out-dir "$TEMP/ebikecheck-report"   # 报告导出（Markdown + XLSX 单一渲染源；--generated-at 输入侧时间）
ebikecheck gui                       # 桌面界面（PySide6 四页签；需 extras: pip install -e ".[gui]"）
ebikecheck rules                     # 规则库概览与逐册门控计数
ebikecheck bench                     # 内置评测基准（八套件，门槛自 manifest 下发）
ebikecheck version
python -m pytest -q                  # 测试套件（234 项）
python tools/gen_rulesets.py --check # 规则包冻结守门（再生成逐字节一致）
python tools/gen_synthetic.py --check# 真值库冻结守门
python tools/gen_mapping.py --check  # 字段映射表冻结守门
python tools/gen_knowledge.py --check# 依据索引冻结守门
python tools/check_zero_literals.py  # 零字面量门禁
python tools/audit_desensitize.py    # 脱敏审计（tracked/history/messages + selftest）
python tools/audit_desensitize.py --mode dist --dist-dir dist  # 构建产物本体扫描（上游固有元数据豁免单列）
python tools/gen_demo_assets.py      # 演示素材程序化产出（PNG + GIF，两次生成 sha256 一致）
```

**打包**（onedir 双 exe，需 extras: `pip install -e ".[build]"`）：

```bash
py -3.12 -m PyInstaller tools/ebikecheck.spec --noconfirm
# 产物 build/dist/ebikecheck-desktop/：
#   ebikecheck-gui.exe（图形界面）+ ebikecheck-cli.exe（命令行）+ _internal/data（冻结态数据随包走）
# 冻结态自检：ebikecheck-cli.exe selfcheck → frozen=True / data_dir_within_exe_dir=True
```

**发布**：GitHub Release `v0.1.0`（M6）与 **`v0.1.1`（2026-10-19，本轮迭代）**，均附双 exe zip；sha256 留档与真下载核对见 [docs/release-sha256.md](docs/release-sha256.md)。

### CLI 退出码

| 码 | 含义 |
|---|---|
| 0 | 通过（无"不符合"；仅"未提供"不改退出码） |
| 1 | 检出不符合 / 基准未达标 |
| 2 | 用法或输入错误（文件不存在、schema 非法、`--only` 未知名） |

> **"未判定"与"判出违规"是两种退出码语义**。"有一件没判定"不会报成"检出违规"，否则 CI 会误判。

## 里程碑

| 里程碑 | 内容 | 状态 |
|---|---|---|
| M0 | 计划 00–06 定稿 + 可运行骨架（规则加载/门控/限值骨架/CLI/基准/门禁/测试/CI） | ✅ 2026-10-14 完成（87 测试 3.8/3.12 双绿；CI 于 M6 首推后全绿，见 M6 行） |
| M1 | 数据先行：限值规则逐条挂原文核对（补条款号）+ 字段映射 + 依据索引 | ✅ 2026-10-14 完成（94 测试 3.8/3.12 双绿；条款号 11 条 verified；见 [05 §四 M1 DoD](plan/05-数据计划与里程碑.md)） |
| M2 | 限值矩阵引擎完整：三维（整车/电池/充电器）判定 + 跨标准统一结论 + 边界枚举与规则驱动基准 | ✅ 2026-10-14 完成（133 测试 3.8/3.12 双绿；bench 六套件全绿 17/17·26/26·26/26·4/4·12/12·1/1；见 [05 §四 M2](plan/05-数据计划与里程碑.md)） |
| M3 | 字段映射与对账：列名映射 + 批量扫描 + 跨轮对账 + 报告/证据链 | ✅ 2026-10-14 完成（162 测试 3.8/3.12 双绿；bench 八套件全绿 84/84·3/3；见 [05 §四 M3](plan/05-数据计划与里程碑.md)） |
| M4 | 基准完整：八套件 + 探活，指标进 README；版本差异对照报告 | ✅ 2026-10-14 完成（192 测试 3.8/3.12 双绿；`diff`/`diff-profile` 从两版规则包 diff 生成；见 [05 §四 M4](plan/05-数据计划与里程碑.md)） |
| M5 | 桌面交付：报告导出（MD/XLSX 单一渲染源）+ PySide6 界面 + PyInstaller 打包 + 技术报告 + 演示素材 | ✅ 2026-10-14 完成（226 测试 3.8/3.12 双绿；报告两格式对等/逐字节可复现/无外链；双 exe 中立目录冻结态自检通过；见 [docs/技术报告.md](docs/技术报告.md)） |
| M6 | 脱敏发布 GitHub + Release（exe）+ 收尾固化 | ✅ 2026-10-14 完成（CI 三矩阵全绿、push 数 = run 数对账；Release v0.1.0 附件 sha256 留档一致；干净环境验证 + 发布物中立目录自检通过；见 [docs/release-sha256.md](docs/release-sha256.md) 与 [05 §四 M6](plan/05-数据计划与里程碑.md)） |

> **M0 诚实说明的回填（M6）**：M0 时 CI 仅本地等价校验未真实运行；M6 首推后真实 CI 已跑——首跑失败（dev extras 缺 Pillow，与 M6-2 干净环境暴露的是同一缺口）→ 修复提交 e117602 → **三矩阵全绿**。诚实记录保留：首跑失败不遮掩。

## 内置评测基准（零 API 依赖、离线可跑）

门槛**只从 manifest 读**（数据非代码）；每套件配**可证伪探活**（注入缺陷后必须报未达标）。
下表为 M4 收尾（2026-10-14）实测快照，与 `ebikecheck bench` 输出一致；复跑以命令实测为准。

| 套件 | 层 | 测什么 | passed/total | 门槛（manifest 下发） | 探活 |
|---|---|---|---|---|---|
| `rules` | 规则包自洽 | `status` 门控计数正确、`pending` 零进入核查路径 | 17/17 | 1.0 | ✅ True |
| `boundary` | **规则驱动** | 由规则表推导全部限值端点（覆盖 `<= >= < > == != in not_in range` 与布尔/无量纲条目） | 26/26 | 1.0 | ✅ True |
| `rule_driven` | **规则驱动** | 同一套推导端点走完整三维核查路径端到端对账（不读真值库） | 26/26 | 1.0 | ✅ True |
| `dimensions` | **规则驱动** | 三维齐备 + 越限所在维度判不符合 + 统一结论不丢维度结论 | 4/4 | 1.0 | ✅ True |
| `synthetic` | 样本驱动 | 合成真值库逐例对账（含边界/缺参数/单位换算/干净/版本差异） | 12/12 | 1.0 | ✅ True |
| `version` | 样本驱动 | 双版本对照：同档案两版期望结论不同 | 1/1 | 1.0 | ✅ True |
| `mapping` | **规则驱动** | 字段映射：全部已登记变体精确命中 + 歧义列名判 uncertain + 未登记判 unmapped | 84/84 | 0.98 | ✅ True |
| `reconcile` | 样本驱动 | 跨轮对账三集合语义端到端（真值库构造整改/新增/缺失件场景） | 3/3 | 1.0 | ✅ True |

总耗时 ≈0.12 s（实测 0.115 s 源码态 / 0.13 s 冻结 exe；上限 1.0s，随 manifest 下发；`bench_max_seconds`）。`boundary` / `rule_driven` /
`dimensions` / `mapping` **不读真值库**，只从规则包/映射表推导 —— 新增规则或映射条目自动进枚举，无需改基准代码。

## 报告导出与桌面界面（M5）

**报告导出**（`export` 子命令 / GUI 一键导出）：

- 单一渲染源：九章节结构化载荷（报告头/输入事实/参数来源块/逐项结论/越限与整改/未评估与门控排除/版本坐标与两版差异/证据指纹/免责声明），Markdown 与 XLSX 两渲染器只消费它 → 两格式内容逐项对等（测试断言）；
- 无外链：来源 URL 只渲染成"来源编号"，MD 正文与 XLSX 单元格不得出现 `http(s)://`（离线可审计、导出不外发）；
- 逐字节可复现：生成时间取输入侧（`--generated-at`），XLSX 自写最小 OOXML（`ZIP_STORED` + 固定时间戳），同输入两次导出 sha256 一致；
- 证据链前置硬门：`§8 证据指纹` 直接消费 `service.evidence_chain`（内部先跑溯源完整性断言，失败即拒绝导出）。

**桌面界面**（`gui` 子命令，PySide6）：单车核查 / 批量扫描 / 跨轮对账 / 版本差异四页签；**零判定逻辑**——取数全部经 `service`（与 CLI 同一事实源），AST 门禁禁止 import 引擎层。安装：`pip install -e ".[gui]"`。

## 版本差异对照（FR-07）

差异表**从两版规则包 diff 生成**（非手写，plan/04 §6.3）：逐参数按 `applies_if` 配对
（旧版无条件规则 vs 新版条件拆分时逐分支配对，不误报整体新增），差异类型 ∈
**新增 / 废止 / 收紧 / 放宽 / 数值变化 / 判定方式变化**。以现行库实测（2018 → 2024）：
新增 7 条（塑料占比 ≤5.5%、标称电压 ≤48V、电机功率 ≤400W、超速断电、防篡改三项）、
铅蓄电池整车质量分支放宽（限值上调、其余分支不变）、最高车速不变。

```bash
ebikecheck diff                      # 两版规则包差异（--old/--new 显式指定版本键，缺省按发布日取两端）
ebikecheck diff --json               # 机读载荷（含两版分册 file + sha256，可溯源）
ebikecheck diff-profile examples/sample-profile.json  # 同一档案两版逐参数结论对照（动态半边）
```

## 限制与免责

- **首期范围**：GB 17761—2024 主要可参数化限值 + GB 43854—2024 + GB 42296—2022；GB 17761—2018 历史对照；纯试验方法条款（阻燃、电磁兼容等）**不建规则**（无参数化输入面，硬判必错）。
- **数据底座诚实说明**：限值规则由 **openstd 标准元数据页 + gov.cn 官方问答页 + openstd 国家标准全文公开系统**三个可直连来源支撑。M0 时强制标准全文正文未取得可直连解析载荷、条款号一律待核对；**M1 已突破**：经 openstd 全文公开系统（在线预览页图精灵图通道）取得 GB 17761—2024 / GB 43854—2024 / GB 42296—2022 三份现行标准全文，**逐条核到条款号**（11 条 `verified`）。唯一例外是**已废止的 GB 17761—2018**——官方明示"废止标准不提供标准文本阅读服务"，其条款号如实标 `pending`，**不编造**。GB 43854 经全文核对确认**无可参数化固定数值限值**（型式试验类）、GB 42296 仅 5.5.4 一条可参数化，其余条目 `pending` 且 `value: null`，**不进入核查路径**。
- 本工具输出为**基于标准限值的合规检查发现**，不构成产品合格判定、检测结论或行政认定；正式结论以具备资质的检验检测机构报告与市场监管部门口径为准。
- 规则条目核对状态以规则库 `status` 为准；**`pending` 条目不参与核查**，报告会显式列出"本次未启用 N 条"。
- 演示与基准一律使用**合成车型档案**（虚构企业名 + 测试号段 `90000000…SYN`、车型代号 `SYN-…`），不含任何真实企业或产品信息。

## 目录结构

```
plan/                计划文档 00–06 + HANDOFF
data/rules/          限值规则包（生成器冻结产物，禁手改）
data/mapping/        字段映射表 + 单位别名表（生成器冻结产物）
data/knowledge/      依据索引 + 官方快照（生成器冻结产物 + 逐份 sha256）
data/truth/          合成车型档案 + 真值库（生成器冻结产物）
docs/                技术报告 + 演示素材（程序化产出，docs/assets/）
tools/               生成器 / 门禁 / 脱敏审计器 / 打包 spec / 素材生成器
src/ebikecheck/      包（engine/ 为确定性内核，零第三方依赖；gui/ 为 PySide6 界面）
tests/               pytest 测试套件
benchmark 套件       内置评测基准（src/ebikecheck/benchmark/）
```

## 许可

MIT，见 [LICENSE](LICENSE)。
