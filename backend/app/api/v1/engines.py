"""AB-P004 P4 引擎可插拔路由：GET /engines + PATCH /spaces/{id}/engine。

- GET /api/v1/engines（登录保护）→ 5 引擎位 + Key 可用性 + 生效来源：
  data.items=[{engine, configured, available, allowlisted, keyEnv, activeSource,
               decryptFailed, description}]
  builtin 恒 available；main/coze/dify/fastgpt 按「登记表 > env」解析 Key，
  activeSource 显式回报 env | registered | null（登记覆盖 env 不静默）。
- PATCH /api/v1/spaces/{id}/engine {engine} → 校验 allowlist + Key 可用性：
  未配 Key 切非 builtin → 403（10004 语义）提示找管理员；成功 200 {engine, engineKbId}；
  双写 engine_kb_id（builtin 时与 langbot_kb_uuid 同步）。
越权/无效空间 → 30004。

「有凭据/无凭据」只有一个谓词：core.engine_keyring.resolve_engine_key。
本模块的 GET 上报与 PATCH 前置校验、engine_port 的路由判定全部走它——
T5.4 前这里曾有一份与 EngineRouter 结论相反的 main 判定（只查 base 不查 key）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db
from app.core.config import Settings, get_settings
from app.core.engine_keyring import resolve_engine_key, set_snapshot
from app.core.errors import ForbiddenError, RequestInvalidError, ResourceNotFoundError
from app.core.response import success
from app.providers.engine_port import ENGINE_IMPLEMENTED, ENGINE_ORDER
from app.repositories.space import SpaceRepository
from app.services.engine_keys import EngineKeyService

engines_router = APIRouter(prefix="/api/v1", tags=["engines"])
space_engine_router = APIRouter(prefix="/api/v1/spaces", tags=["engines"])


class PatchEngineRequest(BaseModel):
    engine: str = Field(min_length=1, max_length=32)


def _engine_allowlist(settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    return [x.strip() for x in str(settings.kb_engine_allowlist).split(",")]


_DESCRIPTIONS: dict[str, str] = {
    "builtin": "内置引擎（LangBot 系，默认）",
    "main": "主平台知识库（RAGFlow 拓展系）",
    "coze": "Coze 知识库 API（SaaS）",
    "dify": "Dify Cloud Knowledge API（SaaS）",
    "fastgpt": "FastGPT Cloud Dataset API（SaaS）",
}


def _engine_status(
    engine: str,
    settings: Settings | None = None,
    registered: Mapping[str, str] | None = None,
    decrypt_bad: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """引擎位状态——configured 判定委托单一谓词 resolve_engine_key。

    registered：登记表已解密明文（异步读库所得）；decrypt_bad：解密失败行。
    状态上报直接读库、不走进程内快照，故不同步陈旧。
    """
    settings = settings or get_settings()
    res = resolve_engine_key(engine, settings, registered)
    allowlist = _engine_allowlist(settings)
    return {
        "engine": engine,
        "configured": res.configured,
        # R1 修复：available 三条件同口径（configured + allowlisted + implemented），与 EngineRouter 一致
        "available": _engine_available(engine, res.configured, allowlist),
        "allowlisted": engine in allowlist,
        "implemented": ENGINE_IMPLEMENTED.get(engine, False),
        "keyEnv": res.env_var,
        # T5.4：生效来源显式回报——登记覆盖 env 必须可见，「存了但没生效」是最差失败形态
        "activeSource": res.source,
        "decryptFailed": bool(decrypt_bad and engine in decrypt_bad),
        "description": _DESCRIPTIONS.get(engine, engine),
    }


def _engine_available(engine: str, configured: bool, allowlist: list[str]) -> bool:
    """三条件可用谓词（configured ∧ allowlisted ∧ implemented）——GET /engines 与
    PATCH 前置校验的共同口径（kb.ingest_url 的 EngineRouter.available 同义）。

    builtin 恒 True：它是回退通道。若随 allowlist 判定，管理员误配 allowlist（不含
    builtin）会让 GET 报 builtin 不可用而 PATCH 仍允许切入——同一份数据两个谓词。
    """
    if engine == "builtin":
        return True
    return configured and engine in allowlist and ENGINE_IMPLEMENTED.get(engine, False)


def assert_engine_switchable(
    engine: str,
    settings: Settings | None = None,
    registered: Mapping[str, str] | None = None,
) -> None:
    """引擎切换前置校验——与消费侧（kb.ingest_url 的 available 三条件）同口径。

    builtin 恒可通过：它是回退通道，漏掉会让空间被切到不可用引擎后无法恢复。
    其余四类拒绝按最具体原因分层（顺序不可换，否则原因提示失真）：
      未知引擎位 10005 / 未开放 10004 / 未配 Key 10004 / 已配 Key 但未实接 10004。
    """
    if engine not in ENGINE_ORDER:
        raise RequestInvalidError(f"未知引擎位: {engine}（可选 {ENGINE_ORDER}）")
    if engine == "builtin":
        return
    st = _engine_status(engine, settings, registered)
    if not st["allowlisted"]:
        raise ForbiddenError(
            f"引擎 {engine} 未开放（allowlist={_engine_allowlist(settings)}），请联系管理员"
        )
    if not st["configured"]:
        raise ForbiddenError(
            f"引擎 {engine} 未配置 API Key（登记表或 env: {st['keyEnv']}），请联系管理员登记"
        )
    if not ENGINE_IMPLEMENTED.get(engine, False):
        raise ForbiddenError(f"引擎 {engine} 尚未实接（仅骨架实现），暂不可切换")


@engines_router.get("/engines")
async def list_engines(
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """GET /engines：5 引擎位 + Key 可用性 + 生效来源（builtin 恒 available）。

    登记表直接读库（不经进程内快照，故不同步陈旧）；顺带把快照刷到最新，
    让 sync 的 EngineRouter/make_engine 在重启后也能看到已登记 Key。
    """
    svc = EngineKeyService(session)
    loaded = await svc.load()
    set_snapshot(loaded.plaintext)
    items = [_engine_status(e, None, loaded.plaintext, loaded.decrypt_bad) for e in ENGINE_ORDER]
    body = success(data={"items": items, "defaultEngine": get_settings().kb_default_engine})
    return JSONResponse(status_code=200, content=body.model_dump())


@space_engine_router.patch("/{space_id}/engine")
async def patch_space_engine(
    space_id: str,
    payload: PatchEngineRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """PATCH /spaces/{id}/engine：切换空间引擎（双写 engine/engine_kb_id）。

    校验谓词与消费侧（kb.ingest_url 前置检查）同口径——三条件 available
    （configured ∧ allowlisted ∧ ENGINE_IMPLEMENTED）。此前仅查 allowlist + configured，
    漏查 ENGINE_IMPLEMENTED，导致空间可被切到未实接的骨架引擎：此后 ingest 全 403，
    且 delete_space 走 adapter 分支抛 NotImplementedError 整体回滚 → 空间无法删除。
    builtin 恒可切回（回退通道，防空间被切到不可用引擎后锁死）。

    - 未知引擎位 → 10005；不在 allowlist → 10004（提示找管理员）；
    - 非 builtin 未配 Key（登记表与 env 皆空）→ 10004；已配 Key 但未实接 → 10004（骨架位）；
    - builtin 切换：engine=builtin，engine_kb_id 与 langbot_kb_uuid 双写同步；
    - 非 builtin 切换：engine_kb_id 暂空（实接后回填），旧文档不动（ADR-0004 §三③）。
    """
    # 登记表与 GET /engines 同源读取：登记的 Key 同样可让引擎位可切换，避免两份判定
    _loaded = await EngineKeyService(session).load()
    assert_engine_switchable(payload.engine, None, _loaded.plaintext)

    repo = SpaceRepository(session)
    space = await repo.get_by_id(space_id)
    if space is None or space.user_id != user_id:
        raise ResourceNotFoundError(space_id)

    space.engine = payload.engine
    if payload.engine == "builtin":
        # 双写：builtin 引擎 kb id 与 langbot_kb_uuid 同源
        space.engine_kb_id = space.langbot_kb_uuid
    else:
        # 非 builtin：engine_kb_id 保留既有映射（无则空串，实接后回填）
        space.engine_kb_id = space.engine_kb_id or ""
    await session.commit()
    body = success(
        data={"engine": space.engine, "engineKbId": space.engine_kb_id, "spaceId": space.id}
    )
    return JSONResponse(status_code=200, content=body.model_dump())
