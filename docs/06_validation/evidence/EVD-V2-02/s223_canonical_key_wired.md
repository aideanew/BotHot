# S2.2.3/S2.2.4/S2.3.1/S2.3.3：规范键接上生产者

批次：`STEP-02` 第二批，基线 `main@2987f46`（返工后）。读数标机器位
（`@win` = 本机 Win10 + `apps/api/.venv`，无 PostgreSQL：5432/5433 拒连、无 docker；`@ci` = GitHub Actions ubuntu-latest）。

## 1. 改动清单（含"为什么这样切"）

| 位置 | 改动 | 依据 |
|---|---|---|
| `app/services/kb.py:599` | `_article_key` → `canonical_article_key` 的薄委托（保留函数名） | S2.2.3.2。5 个取键点（`kb.py:241/282/461/467/510` 现读）全经此函数 ⇒ 卡面"逐处替换"收敛为 1 处；少改一处少一处回归面。 |
| `app/services/batch_ingest.py:44` | 同一委托；删掉本地末段算法 | S2.3.3（第二份手写副本是双源病） |
| `app/services/kb.py` `_ingest_url_inner` / `_find_source_by_anchor` | 新增可选 `legacy_key`（短链裸 token），资产等值与第三条锚各带一次**只读**旧键查询 | S2.2.4。命中不改写旧行——回填是 STEP-07 的活（ADR-0011 §6/§8、裁决 D-V9-01 默认值 A） |
| `tests/test_batch_ingest_key_drift.py`（新） | 两模块取键与真源逐字符相等 + 反证（旧算法必然与规范键分叉） | S2.3.3 的"漂移守卫用例" |
| `tests/test_idempotency_lock.py:130`、`tests/test_p0_asset_cache.py:64` | 测试内的第三/第四份算法复刻 → 改为 import 真源 | S2.3.1「只改键期望值，不改业务断言」 |
| `tests/test_d04_short_link.py` | 前提改为 `s:FINAL-KEY`，并钉住"映射键=裸 token / 文章身份=`s:token`"这条不对称 | 迁移后两形并存是 S2.2.4 存在的原因 |
| `tests/test_kb_multisource_anchor.py` | `assert key == "s"` → `assert key.startswith("b:")`；`"s"` 反查护栏改注为**回归**护栏 | S2.2.3.4 |
| `app/repositories/asset.py`、`app/contracts/resources.py`、`tests/fixtures/wechat_urls.py`、`test_kb_longlink_ingest.py` 头 | 注释/描述随行为更正；**行号锚一律换成符号名** | 行号每批都漂；`resources.py` 的 description 是契约产物的一部分，改后重新生成 |
| `tests/test_kb_longlink_ingest.py::test_two_distinct_long_links`（新） | P-3 探针转正：同号两篇 `fetch_count == 2`、同篇两书写**不得**多抓 | S2.2.3.3 |

## 2. 读数（全部在最后一次编辑之后取，`@win`）

- 调用面全集（`grep -rl "_article_key\|_find_source_by_anchor\|ingest_url\|canonical_article_key\|MIN_FRAGMENT_LEN\|get_by_source_external" tests/` 得 15 个测试文件）：
  **270 passed, 63 skipped**，88.20s，`PYTEST_RC=0`
- 静态 gate 五文件合跑：**227 passed, 2 skipped**
- `ruff check app tests` → `All checks passed!`；`mypy app` → `Success: no issues found in 112 source files`
- `gen_contracts.py --check` → `RC=0`，**10** 条幂等一致；`check_docs_consistency.py` → 通过
- `pytest --collect-only tests` → **1278 tests collected**（无 import 错）

## 3. 两个差点进 CI 的错误（都记下来，因为它们属于同一族）

1. **`SpaceRepository` 未 import**：新写的 PG 用例在本机 skip ⇒ 函数体从不执行，本地全绿
   （11 passed / 1 skipped）而 CI 会 `NameError`。被抓 purely 因为先跑了 `ruff check app tests`（F821）。
   我先用一个含未定义名的样本**确认 ruff 覆盖这一类**，才把安全寄托在它上面——
   "工具应该会抓到"不是证据。固化：ruff → mypy → pytest → collect-only。
2. **改一行契约描述会牵动产物**：`app/contracts/resources.py` 的 `description` 参与
   `packages/contracts/schemas/resources.schema.json` 的字节一致与稿-源比对，
   必须重生成后再判（本批重生成，`--check` 十条一致）。

## 4. 还没有被证明的部分（不写进结论）

63 条 skip 覆盖的正是这次改变行为的路径：短链二次入库 0 抓、旧裸 token 兜底命中、
`_ensure_source` 迁移后的建键、新转正的 P-3 用例。本机无 PG ⇒ 这些**只能由 `@ci` 判**（D-V4-01）。
本文件提交时 `@ci` 读数尚未回；`CI` 对 HEAD 的 run id + conclusion 记录在 `09-执行过程-独立执行段第二批.md` §7，
不在这里预填。
