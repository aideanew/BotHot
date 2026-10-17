"""STEP-22：推送域读接口的越权面与路由遮蔽（S22.1 先红 + S22.3 防复发）。

两节，分处两台机器：

- **第 1 节（本机 `@win` 就能判）**：两道**结构性**守卫——
  ① 路由面守卫：`/api/v1/bots` 下每个操作的依赖树里必须有 `require_roles`（白名单除外）；
  ② 路由遮蔽守卫：`/api/v1/bots` 下每个静态段路径，首个 FULL 匹配必须是它自己。
  这一节不需要数据库，也正是它能立刻抓住缺陷的原因（与 `test_idor_matrix.py` 同理）。
- **第 2 节（连库，`@ci` ubuntu 判，D-V4-01）**：真的用 `role=user` 的登录用户打四个读接口，
  判 403/10004 且响应体里不含播种的凭据；再用 operator 打 `GET /bots/tasks` 判 200 分页列表。

证据链（规划方在 314d7f2 上的真库读数，`docs/任务规划V0.13.0/evidence/314d7f2/`）：
`GET /api/v1/bots/{id}` 与 `GET /api/v1/bots?page_size=100` 都 **200**，且同时泄露 webhook
令牌与**解密后**的 `app_secret`；对照组 `PUT /api/v1/bots/{id}` 401（它有 `require_roles`）。
`GET /api/v1/bots/tasks` 因 `/{channel_id}` 声明在前而恒 404/30004。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.routing import Match

from app.api.deps import get_current_sub, get_db
from app.core.config import get_settings
from app.core.secret_crypto import encrypt_extra_config
from app.main import create_app
from app.models.bothot_entities import BotChannel
from app.models.entities import User

BOTS_PREFIX = "/api/v1/bots"

#: 白名单：只回渠道**类型枚举**（`registered_channels()`），不含任何实例数据与凭据。
#: 登录即可读是设计意图（前端新建渠道的下拉框要它），S22.2.3 的理由登记在 EVD。
NO_ROLE_GATE_ALLOWED: frozenset[tuple[str, str]] = frozenset({("GET", f"{BOTS_PREFIX}/channels")})

_MARKER_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/s22-marker-webhook"
_MARKER_SECRET = "s22-marker-appsecret"


# ── 1. 结构性守卫（本机可判）──────────────────────────────────────────────────


def _ordered_bots_routes() -> list[Any]:
    """按**声明顺序**摊平出 `/api/v1/bots` 下的路由对象。

    本版 FastAPI（0.143.1）的 `app.routes` 里，`include_router` 进来的是 `_IncludedRouter`
    包装对象——它自己没有 `path`。照 `for r in app.routes: r.path` 写会读出 0 条，
    守卫静默变空 = 没有守卫（`test_idor_matrix.py` 里踩过的那个实现陷阱，这里同形复用其解法）。
    """
    out: list[Any] = []

    def walk(routes: list[Any]) -> None:
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                walk(list(inner.routes))
                continue
            path = getattr(route, "path", None)
            if not path or not getattr(route, "methods", None):
                continue
            if path == BOTS_PREFIX or path.startswith(f"{BOTS_PREFIX}/"):
                out.append(route)

    walk(list(create_app().routes))
    return out


def _dep_qualnames(route: Any) -> list[str]:
    names: list[str] = []

    def walk(dependant: Any) -> None:
        for sub in dependant.dependencies:
            call = getattr(sub, "call", None)
            names.append(str(getattr(call, "__qualname__", call)))
            walk(sub)

    walk(route.dependant)
    return names


def _has_role_gate(route: Any) -> bool:
    """依赖树里有没有 `require_roles` 工厂产出的那道门。"""
    return any(name.startswith("require_roles.<locals>.") for name in _dep_qualnames(route))


def _first_full_match(method: str, path: str) -> Any:
    scope = {"type": "http", "method": method, "path": path}
    for route in _ordered_bots_routes():
        if method not in set(route.methods or ()):
            continue
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return route
    return None


def test_role_gate_predicate_itself_has_teeth() -> None:
    """先判**判据本身**，两个极性都要有。

    没有这条，下面两道守卫可以靠"恒 False 的判据 + 恒 True 的断言"双双假绿——
    本仓库为这类错付过不止一轮。

    - 正极：同一套读法在**已知有门**的写接口上必须为真（认不出已有的门 = 守卫是空的）；
    - 负极：给一个依赖树为空的假路由，必须为 **False**（判据恒真 = 第 2 节的绿没有含义）。
    """
    routes = {
        (m, r.path): _has_role_gate(r) for r in _ordered_bots_routes() for m in set(r.methods or ())
    }
    assert routes.get(("PUT", f"{BOTS_PREFIX}/{{channel_id}}")) is True, "判据认不出已有的门 ⇒ 守卫是空的"
    assert routes.get(("POST", f"{BOTS_PREFIX}/{{channel_id}}/test")) is True

    bare = type("R", (), {"dependant": type("D", (), {"dependencies": []})()})()
    assert _has_role_gate(bare) is False, "判据恒真：它在没有依赖的路由上也说'有门'"


def test_every_bots_operation_except_the_whitelist_has_a_role_gate() -> None:
    """S22.3.1：漏门的读接口逐个点名；将来新增读端点忘加门也在这里红。

    白名单只有 `GET /bots/channels`（类型枚举，无实例数据）。写接口本来就有门，
    这条把它们一起纳入检查面，是为了让"新增端点"这件事没有默认放行的口子。
    """
    offenders: list[str] = []
    for route in _ordered_bots_routes():
        for method in sorted(set(route.methods or ()) - {"HEAD", "OPTIONS"}):
            if (method, route.path) in NO_ROLE_GATE_ALLOWED:
                continue
            if not _has_role_gate(route):
                endpoint = getattr(route.endpoint, "__name__", "?")
                offenders.append(f"{method} {route.path} -> {endpoint}")
    assert not offenders, f"推送域这些操作没有角色门（普通登录用户可读明文凭据）：{offenders}"


def _static_bots_get_paths() -> list[str]:
    """从**路由表**枚举静态段 GET 路径，不是硬编码清单。

    上一版这里是写死的三条参数，第一轮验证者判它是"装饰"：将来有人新增一个静态段
    却声明在 `/{channel_id}` 之后，那条守卫根本不知道有新路由 ⇒ 永不复红。
    守卫必须随路由表长大而变长，这条卡防的才是它自己声称防的那个复发型态。
    """
    return sorted(
        {
            route.path
            for route in _ordered_bots_routes()
            if "{" not in route.path and "GET" in set(route.methods or ())
        }
    )


def test_every_static_bots_get_path_owns_its_own_match() -> None:
    """S22.3.2：每个静态段 GET 的首个 FULL 匹配必须是它自己。

    `GET /bots/tasks` 改前被 `/{channel_id}` 吃掉（恒 404/30004，
    `evidence/314d7f2/route_shadow_bots_tasks.txt`）；FastAPI 按声明顺序匹配，
    所以这条判的是文件里的排列纪律（S22.2.1 的前置）。
    """
    paths = _static_bots_get_paths()
    assert paths, "静态段枚举读空了——`app.routes` 的形状又变了，本文件的摊平假设失效"
    assert f"{BOTS_PREFIX}/tasks" in paths, "本卡修的那条必须在判据面里，否则这条守卫是空转"
    shadowed: list[str] = []
    for path in paths:
        winner = _first_full_match("GET", path)
        winner_path = getattr(winner, "path", None)
        if winner_path != path:
            handler = getattr(getattr(winner, "endpoint", None), "__name__", "?")
            shadowed.append(f"GET {path} -> 命中 {winner_path}（{handler}）")
    assert not shadowed, f"静态段被通配路由遮蔽：{shadowed}"


# ── 2. 真读一遍（连库，`@ci` 判）──────────────────────────────────────────────


async def _seed_channel(db_session: Any) -> str:
    """播一条属于**别人**的飞书渠道：webhook 带令牌、extra_config 带 app_secret。

    `extra_config` 的落法按环境分两种，但**响应侧必须是同一条泄露面**：
    - 有主密钥（`compose-smoke`/生产）：AES 密文，路由解密后回显；
    - 无主密钥（`backend` job 不生成 `PUSH_SECRET_MASTER_KEY`）：落**存量明文 JSON**，
      `decrypt_extra_config` 的兼容读（`secret_crypto.py:132-140`，`{` 开头原样返回）同样会回显。
    两种都会把 `_MARKER_SECRET` 放进响应体，所以判据不随环境放宽。
    """
    cid = str(uuid.uuid4())
    if get_settings().push_secret_master_key:
        raw = encrypt_extra_config(cid, json.dumps({"app_secret": _MARKER_SECRET}))
    else:
        raw = json.dumps({"app_secret": _MARKER_SECRET})
    db_session.add(
        BotChannel(
            id=cid,
            name="s22-owner-feishu",
            channel_type="feishu",
            webhook_url=_MARKER_WEBHOOK,
            extra_config=raw,
            status="active",
            user_id=None,
        )
    )
    await db_session.flush()
    return cid


async def _seed_user(db_session: Any, sub: str, role: str) -> User:
    user = User(sub=sub, email=f"{sub}@s22.test", nickname=sub, role=role)
    db_session.add(user)
    await db_session.flush()
    return user


def _client(db_session: Any, user: User | None) -> TestClient:
    """按 `sub` 注入身份，**让真实的授权链跑完**而不是抄近路覆写 `get_current_user_id`。

    第一轮独立验证实测出我原来的写法是错的：`bots.py:51` 在 **router 层**挂了
    `dependencies=[Depends(get_current_sub)]`，而 `get_current_user_id` 本身也依赖 `get_current_sub`
    ——只覆写 `get_current_user_id` 时，请求在进任何角色门**之前**就被登录门挡成 `401/10001`
    （`auth/service.py` 的会话校验早于任何 DB 访问），于是这里的 403 与 200 断言全都到不了判据。
    覆写 `get_current_sub` 才是这条链的入口：`sub → users 行 → has_min_rank`，
    与生产同路径，也顺带证明 P-21 担心的"口径不同源"没发生在后端。
    """
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    if user is not None:
        app.dependency_overrides[get_current_sub] = lambda: user.sub
    return TestClient(app)


async def test_plain_user_cannot_read_any_bots_endpoint(
    db_session: Any,
) -> None:  # type: ignore[no-untyped-def]
    """S22.1.1 的正体：`role=user` 打四个读接口一律 403/10004，且响应体不含任何凭据。

    改前读数是 200 + 两支都漏（`evidence/314d7f2/probe_bots_read_by_plain_user.txt`）。
    这里覆盖 `GET /bots`、`GET /bots/{id}`、`GET /bots/{id}/logs`、`GET /bots/tasks` 四个面，
    以及对照组 `PUT /bots/{id}`（本来就有门，判它没被这次改动弄坏）。
    """
    cid = await _seed_channel(db_session)
    plain = await _seed_user(db_session, "s22-plain", "user")
    client = _client(db_session, plain)

    for path in (f"{BOTS_PREFIX}?page_size=100", f"{BOTS_PREFIX}/{cid}", f"{BOTS_PREFIX}/{cid}/logs"):
        resp = client.get(path)
        body = resp.json()
        assert resp.status_code == 403, f"{path} 实得 {resp.status_code}/{body.get('code')}"
        assert body.get("code") == 10004, f"{path} 错误码应为 10004：{body}"
        text = json.dumps(body, ensure_ascii=False)
        assert _MARKER_WEBHOOK not in text, f"{path} 仍回显 webhook 令牌"
        assert _MARKER_SECRET not in text, f"{path} 仍回显 app_secret"

    put = client.put(f"{BOTS_PREFIX}/{cid}", json={"name": "x"})
    assert put.status_code == 403 and put.json()["code"] == 10004, put.json()


async def test_operator_reads_the_task_list_and_the_channel_detail(
    db_session: Any,
) -> None:  # type: ignore[no-untyped-def]
    """S22.1.1 的另一半：operator 放行，且 `GET /bots/tasks` **不再 404**。

    只判 403 会把"整片 403"也当成修好了——这条是同一枚判据的另一极：
    路由前置之后 `/tasks` 必须命中 `list_push_tasks` 并回分页壳。
    """
    cid = await _seed_channel(db_session)
    op = await _seed_user(db_session, "s22-op", "operator")
    client = _client(db_session, op)

    detail = client.get(f"{BOTS_PREFIX}/{cid}")
    assert detail.status_code == 200 and detail.json()["code"] == 0, detail.json()
    assert detail.json()["data"]["id"] == cid
    # **正控**（第一轮验证者指出缺它就没有这条判据）：普通用户那条"响应体不含凭据"是恒真的，
    # 除非同一份数据在放行者眼里**确实**含凭据。没有这两行，"403 且看不到密钥"可以只因
    # 为响应体是个空壳而通过——那正是"泄露已封堵"与"接口压根没返回数据"读成同一个绿。
    detail_text = json.dumps(detail.json(), ensure_ascii=False)
    assert _MARKER_WEBHOOK in detail_text, "operator 眼里 webhook 令牌必须可见，否则负控没有对照物"
    assert _MARKER_SECRET in detail_text, "operator 眼里 app_secret 必须可见（S2.1 的回显语义）"

    listing = client.get(f"{BOTS_PREFIX}/tasks")
    assert listing.status_code == 200, f"GET /bots/tasks 实得 {listing.status_code}：{listing.json()}"
    data = listing.json()["data"]
    assert isinstance(data.get("items"), list), f"分页壳缺失：{data}"


async def test_anonymous_still_gets_401_on_the_read_surface(db_session: Any) -> None:
    """三门之外的一门：没登录仍是 10001/401，不许被角色门改成 403。

    顺序判据（先认证后授权）如果写反，未登录会先撞 10004——那会把"没登录"说成"没权限"，
    前端据此把用户困在无权页。
    """
    await _seed_channel(db_session)
    resp = _client(db_session, None).get(BOTS_PREFIX)
    assert resp.status_code == 401 and resp.json()["code"] == 10001, resp.json()


async def test_channel_types_stays_readable_for_a_plain_user(db_session: Any) -> None:
    """白名单必须是**白**的：`GET /bots/channels` 只回类型枚举，普通用户仍要能读。

    这条守着 S22.2.3 的例外本身——顺手给整片加门会把前端新建渠道的下拉框打死。
    """
    plain = await _seed_user(db_session, "s22-plain2", "user")
    resp = _client(db_session, plain).get(f"{BOTS_PREFIX}/channels")
    assert resp.status_code == 200 and resp.json()["code"] == 0, resp.json()
    body_text = json.dumps(resp.json(), ensure_ascii=False)
    assert _MARKER_WEBHOOK not in body_text and _MARKER_SECRET not in body_text


async def test_seeded_channel_row_is_cleaned_up_by_the_fixture(db_session: Any) -> None:
    """夹具纪律：播种行必须随外层事务回滚，不给下一个用例留脏渠道。

    判法用计数而不是"看不见"：同一会话里刚播的行 flush 后可查，
    而 `select` 出来的条数正好是 1，说明本文件的四条用例各播各的、互不复用。
    """
    await _seed_channel(db_session)
    rows = (await db_session.scalars(select(BotChannel).where(BotChannel.webhook_url == _MARKER_WEBHOOK))).all()
    assert len(rows) == 1, f"同一条标记 webhook 应当只有本用例那一行，实得 {len(rows)}"
