# STEP-RV：R0 与 STEP-16 的真库验收（V0.17.0 队列⑮ 第六张）

- 日期：2026-10-23
- 卡面：`docs/任务规划V0.13.0/steps/STEP-RV-R0与16真库验收.md`（依赖标注 BLOCKING：需 PG+Redis 执行机）
- 所有权：**仅证据目录**（发现缺陷 ⇒ 开新卡，本卡不改 `apps/**`）
- 结论一句话：**五项里三项可由 CI/静态面判，两项被本机环境挡住**。
  本机 2026-10-23 现读没有 docker、没有 PG/Redis 监听 ⇒ 手测两项**未测**，不冒充。

## 0. 环境与前提的现读（先纠正卡面两处过期）

| 卡面 | 现读 |
|---|---|
| SRV.1.2「`alembic upgrade head` = ab1005w5b」 | 过期：当前单头是 **ab1006c2a**（STEP-04 的 `ab1006c1a` 之后又走过一批迁移；CI 有单头断言与往返门在守） |
| 字段 14「需 PG+Redis 执行机」 | 本机 2026-10-23 无满足条件的环境：`docker` = command not found、Docker Desktop 安装路径不存在、`netstat` 对 5547/5433/6390/6379/6380 **无监听**、`tasklist` 无 postgres 进程（同一天上午这里还有一套隔离 PG16@5547 可连，晚间会话中断后消失） |
| 「自动化一半已由 CI 满足」（V0.10.0 变更段） | 成立，且证据比那一轮更强：见下面 §1 的三条 run 读数 |

## 1. 可以判的三项

### SRV.1.3 skip 列表：PG 不可达类必须为 0 —— 成立（取 `@ci` 面）

| run | 读数 |
|---|---|
| 39885880010 @3491054 | `2258 passed, 6 skipped, 4 deselected` + `skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0` |
| 39887049558 @bf141d5 | 同口径 success（补丁批后复算） |
| 39885880055 @3491054（@win） | `1598 passed, 666 skipped, 4 deselected`，`failed=0 total_skipped=666 baseline=666`，未知族 0 |

六条 skip 逐条点名（ubuntu）：`test_chat_sse:1130`、`test_chat_sse:1208`（LangBot 冒烟两条）、
`test_env_isolation:77`（代理变量未设，判据无判定力时自跳）、
`test_session_store_redis:47`、`test_session_store_redis:71`、`test_we_notifications:247`（Redis 类三条）。
⇒ **PG 不可达类 = 0**，且被 STEP-00E 点名的 R0 回归用例
（`test_be02_engine_routing.py::test_short_link_second_ingest_hits_cache_via_url_fallback`）
不在这六条里 ⇒ 它在真库上实跑。

### SRV.2.2 AST 判据：`kb.py` 里没有 `Source.url.like` 调用 —— 成立

本机直接对 `apps/api/app/services/kb.py` 做 AST 遍历（不依赖 PG）：
`ast.walk` 找到的 `.like` 属性访问 **0 处**。
同时记一条判据形态的坑：同一文件里字符串 `Source.url.like` 出现 **1 次**，
但那在 S2.1.4 的注释里（解释"为什么这条兜底已删、且不复活它"）——
所以"grep 必须为空"这种写法在这份文件上不可满足，卡面用的是 AST 口径（正确）。
常驻门禁侧：`apps/api/tests/test_kb_multisource_anchor.py` 与
`docs/06_validation/evidence/EVD-V2-02/` 的静态判据承担同一件事（不是靠本文件的一次性读数）。

### SRV.2.1 R0 相关用例 0 failed —— 成立（真库面由 CI 代跑）

短链/长链/资产回查那批用例（`test_d04_short_link.py`、`test_kb_longlink_ingest.py`、
`test_kb_multisource_anchor.py`、`test_be02_engine_routing.py`、`test_p0_asset_cache.py`、
`test_idempotency_lock.py`、`test_e2e_collection.py`）在 `@ci` 的 2258 条里实跑，
`0 failed`；本机因无 PG 不重复主张。

## 2. 本机做不了的两项 —— 未测（不冒充）

| 项 | 为什么未测 | 需要什么 |
|---|---|---|
| SRV.2.3 真库手测：同一短链入库两次，第二次命中缓存且 asset 数不变 | 需要真 PG 的**手测**面；本机无 PG。自动化面其实覆盖了同一事实（`test_p0_asset_cache.py` 机器门①/③ + `test_d04_short_link.py`），但卡面要的是"手测读数"，不用自动化替它签字 | 任一能起 compose/test-env 的执行机 |
| SRV.3.1 `/ready` 返回告警字段且 `enabled=true`；SRV.3.2 600s 宽限内不告警、故障持续时 1800s 只告一次 | 需要**跑起来的后端**（uvicorn + PG + Redis）。本机三样都没有；`SRV.3.2` 还要跨越 600s/1800s 的真实时间窗 | 依赖机 + 一段不被打断的 30 分钟；或用 `ALERTING_*` 注入时钟的等价手测（属 STEP-16 的实施面，本卡不改代码） |

⇒ 卡面 SRV.3.3「CI+Security 双绿后把 R0/16 在 04 状态表标 ✅」这条**今天不能做**：
双绿成立，但它的前半（三条手测）不成立。按卡面验收句「三条手测有截图/日志」，
缺任何一条就不该标 ✅。这一条留给有环境的执行者，不是本卡可以"按 CI 绿"顺手勾掉的。

## 3. 顺带发现的两个可复现事实（不改代码，只登记）

1. **环境不是稳定的**：同一天内 5547 从可连变成无监听、`docker` 从"能装到别处"变成 CLI 不存在。
   这与 `docs/04_engineering/conventions.md` §4.3 第 3 条（验收环境每轮重取）是同一件事的新证据，
   也正是队列里 STEP-00E 未闭合项（S00E.1.2 固定起法、S00E.3.2 复跑一致性）要解决的问题。
2. **卡面自己的锚点会过期**（`ab1005w5b` 已是两个版本前的头）。
   RV 是"验收卡"，它没有代码 diff 面，唯一能留下的就是这份把现读与卡面差行列出来的读数件。

## 4. 本卡出门判定

| 三级任务 | 判定 |
|---|---|
| SRV.1.1 起 PG/Redis | **未测**（本机无 docker；未尝试安装第三方运行时） |
| SRV.1.2 `alembic upgrade head` 到头 | 卡面期望值过期（实际头 ab1006c2a）；单头与往返由 CI 常驻门在守 |
| SRV.1.3 skip 列表 PG 类 = 0 | 达成（CI + @win 双读数） |
| SRV.2.1 R0 用例 0 failed | 达成（真库面由 `@ci` 代跑；本机未复算） |
| SRV.2.2 AST 判据 | 达成（本机实跑，0 调用点） |
| SRV.2.3 同一短链二次入库手测 | **未测** |
| SRV.3.1 / SRV.3.2 `/ready` 告警字段与宽限/冷却 | **未测** |
| SRV.3.3 状态表标 ✅ | **不做**——前置的三条手测未成立，见 §2 |
| 发现缺陷 ⇒ 开新卡 | 本卡未产生新缺陷（`P-99` 是环境无关的另一件事，已登记） |
