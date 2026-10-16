"""异步事件与作业契约（STEP-01 S1.2.2 第三个域）——唯一源是这里，产物是 `events.schema.json`。

依据：`docs/任务规划V0.12.0/contracts/events.schema.json`（冻结稿 V0.7.0）与 ADR-0008。
依赖方向同前两个域：不 import `app.services` / `app.providers` / `app.models`。
所以「事件名集合 == `push_events.VALID_EVENT_TYPES`」「退避 = 60·4^(n-1) 且上限 3 次」
这两类**跨包一致性**由 `tests/test_collection_contract.py` 单向核对，契约里不复制实现。

不在本模块的东西（都已在冻结稿根层打 `x-not-in-single-source` 标记，比对脚本据此跳过，
并由 `test_not_a_shape_claims_are_narrow` 反向核验「确实不是形状 + 确实有登记接手」）：
- `EventPayloadRules`：payload 自足原则与三类快照字段表。它讲的是「emit 时快照哪些键」，
  Pydantic 表达不了这条已知缺陷——查不到对象时静默置空串（稿里 `x-known-defect` 已转 STEP-05）。
- `QueueMechanism`：PG + `FOR UPDATE SKIP LOCKED`、禁 Redis 队列、Redis 不可达时三处降级行为。
  全是实现选型与可用性规则，不是字段形状。
- `ManifestTransition`：四态状态机与两条非法边。**值集已在 `collection.ManifestStatus` 钉过**，
  这里再建一个枚举就是第二个真源；边能不能走是行为，由 STEP-04 S4.4.2.1 的用例负责。

刻意收编但**与实现冲突**的一条：`PushRetryState.responseData`。稿里写 `object|null`，
实测生产端 `providers/push/base.py:50` 是 `response_data: str = ""`（六个 Provider 无一例外把
上游回执原文按字符串塞进来）。两者类型不相交，契约取实测——产物是消费端读的形状，
写成 `object|null` 会让前端按稿实现的解析器在第一条真实回执上就炸。
冲突不许被「取实测」掩盖：见登记表 `response-data-type-conflict` 与它的裁决请求。
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from . import Divergence

# Job.idempotency_key 的长度上界（DB 列 String(128)）。稿里另有两条**非形状**规则
# （键必须由「定宽时间戳 + 资源 id」构成、禁止拼用户可控串），本模块表达不了，
# 由登记表点名责任人，而不是删掉当没写过。
IdempotencyKey = Annotated[str, StringConstraints(max_length=128)]


class EventName(str, Enum):
    """事件名值集。真源是 `services/push_events.py:26` 的 `VALID_EVENT_TYPES`。

    新增事件名属契约变更：本枚举、那个常量、冻结稿的 `enum` 三处必须同时改，
    由 `test_event_name_set_equals_valid_event_types` 钉住三方相等。
    顺序也带语义（稿里是声明序）——比对器比 enum 列表原序，不排序。
    """

    NEW_ARTICLE = "new_article"
    HOT_TOPIC_UPDATE = "hot_topic_update"
    DAILY_REPORT = "daily_report"


class PushRetryState(BaseModel):
    """一次投递的回执与重试判据（运行时形状来自 `providers/push/base.py:39-51` 的 `PushResult`）。

    与 `PushResult` 的已知不等写在登记表 `response-data-type-conflict` 里，
    两边对应关系由契约测试单向核对——这里复制那份 dataclass 就是第二个真源。
    """

    model_config = ConfigDict(populate_by_name=True)

    delivered: bool
    reason: str = Field(max_length=512, description="失败必有可读原因，不伪造回执（AGENTS.md 关键约束 6）")
    # 实测是字符串（上游回执原文）；稿里的 object|null 从未在任何 Provider 里成立过。
    response_data: str = Field(default="", alias="responseData")
    retryable: bool


# ── 与冻结稿的差异登记（比对脚本按 (域, ref, field) 放行）─────────────────────

CONTRACT_DIVERGENCES: tuple[Divergence, ...] = (
    Divergence(
        "EventPayloadRules / QueueMechanism / ManifestTransition",
        "*",
        "structural",
        "not-a-shape",
        "三个 definitions 条目：事件快照字段表、队列机制声明、四态状态机",
        "生成物里没有这三个 def，也不会有——Pydantic 不承载「emit 时快照哪些键」"
        "「用什么锁领取」「沿哪些边迁移」这类规则",
        "退出比对必须由**稿自己声明**（根层 `x-not-in-single-source`）+ 本条 structural 点名，"
        "两处缺一处都红（`test_not_a_shape_claims_are_narrow`）。责任落点："
        "EventPayloadRules → `push_events.py:29-66` 的 `_hydrate_payload` + STEP-05 的空值计数告警"
        "（稿里 `x-known-defect` 那条「查不到就静默置空串」目前无人可见）；"
        "QueueMechanism → AGENTS.md 关键约束 4 与 `repositories/job.py` 的 SKIP LOCKED；"
        "ManifestTransition → 值集已由 `collection.ManifestStatus` 钉住，边的合法性由 STEP-04 "
        "S4.4.2.1 逐条建用例（两条非法边各一条）。",
    ),
    Divergence(
        "IdempotencyKey",
        "x-rule, x-forbidden",
        "structural",
        "alias-inlining",
        "是 definitions 条目，带 `maxLength: 128` 与两条治理注释",
        "类型别名不出现在 `$defs`；本域**没有任何模型引用它**，所以约束在产物里根本不存在",
        "与 identity 的 `UserId` 同一类：约束只剩「源模块 + 见证测试」两个落点，"
        "由 `ALIAS_WITNESSES` 点名 `test_idempotency_key_alias_witness` 直接跑 TypeAdapter——"
        "不许再写一句「会被内联到使用处」把它讲圆，那句话在这里没有指代对象。"
        "`x-rule`（定宽时间戳 + 资源 id，禁随机 uuid）与 `x-forbidden`（禁拼用户可控串，"
        "否则前缀 LIKE 会越权命中他人作业）都不是形状：前者的实测键形状"
        "（`sync_account:{sourceId}…` / `hot_rescore:yyyyMMddHH`）由见证测试覆盖，"
        "后者属写入侧纪律，转 STEP-03 的作业创建路径评审，不在这里假装 schema 能挡住。",
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
        "产物必须自证是谁生成的；比对器允许它存在但要求本条登记在位。"
        "消费者：`test_artifact_provenance_keys_are_declared`（逐域验，含本域）。",
    ),
    Divergence(
        "*（本域全部 def）",
        "*",
        "structural",
        "definitions-vs-refs-dialect",
        "本域冻结稿用 draft-07 风格的 `definitions` 容器与 `#/definitions/X` 引用",
        "生成物用 2020-12 的 `$defs` 与 `#/$defs/X`",
        "同一仓库里两种方言并存是稿子内部的不一致（只有 collection 用 `$defs`）。"
        "比对器按同一语义处理两者，**不静默选一个**：见 rule 的消费点。",
    ),
    Divergence(
        "EventName",
        "x-source-of-truth",
        "documentation",
        "event-name-set-anchor",
        "枚举上挂着「真源是 push_events.py:26 的 VALID_EVENT_TYPES，新增须三处同改」这条注释",
        "生成物只有 enum 值集",
        "注释说的是一件**可以被机器判**的事，所以不留在文本里：契约测试断言 "
        "`{e.value for e in EventName} == VALID_EVENT_TYPES`，且与稿的 enum **同序**。"
        "消费者：`test_event_name_set_equals_valid_event_types`。",
    ),
    Divergence(
        "PushRetryState",
        "x-retry-policy, x-contract-gap",
        "documentation",
        "push-retry-annotations",
        "退避表（maxRetries 3 / 60,240,960 / 60·4^(n-1) / 第 4 次转死信）"
        "与一条「前端看不到投递终态」的缺口声明",
        "生成物只有字段形状",
        "退避那组数字是可执行事实，不该只当注释：测试直接读 `push_scheduler.MAX_PUSH_RETRIES` 与 "
        "`RETRY_BACKOFF_BASE_SECONDS`，算出前三次退避再与稿的 `backoffSeconds` 比。"
        "`x-contract-gap`（投递终态无消费面）是缺口不是形状，转 STEP-06 的 admin 读面——"
        "在这里补一份字段等于凭空造契约面。消费者：`test_retry_policy_constants_match_frozen_draft`。",
    ),
    Divergence(
        "PushRetryState",
        "properties.responseData.types, properties.responseData.nullable",
        "tightening",
        "response-data-type-conflict",
        '`"type": ["object", "null"]`（对象或 null）',
        '`"type": "string"`（实测生产端形状，默认空串）',
        "两侧**类型不相交**，不是宽严关系：稿说 object|null，而 `providers/push/base.py:50` 是 "
        '`response_data: str = ""`，六个 Provider 无一例外把上游回执原文按字符串塞进来。'
        "本条取实测，同时把它标成**待裁决的冻结稿缺陷**：出路是裁决「改 PushResult 成结构化」"
        "还是「改稿」，而不是让契约与实现悄悄分家——那正是这条门禁要防的事。"
        "消费者：`test_push_retry_state_tracks_runtime_push_result`（钉住两边当前真实形状与差集）。",
    ),
    Divergence(
        "PushRetryState",
        "responseData",
        "serialization",
        "events-dump-materializes-defaults",
        "可选字段，无 default",
        'default="" ⇒ model_dump() 物化空串，且生成物里显式带 `default` 键',
        "接受集不变（稿没写默认值，模型给的是「缺失即空串」）。"
        "消费者：`test_push_retry_default_materializes_on_dump`。",
    ),
)
