"""AB-P004 P5 引导页路由：GET /api/v1/onboarding/steps。

R6.6.8（F-25）裁定：删桩。原端点返回硬编码 step=1/progress=0/completedSteps=[]，
但 docstring 称"跨会话/跨机器的快照同步入口"且无对应写入端点——误导性可用位。
真实进度以前端 localStorage 为准，后端无持久化支撑此端点。
返回 410 Gone + 说明，避免已接线前端静默降级。
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.response import failure

router = APIRouter(prefix="/api/v1", tags=["onboarding"])


@router.get("/onboarding/steps")
async def get_onboarding_steps() -> JSONResponse:
    """R6.6.8：桩已删除——410 Gone。

    真实进度以前端 localStorage（STORAGE_KEY="bothot_onboarding_v1"）为准，
    后端无写入端点与持久化支撑，本端点已裁为误导性可用位。
    """
    body = failure(10005, "本端点已下线（R6.6.8），真实进度请以前端 localStorage 为准")
    return JSONResponse(status_code=410, content=body.model_dump())
