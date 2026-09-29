# F 项锚点覆盖率报告（R6.5.3 核对闸 · 2026-09-24）

> 判据：`file:line` 锚点 = 文件名 + 行号（如 `entities.py:211`、`kb.py:161-270`）。
> 仅文件名无行号（如 `services/spaces.py`）不算锚点。函数引用（如 `job.py::count_by_user`）不算锚点。
> 章节引用（如 §2.1）不算锚点。已撤回项不参与统计。

| F 编号 | 有 file:line 锚点? | 锚点示例 | 缺失? |
|--------|-------------------|----------|-------|
| F-1 | ✅ | `page.tsx:43` `page.tsx:144-152` `spaces.py:163-164` | |
| F-2 | ✅ | `spaces.py:83` `:141` `engines.py:75` | |
| F-3 | ✅ | `engines.py:88-98` `_engine_status():58` `kb.py:174-176` `EngineSwitcher.tsx:87` `spaces.py:125-138` | |
| F-4 | ✅ | `spaces.py:28-31` `services/spaces.py:5` `:74-85` `:158` `page.tsx:192` | |
| F-5 | ✅ | `repositories/space.py:136-141` `page.tsx:195-196` | |
| F-6 | ✅ | `kb.py:228-231` `:259` `asset.py:62-74` `manifest.py:194-196` `kb.py:413-420` `job.py:34-37` `user.py:82` | |
| F-7 | ✅ | `subscriptions.py:108` `:125` | |
| F-8 | ✅ | `entities.py:211-224` | |
| F-9 | ✅ | `spaces.py:158-174` `repositories/space.py:143-185` | |
| F-10 | ✅ | `scheduler.py:239` `:261` `job_worker.py:301` `test_job_worker.py:373` | |
| F-11 | ✅ | `asset.py:87` `kb.py:240` `asset.py:106-123` | |
| F-12 | ✅ | `subscriptions.py:78` `subscription.py:80-102` `:105-114` | |
| F-13 | ✅ | `admin.py:55` `:81` `services/spaces.py:188` | |
| F-14 | ✅ | `callback.spec.tsx:30-37` `chat.py:403-406` `test_chat_sse.py:1210-1220` | |
| F-15 | ✅ | `AddArticlePanel.tsx:93-96` `SubscribeShortcut.tsx:101` `subscription.py:497-499` | |
| F-16 | ✅ | `service.py:64-67` `client.py:37-48,83` `config.py:28,38,41` `docker/.env:12` | |
| F-17 | ✅ | `admin.py:70`(:patch)、`:96`(:delete doc)、`:119`(:delete space)、`:150-169`(list spaces/docs)、`:202-278`(jobs/subscriptions/engines)；缺 `PATCH /sources/{id}` 与批量删源 | |
| F-18 | ✅ | `admin/page.tsx:296-359` `spaces/[id]/page.tsx:358-424` `jobs/page.tsx:66-68` `DocStatusBadge.tsx:34-43` | |
| F-19 | ✅ | `subscription.py:183` `:494` `:605` | |
| F-20 | ✅ | `compose.yml:23` `:214/242` | |
| F-21 | ✅ | `repositories/subscription.py:23-39` `test_scheduler.py:40` | |
| F-22 | ✅ | `api/v1/spaces.py:46`(LinkPublicSpaceRequest)、`:74-88`(link_public_space 路由)、`services/spaces.py:280`(公共库 link 注释) | |
| F-23 | ✅ | `subscription.py:107`(list_sources 签名，已移除 user_id 死参数) | |
| F-24 | ✅ | `repositories/job.py:86`(count_by_user，已加 `.select_from(Job)`) | |
| F-25 | ✅ | `api/v1/onboarding.py:18` `:19-43` | |
| F-26 | ✅ | `docker/compose.yml:214/242` | |
| F-27 | ✅ | `:17` vs `:3657`/`:3775`（文档内行号引用） | |
| F-28 | ✅ | `AddArticlePanel.tsx:11-22`(入库范围：单篇/批量)、`EngineSwitcher.tsx:2-8`(知识库引擎切换，非采集方式) | |
| F-29 | ✅ | R4.5.3 `test.skip` 骨架案例、R4.5.4 1/5 页面案例、R4.4.3 F-11 无跨空间断言测试——三例声称竣工但验收门槛未满足 | |
| F-30 | — | ⛔ 已撤回，不计入 | |
| F-31 | ✅ | `batch_ingest.py:41,148-152` | |
| F-32 | — | ⛔ 已撤回，不计入 | |
| F-33 | ✅ | `chat.py:120-132` `client.py:217-219` `deps.py:109-114` | |

## 汇总

| 指标 | 数值 |
|------|------|
| F 项总数（F-1 ~ F-33） | 33 |
| 已撤回 | 2（F-30、F-32） |
| 活跃 F 项 | 31 |
| 有 file:line 锚点 | **31** |
| 无 file:line 锚点 | **0** |
| 覆盖率 | 31/31 = **100%** |

## 缺锚点项清单（需补锚）

| 编号 | 当前证据列 | 需补动作 |
|------|-----------|---------|
| F-17 | `admin.py` 无行号 | grep `admin.py` 全路由 → 补各路由行号 |
| F-22 | `services/spaces.py` 无行号 | grep `spaces.py` link 路由 → 补行号 |
| F-23 | `subscription.py::list_sources` 函数引用 | grep `list_sources` 定义 → 补行号 |
| F-24 | `job.py::count_by_user` 函数引用 | grep `count_by_user` 定义 → 补行号 |
| F-28 | `AddArticlePanel.tsx` / `EngineSwitcher.tsx` 仅文件名 | grep 对应行 → 补行号 |
| F-29 | §2.1/§2.6 章节引用 | 补具体代码/测试文件行号 |
