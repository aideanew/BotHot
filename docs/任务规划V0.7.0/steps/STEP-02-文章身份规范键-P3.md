# STEP-02 文章身份规范键-P3

| 项 | 值 |
|---|---|
| 里程碑 | M1 |
| 档位 | sonnet |
| 规模 | 中（约 1.25 人日） |
| 依赖 | STEP-R0；S2.2 起：STEP-01（ADR-0011） |
| 裁决 | D-V2-01、D-13 |
| 剩余原子任务 | 7（👤 0） |
| 所有权（写） | W：apps/api/app/services/article_identity.py、kb.py、batch_ingest.py、repositories/asset.py；apps/api/tests/test_article_identity.py、test_kb_longlink_ingest.py、test_kb_multisource_anchor.py（新）及复刻旧键的 3 个测试文件 |
| 基线 | main@a9b194d |

## 1. 目标与可证伪验收
- P-3：同号两篇不同长链 ⇒ `fetch_count=2`、`B.hitCache=False`、`same_doc=False`。
- 全仓文章键只有一个定义（`canonical_article_key`），kb 与 batch_ingest 结果恒等。
- `test_kb_multisource_anchor.py:75` 的前提断言 `key == "s"` 按计划翻转（它是专门留着在键口径变化时报警的）。

## 2. 证据链（现状）
- 已完成：S2.1.1/S2.1.2（78e3378）、S2.1.3（c10b229…62446ab）、**S2.1.4/S2.1.5（078dc30）**：LIKE 兜底已删、两条锚 `.limit(1)`、`get_by_url_fragment` 加 `MIN_FRAGMENT_LEN=8`。P-4 探针在 a9b194d 输出 `PROBE2 ok`（probes_a9b194d.txt）——**P-4 已关闭**。
- 但 078dc30 带入短链缓存回归，由 STEP-R0 修。
- P-3 在 a9b194d 仍复现：`fetch_count=1 A.hitCache=False B.hitCache=True same_doc=True`。冒名路径：S2.1.3 之后长链能解出 biz ⇒ biz 锚命中源 ⇒ `get_by_source_external(source, "s")` 精确命中 A 的资产（kb.py:241）。片段守卫拦的是 LIKE 路径，拦不住这条等值查询，所以 P-3 只能靠换键修。
- 键定义 kb.py:554-557 `_article_key` 仍是取末段；调用点 kb.py:235/:276/:426/:432/:471、batch_ingest.py:44/:137。

## 3. 执行逻辑穿透
根因已收窄到一处：长链键恒为 `"s"`。修复顺序：引入规范键 → 6 个调用点委托 → 短链映射写规范键 → 历史裸 token 只读兼容 → R0 的反查守卫随之自然生效（规范键都 ≥8 字符，带 `b:` 前缀）。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S2.2 规范键（依赖 ADR-0011）
- **S2.2.1** 🔴 test_article_identity.py 增 `canonical_article_key` 用例：长链同篇不同追踪参数同键、同号不同 mid 异键、短链 `s:`、非微信 host `h:`、任何输入 ≠ `s`
- **S2.2.2** 🛠 article_identity.py 实现 `canonical_article_key` 与 `normalize_url`（基于 parse_wechat_url）
  - S2.2.2.1 S2.2.1 转绿
  - S2.2.2.2 模块覆盖率保持 100%
- **S2.2.3** 🛠 kb.py 5 处调用点委托规范键；`_save_short_link` 写规范键
  - S2.2.3.1 kb.py:235/:276/:426/:432/:471 逐处替换
  - S2.2.3.2 `_article_key` 改为薄委托（保留名字，避免外部 import 断裂）
  - S2.2.3.3 P-3 探针转正为 test_kb_longlink_ingest.py::test_two_distinct_long_links（期望 fetch_count=2）
  - S2.2.3.4 `test_kb_multisource_anchor.py:75` 前提断言改为 `key.startswith("b:")`；`test_asset_fragment_guard.py` 的 8/7 边界用例保持不变
- **S2.2.4** 🛠 历史兼容：规范键未命中且为短链时，用旧裸 token 只读再查一次（不改写）
  - S2.2.4.1 单测：预置旧键资产 ⇒ 短链二次入库仍 0 抓取

### S2.3 回归
- **S2.3.1** 🛠 更新复刻旧键算法的测试辅助函数（只改键期望值，不改业务断言）
  - S2.3.1.1 `grep -rn '_article_key\|rsplit("/"' apps/api/tests`
  - S2.3.1.2 逐处替换为 canonical
- **S2.3.3** 🛠 batch_ingest._article_key 委托 `canonical_article_key`，并加漂移守卫用例（kb 与 batch_ingest 对 LONG_A/LONG_B/SHORT_1 结果一致）
  - S2.3.3.1 与 S2.2.3 同一 PR
- **S2.3.2** ✅ P-3 复跑达“修复后期望”；P-4 与 R0 哨兵保持绿；全量 0 failed；ruff/mypy/CI 双绿

## 5. 测试设计
- 新增：canonical 用例（约 10 条）、漂移守卫（3 条）、历史兼容（2 条）、P-3 常驻用例（1 条）。
- 已存在：test_kb_multisource_anchor.py（2 条 + R0 新增 2 条）、test_asset_fragment_guard.py。

## 6. 停止条件与回滚
- 规范键切换导致既有用例大面积红（>10 条非键期望类）：停止，回到 S2.2.1 补齐不变量再继续。
- 回滚：S2.1 与 S2.2 分 PR；S2.2 revert 后 S2.1 仍独立有效。

## 7. 交付证据
EVD-V2-02（追加）：P-3/P-4 前后读数、覆盖率、CI run id。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
