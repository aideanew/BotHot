"""STEP-11 采集性能基线：三个数字入档，先有数再谈优化（卡面 §6「禁止无基线优化」）。

跑法（默认**不进全量**：`pyproject` 的 `addopts = ["-m", "not perf"]` 把它们摘掉）：

    cd apps/api && AIDEANBOT_TEST_PG_DSN=$DSN DATABASE_URL=$DSN \\
      .venv/Scripts/python.exe -X utf8 -m pytest -m perf tests/perf/ -q -s

三条判据各自量什么、以及为什么那个数不能由别的文件代量：

1. `test_sql_statements_per_page`：1 页 20 行的清单写入到底发多少条 SQL，并且这个数字
   会不会随**本地已有清单规模**增长。第二问才是重点——`sync_source` 先 `_known_count`
   再逐行 `_upsert`，只要每行语句数固定，稳态成本就是 O(页)；若它随存量线性上升，
   等于每轮增量都在为历史买单，那比"慢一点"更坏。
2. `test_diff_plan_at_ten_thousand`：`_compute_new_manifests` 在 10k 清单 / 1k Job 下的
   `EXPLAIN (ANALYZE, BUFFERS)`。刻意**不自己写那条 SQL**：判据必须由生产代码产生——
   用 `before_cursor_execute` 把生产实际发出的语句与绑定参数原样抓下来，再对同一句话
   EXPLAIN。抄一份"我以为它这么查"的计划，等于给未来的漂移留一个绿灯。
3. `test_single_ingest_percentiles`：单篇入库的 p50/p95（n=50，桩掉上游 IO），对照
   REQ-NF-001「文章入库单篇 < 30s」。⚠ 这条量的是**服务层自己那一段**
   （解析→规范化→质量评分→资产 upsert→doc→LangBot 提交），抓取与 LangBot 都是
   MockTransport ⇒ 与真实网络耗时无关，只能用来说"服务层不是那 30 秒的瓶颈"，
   **不能**用来宣布 REQ-NF-001 达标（那需要真后端读数，本卡没有凭据面）。

所有用例都跑在 `db_session` 的外层事务里（回滚清场），10k 造数不留存量。
"""

from __future__ import annotations

import json
import re
import statistics
import time
import uuid
from typing import Any

import pytest
from sqlalchemy import event

from app.models.entities import ArticleManifest, Job, KnowledgeSpace, Source, SourceSubscription, User
from app.repositories.space import SpaceRepository
from app.repositories.user import SqlAlchemyUserStore
from app.services.manifest import ManifestSyncService
from app.services.subscription import SourceSubscriptionService

pytestmark = pytest.mark.perf

_ROWS_PER_PAGE = 20
_MANIFEST_BACKLOG = 10_000
_JOB_BACKLOG = 1_000
_INGEST_SAMPLES = 50
_STATEMENT_KIND = re.compile(r"^(INSERT|SELECT|UPDATE|DELETE|SAVEPOINT|RELEASE|ROLLBACK|SET|WITH|EXPLAIN)")


# ────────────────────────────────────────────── 上游桩（发现层，20 行/页）


class _TwentyRowProvider:
    """一页恰好 20 行的清单桩：dict 行 + total，与 `query_work_list` 旧端口同形。

    页号进 `mid` ⇒ 翻两页得到的是两批不同的行，`sync_source` 的止页条件（末页不足整页 /
    本页含已知行）才有得判；只返回固定 20 行的桩会把翻页逻辑测成恒真。
    """

    name = "perf"

    def __init__(self) -> None:
        self.calls = 0

    async def query_work_list(self, identifier: str, page: int) -> tuple[list[dict[str, Any]], int | None]:
        self.calls += 1
        rows = [
            {
                "id": f"{page:02d}{i:02d}" + "0" * 24,
                "url": f"https://mp.weixin.qq.com/s?__biz={identifier}&mid={2650000000 + page * 100 + i}&idx=1",
                "title": f"perf 行 {page}-{i}",
                "publish_time": "1790659200",
            }
            for i in range(_ROWS_PER_PAGE)
        ]
        return rows, _ROWS_PER_PAGE * 50

    async def aclose(self) -> None:
        return None


# ────────────────────────────────────────────── 语句计数与分类


def _event_target(db_session) -> Any:  # noqa: ANN001
    """语句级事件的挂载点：`db_session` 绑的是 Connection（savepoint 隔离），不是 Engine。

    `get_bind()` 因此返回 AsyncConnection，它没有 `sync_engine`——直接照搬"engine 上挂事件"
    的常见写法会 `AttributeError`。两种绑定都支持，逐个试出来即可，不要写死一种。
    """
    bind = db_session.get_bind()
    return getattr(bind, "sync_engine", None) or getattr(bind, "sync_connection", None) or bind


def _attach_counter(db_session) -> list[str]:
    """挂 `before_cursor_execute` 收语句原文；返回一个会被就地填充的列表。"""
    seen: list[str] = []

    def _listener(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        seen.append(statement)

    event.listen(_event_target(db_session), "before_cursor_execute", _listener)
    return seen


def _breakdown(statements: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in statements:
        m = _STATEMENT_KIND.match(s.strip())
        key = m.group(1) if m else "OTHER"
        out[key] = out.get(key, 0) + 1
    return out


async def _namespace(db_session) -> tuple[User, KnowledgeSpace, Source, SourceSubscription]:
    """一套 user + space + source(wechat_oa) + ACTIVE 订阅；biz 随机以免与并发会话撞唯一键。"""
    ns = uuid.uuid4().hex[:10]
    user = await SqlAlchemyUserStore(db_session).upsert_by_sub(f"sub-perf-{ns}", f"perf-{ns}@test.local", "PERF")
    space = await SpaceRepository(db_session).create(user_id=user.id, name=f"perf空间{ns}")
    source = Source(
        type="wechat_oa", external_id=f"PERFBIZ{ns}", name=f"perf{ns}", url=f"https://upstream.invalid/{ns}"
    )
    db_session.add(source)
    await db_session.flush()
    sub = SourceSubscription(
        id=f"perf-{ns}", user_id=user.id, source_id=source.id, space_id=space.id, status="ACTIVE"
    )
    db_session.add(sub)
    await db_session.commit()
    return user, space, source, sub


# ────────────────────────────────────────────── ① 每页 SQL 语句数


@pytest.mark.parametrize("backlog", [0, 2_000], ids=["empty-local", "2k-backlog"])
async def test_sql_statements_per_page(db_session, backlog: int) -> None:  # type: ignore[no-untyped-def]
    """1 页 20 行的写入语句数，以及它在本地已有 2k 清单时是否变多。

    判据只设**形状上界**不设精度：精确数字入 EVD 由人比对，硬编码在这里会让每次换机器都红，
    而红的原因与性能无关。两档参数化各自成立 ⇒ 跨档比较读打印行。
    """
    _user, _space, source, _sub = await _namespace(db_session)

    if backlog:
        db_session.add_all(
            [
                ArticleManifest(
                    source_id=source.id,
                    external_id=f"seed{i:07d}",
                    article_key=f"h:{i:032x}",
                    url=f"https://mp.weixin.qq.com/s?__biz={source.external_id}&mid={i}&idx=1",
                    title="seed",
                    status="INGESTED",
                )
                for i in range(backlog)
            ]
        )
        await db_session.commit()

    statements = _attach_counter(db_session)
    provider = _TwentyRowProvider()
    report = await ManifestSyncService(db_session, provider).sync_source(source.id, source.external_id, max_pages=1)
    await db_session.commit()

    kinds = _breakdown(statements)
    total = len(statements)
    print(f"PERF-SQL backlog={backlog} rows={report.discovered} calls={report.calls_made} total={total} {kinds}")

    assert report.discovered == _ROWS_PER_PAGE, report
    assert report.calls_made == 1, "max_pages=1 时只许打一次上游"
    assert kinds.get("INSERT", 0) == _ROWS_PER_PAGE, f"每行应恰一笔 INSERT，实得 {kinds}"
    assert total < 4 * _ROWS_PER_PAGE, f"语句数已超出 O(页) 的形状：{total} 对行 {_ROWS_PER_PAGE}，{kinds}"

# ────────────────────────────────────────────── ② 10k 清单 / 1k Job 下的 EXPLAIN


async def test_diff_plan_at_ten_thousand(db_session) -> None:  # type: ignore[no-untyped-def]
    """S11.1.2：抓生产实际发出的 Diff 语句，再对它 `EXPLAIN (ANALYZE, BUFFERS)`。

    造数形状照生产的键空间来：清单 `external_id` 是 32 位 hex（渠道内 id）、`article_key`
    是 `b:{biz}:{mid}:{idx}`；Job 的 `idempotency_key` 前缀必须是 `sync_account:{订阅}:`——
    `_active_sync_job_ids` 就是按那个前缀 LIKE 减在途的，编个别的前缀等于把要量的那条谓词
    从计划里删掉。1k 个 Job 里只放 1 个 QUEUED（且不带条目），这样"在途子查询命中一行但
    不排除任何候选"，减在途那一支照样进计划、却不掩盖主表的扫描形状。
    """
    user, space, source, sub = await _namespace(db_session)
    biz = source.external_id

    db_session.add_all(
        [
            ArticleManifest(
                source_id=source.id,
                external_id=f"{i:032x}",
                article_key=f"b:{biz}:{2650000000 + i}:1",
                url=f"https://mp.weixin.qq.com/s?__biz={biz}&mid={2650000000 + i}&idx=1",
                title="perf10k",
                status="DISCOVERED",
            )
            for i in range(_MANIFEST_BACKLOG)
        ]
    )
    db_session.add_all(
        [
            Job(
                id=f"job-{i:06d}",
                type="sync_account",
                user_id=user.id,
                payload=json.dumps({"space_id": space.id, "source_id": source.id, "subscription_id": sub.id}),
                status="QUEUED" if i == 0 else "SUCCEEDED",
                idempotency_key=f"sync_account:{sub.id}:{i}",
            )
            for i in range(_JOB_BACKLOG)
        ]
    )
    await db_session.commit()

    captured: list[tuple[str, Any]] = []
    target = _event_target(db_session)

    def _listener(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if "FROM article_manifests" in statement and "NOT IN" in statement.upper():
            captured.append((statement, parameters))

    event.listen(target, "before_cursor_execute", _listener)
    try:
        started = time.perf_counter()
        new_rows = await SourceSubscriptionService(db_session)._compute_new_manifests(source.id, sub.id)
        elapsed_ms = (time.perf_counter() - started) * 1000
    finally:
        event.remove(target, "before_cursor_execute", _listener)

    assert captured, "没抓到生产的 Diff 语句——谓词形状变了，本用例失去判定力"
    sql, params = captured[-1]
    print(f"PERF-DIFF 清单={_MANIFEST_BACKLOG} jobs={_JOB_BACKLOG} 命中={len(new_rows)} 耗时={elapsed_ms:.1f}ms")
    print("PERF-DIFF SQL:", " ".join(sql.split()))
    # 原样重放：`%(name)s` 与 `::VARCHAR` 两种语法在 `text()` 里会互相打断（实测两次红：
    # 一次 `%%` 转义、一次 `:name::` 解析歧义）。走 `exec_driver_sql` 把抓到的语句与绑定参数
    # 一字不改地交给同一个 driver——它拿到的就是生产那一刻拿到的东西。
    def _explain(sync_session) -> list[tuple[str, ...]]:  # noqa: ANN001
        return list(sync_session.connection().exec_driver_sql(f"EXPLAIN (ANALYZE, BUFFERS) {sql}", params))

    plan = "\n".join(str(row[0]) for row in await db_session.run_sync(_explain))
    print("PERF-DIFF PLAN:\n" + plan)

    assert len(new_rows) == _MANIFEST_BACKLOG, f"10k 全 DISCOVERED 且无在途 ⇒ 应全部命中，实得 {len(new_rows)}"
    assert "article_manifests" in plan and "jobs" in plan, plan[:600]


# ────────────────────────────────────────────── ③ 单篇入库 p50 / p95


async def test_single_ingest_percentiles(db_session) -> None:  # type: ignore[no-untyped-def]
    """S11.1.3：n=50 单篇入库的 p50/p95，对照 REQ-NF-001 的 30s 预算。

    桩的是上游（文章页与 LangBot 都是 MockTransport），所以这是**服务层自身**的耗时；
    见文件头的 ⚠——本条不许被引用成"REQ-NF-001 已达标"。
    """
    from test_langbot import _client
    from test_p0_asset_cache import _CountingStubResolver

    from app.services.kb import KnowledgeBaseService

    biz = "MjM5MjgwNTQ1MQ=="
    _user, space, _source, _sub = await _namespace(db_session)
    resolver = _CountingStubResolver()
    svc = KnowledgeBaseService(_client(), db_session, resolver)

    samples: list[float] = []
    for i in range(_INGEST_SAMPLES):
        url = f"https://mp.weixin.qq.com/s?__biz={biz}&mid={2651000000 + i}&idx=1&sn=perf{i:04d}"
        started = time.perf_counter()
        result = await svc.ingest_url(space.id, url)
        samples.append((time.perf_counter() - started) * 1000)
        assert result["status"] == "INDEXED", result

    ordered = sorted(samples)
    p50 = statistics.median(ordered)
    p95 = ordered[max(0, int(round(0.95 * len(ordered))) - 1)]
    print(
        f"PERF-INGEST n={len(samples)} p50={p50:.1f}ms p95={p95:.1f}ms max={ordered[-1]:.1f}ms "
        f"fetches={resolver.fetch_count} 预算=30000ms"
    )

    assert resolver.fetch_count == _INGEST_SAMPLES, "n 次入库应当抓 n 次（每次都是不同的一篇）"
    assert p95 < 30_000, f"服务层自身就吃满 30s 预算：p95={p95:.1f}ms"
