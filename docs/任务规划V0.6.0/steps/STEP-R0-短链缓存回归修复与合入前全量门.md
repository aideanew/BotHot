# STEP-R0 短链缓存回归修复与合入前全量门

| 项 | 值 |
|---|---|
| 里程碑 | M0（最高优先） |
| 档位 | sonnet |
| 规模 | 小（约 0.5 人日） |
| 依赖 | —（先于或与 00C 同 PR） |
| 裁决 | — |
| 剩余原子任务 | 7（👤 1） |
| 所有权（写） | W：apps/api/app/services/kb.py（仅 `_find_source_by_anchor`）、apps/api/alembic/versions/ab1006r0a_*.py（新，可选）、apps/api/tests/test_kb_multisource_anchor.py、test_be02_engine_routing.py（只读）；docs/04_engineering/collaboration-discipline.md |
| 基线 | main@a9b194d |

## 1. 目标与可证伪验收
- `test_be02_engine_routing.py::test_short_link_second_ingest_hits_cache_via_url_fallback` 恢复绿：短链（不带 `__biz`）二次入库 `fetch_count==1`、`hitCache=True`、`docId` 相同。
- P-4 不回退：多源时仍不抛错，且代码里不再出现 `LIKE`。
- P-3 不被掩盖：长链键 `"s"` 不能触发新增的反查（长度守卫），P-3 仍由 STEP-02 S2.2 修复。
- 流程：业务代码提交必须附依赖环境全量 pytest 读数，「本机跑不起来」不能作为免跑理由。

## 2. 证据链（现状）
- a9b194d 全量：`1 failed, 1044 passed, 5 skipped`，失败的是 test_be02_engine_routing.py:301 `assert 2 == 1`（evidence/a9b194d/pytest_full_pg_a9b194d.txt:17-72）。
- 同一用例在 65f508b worktree 上 `1 passed`（regression_bisect_a9b194d.txt）⇒ 回归由 078dc30 引入。
- 根因：078dc30 删除的 `Source.url.like('%article_key%')` 兜底同时承担着「无参短链 + 页面 biz 源」场景：`_ensure_source` 用页面 biz 建源（kb.py:471），资产键是短链 token；二次入库时 URL 里解不出 biz（短链没有 `__biz`），用 article_key 锚也对不上 ⇒ source=None ⇒ 跳过缓存（kb.py:240）⇒ 每次重抓。078dc30 的提交说明只论证了长链（「S2.1.3 后长链能解出 __biz」），漏掉了短链。
- 为什么没被拦住：CI backend 卡在 ruff（:67），pytest 已经 22 次没跑（ci_runs_a9b194d.txt）；执行机没装依赖，06 执行记录 §4 写着连库用例「不由本会话执行」。
- 次生影响：版本管理（kb.py:281-288 `stale` 查找）也依赖 source，短链改文不再标 superseded。

## 3. 执行逻辑穿透
修复方案（已在 a9b194d 的临时 worktree 实测，patch 见 evidence/a9b194d/STEP-R0_regression_fix_simulated.patch）：
`_find_source_by_anchor` 在两条锚都未命中后，加第三条**精确等值**反查：
`select(Source).join(ContentAsset, ContentAsset.source_id == Source.id).where(Source.type == 'wechat_oa', ContentAsset.external_id == article_key).limit(1)`，并且只在 `len(article_key) >= MIN_FRAGMENT_LEN` 时执行。
- 为什么用等值不用 LIKE：资产键就是 article_key，等值就能命中，不存在「一个字母命中全表」的问题。
- 为什么要长度守卫：长链键现在是 `"s"`，没有守卫的话 `"s"` 会反查到任意长链资产，P-3 的冒名问题会扩散到跨源。
- 被否决的方案：①恢复 LIKE（P-4 会回来）②`Source.url == url`（源只记首篇 URL，第二篇短链对不上）③只靠短链映射表（`_save_short_link` 只在 `final_key != short_key` 时写，直抓后 URL 不变的场景写不进去）。
- 性能：`uq_asset_source_external(source_id, external_id)` 的前导列是 source_id，只按 external_id 查不走这个索引 ⇒ 资产量上来后要加 `ix_content_assets_external_id`（R0.3）。
实测：修复后全量 `1045 passed, 5 skipped, 0 failed`，ruff/mypy 0 问题，P-4 探针不崩。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### R0.1 锁定回归
- **R0.1.1** ✅ 在 EVD-V2-R0 记录二分证据：a9b194d 红、65f508b 绿（同一条命令、同一个库）
  - R0.1.1.1 命令：`pytest tests/test_be02_engine_routing.py -k short_link_second -q`

### R0.2 修复
- **R0.2.1** 🛠 `_find_source_by_anchor` 加第三条资产反查（精确等值 + `MIN_FRAGMENT_LEN` 守卫 + `.limit(1)`）
  - R0.2.1.1 kb.py import `ContentAsset`、`MIN_FRAGMENT_LEN`（从 repositories/asset 导入，不另定义）
  - R0.2.1.2 docstring 更正：说明第三条锚负责的场景（无参短链 + 页面 biz 源）
- **R0.2.2** 🔴✅ test_kb_multisource_anchor.py 新增 2 条：①键 `"s"` 不触发反查（预置一条 external_id=`s` 的资产，入库 LONG_B 时 source 仍为 None 或 biz 源，SQL 记录里没有 join content_assets）②反查命中时返回资产所属源
  - R0.2.2.1 变异：删掉长度守卫 ⇒ 用例①红
- **R0.2.3** ✅ 全量连库 pytest 0 failed；P-4 探针 `PROBE2 ok`；`grep -n "like(" app/services/kb.py` 为空

### R0.3 索引（数据量门槛触发）
- **R0.3.1** 🗄 迁移 ab1006r0a：`CREATE INDEX CONCURRENTLY ix_content_assets_external_id ON content_assets(external_id)`
  - R0.3.1.1 与 STEP-04 迁移号 ab1006c1a 串行（down_revision 指向 ab1006r0a），单头门禁通过
  - R0.3.1.2 `EXPLAIN` 显示 Index Scan，读数入 EVD

### R0.4 合入前全量门（治理）
- **R0.4.1** 📄 collaboration-discipline 增一条：改 `apps/api/app/**` 的提交，提交说明或 EVD 里必须有依赖环境 `pytest tests/ -q` 末行读数；没有就不合入
- **R0.4.2** 👤 执行机二选一：装 venv（`uv sync --extra dev` + 本地 PG）或固定把全量跑交给有依赖的沙箱，在 decision-log 里登记

## 5. 测试设计
- 既有：test_be02_engine_routing.py::test_short_link_second_ingest_hits_cache_via_url_fallback（回归哨兵，不改）。
- 新增：test_kb_multisource_anchor.py 2 条。

## 6. 停止条件与回滚
- 若反查导致其他用例红：说明有数据依赖「源找不到」这个结果，停下来逐条分析，不加条件绕过。
- 回滚：单文件 revert；不要回退到 LIKE。

## 7. 交付证据
EVD-V2-R0：二分读数、修复前后全量读数、变异反证、EXPLAIN。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
