"""S2.1：bot_channels.extra_config 明文 JSON → AES-256-GCM 重加密。

逐行扫 bot_channels.extra_config：
- 空 / 以 "{" 开头（明文 JSON）→ 待迁移
- 已是密文（b64.b64 形态，不以 "{" 开头且含 "."）→ 跳过
- 其余（畸形）→ 中止迁移（fail-closed）

密文 AAD = "{id}:extra_config"（域分隔，与 secret_enc 不可互换），运行时读侧
decrypt_extra_config 同口径（"{" 开头明文兼容读兜底迁移回滚场景）。

主密钥纪律与 ab1004w1a 一致（fail-closed）：存在待迁移存量行而
PUSH_SECRET_MASTER_KEY 缺失/畸形时**中止迁移**而非跳过。

Revises: ab1005w5a
"""

from __future__ import annotations

import base64
import logging

import sqlalchemy as sa
from sqlalchemy import column, table
from sqlalchemy.dialects.postgresql import TEXT

from alembic import op

logger = logging.getLogger(__name__)

revision: str = "ab1005w5b"
down_revision: str | None = "ab1005w5a"
branch_labels = None
depends_on = None


def _load_master_key() -> bytes | None:
    """主密钥解析（32 字节 base64）；畸形返回 None 由调用方裁定是否 fail-closed。"""
    import os

    raw = os.environ.get("PUSH_SECRET_MASTER_KEY", "")
    if not raw:
        return None
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception:
        return None
    return key if len(key) == 32 else None


def upgrade() -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    bot_channels = table(
        "bot_channels", column("id", sa.String), column("extra_config", TEXT)
    )
    conn = op.get_bind()
    rows = conn.execute(sa.select(bot_channels.c.id, bot_channels.c.extra_config)).fetchall()

    pending: list[tuple[str, str]] = []
    already: list[str] = []
    malformed: list[str] = []
    for row in rows:
        raw = row.extra_config
        if not raw:
            continue
        if raw.startswith("{"):
            pending.append((row.id, raw))  # 明文 JSON（含默认 "{}"）
        elif "." in raw:
            already.append(row.id)  # 已加密
        else:
            malformed.append(row.id)

    if malformed:
        raise RuntimeError(
            f"ab1005w5b: {len(malformed)} 条 extra_config 形态畸形（非 JSON 非密文），"
            f"channel_ids={malformed[:5]}。请人工核查后重跑（fail-closed，不静默跳过）"
        )

    if not pending:
        logger.info(
            "ab1005w5b: 无明文 extra_config 待迁移（plain=0, aes=%d），跳过", len(already)
        )
        return

    master_key = _load_master_key()
    if master_key is None:
        raise RuntimeError(
            f"ab1005w5b: 检测到 {len(pending)} 条明文 extra_config 待加密，"
            "但 PUSH_SECRET_MASTER_KEY 缺失/畸形。请配置 32 字节密钥的 base64 后重跑迁移"
            "（fail-closed：跳过会让敏感配置永久停留在明文态）"
        )

    aes = AESGCM(master_key)
    import os as _os

    for channel_id, plaintext in pending:
        nonce = _os.urandom(12)
        ct = aes.encrypt(nonce, plaintext.encode(), f"{channel_id}:extra_config".encode())
        ciphertext = base64.b64encode(nonce).decode() + "." + base64.b64encode(ct).decode()
        conn.execute(
            bot_channels.update()
            .where(bot_channels.c.id == channel_id)
            .values(extra_config=ciphertext)
        )
    logger.info("ab1005w5b: 已加密 %d 条 extra_config（aes 已有 %d 条）", len(pending), len(already))


def downgrade() -> None:
    """不可逆：密文→明文需主密钥且无安全收益（历史明文已不可恢复），拒绝降级。"""
    raise RuntimeError("ab1005w5b 不支持降级：extra_config 加密为单向加固（与 ab1004w1a 同裁定）")
