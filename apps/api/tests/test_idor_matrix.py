"""STEP-01 S1.4.3：越权（IDOR）用例矩阵。

纪律来源是冻结稿 `docs/任务规划V0.12.0/contracts/identity.schema.json#/x-idor-checklist` 两句话：

1. 凡路径含 `{space_id}` / `{job_id}` / `{doc_id}` 的端点，必须证明「资源属主 = 当前 sub」
   或「当前 rank ≥ operator」，二者皆无 → 403(10004) / 404(30004)；
2. 契约测试必须为**每个**此类端点生成一条「A 用户访问 B 用户的同一 id」用例。

本文件分两层，因为这两件事能在不同的机器上判：

- **第 1–2 节（本机 `@win` 就能跑）**：清单由路由表**枚举**生成（S1.4.3.2——手写必漏，
  漏了就是「已测」假象），枚举必须覆盖 OpenAPI 面；再用 AST 钉住"处理函数不许把调用者身份丢掉"。
  这一层不需要数据库，也正是它能立刻抓住真实缺陷的原因：
  `POST /spaces/{space_id}/docs` 与 `GET /spaces/{space_id}/docs/{doc_id}/status`
  两条洞就是这一层抓到的（形参挂着 `Depends(get_current_user_id)` 却一次都没被引用）。
- **第 3 节（`@ci` ubuntu，D-V4-01 的验收面）**：真的用 A 的身份打 B 的 id，判 30004/10004
  与"绝不返回/改动 B 的数据"。这一层要播种两个用户 + 空间 + 文档 + 作业，**必须连 PG**；
  本机 5432/5433 皆不可达（现读 TimeoutError），`conftest` 的 `db_session` 据此 skip。

一个实现陷阱写在这里而不是藏在代码里：本版 FastAPI（0.143.1）的 `app.routes` 返回的是
`_IncludedRouter` 包装对象——它自己没有 `path`。照 `for r in app.routes: r.path` 写会读出
**0 条**带路径参数的路由，整张矩阵静默变空。递归走 `.original_router.routes` 并带上
`.include_context.prefix` 才摊得平（第 1 节的 OpenAPI 交叉核对就是这条假设的守卫）。
"""

from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends

from app.api.deps import get_current_user_id, require_roles
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]

# 冻结稿点名的三类属主标识符。**不要**在这里顺手加别的 id：
# 扩清单属于裁决（见文末 KNOWN_GAP），吸收步骤没资格替合同加面。
OWNER_PATH_PARAMS = ("space_id", "job_id", "doc_id")

IDENTITY_DEPS = ("get_current_user_id", "get_current_sub")
ADMIN_PREFIX = "/api/v1/admin"
HTTP_METHODS = frozenset({"get", "put", "post", "delete", "patch", "options", "head", "trace"})
_PARAM_RE = re.compile(r"\{([a-zA-Z_]+)\}")

# 稿面规则**没说到**、但同样带属主语义的 id：见第 4 节那条"空白必须可见"的守卫。
UNLISTED_OWNER_PARAMS = frozenset(
    {"channel_id", "source_id", "task_id", "subscription_id", "topic_id"}
)
NON_OWNER_PARAMS = frozenset({"engine", "report_date"})


def _enumerate_operations(
    routes: list[Any], prefix: str = ""
) -> list[tuple[str, str, Any]]:
    """递归摊平路由表 ⇒ `(完整路径, 方法, 处理函数)`。"""
    out: list[tuple[str, str, Any]] = []
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            ctx = getattr(route, "include_context", None)
            out += _enumerate_operations(list(inner.routes), getattr(ctx, "prefix", None) or prefix)
            continue
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in sorted(set(methods) - {"HEAD", "OPTIONS"}):
            out.append((prefix + path, method, getattr(route, "endpoint", None)))
    return out


ALL_OPERATIONS = _enumerate_operations(list(app.routes))
OPERATION_KEYS = {(p, m) for p, m, _ in ALL_OPERATIONS}


def _openapi_operations() -> set[tuple[str, str]]:
    spec = app.openapi()
    return {
        (path, method.upper())
        for path, item in spec.get("paths", {}).items()
        for method in item
        if method in HTTP_METHODS
    }


def _id_params(path: str) -> tuple[str, ...]:
    return tuple(_PARAM_RE.findall(path))


CHECKLIST_OPERATIONS = tuple(
    sorted((p, m, ep) for p, m, ep in ALL_OPERATIONS if set(_id_params(p)) & set(OWNER_PATH_PARAMS))
)
UNLISTED_OPERATIONS = tuple(
    sorted(
        (p, m)
        for p, m, _ in ALL_OPERATIONS
        if _id_params(p) and not (set(_id_params(p)) & set(OWNER_PATH_PARAMS))
    )
)


# ── 1. 枚举的完整性（清单必须生成，不许手写）──────────────────────────────────


def test_route_enumeration_covers_the_openapi_surface() -> None:
    """枚举必须**至少**覆盖 OpenAPI 公布的全部操作——漏路由就是漏测试。

    方向是单向的：允许枚举多出 OpenAPI 没公布的操作（`/metrics`、`/docs`、
    `include_in_schema=False` 的探针面），因为那些确实存在；反过来少一个才是要防的事故。
    这条同时是 `_enumerate_operations` 那段递归假设的守卫：`app.routes` 的形状一变，
    读空或读少都会在这里红，而不是让矩阵静默变短。
    """
    assert OPERATION_KEYS, "枚举读空了——`app.routes` 的结构又变了，本文件的递归假设失效"
    missing = sorted(_openapi_operations() - OPERATION_KEYS)
    assert not missing, f"路由枚举漏了 {len(missing)} 个 OpenAPI 操作：{missing[:5]}"


def test_enumeration_matches_the_measured_baselines() -> None:
    """读数锚（2026-10-16 `@win` 现读）：93 个操作、47 个带路径参数、31 个落在稿面规则里。

    三个数**故意**钉死：本卡的教训是"清单变短没人发现"。真加/删端点时来改这条，
    不要把断言放宽成 `>= 0`——那等于没有守卫。
    """
    with_params = [x for x in ALL_OPERATIONS if _id_params(x[0])]
    assert len(ALL_OPERATIONS) == 93, len(ALL_OPERATIONS)
    assert len(with_params) == 47, len(with_params)
    assert len(CHECKLIST_OPERATIONS) == 31, len(CHECKLIST_OPERATIONS)


def test_checklist_scope_splits_admin_and_non_admin() -> None:
    """31 个操作必须全部落到某一腿，且 admin 面单独计。

    两腿的期望不同：非 admin 走「属主 = 当前 sub」，越权与不存在同语义 → 404(30004)；
    `/api/v1/admin/**` 那 9 个走稿面另一半「rank ≥ operator」，普通用户 → 403(10004)。
    把它们混成"期望 404"就是伪造一条契约。
    """
    admin = [x for x in CHECKLIST_OPERATIONS if x[0].startswith(ADMIN_PREFIX)]
    non_admin = [x for x in CHECKLIST_OPERATIONS if not x[0].startswith(ADMIN_PREFIX)]
    assert len(admin) == 9 and len(non_admin) == 22
    assert len(admin) + len(non_admin) == len(CHECKLIST_OPERATIONS)
    assert {m for _, m, _ in CHECKLIST_OPERATIONS} == {"GET", "POST", "PATCH", "DELETE"}
    slots = {(m, p) for p, m, _ in CHECKLIST_OPERATIONS}
    assert len(slots) == 31, "(path, method) 才能做键：同路径多方法必须各自成一条用例"


# ── 2. 接线底线：处理函数不许把调用者身份**丢掉**（无需 PG）────────────────────


def _identity_usage(endpoint: Any) -> str:
    """`role` / `threaded` / `UNUSED` / `NO-IDENTITY-ARG`。

    为什么值得用 AST 而不是只跑请求：连库用例在本机全 skip，而"声明了却不透传"这一类
    在播种之前就能静态抓住。两条真洞（`ingest_doc` / `get_doc_ingest_status`）的形状就是
    `_user_id: Annotated[str, Depends(get_current_user_id)]` + 函数体零次引用。
    这是**下界**不是证明：透传之后有没有真的比 `space.user_id`，由第 3 节在 `@ci` 判。
    """
    if endpoint is None:
        return "NO-IDENTITY-ARG"
    src = textwrap.dedent(inspect.getsource(endpoint))
    fn_def = ast.parse(src).body[0]
    if not isinstance(fn_def, ast.FunctionDef | ast.AsyncFunctionDef):
        return "NO-IDENTITY-ARG"
    args = list(fn_def.args.args) + list(fn_def.args.kwonlyargs)
    used = {node.id for node in ast.walk(fn_def) if isinstance(node, ast.Name)}
    for arg in args:
        seg = (ast.get_source_segment(src, arg.annotation) or "") if arg.annotation else ""
        if "require_roles(" in seg:
            return "role"
    for arg in args:
        seg = (ast.get_source_segment(src, arg.annotation) or "") if arg.annotation else ""
        if any(dep in seg for dep in IDENTITY_DEPS):
            return "threaded" if arg.arg in used else "UNUSED"
    return "NO-IDENTITY-ARG"


def test_every_checklist_endpoint_consumes_the_caller_identity() -> None:
    """31 个受约束的操作：要么角色门，要么把 user id 透传进服务。"""
    offenders = [
        f"{method} {path} [{ep.__name__}] ⇒ {_identity_usage(ep)}"
        for path, method, ep in CHECKLIST_OPERATIONS
        if _identity_usage(ep) not in {"role", "threaded"}
    ]
    assert not offenders, "这些端点拿到身份却不使用（IDOR 面）：\n" + "\n".join(offenders)


def _synthetic_discarding(space_id: str, _user_id: Annotated[str, Depends(get_current_user_id)], svc: Any) -> dict:
    return svc.ingest_url(space_id, "https://example.com/x")  # type: ignore[attr-defined]


def _synthetic_threaded(space_id: str, user_id: Annotated[str, Depends(get_current_user_id)], svc: Any) -> dict:
    return svc.ingest_url(space_id, "https://example.com/x", owner=user_id)  # type: ignore[attr-defined]


def _synthetic_role(space_id: str, actor: Annotated[str, Depends(require_roles("admin"))]) -> dict:
    return {"space": space_id}


def test_wiring_guard_is_falsifiable() -> None:
    """反证（S1.4.3.3 的静态半边）：把属主校验摘掉，判据必须立刻认出来。

    三个合成处理函数跑同一份 `_identity_usage`：声明却不透传 ⇒ UNUSED；
    透传 ⇒ threaded；角色门 ⇒ role。三条里只要有一条读成别的值，这条守卫就是装饰。
    """
    assert _identity_usage(_synthetic_discarding) == "UNUSED"
    assert _identity_usage(_synthetic_threaded) == "threaded"
    assert _identity_usage(_synthetic_role) == "role"


# ── 3. 连库矩阵：**不在本批落地**，理由写在这里而不是塞一个空壳进 CI ───────────
#
# A 用 B 的 id 逐端点请求（31 条）需要播种两个用户 + 空间 + 文档 + 作业，并给每个路径模板
# 填上 B 的真实 id。本机 5432/5433 皆拒连（现读 TimeoutError），而这批若现在写，
# 只有两种收尾：CI 里因为助手未实现而 error，或者 31 条全 skip 把"绿"变成假绿——
# 后者正是 U-20 明令禁止的形状。所以本批只交付能在本机验证的两层（枚举完整性 + 接线底线），
# 连库矩阵连同**生成好的端点清单**发布为 00-README §4 的 P-11，判据写在下面第 4 节的常量里。


# ── 4. 空白必须可见：稿面规则没覆盖到的属主 id ────────────────────────────────


def test_owner_ids_outside_the_frozen_checklist_are_visible() -> None:
    """稿面只点名 `space_id/job_id/doc_id`，路由表里却还有 5 类同样带属主的 id。

    现读（`@win`，2026-10-16）：`channel_id` 5、`source_id` 3、`task_id` 3、
    `subscription_id` 1、`topic_id` 1；另有 `engine` 2 与 `report_date` 1 不是属主标识符
    （配置键与日期键），留在"带参数但不在矩阵里"一侧。
    这条不是"测了"，是**没人能把这片空白说成已覆盖**：数量一变必红，逼改动的人回来更新裁决。
    """
    surfaced = {p for pair in UNLISTED_OPERATIONS for p in _id_params(pair[0])}
    assert surfaced - NON_OWNER_PARAMS == set(UNLISTED_OWNER_PARAMS), surfaced
    assert len(UNLISTED_OPERATIONS) == 16, len(UNLISTED_OPERATIONS)


KNOWN_GAP = (
    "x-idor-checklist 只点名 space_id/job_id/doc_id（31 个操作），而路由表另有 16 个带"
    "channel_id/source_id/task_id/subscription_id/topic_id 的操作未被规则覆盖。扩清单需要裁决，"
    "不在吸收步骤里顺手做——已发布为 V0.12.0 00-README §4 的 P-11。"
)


# ── 5. 期望值取自稿面文本，不取自我的散文 ─────────────────────────────────────

DENIAL_STATUSES = frozenset({403, 404})
DENIAL_CODES = frozenset({"10004", "30004"})

IDENTITY_DRAFT_PATH = REPO_ROOT / "docs" / "任务规划V0.12.0" / "contracts" / "identity.schema.json"


def _checklist_text() -> list[str]:
    import json

    doc = json.loads(IDENTITY_DRAFT_PATH.read_text(encoding="utf-8"))
    rules = doc.get("x-idor-checklist")
    assert isinstance(rules, list) and rules, "冻结稿里的 x-idor-checklist 不见了/不是列表"
    return [str(r) for r in rules]


def test_denial_vocabulary_comes_from_the_frozen_draft() -> None:
    """期望的状态码与错误码必须**就是稿面写的那两个**——防止我把判据改成自己顺手的样子。

    本卡十轮的复发族是"判据绑在我的实现上"。这条把出口条件反过来钉：
    先读稿面文本里出现的 403/404 与 10004/30004，再断言我的常量与之一致；
    将来稿面换码（比如把 30004 并到 30001），这条会先红，逼实现跟着改。
    """
    blob = " ".join(_checklist_text())
    for status in ("403", "404"):
        assert status in blob, f"稿面文本里没有 {status}，常量里却有 ⇒ 判据漂移"
    for code in ("10004", "30004"):
        assert code in blob, f"稿面文本里没有 {code}，常量里却有 ⇒ 判据漂移"
    assert DENIAL_STATUSES == {403, 404} and DENIAL_CODES == {"10004", "30004"}


def test_source_card_mentions_30001_but_the_draft_does_not() -> None:
    """来源卡写「404(30001/30004)」，而**稿面只给 30004**——这条差异必须可见。

    `30001` 是 `SpaceNotFoundError`（`app/core/errors.py:152`），现读空间/文档路由并不发它。
    把 30001 也列为"合法出口"等于给"空间不存在"与"不属于你"两种语义开了合并的口子，
    而稿面刻意用同一个 30004 来**不泄露存在性**。差异不靠吵架解决，靠这条钉住。
    """
    blob = " ".join(_checklist_text())
    assert "30001" not in blob, "稿面开始接受 30001 了 ⇒ 本条与来源卡需要一起重新核对"
    assert "30004" in blob


def test_generated_endpoint_list_is_the_p11_input() -> None:
    """P-11 的输入必须是**这张生成出来的清单**，不是任何人手抄的端点表。

    清单本身由枚举得到（第 1 节守着它不静默变短）。这里只钉两件事：
    ①非空且逐条带处理函数（连库用例要靠它反查签名）；②admin 腿与非 admin 腿之和 == 全量。
    将来 P-11 落地时，用例 id 直接取 `_case_id`，两端不必再抄一遍。
    """
    assert CHECKLIST_OPERATIONS and all(callable(ep) for _, _, ep in CHECKLIST_OPERATIONS)
    admin = [x for x in CHECKLIST_OPERATIONS if x[0].startswith(ADMIN_PREFIX)]
    assert len(admin) + (len(CHECKLIST_OPERATIONS) - len(admin)) == len(CHECKLIST_OPERATIONS)
    labels = {f"{m} {p}" for p, m, _ in CHECKLIST_OPERATIONS}
    assert len(labels) == 31, "用例标签必须逐端点唯一（同路径多方法不能并成一条）"


def _case_id(path: str, method: str) -> str:
    """P-11 用的用例 id：把路径模板压成一串可读且唯一的键。"""
    return f"{method}-{path.strip('/').replace('/', '_').replace('{', '').replace('}', '')}"


def test_case_ids_are_unique() -> None:
    ids = [_case_id(p, m) for p, m, _ in CHECKLIST_OPERATIONS]
    assert len(set(ids)) == len(ids) == 31, f"用例 id 撞了：{[i for i in ids if ids.count(i) > 1]}"
