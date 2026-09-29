"""SPEC-M3 批次 3 / T5.4（2026-09-23）验收测试：引擎 Key 登记表（AES-256-GCM 落库）。

四层覆盖：
- 加密层：AES-GCM 往返、AAD 绑定（密文不可在引擎位间搬移）、主密钥缺失/畸形拒绝；
- 谓词层：main 需 base **且** key（锁定历史 bug——engines.py 曾只查 base，与
  EngineRouter 的 base-且-key 判定结论相反，两份拷贝对同一份数据给出两个答案）；
  登记表 > env 的优先级与 activeSource 显式回报；
- 服务层：密文落库（零明文）、upsert 轮换 key_id、撤销、解密失败不被静默丢弃；
- 路由层：operator+ 门禁（user 拒绝）、无主密钥 50002、builtin/未知位 10005。

不覆盖：真实引擎实接（ENGINE_IMPLEMENTED 全 False，锁 D10）——登记表当前只影响
状态上报与切换前置校验，不影响实际入库链路。
"""

from __future__ import annotations

import base64
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_db
from app.api.v1.engines import _engine_status
from app.core.config import get_settings
from app.core.engine_keyring import (
    KEYABLE_ENGINES,
    decrypt_secret,
    encrypt_secret,
    master_key,
    resolve_engine_key,
    set_snapshot,
)
from app.core.errors import DependencyUnavailableError, RequestInvalidError
from app.main import create_app
from app.models.entities import User
from app.providers.engine_port import ENGINE_ORDER, EngineRouter
from app.services.engine_keys import EngineKeyService

# 32 字节主密钥的 base64（AES-256）
_MASTER_B64 = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()

# 端点用例前置清空的环境变量（隔离 backend/.env 占位值，与 test_p4_engines 同惯例）
_ENGINE_ENV_KEYS = ["COZE_API_KEY", "DIFY_API_KEY", "FASTGPT_API_KEY", "MAIN_KB_API_KEY", "MAIN_KB_API_BASE"]


@pytest.fixture(autouse=True)
def _isolate_engine_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认无引擎 Key、无主密钥；用例自行 set_master_key 注入。

    get_settings 带 lru_cache，改 env 后必须 cache_clear 才生效。
    快照为进程级全局，用例间清空防泄漏。
    """
    for key in _ENGINE_ENV_KEYS:
        monkeypatch.setenv(key, "")
    monkeypatch.delenv("ENGINE_KEY_MASTER_KEY", raising=False)
    get_settings.cache_clear()
    set_snapshot({})
    yield
    set_snapshot({})
    get_settings.cache_clear()


def set_master_key(monkeypatch: pytest.MonkeyPatch, b64: str = _MASTER_B64) -> None:
    monkeypatch.setenv("ENGINE_KEY_MASTER_KEY", b64)
    get_settings.cache_clear()


class _S:
    """Settings 替身：只暴露谓词需要的字段。"""

    kb_engine_allowlist = "builtin"

    def __init__(
        self,
        base: str = "",
        main_key: str = "",
        coze_key: str = "",
        dify_key: str = "",
        fastgpt_key: str = "",
    ) -> None:
        self.main_kb_api_base = base
        self.main_kb_api_key = main_key
        self.coze_api_key = coze_key
        self.dify_api_key = dify_key
        self.fastgpt_api_key = fastgpt_key


# 加密层单测直接用裸 32 字节主密钥，不经 config（与配置解析解耦）
_KEY = b"0123456789abcdef0123456789abcdef"


# ------------------------------------------------------------------ ① 加密层


def test_encrypt_decrypt_round_trip() -> None:
    assert len(_KEY) == 32  # AES-256
    ct = encrypt_secret("coze", "sk-live-abc123", _KEY)
    assert decrypt_secret("coze", ct, _KEY) == "sk-live-abc123"
    # 明文不得出现在密文里（落库零明文的前提）
    assert "sk-live-abc123" not in ct
    # 两段式 wire：b64(nonce).b64(ct+tag)
    assert ct.count(".") == 1


def test_each_call_uses_fresh_nonce() -> None:
    """每次加密新 nonce：同一明文两次密文不同（GCM nonce 复用会泄露，必须防）。"""
    assert encrypt_secret("coze", "same-key", _KEY) != encrypt_secret("coze", "same-key", _KEY)


def test_aad_binds_ciphertext_to_engine() -> None:
    """AAD=引擎名：coze 的密文挪到 dify 行解密必须失败（不静默读错 Key）。"""
    ct = encrypt_secret("coze", "sk-real-key", _KEY)
    with pytest.raises(RequestInvalidError, match="不可解"):
        decrypt_secret("dify", ct, _KEY)


def test_empty_plaintext_refused() -> None:
    with pytest.raises(RequestInvalidError, match="不能为空"):
        encrypt_secret("coze", "", _KEY)


def test_master_key_absent_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """主密钥缺失 → 50002 并指明 env 变量名；**绝不回落明文**。"""
    get_settings.cache_clear()
    with pytest.raises(DependencyUnavailableError, match="ENGINE_KEY_MASTER_KEY"):
        master_key()


def test_master_key_wrong_length_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    set_master_key(monkeypatch, base64.b64encode(b"short").decode())
    with pytest.raises(DependencyUnavailableError, match="32 字节"):
        master_key()


def test_master_key_invalid_base64_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    """畸形 base64 也拒：静默按截断处理会把「配置错了」伪装成「配置对了」。"""
    set_master_key(monkeypatch, "not:valid:base64!!!")
    with pytest.raises(DependencyUnavailableError, match="base64"):
        master_key()


# ------------------------------------------------------------------ ② 谓词层


def test_main_requires_base_and_key() -> None:
    """历史 bug 锁：main 只有 base 无 key 时**不可**判为已配置。

    engines.py 曾只查 main_kb_api_base（忽略 key），engine_port.EngineRouter 查
    base 且 key——同一份数据两个谓词给出相反结论。现两份已收敛到
    resolve_engine_key，本用例锁「base-only → 未配置」这个此前无人覆盖的分支。
    """
    base_only = _S(base="http://main-kb:8001")
    assert resolve_engine_key("main", base_only).configured is False
    assert resolve_engine_key("main", base_only).source is None

    key_only = _S(main_key="sk-main-1")
    assert resolve_engine_key("main", key_only).configured is False

    both = _S(base="http://main-kb:8001", main_key="sk-main-1")
    res = resolve_engine_key("main", both)
    assert res.configured is True and res.source == "env" and res.key == "sk-main-1"


def test_registered_wins_over_env_and_is_reported() -> None:
    """登记表优先于 env，且 activeSource 显式回报——覆盖不静默（F-4 教训）。

    用 coze（只需 Key 的位）；main 另需 base，见 test_main_requires_base_and_key。
    """
    settings = _S(coze_key="sk-env-value")
    assert resolve_engine_key("coze", settings).source == "env"

    res = resolve_engine_key("coze", settings, {"coze": "sk-registered-value"})
    assert res.configured is True
    assert res.source == "registered"
    assert res.key == "sk-registered-value"  # 实际生效的是登记值


def test_registered_wins_for_main_with_base() -> None:
    """main 也遵循同一优先级：base 来自 env，Key 来自登记表。"""
    settings = _S(base="http://main-kb:8001", main_key="sk-env-main")
    assert resolve_engine_key("main", settings).source == "env"

    res = resolve_engine_key("main", settings, {"main": "sk-reg-main"})
    assert res.configured is True and res.source == "registered"
    assert res.key == "sk-reg-main"


def test_registered_empty_falls_back_to_env() -> None:
    """登记表空值不算覆盖：回落 env 并如实标注 env。"""
    res = resolve_engine_key("coze", _S(coze_key="sk-env"), {"coze": ""})
    assert res.configured is True and res.source == "env"


def test_builtin_never_needs_key() -> None:
    """builtin 是回退通道：无 Key、恒已配置、source 恒 None（不被登记表/env 判定）。"""
    res = resolve_engine_key("builtin", _S())
    assert res.configured is True and res.source is None and res.env_var == ""


def test_unknown_engine_never_invented() -> None:
    """未知引擎位不臆造凭据（交由调用方走 10005 校验）。"""
    assert resolve_engine_key("notion", _S()).configured is False


def test_engine_router_configured_agrees_with_predicate_on_main() -> None:
    """收敛验收：EngineRouter.configured 与 GET /engines 的 _engine_status 在
    base-only 与 base+key 两个分支上必须同结论（R0.3.2 既有不变式未覆盖 base-only）。
    """
    for settings in (_S(base="http://main-kb:8001"), _S(base="http://main-kb:8001", main_key="sk-1")):
        assert resolve_engine_key("main", settings).configured is EngineRouter(
            settings=settings
        ).configured("main")
        assert resolve_engine_key("main", settings).configured is bool(
            _engine_status("main", settings)["configured"]
        )


def test_all_slots_two_predicates_agree() -> None:
    """遍历 5 引擎位 × 两组配置：两份判定全等（防未来新增引擎位时再次漂移）。"""
    configs = [_S(), _S(base="http://b", main_key="k", coze_key="k", dify_key="k", fastgpt_key="k")]
    for settings in configs:
        router = EngineRouter(settings=settings)
        for engine in ENGINE_ORDER:
            expected = resolve_engine_key(engine, settings).configured
            assert router.configured(engine) is expected, f"{engine}: router 与谓词分歧"
            assert bool(_engine_status(engine, settings)["configured"]) is expected


def test_key_env_reports_real_env_var_name() -> None:
    """keyEnv 指向真实 env 变量名（此前给的是 settings 字段名，前端契约本就要大写）。"""
    assert resolve_engine_key("main", _S()).env_var == "MAIN_KB_API_KEY"
    assert resolve_engine_key("coze", _S()).env_var == "COZE_API_KEY"
    assert KEYABLE_ENGINES == ("main", "coze", "dify", "fastgpt")


# ------------------------------------------------------------------ ③ 服务层


async def _seed_operator(db_session: Any) -> str:
    """建一个真实 operator 用户（registered_by 有 FK，必须指向 users 行）。"""
    op = User(sub="r11-key-op-svc", email="r11-key-op-svc@r11.test", nickname="op", role="operator")
    db_session.add(op)
    await db_session.flush()
    return op.id


async def test_register_persists_ciphertext_not_plaintext(
    db_session, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from app.models.entities import EngineKeyRegistration

    set_master_key(monkeypatch)
    op = await _seed_operator(db_session)
    svc = EngineKeyService(db_session)
    res = await svc.register(op, "coze", "sk-live-secret-99")
    assert res["engine"] == "coze" and res["keyId"]

    row = await db_session.get(EngineKeyRegistration, "coze")
    assert row is not None
    assert row.secret_ref != "sk-live-secret-99"          # 零明文落库
    assert "sk-live-secret-99" not in row.secret_ref
    assert row.registered_by == op
    # 解密回来才是真值
    assert decrypt_secret("coze", row.secret_ref, master_key()) == "sk-live-secret-99"

    loaded = await svc.load()
    assert loaded.plaintext == {"coze": "sk-live-secret-99"}
    assert loaded.decrypt_bad == {}
    assert loaded.rows[0]["engine"] == "coze" and loaded.rows[0]["keyId"] == res["keyId"]


async def test_register_rejects_builtin_and_unknown(db_session) -> None:  # type: ignore[no-untyped-def]
    svc = EngineKeyService(db_session)
    with pytest.raises(RequestInvalidError, match="内置引擎"):
        await svc.register("op-1", "builtin", "x")
    with pytest.raises(RequestInvalidError, match="未知引擎位"):
        await svc.register("op-1", "notion", "x")


async def test_register_rejects_blank_and_control_chars(db_session) -> None:  # type: ignore[no-untyped-def]
    svc = EngineKeyService(db_session)
    with pytest.raises(RequestInvalidError, match="不能为空"):
        await svc.register("op-1", "coze", "")
    with pytest.raises(RequestInvalidError, match="不能为空"):
        await svc.register("op-1", "coze", "   ")  # strip 后为空
    with pytest.raises(RequestInvalidError, match="控制字符"):
        await svc.register("op-1", "coze", "sk\x00bad")


async def test_register_without_master_key_refuses_and_writes_nothing(
    db_session, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """无主密钥 → 50002 拒绝，且不落任何行（绝不回落明文）。"""
    svc = EngineKeyService(db_session)
    with pytest.raises(DependencyUnavailableError, match="ENGINE_KEY_MASTER_KEY"):
        await svc.register("op-1", "coze", "sk-live")
    assert (await svc.load()).rows == []


async def test_register_overwrites_and_rotates_key_id(
    db_session, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    set_master_key(monkeypatch)
    op1 = await _seed_operator(db_session)
    op2 = User(sub="r11-key-op2-svc", email="r11-key-op2-svc@r11.test", nickname="op2", role="operator")
    db_session.add(op2)
    await db_session.flush()
    svc = EngineKeyService(db_session)
    first = await svc.register(op1, "coze", "sk-old")
    second = await svc.register(op2.id, "coze", "sk-new")
    assert first["keyId"] != second["keyId"]

    loaded = await svc.load()
    assert len(loaded.rows) == 1                       # 一行一引擎位，不并排多版本
    assert loaded.plaintext["coze"] == "sk-new"        # 生效的是新值
    assert loaded.rows[0]["keyId"] == second["keyId"]
    assert loaded.rows[0]["registeredBy"] == op2.id


async def test_revoke_deletes_and_absent_revoke_is_404(
    db_session, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """撤销后回落 env；重复撤销无登记行 → 30004（不谎报已撤销）。"""
    from app.core.errors import ResourceNotFoundError

    set_master_key(monkeypatch)
    svc = EngineKeyService(db_session)
    op = await _seed_operator(db_session)
    await svc.register(op, "coze", "sk-x")
    res = await svc.revoke(op, "coze")
    assert res == {"engine": "coze", "revoked": True}
    assert (await svc.load()).rows == []

    with pytest.raises(ResourceNotFoundError, match="无登记 Key"):
        await svc.revoke(op, "coze")


async def test_load_flags_decrypt_failure_instead_of_dropping_it(
    db_session, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """密文损坏（或主密钥轮换）→ 该行不计入可用集，但必须被标注。

    静默当「未配置」会让操作者以为登记丢了——F-4 教训。
    """
    from app.models.entities import EngineKeyRegistration

    set_master_key(monkeypatch)
    svc = EngineKeyService(db_session)
    await svc.register(await _seed_operator(db_session), "coze", "sk-real")

    row = await db_session.get(EngineKeyRegistration, "coze")
    assert row is not None
    row.secret_ref = "tampered.nonsense"
    await db_session.commit()

    loaded = await svc.load()
    assert loaded.plaintext == {}
    assert set(loaded.decrypt_bad) == {"coze"}
    assert "不可解" in loaded.decrypt_bad["coze"]
    assert loaded.rows[0]["engine"] == "coze"  # 行仍在，只是不可用


async def test_load_without_master_key_flags_all_rows(
    db_session, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """主密钥未配置且已有登记行 → 全部行显式标注不可读，不静默当未配置。"""
    set_master_key(monkeypatch)
    svc = EngineKeyService(db_session)
    await svc.register(await _seed_operator(db_session), "coze", "sk-1")

    # 撤掉主密钥（模拟漏配或轮换后未同步）
    monkeypatch.delenv("ENGINE_KEY_MASTER_KEY", raising=False)
    get_settings.cache_clear()

    loaded = await svc.load()
    assert loaded.plaintext == {}
    assert set(loaded.decrypt_bad) == {"coze"}
    assert "ENGINE_KEY_MASTER_KEY" in loaded.decrypt_bad["coze"]


# ------------------------------------------------------------------ ④ 路由层


def _app(db_session: Any, actor_id: str) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_current_user_id] = lambda: actor_id
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


async def _seed_roles(db_session) -> dict[str, str]:
    """三个角色账号（无自有空间，专供门禁用例）。"""
    user = User(sub="r11-key-user", email="r11-key-user@r11.test", nickname="user")
    operator = User(sub="r11-key-op", email="r11-key-op@r11.test", nickname="op", role="operator")
    admin = User(sub="r11-key-admin", email="r11-key-admin@r11.test", nickname="admin", role="admin")
    db_session.add_all([user, operator, admin])
    await db_session.flush()
    return {"user": user.id, "operator": operator.id, "admin": admin.id}


async def test_admin_engine_keys_gate_operator_and_above(db_session) -> None:  # type: ignore[no-untyped-def]
    """operator+ 门禁：admin 经单调秩覆盖 operator（require_role 取 max rank）。"""
    rows = await _seed_roles(db_session)

    resp = _app(db_session, rows["user"]).get("/api/v1/admin/engines/keys")
    assert resp.status_code == 403 and resp.json()["code"] == 10004

    resp = _app(db_session, rows["operator"]).get("/api/v1/admin/engines/keys")
    assert resp.status_code == 200 and resp.json()["code"] == 0
    data = resp.json()["data"]
    assert data["masterKeyConfigured"] is False  # 本用例未注入主密钥
    assert [i["engine"] for i in data["items"]] == list(KEYABLE_ENGINES)
    for item in data["items"]:
        assert item["registered"] is False and item["keyId"] == "" and item["decryptFailed"] is False

    resp = _app(db_session, rows["admin"]).get("/api/v1/admin/engines/keys")
    assert resp.status_code == 200  # admin 覆盖 operator


async def test_admin_register_list_and_revoke_lifecycle(db_session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    set_master_key(monkeypatch)
    rows = await _seed_roles(db_session)
    client = _app(db_session, rows["operator"])

    # env 也配了同名 Key → 登记后 activeSource 必须从 env 翻到 registered
    monkeypatch.setenv("COZE_API_KEY", "sk-env-side")
    get_settings.cache_clear()
    before = client.get("/api/v1/admin/engines/keys").json()["data"]["items"]
    coze_before = next(i for i in before if i["engine"] == "coze")
    assert coze_before["configured"] is True and coze_before["activeSource"] == "env"
    assert coze_before["envConfigured"] is True

    resp = client.post("/api/v1/admin/engines/keys/coze", json={"key": "sk-registered-side"})
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["ok"] is True and body["engine"] == "coze" and body["keyId"]
    assert "sk-registered-side" not in resp.text  # 明文不回显

    after = client.get("/api/v1/admin/engines/keys").json()["data"]
    assert after["masterKeyConfigured"] is True
    coze = next(i for i in after["items"] if i["engine"] == "coze")
    assert coze["registered"] is True and coze["activeSource"] == "registered"
    assert coze["envConfigured"] is True and coze["keyId"] == body["keyId"]
    assert coze["registeredBy"] == rows["operator"]
    assert coze["updatedAt"]  # 登记时间可见（审计）

    # 撤销后回落 env（envConfigured 仍为真 → configured 仍为真，来源变回 env）
    resp = client.delete("/api/v1/admin/engines/keys/coze")
    assert resp.status_code == 200 and resp.json()["data"] == {
        "ok": True, "engine": "coze", "revoked": True
    }
    items_after = client.get("/api/v1/admin/engines/keys").json()["data"]["items"]
    coze_after = next(i for i in items_after if i["engine"] == "coze")
    assert coze_after["registered"] is False
    assert coze_after["activeSource"] == "env"
    assert coze_after["configured"] is True


async def test_admin_register_without_master_key_is_50002(db_session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """无主密钥登记 → 50002（依赖未就绪），不是 4xx、不回落明文。"""
    rows = await _seed_roles(db_session)
    resp = _app(db_session, rows["operator"]).post(
        "/api/v1/admin/engines/keys/coze", json={"key": "sk-live"}
    )
    assert resp.status_code == 503 and resp.json()["code"] == 50002
    assert "ENGINE_KEY_MASTER_KEY" in resp.json()["message"]


async def test_admin_reject_builtin_unknown_blank_and_absent(db_session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    set_master_key(monkeypatch)
    rows = await _seed_roles(db_session)
    client = _app(db_session, rows["operator"])

    for engine, payload in (("builtin", "x"), ("notion", "x")):
        resp = client.post(f"/api/v1/admin/engines/keys/{engine}", json={"key": payload})
        assert resp.status_code == 422 and resp.json()["code"] == 10005, engine

    resp = client.post("/api/v1/admin/engines/keys/coze", json={"key": "   "})
    assert resp.status_code == 422 and resp.json()["code"] == 10005

    resp = client.delete("/api/v1/admin/engines/keys/coze")
    assert resp.status_code == 404 and resp.json()["code"] == 30004

    # 越权撤销同样被拦（门禁在取数据之前）
    resp = _app(db_session, rows["user"]).delete("/api/v1/admin/engines/keys/coze")
    assert resp.status_code == 403 and resp.json()["code"] == 10004


async def test_get_engines_reflects_registration(db_session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """登记后登录用户（非 operator）在 GET /engines 亦能看到生效来源——
    登记不只影响 admin 视图，也影响前端引擎切换器的「未配置 Key」判定。"""
    set_master_key(monkeypatch)
    rows = await _seed_roles(db_session)

    client = _app(db_session, rows["user"])
    coze = next(i for i in client.get("/api/v1/engines").json()["data"]["items"] if i["engine"] == "coze")
    assert coze["configured"] is False and coze["activeSource"] is None

    _app(db_session, rows["operator"]).post("/api/v1/admin/engines/keys/coze", json={"key": "sk-1"})

    coze = next(i for i in client.get("/api/v1/engines").json()["data"]["items"] if i["engine"] == "coze")
    assert coze["configured"] is True and coze["activeSource"] == "registered"
    assert coze["available"] is False  # 已配 Key 但骨架位未实接（ENGINE_IMPLEMENTED=False）
