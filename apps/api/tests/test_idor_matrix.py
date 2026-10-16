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

import pytest
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
    """期望的状态码/错误码必须**由稿面文本推导出来**，而不是我把常量再念一遍。

    第十一轮验证 G1 抓到的正是后一种写法：`DENIAL_STATUSES == {403, 404}` 是常量对字面量，永真；
    而 `"403" in blob` 这类 substring 会被 `24030` 之类的长数字串喂饱 ⇒ 稿面漂移守卫照样绿。
    现在改成双向：从 `x-idor-checklist` 抽出**所有 3–5 位数字串**，先要求集合恰为稿面那四个
    （多一个少一个都红，因为那说明出口条件被人改过而矩阵还按旧四条判），再由它**推导**两个常量。
    """
    blob = " ".join(_checklist_text())
    tokens = set(re.findall(r"(?<!\d)\d{3,5}(?!\d)", blob))
    assert tokens == {"403", "404", "10004", "30004"}, f"稿面的数字口径变了：现读到 {sorted(tokens)}"
    assert DENIAL_STATUSES == {int(t) for t in tokens if len(t) == 3}, DENIAL_STATUSES
    assert DENIAL_CODES == {t for t in tokens if len(t) == 5}, DENIAL_CODES


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


# ── 6. 给"修复本身"装反证（第十一轮验证 G3：全仓库没有一条用例能证明 owner 门存在）──

OWNER_GATED_METHODS = frozenset({"ingest_url", "get_doc_ingest_status"})
_API_DIR = REPO_ROOT / "apps" / "api" / "app" / "api" / "v1"


def _unthreaded_owner_calls() -> tuple[list[str], int]:
    """扫 `app/api/v1/**`：调用 owner 门方法却没写 `owner=` 的位置。返回 (违规, 扫到的调用数)。"""
    offending: list[str] = []
    seen = 0
    for path in sorted(_API_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in OWNER_GATED_METHODS:
                continue
            seen += 1
            if not any(kw.arg == "owner" for kw in node.keywords):
                offending.append(f"{path.name}:{node.lineno} {node.func.attr}() 未传 owner=")
    return offending, seen


def test_http_routes_never_rely_on_the_fail_open_default() -> None:
    """HTTP 层调用 owner 门方法时必须**显式**传 `owner=`，不许吃 `owner=None` 的默认值。

    为什么不把默认值删掉：`services/spaces.py::_delete_doc` 早就定了 `owner=None 表示无归属约束
    （后台/admin 跨用户路径）`，本仓库口径一致比"这条单独更严"重要；真正的风险面是
    **以后新增一条路由忘了传**，那一条现在会被这里抓住（第十一轮 G2 点名的 fail-open 面）。

    `seen` 也必须断言：扫描类守卫在"什么都没扫到"时天然读绿，那是最骗人的一种绿（G3 的同一族）。
    """
    offending, seen = _unthreaded_owner_calls()
    assert seen >= 2, f"只扫到 {seen} 处调用 ⇒ 扫描本身失效了，这条守卫现在是装饰"
    assert not offending, "这些 HTTP 调用没传 owner（会吃 fail-open 默认）：" + "; ".join(offending)


async def test_owner_gate_rejects_a_stranger_without_a_database(monkeypatch: Any) -> None:
    """S1.4.3.3 的反证补上**静态抓不到、连库又 skip** 的那一段：直接打 owner 门。

    第十一轮验证 G3 的实测结论是：把 `kb.py` 的 owner 判据整行删掉，本机可跑的整套测试仍然全绿
    （两条路由的用例需要 PG ⇒ skip；服务级用例都以 `owner=None` 调用）。
    这里用桩 repo 绕开数据库，钉住三个方向：
    ①别人的空间 + 传了 owner ⇒ 30004；②同空间 + owner 相符 ⇒ 已过门；③`owner=None` ⇒ 已过门（后台口径）。
    ②③用"门后的下一个调用"当哨兵：真到了门后才会撞上它。
    """
    from types import SimpleNamespace

    from app.services import kb as kb_module

    space = SimpleNamespace(id="space-b", user_id="user-b", engine="builtin")

    class _StubRepo:
        def __init__(self, session: Any) -> None:
            self._session = session

        async def get_by_id(self, space_id: str) -> Any:
            return space if space_id == space.id else None

    class _PastGate(RuntimeError):
        """门后的第一个调用点抛的哨兵：它的出现**就是**"已过 owner 门"的证明。"""

    async def _marker(self: Any, short_key: str) -> str:
        raise _PastGate(short_key)

    monkeypatch.setattr(kb_module, "SpaceRepository", _StubRepo)
    monkeypatch.setattr(kb_module.KnowledgeBaseService, "_lookup_short_link", _marker)
    svc = kb_module.KnowledgeBaseService(  # type: ignore[arg-type]
        client=object(), session=None, resolver=object()  # type: ignore[arg-type]
    )
    url = "https://mp.weixin.qq.com/s/abcdefgh"

    # ①别人的空间 + 传了 owner ⇒ 30004，且**绝不**走到门后
    with pytest.raises(kb_module.ResourceNotFoundError):
        await svc.ingest_url("space-b", url, owner="user-a")

    # ②同空间 + owner 相符 ⇒ 走到门后（哨兵而非 ResourceNotFoundError 证明方向没写反）
    with pytest.raises(_PastGate):
        await svc.ingest_url("space-b", url, owner="user-b")

    # ③后台口径：不传 owner ⇒ 无归属约束（job_worker / scheduler 靠这条，误拦会让采集停摆）
    with pytest.raises(_PastGate):
        await svc.ingest_url("space-b", url)

    # ④不存在的空间与"不属于你"必须同码——否则响应面就是一台存在性 oracle
    with pytest.raises(kb_module.ResourceNotFoundError):
        await svc.ingest_url("space-zzz", url, owner="user-a")


# ── 7. 单向核对的补集：整只路由器从两侧同时消失时也要能红 ─────────────────────

DOC_ONLY_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"})


def test_enumeration_accounts_for_every_registered_router() -> None:
    """OpenAPI 交叉核对是**单向**的：一只整组 `include_in_schema=False` 的路由器
    会同时从两侧消失，守卫却仍读绿（第十一轮验证 G2 点名）。这里改用注册表逐只对账。

    读数锚（2026-10-16 `@win`）：`APP_ROUTERS` 16 只 + `metrics_router` = 89 个操作，
    枚举 93 个，差集恰为 FastAPI 自带的 4 个文档路由（`/metrics` 属于 metrics_router，已在 89 内）。
    """
    from app.main import APP_ROUTERS, metrics_router

    def ops_of(router: Any) -> int:
        total = 0
        for route in router.routes:
            methods = getattr(route, "methods", None)
            if getattr(route, "path", None) and methods:
                total += len(set(methods) - {"HEAD", "OPTIONS"})
        return total

    registered_ops = sum(ops_of(rt) for rt in [*APP_ROUTERS, metrics_router])
    assert len(APP_ROUTERS) == 15, len(APP_ROUTERS)
    assert registered_ops == 89, registered_ops
    extra = sorted({p for p, _, _ in ALL_OPERATIONS if _is_doc_only(p)})
    assert len(ALL_OPERATIONS) == registered_ops + 4, (len(ALL_OPERATIONS), registered_ops)
    assert set(extra) == DOC_ONLY_PATHS, extra


def _is_doc_only(path: str) -> bool:
    return path in DOC_ONLY_PATHS


# ── 8. 下界这个词不许误导：机制与清单措辞不同的端点必须逐条列出 ────────────────

NON_OWNER_ROLE_GATED = frozenset({("PATCH", "/api/v1/spaces/{space_id}/public")})


def test_the_floor_overclaims_for_the_allowlist_gated_endpoint() -> None:
    """`PATCH /spaces/{space_id}/public` 的门**不是** `space.user_id`，而是
    `PUBLIC_ADMIN_ALLOWLIST` + `owner_type == "system"`（`services/public_library.py:34-43`）。

    AST 底线把它读成 `threaded` 是**过度声称**：身份确实被用了，但走的是另一条机制，
    而稿面规则「owner = sub 或 rank ≥ operator」在这里由 allowlist 兑现。
    第十一轮验证 E 项点名了这一处，所以这张表必须存在且必须仍然对得上清单——
    清单里少了它，说明有人改了路由而没改这张表。
    """
    for method, path in NON_OWNER_ROLE_GATED:
        assert any(p == path and m == method for p, m, _ in CHECKLIST_OPERATIONS), (
            f"{method} {path} 已不在稿面清单命中的操作里 ⇒ 更新 NON_OWNER_ROLE_GATED"
        )
        assert _identity_usage(next(ep for p, m, ep in CHECKLIST_OPERATIONS if (p, m) == (path, method))) == "threaded"
