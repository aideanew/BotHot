# STEP 继承卡增量（V0.23）

> 按 `docs/任务规划-命名规则.md` §4：继承卡不重编号、不重写原卡，增量写在本文件。
> 原卡位置：`docs/任务规划V0.22.0/steps/STEP-60-聊天流式八态.md`、`STEP-62-需求判词纠真.md`、`STEP-63-发布v1.1.5.md`。
> 冲突时**本文件的增量优先**，其余字段仍读原卡。

---

## STEP-60 聊天流式八态

| 原卡字段 | 增量 |
|---|---|
| 12 依赖 | 原「依赖 59」。**新增：依赖 64（八态枚举的活体来源）、依赖 65（八态 UI 已兑现）**。理由：60 断言的是 UI 态，65 未落地时 e2e 必红；60 要读枚举，64 未落地时只能读历史版本目录 |
| 4 输出（S60.4） | 原「八态枚举改为读 `ux_states.schema.json`」。**改为**：读 `packages/contracts/schemas/ux.schema.json` 的 `$defs.State.enum`（64 的产物）；**禁止**读 `docs/任务规划V0.12.0/contracts/ux_states.schema.json`（历史版本目录，D-V23-02） |
| 5 验收（新增两条） | ① 若 `ux.schema.json` 不存在或读不到 `$defs.State.enum` ⇒ **红**（不得回退成硬编码数组）② 枚举取值集合必须等于 8 值，且与 spec 里原有数组逐值相等（防"读到了但是空的"） |
| 6 允许修改 | 原允许面不变。**新增禁止**：不得修改 `docs/任务规划V0.12.0/contracts/**`；不得修改 `apps/web/components/**`、`apps/web/app/**`（UI 归 65） |
| 10 验证命令 | 原命令不变（`@ci` 读 `e2e-real` job）。**新增 `@win`**：`node -e "const s=require('./packages/contracts/schemas/ux.schema.json'); console.log(s['$defs'].State.enum.length)"` 输出 `8` |
| 13 阻塞条件（新增） | 若 65 的 UI 文案与契约不逐字一致 ⇒ 停（e2e 会因文案断言失败，根因不在 60） |

---

## STEP-62 需求判词纠真

| 原卡字段 | 增量 |
|---|---|
| 4 输出 | 原「五处判词（005/008/NF-002/C-001/C-002）」。**扩到七处**：新增 X-1（`docs/04_engineering/roadmap.md:93` 的「启动 lifespan 自动调用待接」）与 X-2（同文件 `:114` 的「identity/chat/engine 骨架待接」中 engine 已接） |
| 5 验收（新增） | ① X-1 改后必须引 `apps/api/app/main.py:275-277` 作证据 ② X-2 改后必须区分"engine 已接（`packages/contracts/src/engine/dto.ts` 32 行）"与"identity/chat 仍缺"③ `grep -n "待接" docs/04_engineering/roadmap.md` 的剩余命中必须逐条有对应 P 号或卡号 |
| 6 允许修改 | 原允许面 + `docs/04_engineering/roadmap.md`（**仅** `:93` 与 `:114` 两行） |
| 7 禁止修改 | 原禁止面 + 不得改 `roadmap.md` 其他行（历史回填段是有出处的记录） |
| 13 阻塞条件（新增） | 若 F-005/F-008 的判词要写"已实现"而 60 的 `@ci` 读数未取到 ⇒ 停（**不得**用"代码写了"代替"跑过了"） |

---

## STEP-63 发布 v1.1.5

| 原卡字段 | 增量 |
|---|---|
| 3 目标 | 原「发 v1.1.5」。**新增本版内容清单**：① ux 域进契约链（64）② 八态 UI 五条兑现（65）③ identity/shapes 形状契约化（66）④ 真后端八态 e2e（60）⑤ 判词七处纠真（62） |
| 5 验收（新增） | ① `git diff --stat v1.1.4..HEAD` 里 `apps/api/app/**` 只出现 `contracts/ux.py`、`contracts/shapes.py` 两个文件（**证明本版没碰业务逻辑**）② `CHANGELOG.md` 的 `[v1.1.5]` 段条目数 = `git rev-list --count v1.1.4..HEAD` 减去文档提交数，且逐条对得上（AGENTS.md 记的失真教训：条数 ≠ 区间提交数，必须按区间重新对账） |
| 7 禁止修改 | 原禁止面不变。**新增**：不得移动/删除 `v1.1.4` 及更早的 tag |
| 10 验证命令 | 原命令（04 附录 B）。**新增对账**：`git rev-parse v1.1.5^{commit}`（注意 `git rev-parse v1.1.5` 给的是标签对象 sha，不是被标提交） |

---

## 三张继承卡的状态同步

本版卡表（`04` §2）里 60/62/63 的状态列与 `docs/任务规划V0.22.0/04-剩余可执行大纲体系.md` §2 的卡表
**必须同源**：V0.22.0 那张表保持"⬜ 未开"不动（历史记录），本版这张表是本版的执行视图。
两处不一致时以**本版**为准，并在 `07` 记一行说明。
