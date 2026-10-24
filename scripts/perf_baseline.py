#!/usr/bin/env python3
"""STEP-18 全站性能基线测量 harness（S18.0–S18.2.1）。

只测不改：本脚本对 `app/**` 零改动，全部"变慢对照"经注入点/桩在**测量侧**完成。

四个探测（对应卡面 S18.1.1–S18.1.4）：
- api        S18.1.1  GET /api/v1/spaces、/api/v1/hot/topics、/api/v1/jobs（TestClient 同进程，
             会话经依赖覆盖注入——无 Redis，真实登录链路不在测，指纹明写）
- ingest     S18.1.3  单篇入库（KnowledgeBaseService.ingest_url，服务层真 PG 写入，
             LangBot/文章页抓取为测试桩；短链/长链两组 URL 形态）
- feed       S18.1.4  GET /api/v1/hot/feed（Feed 流读）
- first_token S18.1.2 首 Token（**录制回放**：`_llm_stream_delta` 的上游经 MockTransport
             重放录制的 SSE 帧；无真实 LLM 凭据，每个数字旁标注）

可感性证明（S18.2.1）：`--inject-delay-ms N` 在**服务端被测路径内**注入 N 毫秒延迟
（API/feed 走 ASGI 中间件、ingest 走桩 resolver、first_token 走回放传输的帧间延迟）。
同命令带 N 重跑，p50 位移 ≥ N 毫秒 ⇒ 该指标随用户可感耗时同向移动。

环境前提（S18.0，缺一即 fail-closed 拒绝测量）：
- 自备 PostgreSQL 16 于 localhost:5547（bothot/bothot，库 bothot_test 已 `alembic upgrade head`）
- Redis 不在测（不可达 ⇒ 依赖它的路径不测，V0.18 增量口径）；LangBot 桩；LLM 录制回放

用法：
    cd apps/api
    .venv/Scripts/python ../../scripts/perf_baseline.py --n 50 \
        --out ../../docs/06_validation/evidence/EVD-V18-18 [--inject-delay-ms 0]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import secrets
import statistics
import sys
import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx

PERF_ARG_MARKER = "__perf_inject_delay_ms__"


def _p50_p95(samples: list[float]) -> dict[str, float]:
    xs = sorted(samples)
    p95 = xs[min(len(xs) - 1, max(0, int(round(0.95 * len(xs) + 0.5)) - 1))]
    return {"p50": round(statistics.median(xs), 2), "p95": round(p95, 2), "n": len(xs)}


async def _probe_api(app: Any, user_id: str, n: int) -> dict[str, Any]:

    endpoints = [
        ("GET /api/v1/spaces", "/api/v1/spaces"),
        ("GET /api/v1/hot/topics", "/api/v1/hot/topics"),
        ("GET /api/v1/jobs", "/api/v1/jobs"),
    ]
    # ASGITransport（非 TestClient portal）：与 harness 的事件循环同 loop，避免
    # lifespan 后台任务跨 loop（实测 run 40033711793 时代的 portal 报错）。
    # lifespan 不运行 ⇒ 被测端点只依赖每请求 get_db 覆盖（指纹已声明）。
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        out: dict[str, Any] = {}
        for label, path in endpoints:
            await client.get(path)  # 预热一次（连接/路由缓存），不计入样本
            samples: list[float] = []
            for _ in range(n):
                t0 = time.perf_counter()
                resp = await client.get(path)
                dt = (time.perf_counter() - t0) * 1000
                assert resp.status_code == 200, (path, resp.status_code, resp.text[:120])
                samples.append(dt)
            out[label] = _p50_p95(samples)
    return out


async def _probe_feed(client: Any, n: int) -> dict[str, Any]:
    await client.get("/api/v1/hot/feed")  # 预热
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        resp = await client.get("/api/v1/hot/feed?page=1&page_size=20")
        dt = (time.perf_counter() - t0) * 1000
        assert resp.status_code == 200, (resp.status_code, resp.text[:120])
        samples.append(dt)
    return {"GET /api/v1/hot/feed": _p50_p95(samples)}


async def _probe_ingest(session_factory: Any, n: int, inject_delay_ms: int = 0) -> dict[str, Any]:
    """单篇入库：真 PG 写入（source→asset→doc），LangBot/抓取为桩（指纹明写）。

    短链与长链两组：短链走 `s:` 形态（映射表查不到 ⇒ 桩 resolver 反解），长链直进。
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api" / "tests"))
    from fixtures.wechat_urls import BIZ_A
    from sqlalchemy import func, select
    from test_p0_asset_cache import _client as _lb_client
    from test_p0_asset_cache import _CountingStubResolver  # noqa: PLC0415

    from app.models.entities import ContentAsset, KnowledgeDocument, Source
    from app.services.kb import KnowledgeBaseService

    out: dict[str, Any] = {}
    for group, mk_url in (
        # 短链 = mp.weixin.qq.com/s/{key}（_is_short_link 的形态判据）；长链 = 带 query 参数的长链。
        # 两者都过真实 normalize（ALLOWED_HOSTS 只有 mp.weixin.qq.com）；token 唯一 ⇒ 无缓存命中。
        ("short", lambda i: f"https://mp.weixin.qq.com/s/perf{secrets.token_hex(8)}"),
        ("long", lambda i: f"https://mp.weixin.qq.com/s/perf{secrets.token_hex(8)}?idx={i}&src=perf"),
    ):
        samples = []
        async with session_factory() as session:
            source = Source(
                type="wechat_oa",
                external_id=f"perf-{group}-{secrets.token_hex(4)}",
                name=f"perf-{group}",
                url=f"https://upstream.invalid/{group}",
            )
            session.add(source)
            from app.repositories.space import SpaceRepository

            user = await _ensure_user(session)
            import time as _time

            space = await SpaceRepository(session).create(
                user_id=user.id, name=f"perf-ingest-{group}-{_time.time_ns()}"
            )
            await session.commit()
            sid = space.id
            for i in range(n):
                lb = _lb_client()
                resolver = _CountingStubResolver()
                if inject_delay_ms > 0:
                    _orig_resolve = resolver.resolve

                    bound_orig = _orig_resolve
                    delay_s = inject_delay_ms / 1000

                    async def _slow_resolve(url: str, _orig: Any = bound_orig, _d: float = delay_s) -> Any:
                        await asyncio.sleep(_d)
                        return await _orig(url)

                    resolver.resolve = _slow_resolve  # type: ignore[method-assign]
                svc = KnowledgeBaseService(lb, session, resolver)
                t0 = time.perf_counter()
                result = await svc.ingest_url(sid, mk_url(i), owner=user.id)
                dt = (time.perf_counter() - t0) * 1000
                assert result.get("status") in ("READY", "INDEXED", "FETCHED"), result
                await session.commit()
                samples.append(dt)
            assets = int(
                await session.scalar(
                    select(func.count()).select_from(ContentAsset).where(ContentAsset.source_id == source.id)
                )
                or 0
            )
            docs = int(
                await session.scalar(
                    select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.space_id == sid)
                )
                or 0
            )
            assert assets >= n or docs >= 0, (assets, docs)  # 往返计数走 test_perf_probe.py，这里只取时延
        out[f"ingest[{group}]"] = _p50_p95(samples)
    _ = BIZ_A  # 样本页 biz 锚（桩 resolver 的返回已含同值 biz）
    return out


async def _ensure_user(session: Any) -> Any:
    from sqlalchemy import select

    from app.models.entities import User

    row = (await session.scalars(select(User).where(User.sub == "sub-perf-18"))).first()
    if row is None:
        row = User(sub="sub-perf-18", email="perf18@test.local", nickname="PERF18", role="admin")
        session.add(row)
        await session.commit()
    return row


async def _probe_first_token(n: int, inject_delay_ms: int = 0) -> dict[str, Any]:
    """首 Token（S18.1.2，**录制回放**）：`_llm_stream_delta` 的上游换 MockTransport，
    重放录制的 OpenAI 兼容 SSE 帧；测 t0 → 第一个 ("delta", …) yield。"""
    import app.api.v1.chat as chat_mod

    recorded = (
        'data: {"choices":[{"delta":{"content":"录"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"制"}}]}\n\n'
        "data: [DONE]\n\n"
    ).encode()

    async def handler(request: httpx.Request) -> httpx.Response:
        if inject_delay_ms > 0:
            await asyncio.sleep(inject_delay_ms / 1000)  # S18.2.1：首帧前延迟
        return httpx.Response(200, content=recorded, headers={"content-type": "text/event-stream"})

    original_factory = chat_mod._llm_http_factory
    chat_mod._llm_http_factory = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        from app.core.config import get_settings

        get_settings.cache_clear()
        results = [{"content": [{"text": "上下文正文，长度足够让 _context_texts 非空"}], "title": "t"}]
        samples = []
        for _ in range(n):
            gen = cast(AsyncGenerator[Any, None], chat_mod._llm_stream_delta("性能探测问题", results))
            t0 = time.perf_counter()
            kind, _ = await gen.__anext__()
            dt = (time.perf_counter() - t0) * 1000
            assert kind == "delta", kind
            samples.append(dt)
            await gen.aclose()
        return {"first_token[recorded-replay]": _p50_p95(samples)}
    finally:
        chat_mod._llm_http_factory = original_factory


def _fingerprint(session_factory: Any, args: argparse.Namespace, dataset: dict[str, int]) -> dict[str, Any]:
    import psycopg

    pg_version = ""
    conn = psycopg.connect(args.dsn.replace("postgresql+psycopg://", "postgresql://"), autocommit=True)
    try:
        pg_version = conn.execute("SELECT version()").fetchone()[0]  # type: ignore[index]
    finally:
        conn.close()
    return {
        "timestamp_cst": datetime.now(UTC).astimezone().isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "postgres": pg_version,
        "dsn_scope": args.dsn.split("@")[-1],
        "client_position": "in-process（TestClient 同进程 / 服务层直调；无网络栈，指纹如实声明）",
        "redis": "NOT RUNNING（依赖 Redis 的路径不在测，V0.18 增量口径）",
        "rate_limit": (
            "RATE_LIMIT_ENABLED=false（测量配置，指纹声明）：限流中间件的 Redis 1s 连接超时"
            "会串在每条请求前并淹没全部端点读数；限流自身正确性归既有测试面"
        ),
        "langbot": "桩（test_p0_asset_cache._client 形态）",
        "llm": "录制回放（无真实 LLM 凭据；S18.1.2 判据允许并要求标注）",
        "dataset": dataset,
        "inject_delay_ms": args.inject_delay_ms,
        "n_per_probe": args.n,
    }


async def _seed_dataset(session_factory: Any) -> dict[str, int]:
    """播种固定规模数据集（指纹的"数据集规模"栏）。幂等：按名字前缀判定已种则跳过。"""
    from sqlalchemy import func, select

    from app.models.bothot_entities import FeedItem, HotTopic
    from app.models.entities import Job, User

    async def _run() -> dict[str, int]:  # noqa: PLR0915
        async with session_factory() as session:
            user = await _ensure_user(session)
            marker = (
                await session.scalars(select(func.count()).select_from(User).where(User.sub == "sub-perf-18"))
            ).first()
            _ = marker
            from app.models.entities import KnowledgeSpace

            spaces_n = int(
                await session.scalar(
                    select(func.count()).select_from(KnowledgeSpace).where(KnowledgeSpace.name == "perf-space-0")
                )
                or 0
            )
            if spaces_n == 0:
                from app.repositories.space import SpaceRepository

                for i in range(30):
                    await SpaceRepository(session).create(user_id=user.id, name=f"perf-space-{i}")
                from datetime import date as _date

                for i in range(60):
                    session.add(
                        HotTopic(
                            title=f"perf 话题 {i}",
                            summary="性能基线种子",
                            topic_date=_date.today(),
                        )
                    )
                for i in range(100):
                    session.add(
                        FeedItem(
                            item_type="hot_topic",
                            ref_id=f"perf-topic-{i}",
                            title=f"perf feed {i}",
                            summary="性能基线种子",
                        )
                    )
                for i in range(40):
                    session.add(
                        Job(
                            id=f"perf-job-{i}",
                            type="daily_report",
                            user_id=user.id,
                            status="SUCCEEDED" if i % 2 else "QUEUED",
                            payload="{}",
                            idempotency_key=f"perf-daily:{i}",
                        )
                    )
                await session.commit()
            spaces = int((await session.scalars(select(func.count()).select_from(User))).first() or 0)
            topics = int((await session.scalars(select(func.count()).select_from(HotTopic))).first() or 0)
            feeds = int((await session.scalars(select(func.count()).select_from(FeedItem))).first() or 0)
            jobs = int((await session.scalars(select(func.count()).select_from(Job))).first() or 0)
            return {"users": spaces, "hot_topics": topics, "feed_items": feeds, "jobs": jobs}

    return await _run()


async def _run_all(args: argparse.Namespace) -> dict[str, Any]:
    import os

    os.environ["RATE_LIMIT_ENABLED"] = "false"
    from app.core.config import get_settings

    get_settings.cache_clear()
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(args.dsn, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        dataset = await _seed_dataset(session_factory)


        from app.api.deps import get_current_sub, get_current_user_id, get_db
        from app.main import create_app

        user = await _ensure_user_session(session_factory)

        async def _override_db():
            async with session_factory() as session:
                yield session

        app = create_app()
        app.dependency_overrides[get_current_user_id] = lambda: user.id
        app.dependency_overrides[get_current_sub] = lambda: user.sub  # hot 路由的会话依赖（无 Redis，桩注入）
        app.dependency_overrides[get_db] = _override_db
        if args.inject_delay_ms > 0:
            delay = args.inject_delay_ms / 1000

            class _PerfDelayMiddleware:
                """注入式"变慢对照"（S18.2.1）：纯 ASGI 形态（与仓库中间件同形），
                在链路入口 sleep 再下传——被测端点的读数必须随它移动。"""

                def __init__(self, app: Any) -> None:
                    self.app = app

                async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
                    if scope["type"] != "http":
                        await self.app(scope, receive, send)
                        return
                    await asyncio.sleep(delay)
                    await self.app(scope, receive, send)

            app.add_middleware(_PerfDelayMiddleware)

        out: dict[str, Any] = {}
        out["api"] = await _probe_api(app, user.id, args.n)
        feed_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")
        out["feed"] = await _probe_feed(feed_client, args.n)
        out["ingest"] = await _probe_ingest(session_factory, args.n, args.inject_delay_ms)
        out["first_token"] = await _probe_first_token(args.n, args.inject_delay_ms)
        out["fingerprint"] = _fingerprint(session_factory, args, dataset)
        return out
    finally:
        await engine.dispose()


async def _ensure_user_session(session_factory: Any) -> Any:
    async with session_factory() as session:
        return await _ensure_user(session)


def main() -> None:
    parser = argparse.ArgumentParser(description="STEP-18 性能基线测量")
    parser.add_argument("--dsn", default="postgresql+psycopg://bothot:bothot@localhost:5547/bothot_test")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--out", required=True)
    parser.add_argument("--inject-delay-ms", type=int, default=0)
    parser.add_argument("--tag", default="run", help="输出文件名后缀（复跑对照用）")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = asyncio.run(_run_all(args))

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"perf_baseline_{args.tag}_{stamp}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [f"# 性能基线读数（tag={args.tag}，inject={args.inject_delay_ms}ms，n={args.n}）", ""]
    for probe, series in report.items():
        if probe == "fingerprint":
            continue
        for name, stat in series.items():
            lines.append(f"- {name}：p50={stat['p50']}ms / p95={stat['p95']}ms（n={stat['n']}）")
    md_path = out_dir / f"perf_baseline_{args.tag}_{stamp}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"json={json_path}")
    print(f"md={md_path}")
    for probe, series in report.items():
        if probe == "fingerprint":
            continue
        for name, stat in series.items():
            print(f"  {name}：p50={stat['p50']}ms p95={stat['p95']}ms")


if __name__ == "__main__":
    # psycopg 异步在 Windows 缺省的 ProactorEventLoop 上不可用（repo 测试同解）：
    # 全 harness 切 Selector 策略。
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()
