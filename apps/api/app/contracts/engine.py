"""可插拔引擎能力面契约（STEP-13 S13.3.1，D-V3-03 选 A：本轮不实接，只做能力面可见化）——唯一源是这里。

依据：`docs/任务规划V0.12.0/contracts/engine.schema.json`（STEP-13 新冻结）、ADR-0004、ADR-0008。
依赖方向同其余各域：不 import `app.providers` / `app.services` / `app.api`。
所以"`reason` 的取值来自 `ENGINE_IMPLEMENTED` 与 Key 解析"这条**实现一致性**由
`tests/test_engines_capability.py` 判，这里不复制引擎名单。

设计要点（为什么是这四个值、为什么是这个顺序）：
- 一个引擎位不可用，可能同时有好几个原因（没开放、没 Key、没实接）。用户与管理员要的是
  **最先该处理的那一个**，所以 `reason` 只给一个值，按"谁能解决"排序：
  `not_allowlisted`（管理员改开放名单）→ `key_missing`（管理员登记 Key）→ `not_implemented`
  （开发排期，D-V3-03 未推翻前无解）。这个顺序与切换校验 `assert_engine_switchable` 的拒绝顺序同源，
  两边读同一个函数，不各写一遍。
- `builtin` 是回退通道，恒为 `ok`：它若可以不可用，空间被切到坏引擎后就切不回来。
- `available == (reason == "ok")` 是不变量，不是巧合；契约测试逐条核。
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from . import Divergence


class EngineReason(str, Enum):
    """引擎位不可用的首要原因；可用时为 `ok`。"""

    ok = "ok"
    not_allowlisted = "not_allowlisted"
    key_missing = "key_missing"
    not_implemented = "not_implemented"


class EngineCapability(BaseModel):
    """`GET /api/v1/engines` 的 `items[]` 元素。"""

    model_config = ConfigDict(extra="forbid")

    engine: Annotated[str, Field(min_length=1, max_length=32)]
    available: bool
    reason: EngineReason
    implemented: bool
    configured: bool
    allowlisted: bool
    keyEnv: str  # noqa: N815 —— 已发布面保持 camelCase
    activeSource: Annotated[  # noqa: N815
        str | None, Field(description="生效的 Key 来源：registered / env；未配置或 builtin 为 null")
    ]
    decryptFailed: bool  # noqa: N815
    description: str


class EngineList(BaseModel):
    """`GET /api/v1/engines` 的信封 `data`（STEP-46，D-V21-01：响应形状进契约）。"""

    model_config = ConfigDict(extra="forbid")

    items: list[EngineCapability]
    defaultEngine: Annotated[str, Field(min_length=1, max_length=32)]  # noqa: N815


class SpaceEngineBinding(BaseModel):
    """`PATCH /api/v1/spaces/{space_id}/engine` 的信封 `data`（STEP-46）。

    `engineKbId` 对应 `knowledge_spaces.engine_kb_id`（String(128) NOT NULL DEFAULT ''）：
    非 builtin 引擎未实接前为空串，不是 null。
    """

    model_config = ConfigDict(extra="forbid")

    engine: Annotated[str, Field(min_length=1, max_length=32)]
    engineKbId: Annotated[str, Field(max_length=128)]  # noqa: N815
    spaceId: str  # noqa: N815


#: 稿与本模块的已知差异（语义判定见 tests/test_contract_jsonschema.py）。
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
        draft="稿里只有 activeSource 带说明",
        model="模型 docstring 会在更多位置生成 description",
        reason="文本不参与相等判定；单向断言「稿里有 ⇒ 产物也得有」由 `_description_losses` 承担。",
    ),
    Divergence(
        ref="*（本域所有可空字段）",
        field="*",
        kind="structural",
        rule="nullable-form",
        draft='activeSource 写成 "anyOf": [string, null]',
        model='同样是 "anyOf": [ …, {"type": "null"}]',
        reason="比对器对可空写法统一在事实层合流（types/nullable 两个事实位），归一被用到就要有人认领。",
    ),
)
