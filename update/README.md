# update 交接索引 — e-bike-compliance-checker

> 诊断日期：2026-10-19
> 诊断方边界：只读诊断；未改任何受版本控制文件、未改 GitHub 状态、未发版、未改依赖。
> 唯一写入：本 `update/` 目录。

## 一句话结论

**建议迭代，产品面健康。** 226 项测试双解释器全绿、八套件基准全达标（门槛来自 manifest）、双状态门控（`status` + `clause_status`）落实、报告两格式两次导出逐字节一致且无外链、发布 zip 与 Release digest 逐位一致、冻结 exe 自检 `frozen=True` 且 bench 达标。要修的是两个「接缝」问题：**README 的每条命令都指向仓内不存在的 `<车型.json>`**（新 clone 跑不通主链路）；**CI 不跑脱敏的历史/提交信息扫描，且发布产物本体扫描工具只存在于被忽略的 `.tmp/`**。

## 文件索引

| 文件 | 用途 |
|---|---|
| [00-诊断报告.md](00-诊断报告.md) | 现状基线、自述逐项实测、做得好的部分、缺陷 D1-D8、失效模式逐条结论 |
| [01-迭代路线.md](01-迭代路线.md) | 分批动作、每批门禁、范围边界、本仓库特有的坑 |
| [02-提示词-迭代对话.md](02-提示词-迭代对话.md) | 可直接复制到新对话的完整执行提示词 |
| `03-执行记录.md` | 由**执行方**新建；记录决策、每批命令/汇总行/退出码，状态「待复验」 |

## 需要用户拍板的决策

### D-1 脱敏门禁常驻范围

| 方案 | 内容 | 收益 | 代价 | 建议 |
|---|---|---|---|---|
| **A** | CI 加 `audit_desensitize.py --mode all`；并把发布产物本体扫描并入 `tools/audit_desensitize.py`（新增 `--mode dist`）或入仓为独立工具 | 公开仓库的两类"不可撤回"风险都有常驻门禁；M6 的手工证据变成可复跑命令 | 需要把上游豁免清单（CPython 邮箱/Qt 构建路径/ASUSTek）入仓（片段拼接） | **推荐** |
| B | 只在 CI 加 `--mode all`；产物本体扫描仍手工 | 改动更小 | 产物扫描仍不可复跑（D7 仍在） | 可选 |
| C | 都不做 | 零改动 | 公开仓库无历史扫描门禁；留档声称的"实测"不可复跑 | 不推荐 |

> 事实：`audit_desensitize.py` 支持 `tracked/history/messages/all` 但**没有 dist 模式**；CI 目前只跑 `--selftest`（`tracked` 由 `tests/test_gates.py:269` 覆盖）。手工实测 `--mode all` = `DESSENSITIZE_AUDIT_OK`（0 HARD）。

### D-2 README 可运行示例

| 方案 | 内容 | 收益 | 代价 | 建议 |
|---|---|---|---|---|
| **A** | 入仓 `examples/sample-profile.json`（取 `data/truth/cases/SYN-CASE-001.json` 的 `profile` 对象），README/技术报告命令改指它 | 新 clone 直接可跑；示例合成、无真实信息 | 多一个仓内文件 | **推荐** |
| B | 不入仓，只在 README 补"从真值库提取 profile"的一行命令 | 不加文件 | 陌生人仍要多跑一步 `python -c`；文档更绕 | 可选 |
| C | 不改 | 零改动 | "按 README 逐字跑通"在新 clone 上不成立 | 不推荐 |

> 事实：仓内没有任何可直接 `check` 的档案；`check data/truth/cases/SYN-CASE-001.json` → exit 2「档案缺少 profile_id」。

### D-3 运行时与依赖口径（含发布）

| 方案 | 内容 | 收益 | 代价 | 建议 |
|---|---|---|---|---|
| **A** | `requires-python >=3.12`；CI 去 3.8；`gui = ["PySide6>=6.12,<7"]`；`build = ["pyinstaller>=6.22,<7", "setuptools<81"]`；升 `0.1.1` 并在用户确认后发布 | 与实测一致（Qt 6.12 → 226 passed；PyInstaller 6.22.3 构建通过）；去掉 EOL 运行时 | 排除 3.9–3.11 源码用户；PyInstaller 6 在 3.8 上未实测 | **推荐** |
| B | `>=3.11` + CI 加 3.11；其余同 A | 多覆盖一个受支持版本 | 多一个矩阵；本次未在 3.11 实测 | 可选 |
| C | 保留 `>=3.8`，只改上界与文档 | 不破坏 3.8 用户 | 继续背 EOL；**需先实测 PyInstaller 6 在 3.8 可用**（当前未验证） | 视用户需要 |

> 不要移动远端已有 tag `v0.1.0`（指向 `e117602`）；发布用新 tag。

### D-4 发布包是否包含 `data/knowledge/raw/`

| 方案 | 内容 | 收益 | 代价 | 建议 |
|---|---|---|---|---|
| **A** | 保持现状：`_internal/data/` 自带 6 份官方快照（4 份 openstd 元数据页 + 1 份问答 + 1 份 CCC 公告，**无标准全文**） | 发行包可离线溯源；与当前发布物一致 | 与同系列 labor/pipl 的"raw 不入包"口径不同 | **推荐**（内容经核实无版权/泄露问题） |
| B | 对齐姊妹仓：`data/knowledge/raw` 排除出包，包内只留 `clauses.json` | 口径统一 | 需改 spec 的 datas + 产物扫描白名单 + 重跑冻结态自检 | 可选 |

> 本诊断抽样读了 6 份快照正文：均为页面标题/元数据/问答，**未发现标准全文**；`data/README.md` 已登记版权口径。

## 本次迭代的边界

- **做**：入仓可运行示例 + README 命令落地 + 接线断言；CI 加 `--mode all`；产物本体扫描入仓（`--mode dist`）；README 徽章 + 内联演示 GIF；bench 耗时数字改实测；按 D-3 统一运行时口径。
- **不做**：改规则包数值/`status`/`clause_status`、改三态语义、改门槛与 manifest 阈值、改真值库、改退出码 0/1/2、改报告九章节结构、引入联网/LLM、发布（除非 D-3 选发布且用户执行）。
- **并行任务**：如果另一个对话在改别的仓库，本仓库只动本目录；不要跨仓库 `git add -A`。

## 起点基线（执行方不要重新论证）

- 路径：`D:\ProgramData\zcode\10-14-e-bike-compliance-checker`
- HEAD：`268b917783b37db6ff6b829e3f00b2976ec36708`；与 `origin/main` 0/0；工作树干净；**本地无 tag**，远端 `v0.1.0` → `e117602`。
- 测试：**226 collected / 226 passed**（py3.12 3.01 s；py3.8 3.88 s；py3.12 + PySide6 **6.12.0** 3.16 s）；dev-only（无 gui）→ 226 collected / 225 passed / 1 skipped。
- 基准：rules 17/17、boundary 26/26、rule_driven 26/26、dimensions 4/4、synthetic 12/12、version 1/1、mapping 84/84（门槛 0.98）、reconcile 3/3；耗时 **0.115 s**（README 写 0.059 s）。
- 规则条目：**verified=13 / pending=4**；pending 条目 `value` 均为 `null`。
- 依据索引：17 条，`clause_status` verified **11** / pending 6；知识快照 6 份（tracked，约 144 KB）。
- 真值库：`data/truth/cases/` 13 个文件。
- Release：`ebikecheck-desktop-v0.1.0-win64.zip` **118,335,198 B** digest `sha256:78b2e2c0e352210d569fb47b76364f5efc812a824dc4083ab5e3d9ac3d487ba5`；本地 `dist/release/` 同名 zip 的 sha256 **逐位一致**。
- 发布物：182 条目；`_internal/data/` 27 项（rules 5 + mapping 1 + knowledge 1 + **knowledge/raw 6** + truth 13 + README 1）。
- 发布物验收：解压后 `ebikecheck-cli.exe selfcheck` rc 0（`冻结态: True`、`数据在 exe 目录内: True`、verified=13/pending=4）；`bench` rc 0；`check`/`export`/`diff` rc 0。
- 报告：两次导出 `.md` 8,816 B / `.xlsx` 38,658 B sha256 全同；`.md` 中 `http` 计数 0。
- 门禁：零字面量（7 token，含 selftest）OK；四生成器 `--check` OK（5/13/1/1 份）；`audit_desensitize --mode all` = `DESSENSITIZE_AUDIT_OK`（0 HARD）；提交邮箱唯一 `yuluo554@users.noreply.github.com`。
- CI：最新 run `38524237502` 3 job 全 success；**CI 无 `--mode all`，也无 dist 产物扫描**。
- 实测现代化：py3.12 + PySide6 6.12.0 → 226 passed；**无任何 `examples/` 档案**，`check data/truth/cases/SYN-CASE-001.json` → exit 2。