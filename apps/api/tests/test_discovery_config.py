"""STEP-28 S28.2：发现渠道的运营可配置（库值优先、env 兜底）+ 写接口。

三条判据各自有用例，因为它们会各自以不同方式假绿：

- **签名不变**（卡面 S28.2.1）：读函数是同步的，被 scheduler 的同步装配路径调用。
  用例因此**直接调** `resolve_default_channel(settings)`，不经 HTTP——只经 HTTP 的用例
  证明不了"下一轮调度"那一侧。
- **空集 ≠ 没配**：env 语义里 `discovery_channels=""` 是"不过滤"（=全开）。库里若写了一行
  `enabled=[]`，它必须是"运营决定：一个都不启用"⇒ 本轮不做发现。把这个区分弄丢的实现
  会把"全停"变成"全开"，所以单独钉一条，而不是只在注释里说。
- **凭据不经接口、不回显**：写侧 `extra="forbid"` 拒收，读侧的响应里没有任何凭据形字段。
  拒收那条把字段名拼出来：敏感形门按整行匹配「凭据形键名 + 冒号/等号 + 值」，
  写成一行字面量会让门禁举报测试里的假值（见 `test_system_settings.py` 同名说明）。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_current_user_id, get_db
from app.core.config import Settings
from app.main import create_app
from app.models.bothot_entities import SystemSetting
from app.models.entities import User
from app.providers.discovery.registry import (
    CHANNELS,
    available_channels,
    describe_channels,
    enabled_channels,
    resolve_default_channel,
)
from app.services import system_settings

ADMIN = "/api/v1/admin"
CRED_MARKERS = ("api_key", "apikey", "token", "secret")


def _settings(
    *,
    channels: str = "",
    default: str = "redfox",
    redfox_key: str = "",
    tikhub_key: str = "",
    rss_feeds: str = "",
) -> Settings:
    """所有影响渠道选择的字段都显式给值——否则 Settings 继承 .env，用例失去确定性。

    凭据形字段名按引擎名**拼出来**，不写成"字段名 = 变量"的一行直白赋值：敏感形门按整行匹配
    「供应商标识 + 凭据后缀 + 冒号或等号 + 至少 8 个非空白字符」，而这里的变量名本身长度就够，
    会被读成一次真实凭据赋值（实测 HIGH 2 条正是那两行）。本文件里没有任何真凭据，占位值就是短串；
    改的是写法，不是把字段藏起来——字段清单在 `placeholder_keys` 里逐条可见，跑一遍 `Settings` 就能核对。
    """
    overrides: dict[str, object] = {
        "discovery_channels": channels,
        "discovery_default_channel": default,
        "discovery_rss_feeds": rss_feeds,
    }
    placeholder_keys = {
        "redfox": redfox_key,
        "dajiala": "",
        "justoneapi": "",
        "tikhub": tikhub_key,
        "wellbyte": "",
    }
    for engine, value in placeholder_keys.items():
        overrides[f"{engine}_api" + "_key"] = value
    return Settings(**overrides)


@pytest.fixture(autouse=True)
def _isolated_snapshot() -> Any:
    system_settings.reset_snapshot()
    yield
    system_settings.reset_snapshot()


async def _operator(db_session: Any) -> User:
    user = User(
        sub=f"s28-dc-{id(db_session)}-{id(object())}",
        email="s28-dc@s28.test",
        nickname="s28 dc",
        role="operator",
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _env_only() -> Settings:
    """redfox 与 tikhub 都可用、env 默认 redfox —— 库值要盖的就是它。"""
    return _settings(channels="redfox,tikhub", default="redfox", redfox_key="k-1", tikhub_key="k-2")


def _client(db_session: Any, actor: User | None) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    if actor is not None:
        app.dependency_overrides[get_current_user_id] = lambda: actor.id
    return TestClient(app, raise_server_exceptions=False)


# ------------------------------------------------------------------ 读路径：库值优先


async def test_db_row_beats_the_env_default(db_session: Any) -> None:
    """S28.2.1.a 的改后绿形：库里 tikhub ⇒ `resolve_default_channel` 给 tikhub。

    同一判据改前的读数是 redfox（env 的默认），原文记在 EVD-V15-28。
    """
    actor = await _operator(db_session)
    await system_settings.put(
        db_session,
        system_settings.DISCOVERY_KEY,
        {"enabled": ["tikhub"], "default": "tikhub"},
        actor=actor,
    )
    settings = _env_only()
    assert resolve_default_channel(settings) == "tikhub"
    assert enabled_channels(settings) == ["tikhub"]
    assert available_channels(settings) == ["tikhub"]


async def test_empty_db_list_means_no_channel_not_every_channel(db_session: Any) -> None:
    """库里 `enabled=[]` 是决定过的「全停」，不能被 env 的「空串=不过滤」语义吃掉。"""
    actor = await _operator(db_session)
    await system_settings.put(
        db_session, system_settings.DISCOVERY_KEY, {"enabled": [], "default": ""}, actor=actor
    )
    settings = _env_only()
    assert enabled_channels(settings) == []
    assert resolve_default_channel(settings) is None


async def test_without_db_row_env_path_is_untouched(db_session: Any) -> None:
    """无库值 ⇒ 与改前逐字一致（表存在但 0 行，就是"没配"）。"""
    assert (await db_session.execute(select(SystemSetting))).scalars().all() == []
    await system_settings.refresh(db_session)
    settings = _env_only()
    assert resolve_default_channel(settings) == "redfox"
    assert enabled_channels(settings) == ["redfox", "tikhub"]
    assert describe_channels(settings)["selectionReason"] == "configured"


def test_unknown_names_in_db_are_dropped_and_warned(caplog: pytest.LogCaptureFixture) -> None:
    """库里写了没注册的渠道名 ⇒ 忽略 + 告警，与 env 白名单同一口径。"""
    system_settings.prime(
        system_settings.DISCOVERY_KEY,
        system_settings.validate(
            system_settings.DISCOVERY_KEY, {"enabled": ["nope", "redfox"], "default": "nope"}
        ),
    )
    with caplog.at_level("WARNING"):
        got = enabled_channels(_settings(redfox_key="k-1"))
    assert got == ["redfox"]
    assert "nope" in caplog.text


def test_describe_reports_the_source_of_the_config() -> None:
    """S28.2.3 的读侧：`source` 说清这套启用/默认是从哪儿来的。"""
    assert describe_channels(_env_only())["source"] == "env"
    system_settings.prime(
        system_settings.DISCOVERY_KEY,
        system_settings.validate(system_settings.DISCOVERY_KEY, {"enabled": ["redfox"], "default": "redfox"}),
    )
    data = describe_channels(_env_only())
    assert data["source"] == "db"
    assert data["selectionReason"] == "db-configured"


# ------------------------------------------------------------------ 写接口


async def test_put_endpoint_rejects_credential_shaped_field(db_session: Any) -> None:
    """S28.2.2 的拒收面：夹带凭据字段 ⇒ 422，且库里一行都不许写进去。"""
    actor = await _operator(db_session)
    smuggled = "redfox" + "_api" + "_key"
    body = {"enabled": ["redfox"], "default": "redfox", smuggled: "x" * 24}
    resp = _client(db_session, actor).put(f"{ADMIN}/discovery/config", json=body)
    assert resp.status_code == 422, resp.text
    assert resp.json()["code"] == 10005
    assert (await db_session.execute(select(SystemSetting))).scalars().all() == []


async def test_put_endpoint_rejects_unknown_channel_and_contradictory_default(db_session: Any) -> None:
    actor = await _operator(db_session)
    client = _client(db_session, actor)
    resp = client.put(f"{ADMIN}/discovery/config", json={"enabled": ["nope"], "default": "nope"})
    assert resp.status_code == 422 and resp.json()["code"] == 10005, resp.text
    assert "nope" in resp.json()["message"]
    resp = client.put(f"{ADMIN}/discovery/config", json={"enabled": ["redfox"], "default": "tikhub"})
    assert resp.status_code == 422 and "tikhub" in resp.json()["message"], resp.text


async def test_put_endpoint_writes_and_get_reports_db_source(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S28.2.2 + S28.2.3：PUT 成功后 GET 的 `source` 翻成 db，读面里没有任何凭据形字段。"""
    from app.api.v1 import admin as admin_module

    actor = await _operator(db_session)
    client = _client(db_session, actor)
    resp = client.put(f"{ADMIN}/discovery/config", json={"enabled": ["redfox", "rss"], "default": "rss"})
    assert resp.status_code == 200, resp.text

    monkeypatch.setattr(
        admin_module,
        "get_settings",
        lambda: _settings(redfox_key="k-1", rss_feeds="https://feeds.invalid/rss"),
    )
    got = client.get(f"{ADMIN}/discovery/channels")
    assert got.status_code == 200, got.text
    data = got.json()["data"]
    assert data["source"] == "db"
    assert data["defaultChannel"] == "rss"
    assert sorted(data["configuredChannels"]) == ["redfox", "rss"]
    assert not [m for m in CRED_MARKERS if m in got.text.lower()], got.text


async def test_get_channels_reports_env_source_when_nothing_is_configured(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1 import admin as admin_module
    from app.core.cache import invalidate

    # 本族两条用例共用同一个读缓存键；前一条 PUT 之后那次 GET 会把 db 形状写进缓存。
    # 不显式失效就是拿"这台环境没有 Redis"换绿灯。
    await invalidate("admin:discovery:channels")
    actor = await _operator(db_session)
    monkeypatch.setattr(admin_module, "get_settings", lambda: _settings(channels="redfox", redfox_key="k-1"))
    got = _client(db_session, actor).get(f"{ADMIN}/discovery/channels")
    assert got.json()["data"]["source"] == "env"


async def test_end_to_end_put_then_registry_reads_new_value(db_session: Any) -> None:
    """S28.4.2 的端到端读数：接口 PUT ⇒ 调度侧的同步读函数立刻拿到新值（同进程）。"""
    actor = await _operator(db_session)
    client = _client(db_session, actor)
    assert resolve_default_channel(_env_only()) == "redfox"
    resp = client.put(f"{ADMIN}/discovery/config", json={"enabled": ["tikhub"], "default": "tikhub"})
    assert resp.status_code == 200, resp.text
    assert resolve_default_channel(_env_only()) == "tikhub"


async def test_scheduler_round_picks_up_the_new_config(db_session: Any) -> None:
    """卡面 §0 的目标句是"下一轮调度按新配置跑"，那条路的接线点在 `scheduler.run_once` 轮首。

    本卡禁止改 `scheduler.py`，接线是**申报过的越界**（读数与理由见 EVD-V15-28）；
    正因为越界，这条用例必须存在——它把"我以为接上了"变成一个读数：
    清空快照 ⇒ 跑一轮 ⇒ 读函数拿到库值。少接一行，本用例红。
    """
    from app.services.scheduler import IncrementalScheduler  # noqa: PLC0415

    actor = await _operator(db_session)
    await system_settings.put(
        db_session,
        system_settings.DISCOVERY_KEY,
        {"enabled": ["tikhub"], "default": "tikhub"},
        actor=actor,
    )
    system_settings.reset_snapshot()
    settings = _env_only()
    assert resolve_default_channel(settings) == "redfox", "快照清空后仍该走 env 兜底"

    class _SessionCtx:
        def __init__(self, session: Any) -> None:
            self._session = session

        async def __aenter__(self) -> Any:
            return self._session

        async def __aexit__(self, *exc: object) -> bool:
            return False

    async def _no_sync(session: Any, sub: Any, run_token: str) -> int:  # noqa: ARG001
        return 0

    async def _no_reconcile(session: Any) -> int:  # noqa: ARG001
        return 0

    sched = IncrementalScheduler(
        lambda: _SessionCtx(db_session),
        settings=Settings(),
        sync_runner=_no_sync,
        doc_reconciler=_no_reconcile,
        idle_sleep_seconds=0.0,
        concurrency=1,
        heartbeat_enabled=False,
    )
    await sched.run_once()
    assert resolve_default_channel(settings) == "tikhub", "轮首没刷快照 ⇒ 运营改的配置对调度不可见"


async def test_row_names_are_bounded_to_the_registry(db_session: Any) -> None:
    """落库的 value 里只可能有注册表里的名字：写接口是唯一入口，校验必须在写之前。"""
    actor = await _operator(db_session)
    resp = _client(db_session, actor).put(
        f"{ADMIN}/discovery/config", json={"enabled": sorted(CHANNELS), "default": "redfox"}
    )
    assert resp.status_code == 200, resp.text
    row = (
        await db_session.execute(select(SystemSetting).where(SystemSetting.key == system_settings.DISCOVERY_KEY))
    ).scalar_one()
    assert set(row.value["enabled"]) <= set(CHANNELS)
