# EVD-V3-19 · STEP-19 判定表（已实现未纳管域：推送 / 热点 / RAG / SSO / 端口）

> 卡面：`docs/任务规划V0.13.0/steps/STEP-19-已实现未纳管域验证.md`（来源卡 `docs/任务规划V0.7.0/steps/STEP-19-…md`，
> 档位 opus——**本卡的产物是判定，不是实现**：卡面「禁止修改」含 `apps/api/app/**`，发现缺陷只记录不修）。
> 交付基线 `8d3448d`（STEP-09 收口提交）。
> 卡面字段 11 的证据路径写作 `docs/任务规划V0.8.0/evidence/61358c3-19/`，本仓从未建过（P-58/P-65 同形）
> ⇒ 按现行约定落本目录。
>
> 档位口径（卡面 S19.3.1）：**已确认 / 部分确认 / 证据不足 / 存在缺陷 / 需要返工**，无读数不得写"已确认"。

## 0. 先读现读锚（卡面 2 的静态锚全部有漂移，按 V0.13.0「禁止照抄来源卡读数」重锚）

| 卡面锚 | 现读（`8d3448d`） | 结果 |
|---|---|---|
| `providers/push/__init__.py:23-30`（6 渠道） | 渠道注册表在，6 家 ✓（行号未复核到行级——本卡判为"渠道在位"，不作为命题读数） | 不影响判定 |
| `push_scheduler.py:229` 唯一生产调用点（定义 `:274`） | 现读调用点 **4 处**：`push_scheduler.py:245`、`services/push.py:73`、`api/v1/bots.py:522`、`api/v1/bots.py:682`；定义在 `:274` | **命题已被 STEP-23/26 改掉**，见 §1 |
| `job_worker.py:280-296`（三分支均调 `run_scoring`） | 现读 `run_scoring` 在 `job_worker.py` 内被调用，日报前兜底 + 每小时重评在 `scheduler.py` | 见 §2 |
| `hot_cluster.py:276` 落 0.0 占位 | 现读 `hot_score=0.0` 在 `hot_cluster.py:275` | ✓ 一致 |
| `api/v1/auth.py:159` backchannel-logout | 现读 `@router.post("/backchannel-logout")` 在 `auth.py:159-160` | ✓ 一致 |
| `docker/compose.yml:235`（端口） | 现读全文件只有 3 处 `ports:` 映射：`5300:5300` / `3300:3300` / `3200:3000`（`:235` 已不是端口行） | 见 §4 |

## 1. REQ-F-001 站内通知历史 —— **已确认**（判定范围内）

命题："事件触发/手动触发路径是否真的写 `notifications` 行？（疑：不写）"。
判据文件：`apps/api/tests/test_r19_notification_paths.py`（新增常驻用例，8 条，全部连库真跑）。

| web 投递入口 | 判定读数 | 用例 |
|---|---|---|
| 定时（cron 到期 → 调度器领取投递） | `notifications` 增量 **恰 1 行** | `test_cron_claim_by_scheduler_writes_exactly_one_notification` |
| 事件（emit 阶段） | 增量 **0 行**（emit 只登记 `push_events`，职责正确） | `test_event_emit_writes_nothing_and_dispatch_writes_one` |
| 事件（调度器派发阶段） | 增量 **恰 1 行** | 同上一条的后半 |
| 手动 run-now（`POST /bots/tasks/{id}/run`） | **恰 1 行** + 载荷预铸 `notification_id` | `test_manual_run_now_writes_one_notification` |
| 一键测试（`POST /bots/{id}/test`） | **恰 1 行** | `test_test_push_on_web_channel_writes_one_notification` |
| 管理端直投（`PushService.push`） | **恰 1 行** | `test_admin_direct_push_writes_one_notification` |
| 反向极性：投递失败（`delivered=False`） | **0 行** | `test_a_failed_delivery_writes_no_notification` |
| 行与载荷同 id / 广播-定向同源 | 成立 | `test_notification_row_is_bound_to_the_delivered_payload` |

摘除反证（scratch 插件 `-p probe_r19_notify`，运行期摘，不改仓库生产文件）：

| 摘掉 | 变红的用例 | 计数 |
|---|---|---|
| N1 三条命名空间里的 `persist_web_notification` 全换成空函数 | cron / 事件 / run-now / test-push / 管理端直投 / id 同源 | 6（另 2 条不该红的仍绿：结构守卫读的是源文本，失败投递判的是 0 行） |
| N2 事件领取 `claim_pending_events ⇒ []` | **只有**事件那一条 | 1（证明 cron 与 event 两条路径真的被分开判） |
| N3 投递失败也补写一行 | 失败极性 + "恰 1 行"两条 | 3 |

卡面 S19.1.1 要求"结论三选一并登记：补实现卡 / 显式 MUST NOT / 设计如此"——
**三者都不需要**：缺口已由 STEP-23（`test_push` + `run_push_task_now`）与 STEP-26（管理端直投）补齐，
本卡复验的是"补齐之后没再退化"，并新增"四条入口共用唯一写入口"的结构守卫
（`test_the_shared_persist_fn_is_the_only_write_door`：`inspect.getsource` 判每条都调
`persist_web_notification(` 且都不自己 `Notification(`）。

## 2. REQ-F-002 热点链路 —— **已确认**（端到端一条链贯通）

命题："聚簇→评分→Feed 回刷→日报降级 端到端一条链是否真贯通？"
判据文件：`apps/api/tests/test_r19_hot_chain.py`（新增常驻用例 4 条，连库真跑）。

读数（同一条链上取，不是四段碎片）：

| 环节 | 读数 |
|---|---|
| 聚簇 | 5 篇语料 → **2 个话题**（两个两篇族各成一簇），孤篇不成话题；`HotTopicArticle` 4 行 |
| 聚簇阶段的分数位 | `hot_score == 0.0` **且** `feed_items.score == 0.0`（占位确实存在 ⇒ "评分回填"是必经点，不是装饰） |
| 评分 | `run_scoring` 后两条话题 `hot_score > 0`，且逐条 `FeedItem.score == HotTopic.hot_score`（差 < 1e-9） |
| 周期重评 | 时钟推后 30h 再 `run_scoring`，Feed 分数仍与话题一致（每小时 `hot_rescore` 那一环的回刷真的在跑） |
| 日报（LLM 正常） | `DailyReport` 落库、`topic_count == 2`、两个话题标题与两枚 LLM 摘要都在正文里，且有对应 `daily_report` Feed 条目 |
| 日报降级（LLM 抛穿） | 日报仍产出，正文里是**中心文章正文首段**（`_fallback_summary`），无 LLM 文本 |
| 日报降级（LLM 返回空） | 同上（两条失败形状分开参数化：`except` 那一支与 `if summary:` 那一支缺一支不会被抓到） |

摘除反证（`-p probe_r19_hot`）：

| 摘掉 | 变红 | 计数 |
|---|---|---|
| H2 `_topic_summary` 不再兜住抛穿 | 只有 `LLM抛穿` 那一条参数化用例 | 1（`LLM返回空` 仍绿——它的降级走另一支，正确） |
| H4 评分后把 Feed 分数刷回 0.0（模拟"回刷那一步不存在"） | 主链条 + 周期重评 | 2 |
| H5 强行把五篇并成一簇 | 主链条（数量与成员数断言） | 1 |
| H3（**无效探针，如实记**） | 0 | 我把 `cluster()` 的 `tau` 改成 0.0，读数与默认阈值**完全一致**——TF-IDF 下无关文档余弦恰为 0，而倒排预筛根本不比较没有共同词的文档对。这个"摘了却没变"的读数不进判据，但它是一条自我教训：**摘除反证必须先证"摘的东西真的改变了被摘函数的行为"**，否则"没红"会被误读成"判据不承重" |

## 3. REQ-F-007 登出链路 —— **已确认**（命题范围内：服务端会话真失效 + backchannel 有可达消费方）

命题："登出后服务端会话是否真失效？backchannel-logout 是否有可达消费方？"
判据文件：`apps/api/tests/test_r19_sso_session.py`（新增常驻用例 4 条，走真 HTTP + 伪 IdP 全登录流）。

| 判据 | 读数 |
|---|---|
| **旧 cookie 重放** | 登出前 `/auth/me` 200；`POST /auth/logout` 200 后，**显式带着登出前那枚 `bothot_session` 值**再打 `/auth/me` ⇒ **401 / 10001** |
| backchannel 授权面 | 只带普通用户 cookie、`logout_token=""` ⇒ 恒 200 同形（`code=0`），且该用户会话**仍在**（`/auth/me` 仍 200） |
| backchannel 面对畸形 token | 一枚签名无效的 JWT ⇒ 200 同形 + 会话未被删（"200 且没删东西"两半都判） |
| 端点可达性 | 摊平 `app.routes` 后 `/api/v1/auth/backchannel-logout` 在其中 |
| 反证 S1 | 把 `AuthService.logout` 换成空函数 ⇒ 重放那一条**红**（证明这条判据真的依赖服务端删会话） |

为什么"旧 cookie 重放"这条不是重复劳动：既有
`test_auth.py::test_logout_revokes_chain_and_clears_session` 登出后再访问 `/me` 得 401，
但它走 `TestClient` 的 CookieJar——logout 的 `Set-Cookie` 已把 jar 里的值清掉，
那一次访问实际是**不带 cookie**。服务端若只信 cookie 不查存储，"不带"照样 401、
"带旧值"会被放行，两者只有后者能区分。本卡补的就是这一格。

未覆盖（如实登记，不在本卡修）：前端 `/auth/aidean/callback` 页在登出后的界面表现、
以及"第二个受登录保护端点上的重放"。后者我一开始写了，随后**撤下**：那次 `/sources` 返 401 是
因为它需要真实 users 行而夹具里没有 ⇒ 正控制拿不到，这条判据不成立，留着就是假绿。

## 4. REQ-C-002 端口准则 —— **部分确认**（宿主零占用成立；端口表两行与实际不符）

命题："全仓是否存在 BotHot 服务占 3000" + "3200/3300/5433/6380 与 AGENTS 端口表逐项核对"。
判据文件：`apps/api/tests/test_r19_ports.py`（7 条，离线可判，`@win` 与 CI 都能跑）。

| 判据 | 读数 |
|---|---|
| compose 里 BotHot 服务发布的宿主端口 | 真解析 `docker/compose*.yml` 得 **3 条映射**：`langbot 5300:5300`、`backend 3300:3300`、`frontend 3200:3000` ⇒ **零占用 3000** ✓ |
| 为什么不用 `grep '3000'` | 文本扫描在本仓命中 `30004` 错误码、`AIDEAN_ISSUER=http://host.docker.internal:3000`（那是**主平台**的地址，不是 BotHot 在监听）与注释"容器内仍 3000"——既误报又漏报，所以判 YAML 结构 |
| 判据极性自检 | 喂一份含 `3000:3000` 与 `127.0.0.1:3000:3000` 的假 compose，谓词必须两条都抓住 ✓（`_host_port` 取的是**倒数第二段**，不是首段） |
| 扫描面非空 | 断言"解析出的映射数 > 0"⇒ compose 改名/目录挪走时不会静默恒绿 ✓ |
| `apps/api/Dockerfile` | `EXPOSE 3300` ✓（`apps/web/Dockerfile:81` 的 `EXPOSE 3000` 是 Next.js 自身监听口，宿主映射 3200，**不违规**，所以本卡不去"修"它） |
| **不符项** | 端口表写 5433（PG 宿主）/6380（Redis 宿主），但 `docker/compose.yml:45-47` 自 2026-10-09 起把两个底座移交给共享基础设施，注释给的是 **PG 宿主 5435 / Redis 宿主 6379**，且 compose 里**没有任何** 5433/6380 映射（现读 3 条映射见上）⇒ 端口表这两行与实际不同源 |

判定：**部分确认**——"3000 零占用"这一半是硬结论（有判据有反证）；"逐项核对"这一半暴露出
文档漂移（表里 5433/6380 两行无人认领）。AGENTS.md 在本卡「禁止修改」清单内，卡面明写
"结论转 STEP-17/12 落地" ⇒ 登记为 **P-78**，本卡不动表。

## 5. REQ-F-005 RAG 流式八态 —— **部分确认**（后端面在案，前端八态证据不足）

命题："流式中断/重连/降级是否满足 `ux_states` 八态？（前端从未在关 mock 下验过）"

| 面 | 判定 | 依据 |
|---|---|---|
| 后端 SSE 帧语义 | 有常驻用例在案（`tests/test_chat_sse.py` 20 条：meta/delta/done、error 帧 50002/30002/10001、首 Token 超时、空闲超时、断连上游中止、畸形 JSON 清理） | 本卡未新增，复核其存在与命名；不重跑判定语义 |
| 前端八态（关 mock） | **证据不足** | 需要两个人工前提：常驻 `MOCK=false` 前端（3200）+ 后端（3300），以及真实 LLM 凭据。卡面「阻塞条件 ①」明令无凭据时不得用超时冒充读数——本执行环境两者都不满足 |
| 交付物 | `apps/web/e2e/r19-chat-stream.spec.ts`（新增，关 mock 通道）：`E2E_REAL_BACKEND=1 ∧ E2E_CHAT_LLM=1` 双开关门（不是 `test.skip(true)` 那种恒跳过死断言），含①success 渐进、②流式中主动断连后内容保留 + 可重发、③unauthenticated 与 forbidden 文案不许混、④八态清单附件 | `tsc --noEmit` 通过；**未执行过**（前提缺失），所以第 3 行仍是"证据不足"而不是"已确认" |

契约文件缺口：卡面引用的 `ux_states` 八态枚举只存在于
`docs/任务规划V0.12.0/contracts/ux_states.schema.json`（`State.enum` 八值），
V0.13.0 及以后的树里没有 `ux_states.schema.json`（`ls docs/任务规划V0.17.0/contracts/` 零命中）
⇒ 判据的**契约真源在历史版本里**，登记为 **P-80**。

## 6. 判定汇总（S19.3.1 要求的表）

| 需求 | 档位 | 承重读数所在 | 需要谁接着做 |
|---|---|---|---|
| REQ-F-001 站内通知历史 | **已确认** | `test_r19_notification_paths.py` 8 条 + N1/N2/N3 反证 | 无（缺口已由 STEP-23/26 补齐，本卡复验未退化） |
| REQ-F-002 热点端到端 | **已确认** | `test_r19_hot_chain.py` 4 条 + H2/H4/H5 反证（H3 无效，已如实记） | 无 |
| REQ-F-007 登出/后端会话失效 | **已确认**（命题范围） | `test_r19_sso_session.py` 4 条 + S1 反证 | 前端 callback 页登出后表现——不在本卡命题内，未派卡 |
| REQ-C-002 端口准则 | **部分确认** | `test_r19_ports.py` 7 条 + 极性自检 | **P-78**：AGENTS.md 端口表 5433/6380 两行与 compose 现状（shared-infra 5435/6379）不同源，转 STEP-17/12 |
| REQ-F-005 RAG 流式八态 | **部分确认**（后端在案 / 前端证据不足） | `test_chat_sse.py`（既有）+ 新增 spec（未执行） | 需要人工把 `MOCK=false` 前后端与 LLM 凭据备齐后执行那条 spec；另 **P-80**：ux_states 契约文件在现行树缺失 |

## 7. 本卡的依赖倒置（如实上报）

卡面字段 14 与来源卡都写 `Depends on：STEP-00C、STEP-15`，而 V0.17.0 附录 A 的串行队列把
**19 排在 15 之前**（队列⑬ = STEP-19，队列⑭ = 15b → 15 → 14b）。本卡能判的三档（F-001/F-002/F-007/C-002）
不依赖 15；**唯一被这个倒置卡住的是 REQ-F-005 的前端八态**——那正是 15 要交付的"关 mock e2e 通道"。
我没有为了"把 19 做完"而把 15 提前（队列顺序是执行助手不得自行改的东西），
处置是：交付 spec + 双开关门，判定停在"证据不足"，并登记 **P-79**（队列与本卡依赖冲突），交规划方裁定。

## 8. 未做的事（不掩盖）

- 没有执行任何 Playwright 用例（前提缺失，见 §5）；`r19-chat-stream.spec.ts` 从未跑过一次，
  所以它只算"通道就位"，不算读数。
- 没有真实 LLM 凭据、没有主平台（SSO）实例：登录流走的是进程内伪 IdP（复用 `test_auth.py` 的 `FakeAideanIdP`）。
- 没有改一行 `app/**` 业务代码（卡面「禁止修改」）；发现的三处不符全部以 P 项交回。
- 未跑"两个真实并发副本抢同一条任务"这类跨进程读数的场景（`test_w3_push_scheduler` 已判过 SKIP LOCKED 那一面）。

## 9. 读数汇总（交付时）

| 命令 | 读数 |
|---|---|
| 四文件合跑（真库 `bothot_test`@5547 / PG 16.4） | `23 passed`（端口 7 + SSO 4 + 热点链 4 + 通知路径 8） |
| 四文件合跑（无 DSN） | `11 passed / 12 skipped`——12 条 skip 全部落在 `AIDEANBOT_TEST_PG_DSN 未设置` 族，11 条不连库（端口 7 + SSO 4）⇒ `SKIP_BASELINE_WIN` 641→**653** |
| 邻族干扰复跑（`test_auth` / `test_backchannel_logout` / `test_chat_sse` / `test_wa_hot_scoring` / `test_hot_scorer_batch` / `test_w2_report` + 四文件） | `140 passed / 2 skipped`（2 条是 Redis/LangBot 不可达族）——本卡用例会真提交并全局清 `push_events`、`run_scoring` 会重算全表非 archived 话题，所以专门复跑一次"谁在我之后跑" |
| 全量（真库） | **2231 passed / 6 skipped / 0 failed**，1042.55s（STEP-09 交付时 2208 + 本卡 23 = 2231；6 条 skip 仍是 LangBot/Redis 族，PG 不可达族 0） |
| lint / 类型 | `ruff check app tests` All checks passed；`mypy app` 无问题 117 文件（本卡**未改一行 `app/**`**，跑它是为了证明"零业务改动"这个说法站得住） |
| 前端 | `pnpm exec tsc --noEmit` 无输出（新 spec 过类型门）；Playwright **未执行**（§5 前提缺失） |
| 文档/门禁 | `check_docs_consistency` 23 引用 0 缺失；`entry.py rounds-check` ✅（本卡第 1 轮）；`entry.py evidence-check` 见下 |
| 契约面 | 本卡不改契约：无迁移、无 `packages/contracts/**` 改动 ⇒ 单头仍 `ab1006c2a` |

## 10. 三绿（验收面 = `@ci` ubuntu-latest）

交付是**第 2 轮** `5f16de9`（第 1 轮 `c9cb215` 的 Security 🔴 见 §11）：

| 工作流 | run id | 结论 |
|---|---|---|
| CI | 39722164669 | success（attempt 1）——正式验收面 |
| Security | 39722164679 | success（attempt 1）：`.gitleaksignore` 生效后本机与 CI 双双 `no leaks found`（本机实测 335 commits scanned） |
| CI-Windows | 39722164694 | success（attempt 1）：`SKIP_BASELINE_WIN` **653** 与实测相符，未知族 0 |

## 11. 第 1 轮的 Security 🔴（是我写出来的缺陷，不是环境抖动）

第 1 轮提交 `c9cb215`：CI 与 CI-Windows 绿，**Security 🔴**，日志一行到位——

```
gitleaks：🔴 检出 1 处明文密钥
  🔴 jwt | apps/api/tests/test_r19_sso_session.py:77 | commit=c9cb2150 | 命中已打码：REDACTED
```

命中的是我为了"验签失败的 token 也不许删会话"那条极性判据**手写在源码里的一枚 JWT 字面量**
（`eyJhbGciOi…`）。它不是真凭据，但**源码里存在密钥形状这件事本身**就是这条门要拦的东西——
"只是测试用的假串"不是豁免理由：形状扫描无法分辨真假，一旦放行这类写法，
下一条真凭据就会混在同一种形状里被提交进来。第 2 轮的处置是**改成运行时现签**
（`_token(key=rsa.generate_private_key(...))`，复用 `test_backchannel_logout.py` 的签名助手），
判据语义不变（仍是一枚"形状合法、签名不匹配"的 token），源码里零密钥形状字面量。

顺带量出一处**本地门与 CI 门的覆盖面缺口**（登记 **P-81**）：同一行文本喂给本仓自己的敏感形扫描器

```
guards.secret_scan(line, code=True,  lang="py") ⇒ []
guards.secret_scan(line, code=False, lang="md") ⇒ []
```

也就是 `entry.py evidence-check` 里那道"扫 index blob"的门**看不见 JWT 形状**，
所以我在提交前拿到的是"✅ evidence-check 全部通过"，推送后 CI 的 gitleaks 却红了。
本机又没有 gitleaks 可执行文件（`which gitleaks` 空 ⇒ `entry.py scan-secrets` 在这台机器上是 rc=3
"工具缺失，不是通过"），所以本地没有任何一道门能复现 CI 的这一维。
这不是"CI 冤枉人"，是**本地门禁的覆盖面比验收面小**：一个只在 CI 存在的 🔴 类别，
执行方必然要烧一轮 CI 才发现（本轮就是这么烧的）。

| 读数 | 值 |
|---|---|
| 第 1 轮 Security | run 39721460521 failure（`gitleaks` 那一维 BLOCK，其余 pip-audit / pnpm-audit / trivy 三轴 OK） |
| 第 1 轮 CI / CI-Windows | 见 §12（两维绿，与本轮这红无关） |
| 第 2 轮复跑（本地） | `pytest tests/test_r19_sso_session.py` ⇒ `4 passed`；`ruff check` 通过；改后该文件已无 `eyJ` 开头的字面量（`grep -c` 复核） |

## 12. 第 2 轮之后没再动的事

本卡没有第 3 轮（D-14 阈值 ≤2 轮，`rounds-check` 在本卡范围内读数：第 1 轮 `c9cb215` + 第 2 轮 `5f16de9`）。
§5 的 REQ-F-005 前端八态仍是 `证据不足`，它等的是 **STEP-15 的关 mock 通道 + 人工供给的 LLM 凭据**，
不是再一轮施工——把那条 spec 真跑起来的人拿到的读数，才是这张判定表缺的最后两行。
§4 的端口表漂移、§5 的 ux_states 契约缺位、§11 的门禁覆盖面缺口，全部按 P-78 / P-80 / P-81 交回，
本卡一行 `app/**` 都没改（卡面「禁止修改」）。
