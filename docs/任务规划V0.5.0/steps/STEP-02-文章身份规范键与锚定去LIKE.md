# STEP-02 文章身份规范键与锚定去LIKE

| 项 | 值 |
|---|---|
| 里程碑 | M1 |
| 档位 | sonnet |
| 规模 | 中（约 1.5 人日） |
| 依赖 | S2.1.x：STEP-00C；S2.2 起：STEP-01（ADR-0011） |
| 裁决 | D-V2-01、D-13 |
| 剩余原子任务 | 6（👤 0）——S2.1.4/S2.1.5 已于第十三轮交付，见下表 ✅ 与 EVD-V2-02 §4.14 |
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

### S2.1 共同部分（不依赖 D-V2-01，立即可做）——第十三轮已交付
- **S2.1.4** ✅🛠 `_find_source_by_anchor` 删除 LIKE 兜底；锚查询加 `.limit(1)` 且 biz 源优先
  - S2.1.4.1 ✅ P-4 探针转常驻用例 `apps/api/tests/test_kb_multisource_anchor.py::test_multi_source_no_crash`
    （改前红的实测读数引 `docs/任务规划V0.3.0/evidence/probes_4afaedd.txt:19`；本机不可跑 ⇒ EVD-V2-02 §5 J-6）
  - S2.1.4.2 ✅ 删兜底那一段；旧 `kb.py:354-361` 的行号随上下文移动，现读用
    `git diff --stat 78e3378 -- apps/api/app/services/kb.py` 与 `grep -n '\.like(' apps/api/app/services/kb.py`
    （后者必须为空；本机由结构面 AF-S1/S6 机检，不靠人眼读 diff）
  - S2.1.4.3 ✅ 本机侧 AF-B1…B5 全绿；连库侧另加 `test_biz_anchor_wins_when_both_anchors_exist`
    （判**顺序**：两条锚源同时存在时返回 biz 那条）
- **S2.1.5** ✅🛠 `get_by_url_fragment` 守卫：片段长度 <8（`MIN_FRAGMENT_LEN`）时直接返回 None 并记 WARNING
  - S2.1.5.1 ✅ 单测 `apps/api/tests/test_asset_fragment_guard.py`：`s` ⇒ None 且**零条 SQL**、
    正常 token ⇒ 命中、边界卡在 8/7、放行路径仍是 `source_id eq + url like + limit(1)`
    （本机不可跑 ⇒ §5 J-7；本机侧等价证明 AF-A1…A5）
  - 卡面那句「或等于 `s` 时」按长度阈值实现：`s` 是长度 1，已被 `<8` 覆盖，不再单列特判
    （单列会让守卫在下一个单字符键形上再次失效——登记为口径说明，不是打折）
  - **代价要说清**：`kb.py:245/:284` 两处调用点传的正是 `article_key`，长链场景它是 `s` ⇒
    这条兜底从此在该场景**恒定放弃**，存量「biz 锚源 + article_key 资产」的缓存命中会退化为
    一次真实重抓、版本比对少一次陈旧参照。选择的是正确性优先于命中率（宁可重抓也不能命中错文章）；
    S2.2 规范键落地后这条兜底应由真正的键替代，届时本条代价自然消失。
- 处置批本身的账在 `docs/06_validation/evidence/EVD-V2-02/README.md` §4.14（五条：驱动崩栈、
  头部现算第二次欠账、指针指空、两处锚随代码漂、卡面 S2.1.4.3 的连库侧补条）。

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
