---
id: REMAINING-OUTLINE
type: plan
title: 剩余任务大纲体系（三级编号 · 原子化 · 可执行 · 每条带证据链）
status: draft-for-review
created: 2026-10-12
scope: 仅"剩余"任务；已执行卡片只列收口动作
sources: 04_planning/current-plan.md §2.3/§4/§6、05_execution/task-index.md、tasks/TASK-0{01..25}.md、_workspace/findings.md §C/§D
---

# R. 剩余任务大纲体系

## R.0 阅读规则（先读这一段，否则编号会被误读）

| 约定 | 含义 |
|---|---|
| 层级 | `R<n>` 一级=分支；`R<n>.<m>` 二级=工作流；`R<n>.<m>.<k>` 三级=**原子任务**（一次可验收的最小单元） |
| 状态标记 | 🟢 本机已可执行并已做 · 🟡 本机可做但尚未做 · 🔵 需人工/外部 · ⛔ 被裁决阻塞（给出裁决 ID） · ⚪ 本机不可证，必须交 CI/有二进制环境 |
| 证据列 | 一律 `文件:行` 或"命令 + 输出"。**没有证据的行不允许开工**，这是本大纲的硬约束 |
| 验收列 | 必须是**可复制执行的命令**或**可核对的断言**，不接受"完成后检查正确性"这类空话 |
| 原子性判据 | 三级任务必须满足：单一 owner 角色 + 单一允许路径集 + 一条能独立失败的验收命令 |

**为什么这样切**：`task-index.md:11-37` 的 25 张卡片里有 **11 张 `blocked（待裁决）`**（逐行数得：
003、006、008、009、012、013、020、022、023、024、025）。其中 **D-09 直接阻塞 3 张**
（006 依赖 D-09、012 依赖 D-09、013 依赖 D-09，见 `task-index.md:18/24/25`），
而 S1+S3 的 **7 张卡全部**直接或传递依赖 D-09
（007←006、008←007、014←012+013、015←014）⇒ **一张批准未下，占全部任务 28% 的契约线整条停摆**。
⇒ 剩余工作的瓶颈**不是编码量，是决策吞吐**。所以 R.1（决策分支）排在所有编码分支之前。

---

## R.1 一级分支总览与关键路径

| 分支 | 主题 | 卡数 | 阻塞源 | 可否与它并行 |
|---|---|---|---|---|
| R.1 | 决策吞吐（裁决 + 前置问题） | 解 11 张 | D-01…D-09 / Q-01…Q-04 | 是，**且必须优先** |
| R.2 | S0 残余收口 | 001 / 003 | 人工 / D-02 | 是 |
| R.3 | S1 错误契约链 | 006 / 007 / 008 | D-09 | 否，串行于自身 |
| R.4 | S2 访客策略 | 009 / 010 / 011 | D-01 | 是 |
| R.5 | S3 响应模型链 | 012 / 013 / 014 / 015 | D-09 | 否，串行于自身 |
| R.6 | S4 通知帧 id + 站内通知写入面 | 016 / 017 + 新 G-1 | 无 | 是，**当前唯一无阻塞可全速推进的编码分支** |
| R.7 | S5 文档残余 | 020 | D-05 | 是 |
| R.8 | S6 性能基线 | 021 | 依赖 TASK-002 | 是 |
| R.9 | S7 数据/资产处置 | 022 / 023 / 024 | D-03 / D-06 / D-07 | 是 |
| R.10 | S8 真后端 e2e | 025 | D-08（外部） | 否 |
| R.11 | 执行中新暴露的缺口任务化 | 新 026…033 | 无 | 是 |
| R.12 | 门禁基础设施补强 | 新（与 R.11 合并排期） | 无 | 是 |
| R.13 | 法务与许可 | 024 的前置 | Q-04 | 否，须先于 R.9.3 |
| R.14 | 不可本地验证项交接 | 横切 | 需 CI/人工 | 是 |

**关键路径**：S1 与 S3 **互不依赖、可并行**，两条链同为 4 节点：
`D-09 → 006 → 007 → 008`（`task-index.md:18-20`）与 `D-09 → {012,013} → 014 → 015`（`:24-27`）。
**次长**：`D-01 → 009 → 010 → 011`（4 节点，`:21-23`）。
⇒ 单点风险集中在 **D-09 一处批准**：它一未批，S1+S3 的 **7 张卡全部**闲置（其中 4 张连一行代码都不用改就能判定"做不了"）。
处置见 R.1.2.3（把否决分支也预先写成可执行卡片，使批准/否决两侧都能立刻开工）。

---

## R.2 分支 R.1：决策吞吐（把 11 个 blocked 变成可执行）

### R.1.1 产品级裁决（需人拍板，Agent 只能准备弹药）

| # | 原子任务 | 证据 | 动作 | 验收 |
|---|---|---|---|---|
| R.1.1.1 🔵 | D-01 访客策略三选一 | `current-plan.md:181,2355`；现状代码 `apps/web/src/middleware.ts` 白名单 + `e2e/auth-gate.spec.ts:10` 注释与实现相反 | 把 A/B/C 三案的**改动面清单**各自算出来（哪些路由、哪些测试要改），交人选择；**不得由 Agent 代选** | 一张三案对比表，每案列"改动文件数/新增测试数/回滚成本" |
| R.1.1.2 🔵 | D-02 端口口径 | `current-plan.md:182,2356`；`AGENTS.md:36-47` 端口表 vs `docker/.env.example:21-27`（共享底座 5435/6379） | 同上：A 案改端口表、B 案恢复栈内 PG/Redis。共同部分 TASK-002 **已完成**（`findings.md §D-1`） | 选定后 TASK-003 解除 blocked |
| R.1.1.3 🔵 | Q-01 共享底座是否仅监听本机 | `current-plan.md:2346` | 问运维；答案只影响 K-02 严重度 | 一句结论 + 来源 |

### R.1.2 架构级裁决（Agent 可给推荐，人只需签字）

| # | 原子任务 | 证据 | 推荐 | 验收 |
|---|---|---|---|---|
| R.1.2.1 🔵 | D-09 ADR-0008 契约唯一源 | `current-plan.md:189,2363`（已注"批准"）；`scripts/gen_contracts.py` 已在生成 TS | **批准**（方向与既有 `gen_contracts` 一致，仅扩大覆盖） | ADR-0008 状态改 accepted ⇒ 同时解 R.3.1 与 R.5.1/5.2 |
| R.1.2.2 🔵 | D-04 前端遗留错误码 | `current-plan.md:184,2358`；计划自身默认 B | **B 保留在 LEGACY 表**（NON_BLOCKING，不占关键路径） | 一行结论 |
| R.1.2.3 🟡 | **D-09 未批时的降级预案** | `current-plan.md:189` 已写明否决后果："S1 退化为手工同步 errors.ts + 单测比对；S3 取消" | 把降级方案也写成**可执行卡片草稿**，使批准与否都能立即开工（消除 6 跳单点） | 降级卡片草稿存在且验收命令可跑 |

### R.1.3 数据/资产级裁决（全部有前置问题，先答问题）

| # | 原子任务 | 证据 | 动作 | 验收 |
|---|---|---|---|---|
| R.1.3.1 🔵 | Q-03 生产 `bot_bindings` 是否有数据 | `current-plan.md:2348`；表定义见 alembic 迁移链（单 head `ab1005w5b`） | **不得猜测**：需运维在生产库执行一条只读 `SELECT count(*)` | 数字 + 执行环境；未答则 D-03 保持 blocked |
| R.1.3.2 🔵 | Q-04 `.project/` 许可证可否随库公开 | `current-plan.md:2349`；`findings.md §C`（MediaCrawler 非商业、firecrawl 与 wandao AGPL） | 这是**法务问题不是技术问题**⇒ 升级给决策人，附三份 LICENSE 原文位置 | 法务书面结论；未答则 D-07/TASK-024 保持 blocked |
| R.1.3.3 🔵 | D-05 / D-06 | `current-plan.md:185,186,2359,2360`；D-05 计划默认 B（归档） | 按默认提案单；D-06 取决于 HOT-005 是否立项 | 两行结论 |

---

## R.3–R.5 契约与响应链（被 D-09 串联）

### R.3 S1 错误契约

| # | 原子任务 | 依赖 | 允许路径（须写入卡片） | 验收 |
|---|---|---|---|---|
| R.3.1.1 ⛔D-09 | TASK-006：`errors.py` 登记表补 50003 + 注册一致性断言 | D-09 | `apps/api/app/core/errors.py`⚠ 属 Agent-Contract 特权区（见 `TASK-004.md` 禁止修改段） | 新增断言单测通过（需 `apps/api/.venv`，**本机无**⇒ ⚪ 交 CI） |
| R.3.2.1 ⛔←006 | TASK-007：`gen_contracts` 生成 `errors.ts` 并纳入 `--check` | TASK-006 | `scripts/gen_contracts.py`、`packages/contracts/**` | `python scripts/gen_contracts.py --check` rc=0 |
| R.3.3.1 ⛔D-04 | TASK-008：前端错误表对齐契约 + 429/413 展示态 | 007、D-04 | `apps/web/**` | `pnpm run typecheck` + 单测（⚪ 本机无 pnpm/node_modules） |

### R.5 S3 响应模型链

| # | 原子任务 | 依赖 | 关键事实 | 验收 |
|---|---|---|---|---|
| R.5.1.1 ⛔D-09 | TASK-012 bot 域 Pydantic 响应模型 | D-09 | bot 域路由当前直返 dict（`apps/api/app/api/v1/bots.py`，含 `:315` `test_push`、`:341`/`:624` `provider.push`） | OpenAPI 里该路由有 `$ref` 响应模型 |
| R.5.2.1 ⛔D-09 | TASK-013 hot 域同上 | D-09 | 同上，`hot` 域 | 同 |
| R.5.3.1 ⛔←012,013 | TASK-014 生成 `*Out` DTO | 012、013 | 复用 R.3.2.1 的同一生成器，**不要另起工具链**（复用原则） | `gen_contracts --check` 覆盖 DTO 文件 |
| R.5.4.1 ⛔←014 | TASK-015 前端改用 `*Out` 类型 | 014 | `apps/web` API 层 | typecheck 通过且无 `any` 残留（grep 判据） |

---

## R.6 分支：S4 通知帧 id（**当前唯一零阻塞的编码分支**；本轮后端半区已交付，前端半区停在授权空档）

### R.6.0 执行逻辑穿透（先读，否则 R.6.1 会改错文件）

**帧 id 为什么原本给不出**——三段证据构成一条硬链（**行号已因本轮实现而整体下移**，
故这里同时给**符号锚**；复算命令：
`grep -n "result = await provider.push(push_msg)\|await persist_web_notification(db, push_msg)\|id=msg.notification_id" apps/api/app/services/push_scheduler.py`）：
1. `push_scheduler.py:194`（原 `:187`）`result = await provider.push(push_msg)` ——
   web 渠道的 SSE 帧在**这一行之前**就已发布；
2. `push_scheduler.py:229`（原 `:222`）`if ch.channel_type == "web" and result.delivered:`
   才调 `persist_web_notification(db, push_msg)` —— **落库严格发生在投递之后**；
3. 原 `:278-289` 构造 `Notification(...)` 时**不含任何 id 字段**（现 `:289` 已是 `id=msg.notification_id or gen_uuid()`）
   ⇒ id 由 ORM 在 flush 时生成 ⇒ 帧发布那一刻，id **尚不存在**。
   ⚠ 上一版把这写成"由 DB 生成"，**不准确**：`bothot_entities.py:283` 是 **Python 侧**默认
   （`default=gen_uuid`），且迁移 `ab1005w5a_notifications.py:30` 的 `id` 列**没有 server_default**
   ⇒ 数据库根本不会替我们生成 id，"提前自铸"不是优化而是**唯一可行路径**（不是等 flush 就能读回的口径）。

**并且**：SSE 端点是**原样转发**，不生产内容——
`apps/api/app/api/v1/system.py:266` `@router.get("/notifications")`、`:259` `yield f"data: {raw}\n\n"  # 原样转发 web provider 发布的 JSON`
⇒ **改 `system.py` 加不上 id**；id 必须在**发布侧**注入。

**结论（这是 TASK-016 的真实改动面，比卡片描述更窄也更深）**：
id 需在 `:187` **之前**用 Python 生成，写入 `PushMessage`（可能需新增字段），
由 web provider 随帧发布，再由 `:279` 以 `Notification(id=…)` **显式主键**落库。

| # | 原子任务 | 证据 | 动作 | 验收 |
|---|---|---|---|---|
| R.6.1.0 🟢 | 确认 `PushMessage` 是否已有可承载 id 的字段（决定是否要改数据类） | `base.py:14-32`（`@dataclass(frozen=True)`，原 9 个字段、现 10 个，**原本无**可承载 id 的字段） | 已核查：必须加字段；已加 `notification_id: str = ""`（`base.py:35`，置于末位；全部调用点用关键字传参 ⇒ 零位置参数破坏） | ✅ 字段清单已出；providers/** 属 TASK-016 **允许修改** 路径 ⇒ 授权成立 |
| R.6.1.1 🟡 | 投递前生成 id 并随帧发布 | 上列 `:194`/`:229`/`:289`/`system.py:259` | **已实现**：`push_scheduler.py:179` 在构造 `PushMessage` 前 `gen_uuid() if ch.channel_type == "web" else ""`；`web.py:40-45` 仅在非空时写 `notification["id"]`；`persist_web_notification` 以 `:289` 的 `id=msg.notification_id or gen_uuid()` 落同一值 | 单测 `apps/api/tests/test_notification_frame_id.py` **三层 6 例**：载荷 2（fake Redis）+ **管道 2（真跑 `_execute_task`，fake session/provider）** + 落库 2（连库）。
  反证（静态）：删 `push_scheduler.py:184` 的 `notification_id=notification_id` ⇒ 管道层 `assert frame_id` 必红。
  ⚠ 第一版 5 例里 3 例**无鉴别力**（外部复核指出），已重做——**本机无 `.venv` 不可跑** ⇒ ⚪ 交 CI；本机仅 `py_compile` 通过 |
| R.6.1.2 🔵 | 重投幂等：同帧重投不得产生第二条落库 | 每次重试都重新进入 `_execute_task` ⇒ **每轮自铸新 id**（`:193-211` 退避路径）；显式主键后不存在撞键 | 待裁决的**设计选择**（不是遗漏）：① 以 `(task.id, 应投递时刻)` 派生确定性 uuid5 ⇒ 重投同 id、天然幂等；② 维持每轮新 id ⇒ "发布成功但提交前崩溃"这一 at-most-once 窗口会出现两条内容相同、id 不同的行 | 选 ① 后：重放同事件 ⇒ 落库 1 行；选 ② 需同时改前端**保留**内容窗口去重（见下方 R.6.2 注） |

### R.6.1.3 ⛔ 新发现的硬停：前端拿不到帧 id（**TASK-017 在自己的授权面内做不到**）

`apps/web/lib/api/notifications.ts:61-71` 的 `parseNotificationFrame` 是**逐字段重建**
`AppNotification`（只取 title/message/url/space_id/doc_id），**未识别的键被丢弃** ⇒
后端即便把 `id` 发出去，组件也**永远看不见**。而 `AppNotification` 的声明也在同一文件（`:20`）。
`TASK-017.md` 的**允许修改**只有 `NotificationBell.tsx` 与它的测试，**禁止修改**列的是
`apps/api/**`、`packages/**` ⇒ `apps/web/lib/api/notifications.ts` 落在"既未授权也未禁止"的空档。

- 处置：**不改该文件**（改它就是重犯我本轮已自纠的那类越界——"主题正当 ≠ 路径授权"）。
- 需一次裁决：给 TASK-017 追加授权 `apps/web/lib/api/notifications.ts`（改动量 = 2 行：
  `AppNotification` 增 `id?: string`；重建时透传 `typeof rec.id === "string" ? rec.id : undefined`）。
- 裁决前的净效果：后端改动**加性且零回归**（旧前端忽略多余键），S4 分支停在"帧已带 id、前端未消费"。
- ⚠ 与 R.6.1.2 的耦合：若最终选 ②（每轮新 id），前端去重必须**叠加**而不是**替换**
  现有 5s 内容窗口（`NotificationBell.tsx:136-152`），否则 at-most-once 崩溃窗口的重复帧
  会从"被内容去重合并"变成"两条都显示"——**这是一次真实的功能退化**，不是理论风险。

### R.6.2 前端：按帧 id 去重

| # | 原子任务 | 证据 | 动作 | 验收 |
|---|---|---|---|---|
| R.6.2.1 ⛔ | `NotificationBell` 用帧 id 去重 | 卡片 `TASK-017.md`；**帧 id 在 `notifications.ts:61-71` 被丢弃**（见 R.6.1.3） | **暂停**：先裁授权（2 行透传），否则组件侧写出来的是死代码 | 组件单测：同 id 两帧 ⇒ 列表 1 条（⚪ 本机无 node_modules） |
| R.6.2.2 ⛔ | 断线重连后不重复计数 | 同上 | 同上阻塞 | 单测覆盖"重连补投同帧" |

### R.6.3 G-1：站内通知**写入面不全**（执行中新发现，必须进本轮）

| # | 原子任务 | 证据 | 动作 | 验收 |
|---|---|---|---|---|
| R.6.3.1 🟡 | 直发路径补写站内通知（或显式声明"直发不产生站内通知"） | `findings.md §C` G-1：`persist_web_notification` **仅 1 个调用点** `push_scheduler.py:229`；而 `bots.py:341`、`bots.py:624` 直接 `provider.push` 绕过落库 | 二选一：①两直发点也落库；②在产品口径上明确"手工测试/立即推送不进气泡"，并写进 REQ-F-001 | grep `persist_web_notification` 调用点数 = 3（①）或文档出现该边界声明（②）；**已同步更新** `product-requirements.md` REQ-F-001 的 ⚠ 注记 |

---

## R.7 / R.8 / R.9 / R.10 其余分支（各只 1–2 个原子任务）

### R.7.1.1 ⛔D-05 — TASK-020 `.docs/` 遗留项迁移或归档

**规模已实测纠正**（卡片与计划都低估）：
| 声称 | 实测 | 证据 |
|---|---|---|
| 计划 §2.3 X-16 与卡片输入段写"6 项" | **14 个映射行** | `grep -n '待迁移' docs/00_governance/doc-migration-map.md` ⇒ 行 43/44/45/47/53/54/75/76/77/79/85/99/105/106 共 14 行 |
| — | `grep -c` 返回 **15** 而非 14 | 第 15 处是图例行 `doc-migration-map.md:115`（`🔲 待迁移 \| 14`）自己含该词 |
| 文件级 | **≈21 个文件** | `:44` 注"（3 个文件）"、`:85` 注"(6 个 LLM 分析结果)"；其余 12 行按 1 文件计 ⇒ 12+3+6=21，**需逐项清点确认**（R.7.1.2） |

⚠ **验收命令的隐含陷阱**：卡片验收是 `grep -c '待迁移' == 0`，而**图例行 `:115` 自己也含这个词**
⇒ 即便 14 项全部迁移/归档完毕，只要图例还在，`grep -c` 就**永远 ≥1**、验收永远失败。
必须在 R.7.1.3 明确：改图例措辞（或把验收命令改为按表格行计数），否则这是一条**结构上不可满足的验收**。
（与 D-1b/D-1c 同类：卡片验收未与自身数据来源交叉校验。）

- R.7.1.2 🟡：先出 14 行 × 处置建议清单（迁 / 归档 / 删），不动文件。
- R.7.1.3 🟡：修正验收命令与图例的自指冲突（属 `docs/00_governance/**`，Agent-Doc 可改）。

### R.8.1.1 🟡 — TASK-021 性能基线脚本与首测
依赖 TASK-002（已完成）。**约束**：用户要求"不实际启动服务"⇒ 本卡片只能**写脚本 + 静态校验脚本可运行性**（`bash -n`），**首测必须交有栈环境执行**（⚪）。这一点要写进验收，否则会出现"为了完成卡片而偷偷起服务"的违规动机。

### R.9.x — 数据/资产处置（全部 ⛔）
| # | 卡片 | 阻塞 | 备注 |
|---|---|---|---|
| R.9.1.1 | TASK-022 `BotBinding` 死表 | D-03 ← Q-03 | 若判删：占用迁移号 `ab1006w6a`，须与单 head `ab1005w5b` 衔接 |
| R.9.2.1 | TASK-023 `embedding.py` | D-06 ← HOT-005 | 删/留皆可，勿默认 |
| R.9.3.1 | TASK-024 `.project/` | D-07 ← **Q-04 法务** | 与 `findings.md` G-8 耦合：扫描域 573/4958 的正当性在此一并裁 |

### R.10.1.1 ⛔D-08（外部）— TASK-025 real-backend e2e 转阻塞门禁
外部依赖主平台 OIDC 白名单/测试账号/真实文章 URL（`current-plan.md:188`）。**本机证据不足**：`apps/web/e2e/*.spec.ts` 5 个文件存在，但 `e2e/auth-gate.spec.ts:10` 注释与实际保护策略相反 ⇒ 归 X-14（属 TASK-010，同样被 D-01 卡）。

---

## R.11 / R.12 新缺口任务化（本轮执行期产出，原计划没有）

| 新卡片（建议号） | 缺口 | 证据（实测） | 允许路径（建议） | 优先级 |
|---|---|---|---|---|
| **G-5 → TASK-026** | `.env.example` 无模板形状守卫，**已证其盲** | 注入真字面口令 ⇒ worktree 命中 46→47 但**告警 0 / rc=0**（`findings.md §D-2`） | `docker/.env.example`（⚠ 现仅 TASK-002 授权）、`scripts/`、`ci.yml` | **MUST** |
| **G-6 → TASK-027** | `check_docs_consistency.py` 只认 `.py/.ts/.tsx/.mjs` 且只扫 `✅` 区块 ⇒ 指向 `Makefile`/`.yml`/`Dockerfile`/`.toml` 的假 `file:line` 检不出 | `scripts/check_docs_consistency.py:33,38,60`；实测 `Makefile:999999` 不被计数（21 而非 22） | `scripts/check_docs_consistency.py`（TASK-018 卡片禁改，故须新卡） | MUST |
| **G-7 → TASK-028** | 守卫自述证据**必须可重算**，禁止快照数字/文件内行号 | `.gitleaks.toml` 行号引用实测 `162→167` 漂移；描述计数的句子自己改变计数（46→47） | `.gitleaks.toml`、`_workspace/` | SHOULD |
| **G-9 → TASK-029** | **无"改动是否越出卡片授权路径"的机械门禁**——我自己越界一次 | `TASK-004.md`/`TASK-019.md` 禁止修改段均含 `docker/**`；`docker/.env.example` 仅 TASK-002 授权；我改了它 ⇒ 自纠撤销 | `scripts/preflight.sh` | **MUST**（纪律类） |
| **G-10 → TASK-030** | 卡片"目标/验收/允许路径"三段未交叉校验，已见两例不自洽 | D-1b：TASK-002 禁改 `ci.yml` 却以 CI 绿为验收；D-1c：TASK-019 验收只列 X-01…X-12，但 `current-plan.md:115` 把 X-15 也指派给它 | `docs/任务规划V0.1.0/**` | MUST |
| **G-11 → TASK-031** | `(^|/)` 锚定不挡嵌套同名路径 ⇒ 豁免面比注释声称的宽 | `allowed()` 用 `re.search`；`x/docker/.env.example` 等同名嵌套同样被豁免 | `.gitleaks.toml` | SHOULD（需先确认 gitleaks 给出的 path 是否仓库根相对，**本机不可证**） |
| **G-12 → TASK-032** | gitleaks **配置加载自检** fixture（区分四种静默结局） | v8 走 koanf、未知键被忽略⇒ 复数键若不匹配是**静默失效**（推断，本机不可证）；已把 bad/ok 双 fixture 写进 footer 待实跑 | `.github/workflows/security.yml` | MUST |
| **G-13 → TASK-033** | `status` 字段**双源不一致**：卡片 frontmatter `ready` vs 索引 `waiting` | `grep ^status tasks/*.md`（007/010/011/014/015/021 = ready）对照 `task-index.md:19-33`（同 6 张 = waiting） | 二者择一为权威 + 生成器 | SHOULD |
| **G-14 → TASK-034** | 守卫**形状盲区**：规则只认 `协议://账号:口令@` 邻接形态，**裸口令词看不见** ⇒ "0 告警"被误用为"无凭据" | 我在 `.gitleaks.toml` 与 `findings.md` 三处逐字写出了 public 仓库历史里的真实 PG 口令，而回放全程 0 告警（`findings.md §D-8`）；违反 `current-plan.md:679` 已定口径 | `.gitleaks.toml`（已改为指针式描述）+ **仓库外**检查（CI secret 注入 / 人工比对） | **MUST** |
| **G-15 → TASK-035** | **同步前置**：TASK-001 口令轮换未确认 ⇒ 任何推送都在扩大同一凭据暴露面 | `TASK-001.md:21/33/44` 要求人工 `ALTER ROLE` + 认证失败验证；`adr-0010:15` 记仓库为 public；`01f6892` 起该串已在历史（`git log -S` 实证） | 无（人工） | **MUST，且排在推送之前** |
| **G-16 → TASK-036** | **25 张卡全部悬空引用**：frontmatter `plan: docs/04_planning/current-plan.md` 指向不存在的文件 | `grep -h '^plan:' tasks/*.md \| sort \| uniq -c` ⇒ **25 次同一路径**（实测）；`ls docs/04_planning` 只有空 `releases/`；真实实体在 `docs/任务规划V0.1.0/04_planning/current-plan.md` | `tasks/*.md` 的 `plan:` 或把计划发布到所指路径（**二选一，需人裁决**） | MUST（否则每张卡的"依据"都不可追溯） |
| **G-17 → TASK-037** | **验收命令普遍无鉴别力**：卡片命令在"什么都没做"的今天就能通过 ⇒ 照命令打勾会把未做判成已做 | TASK-011 的 `python scripts/check_docs_consistency.py` **本轮实测 rc=0**，而 X-13 矛盾句仍活在 `CHANGELOG.md:29` vs `:33-34`；cdc 只校验 backlog 里 24 个 `path:line` 存在性，与该矛盾无关（G-6 的窄口径是其成因之一） | `docs/任务规划V0.1.0/05_execution/tasks/*.md`（给每张卡补**反证**命令：改动前必须 rc≠0） | **MUST**（这是"完整执行"判据本身） |
| **G-18 → TASK-038** | **修漂移的动作会造出新漂移**，而验收命令抓不到自己新写的那段 | 我在 TASK-019 修 X-15 时把 `project-map.md:73-74` 写成"有 `rotate-keys-plan.md` 与 `release-checklist.md`"——`find docs/07_release -type f` 实证只有 `key-rotation-sop.md` + 两个 `.gitkeep`（**本轮已改为实测口径**） | 文档断言需**可执行复算**（把"存在性"写成命令，而不是形容词） | MUST |
| **G-19 → TASK-039** | **帧 id 去重的前提对两条直投路径不成立**：`persist_web_notification` 只有调度器一个调用点 | `grep -rn persist_web_notification apps/api/` ⇒ 生产调用点仅 `push_scheduler.py:229`（原 `:222`，本轮下移）；`bots.py:341`（测试推送）与 `:624`（run-now）都直达 `provider.push()` 而不落库 ⇒ 其 SSE 帧永远无对应表行 | `apps/api/app/api/v1/bots.py`、`app/services/push_scheduler.py` | **MUST，且是 TASK-016 开工前的裁决**（要么纳入落库，要么明确去重只对 Cron/事件成立） |
| **G-21 → TASK-042** | **调度侧 web 通知全部落为广播** ⇒ 任何登录用户可见他人定时通知 | 实测：`push_scheduler.py:181-191` 构造 `PushMessage` **不设 `external_user_id`**（对照 `bots.py:332` 传 `ch.user_id`）⇒ `web.py` 频道恒取 `broadcast` 分支、`persist_web_notification:290-291` 恒 `is_broadcast=True, sub=“”` | `apps/api/app/services/push_scheduler.py`（需先裁决「调度是否本意广播」） | **MUST（数据可见性，优先级高于 S4 收口）** |
| **G-22 → TASK-043** | **孤儿帧窗口**：帧在 `:194` 外发、事务在 `:247` 提交、落库走 savepoint ⇒ 提交失败时“有帧无行”，下一轮换 id | 复算：`grep -n "result = await provider.push\|await db.commit\|begin_nested" apps/api/app/services/push_scheduler.py` ⇒ 194 / 247 / 286 | 需裁决：①发布挂到提交之后（改投递语义）②接受并写进文档（前端保留内容窗口去重兜底） | MUST（裁决项，非编码项） |
| **G-20 → TASK-040** | 卡片的**允许修改/禁止修改**两段之间存在**未定义空档**：既没授权也没禁止的路径，默认语义是什么？没人写过 | TASK-017 允许 = `NotificationBell.tsx` + 其测试，禁止 = `apps/api/**`、`packages/**`，而它**必须**改的 `apps/web/lib/api/notifications.ts:61-71` 两段都没列 ⇒ 该卡在自己的授权面内**结构性做不到**（R.6.1.3） | `docs/任务规划V0.1.0/05_execution/tasks/*.md` 卡模板 + 一次全量交叉核查 | **MUST**（建议默认语义定为"**未列出即禁止**"，并把这条写进模板与 `collaboration-discipline.md`） |

> R.12 排期建议：G-5/G-6/G-9/G-12 四项是**门禁自身的有效性**问题——门禁不可信时，其余卡片"验收通过"都打折。
> 故建议 R.12 与 R.6 并行、**先于** R.3/R.5 的大规模编码。

---

## R.14 不可本地验证清单（诚实边界，禁止用本机结论替代）

| 项 | 为何本机不可证 | 必须在哪跑 |
|---|---|---|
| `gitleaks detect` 真二进制结论 | 本机无 gitleaks；Python `re` 与 Go **RE2 非同一引擎**（`\s`/`\w` 域不同，已实证 `\x0b` 分歧） | CI / 装有 8.21.2 的机器，四条命令 + 双 fixture（`.gitleaks.toml` footer） |
| `rules.allowlists` 复数键是否被识别 | 需二进制 | 同上（R.14 首条） |
| 后端 `ruff/mypy/alembic upgrade head/pytest` | 本机无 `apps/api/.venv`，且用户禁止装依赖 | CI 或隔离环境（PG 用 **5547**，绝不碰 5433） |
| 前端 `pnpm typecheck/test:unit`、`e2e` | 本机无 pnpm/node_modules；且不得起服务 | CI |
| `docker compose … config` / `smoke.sh` / TASK-005 上下文变小 | 本机无 docker | CI（`compose.ci.yml` 那条 `-f` 配对问题见 `progress.md`） |

**本轮已交付但未收口的卡片**：TASK-002、TASK-004（裁剪 3→1 已实测）、TASK-005、TASK-018、TASK-019
（两条验收命令实测 rc=0 / rc=1）。

**第二轮验证子智能体（25 卡真值表）已回，结论按证据采纳/驳回如下**（全量对照见 `findings.md §D-9`）：
- 采纳：`DONE-LOCAL 1（019）｜PARTIAL 4（002/004/005/018）｜NOT-EXECUTED 2（016/017）｜BLOCKED 18`；
  **0 个 `EVD-xxx` 证据目录被建立**（`ls docs/06_validation/evidence/` 仅 `channeltest-20260929`）。
- 采纳：TASK-004 验收项 1 与项 3 在同一份入库配置下**互斥**（`security.yml:99 fetch-depth: 0` 是全历史扫描）
  ⇒ 已按意图改写为"能力证明（反事实配置）+ 共存证明（入库配置）"两条（`TASK-004.md` 验收段）。
- 采纳：`Notification.id` 是 **Python 侧默认**（`bothot_entities.py:283 default=gen_uuid`），
  且迁移 DDL 未给 server_default（`ab1005w5a_notifications.py:30`）⇒ id 必须在发布前由 Python 生成，
  但**不必**重排 persist/publish 顺序（R.6.0 的设计成立，理由更正）。
- 采纳：`preflight.sh:182` 双引号内未转义反引号 ⇒ `file:line` 被命令替换（**本轮已修**）。
- 采纳：`project-map.md:73-74` 两处虚假文件名（**本轮已修**，见 G-18）。
- 更正其表述：TASK-020 判据不是"结构上不可能满足"，而是**判据自指、与目标不同构**
  （允许路径含该文件本身，改统计行措辞即可到 0）；`grep -c 待迁移` 实测 **15** = 14 个状态格 + 图例行 `:115`，
  卡片标题与 `current-plan.md:116` 写"6 项"才是错的那个（实际 14 项）。

---

## R.15 执行顺序建议（拓扑排序后，含并行度）

```
第 0 批（今天，零阻塞，可全并行）
  R.6.1.1  R.6.1.2  R.6.2.1  R.6.2.2  R.6.3.1        ← 唯一无阻塞编码分支
  R.12 的 G-5/G-6/G-9 卡片起草                        ← 门禁自身有效性
  R.1.1.* / R.1.2.* / R.1.3.* 的"弹药准备"            ← 只准备，不代拍板
  R.14 全部（把不可证项打包成 CI 交接清单）
第 1 批（只需签字，快）
  D-09 → R.3.1.1 → R.3.2.1 ；D-04 → R.3.3.1
  D-01 → R.4.1.1 → R.4.2.1 → R.4.3.1（含 X-14）
第 2 批（依赖第 1 批产物）
  D-09 → R.5.1.1 / R.5.2.1 → R.5.3.1 → R.5.4.1
第 3 批（依赖外部事实）
  Q-03 → D-03 → R.9.1.1 ；HOT-005 → D-06 → R.9.2.1 ；Q-04 → D-07 → R.9.3.1（含 G-8 扫描域裁决）
  D-02 → R.2 的 TASK-003 ；D-05 → R.7.1.1（先做 14 项清点）
  D-08 → R.10.1.1 ；TASK-001 人工轮换（S0 唯一硬前置，未确认前 Security 门禁的"已轮换"结论不成立）
```

**性能/吞吐视角**：第 0 批把"能做的"与"等决定的"彻底分离，使 Agent 不因裁决空转而停工；
`R.1.2.3` 的降级草稿把 D-09 的 6 跳关键路径压成 2 跳。这是本大纲里唯一的"排期提速"手段，
其余瓶颈都在人侧，不由代码解决。

---

## R.16 与 GitHub 同步的前置条件（用户新增要求："全部完成后…保证双端一致"）

### R.16.0 当前真实状态（实测，非推断）

| 事实 | 证据 |
|---|---|
| `main` 与 `origin/main` **同一个 commit**，ahead=0 / behind=0 | `git rev-parse HEAD` = `git rev-parse origin/main` = `60e5723…`；`git rev-list --left-right --count origin/main...HEAD` → `0  0` |
| **本轮所有改动都未提交**（14 改 + 2 未跟踪） | `git status --porcelain` → 13 行 ` M` + `?? .gitleaks.toml` + `?? docs/任务规划V0.1.0/` |
| **整个计划目录（42 个文件）是未跟踪的** | `git ls-files docs/任务规划V0.1.0 \| wc -l` → **0**；`find … -type f \| wc -l` → **42** |
| 远端是干净 HTTPS + 仓库级代理 | `git config --get remote.origin.url` / `--get http.proxy`（`http://127.0.0.1:10808`） |
| 仓库为 **public** | `adr-0010-externalize-connection-strings.md:15` 自述"仓库为 public" |

⇒ **"双端一致"此刻平凡成立（都是 60e5723），所以它不是现状，而是一个待执行的意图**：
要么"把本轮成果推上去"，要么"什么都不推、保持对齐"。两者互斥，必须先选。

### R.16.1 三种"一致"及其各自的硬前置

| 口径 | 含义 | 前置（全部满足才可做） |
|---|---|---|
| **A. 提交并推送** | 本轮 14 处改动 + `.gitleaks.toml` + 计划目录进 `origin/main` | ① **TASK-001 轮换确认**（G-15，未确认前推送＝在 public 仓库扩大同一凭据的暴露面）；② 口令字面量复扫为 0（守卫看不见裸口令 ⇒ 必须**库外取值** `grep -rnF "$PW"`，`$PW` 不进仓库）；③ `_workspace/` 里 `*.local.toml`/`__pycache__` 仍被忽略；④ 逐路径 `git add`，禁 `-A`/`.`；⑤ **人对"把内部安全审计写进 public 仓库"这一披露行为签字** |
| **B. 只提交、不推送** | 本地形成可审的 commit，远端不动 | ①②③④ 同上，⑤ 可缓（披露发生在推送那一步） |
| **C. 不提交、保持 0/0** | 维持现状，把工作树当未收口的草稿 | 无。代价：卡片验收里"合并后 0 告警""CI 绿"这类项**物理上无法判定**（本轮已因此只能给近似值） |

### R.16.2 为什么"全部完成后"这个条件目前不成立

`v0.1.0 计划已完整执行` 为**假**，证据（`findings.md §D-9` + 25 卡真值表）：
- 只有 5 张卡在工作树留下改动，且**全部未提交**；
- 18 张为 BLOCKED，其中 **9 张卡在人工裁决**（D-01…D-09）上，Agent 无权代拍；
- 2 张（016/017）零阻塞却**尚未开工**；
- 1 张（001）是人工运维，其"已轮换"结论至今无证据；
- **0 个 `EVD-xxx` 证据目录** ⇒ 卡片自设的证据路径全部缺失；
- R.14 那批项**只能在 CI 证**（gitleaks 二进制 / ruff / mypy / pytest / pnpm / docker 本机皆无）。

⇒ 按用户自己的限定词，同步动作**不应当前执行**。若要把条件放宽成"就现在这 5 张卡推送"，
那是**新的授权**，需要明确指令；我不会把"上次同意过推送"当永久许可。

**本轮为"推送前"额外备好的东西**（降低一旦获批时的返工概率，不构成推送许可）：
`docs/06_validation/evidence/EVD-002|004|005|016|018|019/README.md` 六份证据包，
每份分"本机已实测（命令 + 原样输出）"与"⚪ ci-only（要在 CI 跑的那条）"两栏。
其余 19 张卡仍无 EVD，因为它们的验收项全部落在 ci-only 或人工裁决侧。

### R.16.3 若获批，推送前的最小检查序列（可复制，不含任何口令字面量）

```bash
# 1) 凭据：守卫判据 + 形状断言 + 库外值比对（$PW 由运维工单在本机 shell 里赋值，绝不入库）
#    ⚠ 形状断言**必须带 pathspec**（照 TASK-002 卡片原样）：不带 scopes 时，
#    本文件/HTML 里"这条正则本身的文字"会自匹配 ⇒ 断言永假（同一类"描述改变被描述物"）。
git grep -nE 'bothot_rw:[^<>@[:space:]]+@' -- docker apps scripts packages .github ; test $? -eq 1
grep -rnF "$PW" . --exclude-dir=.git ; test $? -eq 1
python docs/任务规划V0.1.0/_workspace/gitleaks_replay.py tracked   # 期望：告警 0
python docs/任务规划V0.1.0/_workspace/gitleaks_replay.py worktree  # 期望：告警 0（权威档，含未跟踪）
python docs/任务规划V0.1.0/_workspace/gitleaks_replay.py history   # 期望：告警 0
# 2) 文档一致性 + 未转义反引号类缺陷
python scripts/check_docs_consistency.py ; bash scripts/preflight.sh docs
# 3) 只加具体路径（禁 -A/.），逐条看暂存区里有什么
git add <逐个路径> ; git diff --cached --stat ; git diff --cached --name-only
# 4) 代理与远端复核（确认 URL 内无 token）
git remote -v ; git config --get http.proxy
```

其余瓶颈都在人侧，不由代码解决。

## R.16.4 同步已于 2026-10-12 执行（口径 A：提交并推送）

| 项 | 实测 |
|---|---|
| 提交范围 | 起点 `60e5723`（同步前 `origin/main`）⇒ 按卡片分组提交（S0 安全 / 守卫 / 构建 / 门禁 / 文档漂移 / S4 编码 / 计划入库 / 证据重算 / 同步记录） |
| 双端一致判据 | **判据而非快照**：`git fetch origin && git rev-list --left-right --count origin/main...HEAD` → `0	0`，且 `git ls-remote origin refs/heads/main` 与 `git rev-parse HEAD` 同值。**本节不写死哈希**——写死即自证过时（见下方"递归注记"）。 |
| 推送方式 | 每轮均先 `git fetch` 确认远端未移动 ⇒ **fast-forward，无 force**；未碰 `-u/--force-with-lease` |
| 提交前门禁 | 三档告警 0；`grep -c "^+.*口令值"` = 0（口令仅以 `-` 删除行出现在摘除明文的提交里，属既有历史内容）；暂存区无 `.pyc`/`__pycache__`/`*.local.toml`；无 token 串、无本机用户路径 |
| 作者标识 | 本机 `user.name/user.email` 为空 ⇒ 按仓库既有作者 `CodingHeader <coderheader@github.com>` 以**命令级 env 覆盖**提交，**未写入任何 git config** |

**推送后仍未闭合的两件事（不属"一致"判据，但影响真实安全状态）**：
1. **TASK-001 口令轮换至今无证据**——历史里那条凭据是否失效未知，仓库为 public，
   且现在多了一个"这里曾有条凭据"的公开审计线索 ⇒ 轮换是唯一实质处置，需人工执行。
2. **本轮提交的验收项大多只能在 CI 判**（见 R.14 与 6 份 EVD 的 ⚪ ci-only 栏）：
   gitleaks 真二进制四条命令 + 双 fixture、`docker compose config` 两条断言、
   `pytest` 全链（含新增 `test_notification_frame_id.py` 三层 6 例）、`pnpm` 前端链、`actionlint`。
   **"双端一致"不等于"CI 绿"**——本机物理上给不出后者的结论。

**递归注记（G-18 的实例，就地记录以免重犯）**：本节原以"8 个提交 + 哈希 `6b50f6e`"作为一致证据，
而"记录这次同步"本身要求第 9 个提交，推送后该行即刻过时 ⇒ **一致判据被自己的记录动作破坏**。
处置：把证据从**快照**（哈希/计数）换成**可重算命令**（上表"双端一致判据"行），
本节因此对"之后又加了几个提交"免疫。代价是本节不再自带具体哈希，
需现场执行判据命令才能取值——这是"文档会过时"这一物理约束下唯一稳定形态。
