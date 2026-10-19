# 可运行示例（合成数据）

`sample-profile.json` 是 **合成车型档案**（虚构企业名 + 测试号段 `90000000…SYN`、车型代号 `SYN-…`），
内容取自真值库 `data/truth/cases/SYN-CASE-001.json` 的 `profile` 对象，供 README/技术报告的命令直接引用。

- 它**不是**真值用例文件：`data/truth/cases/*.json` 的结构是
  `{case_id, kind, target_param, profile, expect, notes}`，整个用例喂给 `check` 会因缺少顶层
  `profile_id` 而以退出码 2 拒绝；需要独立档案时取其中的 `profile` 对象。
- 示例结论：**无不符合项**（`不符合 0`，退出码 0）；整体结论为「未提供」——用例只覆盖 6 个
  参数，其余参数缺失按纪律判 `not_provided`，**不是「符合」**。示例仅用于确认工具链路可跑；
  **不得据此对任何真实车型作合规结论**。

重新生成（确定性，逐字节一致）：

```bash
py -3.12 - <<'PY'
import json
src = json.load(open('data/truth/cases/SYN-CASE-001.json', encoding='utf-8'))
with open('examples/sample-profile.json', 'w', encoding='utf-8', newline='\n') as fh:
    json.dump(src['profile'], fh, ensure_ascii=False, indent=2)
    fh.write('\n')
PY
```
