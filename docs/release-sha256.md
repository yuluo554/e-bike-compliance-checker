# Release 附件 sha256 留档（M6）

留档时间：2026-10-14（发布期基准日）
仓库：github.com/yuluo554/e-bike-compliance-checker（私有 → 发布期转公开，D-31）
源码锚点：main @ e117602（M6 dev-extras 修复；CI run 38519270253 三矩阵全绿）

## v0.1.1（2026-10-19，本地已打包；**未打 tag / 未发 Release**）

| 附件名（ASCII） | 内容 | sha256 | 字节数 |
|---|---|---|---|
| `ebikecheck-desktop-v0.1.1-win64.zip` | PyInstaller onedir 双 exe（ebikecheck-gui.exe + ebikecheck-cli.exe + `_internal/` 含冻结态 data），Windows x64 | `5246fe64bfe8c4549a275c67b2039a608db4264f7e9814e7da2948f20f956d0e` | 125,273,126 |

- 构建环境（干净 venv）：Python 3.12 + PySide6 **6.12.0** + PyInstaller **6.22.3**
  （迭代 D-47 后 `gui`/`build` extras 的下限，见 [plan/06 §1.6](../plan/06-决策记录.md)）；
- 打包口径与 v0.1.0 相同（`ZIP_STORED` + 条目按路径排序 + 全部条目 `date_time=(2026,10,14,0,0,0)`）；
  本地两次独立打包**逐字节一致**（194 条目，`zf.testzip()` OK）；
- 冻结态自检：`ebikecheck-cli.exe version` → `ebikecheck 0.1.1`；`selfcheck` rc 0
  （`冻结态: True`、`数据在 exe 目录内: True`、verified=13/pending=4）；`bench` rc 0
  （八套件达标，耗时 0.135s，上限 1.0s）；
- 产物本体脱敏扫描（仓内工具复跑）：`py -3.12 tools/audit_desensitize.py --mode dist --dist-dir dist`
  → `DESSENSITIZE_AUDIT_OK`（HARD=0，上游固有元数据精确值豁免单列）；
- **发布动作由用户本人执行**：打 tag `v0.1.1` + `gh release create` + 上传 zip（涉及 2FA）；
  执行方不自宣发布。**不要移动远端已有 tag `v0.1.0`**（指向 `e117602`）。

## v0.1.0 附件（M6，已发布）

| 附件名（ASCII） | 内容 | sha256 | 字节数 |
|---|---|---|---|
| `ebikecheck-desktop-v0.1.0-win64.zip` | PyInstaller onedir 双 exe（ebikecheck-gui.exe + ebikecheck-cli.exe + `_internal/` 含冻结态 data），Windows x64 | `78b2e2c0e352210d569fb47b76364f5efc812a824dc4083ab5e3d9ac3d487ba5` | 118,335,198 |

## 打包口径（可复现）

- 内容源：`dist/ebikecheck-desktop/`（`py -3.12 -m PyInstaller tools/ebikecheck.spec --noconfirm` 产物）；
- zip 打包：Python 标准库 `zipfile`，`ZIP_STORED`（不压缩，exe 已不可压），条目按路径排序，
  全部条目 `date_time` 固定为 `(2026, 10, 14, 0, 0, 0)`；
- **两次独立打包逐字节一致**（M6 实测 `deterministic: True`）；
- 解包后 `zf.testzip()` 完整性 OK（182 条目）。

## 中立目录验证（打包后、发布前，实测）

产物拷贝到仓库外临时目录，清 `PYTHON*`/`EBIKE*` 环境变量、CWD 为临时 witness 目录运行：

```
ebikecheck-cli.exe selfcheck → returncode 0
  冻结态: True
  数据目录在 exe 目录内: True
  规则条目: verified=13 / pending=4（四分册计数与仓内一致）
```

## 构建产物本体脱敏扫描（M6-1，实测）

- 文本类产物（pyi 元数据等）扫描：HARD=0 / REVIEW=0；
- 二进制本体（66 个 exe/dll/pyd/pyc/zip）逐字节搜邮箱/用户目录/手机号/sk- 密钥：
  项目自有内容**零命中**；命中项经溯源全部为上游官方发行件固有元数据
  （CPython 维护者邮箱存在于官方 `python312.dll` 同串——此处不逐字留痕、形态 `ama***@gmail.com`；
  Qt 官方构建账号路径 `C:` + `\` + `Users` + `\qt`——片段拼接以免扫描器自命中；
  `ASUSTek COMPUTER INC` 为 Qt 内置显示设备厂商库串）——非本项目引入，不构成泄露。
- 本机用户名/工作盘符/仓库路径/作者邮箱在产物内零命中。

> **复跑（入仓工具，2026-10-19 起）**：构建产物本体扫描现由仓内脱敏审计器复跑：
> `py -3.12 tools/audit_desensitize.py --mode dist --dist-dir dist`。
> 上游固有元数据豁免清单在 `tools/dist_allowlist.py`（**精确值 + 片段拼接**，不是"全部豁免"）；
> 未登记的 HARD 命中会让命令以退出码 1 结束。历史/提交信息扫描已常驻 CI：`--mode all`。

## 验证记录（M6-5，实测 2026-10-14）

1. **真下载**：`gh release download v0.1.0` 从 GitHub Release 真实下载附件（118,335,198 字节）；
2. **sha256 核对**：下载件 sha256 = `78b2e2c0e352210d569fb47b76364f5efc812a824dc4083ab5e3d9ac3d487ba5`，与上表留档**一致**；
3. **中立目录冻结态自检**：全新临时目录解包，清 `PYTHON*`/`EBIKE*` 环境变量、CWD 为独立 witness 目录：
   `ebikecheck-cli.exe selfcheck` → returncode 0，`冻结态: True`、`数据目录在 exe 目录内: True`、
   规则条目 verified=13 / pending=4（四分册计数与仓内一致）；
4. **冻结态 bench**：同一中立目录 `ebikecheck-cli.exe bench` → returncode 0，八套件达标，耗时 0.073s（上限 1.0s）。
