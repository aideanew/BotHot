"""STEP-14a S14a.2 / S14a.3 —— admin 分页目标壳与统一 envelope 的契约用例。

四件事各自锁一层，少锁一层就会在别的卡里被"顺手改掉"而没人报错：

- 目标壳的键（`page`/`pageSize`/`hasMore`）与旧键（`limit`/`offset`）**同时**在响应里
  ——"只增不删"是"不破旧客户端"这句话的可执行形式；
- 两壳请求参数的优先级（给了任一旧参数就整段按旧参数解释）；
- `hasMore` 的边界（"正好填满最后一页"不等于"还有下一页"，这决定前端会不会多发一次请求）；
- `admin.py` 不自己造错误响应（S14a.2.3 的防回归：扫源码，不扫行为措辞）。

另有一条是本轮真实红过之后加的：`create_app().openapi()` 必须能构建——
分页依赖改成闭包工厂时，注解里的运行期值会变成 pydantic 重建不了的 `ForwardRef`，
报错点不在本模块而在 OpenAPI 生成，只有走到那条路径才看得见（先红读数见 EVD-V13-14a §5）。
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import jsonschema
from fastapi.testclient import TestClient

from app.api.deps import get_current_sub, get_current_user_id, get_db
from app.api.v1 import admin as admin_module
from app.main import create_app
from app.models.entities import KnowledgeSpace, User
from app.schemas.pagination import PageParams, make_page_query, page_query

ADMIN_SPACES = "/api/v1/admin/spaces"
SHELL_KEYS = {"items", "total", "limit", "offset", "page", "pageSize", "hasMore"}
ENVELOPE_SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "contracts"
    / "schemas"
    / "api.envelope.schema.json"
)


async def _seed_spaces(db_session: Any, count: int) -> str:
    """一个 admin 账号 + `count` 个自有空间（清单顺序按 updatedAt 倒序，条数才是判据）。"""
    admin = User(sub="14a-admin", email="14a-admin@14a.test", nickname="14a-admin", role="admin")
    db_session.add(admin)
    await db_session.flush()
    for i in range(count):
        db_session.add(
            KnowledgeSpace(user_id=admin.id, name=f"14A 空间{i}", langbot_kb_uuid=f"kb-14a-{i}")
        )
    await db_session.flush()
    return str(admin.id)


def _client(db_session: Any, actor_id: str) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: actor_id
    app.dependency_overrides[get_current_sub] = lambda: "14a-sub"
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _data(client: TestClient, query: str) -> dict[str, Any]:
    resp = client.get(f"{ADMIN_SPACES}{query}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    jsonschema.validate(body, json.loads(ENVELOPE_SCHEMA.read_text(encoding="utf-8")))
    payload: dict[str, Any] = body["data"]
    return payload


# ------------------------------------------------------------------ 响应形状


async def test_response_carries_target_shell_and_legacy_keys_together(db_session: Any) -> None:
    """目标壳与旧键同时在场：这是"只增不删"的可核对形式，不是注释里的一句承诺。"""
    actor = await _seed_spaces(db_session, 3)
    data = _data(_client(db_session, actor), "")
    assert SHELL_KEYS <= set(data), f"缺键：{SHELL_KEYS - set(data)}"
    assert data["total"] == 3 and len(data["items"]) == 3
    assert (data["page"], data["pageSize"], data["limit"], data["offset"]) == (1, 50, 50, 0)
    assert data["hasMore"] is False, "3 条全在一页里，hasMore 必须是 False"


async def test_has_more_is_false_on_an_exactly_filled_last_page(db_session: Any) -> None:
    """边界：3 条 / pageSize=2 → 第 1 页还有下一页，第 2 页正好填满 ⇒ 没有。"""
    actor = await _seed_spaces(db_session, 3)
    client = _client(db_session, actor)

    first = _data(client, "?pageSize=2&page=1")
    assert len(first["items"]) == 2 and first["hasMore"] is True
    assert (first["offset"], first["limit"]) == (0, 2), "旧键必须由新参数换算出来，不能缺"

    second = _data(client, "?pageSize=2&page=2")
    assert len(second["items"]) == 1 and second["hasMore"] is False
    assert second["page"] == 2 and second["offset"] == 2


async def test_legacy_params_still_position_the_page_unchanged(db_session: Any) -> None:
    """旧客户端一行不改也能跑：`limit`/`offset` 继续是有效定位方式。"""
    actor = await _seed_spaces(db_session, 3)
    data = _data(_client(db_session, actor), "?limit=1&offset=2")
    assert len(data["items"]) == 1 and data["total"] == 3
    assert data["hasMore"] is False and data["page"] == 3 and data["pageSize"] == 1


async def test_docs_endpoint_keeps_its_own_wider_page_size_cap(db_session: Any) -> None:
    """上限逐端点声明：`/spaces/{id}/docs` 的历史上限是 200，收敛时不能被收成 100。"""
    actor = await _seed_spaces(db_session, 1)
    client = _client(db_session, actor)
    space_id = client.get(ADMIN_SPACES).json()["data"]["items"][0]["id"]
    resp = client.get(f"/api/v1/admin/spaces/{space_id}/docs?limit=200")
    assert resp.status_code == 200, f"上限被收紧就会 422：{resp.text}"
    data = resp.json()["data"]
    assert SHELL_KEYS <= set(data) and data["pageSize"] == 200


# ------------------------------------------------------------------ 参数优先级（纯函数，不连库）


async def test_page_query_precedence_and_defaults() -> None:
    assert await page_query(limit=None, offset=None, page=None, page_size=None) == PageParams(50, 0)
    assert await page_query(limit=None, offset=None, page=3, page_size=10) == PageParams(10, 20)
    # 给了任一旧参数 ⇒ 整段按旧参数解释（新参数不参与，避免拼出第三种位置）
    assert await page_query(limit=7, offset=3, page=2, page_size=5) == PageParams(7, 3)
    assert await page_query(limit=None, offset=40, page=2, page_size=5) == PageParams(50, 40)
    # 逐端点声明的边界：docs 的默认与上限都比别处大
    docs_query = make_page_query(default_size=100, max_size=200)
    assert await docs_query(limit=None, offset=None, page=None, page_size=None) == PageParams(100, 0)


# ------------------------------------------------------------------ P-18：重试接回清单四态


async def test_retry_reopens_the_failed_manifest(db_session: Any) -> None:
    """P-18：retry 必须同事务把清单行从 `FAILED` 拉回 `DISCOVERED`（合法边）。

    不拉回的后果不是数据损坏，是**读数失真**：条目重跑成功后 worker 要跨
    `FAILED → INGESTED`，迁移表没这条边 ⇒ `_apply_manifest_status` 拦下并告警，
    于是"篇已入库、清单仍显示失败"。这条用例锁的是可观测事实，不是日志措辞。
    """
    from app.models.entities import ArticleManifest, Job, JobItem, Source, User
    from app.services.subscription import SourceSubscriptionService

    owner = User(sub="14a-owner", email="14a-owner@14a.test", nickname="owner")
    db_session.add(owner)
    await db_session.flush()
    src = Source(type="wechat_oa", external_id="biz-14a-p18", name="14A P-18 测试号", url="https://x/biz")
    db_session.add(src)
    await db_session.flush()
    manifest = ArticleManifest(source_id=src.id, external_id="w-14a-p18", url="https://x/14a-p18")
    manifest.status = "FAILED"
    db_session.add(manifest)
    await db_session.flush()
    job = Job(type="ingest_url", user_id=owner.id, idempotency_key="ingest:14a-p18")
    job.status = "FAILED"
    db_session.add(job)
    await db_session.flush()
    item = JobItem(
        job_id=job.id, external_id="w-14a-p18", url="https://x/14a-p18", manifest_id=manifest.id
    )
    item.status = "FAILED"
    db_session.add(item)
    await db_session.flush()

    out = await SourceSubscriptionService(db_session).retry_job_any(str(job.id))

    assert out["retried"] == 1 and out["status"] == "QUEUED"
    await db_session.refresh(manifest)
    assert manifest.status == "DISCOVERED", "清单行没被拉回 ⇒ 重跑成功后 worker 撞非法边，读数失真"


# ------------------------------------------------------------------ S14a.2.3 与 OpenAPI 两条防回归


def test_admin_module_never_fabricates_error_responses() -> None:
    """错误一律走 errors.global 码表：admin.py 里不许出现自造的非 200 响应。"""
    src = inspect.getsource(admin_module)
    offenders = [
        line.strip()
        for line in src.splitlines()
        if "status_code=" in line and "status_code=200" not in line
    ]
    assert offenders == [], f"admin.py 出现自造状态码响应：{offenders}"


def test_openapi_builds_and_documents_both_paging_dialects() -> None:
    """闭包依赖的注解必须能被 pydantic 重建（本轮真实红过的一条），且两壳参数都在稿上。"""
    spec = create_app().openapi()
    params = {
        p["name"] for p in spec["paths"]["/api/v1/admin/spaces"]["get"]["parameters"]
    }
    assert {"limit", "offset", "page", "pageSize"} <= params, params
