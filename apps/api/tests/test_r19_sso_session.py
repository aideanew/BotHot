"""STEP-19 S19.1.4：登出后**旧 Cookie 重放**与 backchannel 的授权面（REQ-F-007）。

卡面命题："登出后服务端会话是否真失效？backchannel-logout 是否有可达消费方？"
本仓已有的 `test_auth.py::test_logout_revokes_chain_and_clears_session` 登出后再访问 `/me` 得 401/10001，
但它走的是 `TestClient` 的**CookieJar**：logout 的 `Set-Cookie` 会把 jar 里的会话值清掉，
所以那一次访问是"不带 cookie"，不是"带着已经作废的那枚 cookie"。两者只在同一处判得出来——
服务端如果只信 cookie、不查会话存储，"不带"照样 401，而"带旧值"会被放行。
本文件的第一条就是补这一格：**显式重放旧 cookie 值**。

第二条判 backchannel-logout 的授权面：它是服务间端点，凭 `logout_token` 验签授权，
一个普通登录用户的 cookie **不该**是它的通行证——不带 token 只带 cookie 时，
响应仍是恒 200 同形（不向主平台泄露校验差异），但**该用户的会话必须还活着**。
"200 且没删东西"两半都要判：只判 200 的话，一个"照删不误"的实现也绿。

伪 IdP 与装配直接复用 `tests/test_auth.py`（改名那张文件会连带打断本文件——这是有意的耦合，
判据口径必须和那张卡一致；分叉点在"重放旧 cookie"这一处）。
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from test_auth import _client_with, _login_state, _svc_bundle  # 复用同一套伪 IdP 装配（见模块 docstring）

BACKCHANNEL = "/api/v1/auth/backchannel-logout"


def _logged_in() -> tuple[TestClient, str, Any]:
    """跑完一次真授权码流，返回 (client, 服务端会话 cookie 值, 服务)。"""
    svc, idp, _users, sessions = _svc_bundle()
    client = _client_with(svc)
    state = _login_state(client)
    callback = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert callback.status_code == 200 and callback.json()["code"] == 0
    sid = callback.cookies["bothot_session"]
    assert sid and sid in sessions._sessions  # 前提：服务端确有这条会话
    return client, sid, svc


def test_a_replayed_old_cookie_is_rejected_after_logout() -> None:
    """S19.1.4 的正体：登出后把**同一枚旧 cookie 值**再发一次 → 401 / 10001。

    判"带旧值"而不是"不带值"：后者 `test_me_without_session_returns_10001` 已经判过，
    重复它不会抓到任何新缺陷。
    """
    client, sid, _svc = _logged_in()
    assert client.get("/api/v1/auth/me").status_code == 200  # 前提：登出前这枚 cookie 是有效的

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 200 and logout.json()["data"]["logged_out"] is True

    replay = client.get("/api/v1/auth/me", cookies={"bothot_session": sid})
    assert replay.status_code == 401, f"旧 cookie 重放被放行（{replay.status_code}）⇒ 服务端会话没有真失效"
    assert replay.json()["code"] == 10001, f"重放拿到了别的信封码：{replay.json().get('code')}"


def test_backchannel_logout_without_a_token_keeps_the_user_session_alive() -> None:
    """普通用户的 cookie 不是 backchannel 的通行证：恒 200 同形，但会话必须还在。"""
    client, _sid, _svc = _logged_in()
    assert client.get("/api/v1/auth/me").status_code == 200

    resp = client.post(BACKCHANNEL, data={"logout_token": ""})
    assert resp.status_code == 200, "端点不该用 4xx 区分校验结果（不向主平台泄露差异）"
    assert resp.json()["code"] == 0, f"同形信封被破坏：{resp.json()}"

    after = client.get("/api/v1/auth/me")
    assert after.status_code == 200, "空 logout_token 却把带着 cookie 的用户会话删了（授权面失守）"


def test_backchannel_logout_from_an_unrelated_body_deletes_no_session() -> None:
    """畸形体（不是 form、或带一个签不出来的串）同样"200 + 零删除"——把上一条的极性坐实。

    只判空串的话，"任何请求体都当作合法"的实现也能绿；这里给一枚形状合法但签名错误的 JWT。
    """
    client, _sid, _svc = _logged_in()
    forged = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImsxIn0.eyJpc3MiOiJ4Iiwic3ViIjoieSJ9.c2lnLW5vdC12YWxpZA"
    resp = client.post(BACKCHANNEL, data={"logout_token": forged})
    assert resp.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200, "验签失败的 token 也导致了删除"


def test_the_backchannel_route_is_reachable_on_the_app() -> None:
    """"是否有可达消费方"的最便宜判据：路由真的挂在 app 上（不是只有服务层函数）。

    服务层 `handle_backchannel_logout` 早就被 `test_backchannel_*` 判过；
    没有这一条，"主平台能打到这个端点"这件事其实没人证明过。

    形状陷阱（与 `test_idor_matrix.py` / `test_bots_read_authz.py` 同一处）：本版 FastAPI 的
    `app.routes` 里 `include_router` 进来的是 `_IncludedRouter` 包装对象，它自己**没有** `path`，
    照 `for r in app.routes: r.path` 写会读出 0 条 ⇒ 必须先摊平再判。
    """
    from fastapi.routing import APIRoute

    from app.main import create_app

    def walk(routes: list[Any], prefix: str = "") -> set[str]:
        found: set[str] = set()
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                found |= walk(
                    list(inner.routes), prefix + (getattr(route, "path", "") or getattr(route, "prefix", "") or "")
                )
            elif isinstance(route, APIRoute):
                found.add(prefix + route.path)
        return found

    paths = walk(list(create_app().routes))
    assert paths, "摊平后一条路由都没读到——`app.routes` 的形状又变了，本判据的来源已消失"
    assert BACKCHANNEL in paths, f"backchannel 端点没挂上：{sorted(p for p in paths if 'auth' in p)}"
