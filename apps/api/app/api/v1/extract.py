"""正文提取路由（B-T6）：POST /api/v1/extract（登录保护，纯计算无事务）。

内部链路：resolve（B-T5）→ extract（本卡）；响应形状 v0.3e 备案中（A 复核）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_id
from app.core.errors import ExtractQualityLowError
from app.core.response import success
from app.providers.source_resolver import WechatArticleFetcher
from app.services.extractor import ExtractorService
from app.services.normalizer import normalize_extracted
from app.services.quality import score_quality
from app.services.resolver import SourceResolverService

router = APIRouter(prefix="/api/v1", tags=["extract"])

_resolver: SourceResolverService | None = None
_extractor = ExtractorService()


def get_resolver_service_internal() -> SourceResolverService:
    """extract 内部消费的 resolver（独立于 B-T5 路由依赖，避免跨域耦合）。"""
    global _resolver
    if _resolver is None:
        _resolver = SourceResolverService(WechatArticleFetcher())
    return _resolver


class ExtractRequest(BaseModel):
    url: str = Field(min_length=1, max_length=512, description="公众号文章 URL（长链或裸短链）")


@router.post("/extract")
async def extract(
    payload: ExtractRequest,
    _user_id: Annotated[str, Depends(get_current_user_id)],
    svc: Annotated[SourceResolverService, Depends(get_resolver_service_internal)],
) -> JSONResponse:
    """URL → resolve → extract → normalize → score → ExtractedContent。

    B-T7 接线：归一化 → 质量评分；passed=False → 20003（阈值 QUALITY_PASS_THRESHOLD=30）。
    响应 data 追加 qualityScore/qualityPassed/qualityReasons（v0.3f 备案中）。
    """
    article = await svc.resolve(payload.url)
    extracted = _extractor.extract(article)
    extracted = normalize_extracted(extracted)
    verdict = score_quality(extracted)
    if not verdict.passed:
        raise ExtractQualityLowError(f"质量评分不足: {'; '.join(verdict.reasons)}")
    data = {**extracted.to_view(), **verdict.to_view()}
    body = success(data=data)
    return JSONResponse(status_code=200, content=body.model_dump())
