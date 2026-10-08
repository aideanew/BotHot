---
id: TASK-PLAN-v0.9
type: task-plan
title: BotHot 全量剩余任务大纲体系 v0.9（融合外部 81 项参考大纲的裁定版）
status: active
owner: engineering
created: 2026-10-08
updated: 2026-10-08
baseline_commit: fbaaeaa（main，工作树干净）
supersedes: docs/05_execution/tasks/TASK-PLAN-v0.8.md（S0 已收口，本版承接 S1–S4 并吸收外部参考大纲）
---

# BotHot 全量剩余任务大纲体系 v0.9

> **取证基线**：`main @ fbaaeaa`，工作树干净；后端 943/7、前端 vitest 359/359、tsc 硬门禁（2026-10-08 实测）。
> **方法**：对参考大纲 81 项逐条与代码实证对撞——**吸收真实项、剔除已完成项、修正方向性错误、补上遗漏的 P0**。
> **编号**：沿用 v0.8 的 S 阶段骨架，阶段内三级（S<阶段>.<任务>.<原子步骤>）。

## 第零节 对参考大纲的逐条裁定（防重排期、防误修）

### 0.1 剔除——参考大纲列为待办但代码已完成（重排期即造假）

| 参考项 | 裁定 | 证据 |
|---|---|---|
| 2.1.1 推送重试验证 | ✅ 已实现 | `push_scheduler.py` MAX_PUSH_RETRIES+指数退避+死信（PUSH-009），`test_r11_push.py` 覆盖 |
| 3.2.1 OIDC iss/aud 校验 | ✅ 已实现 | `core/config.py:41-43` `oidc_issuer_expected/oidc_audience_expected` + 生产守卫 `:230-232` |
| 3.3.1 结构化日志 | ✅ 已实现 | structlog 143 处；裸 logging 仅 `core/logging.py` 桥接位 |
| 3.3.2 指标监控 | ✅ 已实现 | `core/metrics.py` + `/metrics` 独立路由 |
| 2.2.3 / 3.1.4 Feed 分页优化 | ✅ 已实现 | W8 分页 SQL 下推，路由切片 grep=0 |
| 2.2.1 聚簇护栏 | ✅ 已实现 | 倒排预剪 + `MAX_CANDIDATES_DEFAULT` |
| 5.1.2 push_port.py 残留 | ✅ 已删除 | 全仓无 import（仅注释提及历史纪律） |
| 1.3.2~1.3.8 契约"提取" | 🔧 半真 | 6 域 dto.ts **已生成**；真实缺口是 index.ts 不导出+前端零消费（死代码接线，归 S3.4） |
| 4.1.1/4.1.2 README/CHANGELOG | ✅ 多轮已更 | 剩 v1.0 前复核，归 S4.2 |

### 0.2 修正——方向性错误，照做即引入缺陷

| 参考项 | 错误 | 正确方向 |
|---|---|---|
| 3.2.2 CORS 白名单（P0） | **加 CORS 是负收益**：`frontend/next.config.mjs` rewrites 同源代理，浏览器从不跨域直连后端；加 CORS 反而扩大攻击面 | **维持不加**，conventions 已固化该决策 |
| 1.1/1.2 迁移策略"逐域拆迁+保留旧代码" | backend/app 是完整 FastAPI 包（main→api→services→models 全链 import），把内部重排为 modules/<域> 且新旧并存 = **双源漂移**，违背单一来源 | S3 开工第一步读 `project-structure-design.md` 定目标形态；默认整体 `git mv backend→apps/api`（保 import 与历史），不搞域级新旧并存 |
| 2.2.2 评分分钟级 | hot_rescore 已每小时周期重评 + 落点即评，分钟级收益低、扫描成本翻倍 | 降 P3，仅当产品提出再排 |
| 5.2.2 多租户 / 5.2.3 插件化 | P3 超范围，无产品依据 | **显式排除**（需产品拍板单独立项） |

### 0.3 补遗——参考大纲遗漏的真实 P0（本方案主力）

| 项 | 证据 | 归口 |
|---|---|---|
| **S1 通知持久化四链路**（存储层已建但零接线=死表） | `web.py:54` 仅 publish；无 history/read 端点；`NotificationBell.tsx:53` 预留桩未接 | **S1（本轮开工）** |
| extra_config 明文 JSON（G10） | `bothot_entities.py:36`；secret_crypto 不覆盖 | S2.1 |
| 告警未启用（G11） | compose 无 ALERT_ 变量 | S2.2 |
| 域 DTO 接线（G14） | index.ts 仅导出 common 三型 | S3.4 |

### 0.4 吸收——参考大纲的真实增量

2.4.1 聚簇/评分用例补全（3+7→20+）、2.4.2 outbox 消费端到端用例、2.1.3 `PUSH_SCHEDULER_INTERVAL` env 化（默认 60 不变）、2.1.2 推送日志分页+过滤（P2）、5.1.1 embedding.py 处置（接入或删，S2 拍板）、3.1.x 性能基线留证（降级：无压测环境，承诺 EXPLAIN+耗时日志留证而非达标）、4.1.3/4.1.4 文档（归 S4.2）。

---

## 第一节 执行大纲（剩余全部）

### S1 通知持久化四链路（P0，本轮执行）
- **S1.1 写侧落库**：落库点在 `push_scheduler._execute_task`（session 在手、事务边界清晰，provider 层不碰 DB——比 v0.8 原案"改 web.py"更优）；`channel=="web" and ok` → INSERT Notification（`is_broadcast = not message.external_user_id`）；落库失败不阻断投递（structlog error）
  - a) scheduler 落库分支 b) web.py docstring 同步语义 c) 连库单测：投递→断言行
- **S1.2 读侧**：a) `GET /system/notifications/history`（`get_current_sub` + `get_db` + `limit_offset_query`） b) 过滤 `sub==me OR is_broadcast`，created_at 倒序 c) 响应 `{items,total,limit,offset,unread_total}` d) EXPLAIN 留证
- **S1.3 回执**：a) `PUT /system/notifications/read`（`{id}` 单条 / `{before}` 批量） b) 越权 → 404 语义 c) 单测三分支
- **S1.4 前端**：a) `notifications.ts` 增 `fetchHistory`/`markRead`（走 MOCK 网关） b) Bell 首连拉历史接 `mergeFromHistory` c) 展开下拉时 markRead + 服务端对账
- **S1.5 验收**：连库端到端 + vitest/typecheck 绿 + backlog NOTIF 回填

### S2 遗留拍板项（旁路）
- S2.1 extra_config AES 加密（迁移+读侧+SOP 增补）
- S2.2 告警启用（compose ALERT_ + 三类演练留证）
- S2.3 BotBinding 死表处置（产品拍板）｜S2.4 真后端 e2e 解阻（OIDC 白名单）｜S2.5 Ragflow/Saas 实接（主平台排期）｜S2.6 embedding.py 接入或删（拍板）｜S2.7 推送日志分页+过滤（P2）

### S3 v0.7 目录迁移（功能冻结后压轴）
- S3.1 形态定稿（**第一步读 project-structure-design.md**，默认整体 git mv）
- S3.2 backend→apps/api ｜ S3.3 frontend→apps/web ｜ S3.4 契约接线（index.ts 导出 6 域 + 前端消费 + gen_contracts 双向 diff 硬门禁）
- S3.5 infra/CI 路径 + 清 .gitkeep + 全量门禁
- S3.6 测试补全（聚簇/评分 20+ 例、outbox e2e；吸收参考 2.4.1/2.4.2）

### S4 v1.0 发布
- S4.1 全量门禁（pytest/vitest/mock e2e/compose-smoke/security 四扫描）
- S4.2 文档定稿（README/AGENTS/CHANGELOG v1.0 段/API OpenAPI/架构文档复核）
- S4.3 推送 GitHub aideanew/BotHot（当前 ahead 10；SSH 别名 + ls-remote 核验）+ tag

**执行序**：S1（本轮）→ S2.1/S2.2 → S3 → S4；S2.3–S2.5 等外部拍板随时插入。

## 第二节 验收
门禁全绿 + 通知全链实测（emit→落库→history→read→前端补投）+ 无死表 + 文档零漂移 + 禁改项（不加 CORS / 不碰原项目 / 不 git rm）。

## 第三节 前提与局限
隔离 PG 勿用 5433；S2.3–S2.5/S2.6 依赖外部拍板；性能项以留证替代达标（无压测环境）。
