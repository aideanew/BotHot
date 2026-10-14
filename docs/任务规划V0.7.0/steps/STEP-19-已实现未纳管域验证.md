# STEP-19 已实现未纳管域验证（推送 / 热点 / RAG / SSO）

| 字段 | 值 |
|---|---|
| 归属-切片 | S-M4 未纳管域补齐 |
| 归属-需求 | **REQ-F-001、REQ-F-002、REQ-F-005、REQ-F-007** + REQ-C-002（端口约束复验） |
| 归属-方案 | 04 §4.13、`01` F-88、`coverage §3` |
| 里程碑 | M4 |
| 档位 | **opus**　理由：本卡的产物是「判定」——每条要给 `已确认/部分确认/证据不足/存在缺陷/需返工`，且直接决定后续是否开新切片；判定错的代价（把未实现当已实现）高于实现本身。**升级条件**：发现安全缺陷（越权/凭据外泄）⇒ `fable` 终裁 |
| 规模 | 中（≈1.25 人日） |
| 依赖 | Depends on：STEP-00C（CI 可跑）、STEP-15（关 mock 的 e2e 通道）。Blocks：STEP-12 |
| 基线 | main@13acacc |
| 剩余原子任务 | 6（👤 0） |

## 目标
对四条「代码在、但从没进过任何规划与 backlog」的需求，逐条产出**基于运行/读数**的五档判定；不允许以「代理/文档/注释说已实现」作为通过依据（04 §4.14 排除项 ⑤）。

## 输入（静态读码已确认、但**未运行验证**的锚）
| 需求 | 静态锚 | 待验命题 |
|---|---|---|
| REQ-F-001 | `providers/push/__init__.py:23-30`（6 渠道）、`base.py:38-51`（`delivered/reason/retryable`）、`push_scheduler.py:229`（`persist_web_notification` **唯一生产调用点**，定义在 `:274`） | 事件触发/手动触发路径是否真的写 `notifications` 行？（疑：不写） |
| REQ-F-002 | `job_worker.py:280-296`（三分支均调 `run_scoring`）、`scheduler.py:365-394`（每小时 `hot_rescore`）、`hot_scorer.py:123-150`、`feed_service.py:40,266-273`（Semaphore(3)） | 聚簇→评分→Feed 回刷→日报降级 端到端一条链是否真贯通？ |
| REQ-F-005 | `api/v1/chat.py`、`providers/reranker.py`、`tests/test_chat_sse.py`、`apps/web/app/chat/page.tsx`、`lib/api/ask.ts:50/79` | 流式中断/重连/降级是否满足 `ux_states` 八态？（前端从未在关 mock 下验过） |
| REQ-F-007 | `services/auth/logout_token.py`、`tests/test_backchannel_logout.py`、`api/v1/auth.py:159`、前端 `app/auth/aidean/callback/page.tsx` | 登出后服务端会话是否真失效？backchannel-logout 是否有可达消费方？ |
| REQ-C-002 | `docker/compose.yml:235` 等 | 全仓是否存在 BotHot 服务占 3000？ |

## 输出（文件）
`apps/api/tests/test_r19_notification_paths.py`（新）、`apps/web/e2e/r19-chat-stream.spec.ts`（新，关 mock）、`docs/06_validation/evidence/EVD-V3-19/verdicts.md`、EVD-V3-19/*（读数）
> 本卡**只新增验证用测试**，不改业务代码；发现缺陷 ⇒ 开新卡，不在本卡顺手修。

## Execution Steps
1. [ ] ✅ **S19.1.1** REQ-F-001：分别走「调度器领取 / 事件触发 / 手动触发」三路径，查 `notifications` 行数变化；命令与 SQL 读数入 EVD
   - 结论三选一并登记：补实现卡 / 显式 MUST NOT / 「设计如此」并在需求文本写明
2. [ ] ✅ **S19.1.2** REQ-F-002：造一批文章跑聚簇 → 断言 `HotTopic.hot_score` 非 0.0 占位（`hot_cluster.py:276` 落 0.0 由评分回填）→ 断言 Feed 分数与之一致 → 触发日报并模拟 LLM 失败，断言走降级
3. [ ] ✅ **S19.1.3** REQ-F-005：关 mock 起前端，`/chat` 流式中主动断连，断言已渲染内容保留 + 可重连；按 `ux_states` 八态逐条打勾
4. [ ] ✅ **S19.1.4** REQ-F-007：登录 → 登出 → 用旧 Cookie 重放受保护端点，断言 401/10001；单独打 `auth.py:159` backchannel-logout（服务间签名），断言普通用户 Cookie 被拒
5. [ ] ✅ **S19.2.1** REQ-C-002：`grep -rn '3000' docker apps` 全仓扫描，断言 BotHot 服务零占用；3200/3300/5433/6380 与 AGENTS 端口表逐项核对
6. [ ] 📄 **S19.3.1** 汇总五档判定表（`已确认/部分确认/证据不足/待其他员工完成/存在缺陷`+`需要返工`），每条附命令与读数；**无读数不得写「已确认」**

## 验收标准
- [ ] 四条需求各有一份带读数的判定，判定档位是五档之一
- [ ] 三路径通知落库结论明确（行数读数），若为「不写」则已立项或已显式 MUST NOT
- [ ] 热点链路与登出链路各有至少一条**新增的常驻用例**（不是一次性探针）
- [ ] 端口扫描零违规
- [ ] 本卡 `git diff` 只命中新增测试与 EVD，未触碰 `app/**` 业务逻辑

## 验证命令
```bash
cd apps/api && .venv/bin/python -m pytest tests/test_r19_notification_paths.py -q -rs
psql "$AIDEANBOT_TEST_PG_DSN" -c "select count(*) from notifications;"   # 三路径前后对比
cd ../web && NEXT_PUBLIC_API_MOCK=false pnpm playwright test e2e/r19-chat-stream.spec.ts
grep -rn '3000' docker/ apps/ --include='*.yml' --include='*.ts' --include='*.py' | grep -v '32000\|33000'
```

## 证据路径
`docs/06_validation/evidence/EVD-V3-19/`

## 允许修改
`apps/api/tests/test_r19_*.py`、`apps/web/e2e/r19-*.spec.ts`、EVD-V3-19
## 禁止修改
`apps/api/app/**`（发现缺陷只记录不修）、`packages/contracts/**`、`alembic/**`、`AGENTS.md`（结论转 STEP-17/12 落地）

## 依赖与阻塞
- Depends on：STEP-00C、STEP-15　Blocks：STEP-12
- 阻塞条件：① 无真实 LLM 凭据 ⇒ 首 Token/流式标 `证据不足`，不得用超时冒充；② 无 Redis ⇒ 站内通知链路标 `部分确认`；③ 发现越权可复现 ⇒ 立即 blocked + 上报，本卡不修
