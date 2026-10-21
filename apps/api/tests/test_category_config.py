"""STEP-28 S28.3：采集分类的运营可配置（清单 + 每类关键词 + 启停 + 顺序）。

这一族的判据分三层，缺任何一层都会留下"看起来配好了"的假绿：

1. **自动分类**（`categorize`）只看启用的类，按声明序取首个标题命中；
2. **人工纠偏**（`spaces.validate_category`）接受"库里登记过的类"，含**停用**的——
   停用的含义是"不再自动分进来"，不是"历史行不能再改、筛选里不能再看"；
3. **呈现序**（`spaces.order_categories`）跟库里的声明序走，含停用的类。

删除保护：新列表里没有、而旧生效列表里有的类 = 删除。若 `content_assets` 还有行引用它，
必须 422 并给出引用数——不回写历史数据是 D-V12-12 这一族的既定口径（卡面 §1）。

`其他` 是 `DEFAULT_CATEGORY` 兜底，零命中要有落点，所以必须存在且启用。
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
from app.models.entities import ContentAsset, KnowledgeDocument, Source, User
from app.services import system_settings
from app.services.categorizer import (
    CATEGORIES,
    DEFAULT_CATEGORY,
    active_categories,
    categorize,
    category_allowlist,
    default_categories,
    enabled_rules,
)
from app.services.spaces import SpaceValidationError, order_categories, validate_category

ADMIN = "/api/v1/admin"
NEW_CATEGORY = "质量·验收"
NEW_KEYWORD = "验证"
REFERENCED = "教程·实践"


@pytest.fixture(autouse=True)
def _isolated_snapshot() -> Any:
    system_settings.reset_snapshot()
    yield
    system_settings.reset_snapshot()


async def _operator(db_session: Any) -> User:
    user = User(
        sub=f"s28-cat-{id(db_session)}-{id(object())}",
        email="s28-cat@s28.test",
        nickname="s28 cat",
        role="operator",
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


def _with_new_category(*, enabled: bool = True) -> list[dict[str, Any]]:
    """默认清单 + 一个新类排在最前（声明序即优先级）。"""
    items: list[dict[str, Any]] = [
        {"name": NEW_CATEGORY, "keywords": [NEW_KEYWORD], "enabled": enabled}
    ]
    for item in default_categories():
        items.append(dict(item))
    return items


def _without(name: str) -> list[dict[str, Any]]:
    return [dict(item) for item in default_categories() if item["name"] != name]


# ------------------------------------------------------------------ 1 自动分类


def test_defaults_are_the_verbatim_era_when_no_db_value() -> None:
    """无库值 ⇒ 与今天逐字一致：类序、规则表、兜底都不变。"""
    assert active_categories() == CATEGORIES
    assert [name for name, _ in enabled_rules()] == [c for c in CATEGORIES if c != DEFAULT_CATEGORY]
    assert categorize("一篇没有主题的文章", "其中提到了一次算法") == DEFAULT_CATEGORY
    assert categorize("", "") == DEFAULT_CATEGORY
    assert default_categories()[-1]["name"] == DEFAULT_CATEGORY


async def test_new_keyword_only_lands_after_the_db_value(db_session: Any) -> None:
    """S28.3.1.a 的改后绿形：库里加「质量·验收」+ 关键词「验证」⇒ 命中的是它。

    同一判据改前的读数是「其他」，原文记在 EVD-V15-28。
    """
    assert categorize("某清洗验证通报", "") == DEFAULT_CATEGORY  # 无库值时仍是旧行为
    actor = await _operator(db_session)
    await system_settings.put(db_session, system_settings.CATEGORIES_KEY, _with_new_category(), actor=actor)
    assert categorize("某清洗验证通报", "") == NEW_CATEGORY


async def test_disabled_category_never_matches_automatically(db_session: Any) -> None:
    actor = await _operator(db_session)
    await system_settings.put(
        db_session, system_settings.CATEGORIES_KEY, _with_new_category(enabled=False), actor=actor
    )
    assert categorize("某清洗验证通报", "") != NEW_CATEGORY
    assert NEW_CATEGORY in active_categories()  # 停用≠从筛选里消失
    assert NEW_CATEGORY not in [name for name, _ in enabled_rules()]


async def test_declaration_order_is_the_priority(db_session: Any) -> None:
    """同一标题被两类命中 ⇒ 取声明序在前的那个（顺序即粒度设计）。"""
    actor = await _operator(db_session)
    await system_settings.put(
        db_session,
        system_settings.CATEGORIES_KEY,
        [
            {"name": "甲类", "keywords": ["验证"], "enabled": True},
            {"name": "乙类", "keywords": ["清洗"], "enabled": True},
            {"name": DEFAULT_CATEGORY, "keywords": [], "enabled": True},
        ],
        actor=actor,
    )
    assert categorize("清洗规则验证文章", "") == "甲类"
    assert order_categories(["乙类", "甲类", DEFAULT_CATEGORY]) == ["甲类", "乙类", DEFAULT_CATEGORY]


# ------------------------------------------------------------------ 2 人工纠偏


def test_manual_correction_accepts_disabled_and_rejects_unlisted() -> None:
    system_settings.prime(
        system_settings.CATEGORIES_KEY,
        system_settings.validate(
            system_settings.CATEGORIES_KEY,
            [
                {"name": NEW_CATEGORY, "keywords": [NEW_KEYWORD], "enabled": False},
                {"name": DEFAULT_CATEGORY, "keywords": [], "enabled": True},
            ],
        ),
    )
    assert NEW_CATEGORY in category_allowlist()
    validate_category(NEW_CATEGORY)  # 停用类仍可人工指定：纠偏权在运营手里
    with pytest.raises(SpaceValidationError) as exc:
        validate_category("从没登记过的类")
    assert NEW_CATEGORY in str(exc.value)  # 报错要给出可选项，否则运营只能猜


# ------------------------------------------------------------------ 3 接口


async def test_get_categories_reports_env_source_and_default_keywords(db_session: Any) -> None:
    actor = await _operator(db_session)
    got = _client(db_session, actor).get(f"{ADMIN}/categories")
    assert got.status_code == 200, got.text
    data = got.json()["data"]
    assert data["source"] == "env"
    assert [c["name"] for c in data["categories"]] == CATEGORIES
    assert data["defaultCategory"] == DEFAULT_CATEGORY


async def test_put_categories_writes_and_get_flips_to_db_source(db_session: Any) -> None:
    actor = await _operator(db_session)
    client = _client(db_session, actor)
    resp = client.put(f"{ADMIN}/categories", json={"categories": _with_new_category()})
    assert resp.status_code == 200, resp.text
    data = client.get(f"{ADMIN}/categories").json()["data"]
    assert data["source"] == "db"
    assert data["categories"][0]["name"] == NEW_CATEGORY
    row = (
        await db_session.execute(
            select(SystemSetting).where(SystemSetting.key == system_settings.CATEGORIES_KEY)
        )
    ).scalar_one()
    assert row.value[0]["name"] == NEW_CATEGORY


@pytest.mark.parametrize(
    ("categories", "needle"),
    [
        ([{"name": "AI·技术", "keywords": ["AI"]}], DEFAULT_CATEGORY),
        ([], "至少"),
        (
            [
                {"name": "重复", "keywords": ["x"]},
                {"name": "重复", "keywords": ["y"]},
                {"name": DEFAULT_CATEGORY, "keywords": []},
            ],
            "重复",
        ),
        (
            [{"name": "长" * 33, "keywords": ["x"]}, {"name": DEFAULT_CATEGORY, "keywords": []}],
            "32",
        ),
        (
            [{"name": "空的关键词", "keywords": [""]}, {"name": DEFAULT_CATEGORY, "keywords": []}],
            "关键词",
        ),
    ],
    ids=["missing-bottom-out", "empty", "duplicate-name", "overlong-name", "blank-keyword"],
)
async def test_put_categories_rejects_illegal_lists(db_session: Any, categories: Any, needle: str) -> None:
    actor = await _operator(db_session)
    resp = _client(db_session, actor).put(f"{ADMIN}/categories", json={"categories": categories})
    assert resp.status_code == 422 and resp.json()["code"] == 10005, resp.text
    assert needle in resp.json()["message"]
    assert (await db_session.execute(select(SystemSetting))).scalars().all() == []


async def test_put_categories_rejects_credential_shaped_field(db_session: Any) -> None:
    actor = await _operator(db_session)
    smuggled = "tikhub" + "_api" + "_key"
    body = {
        "categories": [
            {"name": NEW_CATEGORY, "keywords": [NEW_KEYWORD]},
            {"name": DEFAULT_CATEGORY, "keywords": []},
        ],
        smuggled: "x" * 24,
    }
    resp = _client(db_session, actor).put(f"{ADMIN}/categories", json=body)
    assert resp.status_code == 422, resp.text
    assert (await db_session.execute(select(SystemSetting))).scalars().all() == []


async def test_removing_a_referenced_category_is_refused_with_the_count(db_session: Any) -> None:
    """删除保护：还有行引用的类不许从清单里消失，且读数要给出引用数。"""
    actor = await _operator(db_session)
    tag = id(db_session)
    source = Source(type="wechat_oa", external_id=f"s28-ref-{tag}", name="s28 引用源")
    db_session.add(source)
    await db_session.flush()
    for n in range(2):
        db_session.add(
            ContentAsset(
                source_id=source.id,
                external_id=f"s28-ref-asset-{tag}-{n}",
                content_hash=f"s28-ref-hash-{tag}-{n}",
                content_markdown="正文",
                category=REFERENCED,
            )
        )
    await db_session.flush()

    resp = _client(db_session, actor).put(f"{ADMIN}/categories", json={"categories": _without(REFERENCED)})
    assert resp.status_code == 422 and resp.json()["code"] == 10005, resp.text
    message = resp.json()["message"]
    assert REFERENCED in message and "2" in message, message


async def test_stopping_a_referenced_category_is_allowed(db_session: Any) -> None:
    """停用不是删除：有引用也放行，历史行与筛选可见性不变。"""
    actor = await _operator(db_session)
    tag = id(db_session)
    source = Source(type="wechat_oa", external_id=f"s28-stop-{tag}", name="s28 停用源")
    db_session.add(source)
    await db_session.flush()
    db_session.add(
        ContentAsset(
            source_id=source.id,
            external_id=f"s28-stop-asset-{tag}",
            content_hash=f"s28-stop-hash-{tag}",
            content_markdown="正文",
            category=REFERENCED,
        )
    )
    await db_session.flush()

    items = [dict(item) for item in default_categories()]
    for item in items:
        if item["name"] == REFERENCED:
            item["enabled"] = False
    resp = _client(db_session, actor).put(f"{ADMIN}/categories", json={"categories": items})
    assert resp.status_code == 200, resp.text


# ------------------------------------------------------------------ 4 入库链路端到端


async def test_worker_round_picks_up_the_new_categories(db_session: Any) -> None:
    """worker 侧的"下一轮"接线（`job_worker.run_once` 轮首，申报过的越界，见 EVD-V15-28）。

    与 scheduler 那条同形：清空快照 ⇒ 跑一轮 ⇒ 分类读到库值。
    worker 是分类真正被写入 `content_assets` 的那个进程，少接一行就是"后台改了、入库照旧"。
    """
    from app.services.job_worker import JobWorker  # noqa: PLC0415

    actor = await _operator(db_session)
    await system_settings.put(db_session, system_settings.CATEGORIES_KEY, _with_new_category(), actor=actor)
    system_settings.reset_snapshot()
    assert categorize("某清洗验证通报", "") == DEFAULT_CATEGORY

    class _SessionCtx:
        def __init__(self, session: Any) -> None:
            self._session = session

        async def __aenter__(self) -> Any:
            return self._session

        async def __aexit__(self, *exc: object) -> bool:
            return False

    async def _never_called(session: Any, space_id: str, url: str) -> dict[str, Any]:  # noqa: ARG001
        raise AssertionError("本轮无 job，不该调用入库桩")

    worker = JobWorker(
        lambda: _SessionCtx(db_session),
        _never_called,
        settings=Settings(),
        idle_sleep_seconds=0.0,
        heartbeat_enabled=False,
    )
    assert await worker.run_once() is False, "本轮不该有 job；有就说明夹具被上一批污染了"
    assert categorize("某清洗验证通报", "") == NEW_CATEGORY


async def test_service_path_reads_the_db_value_by_itself(db_session: Any) -> None:
    """`SpaceService` 的分类校验读的是**现值**，不靠"这个进程碰巧刷过快照"。

    刻意绕开 `put()`（它顺手把本进程快照刷了），用裸 ORM 写配置行 + `reset_snapshot()`，
    再走 service 的纠偏路径 ⇒ 新类必须被接受。少了 `spaces.py` 里那句 `ensure_loaded`，
    这里读到的还是默认清单，新类会被 10005 拒——"运营配好了、接口按旧值拒"就是这条抓的。
    """
    from test_docs_pagination import _seed_doc, _seed_source, _seed_user_and_space  # noqa: PLC0415

    from app.repositories.space import SpaceRepository  # noqa: PLC0415
    from app.services.spaces import SpaceService  # noqa: PLC0415

    tag = id(db_session)
    user, space = await _seed_user_and_space(db_session, f"sub-s28-live-{tag}", "S28 现值空间")
    source = await _seed_source(db_session, f"s28-live-biz-{tag}")
    await _seed_doc(db_session, space.id, source.id, f"s28-live-doc-{tag}")
    db_session.add(SystemSetting(key=system_settings.CATEGORIES_KEY, value=_with_new_category()))
    await db_session.flush()
    doc = (
        await db_session.execute(select(KnowledgeDocument).where(KnowledgeDocument.space_id == space.id))
    ).scalar_one()

    system_settings.reset_snapshot()
    assert NEW_CATEGORY not in category_allowlist(), "前置：快照清空后新类还不可见"

    svc = SpaceService(SpaceRepository(db_session), session=db_session)
    view = await svc.update_doc_category(user.id, space.id, doc.id, NEW_CATEGORY)
    assert view["category"] == NEW_CATEGORY, view
    assert NEW_CATEGORY in await svc.list_doc_categories(user.id, space.id)


async def test_ingest_path_assigns_the_configured_category(db_session: Any) -> None:
    """S28.4.2 的端到端读数：PUT 分类 ⇒ `kb.ingest` 落库的 `content_assets.category` 是新值。

    走真实入库链（`_StubResolver` 解析固定样本，标题「清洗规则验证文章」），因为
    "接口写进去了"与"下一轮入库真的用了它"是两个命题——后者才是卡面 §0 的目标。
    """
    from test_langbot import _client as _langbot_client  # noqa: PLC0415
    from test_langbot import _StubResolver

    from app.repositories.space import SpaceRepository  # noqa: PLC0415
    from app.repositories.user import SqlAlchemyUserStore  # noqa: PLC0415
    from app.services.kb import KnowledgeBaseService  # noqa: PLC0415

    actor = await _operator(db_session)
    tag = id(db_session)
    user = await SqlAlchemyUserStore(db_session).upsert_by_sub(f"sub-s28-{tag}", "s28@t.local", "S28")
    space = await SpaceRepository(db_session).create(user_id=user.id, name="S28 分类配置空间")
    await db_session.commit()

    svc = KnowledgeBaseService(_langbot_client(), db_session, _StubResolver())

    async def _category_of(url: str) -> str:
        view = await svc.ingest_url(space.id, url)
        doc = (
            await db_session.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == view["docId"]))
        ).scalar_one()
        asset = (
            await db_session.execute(select(ContentAsset).where(ContentAsset.id == doc.asset_id))
        ).scalar_one()
        return str(asset.category)

    assert await _category_of(f"https://mp.weixin.qq.com/s/s28-before-{tag}?biz=MjM5MjgwNTQ1MQ==") == DEFAULT_CATEGORY

    resp = _client(db_session, actor).put(f"{ADMIN}/categories", json={"categories": _with_new_category()})
    assert resp.status_code == 200, resp.text

    assert await _category_of(f"https://mp.weixin.qq.com/s/s28-after-{tag}?biz=MjM5MjgwNTQ1MQ==") == NEW_CATEGORY
