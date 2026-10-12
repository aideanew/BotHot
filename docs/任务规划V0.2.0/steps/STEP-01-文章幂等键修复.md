---
id: STEP-01
title: 文章幂等键修复（canonical article key）
priority: P0
depends: STEP-00；裁决 D-V2-01（S1.3 起）、D-V2-06（S1.4.3）
estimate: 2 人日
---

# STEP-01 文章幂等键修复

## 目标
同一公众号的不同长链文章得到不同资产键；同一篇文章的 URL 变体得到相同资产键；任何入库路径不再因 `LIKE '%s%'` 崩溃或冒名。

## 依据（02 §D-01、§D-01b）
- `services/kb.py::_article_key`（`:554`）长链恒得 `"s"`；探针 P-3：`fetch_count=1, B.hitCache=True, same_doc=True`。
- `services/kb.py::_biz_from_url`（`:587`）只读 `biz` 不读 `__biz`；`_find_source_by_anchor`（`:336`）LIKE 兜底；探针 P-4：`MultipleResultsFound`。
- 复算：`cd apps/api && .venv/bin/python -c "from app.services.kb import _article_key as k; print(k('https://mp.weixin.qq.com/s?__biz=X&mid=1&idx=1&sn=a'))"` → `s`

## 前置裁决
D-V2-01：键格式。推荐 `b:{biz}:{mid}:{idx}` → `s:{token}` → `h:{sha256(规范化URL)[:32]}`（理由见 03 §C-01）。**未批准前只允许做 S1.1、S1.2。**

## 允许修改
`apps/api/app/services/article_identity.py`（新）、`apps/api/app/services/kb.py`、`apps/api/app/repositories/asset.py`（仅 `get_by_url_fragment`）、`apps/api/scripts/backfill_article_keys.py`（新）、`apps/api/scripts/missing_articles_report.py`（新）、`apps/api/tests/test_article_identity.py`（新）、`apps/api/tests/test_kb_longlink_ingest.py`（新）、`apps/api/tests/test_backfill_article_keys.py`（新）、`apps/api/tests/test_d04_short_link.py`（仅 `:25` 的键口径断言）、`apps/api/tests/test_idempotency_lock.py` 与 `apps/api/tests/test_p0_asset_cache.py`（仅各自本地复刻的 `_article_key` 辅助函数 `:130`/`:64`，改为 `from app.services.article_identity import canonical_article_key`）、`docs/06_validation/evidence/EVD-V2-01/**`
## 禁止修改
`manifest.py`、`subscription.py`、`job_worker.py`、`providers/**`、`models/**`、`alembic/**`（本 STEP 无 DDL）、既有测试文件（夹具修正属 STEP-09）。

## 原子任务

| 编号 | 类型 | 动作 | 验收命令 |
|---|---|---|---|
| S1.1.1 | 👤🗄 | 生产只读副本执行审计 SQL（见下），输出入 EVD-V2-01 | 人工；EVD 文件存在且含 4 个计数 |
| S1.1.2 | 👤 | 抽 20 条 `article_manifests.url` 判定 RedFox 形态（关闭 U-01） | 人工；EVD 记录长/短链比例 |
| S1.2.1 | 🔴 | `test_article_identity.py`：①LONG_A≠LONG_B ②LONG_A==LONG_A_TRACKING ③SHORT_1 以 `s:` 开头 ④OFFSITE 以 `h:` 开头 ⑤MALFORMED_LONG 以 `h:` 开头 ⑥键长 ≤128 | 改前 `pytest tests/test_article_identity.py -q` 因模块不存在 ERROR（rc≠0） |
| S1.2.2 | 🔴 | `test_kb_longlink_ingest.py::test_two_distinct_long_links_both_fetched`（探针 P-3 转正：`fetch_count==2`、docId 不同） | 改前 FAIL |
| S1.2.3 | 🔴 | 同文件 `test_long_link_with_multiple_sources_no_crash`（探针 P-4 转正） | 改前 FAIL（MultipleResultsFound） |
| S1.2.4 | 🔴 | 同文件 `test_biz_from_url_reads_double_underscore_biz` | 改前 FAIL |
| S1.3.1 | 🛠 | 新模块：`parse_wechat_url`、`canonical_article_key`；规范化 = 小写 host、去 fragment、query 键排序、去 `scene/chksm/sessionid/key/ascene/devicetype/version/pass_ticket` 等追踪参数 | S1.2.1 绿 |
| S1.3.2 | 🛠 | `kb._article_key` 委托新函数；`_biz_from_url` 依次读 `__biz`、`biz` | S1.2.4 绿 |
| S1.3.3 | 🛠 | `_find_source_by_anchor`：biz 精确 → `ShortLinkMap.biz`（短链）→ None；删除 `Source.url LIKE` 分支 | S1.2.3 绿；`grep -n "Source.url.like" app/services/kb.py` 无输出 |
| S1.3.4 | 🛠 | `get_by_url_fragment`：`len(fragment) < 8` 直接返回 None；调用方仅在键以 `h:` 开头或历史兼容时调用 | 新增单测：`fragment="s"` 返回 None |
| S1.3.5 | 🛠 | `kb.py:276` 处 `final_key` 改 canonical | S1.2.2 绿；`tests/test_d04_short_link.py:25` 断言 `_article_key('…/s/FINAL-KEY') == 'FINAL-KEY'` 会因 `s:` 前缀变红 ⇒ 同步改为 `== 's:FINAL-KEY'`（已列入允许路径） |
| S1.3.6 | 🛠 | 两个测试文件内**复刻**了旧 `_article_key` 逻辑（`test_idempotency_lock.py:130`、`test_p0_asset_cache.py:64`），用旧键直查资产 ⇒ S1.3.2 后必红；改为导入 canonical 函数（只改辅助函数，不改用例语义） | `grep -n "def _article_key" apps/api/tests/*.py` 无输出；两文件全绿 |
| S1.4.1 | 🗄 | `backfill_article_keys.py`：`--dry-run`（默认）/`--apply`、`--batch 500`；按 `content_assets.url` 重算；冲突（同源同新键多行）写 CSV 并跳过 | `python scripts/backfill_article_keys.py --dry-run --dsn $AIDEANBOT_TEST_PG_DSN` rc=0 |
| S1.4.2 | 🔴✅ | `test_backfill_article_keys.py`：造 3 行（2 行冲突）⇒ 改 1 行、报告 1 组冲突、二次运行 0 改动（幂等） | 绿 |
| S1.4.3 | 👤🗄 | 生产：dry-run 报告入 EVD → D-V2-06 批准 → `--apply` | 人工 |
| S1.5.1 | 🛠 | `missing_articles_report.py`：`(job_items.url ∪ article_manifests.url)` 的 canonical key − `content_assets` 键 ⇒ CSV | 隔离库造数单测：缺 2 篇则 CSV 2 行 |
| S1.6.1 | ✅ | 全量回归 + 探针复跑 | `pytest tests -q`；`evidence/probe_longlink_collision.py` 输出 `fetch_count= 2 … same_doc= False`；`probe_multisource_crash.py` 输出 `PROBE2 ok False` |

### S1.1.1 审计 SQL（只读）
```sql
SELECT count(*) AS assets_key_s FROM content_assets WHERE external_id = 's';
SELECT count(*) AS assets_versioned FROM content_assets WHERE version > 1;
SELECT count(*) AS shortmap_key_s FROM short_link_maps WHERE article_key = 's';
SELECT count(*) AS sources FROM sources WHERE type = 'wechat_oa';
SELECT left(url, 40) AS url_prefix, count(*) FROM article_manifests GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
```

## 完成定义
S1.2.* 全绿；全量 pytest 无回退；两个探针达到"修复后期望"；EVD-V2-01 含审计结果与回填 dry-run 报告。

## 回滚
代码：`git revert`。数据：回填脚本 `--apply` 前自动导出 `(id, old_external_id)` CSV；回滚脚本按 CSV 还原。

## 风险
- 键格式变化的外部影响：已核前端 `grep -rn "external_id\|externalId" apps/web/lib apps/web/app` 为 0；后端其他消费者（热点聚簇、推送模板变量）在 S1.3 前再 `grep -rn "\.external_id" app/services` 复核一次。
- 删除 LIKE 兜底可能让 "BE-02 D-2/D-3 历史遗留"数据二次入库不命中缓存 ⇒ 多一次免费直抓，可接受；由回填脚本把历史资产键统一后消失。
