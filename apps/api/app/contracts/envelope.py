"""HTTP 响应信封与分页壳契约（STEP-01 S1.2.2 第五个域 `api.envelope`）——唯一源是这里。

依据：`docs/任务规划V0.12.0/contracts/api.envelope.schema.json`（冻结稿 V0.7.0）、ADR-0008、D-V8-08。
依赖方向同其余四域：不 import `app.core` / `app.services` / `app.models` / `app.api`。

这份稿是五份里**唯一"根即形状"**的一份：信封本身就写在文档根（`type/required/properties`），
没有 `definitions`。所以本模块用 `__contract_root__` 告诉生成器"把 `Envelope` 的形状摊到产物根上"，
产物与稿就是同一份文档的两种写法，消费端按 `$id` 解析时根层能对上（D-V8-08 选 A 的理由）。

三个分页壳原来藏在稿根的 `x-pagination` 注释位里（`styleA_current` / `styleB_current` /
`targetUnified`）。它们是 D-V3-01 裁过的契约面，藏在 `x-` 位等于没有合同——D-V8-08 把它们提升为
`definitions` 的 `PageStyleA` / `PageStyleB` / `PageTargetUnified`，这里一一对应。

**这里描述的是线上的形状，不是运行时类的默认值**：`core/response.py::Envelope` 给 `code`/`message`
带了默认值，但它序列化出去时四个键总在场，所以线上看 `code`/`message`/`requestId` 恒必填。
"运行时产出的每个信封都满足本契约"由 `tests/test_contract_jsonschema.py` 用标准库 validator 判，
不在这里 import 运行时类（那会反转依赖方向）。
"""
from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema

from . import Divergence

#: 稿把 `items` 写成裸 `{"type": "array"}`（元素形状由各端点自己定），Pydantic 对 `list[Any]` 会多写一个
#: 空的 `items: {}`——接受集相同但字面不同。这里直接声明成稿的写法，免得为一处无语义的差异立登记。
_AnyArray = Annotated[list[Any], WithJsonSchema({"type": "array"})]

#: 信封 `data`：稿写的是三支两两不相交的 `oneOf`，照原样声明。
_EnvelopeData = Annotated[
    dict[str, Any] | list[Any] | None,
    WithJsonSchema({"oneOf": [{"type": "null"}, {"type": "object"}, {"type": "array"}]}),
]

#: 告诉 `scripts/gen_contracts.py`：本域产物的**根**就是这个模型的形状（其余模型照常进 `$defs`）。
__contract_root__ = "Envelope"


class Envelope(BaseModel):
    """`{code, message, requestId, data?}`；多余键拒收（稿 `additionalProperties: false`）。"""

    model_config = ConfigDict(extra="forbid")

    code: int
    message: Annotated[str, Field(max_length=512)]
    data: _EnvelopeData = None
    requestId: Annotated[str, Field(min_length=1)]  # noqa: N815 —— 已发布面保持 camelCase（D-V3-02）


class PageStyleA(BaseModel):
    """limit/offset 壳（admin/spaces/subscriptions 存量）。"""

    model_config = ConfigDict(extra="forbid")

    items: _AnyArray
    total: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1)]
    offset: Annotated[int, Field(ge=0)]


class PageStyleB(BaseModel):
    """page/page_size 壳（bots/hot 存量）。"""

    model_config = ConfigDict(extra="forbid")

    items: _AnyArray
    total: Annotated[int, Field(ge=0)]
    page: Annotated[int, Field(ge=1)]
    page_size: Annotated[int, Field(ge=1)]


class PageTargetUnified(BaseModel):
    """V0.7.0 目标唯一分页壳（新接口强制）。稿没写 `additionalProperties` ⇒ 多余键放行。

    稿给 `page`/`pageSize` 同时写了 `default` 与 `required`：线上必须出现，默认值只是给调用方的提示。
    所以这里字段必填，`default` 作为注解写进 schema，不让 Pydantic 把它们变成可缺省字段。
    """

    items: _AnyArray
    page: Annotated[int, Field(ge=1, json_schema_extra={"default": 1})]
    pageSize: Annotated[int, Field(ge=1, le=200, json_schema_extra={"default": 20})]  # noqa: N815
    total: Annotated[int, Field(ge=0)]
    hasMore: Annotated[  # noqa: N815
        bool, Field(description="由服务端算，前端不得自行用 total/pageSize 猜（避免越界请求）")
    ]


#: 稿与本模块的已知差异。语义判定交给标准库 validator（D-V8-05，`tests/test_contract_jsonschema.py`）；
#: 这里只登记**为什么字面不等**，且每条都要被旧比对器真的消费（`test_registry_rules_are_all_consumed`）。
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
        ref="*（所有模型与所有属性）",
        field="title",
        kind="documentation",
        rule="strip-title",
        draft="三个分页壳带作者写的中文 title",
        model="生成器统一剥掉 title（scripts/gen_contracts.py::_strip_titles）",
        reason="title 是人读文本，不参与校验；与 collection 域同一条归一。",
    ),
    Divergence(
        ref="*（本域全部 def 与属性）",
        field="description",
        kind="documentation",
        rule="strip-description",
        draft="稿里 hasMore 带说明",
        model="模型 docstring 会在更多位置生成 description",
        reason="文本不参与相等判定；单向断言「稿里有 ⇒ 产物也得有」由 `_description_losses` 承担。",
    ),
    Divergence(
        ref="*（本域全部 def）",
        field="*",
        kind="structural",
        rule="definitions-vs-refs-dialect",
        draft="本域冻结稿用 draft-07 风格的 `definitions` 容器（D-V8-08 提升出的三个分页壳）",
        model="生成物用 2020-12 的 `$defs`",
        reason="与 identity/events/resources 同一条方言归一；比对脚本按同一语义处理两者。",
    ),
)
