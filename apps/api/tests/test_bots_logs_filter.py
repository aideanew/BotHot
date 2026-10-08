"""R3.1（S2.7 缩水版）推送日志 status 过滤测试。

分页（page/page_size/total）在 W 期已实现且有覆盖，本文件只补 status 过滤分支：
- 不过滤（None）→ 全量
- 合法 status（success/failed/dead）→ 精确过滤
- 非法 status → RequestInvalidError（白名单，非静默空结果）
- 渠道不存在 → ResourceNotFoundError

直调路由函数（Depends 默认值仅 HTTP 路径生效），db_session 外层事务回滚隔离
—— 同 test_notification_history.py 口径。PushLog 为纯数据行（无 FK 依赖），直插即可。
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.bots import list_push_logs
from app.core.errors import RequestInvalidError, ResourceNotFoundError
from app.models.bothot_entities import BotChannel, PushLog


async def _seed_channel(db: AsyncSession) -> BotChannel:
    ch = BotChannel(
        name="logs-filter-channel",
        channel_type="webhook",
        webhook_url="http://localhost:9999/test",
        secret_enc="",
        extra_config="{}",
        status="active",
    )
    db.add(ch)
    await db.flush()
    return ch


async def _seed_log(db: AsyncSession, ch: BotChannel, status: str, preview: str) -> PushLog:
    log = PushLog(
        bot_channel_id=ch.id,
        push_task_id=None,
        status=status,
        content_preview=preview,
        error_message="",
        response_summary="",
    )
    db.add(log)
    await db.flush()
    return log


async def test_logs_no_filter_returns_all(db_session: AsyncSession):
    ch = await _seed_channel(db_session)
    for i, st in enumerate(["success", "failed", "dead"]):
        await _seed_log(db_session, ch, st, f"row-{i}")

    result = await list_push_logs(ch.id, page=1, page_size=20, status=None, db=db_session)
    assert result.data["total"] == 3
    assert len(result.data["items"]) == 3


async def test_logs_filter_by_status(db_session: AsyncSession):
    ch = await _seed_channel(db_session)
    await _seed_log(db_session, ch, "success", "ok-row")
    await _seed_log(db_session, ch, "failed", "bad-row")
    await _seed_log(db_session, ch, "failed", "bad-row-2")

    result = await list_push_logs(ch.id, page=1, page_size=20, status="failed", db=db_session)
    assert result.data["total"] == 2
    assert all(item["status"] == "failed" for item in result.data["items"])

    result_ok = await list_push_logs(ch.id, page=1, page_size=20, status="success", db=db_session)
    assert result_ok.data["total"] == 1
    assert result_ok.data["items"][0]["content_preview"] == "ok-row"


async def test_logs_filter_dead_status(db_session: AsyncSession):
    ch = await _seed_channel(db_session)
    await _seed_log(db_session, ch, "dead", "dead-row")

    result = await list_push_logs(ch.id, page=1, page_size=20, status="dead", db=db_session)
    assert result.data["total"] == 1
    assert result.data["items"][0]["status"] == "dead"


async def test_logs_filter_invalid_status_rejected(db_session: AsyncSession):
    ch = await _seed_channel(db_session)
    with pytest.raises(RequestInvalidError):
        await list_push_logs(ch.id, page=1, page_size=20, status="bogus", db=db_session)


async def test_logs_channel_not_found(db_session: AsyncSession):
    with pytest.raises(ResourceNotFoundError):
        await list_push_logs("no-such-channel", page=1, page_size=20, status=None, db=db_session)
