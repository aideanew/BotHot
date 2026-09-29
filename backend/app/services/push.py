"""SPEC-M3 批次 5 / T6.2：推送触发服务。

把「按 space/doc 推送给某通道目标」的校验与分发收敛到一处。本批为诚实占位
（2026-09-23 管理者裁定）：**校验全部落地**（通道合法、内容合法、目标存在），
**投递不实接**（provider 返回 delivered=False，路由转 50002 依赖不可用）。

授权不在本层——路由层 require_roles("operator")（A-2 叠加口径：operator 以上
可代用户操作，故不做归属校验，与 SpaceService.update_doc_category 同纪律）。

校验顺序固定为 通道 → 内容 → 目标，全部在分发前完成：**任何一步失败都无副作用**
（不落行、不刷新快照），避免「半成功推送」。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import RequestInvalidError, ResourceNotFoundError
from app.models.entities import KnowledgeDocument, KnowledgeSpace
from app.providers.push_port import PushMessage, PushResult, make_push_provider

# 正文长度上限：推送是给人读的短消息，不是文档。
MAX_MESSAGE_CHARS = 2000
MAX_TARGET_CHARS = 128
MAX_REF_CHARS = 36

_CONTROL_MSG = "控制字符"


def _assert_no_control(text: str, field: str) -> None:
    if text and any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        raise RequestInvalidError(f"{field} 含{_CONTROL_MSG}")


class PushService:
    """推送校验 + 分发。只读目标、不写任何行。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def push(
        self,
        channel: str,
        external_user_id: str,
        space_id: str = "",
        doc_id: str = "",
        message: str = "",
    ) -> PushResult:
        channel = channel.strip()
        external_user_id = external_user_id.strip()
        space_id = space_id.strip()
        doc_id = doc_id.strip()
        message = message.strip()

        self._assert_channel(channel)
        self._assert_content(external_user_id, space_id, doc_id, message)
        await self._assert_targets(space_id, doc_id)

        provider = make_push_provider(channel)
        return await provider.push(
            PushMessage(external_user_id=external_user_id, space_id=space_id, doc_id=doc_id, message=message)
        )

    @staticmethod
    def _assert_channel(channel: str) -> None:
        # 未知通道不臆造：转成 10005 而非 500。
        try:
            make_push_provider(channel)
        except ValueError as exc:
            raise RequestInvalidError(str(exc)) from exc

    @staticmethod
    def _assert_content(external_user_id: str, space_id: str, doc_id: str, message: str) -> None:
        if not external_user_id:
            raise RequestInvalidError("推送目标（external_user_id）不能为空")
        if len(external_user_id) > MAX_TARGET_CHARS:
            raise RequestInvalidError(f"推送目标过长（上限 {MAX_TARGET_CHARS} 字符）")
        if not (message or space_id or doc_id):
            raise RequestInvalidError("推送内容为空（message/spaceId/docId 至少一项）")
        _assert_no_control(external_user_id, "推送目标")
        _assert_no_control(message, "推送正文")
        if len(message) > MAX_MESSAGE_CHARS:
            raise RequestInvalidError(f"推送正文过长（上限 {MAX_MESSAGE_CHARS} 字符）")

    async def _assert_targets(self, space_id: str, doc_id: str) -> None:
        """引用的空间/文档必须存在，且文档属于所给空间。

        文档归属空间是数据事实校验（防跨空间误推），与「谁能操作」无关——
        不因 operator 跨用户授权而放宽（与批次 2 doc 端点同口径）。
        """
        if not space_id and not doc_id:
            return
        if len(space_id) > MAX_REF_CHARS or len(doc_id) > MAX_REF_CHARS:
            raise RequestInvalidError(f"引用 id 过长（上限 {MAX_REF_CHARS} 字符）")

        space = (
            await self._session.execute(select(KnowledgeSpace).where(KnowledgeSpace.id == space_id))
        ).scalar_one_or_none() if space_id else None
        if space_id and space is None:
            raise ResourceNotFoundError(f"推送引用的空间不存在: {space_id}")

        doc = (
            await self._session.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == doc_id))
        ).scalar_one_or_none() if doc_id else None
        if doc_id and doc is None:
            raise ResourceNotFoundError(f"推送引用的文档不存在: {doc_id}")
        if doc is not None and space is not None and doc.space_id != space.id:
            raise ResourceNotFoundError(f"推送引用的文档不属于该空间: {doc_id}")
