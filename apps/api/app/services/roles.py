"""SPEC-M3 扩展点①（D9=a 终底）：role 授权判定的单一来源。

所有授权入口须经 require_role()，禁在路由层散落 role 判断。
FastAPI 依赖工厂在 app.api.deps.require_roles —— services 层不反引 api 层
（与 job_worker.py「刻意只在 services 层装配」同纪律）。

角色阶梯 user < operator < admin：判定时按「任一请求角色达标即放行」取秩，
故 admin 自动覆盖 operator 端点，无需在端点处重复声明两级。

**PUBLIC_ADMIN_ALLOWLIST 不在本函数内咨询**（批次 3 双闸收敛，2026-09-23
管理者裁定「按角色分通道」）：allowlist 的唯一合法语义是「公共库发布」，
由 public_library.check_publish_gate 的闸① 持有——那是它从 T1.4.1 起的位置。
本函数曾把它复制成 role 兜底通道，使「allowlist 命中」静默等价于「被请求的
任意角色」，授权面从发布能力放大到全站写权；收敛即删掉这份谓词拷贝。
升权只有一条路：显式写 users.role（可审计），不藏在 env 里。

sub_has_min_rank 是**只读回显**通道（供 /me 出 is_admin），永不用于授权：
授权必须走 require_role——后者缺本地行时抛 10001，前者 fail closed 成 False。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, UnauthenticatedError
from app.models.entities import User
from app.repositories.user import SqlAlchemyUserStore

ROLE_RANK: dict[str, int] = {"user": 0, "operator": 1, "admin": 2}
DEFAULT_ROLE = "user"


def _required_rank(roles: tuple[str, ...]) -> int:
    """请求角色 → 需要的最低秩。空或未知角色名都是编程错误，fail fast。

    静默降级比抛错危险：端点漏传角色若被视为「无要求」，授权面会无声放大。
    """
    if not roles:
        raise ValueError("require_role 至少须指定一个角色")
    unknown = [r for r in roles if r not in ROLE_RANK]
    if unknown:
        raise ValueError(f"未知角色 {unknown}，合法取值 {sorted(ROLE_RANK)}")
    return max(ROLE_RANK[r] for r in roles)


def has_min_rank(role_value: str, *roles: str) -> bool:
    """秩判定的单一实现：行内脏值或缺角色名按最低权限处理（fail closed）。

    不查库、不落异常。require_role 用它判定不达标时抛 10004；
    sub_has_min_rank 用它支撑 /me 的只读回显。两条路径共用同一表达式，
    「是不是 admin」的口径才不会漂移。
    """
    user_rank = ROLE_RANK.get(role_value, ROLE_RANK[DEFAULT_ROLE])
    return user_rank >= _required_rank(roles)


async def sub_has_min_rank(session: AsyncSession, sub: str, *roles: str) -> bool:
    """/me 用的只读判定：按 sub 取本地行，缺行或秩不足一律 False。

    与 require_role 共用 SqlAlchemyUserStore + has_min_rank，判据不复制——
    否则 /me 回显的 is_admin 与 require_roles("admin") 的放行结论会双向分歧
    （UI 显示有权限、后端 403，或反之）。
    只读且不抛错：/me 是全员身份接口，缺本地行（如库被手工清理）时 fail closed
    成 False，不得让 /me 自己开始 10001。
    """
    user = await SqlAlchemyUserStore(session).get_by_sub(sub)
    if user is None:
        return False
    return has_min_rank(user.role, *roles)


async def require_role(session: AsyncSession, user_id: str, *roles: str) -> User:
    """授权主判据（SPEC-M3 §2.3，批次 3 收敛后）：role 达标放行，否则 10004。

    无 allowlist 兜底。过渡期施工改走显式 role 授予（一条 UPDATE），
    而不是把授权面藏在 env 变量里。
    """
    user = await SqlAlchemyUserStore(session).get_by_id(user_id)
    if user is None:
        raise UnauthenticatedError("本地用户不存在，请重新登录")

    if has_min_rank(user.role, *roles):
        return user

    raise ForbiddenError("无此操作权限，请联系管理员")
