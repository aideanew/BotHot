"""采集域契约（STEP-01 S1.2.1）——本模块是采集域形状的唯一源。

依据：`docs/任务规划V0.12.0/contracts/collection.schema.json`（冻结稿 v1，V0.2.1 起未变）
与 ADR-0008（契约唯一源 = 后端 Python 代码，本次归位见 STEP-01 S1.1.0）。
生成面由 `scripts/gen_contracts.py` 负责（S1.3.1），语义比对见 S1.3.2，锚定测试见 S1.4.1。

依赖方向（S1.2.1.2）：本包**不 import** `app.services` / `app.providers` / `app.models`——
契约是被依赖端，反向 import 会让"改服务实现"连带改契约，唯一源就不成立了。
`ChannelName` 与 `app/providers/discovery/registry.py` 的 `CHANNELS` 键**相等**这一事实
由 `tests/test_collection_contract.py` 单向核对（测试可以同时 import 两侧，模型不行）。

与冻结稿的三处**结构性**差异（语义等价，S1.3.2 的比对脚本按此归一，且每条都有见证向量兜底）：
1. 冻结稿 `ArticleKey` 用 `oneOf` 三条 pattern；本模块合成一条带锚定 alternation
   （`b:` / `s:` / `h:` 三个前缀互斥，`^(?:A|B|C)$` 与 oneOf 的接受集相同）。
2. 冻结稿可空写成 `"type": ["string", "null"]`；Pydantic 生成 `anyOf[..., {"type":"null"}]`。
3. 冻结稿 `ChannelName` / `ManifestStatus` 是 `$defs` 条目，本模块用 `str` 枚举（仍生成 `$defs`）；
   `CollectionEvent.event` 与 `ArticleKey` 在 Pydantic 里是内联字面量/约束别名，会被就地展开。

一处**故意的收紧**：`publish_time` / `at` 用 `AwareDatetime`，而 JSON Schema 的
`format: date-time` 默认只是注记、不校验。冻结稿自己的字段说明写着"provider 内即转为带时区时间"
"时间一律 ISO 8601 带时区"，所以"能解析成带时区时间"本来就是契约意图——把它从注记升成真校验。
代价：一个返回 `"2024-01-01"`（无时区）的 provider 以前过 schema、现在被拒。这是要的效果，
不是回归，故在此写明而不是藏进 diff。

一处命名差异（卡面对象叫 `DiscoveryReport`，冻结稿里没有这个形状）：
卡面 S1.2.1 的 `DiscoveryReport` 在冻结稿对应**两个** `$defs`——`ManifestSyncReport`
（单源单轮发现报告）与 `DiscoveryChannelView`（后台渠道就绪度视图）。本模块按冻结稿命名，
不新造第三个名字。
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

# ── ArticleKey ────────────────────────────────────────────────────────────────
# 键形由 ADR-0011（D-V2-01 方案 A：带前缀，自描述来源）：
#   b:<biz>:<mid>:<idx>   微信长链（biz 为 base64 形 token，idx 缺省补 "1"）
#   s:<short_token>       短链 token
#   h:<32 hex>            不可解析 URL 的降级身份 = sha256(normalize_url(url))[:32]
# 不变量 1（"任何输入的返回值 ≠ 's'，且长度 ≥ 8"）由这三条分支共同保证：
# 每条都要求前缀段后至少 8 个字符，裸 "s" 落不进任何分支。
ARTICLE_KEY_PATTERN = (
    r"^(?:b:[A-Za-z0-9+/=_-]{8,64}:[0-9]{1,12}:[0-9]{1,2}|s:[A-Za-z0-9_-]{8,64}|h:[0-9a-f]{32})$"
)

ArticleKey = Annotated[
    str,
    StringConstraints(pattern=ARTICLE_KEY_PATTERN, min_length=3, max_length=128),
]

# ── 枚举 ──────────────────────────────────────────────────────────────────────


class ChannelName(str, Enum):
    """发现渠道名，与 `registry.CHANNELS` 的键一一对应。

    新增渠道 = **契约变更**：这里加一个成员，`CHANNELS` 也得加一个 spec，两边由
    `tests/test_collection_contract.py` 的等值断言钉住（顺序也一致，故用有序比较）。
    数据库侧渠道字段仍是 `String(32)`（AGENTS.md 关键约束 3），本枚举只约束**契约面**。
    """

    REDFOX = "redfox"
    RSS = "rss"
    DAJIALA = "dajiala"
    JUSTONEAPI = "justoneapi"
    TIKHUB = "tikhub"
    WELLBYTE = "wellbyte"


class ManifestStatus(str, Enum):
    """清单行状态机（STEP-04 实现，受 D-V2-02）。

    合法迁移只有这几条，**枚举本身不校验迁移**——迁移表由 STEP-04 的服务层与测试承担：
      DISCOVERED → ENQUEUED
      ENQUEUED   → INGESTED | FAILED | DISCOVERED（仅 stale 回退：Job 终态而行仍 ENQUEUED）
      FAILED     → DISCOVERED（仅人工/重试接口）
    其余迁移非法。
    """

    DISCOVERED = "DISCOVERED"
    ENQUEUED = "ENQUEUED"
    INGESTED = "INGESTED"
    FAILED = "FAILED"


# ── 发现清单 ──────────────────────────────────────────────────────────────────


class WorkListRow(BaseModel):
    """所有 provider `query_work_list` 的唯一输出形状。

    `extra="allow"` 是有意的（冻结稿 `additionalProperties: true`）：渠道各自的上游字段
    差异很大，契约只钉"三个必填 + 时间/正文的类型"，其余透传。透传不等于无序扩张——
    新字段要被消费就得进契约，那时改这里。
    """

    model_config = ConfigDict(extra="allow")

    id: Annotated[str, StringConstraints(min_length=1, max_length=128)] = Field(
        description="上游稳定文章 id；上游无稳定 id 时 = canonical_article_key(url)"
    )
    url: Annotated[str, StringConstraints(min_length=8, max_length=512)]
    title: Annotated[str, StringConstraints(max_length=512)]
    publish_time: AwareDatetime | None = Field(
        default=None, description="provider 内即转为带时区时间；上游无时间才允许 null"
    )
    digest: str = ""
    author: str = ""


class WorkListPage(BaseModel):
    """发现分页壳（STEP-08 协议升级后启用；STEP-03 阶段 provider 仍返回 `list[WorkListRow]`）。"""

    rows: list[WorkListRow]
    next_cursor: str | None = None
    page_size: Annotated[int, Field(ge=1)]
    total: Annotated[int | None, Field(ge=0)] = None


# ── 清单行与同步报告 ─────────────────────────────────────────────────────────


class ArticleManifest(BaseModel):
    """`article_manifests` 行的契约面（持久化形状）。

    `external_id` 与 `article_key` **不是一回事**（D-V3-01）：前者是渠道内幂等键
    （= `WorkListRow.id`，唯一约束 `(source_id, external_id)` 不变），后者是跨渠道的
    文章身份键（= `canonical_article_key(url)`，与 `content_assets.external_id` 同键空间）。
    `article_key` 列由 STEP-04 的迁移 `ab1006c1a` 引入，本契约先钉形状。
    """

    id: Annotated[str, StringConstraints(max_length=36)]
    source_id: Annotated[str, StringConstraints(max_length=36)]
    external_id: Annotated[str, StringConstraints(max_length=128)] = Field(
        description="= WorkListRow.id（渠道内幂等键）"
    )
    article_key: ArticleKey = Field(description="= canonical_article_key(url)；新列 ab1006c1a")
    url: Annotated[str, StringConstraints(max_length=512)]
    title: Annotated[str, StringConstraints(max_length=512)]
    publish_time: AwareDatetime | None = None
    content_hash: Annotated[str, StringConstraints(max_length=64)] = ""
    status: ManifestStatus


class ManifestSyncReport(BaseModel):
    """单源单轮发现报告（`ManifestSyncService.sync_source` 返回值；日志/指标/告警共用）。

    两个计数有告警语义，不是普通整数：
    `id_fallback > 0` 记 WARNING（行缺 id、以规范键兜底，STEP-03.3.4）；
    `all_skipped_pages > 0` 记 ERROR + 告警（整页全跳 = 采集静默失败的形状，STEP-05）。
    """

    channel: ChannelName
    pages: Annotated[int, Field(ge=0)]
    rows: Annotated[int, Field(ge=0)]
    new: Annotated[int, Field(ge=0)]
    updated: Annotated[int, Field(ge=0)]
    unchanged: Annotated[int, Field(ge=0)]
    skipped: Annotated[int, Field(ge=0)]
    id_fallback: Annotated[int, Field(ge=0)] = Field(
        description="行缺 id、以 canonical key 兜底的次数；>0 记 WARNING"
    )
    all_skipped_pages: Annotated[int, Field(ge=0)] = Field(
        default=0, description="skipped == rows > 0 的页数；>0 记 ERROR + 告警"
    )


# ── 后台视图与内部事件 ───────────────────────────────────────────────────────


class DiscoveryChannelView(BaseModel):
    """`GET /api/v1/admin/discovery/channels` 的 `data.channels[i]`。

    字段名是 **camelCase**（HTTP 响应体口径，实测锚 `registry.py:333-340`），
    Python 属性保持 snake_case + alias；`model_json_schema()` 默认按 alias 出属性名。
    三个布尔**刻意不合并**成一个 available：`implemented`（功能做没做）、`enabled`
    （配没配进白名单）、`available`（凭据在不在）合并后无法区分"功能没做"和"功能没配"，
    配置缺失会被伪装成渠道故障——这是 R7.6 的原话，留在这里免得后人"顺手简化"。
    """

    model_config = ConfigDict(populate_by_name=True)

    name: ChannelName
    description: str
    implemented: bool
    enabled: bool
    available: bool
    reason: str
    contract_verified_at: str | None = Field(default=None, alias="contractVerifiedAt")
    verified_scope: str | None = Field(default=None, alias="verifiedScope")
    last_success_at: AwareDatetime | None = Field(
        default=None, alias="lastSuccessAt", description="STEP-05 新增（COULD）"
    )
    last_error: str | None = Field(
        default=None, alias="lastError", description="STEP-05 新增（COULD）；不得含凭据或上游响应原文"
    )


class CollectionEvent(BaseModel):
    """采集域内部事件（结构化日志 + 指标标签）。

    不是 outbox、不跨进程——别把它当持久化事件总线用。`idempotency_key` 是 page 级
    去重键 `{source_id}:{channel}:{yyyymmdd}:{page}`，告警按它一天一次。
    """

    event: Literal[
        "discovery.page_all_skipped",
        "discovery.id_fallback",
        "discovery.failed",
        "manifest.enqueued",
        "manifest.ingested",
        "manifest.failed",
        "manifest.stale_reverted",
    ]
    source_id: str
    channel: ChannelName
    at: AwareDatetime
    idempotency_key: str = ""
    count: Annotated[int, Field(ge=0)] = 0
