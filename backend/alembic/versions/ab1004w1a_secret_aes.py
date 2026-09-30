"""W1：bot_channels.secret_enc 存量 base64 → AES-256-GCM 重加密。

逐行扫 bot_channels：
- 空 secret → 跳过
- 密文含 "." 视为已 AES → 跳过
- 否则 base64 解出明文 → AES 重加密

解密失败即中止迁移（fail-closed，不静默跳过）。

Revises: ab1004bh01
"""

from __future__ import annotations

import base64
import logging

import sqlalchemy as sa
from sqlalchemy import table, column
from sqlalchemy.dialects.postgresql import TEXT

from alembic import op

logger = logging.getLogger(__name__)

revision: str = "ab1004w1a"
down_revision: str | None = "ab1004bh01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """将 bot_channels.secret_enc 从 base64 伪加密迁移到 AES-256-GCM。

    主密钥纪律（fail-closed）：存在待迁移的存量 base64 行而 PUSH_SECRET_MASTER_KEY
    缺失/畸形时**中止迁移**而非跳过——静默跳过会让存量行永久停留在 fail-closed
    解密不可读的状态（运行时 50002），比迁移期显式报错更难排查。空库/无存量行时
    主密钥缺失不阻塞迁移（无行可迁，新密钥走运行时 AES）。
    """
    import os

    bot_channels = table("bot_channels", column("id", sa.String), column("secret_enc", TEXT))
    conn = op.get_bind()
    rows = conn.execute(sa.select(bot_channels.c.id, bot_channels.c.secret_enc)).fetchall()

    legacy_rows = [
        (row.id, row.secret_enc)
        for row in rows
        if row.secret_enc and "." not in row.secret_enc
    ]

    master_key_b64 = os.environ.get("PUSH_SECRET_MASTER_KEY", "")

    def _key_error(reason: str) -> RuntimeError:
        return RuntimeError(
            f"ab1004w1a: 检测到 {len(legacy_rows)} 条存量 base64 渠道密钥待重加密，"
            f"但 PUSH_SECRET_MASTER_KEY {reason}。请配置 32 字节密钥的 base64 后重跑迁移"
            "（fail-closed：跳过会让存量密钥在运行时永久不可解）"
        )

    if legacy_rows:
        if not master_key_b64:
            logger.error("PUSH_SECRET_MASTER_KEY 未配置，且存在存量待迁移密钥，中止迁移")
            raise _key_error("未配置")
        try:
            master_key = base64.b64decode(master_key_b64, validate=True)
        except Exception as exc:
            logger.error("PUSH_SECRET_MASTER_KEY 不是合法 base64，中止迁移")
            raise _key_error("不是合法 base64") from exc
        if len(master_key) != 32:
            logger.error("PUSH_SECRET_MASTER_KEY 非 32 字节，中止迁移")
            raise _key_error(f"长度 {len(master_key)} 字节而非 32 字节")
    else:
        logger.info(
            "ab1004w1a: 无存量 base64 密钥待迁移（empty=%d, aes=%d），跳过重加密",
            sum(1 for _, s in rows if not s),
            sum(1 for _, s in rows if s and "." in s),
        )
        return

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aes = AESGCM(master_key)

    migrated = 0
    skipped_empty = 0
    skipped_aes = 0

    for row_id, secret_enc in legacy_rows:
        # legacy_rows 已过滤空值与 AES 形态，此处必为 base64 旧密文
        try:
            plaintext = base64.b64decode(secret_enc.encode("utf-8")).decode("utf-8")
        except Exception as exc:
            # 解密失败即中止（fail-closed）
            logger.error("bot_channels.%s: 旧密文 base64 解码失败，中止迁移", row_id)
            raise RuntimeError(
                f"bot_channels.{row_id}: 旧密文 base64 解码失败，中止迁移（fail-closed）"
            ) from exc

        if not plaintext:
            skipped_empty += 1
            continue

        nonce = os.urandom(12)
        ciphertext = aes.encrypt(nonce, plaintext.encode(), row_id.encode())
        new_secret = base64.b64encode(nonce).decode() + "." + base64.b64encode(ciphertext).decode()

        conn.execute(
            sa.update(bot_channels).where(bot_channels.c.id == row_id).values(secret_enc=new_secret)
        )
        migrated += 1

    logger.info(
        "密钥重加密完成: migrated=%d, skipped_empty=%d, skipped_aes=%d",
        migrated, skipped_empty, skipped_aes,
    )


def downgrade() -> None:
    """降级不可行：AES 密文无法还原为旧 base64 伪加密（需要明文主密钥且会回退为不安全方案）。"""
    logger.warning("ab1004w1a downgrade: AES→base64 降级不执行（安全回退不可行）")
