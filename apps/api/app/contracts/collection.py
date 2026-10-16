"""采集域契约（STEP-01 S1.2.1）——本模块是采集域形状的唯一源。

依据：`docs/任务规划V0.12.0/contracts/collection.schema.json`（冻结稿 v1，V0.2.1 起未变）
与 ADR-0008（契约唯一源 = 后端 Python 代码，本次归位见 STEP-01 S1.1.0）。
生成面由 `scripts/gen_contracts.py` 负责（S1.3.1），语义比对见 S1.3.2，锚定测试见 S1.4.1。

依赖方向（S1.2.1.2）：本包**不 import** `app.services` / `app.providers` / `app.models`——
契约是被依赖端，反向 import 会让"改服务实现"连带改契约，唯一源就不成立了。
`ChannelName` 与 `app/providers/discovery/registry.py` 的 `CHANNELS` 键**相等**这一事实
由 `tests/test_collection_contract.py` 单向核对（测试可以同时 import 两侧，模型不行）。

与冻结稿的差异**不在本 docstring 里维护**，而在文件末尾的 `CONTRACT_DIVERGENCES`
（机器可读；S1.3.2 的比对脚本按它放行，表里没有的差异 = 比对必须红）。五类：
`structural` 等价写法、`tightening` 模型比 JSON Schema 严（故意的）、
`serialization` 接受集相同但 dump 形状不同、`strictness` 多余字段丢弃 vs 透传、
`documentation` 只动人读文本（description / x-* 注释）不动校验。
第一轮独立验证正是拿"docstring 的叙述清单不全"判我 FAIL 的——叙述会漏项，登记表少一项就红。

一处命名差异（卡面对象叫 `DiscoveryReport`，冻结稿里没有这个形状）：
卡面 S1.2.1 的 `DiscoveryReport` 在冻结稿对应**两个** `$defs`——`ManifestSyncReport`
（单源单轮发现报告）与 `DiscoveryChannelView`（后台渠道就绪度视图）。本模块按冻结稿命名，
不新造第三个名字。
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from . import Divergence

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
    StringConstraints(pattern=ARTICLE_KEY_PATTERN, min_length=8, max_length=128),  # D-V8-02：两稿取更严者

]

# ── 枚举 ──────────────────────────────────────────────────────────────────────


class ChannelName(str, Enum):
    """发现渠道名，与 `registry.CHANNELS` 的键一一对应。

    新增渠道 = **契约变更**：这里加一个成员，`CHANNELS` 也得加一个 spec，两边由
    `tests/test_collection_contract.py` 钉住。比较口径（第一轮验证者指出我原来"按顺序比较"
    是错的耦合）：**与 `CHANNELS` 比集合**——dict 的插入序是实现细节，不该被契约依赖；
    **顺序只与冻结稿比**（`collection.schema.json` 的 enum 数组），那才是合同。
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
    url: Annotated[
        str,
        StringConstraints(min_length=8, max_length=512),
        # 冻结稿声明 `format: uri`（draft 2020-12 里默认只是注记、不assert）。
        # 这里显式把它带进生成物，而不是"登记一条差异然后放过"—— 形状对齐、校验强度不变，
        # 少一条需要比对脚本记住的例外（第二轮验证正是抓到这条没人登记才暴露的）。
        Field(json_schema_extra={"format": "uri"}),
    ]
    title: Annotated[str, StringConstraints(max_length=512)]
    publish_time: AwareDatetime | None = Field(
        default=None, description="provider 内即转为带时区时间；上游无时间才允许 null"
    )
    digest: str = ""
    author: str = ""


class WorkListPage(BaseModel):
    """发现分页壳（STEP-08 协议升级后启用；STEP-03 阶段 provider 仍返回 `list[WorkListRow]`）。

    `next_cursor` 是**必填可空**（冻结稿 `required: [rows, next_cursor, page_size]`）：
    "到底了"要显式写 `null`，不能靠缺字段表达——缺字段与"末页"在两方协议里是不同事实，
    混用会让上层把"provider 忘了给游标"读成"已经没有下一页"。
    """

    rows: list[WorkListRow]
    next_cursor: str | None
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
    idempotency_key: str = Field(
        default="",
        description="page 级去重键 {source_id}:{channel}:{yyyymmdd}:{page}；告警按此键一天一次",
    )
    count: Annotated[int, Field(ge=0)] = 0


# ── 与冻结稿的差异登记表（S1.3.2 的比对脚本消费它）────────────────────────────


CONTRACT_DIVERGENCES: tuple[Divergence, ...] = (
    Divergence(
        "ArticleKey",
        "article_key（所有引用处）",
        "structural",
        "pattern-equivalence",
        "是 9 个 $defs 之一，`oneOf` 三条带锚 pattern",
        "生成物 $defs 只有 8 个；引用处内联成**一条**带锚 alternation",
        "等价性由**文本推导**证明而不是靠语料：比对器把稿的三支去掉 ^/$ 后拼成 "
        "`^(?:A|B|C)$`，与生成物的 pattern **逐字符相等**才算过。第三轮验证证明"
        "只用 11 条见证语料会漏掉 `{32}`→`{31,32}`、字符类去掉 `-`、`{1,12}`→`{1,13}` 等 4 类改动"
        "——量词和字符类是 regex 的语义，不是有限样本能覆盖的。",
    ),
    Divergence(
        "ArticleKey",
        "minLength/maxLength",
        "structural",
        "bounds-redundant",
        "minLength 3 / maxLength 128",
        "同样声明 3 / 128，但对 pattern 而言是冗余约束",
        "最短可通过串是 `s:12345678`（10 字符）、最长分支 ≤ 82 ⇒ 两条边界永远先不到。"
        "由 `test_article_key_bounds_are_redundant` 断言「三支分支各自能过的极值都在 3/128 之内」。",
    ),
    Divergence(
        "ArticleManifest",
        "properties.article_key.minLength",
        "tightening",
        "article-key-min-length-unified",
        "`minLength: 3`",
        "`minLength: 8`（与 resources 稿对齐后的唯一源取值）",
        "两稿对同一个键写了不同的冗余下界（3 vs 8），而唯一源只能有一个别名 ⇒ 台账行 **D-V8-02** 取更严者。"
        "取 8 不排任何合法键：三支分支各自最短可过串是 `s:`+8=10、`b:…:1:1` 支 14、`h:`+32 支 34，全部 >8，"
        "所以这一档收紧对接受集是**恒等变换**——由 `test_article_key_bounds_are_redundant` 算给看，"
        "不是嘴上说一句「反正冗余」。",
    ),
    Divergence(
        "ArticleKey",
        "minLength, maxLength, oneOf",
        "structural",
        "alias-inlining",
        "是 $defs 条目，被 `$ref: #/$defs/ArticleKey` 引用",
        "生成物 $defs 里没有它：约束内联到使用处（`ArticleManifest.properties.article_key` 三件套齐全）",
        "Pydantic 不为类型别名建 $defs，只为 BaseModel/Enum 建 ⇒ 这是生成器的固定行为，不是漏项。"
        "第六轮验证之后这条必须**自己存在**而不是蹭 `pattern-equivalence` 那一条：比对器用到哪个归一，"
        "就要有一条同名登记认领它（否则任何一条 documentation 登记都能替归一发通行证）。"
        "内联是否真的发生，由逐 def 比对在使用处验：`test_article_key_pattern_text_is_derivable_from_draft`。",
    ),
    Divergence(
        "ArticleKey",
        "oneOf",
        "structural",
        "oneOf-to-pattern-set",
        "三条带锚的 pattern 分支写在 `oneOf` 里",
        "折成一条带锚 alternation `^(?:A|B|C)$`",
        "折叠本身是归一，必须被同名条目认领（第六轮之后 `test_normalizations_used_are_all_backed_by_registry`"
        "按 rule 名核对，蹭别的条目不给通行证）。等价性由文本推导证明而不是语料抽样，"
        "见 `pattern-equivalence` 与 `test_article_key_pattern_text_is_derivable_from_draft`。",
    ),
    Divergence(
        "*（所有 def）",
        "required",
        "structural",
        "required-order",
        "required 是作者手写的顺序",
        "生成物按模型字段顺序，比对时排序后比集合",
        "JSON Schema 里 required 是集合，顺序无语义；但**归一必须被登记**，"
        "否则「排序再比」就是无人负责的宽松化。消费者：比对器的 _note_rule 记账 + 本条存在性核对。",
    ),
    Divergence(
        "*（文档根）",
        "x-generated-by, x-source-module",
        "documentation",
        "generated-provenance-keys",
        "稿里没有这两个键",
        "生成物根层带这两个溯源键",
        "产物必须能回答「是谁生成的、源模块是谁」，否则有人手改产物时无从判断。"
        "比对器允许它存在，但**必须**有本条登记（见 compare_defs 里的 generated-provenance-keys 检查）。",
    ),
    Divergence(
        "*（所有可空字段）",
        "*",
        "structural",
        "nullable-form",
        '"type": ["string", "null"]',
        '"anyOf": […, {"type": "null"}]',
        "Pydantic 生成器的固定写法，语义相同；比对脚本按此归一。",
    ),
    Divergence(
        "*（所有模型与所有属性）",
        "title",
        "documentation",
        "strip-title",
        "只有 3 个 def 有 title",
        "每个模型/属性都带 title（类名、字段名派生）",
        "关不掉：`ConfigDict(field_title_generator=…)` 返回 None 实测抛 "
        "`TypeError: must return str` ⇒ 比对脚本剥离 title 后比。",
    ),
    Divergence(
        "*（所有模型与所有属性）",
        "description",
        "documentation",
        "strip-description",
        "只有 3 个 def 带 description",
        "每个模型都带（类 docstring），每个带说明的字段都带（Field description）",
        "文本不同不构成契约差异：描述是人读面。比对脚本剥离 description 文本，"
        "但保留一条断言：**稿里某个 def/字段有 description ⇒ 生成物对应位置也得有**"
        "（否则「唯一源把说明弄丢了」就没人管）。",
    ),
    Divergence(
        "ArticleKey",
        "x-not",
        "documentation",
        "x-not-by-witness",
        '有注释性禁令 `x-not: "禁止单字符或纯 s（P0-1 回归锚）"`',
        "生成物无对应键",
        "`x-not` 不是校验关键词，删掉就算对齐会让 P0-1 回归锚无主 ⇒ 改由见证向量承担："
        "裸 `s` 被 `ValidationError(string_too_short)` 拒。另由 "
        "`test_every_draft_x_keyword_is_registered` 强制「稿里每个 x-* 都能在本表 field 里找到」。",
    ),
    Divergence(
        "WorkListRow / ArticleManifest",
        "publish_time",
        "tightening",
        "timezone-required:publish_time",
        "format: date-time（默认只是注记，不 assert）",
        "AwareDatetime：无时区串被拒",
        "稿内字段说明自己写「provider 内即转为带时区时间」⇒ 把意图从注记升成真校验。"
        "消费者：`test_publish_time_requires_timezone_aware_value`。",
    ),
    Divergence(
        "CollectionEvent",
        "at",
        "tightening",
        "timezone-required:at",
        "format: date-time（注记）",
        "AwareDatetime",
        "「时间一律 ISO 8601 带时区；存储 UTC，业务日界 Asia/Shanghai」的落点。"
        "消费者：`test_collection_event_at_requires_timezone`。",
    ),
    Divergence(
        "DiscoveryChannelView",
        "lastSuccessAt",
        "tightening",
        "timezone-required:lastSuccessAt",
        "format: date-time + [string,null]",
        "AwareDatetime | None：无时区串被拒",
        "与 publish_time 同口径。第一版清单漏了它，是第二轮验证者补的。"
        "消费者：`test_last_success_at_requires_timezone`。",
    ),
    Divergence(
        "WorkListRow / WorkListPage / ArticleManifest / ManifestSyncReport / CollectionEvent / DiscoveryChannelView",
        "digest, author, content_hash, all_skipped_pages, idempotency_key, count, "
        "contractVerifiedAt, verifiedScope, lastSuccessAt, lastError, publish_time, total",
        "serialization",
        "dump-materializes-defaults",
        "可选字段，无 default",
        'default="" / 0 / None ⇒ model_dump() 会物化出来，且生成物里显式带 `default` 键',
        "接受集不变，但响应里多出显式的空串/0/null，前端按「字段是否存在」分支时会看到。"
        "消费者：`test_optional_defaults_materialize_on_dump`——本条 reason 第一次写的时候"
        "只承诺「另设一条 dump 形状检查」却没有实现者，第三轮验证正是因此判它 dead claim。"
        "**第五轮验证补的两件事**：①`default` 过去被比对器整个剥掉不比 ⇒ 两侧随便改默认值都读 0 条 "
        "差异，现在它进约束面，且只放行「稿没写⇒模型物化」这一个方向；②WorkListPage 之前没列进 ref，"
        "它自己物化的 `total` 默认值与 rows 里内联的 WorkListRow 默认值都无处认领。",
    ),
    Divergence(
        "*（除 WorkListRow 外所有模型）",
        "*",
        "strictness",
        "extra-dropped",
        "未声明 additionalProperties（= 允许）",
        'Pydantic 默认 extra="ignore" ⇒ 多余字段静默丢弃；生成物里也没有 additionalProperties 键',
        "有意不对称：WorkListRow 是上游透传面（稿里明写 additionalProperties: true），"
        "其余是落库/视图形状。差异体现在「丢弃」而不是「拒绝」⇒ 比对器看不见它，"
        "必须由行为断言负责。消费者：`test_unknown_fields_dropped_except_work_list_row`。",
    ),
)
