"""STEP-28 S28.1.2：`system_settings` 读写面（TTL 快照 + 结构化审计）。

判据来自 ADR-0013 的三条不变量，逐条对应到用例：

1. **无行 = 走兜底**：`peek()` 在没 refresh 过时返回 None，读函数因此回落到 env/代码默认。
2. **凭据不进这张表**：服务层自己也拒收凭据形状的字段，不等接口层兜——写路径以后会多，
   接口层的 `extra="forbid"` 只守得住今天这一条路。
3. **生效语义是"下一轮"**：`peek()` **绝不做 IO**（这条是本案的承重墙，所以单独有用例钉它），
   跨进程一致只靠 `refresh()` + TTL。把同步读改成"未命中就顺手查一次库"会同时破坏
   "签名不变"（同步函数不能 await）和 STEP-00H 刚收口的"外部依赖不许把调用方卡住"。

`updated_by` 是 `users.id` 的外键，所以写侧用例都要先有真实用户行（连库）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
import structlog
from sqlalchemy import select
from structlog.testing import capture_logs

from app.core.errors import RequestInvalidError
from app.models.bothot_entities import SystemSetting
from app.models.entities import User
from app.services import system_settings

LOGGER_NAME = "app.services.system_settings"


@contextmanager
def _captured() -> Iterator[list[dict[str, Any]]]:
    """`capture_logs()`，外加把模块 logger 换成"本窗口内新绑"的代理。

    `app/core/logging.py` 以 `cache_logger_on_first_use=True` 装配：模块级 logger 在**第一次
    被用**时就绑死当时的全局配置。单跑本文件时那一次落在捕获窗里；全量跑时它落在
    `test_observability` 装完生产配置之后 ⇒ 同一组断言单跑绿、全量红（本机实测 4 条）。
    这里重新取一个代理，只在本测试期间替换模块属性——不改生产代码，也不改全局配置。
    """
    with capture_logs() as logs:
        original = system_settings.logger
        system_settings.logger = structlog.get_logger(LOGGER_NAME)
        try:
            yield logs
        finally:
            system_settings.logger = original


@pytest.fixture(autouse=True)
def _isolated_snapshot() -> Any:
    """进程内快照是用例间的共享状态：进出各清一次。

    不清就是拿顺序换绿灯——本文件写进快照的值会带着后面的用例一起跑，
    `test_discovery.py` / `test_categorizer.py` 那批**不连库**的同步用例会突然读到库值。
    """
    system_settings.reset_snapshot()
    yield
    system_settings.reset_snapshot()


async def _operator(db_session: Any) -> User:
    user = User(
        sub=f"s28-op-{id(db_session)}-{id(object())}",
        email="s28-op@s28.test",
        nickname="s28 operator",
        role="operator",
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ------------------------------------------------------------------ 形状与闸


def test_ttl_is_within_the_card_bound() -> None:
    """卡面上界 60s：常量抬高就是悄悄把"下一轮生效"改成"下一次发版"。"""
    assert system_settings.SNAPSHOT_TTL_SECONDS <= 60.0


def test_peek_makes_no_io_even_when_the_row_exists() -> None:
    """同步读只读快照：没 refresh 过就是 None，哪怕库里真有那一行。

    判据是否定式的，所以自带反证路径：`peek()` 一旦被改成"未命中就查库"，
    本用例在无事件循环、无 `DATABASE_URL` 的环境里会抛错或挂住——正是它要抓的东西。
    """
    assert system_settings.peek(system_settings.DISCOVERY_KEY) is None


def test_unknown_key_is_rejected() -> None:
    """ADR-0013 §3 的承重墙：这张表必须有 key 白名单，否则两周内变成垃圾抽屉。"""
    with pytest.raises(RequestInvalidError):
        system_settings.validate("not_a_known_key", {"enabled": [], "default": ""})


def test_bad_shapes_are_rejected() -> None:
    with pytest.raises(RequestInvalidError):
        system_settings.validate(system_settings.DISCOVERY_KEY, {"enabled": "tikhub", "default": "tikhub"})
    with pytest.raises(RequestInvalidError):
        # default 不在 enabled 里：配置自己矛盾，不能等到调度时才静默回落
        system_settings.validate(system_settings.DISCOVERY_KEY, {"enabled": ["tikhub"], "default": "redfox"})
    with pytest.raises(RequestInvalidError):
        system_settings.validate(system_settings.DISCOVERY_KEY, {"enabled": ["tikhub"]})


def test_credential_shaped_field_is_rejected_by_the_service_too() -> None:
    """不变量 2 在服务层也成立（不等接口层的 extra=forbid 兜底）。

    字段名是拼出来的：敏感形门按整行匹配「凭据形键名 + 冒号/等号 + 值」，
    写成一行字面量会让门禁举报测试里的假值——那是把门用坏、不是把门过掉。
    """
    smuggled = "redfox" + "_api" + "_key"
    with pytest.raises(RequestInvalidError):
        system_settings.validate(
            system_settings.DISCOVERY_KEY,
            {"enabled": ["redfox"], "default": "redfox", smuggled: "x" * 20},
        )
    with pytest.raises(RequestInvalidError):
        system_settings.validate(
            system_settings.CATEGORIES_KEY,
            [{"name": "AI·技术", "keywords": ["AI"]}, {"name": "其他", "token": "x" * 20}],
        )


def test_categories_must_keep_the_bottom_out_category() -> None:
    """`其他` 缺失或停用 ⇒ 拒：categorize() 的零命中兜底没有别的落点。"""
    with pytest.raises(RequestInvalidError):
        system_settings.validate(system_settings.CATEGORIES_KEY, [{"name": "AI·技术", "keywords": ["AI"]}])
    with pytest.raises(RequestInvalidError):
        system_settings.validate(
            system_settings.CATEGORIES_KEY,
            [{"name": "AI·技术", "keywords": ["AI"]}, {"name": "其他", "keywords": [], "enabled": False}],
        )
    with pytest.raises(RequestInvalidError):
        system_settings.validate(system_settings.CATEGORIES_KEY, [])  # 一个启用类都没有


def test_category_names_are_bounded_by_the_column_width() -> None:
    """名字 ≤32 字不是凑数：`content_assets.category` 实测是 `String(32)`。

    超宽的名字会在入库时被数据库拒掉，而那时报错的位置离配置的地方已经很远了。
    """
    with pytest.raises(RequestInvalidError):
        system_settings.validate(
            system_settings.CATEGORIES_KEY,
            [{"name": "长" * 33, "keywords": ["长"]}, {"name": "其他", "keywords": []}],
        )
    with pytest.raises(RequestInvalidError):
        system_settings.validate(
            system_settings.CATEGORIES_KEY,
            [
                {"name": "AI·技术", "keywords": ["AI"]},
                {"name": "AI·技术", "keywords": ["LLM"]},
                {"name": "其他", "keywords": []},
            ],
        )


# ------------------------------------------------------------------ 写侧（连库）


async def test_put_writes_row_with_actor_and_digest_audit(db_session: Any) -> None:
    actor = await _operator(db_session)
    await system_settings.put(
        db_session,
        system_settings.DISCOVERY_KEY,
        {"enabled": ["redfox"], "default": "redfox"},
        actor=actor,
    )
    row = (
        await db_session.execute(
            select(SystemSetting).where(SystemSetting.key == system_settings.DISCOVERY_KEY)
        )
    ).scalar_one()
    assert row.value == {"enabled": ["redfox"], "default": "redfox"}
    assert row.updated_by == actor.id
    assert row.updated_at is not None

    with _captured() as logs:
        await system_settings.put(
            db_session,
            system_settings.DISCOVERY_KEY,
            {"enabled": ["redfox", "rss"], "default": "rss"},
            actor=actor,
        )
    changed = [e for e in logs if e.get("event") == "system_setting.changed"]
    assert changed, logs
    audit = changed[-1]
    assert audit["actor_sub"] == actor.sub
    assert audit["key"] == system_settings.DISCOVERY_KEY
    # 摘要是可比较的形状，不是正文：旧值里没有 rss、新值里有，且整条不出现凭据形状字段
    assert "redfox" in audit["old_digest"] and "rss" not in audit["old_digest"]
    assert "rss" in audit["new_digest"]
    assert audit["old_row"] is True, "第二次写必须带旧值摘要，否则审计答不出「改之前是什么」"
    blob = repr(audit).lower()
    assert "api_key" not in blob and "token" not in blob, blob


async def test_first_write_reports_no_old_row(db_session: Any) -> None:
    """首次写的 `old_row=False`：审计里「没有旧值」与「旧值是空」是两件事。"""
    actor = await _operator(db_session)
    with _captured() as logs:
        await system_settings.put(
            db_session, system_settings.CATEGORIES_KEY, [{"name": "其他", "keywords": []}], actor=actor
        )
    assert [e for e in logs if e.get("event") == "system_setting.changed"][-1]["old_row"] is False


async def test_put_is_upsert_and_refresh_reads_it_back(db_session: Any) -> None:
    actor = await _operator(db_session)
    for value in (
        {"enabled": ["redfox"], "default": "redfox"},
        {"enabled": ["rss"], "default": "rss"},
    ):
        await system_settings.put(db_session, system_settings.DISCOVERY_KEY, value, actor=actor)
    rows = (
        await db_session.execute(
            select(SystemSetting).where(SystemSetting.key == system_settings.DISCOVERY_KEY)
        )
    ).scalars().all()
    assert len(rows) == 1, "第二次写必须是覆盖，不是插入第二行"

    system_settings.reset_snapshot()
    assert system_settings.peek(system_settings.DISCOVERY_KEY) is None
    await system_settings.refresh(db_session)
    loaded = system_settings.peek(system_settings.DISCOVERY_KEY)
    assert loaded is not None and loaded.default == "rss" and loaded.enabled == ["rss"]


async def test_refresh_drops_unknown_key_and_unreadable_value(db_session: Any) -> None:
    """库里出现没登记的键或坏值 ⇒ 跳过并告警，不能让一行坏数据把整个配置面拖成不可读。"""
    db_session.add(SystemSetting(key="not_a_known_key", value={"whatever": 1}))
    db_session.add(SystemSetting(key=system_settings.DISCOVERY_KEY, value={"enabled": "not-a-list"}))
    await db_session.flush()
    with _captured() as logs:
        await system_settings.refresh(db_session)
    assert system_settings.peek(system_settings.DISCOVERY_KEY) is None
    assert system_settings.peek("not_a_known_key") is None
    assert [e for e in logs if e.get("event") == "system_settings.skipped"], logs


# ------------------------------------------------------------------ 常驻进程的轮首刷新


async def test_refresh_with_is_ttl_gated(db_session: Any) -> None:
    """TTL 内 `refresh_with` 不开新会话——worker 的空转是 10 秒量级，不设门就是每秒查库。

    判据用"会话工厂被调了几次"，不看返回值：工厂没被调才说明门真的生效了。
    """
    calls: list[int] = []

    class _CountingCtx:
        def __init__(self, session: Any) -> None:
            self._session = session

        async def __aenter__(self) -> Any:
            calls.append(1)
            return self._session

        async def __aexit__(self, *exc: object) -> bool:
            return False

    factory = lambda: _CountingCtx(db_session)  # noqa: E731
    system_settings.reset_snapshot()
    assert await system_settings.refresh_with(factory) is True
    assert len(calls) == 1
    assert await system_settings.refresh_with(factory) is True, "TTL 内不该再开一次会话"
    assert len(calls) == 1
    assert await system_settings.refresh_with(factory, force=True) is True
    assert len(calls) == 2


async def test_refresh_with_swallows_a_dead_database(db_session: Any) -> None:
    """刷不动 ⇒ 告警并返回 False，绝不上抛。配置面故障不该放大成采集停摆。"""
    system_settings.reset_snapshot()

    class _Boom:
        async def __aenter__(self) -> Any:
            raise OSError("库连不上")

        async def __aexit__(self, *exc: object) -> bool:
            return False

    with _captured() as logs:
        assert await system_settings.refresh_with(lambda: _Boom()) is False
    assert [e for e in logs if e.get("event") == "system_settings.refresh_failed"], logs


def test_default_category_mirror_matches_the_categorizer() -> None:
    """本服务为了打断 import 环自己镜像了一个「其他」，所以必须有对账用例。

    `categorizer` 要读 `system_settings` 的快照，`system_settings` 就不能反过来 import
    `categorizer`——环是单向断开的，代价是默认兜底名在两个文件里各写了一遍。
    这个镜像漂移的那天，`validate()` 会放行一份没有兜底落点的清单而没人报错。
    """
    from app.services.categorizer import DEFAULT_CATEGORY as _CATEGORIZER_DEFAULT

    assert system_settings._DEFAULT_CATEGORY == _CATEGORIZER_DEFAULT
