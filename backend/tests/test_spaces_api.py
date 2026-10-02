"""B-T4R 验收测试：spaces 域三端点（v0.3 契约）。

内存桩轮（无 DB）：camelCase 形状精确匹配 / 404(30004) / 10001 登录保护 /
越权隔离 / docs status 三值映射 / 30006 Service 映射；
连库轮（真实 PG:5433）：真约束重名 → 30006、join 查询形状、用户隔离。
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user_id, get_langbot_client, get_space_service
from app.core.errors import DependencyUnavailableError, LangbotApiError
from app.main import create_app
from app.repositories.space import SpaceRepository
from app.services.spaces import SpaceService

# ------------------------------------------------------------------ 内存桩


class InMemorySpaceRepo:
    """SpaceRepository 的内存桩（形状/路由行为测试用，接口对齐真 repo）。"""

    def __init__(self) -> None:
        self._spaces: dict[str, Any] = {}
        self._docs: dict[str, list[dict]] = {}  # space_id -> docs 行
        self._seq = 0
        self._conflict_names: set[tuple[str, str]] = set()  # (user_id, name) 模拟唯一约束

    def seed(
        self,
        user_id: str,
        name: str,
        docs: list[dict] | None = None,
        kb_uuid: str = "",
        description: str | None = None,
    ) -> str:
        self._seq += 1
        space_id = f"space-{self._seq}"
        now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
        self._spaces[space_id] = SimpleNamespace(
            id=space_id,
            user_id=user_id,
            name=name,
            created_at=now,
            updated_at=now,
            doc_count=len(docs or []),
            langbot_kb_uuid=kb_uuid,
            description=description,
        )
        self._docs[space_id] = docs or []
        return space_id

    async def create(
        self,
        user_id: str,
        name: str,
        langbot_kb_uuid: str = "",
        description: str | None = None,
    ) -> Any:
        if (user_id, name) in self._conflict_names:  # 模拟 uq_space_user_name
            raise IntegrityError(
                "INSERT", {}, Exception('duplicate key value violates unique constraint "uq_space_user_name"')
            )
        return SimpleNamespace(id=self.seed(user_id, name, description=description))

    async def get_by_id(self, space_id: str) -> Any:
        return self._spaces.get(space_id)

    async def get_by_name(self, user_id: str, name: str) -> Any:
        for s in self._spaces.values():
            if s.user_id == user_id and s.name == name:
                return s
        return None

    async def list_by_user(self, user_id: str, *, limit: int = 50, offset: int = 0) -> list[Any]:
        rows = [s for s in self._spaces.values() if s.user_id == user_id]
        return rows[offset : offset + limit]

    async def count_by_user(self, user_id: str) -> int:
        return sum(1 for s in self._spaces.values() if s.user_id == user_id)

    async def set_langbot_kb_uuid(self, space_id: str, kb_uuid: str) -> None:
        if space_id in self._spaces:
            self._spaces[space_id].langbot_kb_uuid = kb_uuid

    async def set_description(self, space_id: str, description: str | None) -> None:
        if space_id in self._spaces:
            self._spaces[space_id].description = description

    async def update_doc_count(self, space_id: str, delta: int) -> None:
        if space_id in self._spaces:
            self._spaces[space_id].doc_count = max(0, self._spaces[space_id].doc_count + delta)

    async def count_docs(self, space_id: str, category: str | None = None) -> int:
        return len(self._rows(space_id, category))

    async def count_docs_many(self, space_ids: list[str]) -> dict[str, int]:
        return {sid: len(self._docs.get(sid, [])) for sid in space_ids}

    async def count_chunks(self, space_id: str) -> int | None:
        return None  # R0.5.3（F-5）：数据源未接线 → 不下发 0（与真 repo 行为一致）

    async def list_docs(
        self,
        space_id: str,
        limit: int | None = None,
        offset: int = 0,
        category: str | None = None,
    ) -> list[dict]:
        rows = self._rows(space_id, category)
        if offset:
            rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return rows

    async def list_doc_categories(self, space_id: str) -> list[str]:
        # 去重即可；排序与哨兵翻译在 Service 层（与真 repo 分工一致）
        return list({r.get("category", "") for r in self._docs.get(space_id, [])})

    def _rows(self, space_id: str, category: str | None) -> list[dict]:
        """分类过滤谓词的单一来源：count_docs 与 list_docs 共用。

        与真 repo 的 `_docs_stmt` 对齐——total 与 items 必须走同一谓词，
        否则会出现「过滤后的列表配未过滤的 total」。"""
        rows = list(self._docs.get(space_id, []))
        if category is not None:
            rows = [r for r in rows if r.get("category", "") == category]
        return rows

    async def delete_space_cascade(self, space_id: str) -> dict[str, int]:
        docs = len(self._docs.pop(space_id, []))
        removed = self._spaces.pop(space_id, None)
        return {"docs": docs, "assets": 0, "spaces": 1 if removed else 0}


def _stub_client(svc: SpaceService, user_id: str = "user-1") -> tuple[TestClient, dict]:
    """构造 override 鉴权与 space service 的测试应用；返回 (client, 可变用户槽)。"""
    app = create_app()
    viewer = {"id": user_id}
    app.dependency_overrides[get_current_user_id] = lambda: viewer["id"]
    app.dependency_overrides[get_space_service] = lambda: svc
    return TestClient(app), viewer


def _seed_service(user_id: str = "user-1") -> SpaceService:
    repo = InMemorySpaceRepo()
    repo.seed(
        user_id,
        "技术文章",
        docs=[
            {
                "id": "d1",
                "title": "文章一",
                "source": "公众号A",
                "status": "FETCHED",
                "category": "AI·技术",
                "updated_at": datetime(2026, 9, 7, 10, 0, tzinfo=UTC),
            },
            {
                "id": "d2",
                "title": "文章二",
                "source": "公众号A",
                "status": "READY",
                "updated_at": datetime(2026, 9, 7, 10, 5, tzinfo=UTC),
            },  # 无 category = 未分类
            {
                "id": "d3",
                "title": "文章三",
                "source": "公众号B",
                "status": "FAILED",
                "category": "AI·技术",
                "updated_at": datetime(2026, 9, 7, 10, 6, tzinfo=UTC),
            },
        ],
    )
    return SpaceService(repo)


# ------------------------------------------------------------------ 内存桩轮


def test_list_spaces_items_camel_shape() -> None:
    """GET /spaces：data.items 键精确匹配 v0.3（camelCase）。"""
    client, _ = _stub_client(_seed_service())
    resp = client.get("/api/v1/spaces")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert set(items[0].keys()) == {
        "id",
        "name",
        "description",
        "docCount",
        "updatedAt",
        "engine",
        "engineKbId",
        "isPublic",  # AB-P004 P4 空间视图增量
    }
    assert items[0]["name"] == "技术文章" and items[0]["docCount"] == 3
    assert items[0]["updatedAt"].startswith("2026-09-07T12:00:00")
    assert items[0]["engine"] in ("builtin", "")  # 默认 builtin


def test_get_space_detail_shape_and_stats() -> None:
    """GET /spaces/{id}：详情键精确匹配 + stats{docs,chunks} + createdAt/updatedAt。"""
    client, _ = _stub_client(_seed_service())
    space_id = client.get("/api/v1/spaces").json()["data"]["items"][0]["id"]
    resp = client.get(f"/api/v1/spaces/{space_id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) == {
        "id",
        "name",
        "description",
        "docCount",
        "createdAt",
        "updatedAt",
        "stats",
        "engine",
        "engineKbId",
        "isPublic",  # AB-P004 P4 空间视图增量
    }
    assert set(data["stats"].keys()) == {"docs", "chunks"}
    assert data["stats"]["docs"] == 3 and data["docCount"] == 3  # count 查询而非 mock
    # R0.5.3（F-5）：chunk 数据源未接线时 chunks 为 null 而非 0。
    # 断言 is None 而非 != 0：0 会被前端渲成「已索引 0 块」，
    # 把「指标不可得」谎报成「真的没有分块」，契约就此变成一张假数。
    assert data["stats"]["chunks"] is None


def test_get_space_invalid_id_maps_30004() -> None:
    """GET /spaces/{id}：无效 id → 30004（404）。"""
    client, _ = _stub_client(_seed_service())
    resp = client.get("/api/v1/spaces/nope")
    assert resp.status_code == 404
    assert resp.json()["code"] == 30004


def test_space_isolation_between_users() -> None:
    """越权隔离：user-2 看 user-1 的空间 → 30004；列表互不可见。"""
    client, viewer = _stub_client(_seed_service("user-1"))
    space_id = client.get("/api/v1/spaces").json()["data"]["items"][0]["id"]
    viewer["id"] = "user-2"
    assert client.get(f"/api/v1/spaces/{space_id}").json()["code"] == 30004
    assert client.get(f"/api/v1/spaces/{space_id}/docs").json()["code"] == 30004
    assert client.get("/api/v1/spaces").json()["data"]["items"] == []


def test_space_docs_status_mapping() -> None:
    """GET /spaces/{id}/docs：status 三值映射 pending|ready|failed + items 键精确。

    v0.6 契约演进（T1.5.7/T3.2）：items 增量 category；data 增量 total/limit/offset。"""
    client, _ = _stub_client(_seed_service())
    space_id = client.get("/api/v1/spaces").json()["data"]["items"][0]["id"]
    docs_resp = client.get(f"/api/v1/spaces/{space_id}/docs").json()["data"]
    assert docs_resp["total"] == len(docs_resp["items"])
    items = docs_resp["items"]
    assert [d["status"] for d in items] == ["pending", "ready", "failed"]
    for item in items:
        assert set(item.keys()) == {"id", "title", "source", "status", "updatedAt", "category"}


def test_space_docs_category_filter_and_uncategorized_sentinel() -> None:
    """R0.1.1：`?category=` 服务端过滤 + `__uncategorized__` 哨兵（替代前端客户端过滤，F-9）。

    total 与 items 必须同谓词——否则分页下的 total 会虚高。"""
    client, _ = _stub_client(_seed_service())
    space_id = client.get("/api/v1/spaces").json()["data"]["items"][0]["id"]

    resp = client.get(f"/api/v1/spaces/{space_id}/docs", params={"category": "AI·技术"})
    data = resp.json()["data"]
    assert data["total"] == 2 and [d["id"] for d in data["items"]] == ["d1", "d3"]
    assert all(d["category"] == "AI·技术" for d in data["items"])

    # 哨兵：库里无分类标签的行（d2）；库里不存哨兵值，响应仍是空串
    data = client.get(f"/api/v1/spaces/{space_id}/docs", params={"category": "__uncategorized__"}).json()["data"]
    assert data["total"] == 1 and data["items"][0]["id"] == "d2"
    assert data["items"][0]["category"] == ""

    # 分页 + 过滤：total 是过滤后的数，不是全量 3
    data = client.get(
        f"/api/v1/spaces/{space_id}/docs", params={"category": "AI·技术", "limit": 1, "offset": 0}
    ).json()["data"]
    assert len(data["items"]) == 1 and data["total"] == 2

    # 未登记的取值：读路径不设校验闸门，合法地返回空列表
    data = client.get(f"/api/v1/spaces/{space_id}/docs", params={"category": "随手写的标签"}).json()["data"]
    assert data["total"] == 0 and data["items"] == []

    # 不传参数：向后兼容全量
    data = client.get(f"/api/v1/spaces/{space_id}/docs").json()["data"]
    assert data["total"] == 3


def test_space_docs_category_filter_isolation() -> None:
    """R0.1.1：过滤参数不改变鉴权语义——他人空间仍 30004。"""
    client, viewer = _stub_client(_seed_service("user-1"))
    space_id = client.get("/api/v1/spaces").json()["data"]["items"][0]["id"]
    viewer["id"] = "user-2"
    resp = client.get(f"/api/v1/spaces/{space_id}/docs", params={"category": "AI·技术"})
    assert resp.status_code == 404 and resp.json()["code"] == 30004


def test_space_docs_categories_lists_existing_only() -> None:
    """R0.1.2：docs:categories 只返回本空间实际存在的分类（声明序 + 哨兵置末）。

    用途是前端下拉数据源——分页后不能再按当前页数据推导，否则漏掉不在本页的分类。"""
    client, viewer = _stub_client(_seed_service("user-1"))
    space_id = client.get("/api/v1/spaces").json()["data"]["items"][0]["id"]

    data = client.get(f"/api/v1/spaces/{space_id}/docs:categories").json()["data"]
    assert data == {"items": ["AI·技术", "__uncategorized__"]}, "去重 + 声明序 + 未分类置末"

    # 返回项可直接回传 ?category=（与 docs 列表查询入参口径对称）
    assert (
        client.get(f"/api/v1/spaces/{space_id}/docs", params={"category": "__uncategorized__"}).json()["data"]["total"]
        == 1
    )

    # 鉴权语义不变
    viewer["id"] = "user-2"
    resp = client.get(f"/api/v1/spaces/{space_id}/docs:categories")
    assert resp.status_code == 404 and resp.json()["code"] == 30004


def test_post_space_creates_and_conflict_maps_30006() -> None:
    """POST /spaces：201 详情形状；重名 → 30006/409（Service 层 IntegrityError 映射）。"""
    repo = InMemorySpaceRepo()
    client, _ = _stub_client(SpaceService(repo))
    first = client.post("/api/v1/spaces", json={"name": "新空间"})
    assert first.status_code == 201
    assert set(first.json()["data"].keys()) == {
        "id",
        "name",
        "description",
        "docCount",
        "createdAt",
        "updatedAt",
        "stats",
        "engine",
        "engineKbId",
        "isPublic",  # AB-P004 P4 空间视图增量
    }
    # 标记重名（模拟唯一约束已存在行）
    repo._conflict_names.add(("user-1", "新空间"))
    conflict = client.post("/api/v1/spaces", json={"name": "新空间"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == 30006
    assert conflict.json()["message"] == "空间名称已存在"


# ------------------------------------------------------------------ R0.5.2（F-4）：简介落库


def test_post_space_persists_description() -> None:
    """POST /spaces 的 description 必须落库并回读（F-4 回归锁）。

    旧缺陷：CreateSpaceRequest 声明了 description，Service 只取 name，
    值被静默丢弃且读路径硬编码 ""，前端消费恒为空。
    """
    repo = InMemorySpaceRepo()
    client, _ = _stub_client(SpaceService(repo))
    resp = client.post(
        "/api/v1/spaces",
        json={"name": "公众号合集", "description": "运营侧每日更新"},
    )
    assert resp.status_code == 201
    assert resp.json()["data"]["description"] == "运营侧每日更新"

    # 读路径同样不得再是硬编码空串（旧缺陷在列表与详情两处各藏了一份）
    listed = client.get("/api/v1/spaces").json()["data"]["items"][0]
    assert listed["description"] == "运营侧每日更新"

    # 未传 description → 空串（「未填写简介」，合法状态而非丢失）
    second = client.post("/api/v1/spaces", json={"name": "无简介空间"})
    assert second.status_code == 201
    assert second.json()["data"]["description"] == ""


def test_patch_space_description_updates_and_clears() -> None:
    """PATCH /spaces/{id}：写简介 → 列表与详情同步；传 "" 清空；缺省字段即不改。"""
    repo = InMemorySpaceRepo()
    client, _ = _stub_client(SpaceService(repo))
    space_id = client.post("/api/v1/spaces", json={"name": "P空间"}).json()["data"]["id"]

    ok = client.patch(f"/api/v1/spaces/{space_id}", json={"description": "新简介"})
    assert ok.status_code == 200
    assert ok.json()["data"]["description"] == "新简介"
    # 写端点与列表读路径同口径，否则用户会看到「保存成功但列表还是空」
    listed = client.get("/api/v1/spaces").json()["data"]["items"]
    assert [i["description"] for i in listed].count("新简介") == 1

    # 部分更新语义：body 不含 description 时不得误清空
    noop = client.patch(f"/api/v1/spaces/{space_id}", json={})
    assert noop.status_code == 200
    assert noop.json()["data"]["description"] == "新简介"

    # 显式清空
    cleared = client.patch(f"/api/v1/spaces/{space_id}", json={"description": ""})
    assert cleared.status_code == 200
    assert cleared.json()["data"]["description"] == ""


def test_patch_space_description_validation_10005() -> None:
    """简介超长/含控制字符 → 10005，且先校验后取行：非法值不得写库。"""
    repo = InMemorySpaceRepo()
    client, _ = _stub_client(SpaceService(repo))
    space_id = client.post("/api/v1/spaces", json={"name": "校验空间", "description": "原简介"}).json()["data"]["id"]

    for bad in ("x" * 513, "含控制字符\x02"):
        resp = client.patch(f"/api/v1/spaces/{space_id}", json={"description": bad})
        assert resp.status_code == 422 and resp.json()["code"] == 10005
    # 两次拒绝均无副作用
    assert client.get(f"/api/v1/spaces/{space_id}").json()["data"]["description"] == "原简介"


def test_patch_space_isolation_30004() -> None:
    """他人空间 → 30004/404（不泄露存在性），且目标行不被写入。"""
    repo = InMemorySpaceRepo()
    space_id = repo.seed("user-1", "他人空间", description="原简介")
    client, _ = _stub_client(SpaceService(repo), user_id="user-2")

    resp = client.patch(f"/api/v1/spaces/{space_id}", json={"description": "越权写入"})
    assert resp.status_code == 404 and resp.json()["code"] == 30004

    # 拒绝后无副作用：直接读仓库行确认未被写入
    assert repo._spaces[space_id].description == "原简介"


def test_spaces_require_login_10001() -> None:
    """登录保护：无 cookie / 伪造 cookie → 10001 信封（不 override 鉴权依赖）。"""
    app = create_app()
    app.dependency_overrides[get_space_service] = lambda: SpaceService(InMemorySpaceRepo())
    client = TestClient(app)
    anonymous = client.get("/api/v1/spaces")
    assert anonymous.status_code == 401
    assert anonymous.json()["code"] == 10001
    client.cookies.set("bothot_session", "forged-sid")
    forged = client.get("/api/v1/spaces")
    assert forged.status_code == 401
    assert forged.json()["code"] == 10001


# ------------------------------------------------------------------ 连库轮（真实 PG:5433）


async def test_space_views_against_real_pg(db_session) -> None:
    """连库：docCount/stats 为真实 count 查询；docs join asset/source + 三值映射。"""

    from app.models.entities import ContentAsset, KnowledgeDocument, Source, User

    user = User(sub="sub-bt4r", email="bt4r@test.local", nickname="B-T4R")
    db_session.add(user)
    await db_session.flush()
    source = Source(type="wechat_oa", external_id="bizBT4R", name="契约测试号")
    db_session.add(source)
    await db_session.flush()
    repo = SpaceRepository(db_session)
    space = await repo.create(user.id, "连库契约空间")

    statuses = ["FETCHED", "READY", "FAILED"]
    # 显式给每条 doc 不同 created_at：`created_at` 默认 server_default=now()，而 PG 的 now()
    # 是**事务时刻**，同事务内三条完全相同 → 排序未定序，断言会随库内行数漂移（实测已复现：
    # 引入 T2.6 批量用例后返回序变为 failed/pending/ready）。显式时刻使本用例确定性自持。
    for i, st in enumerate(statuses, 1):
        asset = ContentAsset(
            source_id=source.id,
            external_id=f"art-{i}",
            url=f"u{i}",
            title=f"连库文章{i}",
            content_hash=f"h{i}",
            content_markdown="# m",
        )
        db_session.add(asset)
        await db_session.flush()
        doc = KnowledgeDocument(
            asset_id=asset.id,
            space_id=space.id,
            status=st,
            created_at=datetime(2026, 9, 20, 10, i, 0, tzinfo=UTC),
        )
        db_session.add(doc)
    await db_session.flush()

    svc = SpaceService(repo)
    items, items_total = await svc.list_space_views(user.id)
    assert items_total == 1
    assert items[0]["docCount"] == 3 and items[0]["name"] == "连库契约空间"

    view = await svc.get_space_view(user.id, space.id)
    assert view["stats"]["docs"] == 3

    docs, docs_total = await svc.list_space_docs(user.id, space.id)
    assert docs_total == 3, "T1.5.7：total 独立于分页窗口"
    assert [d["status"] for d in docs] == ["pending", "ready", "failed"]
    assert docs[0]["source"] == "契约测试号" and docs[0]["title"] == "连库文章1"


async def test_space_name_conflict_real_constraint_maps_30006(db_session) -> None:
    """连库：真 uq_space_user_name 约束 → Service 映射 30006（非内存桩模拟）。"""
    from app.models.entities import User

    user = User(sub="sub-bt4r-c", email="c@test.local", nickname="C")
    db_session.add(user)
    await db_session.flush()
    svc = SpaceService(SpaceRepository(db_session))
    await svc.create_space(user.id, "重名空间")
    from app.core.errors import SpaceNameConflictError

    with pytest.raises(SpaceNameConflictError) as exc_info:
        await svc.create_space(user.id, "重名空间")
    assert exc_info.value.code == 30006
    assert exc_info.value.message == "空间名称已存在"


async def test_space_isolation_against_real_pg(db_session) -> None:
    """连库：他人空间 → 30004（不泄露存在性）。"""
    from app.models.entities import User

    u1 = User(sub="sub-bt4r-1", email="1@test.local", nickname="一")
    u2 = User(sub="sub-bt4r-2", email="2@test.local", nickname="二")
    db_session.add_all([u1, u2])
    await db_session.flush()
    repo = SpaceRepository(db_session)
    space = await repo.create(u1.id, "一号的空间")
    svc = SpaceService(repo)
    from app.core.errors import ResourceNotFoundError

    with pytest.raises(ResourceNotFoundError) as exc_info:
        await svc.get_space_view(u2.id, space.id)
    assert exc_info.value.code == 30004


# ------------------------------------------------------------------ AB-T11 DELETE /spaces/{id}


class FakeKbClient:
    """LangBotClient 删除面桩：记录 delete_kb 调用，可注入失败。"""

    def __init__(self, fail: Exception | None = None) -> None:
        self.deleted: list[str] = []
        self._fail = fail

    async def delete_kb(self, kb_uuid: str) -> None:
        if self._fail is not None:
            raise self._fail
        self.deleted.append(kb_uuid)


def _delete_stub_app(user_id: str = "user-1") -> tuple[TestClient, InMemorySpaceRepo, FakeKbClient]:
    repo = InMemorySpaceRepo()
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_space_service] = lambda: SpaceService(repo)
    kb = FakeKbClient()
    app.dependency_overrides[get_langbot_client] = lambda: kb  # type: ignore[arg-type]
    return TestClient(app), repo, kb


def test_delete_space_requires_login_10001() -> None:
    """登录保护：未登录 DELETE → 10001 信封（不 override 鉴权依赖）。"""
    app = create_app()
    client = TestClient(app)
    resp = client.delete("/api/v1/spaces/any-space")
    assert resp.status_code == 401
    assert resp.json()["code"] == 10001


def test_delete_space_not_found_30004() -> None:
    """无效 id / 他人空间 → DELETE 30004/404（不泄露存在性；LangBot 不被触碰）。"""
    client, repo, kb = _delete_stub_app("user-1")
    other = repo.seed("user-9", "别人的空间", kb_uuid="kb-x")
    resp = client.delete("/api/v1/spaces/nope")
    assert resp.status_code == 404 and resp.json()["code"] == 30004
    resp2 = client.delete(f"/api/v1/spaces/{other}")
    assert resp2.status_code == 404 and resp2.json()["code"] == 30004
    assert kb.deleted == []


def test_delete_space_success_calls_langbot_and_returns_ok() -> None:
    """成功删除：先调 LangBot delete_kb（复用真客户端同款方法），再删 PG 行 → {ok:true}。"""
    client, repo, kb = _delete_stub_app("user-1")
    space_id = repo.seed("user-1", "待删空间", kb_uuid="kb-to-delete")
    resp = client.delete(f"/api/v1/spaces/{space_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0 and body["data"] == {"ok": True, "engineResidue": False}
    assert kb.deleted == ["kb-to-delete"]  # LangBot 删库被调用
    assert space_id not in repo._spaces


def test_delete_space_without_kb_skips_langbot() -> None:
    """空间从未建库（langbot_kb_uuid 空）→ 不调 LangBot，直接删 PG → {ok:true}。"""
    client, repo, kb = _delete_stub_app("user-1")
    space_id = repo.seed("user-1", "无库空间")
    resp = client.delete(f"/api/v1/spaces/{space_id}")
    assert resp.status_code == 200 and resp.json()["data"] == {"ok": True, "engineResidue": False}
    assert kb.deleted == [] and space_id not in repo._spaces


def test_delete_space_langbot_failure_returns_envelope() -> None:
    """LangBot 删库失败 → 错误信封（30002/502），空间行保留（未走到 PG 删除）。"""
    repo = InMemorySpaceRepo()
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    app.dependency_overrides[get_space_service] = lambda: SpaceService(repo)
    failing = FakeKbClient(fail=LangbotApiError("LangBot 删除失败: 500"))
    app.dependency_overrides[get_langbot_client] = lambda: failing  # type: ignore[arg-type]
    client = TestClient(app)
    space_id = repo.seed("user-1", "删不掉的空间", kb_uuid="kb-stuck")
    resp = client.delete(f"/api/v1/spaces/{space_id}")
    assert resp.status_code == 502 and resp.json()["code"] == 30002
    assert failing.deleted == [] and space_id in repo._spaces  # 删除未发生


# ------------------------------------------------------------------ AB-T11 连库轮（真实 PG:5433）


async def test_delete_space_real_pg_success_and_langbot_called(db_session) -> None:
    """连库成功删除：LangBot 桩被调用 + docs/assets/space 行真实消失（savepoint 内提交可见）。"""
    from app.models.entities import ContentAsset, KnowledgeDocument, Source, User

    user = User(sub="sub-abt11-ok", email="abt11ok@test.local", nickname="AB-T11")
    db_session.add(user)
    await db_session.flush()
    source = Source(type="wechat_oa", external_id="bizABT11", name="删除测试号")
    db_session.add(source)
    await db_session.flush()
    repo = SpaceRepository(db_session)
    space = await repo.create(user.id, "AB-T11删除空间", langbot_kb_uuid="kb-abt11")
    asset = ContentAsset(
        source_id=source.id,
        external_id="abt11-art",
        url="u",
        title="删我",
        content_hash="habt11",
        content_markdown="# m",
    )
    db_session.add(asset)
    await db_session.flush()
    db_session.add(KnowledgeDocument(asset_id=asset.id, space_id=space.id, status="READY"))
    await db_session.commit()  # 夹具 savepoint 模式：commit 只释放保存点，外层回滚清场

    kb = FakeKbClient()
    counts = await SpaceService(repo, db_session).delete_space(user.id, space.id, kb)
    assert kb.deleted == ["kb-abt11"]
    assert counts == {"docs": 1, "assets": 1, "spaces": 1, "engineResidue": False}
    from app.models.entities import KnowledgeSpace as KS

    assert await db_session.get(KS, space.id) is None
    assert await db_session.get(ContentAsset, asset.id) is None


async def test_delete_space_real_pg_langbot_failure_rolls_back(db_session) -> None:
    """连库整体回滚（LangBot 失败路径的真实事务观测）。

    实现顺序：delete_kb 先抛 → PG 删除根本不执行 → rollback 撤销请求内一切
    未提交改动。本用例在**无 commit**（get_db 生产模式）下种行，delete_space
    失败后断言三张表行全部还在；补一层 rollback 语义覆盖。
    """
    from app.models.entities import ContentAsset, KnowledgeDocument, KnowledgeSpace, Source, User

    user = User(sub="sub-abt11-rb", email="abt11rb@test.local", nickname="回滚")
    db_session.add(user)
    await db_session.flush()
    source = Source(type="wechat_oa", external_id="bizABT11RB", name="回滚测试号")
    db_session.add(source)
    await db_session.flush()
    repo = SpaceRepository(db_session)
    space = await repo.create(user.id, "回滚空间", langbot_kb_uuid="kb-rb")
    asset = ContentAsset(
        source_id=source.id,
        external_id="rb-art",
        url="u",
        title="留下",
        content_hash="hrb",
        content_markdown="# m",
    )
    db_session.add(asset)
    await db_session.flush()
    doc = KnowledgeDocument(asset_id=asset.id, space_id=space.id, status="READY")
    db_session.add(doc)
    await db_session.commit()

    space_id, asset_id, doc_id = space.id, asset.id, doc.id  # rollback 会过期 ORM 实例，先存 id
    kb = FakeKbClient(fail=DependencyUnavailableError("LangBot 不可达"))
    svc = SpaceService(repo, db_session)
    with pytest.raises(DependencyUnavailableError):
        await svc.delete_space(user.id, space_id, kb)
    assert kb.deleted == []
    # 整体回滚观测：delete_kb 先抛 → PG 删除不执行 → 已提交的三表行仍在
    assert await db_session.get(KnowledgeSpace, space_id) is not None
    assert await db_session.get(ContentAsset, asset_id) is not None
    assert await db_session.get(KnowledgeDocument, doc_id) is not None


async def test_delete_space_pending_delete_rolled_back_by_get_db_semantics(db_session) -> None:
    """回滚兜底：级联删除已 flush 但未 commit 时，session.rollback() 使三表行复现。

    对真实 PG 复现「删除执行 → 提交前失败 → 整体回滚」的撤销面（与 get_db
    请求末回滚同机制），并验证 get_by_id 读到空壳行时不误抛，返回 30004。
    """
    from app.models.entities import ContentAsset, KnowledgeDocument, KnowledgeSpace, Source, User

    user = User(sub="sub-abt11-fl", email="abt11fl@test.local", nickname="撤销")
    db_session.add(user)
    await db_session.flush()
    source = Source(type="wechat_oa", external_id="bizABT11FL", name="撤销测试号")
    db_session.add(source)
    await db_session.flush()
    repo = SpaceRepository(db_session)
    space = await repo.create(user.id, "撤销空间", langbot_kb_uuid="kb-fl")
    asset = ContentAsset(
        source_id=source.id,
        external_id="fl-art",
        url="u",
        title="先删后撤",
        content_hash="hfl",
        content_markdown="# m",
    )
    db_session.add(asset)
    await db_session.flush()
    doc = KnowledgeDocument(asset_id=asset.id, space_id=space.id, status="READY")
    db_session.add(doc)
    await db_session.commit()

    space_id, asset_id, doc_id = space.id, asset.id, doc.id  # rollback 过期实例，先存 id
    # 级联删除（flush 未提交）→ 三表行消失
    counts = await repo.delete_space_cascade(space_id)
    assert counts == {"docs": 1, "assets": 1, "spaces": 1}
    assert await db_session.get(KnowledgeSpace, space_id) is None
    # 未 commit 前 rollback → 全部复现（证明 commit 是删除生效的唯一闸口）
    await db_session.rollback()
    assert await db_session.get(KnowledgeSpace, space_id) is not None
    assert await db_session.get(ContentAsset, asset_id) is not None
    assert await db_session.get(KnowledgeDocument, doc_id) is not None


async def test_delete_space_detached_instance_maps_30004(db_session) -> None:
    """防御面：get_by_id 返回空壳行（行已删，session.get 语义）→ 30004 而非 500。"""
    from app.models.entities import User

    user = User(sub="sub-abt11-dt", email="abt11dt@test.local", nickname="空壳")
    db_session.add(user)
    await db_session.flush()
    repo = SpaceRepository(db_session)
    space = await repo.create(user.id, "空壳空间")
    space_id = space.id
    await repo.delete_space_cascade(space_id)  # 已 flush 删除（未 commit）
    svc = SpaceService(repo, db_session)
    from app.core.errors import ResourceNotFoundError

    with pytest.raises(ResourceNotFoundError) as exc_info:
        await svc.delete_space(user.id, space_id, FakeKbClient())
    assert exc_info.value.code == 30004  # 空壳 user_id==""≠user.id → 30004（不泄露/不 500）
