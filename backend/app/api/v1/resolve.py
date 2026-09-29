"""信息源解析路由（B-T5）：POST /api/v1/resolve（登录保护）。

响应形状 {title,author,publishTime,content,url,biz} 为 B-T5 任务卡定案，
已在契约 v0.3c 登记流程内（A 复核中）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_id
from app.core.response import success
from app.providers.source_resolver import WechatArticleFetcher
from app.services.resolver import SourceResolverService

router = APIRouter(prefix="/api/v1", tags=["resolve"])

_service: SourceResolverService | None = None


def get_resolver_service() -> SourceResolverService:
    """FastAPI 依赖入口（测试经 dependency_overrides 替换）。"""
    global _service
    if _service is None:
        _service = SourceResolverService(WechatArticleFetcher())
    return _service


class ResolveRequest(BaseModel):
    url: str = Field(min_length=1, max_length=512, description="公众号文章 URL（长链或裸短链）")


@router.post("/resolve")
async def resolve(
    payload: ResolveRequest,
    _user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SourceResolverService, Depends(get_resolver_service)],
) -> JSONResponse:
    """URL → ResolvedArticle（直抓 + 锚点解析；不落库、不入 LangBot，B-T6+ 编排）。"""
    article = await svc.resolve(payload.url)
    body = success(data=article.to_view())
    return JSONResponse(status_code=200, content=body.model_dump())
