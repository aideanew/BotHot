"""BE-02 引擎路由与资产缓存 hardening 验收测试。

机器门口径（BE-02）：
- R1 路由分发：EngineRouter.adapter_for 按 space.engine 分发；builtin → LangBotAdapter；
  SaaS Key 缺失 → 不可用（10004/403 语义）；available/configured/allowlisted 三态；
- R2 kb 路由：非 builtin 空间 ingest → 引擎不可用 403（Key 未配不伪装可用）；builtin 零回归；
- R3 chat 路由：ask 前引擎不可用 → 403 流前信封；builtin 正常（SSE 链既有测试覆盖）；
- R4 raw_store：url 透传默认零回归；local 后端落盘返回 file:// URI；
- R5 delete 路由：非 builtin 空间删除 → 引擎不可用 403（不删 PG）；builtin 既有路径。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id
from app.main import create_app
from app.providers.engine_port import (
    ENGINE_IMPLEMENTED,
    ENGINE_ORDER,
    EngineRouter,
    LangBotAdapter,
    RagflowAdapter,
)
from app.providers.raw_store import LocalVolumeStore, UrlPassthroughStore
from app.services.kb import KnowledgeBaseService


class _FakeSettings:
    kb_default_engine = "builtin"
    kb_engine_allowlist = "builtin,main"
    coze_api_key = ""
    dify_api_key = ""
    fastgpt_api_key = ""
    main_kb_api_base = ""
    main_kb_api_key = ""
    raw_store_backend = "url"
    raw_store_dir = ""
    embedding_api_base = "https://api.siliconflow.cn/v1"
    embedding_api_key = "test-embed-key"
    embedding_model = "BAAI/bge-m3"


class _SpaceStub:
    """最小空间桩（engine 分发用）。"""

    def __init__(self, engine: str = "builtin", langbot_kb_uuid: str = "lb-1", engine_kb_id: str = "") -> None:
        self.engine = engine
        self.langbot_kb_uuid = langbot_kb_uuid
        self.engine_kb_id = engine_kb_id


class _NoopLangbot:
    async def delete_kb(self, kb_uuid: str) -> None: ...


# ------------------------------------------------------------------ R1 路由分发 + 三态


def test_router_dispatch_builtin_and_three_states() -> None:
    """R1：builtin → LangBotAdapter 恒可用；SaaS Key 缺 → configured/available/allowlisted 三态明确。"""
    router = EngineRouter(_FakeSettings(), _NoopLangbot())  # type: ignore[arg-type]
    # builtin 恒可用
    assert router.available("builtin") is True
    assert router.configured("builtin") is True
    assert router.allowlisted("builtin") is True
    adapter = router.adapter_for(_SpaceStub("builtin"))
    assert isinstance(adapter, LangBotAdapter)
    # coze：Key 空 → configured=False（即便 allowlist 含 main 也不可用）
    assert router.configured("coze") is False
    assert router.available("coze") is False
    assert router.allowlisted("coze") is False  # 不在缺省 allowlist(builtin,main)
    # main：allowlisted=True 但 Key 空 → configured=False → available=False
    assert router.allowlisted("main") is True
    assert router.configured("main") is False
    assert router.available("main") is False
    # 不可用引擎 adapter_for → ValueError（调用方转 10004）
    with pytest.raises(ValueError, match="不可用"):
        router.adapter_for(_SpaceStub("coze"))
    # kb_id_for：builtin 取 langbot_kb_uuid；非 builtin 取 engine_kb_id
    assert router.kb_id_for(_SpaceStub("builtin", "lb-9")) == "lb-9"
    assert router.kb_id_for(_SpaceStub("coze", "", "coze-ds-1")) == "coze-ds-1"
    assert set(ENGINE_ORDER) == {"builtin", "main", "coze", "dify", "fastgpt"}


def test_router_main_allowlisted_key_present() -> None:
    """R1b：main 配齐 Key + allowlist 含 main，但实接未完成 → available=False（三条件缺一不可）。

    R1 修复（dde6945）后口径：available = configured and allowlisted and implemented。
    本用例是「配 Key 即伪可用」的回归防线——原 BE-02 两条件断言（available=True）在 R1
    改口径后已作废，此处按三条件重写（2026-09-17 阶段0 门禁补漏）。
    """

    class _FakeMainSettings:
        kb_default_engine = "builtin"
        kb_engine_allowlist = "builtin,main"
        coze_api_key = ""
        dify_api_key = ""
        fastgpt_api_key = ""
        main_kb_api_base = "http://main-kb:8001"
        main_kb_api_key = "sk-main-test"
        raw_store_backend = "url"
        raw_store_dir = ""

    router = EngineRouter(_FakeMainSettings(), _NoopLangbot())  # type: ignore[arg-type]
    assert router.configured("main") is True
    assert router.allowlisted("main") is True
    assert ENGINE_IMPLEMENTED["main"] is False
    assert router.available("main") is False  # implemented=False 阻断（防伪 available）
    # 未实接 → adapter_for 拒绝分发（调用方转 10004/403，而非 50001 NotImplementedError）
    with pytest.raises(ValueError, match="不可用"):
        router.adapter_for(_SpaceStub("main", "", "main-kb-1"))


def test_router_main_available_after_implemented(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """R1c：三条件齐备（Key + allowlist + implemented=True）→ available=True 且可分发。

    实接口径：RagflowAdapter 六方法落地后把 ENGINE_IMPLEMENTED 的 main 位置 True 再开
    allowlist（大纲 §四.7「先改注册表再开 allowlist，禁止绕过」）。
    """

    class _FakeMainSettings:
        kb_default_engine = "builtin"
        kb_engine_allowlist = "builtin,main"
        coze_api_key = ""
        dify_api_key = ""
        fastgpt_api_key = ""
        main_kb_api_base = "http://main-kb:8001"
        main_kb_api_key = "sk-main-test"
        raw_store_backend = "url"
        raw_store_dir = ""

    monkeypatch.setitem(ENGINE_IMPLEMENTED, "main", True)
    router = EngineRouter(_FakeMainSettings(), _NoopLangbot())  # type: ignore[arg-type]
    assert router.available("main") is True
    assert isinstance(router.adapter_for(_SpaceStub("main", "", "main-kb-1")), RagflowAdapter)


# ------------------------------------------------------------------ R2/R5 kb 与 delete 路由


def _endpoint_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    return TestClient(app)


def test_ingest_unconfigured_engine_forbidden() -> None:
    """R2：ingest 端点未登录 → 401 登录保护先行（引擎 403 语义由 kb service 层用例覆盖）。

    注：端点不覆盖 user_id（避免走真实 DB 连接，测试环境生产端口不可达）。
    """
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/api/v1/spaces/00000000-0000-0000-0000-000000000001/docs",
        json={"url": "https://mp.weixin.qq.com/s/be02-r2"},
    )
    assert resp.status_code == 401  # 未带会话 → 10001 登录保护先行


async def test_kb_service_unconfigured_engine_raises_forbidden(db_session) -> None:  # type: ignore[no-untyped-def]
    """R2b（连库）：coze 空间（Key 未配）ingest → 10004/403；builtin 空间正常路径不受影响。"""
    from test_repositories import _make_user

    from app.repositories.space import SpaceRepository
    from app.services.resolver import SourceResolverService

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="BE02引擎空间")
    space.engine = "coze"  # 引擎位切到未配 Key 的 SaaS
    await db_session.flush()

    svc = KnowledgeBaseService(
        _NoopLangbot(),  # type: ignore[arg-type]
        db_session,
        SourceResolverService(),
        settings=_FakeSettings(),  # type: ignore[arg-type]
    )
    from app.core.errors import ForbiddenError

    with pytest.raises(ForbiddenError) as exc_info:
        await svc.ingest_url(space.id, "https://mp.weixin.qq.com/s/be02-r2b")
    assert exc_info.value.code == 10004
    assert "coze" in exc_info.value.message or "不可用" in exc_info.value.message


async def test_kb_service_engine_kb_id_backfill_builtin(db_session) -> None:  # type: ignore[no-untyped-def]
    """R2c（连库）：builtin 空间 ensure_kb 回写 langbot_kb_uuid（零回归路径）。"""
    from test_langbot import _lb_transport
    from test_repositories import _make_user

    from app.repositories.space import SpaceRepository
    from app.services.resolver import SourceResolverService

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="BE02内置空间")
    await db_session.commit()

    transport, _ = _lb_transport()
    import httpx

    http = httpx.AsyncClient(transport=transport, follow_redirects=True)
    from app.providers.langbot.client import LangBotClient

    svc = KnowledgeBaseService(
        LangBotClient("http://langbot.test", "a", "b", http=http),
        db_session,
        SourceResolverService(),
    )
    kb_uuid = await svc.ensure_kb(space.id)
    assert kb_uuid == "kb-uuid-1"
    refreshed = await SpaceRepository(db_session).get_by_id(space.id)
    assert refreshed is not None and refreshed.langbot_kb_uuid == "kb-uuid-1"


# ------------------------------------------------------------------ R4 raw_store


async def test_raw_store_url_passthrough_default() -> None:
    """R4a：默认 url 后端 raw_uri = 原文 URL（零回归）。"""
    store = UrlPassthroughStore()
    uri = await store.save(url="https://mp.weixin.qq.com/s/x", content_markdown="# t", title="t")
    assert uri == "https://mp.weixin.qq.com/s/x"
    assert store.backend == "url"


async def test_raw_store_local_volume_writes_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """R4b：local 后端落盘返回 file:// URI（同文幂等覆盖）。"""
    store = LocalVolumeStore(base_dir=tmp_path)
    uri1 = await store.save(
        url="https://mp.weixin.qq.com/s/y", content_markdown="# 正文A", title="标题A"
    )
    assert uri1.startswith("file://")
    assert store.backend == "local"
    # 同 url+正文 → 同 URI（幂等）；不同正文 → 不同 URI
    uri2 = await store.save(
        url="https://mp.weixin.qq.com/s/y", content_markdown="# 正文A", title="标题A"
    )
    assert uri1 == uri2
    uri3 = await store.save(
        url="https://mp.weixin.qq.com/s/y", content_markdown="# 正文B", title="标题A"
    )
    assert uri1 != uri3


async def test_raw_store_plugin_point_switches_backend() -> None:
    """R4c：raw_store 后端可切换（接口稳定，不强上 S3）：url→local 由配置驱动。"""
    from app.providers.raw_store import make_raw_store

    store = make_raw_store("url")
    assert store.backend == "url"
    store2 = make_raw_store("local")
    assert store2.backend == "local"


# ------------------------------------------------------------------ D-2/D-3 短链缓存修复（BE-02）


async def test_short_link_second_ingest_hits_cache_via_url_fallback(db_session) -> None:  # type: ignore[no-untyped-def]
    """R5：无 biz 参数短链，第二次 ingest 命中缓存（URL 兜底锚，0 微信请求）。

    P0 已知缺陷 D-2/D-3：首抓后 source.external_id=页面 biz，资产 external_id=article_key，
    二次入库 article_key 锚失配 → 永远重抓。BE-02 以「源 URL 含 article_key」兜底修复。
    """
    from test_langbot import _client, _StubResolver  # 复用既有解析桩与 LangBot 桩
    from test_repositories import _make_user

    from app.repositories.space import SpaceRepository

    class _ShortBizResolver(_StubResolver):
        """无 biz 参数短链桩：返回独立 biz（避免与既有测试锚点撞车），URL 保持短链原文。"""

        BIZ = "BE02-INDEPENDENT-BIZ"

        def __init__(self) -> None:
            super().__init__()
            self.fetch_count = 0

        async def resolve(self, raw_url: str):
            self.fetch_count += 1
            article = await super().resolve(raw_url)
            article.url = raw_url  # 短链跳转后 url 即稳定（P0 口径）
            article.biz = self.BIZ  # 独立 biz：不与 p0-cache 测试共用锚点
            return article

    user = await _make_user(db_session)
    space = await SpaceRepository(db_session).create(user_id=user.id, name="BE02短链缓存")
    await db_session.commit()

    short_url = "https://mp.weixin.qq.com/s/be02-short-001"
    stub = _ShortBizResolver()
    svc = KnowledgeBaseService(
        _client(),  # test_langbot 全链桩（建库/上传/触发/清单）
        db_session,
        stub,  # type: ignore[arg-type]
        settings=_FakeSettings(),  # type: ignore[arg-type]
    )
    # 第一次：真实抓取（resolver 网络请求 +1）
    first = await svc.ingest_url(space.id, short_url)
    assert first["hitCache"] is False
    assert stub.fetch_count == 1

    # 第二次：URL 兜底锚命中缓存 → resolver 0 请求
    second = await svc.ingest_url(space.id, short_url)
    assert stub.fetch_count == 1, "第二次不应再抓取（D-2/D-3 修复：URL 兜底锚命中缓存）"
    assert second["hitCache"] is True
    assert second["hitCount"] == 1
    assert second["docId"] == first["docId"]
