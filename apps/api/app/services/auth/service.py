"""SSO 认证服务：授权码流编排 + 会话生命周期（B-T3）。

流程（指南 §3-§5）：
login → 生成 state（服务端单次存储）→ 302 authorize
callback → 校验 state → code 兑换 → userinfo（权威身份）→ upsert users → 建服务端会话
me → 会话 → userinfo 实时 + wallet 实时（余额不落库铁律；access 过期自动 refresh 一次）
logout → revoke refresh 链 + 删除会话
backchannel-logout → 主平台按用户广播 logout_token → 本地 JWKS 验签 → delete_by_sub

PKCE 决策（R5.1.2 / 裁定 R5.B，2026-09-23）：不引入 PKCE / OAuth2 客户端模式。
理由：① BotHot 是主平台内嵌应用，session cookie 是派生会话机制，非第三方授权码场景；
② PKCE 在本平台内嵌场景无额外安全收益；③ HttpOnly + SameSite=Lax（auth.py:78-87）
已提供基础 CSRF 防护；引入 PyJWT 会改变后端供应链。
若未来管理者裁定引入，需新增 PyJWT 依赖 + 修改兑换流程（回退成本 = 1 个 commit）。

上述「不引入 PyJWT」的前提已于 2026-09-28 复核为不成立（`cryptography>=43.0.0`
早在依赖树中，RS256 验签零新增依赖），但裁定结论本身仍适用：授权码流继续走
userinfo RPC，只有 back-channel logout 这一**无对应 RPC** 的场景（主平台
`/oauth/introspect` 仅支持 refresh 令牌）才做本地验签，见 services/auth/logout_token.py。

信任边界（R5.1.3）：BotHot 的 SSO 信任边界是 aidean_issuer（主平台 OIDC），
userinfo 端点是权威身份来源，非第三方开放授权码流程。
"""

from __future__ import annotations

import secrets
import time
from typing import Any

import structlog

from app.core.config import Settings
from app.core.errors import (
    DependencyUnavailableError,
    SsoTokenExchangeError,
    UnauthenticatedError,
)
from app.providers.aidean import AideanProviderClient
from app.repositories.user import SqlAlchemyUserStore, UserStore
from app.services.auth.logout_token import InvalidLogoutToken, JwksVerifier, verify_logout_token
from app.services.auth.session_store import SessionRecord, SessionStore
from app.services.auth.state_store import SsoStateStore, consume_state
from app.services.roles import sub_has_min_rank

logger = structlog.get_logger(__name__)


class AuthService:
    """SSO 编排（无 HTTP 细节；路由层只做参数装配与 cookie 处理）。"""

    def __init__(
        self,
        client: AideanProviderClient,
        state_store: SsoStateStore,
        session_store: SessionStore,
        user_store: UserStore,
        settings: Settings,
        user_session_factory: Any | None = None,
        jwks: JwksVerifier | None = None,
    ) -> None:
        self._client = client
        self._state_store = state_store
        self._session_store = session_store
        self._user_store = user_store
        self._settings = settings
        # B-T8R：生产装配传入 async_sessionmaker（callback 用户落库走真 PG 并 commit）；
        # 单测不传 → user_store 内存桩路径，不触 DB
        self._user_session_factory = user_session_factory
        # R9：back-channel logout 的 JWKS 验签器（拉取主平台 /.well-known/jwks.json）
        self._jwks = jwks

    # -------------------------------------------------- 登录

    async def build_login(self) -> str:
        """生成一次性 state 并构造 authorize 跳转地址。"""
        state = secrets.token_urlsafe(32)  # ≥16 字符（指南 §3 第 1 步）
        await self._state_store.put(state, self._settings.oidc_state_ttl_seconds)
        return self._client.authorize_url(state, self._settings.oidc_redirect_uri, self._settings.oidc_scopes)

    def _verify_userinfo_claims(self, info: dict) -> None:
        """校验 userinfo 的 iss/aud 声明（R5.1.1 / R6.2.1 fail-closed 化）。

        规则：
        - 若配置了期望值（非空）且 userinfo 未返回该字段 → 拒绝（fail-closed）；
          上游必须提供声明，否则视为身份不完整，不建会话。
        - 若配置了期望值且 userinfo 返回了该字段但不匹配 → 拒绝。
        - 若未配置期望值（空串）→ 跳过（向后兼容；生产守卫在 config.py 另行卡位）。
        校验失败 → SsoTokenExchangeError（10003），不建立会话。
        """
        expected_issuer = self._settings.oidc_issuer_expected
        expected_audience = self._settings.oidc_audience_expected
        actual_issuer = info.get("iss")
        actual_audience = info.get("aud")
        if expected_issuer:
            if actual_issuer is None:
                raise SsoTokenExchangeError(f"userinfo 未返回 iss 声明（期望 {expected_issuer}），拒绝建立会话")
            if str(actual_issuer) != expected_issuer:
                raise SsoTokenExchangeError(f"userinfo iss 不匹配：期望 {expected_issuer}，实际 {actual_issuer}")
        if expected_audience:
            if actual_audience is None:
                raise SsoTokenExchangeError(f"userinfo 未返回 aud 声明（期望 {expected_audience}），拒绝建立会话")
            if str(actual_audience) != expected_audience:
                raise SsoTokenExchangeError(f"userinfo aud 不匹配：期望 {expected_audience}，实际 {actual_audience}")

    async def handle_callback(self, code: str, state: str) -> SessionRecord:
        """state 强校验 → 兑换 → 权威身份 → upsert → 建会话。

        失败语义：state 问题 → 10002（SsoStateInvalidError）；
        code 拒绝（过期/重放/redirect 不一致）→ 10003（SsoTokenExchangeError）。
        """
        await consume_state(self._state_store, state)  # 单次消费，先于任何兑换
        tokens = await self._client.exchange_code(code, self._settings.oidc_redirect_uri)
        info = await self._client.userinfo(tokens.access_token)  # 权威身份（替代本地验签）
        self._verify_userinfo_claims(info)  # R5.1.1：iss/aud 校验（可选）
        sub = str(info.get("sub", ""))
        if not sub:
            raise SsoTokenExchangeError("userinfo 未返回 sub，拒绝建立会话")
        if self._user_session_factory is not None:
            # 生产路径：真 PG upsert + 显式 commit（B-T8R：漏 commit → 请求末回滚
            # → get_current_user_id 查无此人 → 10001 登录死循环）
            async with self._user_session_factory() as session:
                await SqlAlchemyUserStore(session).upsert_by_sub(
                    sub, str(info.get("email", "")), str(info.get("nickname", ""))
                )
                await session.commit()
        else:
            await self._user_store.upsert_by_sub(sub, str(info.get("email", "")), str(info.get("nickname", "")))
        record = SessionRecord(
            session_id=secrets.token_urlsafe(32),
            sub=sub,
            email=str(info.get("email", "")),
            nickname=str(info.get("nickname", "")),
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            access_expires_at=time.time() + tokens.expires_in,
        )
        await self._session_store.create(record, self._settings.session_ttl_seconds)
        return record

    # -------------------------------------------------- 会话维持

    async def _require_session(self, session_id: str | None) -> SessionRecord:
        if not session_id:
            raise UnauthenticatedError("缺少会话凭据")
        record = await self._session_store.get(session_id)
        if record is None:
            raise UnauthenticatedError("会话不存在或已过期")
        return record

    async def current_sub(self, session_id: str | None) -> str:
        """会话 → 身份锚点 sub（登录保护接口的依赖入口，B-T4R）。"""
        record = await self._require_session(session_id)
        return record.sub

    async def refresh_session(self, session_id: str) -> SessionRecord:
        """轮换 access/refresh 并回写（旧 refresh 立即失效，轮换链语义）。"""
        record = await self._require_session(session_id)
        tokens = await self._client.refresh(record.refresh_token)  # invalid_grant → 10003
        record.access_token = tokens.access_token
        record.refresh_token = tokens.refresh_token
        record.access_expires_at = time.time() + tokens.expires_in
        await self._session_store.update_tokens(  # 铁律：最新一代必须可靠持久化
            session_id, tokens.access_token, tokens.refresh_token, record.access_expires_at
        )
        return record

    # -------------------------------------------------- 资料 / 登出

    async def _local_profile(self, sub: str) -> dict | None:
        """本地 users 行快照——主平台不可达时的降级资料源。

        无 DB 工厂（单测桩路径）或无本地行 → None，调用方保持原错误语义。
        """
        if self._user_session_factory is None:
            return None
        async with self._user_session_factory() as session:
            user = await SqlAlchemyUserStore(session).get_by_sub(sub)
            if user is None:
                return None
            return {"email": user.email, "nickname": user.nickname, "role": user.role}

    async def get_me(self, session_id: str | None) -> dict:
        """聚合 userinfo + 实时 wallet；access 过期自动 refresh 一次后重试。

        依赖降级：主平台 userinfo/wallet 不可达时不整站 503。会话本身在服务端
        有效（spaces/jobs 等域不受影响），此时把用户挡回登录页会与「会话有效」
        矛盾。有本地资料快照则回退 users 行并标记 wallet 不可查；无快照保持原
        错误语义（50002）。

        QA fixture 短路（A-T024，2026-10-09）：qa_seed_sessions.py 铸造的 access_token
        命中 settings.qa_fixture_token_prefix 时，**不进主平台**——直接取本地 users
        行与 role，标 providerUnreachable:true / qaFixture:true。设计动机：不这么做
        的话，主平台一旦在线（不再是网络不可达），fixture 假令牌走 userinfo 401 →
        refresh → 主平台 invalid_client 或 invalid_grant → SsoTokenExchangeError（不在本
        函数 except 里）→ 10003 直达前端 → QA 会话 100% 登录失败。本短路的合法性
        由生产守卫卡位：QA_FIXTURE_TOKEN_PREFIX 必须显式置空才能上生产。
        """
        record = await self._require_session(session_id)
        fixture_prefix = self._settings.qa_fixture_token_prefix
        if fixture_prefix and record.access_token.startswith(fixture_prefix):
            local = await self._local_profile(record.sub) or {
                "email": record.email,
                "nickname": record.nickname,
                "role": "",
            }
            return {
                "user": {
                    "sub": record.sub,
                    "email": local["email"],
                    "nickname": local["nickname"],
                    "tier": "",
                    "role": local["role"],
                    "is_admin": await self._is_admin(record.sub),
                },
                "wallet": {"balanceYuan": 0, "currency": "CNY", "available": False},
                "providerUnreachable": True,
                "qaFixture": True,
            }
        try:
            try:
                info = await self._client.userinfo(record.access_token)
            except UnauthenticatedError:
                # 指南 §6：userinfo 401 → refresh 轮换后重试（仅一次，禁止循环）
                record = await self.refresh_session(record.session_id)
                info = await self._client.userinfo(record.access_token)
            wallet = await self._client.wallet(record.sub)  # 实时查询，不落库
        except DependencyUnavailableError:
            local = await self._local_profile(record.sub)
            if local is None:
                raise
            return {
                "user": {
                    "sub": record.sub,
                    "email": local["email"],
                    "nickname": local["nickname"],
                    "tier": "",
                    "role": local["role"],
                    # is_admin 取自本地 users.role，主平台不可达不影响判定
                    "is_admin": await self._is_admin(record.sub),
                },
                "wallet": {"balanceYuan": 0, "currency": "CNY", "available": False},
                "providerUnreachable": True,
            }
        return {
            "user": {
                "sub": str(info.get("sub", record.sub)),
                "email": str(info.get("email", record.email)),
                "nickname": str(info.get("nickname", record.nickname)),
                "tier": str(info.get("tier", "")),
                "role": str(info.get("role", "")),
                # SPEC-M3 批次 2：is_admin 取自本地 users.role（与 require_roles 同源）。
                # 不是上面的 userinfo role——主平台大写枚举，与本地阶梯不同源不同形，
                # 用它门禁 UI 会与后端授权双向分歧。
                "is_admin": await self._is_admin(record.sub),
            },
            "wallet": wallet.get("wallet", wallet),  # 兼容 data 直接为 wallet 形态
        }

    async def _is_admin(self, sub: str) -> bool:
        """本地 users.role 的只读判定。无 DB 工厂（单测桩路径）或缺本地行 → False。"""
        if self._user_session_factory is None:
            return False
        async with self._user_session_factory() as session:
            return await sub_has_min_rank(session, sub, "admin")

    async def logout(self, session_id: str | None) -> None:
        """撤销 refresh 链（两级撤销：仅断本产品）+ 删除服务端会话。"""
        if not session_id:
            return
        record = await self._session_store.get(session_id)
        if record is None:
            return
        await self._client.revoke(record.refresh_token)  # 主平台语义：恒 200
        await self._session_store.delete(session_id)

    async def handle_backchannel_logout(self, logout_token: str) -> dict[str, object]:
        """处理主平台的 back-channel 登出广播：验签 → 按 sub 删除本地会话。

        恒返回结果字典（不抛）：端点须恒 200 同形响应，不向主平台泄露校验结果差异
        （对齐主平台 `/oauth/revoke` 恒 200 口径，见 providers/aidean/client.py）。
        不调用主平台（不做 revoke/introspect）：主平台侧链已在登出时自行撤销，
        且 fire-and-forget 5s 超时约束下不得在此路径同步外呼。
        不清理本地 users 表：身份锚点保留，下次登录可复用。
        日志只记 sub 前缀与原因码，**绝不记录 token 原文**。
        """
        if not logout_token:
            return self._backchannel_result("missing_token", sub_prefix="", deleted=0)
        if self._jwks is None:
            # fail-closed：装配缺失等价于无法证明接收方，拒绝而非跳过
            return self._backchannel_result("jwks_not_configured", sub_prefix="", deleted=0)
        try:
            claims = await verify_logout_token(
                logout_token,
                jwks=self._jwks,
                expected_issuer=self._settings.oidc_issuer_expected,
                expected_audience=self._settings.oidc_audience_expected,
                max_age_seconds=self._settings.oidc_logout_token_max_age_seconds,
            )
        except InvalidLogoutToken as exc:
            result = self._backchannel_result(exc.reason, sub_prefix="", deleted=0)
            logger.warning("back-channel logout 校验失败: %s", exc.reason)
            return result
        deleted = await self._session_store.delete_by_sub(claims.sub)
        result = self._backchannel_result("verified", sub_prefix=claims.sub[:8], deleted=deleted)
        logger.info(
            "back-channel logout 已处理: sub_prefix=%s sessions_deleted=%d",
            claims.sub[:8],
            deleted,
        )
        return result

    @staticmethod
    def _backchannel_result(reason: str, *, sub_prefix: str, deleted: int) -> dict[str, object]:
        """统一结果形状；`reason` 是稳定码，供日志聚合与主平台侧投递排查关联。"""
        return {
            "verified": reason == "verified",
            "reason": reason,
            "subPrefix": sub_prefix,
            "sessionsDeleted": deleted,
        }
