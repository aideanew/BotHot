"""STEP-46（V0.21.0，D-V21-01，解 P-82）：引擎域的**线上响应形状**进契约，并由真端点反向核。

P-82 的病根：契约包只有持久层实体镜像，前端 mock 表与 `lib/api/*` 的线上类型只能各写一份，
"后端改了序列化、前端照旧"没有任何机器会响。这里补的是链条的后端那一半——
`app/contracts/engine.py` 的 `EngineList` / `SpaceEngineBinding` 是唯一源，schema 与 TS 都从它派生，
本文件证明**真端点吐出的 data** 与它逐键一致（`additionalProperties: false`：多一个键也红）。

连库用例沿用全套件 `db_session` 夹具（Windows/无 DSN 下按既有口径 skip）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from app.api.deps import get_current_user_id, get_db
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((REPO_ROOT / "packages" / "contracts" / "schemas" / "engine.schema.json").read_text("utf-8"))
_LIST = Draft202012Validator({**SCHEMA, "$ref": "#/$defs/EngineList"})
_BINDING = Draft202012Validator({**SCHEMA, "$ref": "#/$defs/SpaceEngineBinding"})
TS_DTO = REPO_ROOT / "packages" / "contracts" / "src" / "engine" / "dto.ts"


def _client(user_id: str, db_session: Any) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _errors(validator: Draft202012Validator, data: Any) -> list[str]:
    return [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(data)]


# ── 不连库：契约本身有牙齿 ──────────────────────────────────────────────────────


def test_list_contract_rejects_extra_and_missing_keys() -> None:
    good = {"items": [], "defaultEngine": "builtin"}
    assert not _errors(_LIST, good)
    assert _errors(_LIST, {**good, "extra": 1}), "多键必须红（additionalProperties:false）"
    assert _errors(_LIST, {"items": []}), "缺 defaultEngine 必须红"


def test_binding_contract_rejects_null_kb_id() -> None:
    """engine_kb_id 是 NOT NULL DEFAULT ''：契约写成 null 会让前端多处理一种不存在的态。"""
    assert not _errors(_BINDING, {"engine": "coze", "engineKbId": "", "spaceId": "s"})
    assert _errors(_BINDING, {"engine": "coze", "engineKbId": None, "spaceId": "s"})


def test_ts_dto_is_derived_from_the_same_schema() -> None:
    """TS 产物逐个 def 都在（字节幂等由 gen_contracts --check 管，这里只防"漏导出某个 def"）。"""
    src = TS_DTO.read_text("utf-8")
    for name in SCHEMA["$defs"]:
        assert f" {name} " in src, f"{name} 未出现在 engine/dto.ts"
    assert "unknown" not in src, "响应形状降级成 unknown ⇒ satisfies 失去牙齿"


# ── 连库：真端点吐出的 data 与契约逐键一致 ─────────────────────────────────────────


async def test_get_engines_data_matches_engine_list(db_session) -> None:  # type: ignore[no-untyped-def]
    resp = _client("user-1", db_session).get("/api/v1/engines")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert not _errors(_LIST, data), _errors(_LIST, data)


async def test_patch_engine_data_matches_binding(db_session) -> None:  # type: ignore[no-untyped-def]
    from app.models.entities import KnowledgeSpace
    from app.repositories.user import SqlAlchemyUserStore

    user = await SqlAlchemyUserStore(db_session).upsert_by_sub("sub-s46", "s46@test.local", "S46")
    space = KnowledgeSpace(user_id=user.id, name="S46 契约空间", langbot_kb_uuid="lb-kb-s46")
    db_session.add(space)
    await db_session.flush()

    resp = _client(user.id, db_session).patch(f"/api/v1/spaces/{space.id}/engine", json={"engine": "builtin"})
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert not _errors(_BINDING, data), _errors(_BINDING, data)
    assert data == {"engine": "builtin", "engineKbId": "lb-kb-s46", "spaceId": space.id}
