"""STEP-04 S4.4：清单四态的**迁移判据**（全部不连库，本机可判）。

为什么这条文件要存在：四态在 STEP-04 之前只有 `DISCOVERED` 被真正写过
（`_map_row` 的唯一字面量），其余三个是契约里的装饰。把"入列→ENQUEUED、
入库→INGESTED、永久失败→FAILED、崩溃→回 DISCOVERED"写进服务层而不给它一个
能在本机跑起来的判据面，验收就只能等 @ci 的连库用例——而连库用例在无 PG 的机器上
**skip 而不是 fail**，于是"没人验证过"和"验证通过了"在读数上长成同一个样子。
本文件判的是四件事：

1. **迁移表与契约枚举同源**（`app/contracts/collection.py:ManifestStatus`），
   两边任一新增状态而另一边不动 → 这里红；
2. **worker 的结果映射**（`manifest_status_for_item_outcome`）是纯函数，四种分支各有读数；
3. **入列路径**同事务写 `JobItem.manifest_id` 并把清单置 `ENQUEUED`，重入队先走合法的
   stale 回退而不是自造一条 `ENQUEUED→ENQUEUED`；
4. **Diff 的 SQL 形状**——按键减资产、按键减在途、两支 NULL 守卫都在。
   这里的守卫一旦丢，`NOT IN (含 NULL 的子查询)` 会让 Diff 恒空：比原 bug（恒 1）更坏，
   所以判据既查"有守卫"，也用一发**去掉守卫的副本**证明这条检查真的会咬。
5. **回写发生在哪个事务里**（第 6 节）——`_drain_items` 用假会话跑通，`commit()` 记下**那一刻**
   清单行的状态；回写若掉到 commit 之后，快照就停在 `ENQUEUED`，那正是 S4.4.2 要避免的可见中间态。
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.contracts.collection import ManifestStatus
from app.core.errors import JobStateInvalidError, RateLimitedUpstreamError, SourceUrlUnrecognizedError
from app.models.entities import ArticleManifest, JobItem
from app.services import job_worker
from app.services.job_worker import (
    JobWorker,
    _apply_manifest_status,
    manifest_status_for_item_outcome,
)
from app.services.manifest import (
    MANIFEST_STATUS_DISCOVERED,
    MANIFEST_STATUS_ENQUEUED,
    MANIFEST_STATUS_FAILED,
    MANIFEST_STATUS_INGESTED,
)
from app.services.state_machine import ALLOWED_TRANSITIONS, can_transition, validate_transition
from app.services.subscription import SourceSubscriptionService

URL_A = "https://mp.weixin.qq.com/s?__biz=MjM5MjgwNTQ1MQ%3D%3D&mid=2650&idx=1&sn=aaaa"
KEY_A = "b:gh_aaa:2650:1"


def _sql(stmt: Any) -> str:
    """按 postgresql 方言渲染成单行文本（断言 SQL 形状用，不执行）。

    `literal_binds=True` 是必要的而不是审美：默认渲染把值留成 bind 参数，
    `STATUS = 'DISCOVERED'` 这种形状就根本不出现在文本里——
    第一版断言因此红在"值没渲染"上，而不是红在"键没换"上。
    """
    raw = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    return re.sub(r"\s+", " ", raw).upper()


# ------------------------------------------------------------------ 1. 表 ↔ 枚举同源


def test_manifest_transition_table_is_keyed_by_the_contract_enum() -> None:
    table = ALLOWED_TRANSITIONS["manifest"]
    enum_values = {s.value for s in ManifestStatus}
    # 表里出现的状态必须是枚举的成员（反过来不要求：终态可以没有出边键）
    assert set(table) <= enum_values, f"迁移表写了枚举里没有的状态：{set(table) - enum_values}"
    for targets in table.values():
        assert targets <= enum_values, f"出边写了枚举里没有的状态：{targets - enum_values}"
    assert table[MANIFEST_STATUS_DISCOVERED] == {MANIFEST_STATUS_ENQUEUED}
    assert table[MANIFEST_STATUS_ENQUEUED] == {
        MANIFEST_STATUS_INGESTED,
        MANIFEST_STATUS_FAILED,
        MANIFEST_STATUS_DISCOVERED,
    }
    assert table[MANIFEST_STATUS_FAILED] == {MANIFEST_STATUS_DISCOVERED}
    # INGESTED 是终态：枚举里有它，表里**不该**有它的出边键
    assert MANIFEST_STATUS_INGESTED not in table, "已入库的篇被给了出边 ⇒ 重新发现能把终态倒回"


def test_the_two_edges_the_card_calls_illegal_are_rejected() -> None:
    """卡面 S4.4.2.1 要覆盖两条非法边——这里给三条，第四条是给判据自己用的。"""
    assert not can_transition("manifest", MANIFEST_STATUS_DISCOVERED, MANIFEST_STATUS_INGESTED)
    assert not can_transition("manifest", MANIFEST_STATUS_INGESTED, MANIFEST_STATUS_DISCOVERED)
    assert not can_transition("manifest", MANIFEST_STATUS_ENQUEUED, MANIFEST_STATUS_ENQUEUED)
    with pytest.raises(JobStateInvalidError) as exc:
        validate_transition("manifest", MANIFEST_STATUS_DISCOVERED, MANIFEST_STATUS_INGESTED)
    assert exc.value.code == 30005


# ------------------------------------------------------------------ 2. 结果 → 状态映射


@pytest.mark.parametrize(
    ("error_type", "throttled", "retryable", "expected"),
    [
        ("", False, False, MANIFEST_STATUS_INGESTED),  # 成功
        ("RateLimitedUpstreamError", True, False, None),  # 限流暂停：条目回 PENDING，篇还没结局
        ("ExtractQualityLowError", False, True, None),  # 还能重试：不动
        ("SourceUrlUnrecognizedError", False, False, MANIFEST_STATUS_FAILED),  # 永久失败
        ("ValueError", False, False, MANIFEST_STATUS_FAILED),  # 重试次数耗尽（retryable 已为 False）
    ],
)
def test_worker_maps_item_outcome_to_manifest_status(
    error_type: str, throttled: bool, retryable: bool, expected: str | None
) -> None:
    got = manifest_status_for_item_outcome(error_type=error_type, throttled=throttled, retryable=retryable)
    assert got == expected, f"error_type={error_type!r} throttled={throttled} retryable={retryable} ⇒ {got!r}"


def test_outcome_mapping_covers_the_same_branch_set_as_drain_items() -> None:
    """映射函数的分支集必须与 `_drain_items` 里真正写条目状态的四支**一一对应**。

    这不是"名字出现在源码里就算"的那类检查（本仓库给判据反复修的就是这种）：
    这里比的是**集合**——四支 `set_status(...)` 的目标状态去掉清单侧的映射后，
    必须正好等于纯函数的值域。少一支或多一支都会红。
    """
    import inspect

    from app.services import job_worker

    body = inspect.getsource(job_worker.JobWorker._drain_items)
    written = set(re.findall(r"set_status\(\s*item_id,\s*(ITEM_STATUS_[A-Z_]+)", body))
    assert written == {"ITEM_STATUS_SUCCEEDED", "ITEM_STATUS_PENDING", "ITEM_STATUS_FAILED"}, (
        f"条目侧分支变了，映射函数该跟着改：{written}"
    )
    mapped = {
        manifest_status_for_item_outcome(error_type="x", throttled=t, retryable=r)
        for t in (True, False)
        for r in (True, False)
    } | {MANIFEST_STATUS_INGESTED}
    assert mapped - {None} == {MANIFEST_STATUS_INGESTED, MANIFEST_STATUS_FAILED}, (
        f"清单侧值域与条目侧三支对不上：{mapped}"
    )


def test_sweep_gate_is_wider_than_the_idle_loop_but_finert_than_the_ttl() -> None:
    """回退巡检必须有节流门：`run_forever` 空转间隔只有 5s，而 `status` 上没有索引。

    判的是我选的那条规则本身（`max(60, ttl/4)`），不是"有没有写一个 gate"：
    默认 ttl 下应是 450s；ttl 压到 60s 时不能被压成 15s（那又变回高频扫描）；
    ttl 拉到 7200s 时不该跟着放宽到 1800s 以外……不，规则就是这么定的，所以读数也照实写：
    下限 60s 兜住高频，上限由 ttl/4 兜住"比回收窗口细得多"。
    """
    from app.services.job_worker import JobWorker as _W

    def _interval(ttl: int | None) -> float:
        async def _ingest(*args: object, **kwargs: object) -> dict[str, object]:
            return {}

        w = _W(
            _OneSessionFactory(),  # type: ignore[arg-type]
            _ingest,  # type: ignore[arg-type]
            heartbeat_enabled=False,
            manifest_enqueued_ttl_seconds=ttl,
        )
        return float(w._manifest_sweep._min_interval)  # noqa: SLF001 —— 判的就是这条规则

    assert _interval(1800) == 450.0
    assert _interval(60) == 60.0, "ttl 调小不该把巡检压到分钟级以下"
    assert _interval(None) == 450.0, "缺省取 Settings 的 1800 ⇒ 450s"


class _OneSessionFactory:
    """给构造函数用的最小会话工厂（本条只读 `_min_interval`，不会真的开会话）。"""

    def __call__(self) -> Any:
        raise AssertionError("构造巡检门不该开会话")


# ------------------------------------------------------------------ 3. 回写会话面


class _FakeGetSession:
    """只实现 `get()` 的假会话——`_apply_manifest_status` 用到的 ORM 构造就这一个。

    刻意不把假面做大：每多加一个它支持的构造，就少一分"真库上会不会不一样"的不确定性；
    超出这个面的构造一律 AttributeError 直接红，而不是被假的兜住。
    """

    def __init__(self, row: ArticleManifest | None) -> None:
        self.row = row
        self.asked: list[str] = []

    async def get(self, model: Any, pk: str) -> ArticleManifest | None:
        assert model is ArticleManifest, f"回写面不该查别的表：{model}"
        self.asked.append(pk)
        return self.row


def _manifest(status: str) -> ArticleManifest:
    return ArticleManifest(
        id="m-1",
        source_id="src-1",
        external_id="workUuid-1",
        article_key=KEY_A,
        url=URL_A,
        title="t",
        content_hash="h",
        status=status,
    )


async def test_apply_manifest_status_writes_only_legal_targets() -> None:
    row = _manifest(MANIFEST_STATUS_ENQUEUED)
    session = _FakeGetSession(row)
    assert await _apply_manifest_status(session, "m-1", MANIFEST_STATUS_INGESTED) is True
    assert row.status == MANIFEST_STATUS_INGESTED

    # 非法边：不写、不抛穿 worker，但必须出声（返回 False 由调用方落 warning）
    other = _manifest(MANIFEST_STATUS_INGESTED)
    session2 = _FakeGetSession(other)
    assert await _apply_manifest_status(session2, "m-1", MANIFEST_STATUS_INGESTED) is False
    assert other.status == MANIFEST_STATUS_INGESTED, "非法边不该改行"

    # 关联为空 / 目标为空：一行都不该去查（查了就是拿 None 当状态写）
    never_asked = _FakeGetSession(None)
    assert await _apply_manifest_status(never_asked, None, MANIFEST_STATUS_FAILED) is False
    assert await _apply_manifest_status(never_asked, "m-1", None) is False
    assert never_asked.asked == []

    # 行已消失（FK 是 SET NULL，删清单先于回写）：可见的缺失，不是"回写成功"
    gone = _FakeGetSession(None)
    assert await _apply_manifest_status(gone, "m-1", MANIFEST_STATUS_FAILED) is False
    assert gone.asked == ["m-1"]


# ------------------------------------------------------------------ 4. 入列路径


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)


class _FakeItemRepo:
    def __init__(self) -> None:
        self.created: list[JobItem] = []
        self.statused: list[tuple[str, str]] = []

    async def create(self, job_id: str, external_id: str = "", url: str = "") -> JobItem:
        item = JobItem(
            id=f"item-{len(self.created)}",
            job_id=job_id,
            external_id=external_id,
            url=url,
            manifest_id=None,
        )
        self.created.append(item)
        return item

    async def set_status(self, item_id: str, status: str, error: str = "") -> None:
        self.statused.append((item_id, status))


class _CapturingSession:
    """记录被编译的 Diff 语句；`flush()` 是入列路径唯一用到的写构造。

    假面刻意做小：`_compute_new_manifests` 只走 `scalars().all()` 与一个 `scalar()` 计数，
    `_populate_job_items` 只走 `flush()`。多用一个构造这里就红，而不是被兜住——
    假会话把不该支持的构造悄悄接住，正是本仓库判据"红在工具上却记到代码头上"的那族错。
    """

    def __init__(self, rows: list[Any] | None = None, backlog: int = 0) -> None:
        self.rows = rows or []
        self.backlog = backlog
        self.statements: list[Any] = []
        self.flushed = 0

    async def scalars(self, stmt: Any) -> _FakeResult:
        self.statements.append(stmt)
        return _FakeResult(self.rows)

    async def scalar(self, stmt: Any) -> int:
        return self.backlog

    async def execute(self, stmt: Any) -> _FakeResult:
        # STEP-04 的在途面改成"按解析后的键减"之后，Diff 每轮都会先取一次在途清单行
        # （`SELECT article_manifests.id, ...`）。这里默认回空集 = 没有在途行，
        # 需要它在途语义的用例走 `_UnifySession`，它有分派。
        return _FakeResult([])

    async def flush(self) -> None:
        self.flushed += 1


def _svc(session: _CapturingSession) -> SourceSubscriptionService:
    svc = SourceSubscriptionService(session)  # type: ignore[arg-type]
    svc._item_repo = _FakeItemRepo()  # type: ignore[assignment]
    return svc


async def test_enqueue_writes_manifest_id_and_flips_status_in_one_pass() -> None:
    session = _CapturingSession()
    svc = _svc(session)
    m = _manifest(MANIFEST_STATUS_DISCOVERED)
    assert await svc._populate_job_items("job-1", "src-1", "sub-1", manifests=[m]) == 1
    item = svc._item_repo.created[0]  # type: ignore[attr-defined]
    assert item.manifest_id == "m-1", "S4.3.2：条目没写清单关联 ⇒ 在途面对现实无从减"
    assert m.status == MANIFEST_STATUS_ENQUEUED
    assert session.flushed == 1, "入列与置位要一次提交，分开写会留崩溃窗口"


async def test_enqueue_rejects_rows_that_did_not_come_from_the_diff() -> None:
    """入列只接受 Diff 的产物（status=DISCOVERED）；别的状态一律撞 30005，不静默兜。

    第三轮验证实测：`_create_sync_job` 的两个调用点要么传 None（现算 Diff）、要么传**当轮**
    新鲜 Diff 的结果，永远不会把 ENQUEUED/FAILED 的行带进来，所以"入列前先回退再置位"
    那段是死代码。死代码删掉，换成这条loud guard 的判据：
    - `ENQUEUED → ENQUEUED` 非法（上一条用例已钉它是非法边）⇒ 必须撞，而不是自我循环一次成功；
    - `FAILED → ENQUEUED` 同样非法 ⇒ 永久失败的篇只能经 stale 回退（FAILED→DISCOVERED）
      或重试面（P-18，尚未接）回到队列，入列面不替它开后门。
    """
    session = _CapturingSession()
    svc = _svc(session)
    stuck = _manifest(MANIFEST_STATUS_ENQUEUED)
    with pytest.raises(JobStateInvalidError):
        await svc._populate_job_items("job-2", "src-1", "sub-1", manifests=[stuck])
    assert stuck.status == MANIFEST_STATUS_ENQUEUED, "撞异常前不该已经把状态改掉一半"
    assert not svc._item_repo.created, "异常前不该已经建出条目"  # type: ignore[attr-defined]

    failed = _manifest(MANIFEST_STATUS_FAILED)
    svc2 = _svc(_CapturingSession())
    with pytest.raises(JobStateInvalidError):
        await svc2._populate_job_items("job-3", "src-1", "sub-1", manifests=[failed])
    assert not can_transition("manifest", MANIFEST_STATUS_FAILED, MANIFEST_STATUS_ENQUEUED)

    locked = _manifest(MANIFEST_STATUS_INGESTED)
    svc3 = _svc(_CapturingSession())
    with pytest.raises(JobStateInvalidError):
        await svc3._populate_job_items("job-4", "src-1", "sub-1", manifests=[locked])


# ------------------------------------------------------------------ 5. Diff 的 SQL 形状


async def _diff_sql(session: _CapturingSession, svc: SourceSubscriptionService) -> str:
    await svc._compute_new_manifests("src-1", "sub-1")
    # 第一条被记录的是 Diff 主查询（backlog 计数走 `scalar`，不进 statements）
    assert session.statements, "_compute_new_manifests 没发出任何 scalars 查询"
    return _sql(session.statements[0])


async def test_diff_subtracts_by_article_key_not_the_channel_id() -> None:
    """P-2 的正身：差量必须拿 `article_key` 去减 READY 资产，而不是 `external_id`。"""
    session = _CapturingSession()
    sql = await _diff_sql(session, _svc(session))
    assert "ARTICLE_KEY NOT IN (SELECT CONTENT_ASSETS.EXTERNAL_ID" in sql, sql
    assert "ARTICLE_MANIFESTS.EXTERNAL_ID NOT IN" not in sql, "又拿渠道幂等键去减资产 ⇒ P-2 复发"
    assert "ARTICLE_MANIFESTS.STATUS = 'DISCOVERED'" in sql


async def test_diff_carries_both_null_guards_and_the_check_has_teeth() -> None:
    """两支 NULL 守卫缺一不可，且这条检查必须真的会咬（用拆守卫的副本自证）。

    SQL 的 `x NOT IN (子查询)` 只要子查询里出现一个 NULL 就整体 UNKNOWN ⇒ 候选全被滤光。
    `JobItem.manifest_id` 与 `ArticleManifest.article_key` 都是可空列（S4.2.1 / D-V9-04）。
    断言用**计数**而不是"在某段里"：主查询与在途子查询渲染出的守卫文本一模一样，
    靠分段找会把"数错段"当成通过（本仓库给分段判据修过两次）。
    """
    session = _CapturingSession()
    sql = await _diff_sql(session, _svc(session))
    assert "ARTICLE_MANIFESTS.ARTICLE_KEY IS NOT NULL" in sql  # 主查询：无身份行不入列
    assert "JOIN JOB_ITEMS ON JOB_ITEMS.MANIFEST_ID = ARTICLE_MANIFESTS.ID" in sql, (
        f"在途面没走清单关联：{sql}"
    )
    assert sql.count("ARTICLE_MANIFESTS.ARTICLE_KEY IS NOT NULL") == 2, (
        f"守卫应当是两支（主查询 + 在途子查询），实得 {sql.count('ARTICLE_MANIFESTS.ARTICLE_KEY IS NOT NULL')} 支"
    )

    # 反证的反证：拆掉一支守卫，计数就掉到 1 —— 上面那条计数断言不是恒真
    assert sql.replace("AND ARTICLE_MANIFESTS.ARTICLE_KEY IS NOT NULL", "", 1).count(
        "ARTICLE_MANIFESTS.ARTICLE_KEY IS NOT NULL"
    ) == 1


async def test_diff_orders_by_created_at_with_an_id_tie_breaker() -> None:
    """同篇两形态收敛时"留哪一行"必须是确定值，而不是查询计划的运气。

    第三轮验证抓出来的：`created_at` 是 `func.now()` = **事务**时间戳，同一批 flush 出来的行它全等，
    只按它排就没有 tie-breaker ⇒ 连库用例今天过明天红。所以判据要的是
    `ORDER BY created_at, id`——留的是"确定同一行"，不是"最早那一行"（措辞也跟着改）。
    """
    session = _CapturingSession()
    sql = await _diff_sql(session, _svc(session))
    assert "ORDER BY ARTICLE_MANIFESTS.CREATED_AT, ARTICLE_MANIFESTS.ID" in sql, sql


async def test_diff_returns_one_row_per_article_key_within_a_round() -> None:
    """S4.1.2 的内存面：**同一支键空间**里两行同键 ⇒ 一轮只入列一次（不依赖真库就能判收敛）。

    这里判的是**收敛本身**。跨键空间的那一对（短链 `s:<token>` 与长链 `b:<biz>:<mid>:<idx>`
    算出来就是两个不同的 `article_key`）要靠 `short_link_maps` 先并键，判据在
    `test_manifest_asset_alignment.py::test_two_url_forms_of_one_article_enqueue_once`，
    它的反面（没有映射行 ⇒ 两种形态各排一次队）也单独钉了一条，免得把不可得的行为写成 1。
    """
    a = _manifest(MANIFEST_STATUS_DISCOVERED)
    b = ArticleManifest(
        id="m-2",
        source_id="src-1",
        external_id="workUuid-2",
        article_key=KEY_A,  # 同一篇长链换了追踪参数：同一支键空间
        url=URL_A.replace("sn=aaaa", "sn=aaaa?x=1"),
        title="t",
        content_hash="h2",
        status=MANIFEST_STATUS_DISCOVERED,
    )
    svc = _svc(_CapturingSession(rows=[a, b]))
    out = await svc._compute_new_manifests("src-1", "sub-1")
    assert [m.id for m in out] == ["m-1"], f"同篇两形态只该留排序后的第一行：{[m.id for m in out]}"
    assert b.status == MANIFEST_STATUS_DISCOVERED, "被收敛掉的行不该改状态——等 READY 那一条下轮减掉"


async def test_null_key_backlog_warning_is_counted_not_silent() -> None:
    """无身份行不入列这件事必须**出声**：静默排除就是 STEP-05 那一族"采集静默失败"。"""
    logged: list[dict[str, Any]] = []

    def _capture(event: str, **kw: Any) -> None:
        logged.append({"event": event, **kw})

    import app.services.subscription as sub_mod

    original_logger = sub_mod.logger
    sub_mod.logger = type(
        "FakeLogger",
        (),
        {
            "warning": staticmethod(lambda event, **kw: _capture(event, **kw)),
            "info": staticmethod(lambda event, **kw: None),
        },
    )()
    try:
        svc = _svc(_CapturingSession(rows=[], backlog=7))
        out = await svc._compute_new_manifests("src-1", "sub-1")
    finally:
        sub_mod.logger = original_logger  # 还原真 logger，否则后面所有用例都被这个假面接管
    assert out == []
    hits = [e for e in logged if e["event"] == "manifest.diff.null_key_backlog"]
    assert hits and hits[0]["rows"] == 7, f"backlog 没被计数告警：{logged}"


# ------------------------------------------------ 6. `_drain_items` 的回写与同事务性
#
# 上面那两组只判了纯函数 `manifest_status_for_item_outcome` 和 `_apply_manifest_status` 本身，
# 而 S4.4.2 的声明是"清单回写与条目终态**在同一个事务里**提交"——那一头在 `_drain_items` 里，
# 此前没有任何用例走到过，只能靠读代码相信。这里用一个假会话把声明变成读数：
# `commit()` 记录**那一刻**清单行的状态，回写若掉到 commit 之后，快照就停在 `ENQUEUED`。


class _DrainItem:
    """`claim_next_pending` 返回的条目形状（只带 `_drain_items` 真正读的四个属性）。"""

    def __init__(self, item_id: str) -> None:
        self.id = item_id
        self.url = URL_A
        self.manifest_id = "m-1"
        self.retry_count = 0


class _DrainSession:
    def __init__(self, row: ArticleManifest, journal: list[Any]) -> None:
        self._row = row
        self._journal = journal

    async def get(self, model: Any, pk: str) -> ArticleManifest | None:
        assert model is ArticleManifest, f"回写面不该查别的表：{model}"
        return self._row

    async def commit(self) -> None:
        self._journal.append(("commit", self._row.status))


class _DrainFactory:
    """`async_sessionmaker` 的最小替身：三次 `async with` 都拿同一条会话（同事务的判据基础）。"""

    def __init__(self, session: _DrainSession) -> None:
        self._s = session

    def __call__(self) -> _DrainFactory:
        return self

    async def __aenter__(self) -> _DrainSession:
        return self._s

    async def __aexit__(self, *exc: object) -> bool:
        return False


def _drain_repos(state: dict[str, Any]) -> tuple[type, type]:
    """造 `JobItemRepository` / `JobRepository` 的替身：写操作一律进 journal，不碰库。"""

    class _Items:
        def __init__(self, session: Any) -> None:
            self._s = session

        async def claim_next_pending(self, job_id: str) -> Any:
            return state["items"].pop(0) if state["items"] else None

        async def set_status(self, item_id: str, status: str, error: str = "") -> None:
            state["journal"].append(("item", status))

        async def bump_retry(self, item_id: str) -> None:
            state["journal"].append(("retry",))

        async def counts(self, job_id: str) -> dict[str, int]:
            return {"succeeded": 1, "failed": 0, "pending": 0}

    class _Jobs:
        def __init__(self, session: Any) -> None:
            self._s = session

        async def heartbeat(self, job_id: str, done: int) -> None:
            return None

        async def get_by_id(self, job_id: str) -> None:
            return None

    return _Items, _Jobs


async def _run_drain(
    monkeypatch: pytest.MonkeyPatch, ingest: Any, start_status: str
) -> tuple[list[Any], str]:
    journal: list[Any] = []
    row = _manifest(start_status)
    state: dict[str, Any] = {"items": [_DrainItem("i-1")], "journal": journal}
    items_cls, jobs_cls = _drain_repos(state)
    monkeypatch.setattr(job_worker, "JobItemRepository", items_cls)
    monkeypatch.setattr(job_worker, "JobRepository", jobs_cls)

    async def _no_sleep(_seconds: float) -> None:
        return None

    worker = JobWorker(
        _DrainFactory(_DrainSession(row, journal)),  # type: ignore[arg-type]
        ingest,
        item_interval_seconds=0.0,
        sleep=_no_sleep,
        heartbeat_enabled=False,
    )
    await worker._drain_items("job-1", "space-1")
    return journal, row.status


async def test_drain_writes_ingested_before_committing_the_item_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S4.4.2 正文：ingest 成功 ⇒ 条目 SUCCEEDED、清单 INGESTED，且**在 commit 之前**就已置位。"""

    async def ok(session: Any, space_id: str, url: str) -> dict[str, bool]:
        return {"ok": True}

    journal, final = await _run_drain(monkeypatch, ok, MANIFEST_STATUS_ENQUEUED)
    assert journal == [("item", "SUCCEEDED"), ("commit", MANIFEST_STATUS_INGESTED)], journal
    assert final == MANIFEST_STATUS_INGESTED


async def test_drain_writes_failed_for_a_permanent_error_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """永久失败 ⇒ 条目 FAILED + 清单 FAILED，同样在同一个事务里。"""

    async def bad(session: Any, space_id: str, url: str) -> None:
        raise SourceUrlUnrecognizedError("链接不是公众号文章")

    journal, final = await _run_drain(monkeypatch, bad, MANIFEST_STATUS_ENQUEUED)
    assert journal == [("item", "FAILED"), ("commit", MANIFEST_STATUS_FAILED)], journal
    assert final == MANIFEST_STATUS_FAILED


# ------------------------------------------------ 7. 短链形态的并键（S4.1.2 跨键空间那一半）

URL_SHORT = "https://mp.weixin.qq.com/s/SHORTtoken1234?chksm=x"
_SHORT_TOKEN = "SHORTtoken1234"
KEY_SHORT = f"s:{_SHORT_TOKEN}"


class _FakeRows:
    def __init__(self, pairs: list[Any]) -> None:
        self._pairs = pairs

    def all(self) -> list[Any]:
        return self._pairs


class _UnifySession:
    """Diff 在并键路上要发的四处查询的替身：按 FROM/JOIN 坐标分派，认不出来就红。

    分派键刻意用**表坐标**而不是"第几次调用"：后者把查询顺序写死进测试，实现换一个查询次序
    就红，而那并不是缺陷。坐标认不出来时一律 `AssertionError` 直红，而不是兜一个空结果——
    假面把没支持的构造悄悄接住，就是"红在工具上却记到代码头上"的那族错。
    """

    def __init__(
        self,
        rows: list[ArticleManifest],
        mapped: list[tuple[str, str]],
        ready: list[str],
        inflight_rows: list[tuple[str, str, str]] | None = None,
    ) -> None:
        self.rows = rows
        self.mapped = mapped
        self.ready = ready
        # 在途面的替身从"键列表"改成 **(id, article_key, url) 三元组**：实现现在要先取在途行、
        # 再对它们做同一套短链解析（`@ci` 真库那条红证明按存量键查在途是查不到的）。
        # 默认空集而不是省略参数——省略会让"忘了传"读成"没有在途"。
        self.inflight_rows = inflight_rows or []
        self.map_reads = 0

    async def scalars(self, stmt: Any) -> _FakeResult:
        # 按 SELECT 列表的前缀分派，而不是 `in`：候选查询的子查询里同样出现
        # `FROM article_manifests JOIN job_items`，用子串匹配会把主查询认成在途探针。
        # `_sql()` 渲染成**大写**（`_sql` 里 upper()），所以这里的坐标也必须大写。
        sql = _sql(stmt)
        if sql.startswith("SELECT CONTENT_ASSETS.EXTERNAL_ID"):
            return _FakeResult(self.ready)
        if sql.startswith("SELECT ARTICLE_MANIFESTS.ID"):
            return _FakeResult(self.rows)
        raise AssertionError(f"替身会话认不出这条查询：{sql[:160]}")

    async def scalar(self, stmt: Any) -> int:
        return 0

    async def execute(self, stmt: Any) -> _FakeRows:
        sql = _sql(stmt)
        # 在途行取数走 execute（三元组），短链映射也走 execute——两条必须分得开，
        # 否则"根本没查映射"和"查了映射"在这条判据上长成同一个样子。
        if sql.startswith("SELECT ARTICLE_MANIFESTS.ID, ARTICLE_MANIFESTS.ARTICLE_KEY"):
            return _FakeRows(self.inflight_rows)
        assert "FROM SHORT_LINK_MAPS" in sql, f"并键只该读 short_link_maps：{sql[:160]}"
        self.map_reads += 1
        return _FakeRows(self.mapped)


def _short_manifest(source_id: str, item_id: str) -> ArticleManifest:
    return ArticleManifest(
        id=item_id,
        source_id=source_id,
        external_id=f"workUuid-{item_id}",
        article_key=KEY_SHORT,
        url=URL_SHORT,
        title="t",
        content_hash="h",
        status=MANIFEST_STATUS_DISCOVERED,
    )


def _unify_svc(session: _UnifySession) -> SourceSubscriptionService:
    svc = SourceSubscriptionService(session)  # type: ignore[arg-type]
    svc._item_repo = _FakeItemRepo()  # type: ignore[assignment]
    return svc


async def test_short_form_row_is_subtracted_when_its_long_key_is_already_ready() -> None:
    """P-2 的跨形态面：短链行的 `article_key` 是 `s:`，而 READY 资产锚的是长链 `b:` 键。

    只按存量键减的话这一支**永远减不掉**（两支键空间不相交），于是"已入库的篇每轮重排"
    在短链形态上复活。并键之后才谈得上减资产——这里判的就是这一步有没有真的发生。
    """
    row = _short_manifest("src-1", "m-short")
    svc = _unify_svc(_UnifySession(rows=[row], mapped=[(_SHORT_TOKEN, KEY_A)], ready=[KEY_A]))
    assert await svc._compute_new_manifests("src-1", "sub-1") == [], "长链已 READY，短链形态不该再入列"


async def test_short_form_row_is_subtracted_when_its_long_key_is_in_flight() -> None:
    """在途面的跨形态半边（正向）：长链那一支挂在活动 Job 下时，短链这一支也不能再排一次队。"""
    row = _short_manifest("src-1", "m-short")
    svc = _unify_svc(
        _UnifySession(
            rows=[row],
            mapped=[(_SHORT_TOKEN, KEY_A)],
            ready=[],
            inflight_rows=[("m-long", KEY_A, URL_A)],
        )
    )
    assert await svc._compute_new_manifests("src-1", "sub-1") == [], "同篇长链在途，短链形态绕过了在途保护"


async def test_long_form_row_is_subtracted_when_the_short_form_is_in_flight() -> None:
    """在途面的跨形态半边（反向）——**这一条是 `@ci` 真库实测出来的红**。

    入列的那一支完全可能是短链行：它挂在活动 Job 下，但 `article_key` 存的是 `s:<token>`。
    只拿候选行解析出来的长链键去查 `ArticleManifest.article_key IN (长链键)`，那条在途的短链行
    **命中不了**，于是同一篇的长链形态在下一轮绕过在途保护再排一次队（run 39016275296 的
    `test_two_url_forms_of_one_article_enqueue_once` 就是这么红的）。
    修法是让在途行也过一遍同一套解析：短链在途行 → 长链键 → 候选行长链键命中 → 剔除。
    """
    long_row = _manifest(MANIFEST_STATUS_DISCOVERED)  # 存量键 = KEY_A（长链一支）
    short_inflight = ("m-short-queued", KEY_SHORT, URL_SHORT)
    svc = _unify_svc(
        _UnifySession(
            rows=[long_row],
            mapped=[(_SHORT_TOKEN, KEY_A)],
            ready=[],
            inflight_rows=[short_inflight],
        )
    )
    assert await svc._compute_new_manifests("src-1", "sub-1") == [], (
        "同篇的短链形态已在途，长链这一支绕过了在途保护"
    )


async def test_unification_never_fakes_a_convergence_when_the_map_is_missing() -> None:
    """没有映射行时**不许**假装收敛：短链形态照常入列（首抓之后 `kb.py` 才会落映射）。

    这条是上一对用例的反面。少了它，"把两种形态并起来"可以退化成为所有短链编一个长链键，
    而那正是把不可得的行为写成绿的形状。
    """
    row = _short_manifest("src-1", "m-short")
    svc = _unify_svc(_UnifySession(rows=[row], mapped=[], ready=[]))
    out = await svc._compute_new_manifests("src-1", "sub-1")
    assert [m.id for m in out] == ["m-short"], "无映射时的正确行为是入列，而不是被并键逻辑吞掉"


async def test_a_non_wechat_host_never_consults_the_short_link_map() -> None:
    """并键的入口条件必须与 `canonical_article_key` 采纳 `s:` 支的条件**同一个**。

    驱动这件事的证据是 `parse_wechat_url`（`article_identity.py:82`）：`/s/` 前面已经过了
    `host == WECHAT_HOST` 那道闸。判法用"查没查表"而不是"结果对不对"：非微信 host 的行
    一次都不该去读 `short_link_maps`——真去读了，将来某个 token 撞上一次，就会把一篇合法文章
    误判成"已入库/已在途"而**静默不采**（本卡要消灭的冒名，反向版本）。
    """
    row = ArticleManifest(
        id="m-evil",
        source_id="src-1",
        external_id="workUuid-evil",
        article_key=KEY_SHORT,  # 存量里真有这种脏行：键写着 s:，host 却不是微信
        url="https://evil.example.com/s/SHORTtoken1234",
        title="t",
        content_hash="h",
        status=MANIFEST_STATUS_DISCOVERED,
    )
    session = _UnifySession(rows=[row], mapped=[(_SHORT_TOKEN, KEY_A)], ready=[KEY_A])
    out = await _unify_svc(session)._compute_new_manifests("src-1", "sub-1")
    assert session.map_reads == 0, "非微信 host 也去查了 short_link_maps ⇒ 并键的入口条件放宽了"
    assert [m.id for m in out] == ["m-evil"], "不许凭一个来路不明的 s: 键把这行吞掉"


async def test_drain_keeps_enqueued_when_the_outcome_is_not_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """限流暂停/可重试这两支**不该改清单状态**（映射给 None），但条目仍要落 PENDING。

    这条是回写面的反向判据：把 `manifest_status_for_item_outcome` 改成"有 error 就 FAILED"，
    这里就会读到 `FAILED` 而不是 `ENQUEUED`。
    """

    async def throttled(session: Any, space_id: str, url: str) -> None:
        raise RateLimitedUpstreamError("4004 限频")

    journal, final = await _run_drain(monkeypatch, throttled, MANIFEST_STATUS_ENQUEUED)
    assert journal == [("item", "PENDING"), ("commit", MANIFEST_STATUS_ENQUEUED)], journal
    assert final == MANIFEST_STATUS_ENQUEUED, "限流不该把清单打成终态"
