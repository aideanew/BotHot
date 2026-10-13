# STEP-02 文章身份规范键与锚定去LIKE

| 项 | 值 |
|---|---|
| 里程碑 | M1 |
| 档位 | sonnet |
| 规模 | 中（约 1.5 人日） |
| 依赖 | S2.1.x：STEP-00C；S2.2 起：STEP-01（ADR-0011） |
| 裁决 | D-V2-01、D-13 |
| 剩余原子任务 | 9（👤 0） |
| 所有权（写） | W：apps/api/app/services/article_identity.py、kb.py、batch_ingest.py、repositories/asset.py；apps/api/tests/test_article_identity.py、test_kb_longlink_ingest.py、test_kb_multisource_anchor.py（新）及复刻旧键的 3 个测试文件 |
| 基线 | main@65f508b |

## 1. 目标与可证伪验收
- P-4：多源时不再 `MultipleResultsFound`（500 路径关闭）。
- P-3：同号两篇不同长链 ⇒ `fetch_count=2`、`B.hitCache=False`、`same_doc=False`。
- 全仓文章键只有一个定义（`canonical_article_key`），kb 与 batch_ingest 结果恒等。

## 2. 证据链（现状）
- kb.py:554-557 `_article_key` 去 query 取末段；调用点 kb.py:235/:276/:426/:432/:471、batch_ingest.py:44/:137。
- kb.py:354-361 `Source.url.like(f"%{article_key}%")` + `scalar_one_or_none()`。
- repositories/asset.py:36-44 `get_by_url_fragment` 仅判空串。
- 探针 P-3/P-4 在 65f508b 复现（probes_65f508b.txt）。
- 已完成：S2.1.1/S2.1.2（78e3378，article_identity 100% 覆盖）、S2.1.3（c10b229/b45777a）。

## 3. 执行逻辑穿透
见 02 §2.1。修复顺序：先去 LIKE（不依赖键格式，立刻消除 500）→ 片段守卫 → 引入规范键 → 6 个调用点委托 → 短链映射写规范键 → 历史裸 token 只读兼容。

## 4. 原子任务（三级编号；缩进为四级执行步）

标记：🔴 先红（写失败测试）｜🛠 实现｜✅ 验证/读数｜📄 文档｜🗄 数据/迁移｜👤 人工/裁决

### S2.1 共同部分（不依赖 D-V2-01，立即可做）
- **S2.1.4** 🔴🛠 `_find_source_by_anchor` 删除 LIKE 兜底；锚查询加 `.limit(1)` 且 biz 源优先
  - S2.1.4.1 把 P-4 探针转常驻用例 test_kb_multisource_anchor.py（改前红：MultipleResultsFound）
  - S2.1.4.2 删 kb.py:354-361
  - S2.1.4.3 转绿；另加“已有 biz 源时优先命中 biz 源”用例
- **S2.1.5** 🔴🛠 `get_by_url_fragment` 守卫：片段长度 <8 或等于 `s` 时直接返回 None
  - S2.1.5.1 单测：片段 `s` ⇒ None；正常 token ⇒ 命中

### S2.2 规范键（依赖 ADR-0011）
- **S2.2.1** 🔴 test_article_identity.py 增 `canonical_article_key` 用例：长链同篇不同追踪参数同键、同号不同 mid 异键、短链 `s:`、非微信 host `h:`、任何输入 ≠ `s`
- **S2.2.2** 🛠 article_identity.py 实现 `canonical_article_key` 与 `normalize_url`（基于 parse_wechat_url）
  - S2.2.2.1 S2.2.1 转绿
  - S2.2.2.2 模块覆盖率保持 100%
- **S2.2.3** 🛠 kb.py 5 处调用点委托规范键；`_save_short_link` 写规范键
  - S2.2.3.1 kb.py:235/:276/:426/:432/:471 逐处替换
  - S2.2.3.2 `_article_key` 改为薄委托（保留名字，避免外部 import 断裂）
  - S2.2.3.3 P-3 探针转正为 test_kb_longlink_ingest.py::test_two_distinct_long_links（期望 fetch_count=2）
- **S2.2.4** 🛠 历史兼容：规范键未命中且为短链时，用旧裸 token 只读再查一次（不改写）
  - S2.2.4.1 单测：预置旧键资产 ⇒ 短链二次入库仍 0 抓取

### S2.3 回归
- **S2.3.1** 🛠 更新复刻旧键算法的测试辅助函数（只改键期望值，不改业务断言）
  - S2.3.1.1 `grep -rn '_article_key\|rsplit("/"' apps/api/tests`
  - S2.3.1.2 逐处替换为 canonical
- **S2.3.3** 🛠 batch_ingest._article_key 委托 `canonical_article_key`，并加漂移守卫用例（kb 与 batch_ingest 对 LONG_A/LONG_B/SHORT_1 结果一致）
  - S2.3.3.1 与 S2.2.3 同一 PR
- **S2.3.2** ✅ P-3/P-4 复跑达“修复后期望”；全量双环境 0 failed；ruff/mypy/CI 双绿

## 5. 测试设计
- 新增：test_kb_multisource_anchor.py（3 条）、canonical 用例（约 10 条）、漂移守卫（3 条）、历史兼容（2 条）。
- 连库用例沿用 conftest 门禁；纯函数用例离线可跑。

## 6. 停止条件与回滚
- 规范键切换导致既有用例大面积红（>10 条非键期望类）：停止，回到 S2.2.1 补齐不变量再继续。
- 回滚：S2.1 与 S2.2 分 PR；S2.2 revert 后 S2.1 仍独立有效。

## 7. 交付证据
EVD-V2-02（追加）：P-3/P-4 前后读数、覆盖率、CI run id。

## 8. 完成定义（本卡）
所有权内 diff 与任务一致 ∧ 每个 ✅ 有读数 ∧ 本地 `ruff check app tests`（0.12.12）与 `gitleaks detect` 通过 ∧ 推送后 CI 与 Security 均 success（run id 入 EVD）∧ 复审 ≤2 轮（D-14）。
