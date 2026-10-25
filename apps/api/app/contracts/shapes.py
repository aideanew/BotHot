"""其余 mock 域的**线上响应形状**契约（STEP-47，P-82 第二刀，D-V21-08）——唯一源是这里。

STEP-46 只切了引擎域两条；本模块把前端 mock 表（`apps/web/lib/api/mock-routes.ts`）里
其余 20 条路由的信封 `data` 都写成模型。schema 与 TS 都从这里派生，真端点由
`tests/test_shapes_response_contract.py` 反向核（`additionalProperties: false`：多一个键也红）。

写法纪律（与 engine.py 同）：
- 只描述**后端现在真吐的东西**，不按"理想形状"改写；觉得形状不合理就登记 P 号，不顺手改路由。
- 依赖方向：不 import `app.providers` / `app.services` / `app.api`。
- 键名保持已发布面原样：camelCase 的照抄 camelCase，通知域历史上是 snake_case 也照抄。

本模块里唯一 `extra="allow"` 的是 `MeWallet`：正常分支它是**主平台钱包对象原样透传**
（`wallet.get("wallet", wallet)`），本仓不控制它的键集合。这一处如实写成开放对象，并登记 P-121
（建议后端白名单投影后再收紧），而不是假装它是封闭的。
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import Divergence

_Count = Annotated[int, Field(ge=0)]
_Limit = Annotated[int, Field(ge=1)]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── identity ────────────────────────────────────────────────────────────────


class MeUser(_Closed):
    """`GET /auth/me` → `data.user`。`role` 是主平台 userinfo 原值（大写枚举），门禁看 `is_admin`。"""

    sub: str
    email: str
    nickname: str
    tier: str
    role: str
    is_admin: bool


class MeWallet(BaseModel):
    """`GET /auth/me` → `data.wallet`。降级/fixture 分支恒为 {balanceYuan:0, currency, available:false}。"""

    model_config = ConfigDict(extra="allow")

    balanceYuan: str | float  # noqa: N815
    currency: str
    heldYuan: str | float = 0  # noqa: N815 —— 主平台可不给；默认值仅为让键可选，不代表后端会补 0
    availableYuan: str | float = 0  # noqa: N815
    available: bool = True


class MeView(_Closed):
    """`GET /auth/me` 的信封 `data`。三个分支同一形状：正常 / 主平台不可达降级 / QA fixture。

    降级分支多带 `providerUnreachable: true`，fixture 分支再多带 `qaFixture: true`；
    正常分支两个键都不出现——所以它们是可选键，不是联合形。
    """

    user: MeUser
    wallet: MeWallet
    providerUnreachable: bool = False  # noqa: N815
    qaFixture: bool = False  # noqa: N815


class LogoutResult(_Closed):
    """`POST /auth/logout` 的信封 `data`（幂等：无会话也是这一形）。"""

    logged_out: bool


# ── notifications ───────────────────────────────────────────────────────────


class NotificationItem(_Closed):
    """通知历史条目（与 SSE 通知帧同键，snake_case 为已发布面）。"""

    id: str
    is_broadcast: bool
    title: str
    message: str
    url: str | None
    space_id: str | None
    doc_id: str | None
    read_at: str | None
    created_at: str | None


class NotificationHistoryPage(_Closed):
    """`GET /system/notifications/history` 的信封 `data`（limit/offset 分页 + 未读数）。"""

    items: list[NotificationItem]
    total: _Count
    limit: _Limit
    offset: _Count
    unread_total: _Count


class NotificationReadResult(_Closed):
    """`PUT /system/notifications/read` 的信封 `data`。"""

    updated: _Count


# ── spaces ──────────────────────────────────────────────────────────────────


class SpaceView(_Closed):
    """`GET /spaces` 的 `items[]`（本人列表不带 owner 三键；那三键只在 /admin 面出现）。"""

    id: str
    name: str
    description: str
    docCount: _Count  # noqa: N815
    updatedAt: str  # noqa: N815
    engine: str
    engineKbId: str  # noqa: N815
    isPublic: bool  # noqa: N815


class SpacePage(_Closed):
    """`GET /spaces` 的信封 `data`。"""

    items: list[SpaceView]
    total: _Count
    limit: _Limit
    offset: _Count


class SpaceStats(_Closed):
    """`chunks` 为 null 表示"数据源未接线"，不是 0（R0.5.3）。"""

    docs: _Count
    chunks: Annotated[int, Field(ge=0)] | None


class SpaceDetail(_Closed):
    """`GET/PATCH /spaces/{id}` 与 `POST /spaces`（201）的信封 `data`——三处同一形状。"""

    id: str
    name: str
    description: str
    docCount: _Count  # noqa: N815
    createdAt: str  # noqa: N815
    updatedAt: str  # noqa: N815
    stats: SpaceStats
    engine: str
    engineKbId: str  # noqa: N815
    isPublic: bool  # noqa: N815


class SpaceDeleteResult(_Closed):
    """`DELETE /spaces/{id}` 的信封 `data`。"""

    ok: bool
    engineResidue: bool  # noqa: N815


class PublicSpaceView(_Closed):
    """`GET /spaces/public` 的 `items[]`。"""

    id: str
    name: str
    description: str
    docCount: _Count  # noqa: N815
    engine: str
    isPublic: bool  # noqa: N815
    updatedAt: str  # noqa: N815


class PublicSpacePage(_Closed):
    """`GET /spaces/public` 的信封 `data`。"""

    items: list[PublicSpaceView]
    total: _Count
    limit: _Limit
    offset: _Count


class LinkResult(_Closed):
    """`POST /spaces/{id}/links` 的信封 `data`（幂等 copy）。"""

    copied: _Count
    skipped: _Count
    total: _Count


# ── docs ────────────────────────────────────────────────────────────────────


class SpaceDocStatus(str, Enum):
    """文档列表里的展示态（本地 FETCHED/INDEXED → pending，READY → ready，FAILED → failed）。"""

    pending = "pending"
    ready = "ready"
    failed = "failed"


class SpaceDocItem(_Closed):
    """`GET /spaces/{id}/docs` 的 `items[]`。"""

    id: str
    title: str
    source: str
    status: SpaceDocStatus
    updatedAt: str  # noqa: N815
    category: str


class SpaceDocPage(_Closed):
    """`GET /spaces/{id}/docs` 的信封 `data`。"""

    items: list[SpaceDocItem]
    total: _Count
    limit: _Limit
    offset: _Count


class DocCategoryList(_Closed):
    """`GET /spaces/{id}/docs:categories` 的信封 `data`（未分类哨兵 `__uncategorized__` 置末）。"""

    items: list[str]


class DocDeleteResult(_Closed):
    """`DELETE /spaces/{id}/docs/{docId}` 的信封 `data`。"""

    ok: bool
    docId: str  # noqa: N815
    docs: _Count
    assets: _Count


class DocCategoryPatch(_Closed):
    """`PATCH /spaces/{id}/docs/{docId}` 的信封 `data`（空串入参回显为默认分类）。"""

    docId: str  # noqa: N815
    category: str


class BatchDocFailure(_Closed):
    """批量删除的篇级失败明细。"""

    docId: str  # noqa: N815
    code: int
    error: str


class DocsBatchDeleteResult(_Closed):
    """`POST /spaces/{id}/docs:delete` 的信封 `data`（failed 非空即部分成功）。"""

    ok: bool
    requested: _Count
    docs: _Count
    assets: _Count
    failed: list[BatchDocFailure]


class DocsRecategorizeResult(_Closed):
    """`POST /spaces/{id}/docs:recategorize` 的信封 `data`（整批原子）。"""

    ok: bool
    requested: _Count
    docs: _Count
    category: str


class DocIngestStatus(str, Enum):
    """入库链路的本地状态（FAILED 不出现在 200 里：走 30003 错误信封）。"""

    FETCHED = "FETCHED"
    INDEXED = "INDEXED"
    READY = "READY"


class IngestAccepted(_Closed):
    """`POST /spaces/{id}/docs`（202）的信封 `data`。`taskId` 恒空串（SPEC §3.1 形状稳定位）。"""

    docId: str  # noqa: N815
    title: str
    status: DocIngestStatus
    langbotFileId: str  # noqa: N815
    taskId: str  # noqa: N815
    hitCache: bool  # noqa: N815
    hitCount: _Count  # noqa: N815


class DocIngestState(_Closed):
    """`GET /spaces/{id}/docs/{docId}/status` 的信封 `data`。"""

    docId: str  # noqa: N815
    status: DocIngestStatus
    langbotFileId: str  # noqa: N815


# ── resolve / extract ───────────────────────────────────────────────────────


class ResolvedArticleView(_Closed):
    """`POST /resolve` 的信封 `data`（解析预览；不落库）。"""

    title: str
    author: str
    publishTime: str  # noqa: N815
    content: str
    url: str
    biz: str


class ExtractedImageView(_Closed):
    """抽取结果里的图片（内部 fmt 字段不进视图）。"""

    src: str
    caption: str


class ExtractedArticleView(_Closed):
    """`POST /extract` 的信封 `data`：清洗产物 + 质量评分三键（未过阈值走 20003，不出现在 200 里）。"""

    title: str
    author: str
    publishTime: str  # noqa: N815
    paragraphs: list[str]
    images: list[ExtractedImageView]
    wordCount: _Count  # noqa: N815
    langbotFormat: str  # noqa: N815
    qualityScore: Annotated[int, Field(ge=0, le=100)]  # noqa: N815
    qualityPassed: bool  # noqa: N815
    qualityReasons: list[str]  # noqa: N815


#: 前端 mock 路由 → 契约名（S47.4 机器表的后端一侧；STEP-52 在前端照这张表逐条 satisfies）。
#: 键是 "METHOD 路径模板"，与 `apps/web/lib/api/mock-routes.ts` 的 22 条 pattern 一一对应。
MOCK_ROUTE_CONTRACTS: dict[str, str] = {
    "GET /api/v1/engines": "EngineList",
    "PATCH /api/v1/spaces/{id}/engine": "SpaceEngineBinding",
    "GET /api/v1/auth/me": "MeView",
    "POST /api/v1/auth/logout": "LogoutResult",
    "GET /api/v1/spaces/public": "PublicSpacePage",
    "POST /api/v1/spaces/{id}/links": "LinkResult",
    "POST /api/v1/resolve": "ResolvedArticleView",
    "POST /api/v1/extract": "ExtractedArticleView",
    "POST /api/v1/spaces/{id}/docs": "IngestAccepted",
    "GET /api/v1/spaces/{id}/docs/{docId}/status": "DocIngestState",
    "GET /api/v1/system/notifications/history": "NotificationHistoryPage",
    "PUT /api/v1/system/notifications/read": "NotificationReadResult",
    "POST /api/v1/spaces": "SpaceDetail",
    "GET /api/v1/spaces": "SpacePage",
    "GET /api/v1/spaces/{id}/docs": "SpaceDocPage",
    "GET /api/v1/spaces/{id}/docs:categories": "DocCategoryList",
    "DELETE /api/v1/spaces/{id}/docs/{docId}": "DocDeleteResult",
    "PATCH /api/v1/spaces/{id}/docs/{docId}": "DocCategoryPatch",
    "POST /api/v1/spaces/{id}/docs:delete": "DocsBatchDeleteResult",
    "POST /api/v1/spaces/{id}/docs:recategorize": "DocsRecategorizeResult",
    "GET /api/v1/spaces/{id}": "SpaceDetail",
    "DELETE /api/v1/spaces/{id}": "SpaceDeleteResult",
}


#: 稿与本模块的已知差异（语义判定见 tests/test_contract_jsonschema.py）。与 engine 域同四条。
CONTRACT_DIVERGENCES: tuple[Divergence, ...] = (
    Divergence(
        ref="*（所有 def）",
        field="required",
        kind="structural",
        rule="required-order",
        draft="required 由作者手写顺序",
        model="生成物按模型字段顺序，比对时排序后比集合",
        reason="required 是集合，顺序无语义；登记是为了让「我们排序了」这件事有人负责。",
    ),
    Divergence(
        ref="*（文档根）",
        field="x-generated-by, x-source-module",
        kind="documentation",
        rule="generated-provenance-keys",
        draft="稿里没有这两个键",
        model="生成物根层带这两个溯源键",
        reason="产物必须自证是谁生成的。消费者：`test_artifact_provenance_keys_are_declared`（逐域验）。",
    ),
    Divergence(
        ref="*（本域全部 def 与属性）",
        field="description",
        kind="documentation",
        rule="strip-description",
        draft="稿里不写 def 级说明",
        model="模型 docstring 会在 def 上生成 description",
        reason="文本不参与相等判定；单向断言「稿里有 ⇒ 产物也得有」由 `_description_losses` 承担。",
    ),
    Divergence(
        ref="*（本域所有可空字段）",
        field="*",
        kind="structural",
        rule="nullable-form",
        draft='可空字段写成 "anyOf": [ …, {"type": "null"}]',
        model='同样是 "anyOf": [ …, {"type": "null"}]',
        reason="比对器对可空写法统一在事实层合流（types/nullable 两个事实位），归一被用到就要有人认领。",
    ),
)
