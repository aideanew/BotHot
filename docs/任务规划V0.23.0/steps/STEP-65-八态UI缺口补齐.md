# STEP-65 八态 UI 缺口补齐（P-136 / P-137 / P-138）

> 基线 main@04d50f8｜状态：✅ 已交付（U1 / U2 / U4 / U5 落地——U2 含契约那句的后半段「不得显示为「无通知」」，做法是 `unavailable` 时不再渲那条空态标签；**U3 半落地**：两支原字整句精确落地，但「+ 最近更新时间」缺后端字段（S65.0 探针②现读 `hot.py` 只有 `created_at` ⇒ 按 08 §3.1 走降级版、不用 `new Date()` 伪造、backlog 登记 HOT-006），「分别埋点」那一半不在允许面内。空态按复核结论做成**四档**（feed 失败 / topics 失败两档不下结论），这是本卡对 08 §1.2.3.2 的唯一实质偏离；两处面外笔（`r061-sse-ask.spec.ts`、`we-notifications.spec.ts`）与六条待决登台账 P-143；先红、两次变异牙齿证明、逐字对照与 e2e 穷举 grep 全在 `EVD-V23-65/s65_readings.md`。**第 2 轮（2026-10-28，@ci 抓到本卡一处真回归）**：`CI run 40638671189` 的 `frontend` job 在步 `E2E (mock UI)` 红——`e2e/trunk.spec.ts:122 › ⑥ 错误态 + 重试` 断言 `getByText('机器人服务异常，请稍后重试')` 已不可达（U5 把 30002/50002 分流到契约降级原字），而对照头 `6da2a0c` 的 frontend 是 success ⇒ 归本卡。那份「逐串穷举」的**导出方向错了**：它按「我新写的文案」列 11 条，没按「哪条既有输出因新分支而整条消失」列，所以零命中是真读数、结论却错。处置 = 用户 2026-10-28 授权的一处面外笔（`apps/web/e2e/**` 在第 7 格里是**明列禁止面**）：只把 `:131`/`:135` 两句期望换成契约降级原字（连 `:127` 那句不再真的注释共 3 行），**产品字节零改动**——不写成包含旧句的长句去迁就断言。本机先红复现（`1 failed / 27 passed / 3 did not run`）与复绿同集复算（`31 passed / 11 skipped`＝42 条，含 ⑦⑧⑨ 第一次真跑）三段读数在 `s65_12_e2e_mock_regression.txt`，§8 那句「低风险」按不回改原文的口径在 §11 立订正段；规则缺口登 **P-145**）｜裁决 D-V23-01、D-V23-06、D-V23-07｜切片 S-UX-UI｜归属：执行助手（依 D-V23-07 自规划方改派，UI）

| 字段 | 内容 |
|---|---|
| 1 归属 | 执行助手（opus 档；依 D-V23-07 自规划方改派）｜切片 S-UX-UI｜原子步与判据见 `08-阶段A执行细则.md` §3，冲突以 08 为准 |
| 2 来源 | `ux_states` 冻结稿 `x-core-views` 五条未兑现项：U1（NotificationBell `offstate`）、U2（NotificationBell `degraded` 文案）、U3（/hot `empty`）、U4（/hot `success` 0 值）、U5（/chat `degraded`）⇒ `01` §3；P-136/137/138 |
| 3 目标 | 上述五条**逐条**在 DOM 上可观测且与契约文案逐字对齐；四个新用例先红后绿 |
| 4 输出 | ① `apps/web/tests/notification-offstate.spec.tsx`（新增）；② `apps/web/tests/hot-zero-score.spec.tsx`（新增）；③ `apps/web/tests/hot-empty-states.spec.tsx`（新增）；④ `apps/web/tests/ask-sse-degraded.spec.ts`（新增）；⑤ `apps/web/components/NotificationBell.tsx`（演示态声明 + 降级文案）；⑥ `apps/web/app/hot/page.tsx`（0 值分支 + 空态拆两支）；⑦ `apps/web/components/chat/useSseAsk.ts`（30002/50002 分流 + 慢响应提示）；⑧ 四红四绿原文入证 |
| 5 验收 | ① 四用例在**未改产品代码前**全红，原文入证 ② 改后四用例全绿 ③ 文案与契约**逐字**一致：「演示数据，未连接实时通道」「实时推送暂不可用，历史仍可查」「待评分」「响应较慢」 ④ `hot_score: 0` 时 DOM 中**不出现** `🔥 0.0` ⑤ `pnpm exec vitest run tests/ask-sse.spec.ts tests/r061-sse-ask.spec.ts tests/mock-default.spec.ts` 不回归 ⑥ `pnpm exec tsc --noEmit` rc 0 ⑦ `git diff --stat` 在 `apps/web/lib/api/ask.ts` 上为空（不改码位映射） |
| 6 允许修改 | `apps/web/components/NotificationBell.tsx`、`apps/web/lib/api/notifications.ts`（仅补可观测信号，不改 mock 短路本身）、`apps/web/app/hot/page.tsx`、`apps/web/components/chat/**`、`apps/web/tests/{notification-offstate,hot-zero-score,hot-empty-states}.spec.tsx`、`apps/web/tests/ask-sse-degraded.spec.ts` |
| 7 禁止修改 | `apps/api/app/**`（后端零改动）；`apps/web/lib/api/ask.ts`；`packages/contracts/**`；`.github/workflows/**`（D-V23-06）；`apps/web/e2e/**`（归 60） |
| 8 规模/档位 | ≈1 人日｜opus（UI 设计 + 流式状态机分支，用户点名的高难项） |
| 9 熔断 | 同判据 2 次 FAIL ⇒ 停手写 P 号（从 P-140）交回；若 S65.0 读到 `/hot/feed` 无更新时间字段 ⇒ M4 降级为"只拆两态文案"，**不得伪造 now()**；若 `/spaces` 的 degraded 判定为"已落地" ⇒ 该子项不做，卡面记一行"已落地，无需改" |
| 10 验证命令 | `@win`：`cd apps/web && pnpm exec vitest run tests/notification-offstate.spec.tsx tests/hot-zero-score.spec.tsx tests/hot-empty-states.spec.tsx tests/ask-sse-degraded.spec.ts` → `pnpm exec vitest run tests/ask-sse.spec.ts tests/r061-sse-ask.spec.ts tests/mock-default.spec.ts` → `pnpm exec tsc --noEmit`；`@ci`：`frontend` job 的 vitest 步绿 |
| 11 证据 | `docs/06_validation/evidence/EVD-V23-65/`（四红四绿原文、文案↔契约逐字对照表 5 行、S65.0 两项探针读数） |
| 12 依赖 | 64（枚举类型；若 64 走方案 B 则 import 常量模块）｜Blocks：60 |
| 13 阻塞条件 | ① 契约文案本身有歧义（例如"最近更新时间"取哪个字段）⇒ 停，交回规划方定，不自行解释；② 为让用例绿而需要改后端响应 ⇒ 停（本卡后端零改动是硬约束） |
| 14 升级条件 | 需要改 SSE 协议（新增帧类型）才能区分降级 ⇒ 升 fable 并先开裁决 |
| 15 档位理由 | UI 呈现 + 状态机分支判断，属 opus 面；不涉需求终裁故不用 fable |
| 16 规模 | 中（≈1 人日）；拆 5 个原子步，每步 <2 小时 |

## 附：五条缺口的证据摘要（逐条可复跑）

| 缺口 | 契约要求（一级） | 代码现状（二级） | 复跑检索（三级） |
|---|---|---|---|
| U1 演示态静默 | 「演示态必须显式显示「演示数据，未连接实时通道」，禁止静默装作正常」 | `lib/api/notifications.ts:103-105` `isMockMode()` 下 `return () => {}`；`NotificationBell.tsx:246` 仍渲染「暂无通知」 | `grep -rn "演示数据" apps/web/components apps/web/app --include=*.tsx` ⇒ 仅 `app/admin/ops/page.tsx:52`（无关） |
| U2 降级文案缺半句 | 「显示「实时推送暂不可用，历史仍可查」，不得显示为「无通知」」 | `NotificationBell.tsx:240-243` =「通知服务暂不可用，请稍后重试」 | 帧解析在 `notifications.ts:114-116`，通路不缺 |
| U3 空态未拆 | 「「今日暂无热点」+ 最近更新时间；与「聚类未产出」区分」 | `hot/page.tsx:296` 一句合并文案 | `grep -n "今日暂无热点\|最近更新" apps/web/app/hot/page.tsx` ⇒ 0 |
| U4 0 值冒充 0 分 | 「score 为 0.0 时显示为「待评分」而非「0 分」」 | `hot/page.tsx:232` `🔥 {t.hot_score.toFixed(1)}` | `grep -n "待评分" apps/web/app/hot/page.tsx` ⇒ 0 |
| U5 降级无分流 | 「30002 / 50002 ⇒ 回落非流式或提示不可用；超时给「响应较慢」」 | `useSseAsk.ts:100-102` 通用气泡 | 后端码位在 `chat.py:11-12`；`grep -rn "响应较慢" apps/web` ⇒ 0 |
