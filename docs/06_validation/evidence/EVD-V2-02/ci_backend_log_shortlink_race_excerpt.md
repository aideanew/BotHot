# CI 后端日志摘录 — 短链映射竞态（`uq_shortlink_key`）

> 用途：把"这条洞早就在、只是靠时序间歇暴露"这个前提**存档**，而不是留在叙述文字里。
> 取数方式：GitHub REST `/repos/aideanew/BotHot/actions/jobs/<job>/logs`（token 由
> `git credential fill` 现取、用完即删，本文件不含任何凭据形）。
> 本机无 `gh`（见 `docs/04_engineering/collaboration-discipline.md` 的工具口径与 D-V6-02：
> 无 gh 时抄录原始响应行即算 `采信[REMOTE]`）。

## 1. 红的那次（修复前）

- run **38908795127**（workflow `CI`，head `76424cc`，branch `main`）→ conclusion **failure**
- job **116999065891**（`backend`）→ 失败步 `Tests (pytest) + coverage + skip gate`

```
E       AssertionError: 并发竞态不得未捕获异常冒泡（应被生产兜底收敛），实际 [('B', 'IntegrityError:
E         (psycopg.errors.UniqueViolation) duplicate key value violates unique constraint
E         "uq_shortlink_key"  DETAIL:  Key (short_k…')]
```

（原文一行截断处即日志原样，未补写。）

## 2. 绿的那次（同一用例，更早的 head）

- run **38904912095**（workflow `CI`，head `b84dc53`）→ conclusion **success**
- job **116985940757**（`backend`）

```
1303 passed, 6 skipped, 1 warning in 93.02s (0:01:33)
skip 门禁：total_skipped=6 baseline=6 pg_unreachable=0
✅ skip 门禁通过：连库用例真实执行，skip 数在基线内
```

## 3. 这两份放在一起说明什么

同一条用例 `tests/test_idempotency_lock.py::test_concurrent_same_url_converges`：
在 `b84dc53` 上绿、在 `76424cc`（只改了三个 md 文件，没碰代码）上红。
文档改动不可能改变并发交错，所以**唯一自洽的读法是"洞一直在，交错靠运气"**——
这正是必须补 savepoint 兜底、并把交错用 barrier 钉成确定性的理由（`d2f536c`）。

反面也要写着：本文件**不能**证明"洞在 `b84dc53` 之前就一直存在"。那需要更早 head 的复跑读数，
而更早的 run 里这条用例也是绿的（绿只说明那一次没交错）。要断言引入点，得对着
`git log -p` 里 `_save_short_link` 的写入条件变化单独做一次复现，不在本件射程内。
