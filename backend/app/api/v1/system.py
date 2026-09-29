"""系统路由：健康检查与公开配置。"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.response import success

router = APIRouter(prefix="/api/v1/system", tags=["system"])


async def _check_pg() -> str:
    try:
        from app.db import get_engine
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return "ok"
    except Exception:
        return "unreachable"


async def _check_redis() -> str:
    try:
        import redis.asyncio as aioredis
        settings = get_settings()
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        return "ok"
    except Exception:
        return "unreachable"


async def _check_langbot() -> str:
    """LangBot 2.x **没有** `/api/health`，而 `/health` 是前端 SPA 的 catch-all
    ——API 层挂了它照样返 200（返回 index.html），拿它当探针会把真故障判成健康。

    改探测一个真实存在的路由 `/api/v1/knowledge/engines`：未登录时它回 LangBot 的
    JSON 错误信封（证明 API 路由在应答），未知路径才落到 SPA 兜底返 HTML。
    判据取「响应是 LangBot 的信封」而非单看状态码——两者都成立才算活，
    避免 LangBot 调整状态码时探针静默失效。
    """
    try:
        import httpx

        settings = get_settings()
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(
                f"{settings.langbot_base_url}/api/v1/knowledge/engines"
            )
        if resp.status_code != 401:
            return "unhealthy"
        try:
            body = resp.json()
        except ValueError:
            return "unhealthy"
        return "ok" if isinstance(body, dict) and "code" in body else "unhealthy"
    except Exception:
        return "unreachable"


@router.get("/health")
async def health() -> object:
    """R6.1.5：功能探活——依赖活性逐项暴露（存活仍 200，降级面可见）。

    deps 中各项：ok / unreachable / unhealthy；
    任一非 ok 说明功能降级（如 Redis 不可达→会话回退 memory，LangBot 不可达→检索/入库不可用）。
    """
    settings = get_settings()
    pg = await _check_pg()
    redis = await _check_redis()
    langbot = await _check_langbot()
    deps = {"postgres": pg, "redis": redis, "langbot": langbot}
    all_ok = all(v == "ok" for v in deps.values())
    return success(data={
        "status": "ok" if all_ok else "degraded",
        "app": settings.app_name,
        "env": settings.app_env,
        "deps": deps,
    })
