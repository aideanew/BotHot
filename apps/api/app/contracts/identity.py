"""身份与权限边界契约（STEP-01 S1.2.2）——唯一源是这里，产物是 `api.contracts.identity` 的 schema。

依据：`docs/任务规划V0.12.0/contracts/identity.schema.json`（冻结稿 V0.7.0）与 ADR-0008。
依赖方向同 `collection.py`：不 import `app.services` / `app.models` / `app.api`。
所以"角色梯 = `ROLE_RANK`"这类**跨包一致性**由 `tests/test_collection_contract.py` 单向核对，
不在模型里 import 被测实现。

不在本模块的东西（都已在冻结稿里打 `x-not-in-single-source` 标记，比对脚本据此跳过）：
- `x-permission-matrix` / `x-idor-checklist` / `x-admin-escalation-prohibited-paths`：
  它们是"端点 × 角色"的治理矩阵与越权清单，Pydantic 没有对应的表达能力；
  其执行面是 S1.4.3 的 IDOR 用例生成器与 `require_roles` 本身。
- `Role` 上的 `x-rank` / `x-grant-rule` / `x-default`：等级比较规则住在 `app/services/roles.py`，
  契约只钉**取值集**；两边相等由契约测试断言，不是由这里复制一份 rank 表
  （复制就是第二个真源，正是要消灭的东西）。
- `SessionClaims` 的 `x-transport` / `x-never-persisted`：传输与"不落库"是架构约束，不是字段形状。
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from . import Divergence

# users.sub：全项目唯一身份锚（AGENTS.md 关键约束 2）。DB 列 String(64) UNIQUE NOT NULL。
Sub = Annotated[str, StringConstraints(min_length=1, max_length=64)]

# 本地代理主键 UUID。**只**做域表外键锚，不外泄给前端当身份判断——那是 sub 的职责。
USER_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
UserId = Annotated[str, StringConstraints(pattern=USER_ID_PATTERN)]

# /me 的回显位。它不是校验对象、也不参与授权（缺本地 users 行时它 fail-closed 成 False，
# 而授权路径抛 10001，两者刻意分歧），所以只保留类型、不造模型。
IsAdminEcho = bool


class Role(str, Enum):
    """角色取值集。DB 侧仍是 `String(32)`（新增角色零迁移的项目惯例）。

    授权走等级比较而不是等值，比较表住在 `app/services/roles.py` 的 `ROLE_RANK`；
    本枚举与它的键集**必须相等**，由契约测试钉住。
    """

    USER = "user"
    OPERATOR = "operator"
    ADMIN = "admin"


class SessionClaims(BaseModel):
    """会话声明的最小集：只有 `sub` 是必填。

    `iss` / `aud` 在生产必须校验（REQ-NF-002），但**不在契约里设必填**——
    开发/测试链路的 stub IdP 不签发它们，设必填会让本地跑不起来而逼人绕过校验。
    这条选择是有意的，不是漏写。
    """

    model_config = ConfigDict(extra="forbid")

    sub: Sub
    iss: str = Field(default="", description="签发者；生产必须校验 iss/aud（REQ-NF-002）")
    aud: str = Field(default="", description="受众；与 iss 一并在生产侧校验")
    exp: int


# 刻意**不放**在这里的东西：越权（IDOR）用例的行形状。冻结稿的 `x-idor-checklist` 不是 def，
# 把它建成本域的一个模型会让生成物多出一个稿里没有的形状——吸收步骤没有资格新增契约面。
# 那个形状属于 S1.4.3 的生成器，与它一起落地。


# ── 与冻结稿的差异登记（比对脚本按 (域, ref, field) 放行）─────────────────────

CONTRACT_DIVERGENCES: tuple[Divergence, ...] = (
    Divergence(
        "Sub / SessionClaims",
        "x-rule, x-transport, x-never-persisted, x-never-persisted-reason",
        "documentation",
        "identity-x-annotations",
        "四条注释：sub 不得被本地 id 取代；会话走 HttpOnly Cookie；balance/level/credits 永不落库",
        "生成物里没有这些键（Pydantic 不承载治理注释）",
        "它们不是字段形状：前两条由 `tests/test_collection_contract.py` 的锚定断言 + 代码评审承担，"
        "第三条（永不落库）由 `x-never-persisted` 的检查脚本承担（当前实现是 grep，见 consumers）。"
        "把注释抄进模型只会造出第二个真源，所以这里只登记「谁负责」。",
    ),
    Divergence(
        "Sub / UserId / IsAdminEcho",
        "*",
        "structural",
        "alias-inlining",
        "三个都是 definitions 条目：Sub 有 min/maxLength，UserId 有 UUID pattern，"
        "IsAdminEcho 是 boolean 带 x-authoritative",
        "生成物里三个都没有，但**原因各不相同**——这一条以前把三者混成一句「约束被内联进使用处」，"
        "而 UserId 根本没有使用处，那句话对它是假的（第五轮验证抓到）",
        "Sub：`SessionClaims.properties.sub` 用 `$ref` 引它 ⇒ 约束在**产物里现形**（minLength 1 / maxLength 64），"
        "这是真正的别名内联。UserId：本域没有任何模型引用它，所以 pattern 既不在产物也不在任何使用处，"
        "它由 `ALIAS_WITNESSES` 点名的 `test_user_id_pattern_witnesses` 直接跑 TypeAdapter 见证——"
        "要么给它一个使用处，要么由后续裁决删掉这个别名，不能拿一句「内联了」把消失讲圆。"
        "IsAdminEcho：稿里已加 `x-not-in-single-source` 标记，它的职责（回显位不参与授权）是行为约束、"
        "不是形状，由 roles.py 与前端各自负责。",
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
        "产物必须自证是谁生成的；比对器允许它存在但要求本条登记在位。",
    ),
    Divergence(
        "*（本域全部 def）",
        "*",
        "structural",
        "definitions-vs-refs-dialect",
        "本域冻结稿用 draft-07 风格的 `definitions` 容器与 `#/definitions/X` 引用",
        "生成物用 2020-12 的 `$defs` 与 `#/$defs/X`",
        "collection 域的稿用 `$defs`，其余四域用 `definitions`——同一仓库里两种方言并存本身就是稿子的"
        "不一致。比对脚本按同一语义处理两者，**不静默选一个**：见 rule 的消费点。",
    ),
    Divergence(
        "SessionClaims",
        "exp, required",
        "tightening",
        "exp-required",
        "可选（required 只有 sub），类型 integer（不接受 null）",
        "必填 int：缺失与 null 都拒",
        "JWT 的 exp 缺失即无法判有效期，「可选」在这里没有可用场景；稿里 iss/aud 的默认 "" 同理保留宽松。"
        "消费者：`test_session_claims_requires_exp`。",
    ),
    Divergence(
        "SessionClaims",
        "iss, aud",
        "serialization",
        "identity-dump-defaults",
        "可选字符串，无 default",
        'default="" ⇒ model_dump() 物化空串',
        "接受集不变；消费者：`test_identity_defaults_materialize_on_dump`。",
    ),
    Divergence(
        "SessionClaims",
        "additionalProperties",
        "strictness",
        "identity-extra-forbid",
        "未声明 additionalProperties（= 允许）",
        'extra="forbid" ⇒ 多余键直接拒绝（比 collection 域的 ignore 更严）',
        "会话声明是安全边界，多一个未知 claim 不该被静默吞掉；这里选 forbid 而不是 ignore，"
        "并与 `x-never-persisted`（balance/level/credits）形成合力：就算有人塞进来也会被拒。"
        "消费者：`test_session_claims_rejects_unknown_claim`。",
    ),
    Divergence(
        "Role",
        "x-rank, x-default, x-grant-rule",
        "documentation",
        "role-rank-anchor",
        "枚举上挂三条注释：rank 表、默认 user、升权只有一条路",
        "生成物只有 enum 值集",
        "rank 表住在 services/roles.py（本包不许反向 import）⇒ 由契约测试断言"
        "`{r.value for r in Role} == set(ROLE_RANK)`；默认值与「只有一条路」是行为规则，不假装能被形状表达。",
    ),
)
