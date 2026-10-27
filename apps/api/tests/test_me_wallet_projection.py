"""STEP-57：`/auth/me` 的钱包只吐白名单五键（P-121，裁决 D-V21-17 取代 D-V21-09）。

先红那条判的是「上游多给一个键，我们就原样转出去」。风险面在于这件事在改前**任何一道门都不会红**：
当时契约侧还是开放对象（`shapes.py` 里那行 `extra="allow"`，规划方 2026-10-27 在 P-129 三条出路里
选定本卡只发投影那一半），而主平台加字段不需要通知我们 ⇒ STEP-57 断的是泄露这条腿。
判形那条腿由 **STEP-61** 补上（D-V21-21 留下的另一半、D-V22-05 的落笔方式）：`MeWallet` 现已封闭，
两侧的同步关系由本文件末尾的 `test_degraded_shape_and_contract_agree_on_the_five_keys` 钉住。
"""

from __future__ import annotations

import structlog.testing
from test_auth import _client_with, _login_state, _svc_bundle

from app.contracts.shapes import MeWallet
from app.services.auth.service import _WALLET_KEYS, _WALLET_UNAVAILABLE, _project_wallet

#: 卡面 S57.2 的白名单，就这五个。唯一源在 `app/services/auth/service.py` 的 `_WALLET_KEYS`，
#: 本文件只用来判「响应里不许出现白名单之外的键」，不重复实现投影逻辑（抄一份就是第二个真源）。
WALLET_KEYS = frozenset({"balanceYuan", "currency", "heldYuan", "availableYuan", "available"})
#: 降级形（与 `/me` 的 fixture 分支、主平台不可达分支同形，同源于 `_WALLET_UNAVAILABLE`）。
DEGRADED = {"balanceYuan": 0, "currency": "CNY", "available": False}


def _me_wallet(wallet_extra: dict[str, object]) -> dict[str, object]:
    """走完整登录链拿 `/auth/me` 的 `data.wallet`（内存桩，不连库）。"""
    svc, idp, _, _ = _svc_bundle(wallet_extra=wallet_extra)
    client = _client_with(svc)
    state = _login_state(client)
    callback = client.get(f"/api/v1/auth/callback?code={idp.issue_code()}&state={state}")
    assert callback.status_code == 200, callback.text
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["wallet"]


# ── S57.1 先红：契约外键不许从上游走到我们的响应 ──────────────────────────────


def test_upstream_wallet_cannot_add_a_key_to_our_response() -> None:
    """上游多吐一个键 ⇒ 我们的响应里不许出现它（改前红，红的正是透传本身）。

    取一个「主平台风控才会有的内部字段名」而不是一个看起来像余额的键名：这条用例要判的是
    「我们没声明过的东西不往外走」，键名越不像业务字段，越不会被读成"这个本来就该给"。
    """
    wallet = _me_wallet({"internalNote": "主平台内部风控备注，不该出现在我们的响应里"})
    assert "internalNote" not in wallet, f"钱包透传未过滤，响应带出契约外键：{sorted(wallet)}"
    assert set(wallet) <= WALLET_KEYS, f"响应里的键超出白名单五键：{sorted(set(wallet) - WALLET_KEYS)}"
    # 过滤不等于丢业务键：既有的四个键必须照旧在（先红那次响应是五键齐全，改后不许少给）
    for key in ("balanceYuan", "heldYuan", "availableYuan", "currency"):
        assert key in wallet, f"投影把上游真给的 {key} 一起丢了：{sorted(wallet)}"


# ── S57.2 纯函数四例（卡面验收②）+ 两条降级 ──────────────────────────────────


def test_projection_keeps_all_five_keys() -> None:
    raw = {
        "balanceYuan": "12.34",
        "currency": "CNY",
        "heldYuan": "2.00",
        "availableYuan": "10.34",
        "available": True,
    }
    assert _project_wallet(raw) == raw


def test_projection_leaves_absent_optional_keys_absent() -> None:
    """只给必填两键 ⇒ 输出就只有这两键。

    这一条钉的是「不补 0」：`heldYuan`/`availableYuan` 在契约里有默认值，那只是让键可选，
    不代表后端可以替上游造一个 0 出去——前端对「0 元」与「余额暂不可查」给的是两种文案。
    """
    assert _project_wallet({"balanceYuan": "5.00", "currency": "USD"}) == {
        "balanceYuan": "5.00",
        "currency": "USD",
    }


def test_projection_drops_unknown_keys_and_logs_only_their_names() -> None:
    raw = {"balanceYuan": "1.00", "currency": "CNY", "internalNote": "风控内部值，不该进日志"}
    with structlog.testing.capture_logs() as events:
        out = _project_wallet(raw)
    assert out == {"balanceYuan": "1.00", "currency": "CNY"}
    logged = [e for e in events if "契约外键" in str(e.get("event"))]
    assert len(logged) == 1, f"多余键名应当恰好记一次（每次投影记一次，不做进程级去重），实得 {len(logged)} 条"
    assert logged[0]["keys"] == ["internalNote"], logged[0]
    assert logged[0]["log_level"] == "debug", f"不该抬到 info 以上污染生产日志：{logged[0]['log_level']}"
    # 判**整批事件**而不是那一条：值从别的字段（或将来别处的一条日志）漏出去同样是漏
    assert "风控内部值" not in str(events), "上游给的值不许出现在任何一条日志里"


def test_projection_degrades_when_a_required_key_is_missing_or_null() -> None:
    """缺 `balanceYuan` ⇒ 回降级形，不抛 500（会话已建立，不能让登录成功的人整页失败）。

    `null` 也算缺：键在但值是 `null` 时，只判 `key in raw` 会把它当合法放行，而信封层
    （`core/response.py` 的 `success(data=...)`）不做形状校验——那种值会一路走到契约之外。
    """
    assert _project_wallet({"currency": "CNY", "heldYuan": "1.00"}) == DEGRADED
    assert _project_wallet({"balanceYuan": "1.00"}) == DEGRADED
    assert _project_wallet({"balanceYuan": None, "currency": "CNY"}) == DEGRADED
    with structlog.testing.capture_logs() as events:
        _project_wallet({"balanceYuan": None, "currency": "CNY"})
    cause = [e for e in events if "缺必填键" in str(e.get("event"))]
    assert len(cause) == 1 and cause[0]["missing"] == ["balanceYuan"], f"降级得报对原因：{cause}"


def test_projection_degrades_on_a_non_dict_payload() -> None:
    """上游把 wallet 发成列表/字符串/数字也不崩——降级形是唯一出口。

    这里只喂**非字典**；"是字典但缺必填键"是上一条的口径，两条各自判一条出口，
    不然一条红了你不知道是哪条腿断的。
    """
    for bad in (None, [], "", 0, 1.5, True):
        assert _project_wallet(bad) == DEGRADED, bad


def test_projection_survives_mixed_key_types() -> None:
    """纯函数会被直接喂字典：混合键型排不了序就是 TypeError，而承诺是"不抛 500"。"""
    raw: dict[object, object] = {1: "内部值", "balanceYuan": "1.00", "currency": "CNY"}
    with structlog.testing.capture_logs() as events:
        out = _project_wallet(raw)
    assert out == {"balanceYuan": "1.00", "currency": "CNY"}
    assert [e for e in events if "契约外键" in str(e.get("event"))][0]["keys"] == ["1"], events


def test_projection_copies_the_degraded_shape_instead_of_sharing_it() -> None:
    """降级形每次给新字典：调用方改了返回值不该污染下一个人的响应。"""
    first = _project_wallet({"currency": "CNY"})
    first["balanceYuan"] = "篡改"
    assert _project_wallet({"currency": "CNY"}) == DEGRADED


def test_degraded_shape_and_contract_agree_on_the_five_keys() -> None:
    """STEP-61 验收④：投影侧白名单、降级形、契约发布的键三者同源，谁漂了谁红。

    只判「降级形 ⊆ 五键」不够——那是卡面判据的下半；契约若少发一个键，前端照契约写就会读不到
    我们其实会吐的字段，所以两边都必须正好是这五个。`extra` 这一条钉的是"开放没被谁悄悄改回去"。
    """
    assert set(_WALLET_UNAVAILABLE) <= set(_WALLET_KEYS), "降级形含白名单外的键 ⇒ 先改 service 再谈契约"
    assert set(_WALLET_KEYS) == set(WALLET_KEYS), "投影白名单与本文件登记的五个键不一致"
    assert set(MeWallet.model_fields) == set(WALLET_KEYS), "契约发布的键集合与投影白名单不一致"
    assert MeWallet.model_config.get("extra") == "forbid", "MeWallet 又变回开放对象了"
