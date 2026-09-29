"""SPEC-M3 批次 3 / T5.4：引擎 Key 登记服务。

operator 可登记/撤销引擎 Key，替代「找管理员改 env 再重启」。密文落库
（core.engine_keyring AES-256-GCM），写后刷新进程内快照。

授权不在本层——路由层 require_roles("operator")；本层只做数据操作
（与 M3 批次 2 SpaceService.update_space_any 同纪律）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.engine_keyring import KEYABLE_ENGINES, decrypt_secret, encrypt_secret, master_key, set_snapshot
from app.core.errors import DependencyUnavailableError, RequestInvalidError, ResourceNotFoundError
from app.models.entities import EngineKeyRegistration

# 明文 Key 长度上限（密文长度随之线性增长，secret_ref 用 Text 无截断风险）
MAX_KEY_CHARS = 1024


@dataclass(frozen=True)
class RegistryLoad:
    """一次读表的完整结果。

    plaintext 只含解密成功的行；decrypt_bad 标注失败行（不静默当「未配置」）；
    rows 为行元数据（不含明文），供 admin 列表展示。
    """

    plaintext: dict[str, str]
    decrypt_bad: dict[str, str]
    rows: list[dict[str, object]]


class EngineKeyService:
    """engine_key_registrations 读写与快照刷新。

    事务约定：显式 commit（与 PublicLibraryService 同口径）；测试借外层事务
    savepoint 回滚隔离。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get(self, engine: str) -> EngineKeyRegistration | None:
        return (
            await self._session.execute(
                select(EngineKeyRegistration).where(EngineKeyRegistration.engine == engine)
            )
        ).scalar_one_or_none()

    @staticmethod
    def _assert_engine(engine: str) -> None:
        if engine == "builtin":
            raise RequestInvalidError("builtin 为内置引擎，无需登记 Key")
        if engine not in KEYABLE_ENGINES:
            raise RequestInvalidError(f"未知引擎位: {engine}（可选 {list(KEYABLE_ENGINES)}）")

    async def load(self) -> RegistryLoad:
        """读全表并解密。解密失败的行**不计入**可用集，但必须被标注——静默当
        「未配置」会让操作者以为登记丢了（F-4 教训）。主密钥缺失时同样标注全部现存行。
        """
        rows = (await self._session.execute(select(EngineKeyRegistration))).scalars().all()
        metadata: list[dict[str, object]] = [
            {
                "engine": r.engine,
                "keyId": r.key_id,
                "registeredBy": r.registered_by,
                "updatedAt": r.updated_at.isoformat() if r.updated_at else "",
            }
            for r in rows
        ]
        if not rows:
            return RegistryLoad({}, {}, metadata)

        try:
            master = master_key()
        except DependencyUnavailableError as exc:
            return RegistryLoad({}, {r.engine: exc.message for r in rows}, metadata)

        plaintext: dict[str, str] = {}
        decrypt_bad: dict[str, str] = {}
        for row in rows:
            try:
                plaintext[row.engine] = decrypt_secret(row.engine, row.secret_ref, master)
            except RequestInvalidError as exc:
                decrypt_bad[row.engine] = exc.message
        return RegistryLoad(plaintext, decrypt_bad, metadata)

    async def _refresh(self) -> None:
        loaded = await self.load()
        set_snapshot(loaded.plaintext)

    async def register(self, operator_id: str, engine: str, plaintext: str) -> dict[str, str]:
        """登记/覆盖某引擎位的 Key（upsert，一行一引擎位）。"""
        self._assert_engine(engine)
        plaintext = str(plaintext or "").strip()
        if not plaintext:
            raise RequestInvalidError("引擎 Key 不能为空")
        if len(plaintext) > MAX_KEY_CHARS:
            raise RequestInvalidError(f"引擎 Key 过长（上限 {MAX_KEY_CHARS} 字符）")
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in plaintext):
            raise RequestInvalidError("引擎 Key 含控制字符")

        master = master_key()  # 缺失/畸形 → 50002，绝不回落明文落库
        key_id = uuid.uuid4().hex
        row = await self._get(engine)
        if row is None:
            row = EngineKeyRegistration(
                engine=engine,
                secret_ref=encrypt_secret(engine, plaintext, master),
                key_id=key_id,
                registered_by=operator_id,
            )
            self._session.add(row)
        else:
            row.secret_ref = encrypt_secret(engine, plaintext, master)
            row.key_id = key_id
            row.registered_by = operator_id

        await self._session.commit()
        await self._refresh()
        return {"engine": engine, "keyId": key_id}

    async def revoke(self, operator_id: str, engine: str) -> dict[str, object]:
        """撤销登记（回落 env；env 亦空则该引擎位不再可用）。"""
        self._assert_engine(engine)
        if await self._get(engine) is None:
            raise ResourceNotFoundError(f"引擎 {engine} 无登记 Key")
        await self._session.execute(
            delete(EngineKeyRegistration).where(EngineKeyRegistration.engine == engine)
        )
        await self._session.commit()
        await self._refresh()
        return {"engine": engine, "revoked": True}
