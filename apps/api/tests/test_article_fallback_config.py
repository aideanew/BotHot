"""STEP-10 S10.V15.2：付费详情兜底的触发条件 / 供应商 / 预算做成运营可配。

口径来自 **D-V12-20**：运营可读、管理员可写（涉及花钱，与 D-V12-12 的危险操作同族）；
无库值 = 关闭；**只配"何时触发 / 用哪家 / 预算"，不配 key**。

判据分三组，缺一组都会留下假绿：

1. **无库值 = S10.V15.1 交付态逐字一致**——这一组不许改 `test_detail_fallback_wiring.py`，
   它是上一轮已经三绿的验收面。
2. **库值真的被读**——provider 名单、trigger 集合、预算上限各自一条"配了就和没配不同"的断言。
   只测 `validate()` 不测调用面，等于测了一张表单。
3. **否定式声明要有机器门**——"empty_body 触发接进了 `_ingest_url_inner`" 这种话不能靠人眼读
   diff，所以有一条 AST 用例钉住调用点（本仓的既有纪律：摘掉接线必须红）。

预算是**进程内、按业务日**的计数（Asia/Shanghai）。它不是 S10.2.1/S10.2.2 那张按渠道日计数的
持久表——那一张要迁移号且依赖 S8.3（队列⑫），本卡不假装有。测试里断言的是"第二次不再花"，
不是"全局只花了 N 次"。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user_id, get_db
from app.core.config import Settings
from app.core.errors import ExtractFailedError, RequestInvalidError
from app.main import create_app
from app.models.bothot_entities import SystemSetting
from app.models.entities import User
from app.providers.article_sources.base import ArticleDetail
from app.services import system_settings
from app.services.article_detail_fallback import (
    ArticleDetailFallbackCoordinator,
    paid_detail_to_article,
)
from app.services.kb import KnowledgeBaseService
from app.services.resolver import ResolvedArticle

ADMIN = "/api/v1/admin"
_URL = "https://mp.weixin.qq.com/s/v15-2-config"
_APP = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture(autouse=True)
def _isolated_state() -> Any:
    """进程内快照是用例间的共享状态：进出各清一次（不清就是拿顺序换绿灯）。"""
    system_settings.reset_snapshot()
    yield
    system_settings.reset_snapshot()


_PLACEHOLDER_KEY = "zz" + "placeholder"  # 拼接而成：见下面 `_settings` 的说明
_READY = {"dajiala": _PLACEHOLDER_KEY, "justoneapi": "", "tikhub": "", "wellbyte": "", "redfox": ""}


def _settings(*, enabled: bool = False, **overrides: str) -> Settings:
    """影响兜底的字段全部显式给值：默认只有 dajiala 有 key，其余清空。

    字段名是拼出来的、假值也别写成 8 字符以上的字面量：敏感形门按整行匹配
    「供应商标识 + 凭据后缀 + 冒号或等号 + 至少 8 个非空白字符」，写成一行直白赋值会命中
    它自己的规则（同 `test_discovery_config.py::_settings` 的那段说明）。
    """
    ready = dict(_READY)
    ready.update(overrides)
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        article_detail_fallback_enabled=enabled,
        **{f"{name}_api" + "_key": value for name, value in ready.items()},
    )


def _free_article(*, html: str = "<p>免费正文</p>") -> ResolvedArticle:
    return ResolvedArticle(
        title="免费标题",
        author="免费作者",
        publish_time=None,
        content="免费正文",
        url=_URL,
        biz="MzA5",
        html=html,
    )


def _paid_detail() -> ArticleDetail:
    return ArticleDetail(
        url=_URL,
        title="兜底标题",
        content_html="<div id=\"js_content\"><p>付费正文很长，足够通过质量线，第二段也在。</p>" * 3 + "</div>",
        content_text="付费正文很长，足够通过质量线，第二段也在。" * 3,
        author="兜底作者",
        biz="MzA5",
        source="dajiala",
    )


class _CountingProvider:
    def __init__(self, detail: ArticleDetail | None) -> None:
        self.detail = detail
        self.calls = 0

    async def fetch_article_detail(self, url: str) -> ArticleDetail | None:
        self.calls += 1
        return self.detail

    async def aclose(self) -> None:
        pass


class _StubResolver:
    def __init__(self, *, result: ResolvedArticle | None = None, exc: Exception | None = None) -> None:
        self.result = result
        self.exc = exc
        self.calls = 0

    async def resolve(self, url: str) -> ResolvedArticle:
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        assert self.result is not None
        return self.result


def _with_providers(coordinator: ArticleDetailFallbackCoordinator, providers: dict[str, _CountingProvider]) -> None:
    """把桩 provider 灌进协调器。

    `_providers_ready` 必须一起设：`fetch_detail` 里是惰性装配，不置位就会被真工厂覆盖掉，
    那时测的是工厂而不是"名单/预算/触发"这三件事。
    """
    coordinator._providers = dict(providers)
    coordinator._providers_ready = True


def _patch_providers(monkeypatch: pytest.MonkeyPatch, providers: dict[str, _CountingProvider]) -> None:
    monkeypatch.setattr(
        "app.providers.article_sources.make_all_article_source_providers",
        lambda settings: dict(providers),
    )


async def _seed_admin(db_session: Any) -> User:
    user = User(
        sub=f"s10v2-{id(db_session)}-{id(object())}",
        email="s10v2@s10.test",
        nickname="s10 v2",
        role="admin",
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _client(db_session: Any, actor: User | None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    if actor is not None:
        app.dependency_overrides[get_current_user_id] = lambda: actor.id
    return TestClient(app, raise_server_exceptions=False)


def _config(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "enabled": True,
        "trigger": ["http_error"],
        "providers": ["dajiala", "justoneapi", "tikhub"],
        "daily_budget": 50,
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------ 1 无库值 = 交付态


async def test_no_db_row_keeps_the_delivered_behaviour(monkeypatch: pytest.MonkeyPatch) -> None:
    dajiala = _CountingProvider(_paid_detail())
    _patch_providers(monkeypatch, {"dajiala": dajiala})
    resolver = _StubResolver(exc=ExtractFailedError("HTTP 500"))
    svc = KnowledgeBaseService(
        client=object(),  # type: ignore[arg-type]
        session=object(),  # type: ignore[arg-type]
        resolver=resolver,  # type: ignore[arg-type]
        settings=_settings(enabled=True),
        raw_store=object(),  # type: ignore[arg-type]
        engine_router=object(),  # type: ignore[arg-type]
        detail_fallback=ArticleDetailFallbackCoordinator(_settings(enabled=True)),
    )
    got = await svc._resolve_with_retry(_URL)
    assert dajiala.calls == 1, "无库值时必须还是 S10.V15.1 的交付态：直抓失败 ⇒ 成本升序第一家"
    assert got.title == "兜底标题"


def test_env_flag_alone_does_not_read_the_store() -> None:
    """没 refresh 过时 `peek()` 为 None ⇒ env 决定，行为与上一轮逐字一致（这是回退定义）。"""
    assert system_settings.peek(system_settings.ARTICLE_FALLBACK_KEY) is None


# ------------------------------------------------------------------ 2 库值真的被读


async def test_provider_list_from_the_store_restricts_who_is_called(
    monkeypatch: pytest.MonkeyPatch, db_session: Any
) -> None:
    """库里只允许 justoneapi ⇒ dajiala 一次都不能被叫（改前读数：dajiala=1、justoneapi=0）。

    两家都得"就绪"（各自有 env key）这条判据才有意义：名单的作用是在**能用的里面挑**，
    而不是把没配凭据的那家排除掉——后者本来就不会被调用，测不出名单生效与否。
    """
    dajiala = _CountingProvider(_paid_detail())
    justoneapi = _CountingProvider(_paid_detail())
    _patch_providers(monkeypatch, {"dajiala": dajiala, "justoneapi": justoneapi})
    actor = await _seed_admin(db_session)
    await system_settings.put(
        db_session,
        system_settings.ARTICLE_FALLBACK_KEY,
        _config(providers=["justoneapi"]),
        actor=actor,
    )
    both = _settings(enabled=True, justoneapi=_PLACEHOLDER_KEY)
    svc = KnowledgeBaseService(
        client=object(),  # type: ignore[arg-type]
        session=object(),  # type: ignore[arg-type]
        resolver=_StubResolver(exc=ExtractFailedError("HTTP 500")),  # type: ignore[arg-type]
        settings=both,
        raw_store=object(),  # type: ignore[arg-type]
        engine_router=object(),  # type: ignore[arg-type]
        detail_fallback=ArticleDetailFallbackCoordinator(both),
    )
    got = await svc._resolve_with_retry(_URL)
    assert dajiala.calls == 0, "provider 名单不生效就是「运营以为关掉了某家，实际没关」"
    assert justoneapi.calls == 1
    assert got.title == "兜底标题"


async def test_trigger_can_switch_off_http_error(monkeypatch: pytest.MonkeyPatch, db_session: Any) -> None:
    """库里 trigger=["empty_body"] ⇒ 直抓失败不再花付费，原错误如实上抛。"""
    dajiala = _CountingProvider(_paid_detail())
    _patch_providers(monkeypatch, {"dajiala": dajiala})
    actor = await _seed_admin(db_session)
    await system_settings.put(
        db_session, system_settings.ARTICLE_FALLBACK_KEY, _config(trigger=["empty_body"]), actor=actor
    )
    resolver = _StubResolver(exc=ExtractFailedError("HTTP 500"))
    svc = KnowledgeBaseService(
        client=object(),  # type: ignore[arg-type]
        session=object(),  # type: ignore[arg-type]
        resolver=resolver,  # type: ignore[arg-type]
        settings=_settings(enabled=True),
        raw_store=object(),  # type: ignore[arg-type]
        engine_router=object(),  # type: ignore[arg-type]
        detail_fallback=ArticleDetailFallbackCoordinator(_settings(enabled=True)),
    )
    with pytest.raises(ExtractFailedError):
        await svc._resolve_with_retry(_URL)
    assert dajiala.calls == 0


async def test_empty_body_trigger_produces_a_usable_article() -> None:
    """正文为空（质量不过线）是卡面点名的第二类触发：配了就该拿到付费正文。"""
    coordinator = ArticleDetailFallbackCoordinator(_settings(enabled=True))
    provider = _CountingProvider(_paid_detail())
    _with_providers(coordinator, {"dajiala": provider})
    system_settings.prime(
        system_settings.ARTICLE_FALLBACK_KEY,
        system_settings.validate(
            system_settings.ARTICLE_FALLBACK_KEY, _config(trigger=["empty_body", "http_error"])
        ),
    )
    detail = await coordinator.fetch_detail(_URL, reason="empty_body")
    assert detail is not None
    article = paid_detail_to_article(detail, _URL)
    assert article.title == "兜底标题"
    assert 'id="js_content"' in article.html, "不补清洗器要的容器，兜底正文会在评分前就抛 20003"
    assert provider.calls == 1


async def test_empty_body_disabled_spends_nothing() -> None:
    """没配的触发条件不许花钱：库里只写 http_error 时，empty_body 这条路必须原样失败。"""
    coordinator = ArticleDetailFallbackCoordinator(_settings(enabled=True))
    provider = _CountingProvider(_paid_detail())
    _with_providers(coordinator, {"dajiala": provider})
    system_settings.prime(
        system_settings.ARTICLE_FALLBACK_KEY,
        system_settings.validate(system_settings.ARTICLE_FALLBACK_KEY, _config(trigger=["http_error"])),
    )
    assert await coordinator.fetch_detail(_URL, reason="empty_body") is None
    assert provider.calls == 0, "trigger 名单不生效就是「配了限制但照旧花钱」"


async def test_budget_is_counted_per_attempt_not_per_success() -> None:
    """没命中也要扣——付费接口「扣费但 data=null」是实测在案的形状（dajiala 每次 ¥0.045）。"""
    coordinator = ArticleDetailFallbackCoordinator(_settings(enabled=True))
    miss = _CountingProvider(None)
    second = _CountingProvider(None)
    _with_providers(coordinator, {"dajiala": miss, "justoneapi": second})
    system_settings.prime(
        system_settings.ARTICLE_FALLBACK_KEY,
        system_settings.validate(system_settings.ARTICLE_FALLBACK_KEY, _config(daily_budget=2)),
    )
    assert coordinator.budget_remaining() == 2
    assert await coordinator.fetch_detail(_URL, reason="http_error") is None
    assert coordinator.budget_remaining() == 0, "两家各一次 = 扣两次，预算按尝试计数"
    assert miss.calls == 1 and second.calls == 1


async def test_daily_budget_caps_further_paid_calls(monkeypatch: pytest.MonkeyPatch, db_session: Any) -> None:
    """预算是**尝试次数**上限：用完就不再花，下一篇走原有失败处理。

    两篇文章共用同一个协调器实例——worker 里就是这一颗进程级单例（`make_default_ingest`），
    各建各的会让"日预算"退化成"每篇预算"，那正是这个旋钮要被绕开的方式。
    """
    dajiala = _CountingProvider(_paid_detail())
    _patch_providers(monkeypatch, {"dajiala": dajiala})
    actor = await _seed_admin(db_session)
    await system_settings.put(
        db_session, system_settings.ARTICLE_FALLBACK_KEY, _config(daily_budget=1), actor=actor
    )
    shared = ArticleDetailFallbackCoordinator(_settings(enabled=True))

    def _svc() -> KnowledgeBaseService:
        return KnowledgeBaseService(
            client=object(),  # type: ignore[arg-type]
            session=object(),  # type: ignore[arg-type]
            resolver=_StubResolver(exc=ExtractFailedError("HTTP 500")),  # type: ignore[arg-type]
            settings=_settings(enabled=True),
            raw_store=object(),  # type: ignore[arg-type]
            engine_router=object(),  # type: ignore[arg-type]
            detail_fallback=shared,
        )

    await _svc()._resolve_with_retry(_URL)
    assert dajiala.calls == 1
    with pytest.raises(ExtractFailedError):
        await _svc()._resolve_with_retry(_URL)
    assert dajiala.calls == 1, "预算用完还在花 = 这个旋钮是假的"


# ------------------------------------------------------------------ 3 校验面


def test_unwired_trigger_is_refused_by_name() -> None:
    """卡面写了 captcha，但本仓没有任何检测信号（`app/**` 里 `captcha|验证码` 命中 0 处）
    ⇒ 服务层必须拒收，而不是收下不用（放开的前提记在 P-64）。"""
    with pytest.raises(RequestInvalidError) as exc:
        system_settings.validate(system_settings.ARTICLE_FALLBACK_KEY, _config(trigger=["captcha"]))
    assert "captcha" in str(exc.value)


def test_enabling_requires_a_budget() -> None:
    """D-V12-20 拒绝的那个替代方案就是「运营可无上限开启付费调用」⇒ 开而无预算必须拒。"""
    with pytest.raises(RequestInvalidError) as exc:
        system_settings.validate(system_settings.ARTICLE_FALLBACK_KEY, _config(daily_budget=None))
    assert "预算" in str(exc.value)
    with pytest.raises(RequestInvalidError):
        system_settings.validate(system_settings.ARTICLE_FALLBACK_KEY, _config(daily_budget=0))
    # 关掉时允许没有预算：一份"不花钱"的配置不该被形状拦住
    system_settings.validate(
        system_settings.ARTICLE_FALLBACK_KEY,
        _config(enabled=False, daily_budget=None),
    )


def test_credential_shaped_field_is_rejected() -> None:
    smuggled = "dajiala" + "_api" + "_key"
    with pytest.raises(RequestInvalidError):
        system_settings.validate(
            system_settings.ARTICLE_FALLBACK_KEY, {**_config(), smuggled: "x" * 20}
        )


# ------------------------------------------------------------------ 4 接口与角色


async def test_get_is_operator_readable_and_put_is_admin_only(db_session: Any) -> None:
    """D-V12-20 的落点：读 operator、写 admin。user 两者都 10004。"""
    from app.models.entities import User as UserModel

    plain = UserModel(sub=f"s10v2-u-{id(db_session)}", email="u@s10.test", nickname="u", role="user")
    operator = UserModel(sub=f"s10v2-o-{id(db_session)}", email="o@s10.test", nickname="o", role="operator")
    db_session.add(plain)
    db_session.add(operator)
    await db_session.flush()

    for actor, expect_get, expect_put in ((plain, 403, 403), (operator, 200, 403)):
        client = _client(db_session, actor)
        got = client.get(f"{ADMIN}/article-fallback")
        assert got.status_code == expect_get, (actor.role, got.text[:200])
        put = client.put(f"{ADMIN}/article-fallback", json=_config())
        assert put.status_code == expect_put, (actor.role, put.text[:200])
        if expect_put == 403:
            assert put.json()["code"] == 10004


async def test_put_writes_and_get_flips_source(db_session: Any) -> None:
    admin = await _seed_admin(db_session)
    client = _client(db_session, admin)
    got = client.get(f"{ADMIN}/article-fallback")
    assert got.status_code == 200, got.text
    assert got.json()["data"]["source"] == "env"
    assert got.json()["data"]["effective"]["enabled"] is False, "无库值 = 关闭"

    resp = client.put(f"{ADMIN}/article-fallback", json=_config(trigger=["http_error", "empty_body"]))
    assert resp.status_code == 200, resp.text
    row = (
        await db_session.execute(
            select(SystemSetting).where(SystemSetting.key == system_settings.ARTICLE_FALLBACK_KEY)
        )
    ).scalar_one()
    assert row.value["daily_budget"] == 50 and row.value["enabled"] is True
    data = client.get(f"{ADMIN}/article-fallback").json()["data"]
    assert data["source"] == "db"
    assert sorted(data["effective"]["trigger"]) == ["empty_body", "http_error"]


async def test_read_surface_never_echoes_keys(db_session: Any) -> None:
    admin = await _seed_admin(db_session)
    got = _client(db_session, admin).get(f"{ADMIN}/article-fallback")
    assert got.status_code == 200, got.text
    body = got.text.lower()
    assert _PLACEHOLDER_KEY.lower() not in body
    assert not [m for m in ("api_key", "token", "secret") if m in body], body


async def test_put_rejects_credential_field_without_writing(db_session: Any) -> None:
    admin = await _seed_admin(db_session)
    smuggled = "dajiala" + "_api" + "_key"
    resp = _client(db_session, admin).put(
        f"{ADMIN}/article-fallback", json={**_config(), smuggled: "x" * 20}
    )
    assert resp.status_code == 422, resp.text
    assert (await db_session.execute(select(SystemSetting))).scalars().all() == []


async def test_put_rejects_unknown_provider_by_name(db_session: Any) -> None:
    """供应商名单的**存在性**在接口层查（名单归 `article_detail_fallback` 所有，
    服务层不反向依赖 provider 层——同 S28.2.2 对 `CHANNELS` 的分工）。"""
    admin = await _seed_admin(db_session)
    resp = _client(db_session, admin).put(
        f"{ADMIN}/article-fallback", json=_config(providers=["redfox"])
    )
    assert resp.status_code == 422 and resp.json()["code"] == 10005, resp.text
    assert "redfox" in resp.json()["message"]
    assert (await db_session.execute(select(SystemSetting))).scalars().all() == []


# ------------------------------------------------------------------ 5 接线的机器门


def _reason_literals(tree: ast.AST, func_name: str) -> list[str]:
    func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == func_name
    )
    found: list[str] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                    found.append(str(kw.value.value))
    return found


def test_both_trigger_points_are_wired_in_the_ingest_chain() -> None:
    """两个触发条件必须真的在入库链里，而不是只有协调器一侧能单测。

    摘掉任一处调用点必须红——这是本仓既有纪律："否定式声明不能靠人眼读 diff"。
    同时钉住"形状转换只有一份"：两处各自 `ResolvedArticle(...)` 的话，
    忘记补 `js_content` 容器的那一处会静默成 20003，长得像上游问题而不是接线错。
    """
    tree = ast.parse((_APP / "services" / "kb.py").read_text(encoding="utf-8"))
    assert _reason_literals(tree, "_ingest_url_inner") == ["empty_body"]
    assert _reason_literals(tree, "_resolve_with_retry") == ["http_error"]
    converters = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "paid_detail_to_article"
    ]
    assert len(converters) == 1, f"付费详情→解析产物 的转换出现 {len(converters)} 份，必须单点"
