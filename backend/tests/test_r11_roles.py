"""SPEC-M3 批次 1/3（T5.0 role 迁移 + require_role 判定 + 双闸收敛）验收测试。

口径（SPEC-M3 §2.1/§2.3/§2.4，D9=a 终底）：
- 三态阶梯 user < operator < admin，按「任一请求角色达标即放行」取秩；
- role 未达标 → 直接 10004/403。**无 PUBLIC_ADMIN_ALLOWLIST 兜底**（批次 3 双闸
  收敛，2026-09-23 管理者裁定「按角色分通道」）：allowlist 语义归公共库发布闸
  `public_library.check_publish_gate` 独有，见 tests/test_public_library_admin.py；
- 判定单一来源 = app.services.roles.require_role；路由经 app.api.deps.require_roles
  依赖工厂接入（services 层不反引 api 层，与 job_worker 同纪律）。

门禁对应：§2.4 三态用例矩阵；§七-4 越权不泄露存在性（统一 10004/403）。
PG 连库用例走真实 PG:5433（外层事务回滚隔离，零残留）；不可达自动 skip。
"""

from __future__ import annotations

from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.deps import get_current_user_id, get_db, require_roles
from app.core.errors import ForbiddenError, UnauthenticatedError
from app.core.response import success
from app.main import create_app
from app.models.entities import User
from app.services import roles
from app.services.roles import (
    DEFAULT_ROLE,
    ROLE_RANK,
    _required_rank,
    has_min_rank,
    require_role,
    sub_has_min_rank,
)

# 本地 users.id 取值（非主平台 sub）。故意取「形如 allowlist 条目」的值，
# 用于锁定批次 3 收敛后该形状不得再影响 role 判定。
OP_USER = "11111111-1111-1111-1111-111111111111"
NOBODY = "99999999-9999-9999-9999-999999999999"
MISSING = "00000000-0000-0000-0000-000000000000"


# ------------------------------------------------------------------ 纯逻辑（离线口径）


def test_required_rank_picks_highest_of_requested() -> None:
    """阶梯判定取最高秩：声明 ("operator","admin") 仍按 admin 校。"""
    assert _required_rank(("operator", "admin")) == ROLE_RANK["admin"]
    assert _required_rank(("operator",)) == ROLE_RANK["operator"]
    assert _required_rank(("user",)) == ROLE_RANK["user"]


def test_required_rank_rejects_empty_request() -> None:
    """漏传角色 = 编程错误。静默按「无要求」处理会让授权面无声放大。"""
    with pytest.raises(ValueError, match="至少须指定一个角色"):
        _required_rank(())


def test_required_rank_rejects_unknown_role() -> None:
    """未知角色名同样 fail fast——拼写错误不该被当成 user 放行。"""
    with pytest.raises(ValueError, match="未知角色"):
        _required_rank(("admn",))


def test_default_role_is_least_privilege() -> None:
    assert DEFAULT_ROLE == "user"
    assert ROLE_RANK[DEFAULT_ROLE] == min(ROLE_RANK.values())


def test_role_ladder_is_strictly_increasing() -> None:
    """阶梯单调：admin > operator > user。倒挂会让高阶角色失去覆盖能力。"""
    assert ROLE_RANK["user"] < ROLE_RANK["operator"] < ROLE_RANK["admin"]
    assert set(ROLE_RANK) == {"user", "operator", "admin"}


def test_has_min_rank_fails_closed_and_validates_request() -> None:
    """秩判定的单一实现：脏值按最低权限，未知请求角色名仍 fail fast。"""
    assert has_min_rank("admin", "admin") is True
    assert has_min_rank("admin", "operator") is True
    assert has_min_rank("operator", "admin") is False
    assert has_min_rank("user", "admin") is False
    assert has_min_rank("superadmin", "admin") is False
    assert has_min_rank("", "admin") is False
    with pytest.raises(ValueError, match="未知角色"):
        has_min_rank("admin", "admn")


def test_role_module_does_not_read_allowlist() -> None:
    """批次 3 双闸收敛锁：role 判定不得咨询 allowlist / settings。

    批次 1 时本模块内联了一份 allowlist 谓词作兜底通道，使「allowlist 命中」
    静默等价于「被请求的任意角色」——授权面从「可发布公共库」放大到全站写权。
    收敛即删掉该谓词拷贝，allowlist 语义回到 `check_publish_gate` 闸① 独占。
    结构性断言而非仅行为断言：读回 settings 的行为可在 env 为空时被测漏。
    """
    assert "get_settings" not in dir(roles)
    assert "in_admin_allowlist" not in dir(roles)


# ------------------------------------------------------------------ PG 连库口径


async def _seed_user(
    db_session: Any,
    sub: str,
    role: str = "user",
    uid: str | None = None,
) -> User:
    user = User(sub=sub, email=f"{sub}@r11.test", nickname=f"r11-{sub}", role=role)
    if uid is not None:
        user.id = uid
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


async def _allowed(db_session: Any, actor: User, wanted: tuple[str, ...]) -> bool:
    try:
        await require_role(db_session, actor.id, *wanted)
        return True
    except ForbiddenError:
        return False


async def test_role_column_defaults_to_user_on_insert(db_session) -> None:  # type: ignore[no-untyped-def]
    """迁移后新建账号落最小权限态；不显式指定 role 不得越权。"""
    user = User(sub="r11-default", email="r11-default@r11.test", nickname="默认")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    assert user.role == "user"
    assert await require_role(db_session, user.id, "user") is user


async def test_role_ladder_matrix(db_session) -> None:  # type: ignore[no-untyped-def]
    """§2.4 三态用例矩阵：user 全拒 / operator 仅 operator 位 / admin 全放行。"""
    user = await _seed_user(db_session, "r11-matrix-user")
    operator = await _seed_user(db_session, "r11-matrix-operator", role="operator")
    admin = await _seed_user(db_session, "r11-matrix-admin", role="admin")

    cases = [
        (user, ("user",), True),
        (user, ("operator",), False),
        (user, ("admin",), False),
        (operator, ("user",), True),
        (operator, ("operator",), True),
        # 多角色元组取**最高秩**而非「任一成员命中」：声明 ("operator","admin")
        # 等价于 ("admin",)。SPEC-M3 §2.3 原文写 role ∈ roles，但成员语义会让
        # admin 被 operator 端点拒——与其自身「admin 全放行」验收锚矛盾，
        # 故取单调秩语义，此处锁定该取舍。
        (operator, ("operator", "admin"), False),
        (operator, ("admin",), False),
        (admin, ("user",), True),
        (admin, ("operator",), True),
        (admin, ("admin",), True),
        (admin, ("operator", "admin"), True),
    ]
    for actor, wanted, expect_allow in cases:
        outcome = await _allowed(db_session, actor, wanted)
        assert outcome is expect_allow, f"role={actor.role} 请求 {wanted} → {outcome}"


async def test_garbage_role_fails_closed(db_session) -> None:  # type: ignore[no-untyped-def]
    """行内脏值（手工改成非法角色）按最低权限处理——fail closed。"""
    actor = await _seed_user(db_session, "r11-garbage", role="superadmin")
    with pytest.raises(ForbiddenError):
        await require_role(db_session, actor.id, "admin")


async def test_missing_user_raises_unauthenticated(db_session) -> None:  # type: ignore[no-untyped-def]
    """本地无行 → 10001（不是 10004）：授权前先确认身份存在。"""
    with pytest.raises(UnauthenticatedError) as exc:
        await require_role(db_session, MISSING, "admin")
    assert exc.value.code == 10001


async def test_sub_has_min_rank_missing_user_fails_closed(db_session) -> None:  # type: ignore[no-untyped-def]
    """缺本地行 → False 且**不抛错**：/me 是全员身份接口，缺行不得让它 10001。

    对比 require_role 的 10001：授权必须先确认身份存在，回显只需如实说「不是 admin」。
    """
    assert await sub_has_min_rank(db_session, "r11-ghost", "admin") is False
    assert await sub_has_min_rank(db_session, "r11-ghost", "user") is False


async def test_is_admin_flag_and_admin_gate_agree(db_session) -> None:  # type: ignore[no-untyped-def]
    """/me 的 is_admin 与 require_roles("admin") 的放行结论逐角色一致（同源锁）。

    漂移的代价是双向分歧：UI 显示有权限而后端 403，或反之。两条路径共用
    SqlAlchemyUserStore + has_min_rank，本用例如断则判据已复制成两份。
    """
    for role in ("user", "operator", "admin", "superadmin", ""):
        actor = await _seed_user(db_session, f"r11-agree-{role or 'blank'}", role=role)
        assert (
            await sub_has_min_rank(db_session, actor.sub, "admin")
            is await _allowed(db_session, actor, ("admin",))
        ), f"role={role!r} 的回显与门禁结论分歧"


async def test_allowlisted_user_id_still_denied(db_session) -> None:  # type: ignore[no-untyped-def]
    """按角色分通道（行为口径）：id 形如 allowlist 条目的账号仍按 role 判定。

    批次 1 时该形状会经兜底通道拿到任意角色；批次 3 收敛后无此路径。
    过渡期施工改走显式 role 授予（一条 UPDATE），不藏在 env 里。
    """
    actor = await _seed_user(db_session, "r11-allowlisted", role="user", uid=OP_USER)
    for wanted in (("operator",), ("admin",)):
        with pytest.raises(ForbiddenError):
            await require_role(db_session, actor.id, *wanted)


# ------------------------------------------------------------------ 依赖工厂端到端（TestClient）


def _gated_app(db_session: Any, actor: User) -> TestClient:
    """挂两条受 role 保护的路由，验证工厂与既有依赖在同一会话上协作。"""
    app = create_app()
    router = APIRouter(prefix="/r11")

    @router.get("/op")
    async def op_endpoint(user: Annotated[User, Depends(require_roles("operator"))]) -> JSONResponse:
        return JSONResponse(status_code=200, content=success(data={"role": user.role}).model_dump())

    @router.get("/admin")
    async def admin_endpoint(
        user: Annotated[User, Depends(require_roles("admin"))],
    ) -> JSONResponse:
        return JSONResponse(status_code=200, content=success(data={"role": user.role}).model_dump())

    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: actor.id
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


async def test_require_roles_dependency_matrix_end_to_end(
    db_session,
) -> None:  # type: ignore[no-untyped-def]
    """门禁 §七-4：越权统一 10004/403、阶梯覆盖；allowlist 形状不得放通。"""
    actors = {
        "user": await _seed_user(db_session, "r11-wire-user"),
        "operator": await _seed_user(db_session, "r11-wire-operator", role="operator"),
        "admin": await _seed_user(db_session, "r11-wire-admin", role="admin"),
        # id = OP_USER：正是「会被写进 allowlist」的形状，锁定收敛后不再生效
        "allowlisted": await _seed_user(
            db_session, "r11-wire-allowlisted", role="user", uid=OP_USER
        ),
    }

    def _hit(actor: User, path: str) -> tuple[int, int]:
        resp = _gated_app(db_session, actor).get(path)
        return resp.status_code, resp.json()["code"]

    assert _hit(actors["user"], "/r11/op") == (403, 10004)
    assert _hit(actors["user"], "/r11/admin") == (403, 10004)
    assert _hit(actors["operator"], "/r11/op") == (200, 0)
    assert _hit(actors["operator"], "/r11/admin") == (403, 10004)
    assert _hit(actors["admin"], "/r11/op") == (200, 0)  # 阶梯覆盖
    assert _hit(actors["admin"], "/r11/admin") == (200, 0)

    # 批次 3 收敛：allowlist 形状不再等价于任意角色
    assert _hit(actors["allowlisted"], "/r11/op") == (403, 10004)
    assert _hit(actors["allowlisted"], "/r11/admin") == (403, 10004)
