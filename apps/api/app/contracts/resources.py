"""资源域契约（STEP-01 S1.2.2 第四个域）——唯一源是这里，产物是 `resources.schema.json`。

依据：`docs/任务规划V0.12.0/contracts/resources.schema.json`（冻结稿 V0.7.0）与 ADR-0008/0011/0012。
依赖方向同前三个域：不 import `app.services` / `app.models` / `app.api`。
**例外一处**：`ArticleKey` 从 `collection.py` 引——键空间是全仓共享的事实，
在这里再写一份 pattern 就是第二个真源，而那正是本卡要消灭的东西（ADR-0011）。

不在本模块的东西（稿根层已打 `x-not-in-single-source`，比对脚本据此跳过，
并由 `test_not_a_shape_claims_are_narrow` 反向核验）：
- `ChannelSecret`：AES-256-GCM、AAD 绑定渠道 id、fail-closed、生产双主密钥守卫、
  管理端只回显掩码。全是加密实现与运维纪律，没有一条是字段形状；
  而且**任何响应都不该出现这个形状**（`x-projection-rules` 明令不得回传密文或解密材料）。

刻意收编但带两条已登记不等的地方：
1. `ContentAsset.externalId` / `ShortLinkMap.articleKey`：稿里 `$ref` 到的 `ArticleKey` 只有
   长度界（8/128），规范 pattern 只活在 `x-target-pattern` 这句注释里；产物的别名带 pattern ⇒
   产物比稿多一条校验。见 `resources-pattern-not-validated-in-draft`（conflict，台账 D-V8-06）。
2. `InAppNotification.sub`：identity 域有 `Sub`（1..64）这个别名，这里**不用它**——
   本域稿写的是裸 `string`，套上 `Sub` 等于替这份合同加它没声明的边界。
   同一概念在两域有两种形状，是跨域事实不一致，登记 `sub-not-aliased-to-identity` 并发布于
   `00-README` 的待认领清单，不由我静默统一。
"""
from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from . import Divergence
from .collection import ArticleKey

# publishedAt 的语义由稿钉死：null = 上游没给时间，**禁止**用抓取时间伪造（P-1 那条 RSS 缺陷）。
# 所以这里保持可空，且用 AwareDatetime 要求带时区（与 collection 域同口径）。
# 只留**被模型用到的**名字：一个没人引用的类型别名就是死契约面（identity 的 UserId 前车之鉴）。
AssetStatus = Literal["READY", "PENDING", "FAILED", "STALE", "SUPERSEDED"]


class ContentAsset(BaseModel):
    """内容资产（运行时形状来自 `models/entities.py:118-146` 的 `ContentAsset` 表）。

    属性名用 camelCase 别名（稿面如此），Python 侧保持 snake_case；
    `external_id` 装的是**规范文章键**，不是渠道上游 id——那两层键空间的区别见 ADR-0012 §1。
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(max_length=36)
    source_id: str = Field(max_length=36, alias="sourceId", description="FK sources.id ON DELETE CASCADE")
    external_id: ArticleKey = Field(
        alias="externalId",
        description="文章身份键。实测 ContentAsset.external_id 取 `kb._article_key(url)`"
        "（S2.2.3 起即 ADR-0011 规范键；此处刻意不写行号锚——本仓库行号每批都漂，"
        "符号名才是可查的锚）；而 ArticleManifest.external_id 装渠道上游 id——"
        "两个键空间不相交即 P0-2/P-2 根因（ADR-0012 §1）",
    )
    url: str = Field(
        default="",
        max_length=512,
        description="原文 URL。片段反查靠 url LIKE '%fragment%'（repositories/asset.py:66），故必须含可定位末段",
    )
    title: str = Field(default="", max_length=512)
    author: str = Field(default="", max_length=128)
    published_at: AwareDatetime | None = Field(
        default=None,
        alias="publishedAt",
        description="null = 上游未给时间，禁止用抓取时间伪造（P-1：RSS RFC 822 解析失败即属此类）",
    )
    content_type: Literal["article"] = Field(
        default="article", alias="contentType", description="String(16) 默认 article；新增取值属契约变更"
    )
    content_hash: str = Field(min_length=64, max_length=64, alias="contentHash", description="幂等三元组之一")
    raw_uri: str = Field(default="", max_length=512, alias="rawUri")
    content_markdown: str = Field(
        default="", alias="contentMarkdown", description="标准化正文；大正文不得进列表响应（x-projection-rules）"
    )
    version: int = Field(default=1, ge=1)
    quality_score: float = Field(default=0.0, ge=0, le=100, alias="qualityScore")
    # 稿把 status 列进 required，所以这里不给默认值：DB 的 default="READY" 是落库便利，
    # 不是合同允许省略它（省略就该拒）。
    status: AssetStatus = Field(description="实测代码只用到 READY 与 stale 语义，后四值是目标枚举")
    hit_count: int = Field(default=0, ge=0, alias="hitCount", description="命中即 +0 微信请求（AB-P004）")
    category: str = Field(default="", max_length=32)


class ShortLinkMap(BaseModel):
    """短链 key → 长链 article_key 的映射（`entities.py:148+`）。

    视图形状只带稿声明的两个字段：DB 行还有 `id` 与 `biz`，把它们收进来就是
    **吸收步骤擅自新增契约面**（identity 域那次 `SpaceAccessRow` 的错我不再犯第二次）。
    """

    model_config = ConfigDict(populate_by_name=True)

    short_key: str = Field(max_length=128, alias="shortKey")
    article_key: ArticleKey = Field(
        alias="articleKey", description="长链形态的规范文章键（全仓唯一在用它的位置之一）"
    )


class InAppNotification(BaseModel):
    """站内通知（`models/bothot_entities.py:265` 的 `Notification`）。

    `sub` 是可见性锚：定向与广播共用同一谓词（`api/v1/system.py:297` 注释），
    广播落库时 `sub=""` 且 `is_broadcast=True`——那个位标志不在本域稿里，故不进视图。
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(max_length=36)
    sub: str = Field(description="可见性锚。定向 + 广播共用同一谓词")
    title: str = Field(max_length=256)
    body: str = Field(default="")
    read_at: AwareDatetime | None = Field(default=None, alias="readAt")
    created_at: AwareDatetime = Field(alias="createdAt")


# ── 与冻结稿的差异登记（比对脚本按 (域, ref, field) 放行）─────────────────────

CONTRACT_DIVERGENCES: tuple[Divergence, ...] = (
    Divergence(
        "ChannelSecret",
        "*",
        "structural",
        "not-a-shape",
        "一个 definitions 条目，内容是算法/AAD/fail-closed/生产守卫/管理面回显规则",
        "生成物里没有这个 def，也不会有",
        "退出比对由**稿自己声明**（根层 `x-not-in-single-source`）+ 本条 structural 点名，缺一处都红"
        "（`test_not_a_shape_claims_are_narrow`）。责任落点：`core/secret_crypto.py`（AES-256-GCM、"
        "域分隔 AAD、fail-closed）、`config.py` 的生产守卫、`api/v1/admin.py` 的掩码回显。"
        "**更要紧的是这条不该有形状**：`x-projection-rules` 明令任何响应都不得包含密文或解密材料，"
        "把它做成一个可实例化的模型反而诱导有人去序列化它。",
    ),
    Divergence(
        "ArticleKey",
        "x-current-algo, x-target-pattern, minLength, maxLength",
        "structural",
        "alias-inlining",
        "是 definitions 条目：`minLength: 8`、`maxLength: 128`，两条注释分别写现状算法与目标 pattern",
        "类型别名不出现在 `$defs`，约束被内联进 `ContentAsset.externalId` 与 `ShortLinkMap.articleKey`",
        "别名是从 `collection.py` 引过来的（同一个键空间只能有一个真源），"
        "所以长度界取两稿里更严的 8——台账行 **D-V8-02**，且已实测三支分支最短可过串是 10 字符，"
        "取 8 不排任何合法键（`test_article_key_bounds_are_redundant` 同时钉两稿的界与产物取值）。"
        "`x-current-algo` 记的是**现状缺陷**（长链恒为 `s`，P-3 冒名根因），不是目标；"
        "`x-target-pattern` 的目标形状见下一条——它在这里只是注释，在产物里是校验。",
    ),
    Divergence(
        "ContentAsset / ShortLinkMap",
        "properties.externalId.pattern, properties.articleKey.pattern",
        "conflict",
        "resources-pattern-not-validated-in-draft",
        "键的规范形状只活在 `x-target-pattern` 这句**注释**里，`$ref` 到的 ArticleKey 只有长度界",
        "产物的别名带 `pattern`，于是这两个位置的接受集比稿更窄",
        "两侧不是等价改写、也不是宽严可判：稿把规范键当**说明**，源把它当**校验**。"
        "取源侧（ADR-0011 的 b:/s:/h: 是已签裁决 D-V2-01/D-V3-01 的形状，注释只是它的散文形式），"
        "但把不等登记成 conflict 并引台账：**D-V8-06**。"
        "消费者：`test_resources_pattern_is_the_a_d_r0011_shape`（拿 ADR 文本与两域产物三方对读）。",
    ),
    Divergence(
        "InAppNotification",
        "sub",
        "documentation",
        "sub-not-aliased-to-identity",
        "本域稿写的是裸 `string`（无 min/maxLength）",
        "产物也是裸 string——**没有**改用 identity 的 `Sub`（1..64）",
        "同一概念在两域有两种形状是跨域事实不一致：改套 `Sub` 等于替这份合同加它没声明的边界，"
        "不套则 `sub` 的长度只在 DB 列与 identity 域有据。这条登记负责让分歧**可见**，"
        "统一与否发布于 `00-README` 待认领清单由 owner 判，不由吸收步骤静默决定。"
        "消费者：`test_inapp_notification_sub_is_deliberately_unbounded`。",
    ),
    Divergence(
        "ContentAsset",
        "properties.contentType.const, properties.contentType.enum",
        "structural",
        "single-value-literal-is-enum",
        "单值枚举写成 enum: [article]（稿里的字面形式）",
        "同样的单值约束在产物里写成 const（Pydantic 对单成员 Literal 的固定写法）",
        "取值集相同、接受集相同，只是两种写法；这一条与 `default` 那半句配套："
        "产物会顺带物化一个默认值，而那是**唯一取值的复述**、不是新的契约事实"
        "反过来（默认值不等于唯一取值）就不是复述，而是真的改契约 ⇒ 必红。"
        "消费者：`test_content_type_single_value_enum_is_equivalent`。",
    ),
    Divergence(
        "ContentAsset",
        "contentType",
        "structural",
        "single-value-enum-to-const",
        "单值枚举写成 enum: [article]（稿里的字面形式）",
        "生成物写成 const: article",
        "在**事实层**合流而不是各记一条差异：单成员 enum 与 const 是同一接受集的两种写法。"
        "合流有边界——两支及以上 enum 不合流（`test_single_value_enum_normalization_cannot_hide_a_second_value`），"
        "所以它不能被用来藏第二个取值。",
    ),
    Divergence(
        "*（本域全部 def 与属性）",
        "description",
        "documentation",
        "strip-description",
        "稿里 ContentAsset 多个属性与 InAppNotification.sub 带说明",
        "模型 docstring / Field description 会在更多位置生成 description",
        "文本不参与相等判定；单向断言「稿里有 ⇒ 产物也得有」由 `_description_losses` 承担。",
    ),
    Divergence(
        "*（本域所有可空字段）",
        "*",
        "structural",
        "nullable-form",
        '写成 "type": ["object", "null"] 或 ["string", "null"]',
        '写成 "anyOf": [ …, {"type": "null"}]',
        "Pydantic 的可空固定写法，语义相同；比对器在事实层合流（types/nullable 两个事实位）。"
        "同名条目必须存在：归一被用到就要有人认领（第六轮之后按 rule 名核对）。",
    ),
    Divergence(
        "ContentAsset",
        "status",
        "structural",
        "default-on-required-is-inert",
        "status 同时出现在 `required` 与带 `default: READY` 的位置",
        "产物里 status 是必填、**不写** default",
        "required 已经保证这个键必然存在 ⇒ 稿那句 default 不参与校验，产物不写它不算差异。"
        "只开「稿有、产物不写」一个方向：第八轮验证 T3(b) 打穿的就是我把方向写漏了——"
        "产物把默认值改成 PENDING 也曾读绿，那已经是改接受语义而不是省略惰性事实，"
        "现由 `test_inert_default_rule_does_not_cover_a_changed_value` 钉住。",
    ),
    Divergence(
        "*（所有 def）",
        "required",
        "structural",
        "required-order",
        "required 由作者手写顺序",
        "生成物按模型字段顺序，比对时排序后比集合",
        "required 是集合，顺序无语义；登记是为了让「我们排序了」这件事有人负责。",
    ),
    Divergence(
        "*（文档根）",
        "x-generated-by, x-source-module",
        "documentation",
        "generated-provenance-keys",
        "稿里没有这两个键",
        "生成物根层带这两个溯源键",
        "产物必须自证是谁生成的。消费者：`test_artifact_provenance_keys_are_declared`（逐域验）。",
    ),
    Divergence(
        "*（文档根）",
        "type",
        "structural",
        "root-is-a-container",
        "稿根声明 `type: object`",
        "生成物根层没有 `type`（它是 `$defs` 容器文档）",
        "同 collection/events：稿根那句是「本文描述一个对象文档」的占位，产物把每个形状放 `$defs`。"
        "只解释「稿声明而产物不声明」这一个方向。消费者：`test_document_root_divergences_are_named`。",
    ),
    # root-identifier-conflict 不再需要：三份稿的 $id 已按 D-V8-03 的默认值 A 统一到产物侧标识符式。
    Divergence(
        "*（本域全部 def）",
        "*",
        "structural",
        "definitions-vs-refs-dialect",
        "稿用 draft-07 的 `definitions` 与 `#/definitions/X`",
        "生成物用 2020-12 的 `$defs` 与 `#/$defs/X`",
        "两种方言并存是稿子内部的不一致（只有 collection 用 `$defs`），比对器按同一语义处理，不静默择一。",
    ),
    Divergence(
        "ContentAsset / ShortLinkMap / InAppNotification",
        "x-unique, x-index-strategy, x-write-rule, x-delivery, x-offline-catchup, x-index",
        "documentation",
        "resources-annotations-have-owners",
        "五个注释键：唯一键名、索引缺口、写入条件、写侧调用点、离线补投机制",
        "生成物里没有这些键",
        "每条都点名了责任人而不是被删掉：`x-unique`/`x-index-strategy` 的**索引缺口**是 STEP-R0 R0.3.1 "
        "的实测项（按 external_id 单查不走 `uq_asset_source_external` 前导列，需 `ix_content_assets_external_id`，"
        "迁移号 ab1006r0a）；`x-write-rule` 说「仅 final_key != short_key 才写」——正因如此 R0 不能用映射表"
        "替代资产反查（直抓短链 URL 不变时写不进表）；`x-delivery` 的「手动/测试路径不落库」由 coverage §3 记账；"
        "`x-offline-catchup` 是 notifications 表 + SSE 首连拉 history，不是消息队列重放。"
        "本条的可执行落点是 `test_resources_annotations_name_real_anchors`：它去代码里找这些锚点还在不在。",
    ),
    Divergence(
        "ContentAsset / InAppNotification",
        "url, title, author, rawUri, contentMarkdown, body, publishedAt, readAt, contentType",
        "serialization",
        "resources-dump-materializes-defaults",
        "这些字段在稿里是可选、无 default",
        '模型有默认值 ⇒ dump 物化出空串，且生成物显式带 `default` 键',
        "接受集不变。消费者：`test_resources_defaults_materialize_on_dump`。",
    ),
)
