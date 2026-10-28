# STEP-70：`ux` 契约自洽化（P-147 + P-150）

## 1. 归属

- 所属切片：P-A 契约自洽层
- 来源需求：`02` M-5；台账 P-147、P-150
- 来源方案：D-V24-02、D-V24-03
- 语义作者：规划方（`03` §2 给出逐字新文本）；**本卡执行侧只做字节替换**

## 2. 目标

`docs/任务规划V0.12.0/contracts/ux_states.schema.json` 不再自相矛盾：`definitions.State` 不再声称「每视图必交 8 态」，6 个视图的 `states` 键集全部是 enum 的子集，且 `pytest tests/test_ux_states_contract.py` 四条仍全绿。

## 3. 输入

- 文档：`docs/任务规划V0.24.0/03-裁决与契约增量.md` §2（**逐字新文本，唯一依据**）
- 契约：`docs/任务规划V0.12.0/contracts/ux_states.schema.json`
- 前置任务：无
- 前置状态：`main@3c4138d`，工作树干净

## 4. 输出

- 修改：`docs/任务规划V0.12.0/contracts/ux_states.schema.json`（五处，见 S70.1～S70.5）
- 新增：`docs/06_validation/evidence/EVD-V24-70/before_after.json`（五处替换的前后原文）
- 修改：`docs/06_validation/evidence/EVD-V24-70/readings.md`（pytest 输出原文）
- 修改：`docs/任务规划V0.12.0/00-README.md`（P 表新增 P-153）

## 5. Execution Steps

1. [ ] 先 `cp` 一份原文件到 `EVD-V24-70/ux_states.before.json`（供 before/after 对照）
2. [ ] **S70.1** `definitions.State` 的 `"x-required-for-every-core-view": true` → `false`（只改值）
3. [ ] **S70.2** `definitions.State` 的 `note` 整串替换为 `03` §2.2 的新串（逐字，不得增删标点）
4. [ ] **S70.3** `x-universal-rules` 数组第 5 项（下标 4）整串替换为 `03` §2.3 的新串
5. [ ] **S70.4** 三处 `unauthenticated` 整串替换为 `03` §2.4 的 (a)(b)(c)
6. [ ] **S70.5** 把 `NotificationBell` 视图 `states` 里的 `"offstate": "..."` 整项**剪切**，作为该视图新增键 `x-build-mode-notes` 下的 `offstate`，值改为 `03` §2.5 给的新串
7. [ ] `python -c "import json;json.load(open(...,encoding='utf-8'))"` 校验可解析
8. [ ] 跑 `pytest tests/test_ux_states_contract.py -q`，四条全绿
9. [ ] 写 `before_after.json`（五处 old/new 原文）与 `readings.md`
10. [ ] 本卡单独提交并推送，核验远端包含该提交

## 6. 验收标准

- [ ] `python -c` 能 `json.load` 该文件（语法有效）
- [ ] `grep -c '"x-required-for-every-core-view": false'` = 1
- [ ] `definitions.State.enum` 仍恰 8 值且顺序未变（`test_ux_states_literal_equals_frozen_draft_enum` 绿）
- [ ] `note` 与 `x-required-for-every-core-view` 两个**键**仍存在（`test_frozen_draft_is_read_only_for_this_card` 绿）
- [ ] `NotificationBell.states` 的键集 = `{loading,empty,success,error,degraded}`（5 个，无 `offstate`）
- [ ] 每个视图的 `states` 键集都是 `definitions.State.enum` 的子集（6/6 视图）
- [ ] `pytest tests/test_ux_states_contract.py` 4 passed
- [ ] `git diff --stat` 只含本卡第 4 节列出的文件

## 7. 验证命令

```bash
cd /d/Code/AideanBotHot
python -c "import json;d=json.load(open('docs/任务规划V0.12.0/contracts/ux_states.schema.json',encoding='utf-8'));print('ok')"
python -c "
import json
d=json.load(open('docs/任务规划V0.12.0/contracts/ux_states.schema.json',encoding='utf-8'))
enum=set(d['definitions']['State']['enum'])
print('x-required=',d['definitions']['State']['x-required-for-every-core-view'])
for v in d['x-core-views']:
    ks=set(v['states']); print(v['view'][:20], len(ks), 'subset=', ks<=enum, sorted(ks-enum))
"
cd apps/api && python -m pytest tests/test_ux_states_contract.py -q
```

## 8. 证据路径

`docs/06_validation/evidence/EVD-V24-70/`

## 9. 允许修改

- `docs/任务规划V0.12.0/contracts/ux_states.schema.json`
- `docs/06_validation/evidence/EVD-V24-70/**`
- `docs/任务规划V0.12.0/00-README.md`（仅追加 P-153 一行）

## 10. 禁止修改

- `definitions.State.enum`（8 值一个都不许动）
- 任何 `apps/**`、`packages/**`、`scripts/**`、`.github/**`（本卡是纯契约卡）
- 任何测试文件（`apps/api/tests/**` 若红 ⇒ 停手交回，不许改测试迁就）

## 11. 依赖与阻塞

- Depends on：无
- Blocks：STEP-69、STEP-68
- 阻塞条件：`pytest tests/test_ux_states_contract.py` 有任一条红且原因不是「文本没替换干净」⇒ 停手，把红的原文贴回来。**尤其**：若 `test_frozen_draft_is_read_only_for_this_card` 因「值变了」而红（它本该只判键存在），说明判据是判值的 ⇒ 停，交回规划方，不许改测试。

## 12. 建议执行档位

sonnet。理由：语义已由规划方逐字给定，执行侧是机械替换 + 一条 pytest。

## 13. 升级条件

- 出现「需要判断某句该不该改」的情形（`03` §2 没覆盖到的第 6 处矛盾）⇒ 升级 opus，并停手交回规划方
- `test_collection_contract.py` 因本卡改动而红 ⇒ 立即停，说明改到了生成器可见面

## 14. 预估规模

小，≈0.2 人日，小于 2 小时。

## 15. 熔断

同一判据 2 轮未过 ⇒ 停手，登 P 号，不许第 3 轮。

## 16. 交接物

`EVD-V24-70/before_after.json` 必须能让一周后的人不看提交就复现「改了哪五处、原文是什么」。
