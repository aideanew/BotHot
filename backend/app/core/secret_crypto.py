"""渠道密钥 AES-256-GCM 加解密。

照 core/engine_keyring.py:67-120 的纪律实现：
- 密文形态 b64(nonce).b64(ct+tag)
- AAD 绑定 bot_channel.id（密文无法在渠道之间搬移，换行解密必失败）
- 空明文直接返回空串（不加密）
- 主密钥缺失/非 32 字节 base64 时 raise DependencyUnavailableError（fail-closed，绝不回落明文）
"""

from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings, get_settings
from app.core.errors import DependencyUnavailableError, RequestInvalidError

# GCM 推荐 96 bit nonce；AES-256 需 32 字节主密钥
_NONCE_BYTES = 12
_KEY_BYTES = 32

# settings 字段 → 对外展示的 env 变量名
_ENV_VAR_NAME = "PUSH_SECRET_MASTER_KEY"


def _master_key(settings: Settings | None = None) -> bytes:
    """主密钥解析：32 字节 base64，缺失/畸形一律拒绝——绝不回落明文。"""
    raw = str(getattr(settings or get_settings(), "push_secret_master_key", "") or "")
    if not raw:
        raise DependencyUnavailableError(
            f"{_ENV_VAR_NAME} 未配置（需 32 字节密钥的 base64），无法加密或解密渠道密钥"
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DependencyUnavailableError(
            f"{_ENV_VAR_NAME} 不是合法 base64，无法加密或解密渠道密钥"
        ) from exc
    if len(key) != _KEY_BYTES:
        raise DependencyUnavailableError(
            f"{_ENV_VAR_NAME} 需 {_KEY_BYTES} 字节（AES-256），当前 {len(key)} 字节"
        )
    return key


def encrypt_channel_secret(
    channel_id: str,
    plaintext: str,
    master: bytes | None = None,
    settings: Settings | None = None,
) -> str:
    """AES-256-GCM 加密渠道密钥。AAD = channel_id。

    返回 b64(nonce).b64(ciphertext+tag)。空明文直接返回空串（不加密）。
    """
    if not plaintext:
        return ""

    mk = master if master is not None else _master_key(settings)
    aes = AESGCM(mk)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = aes.encrypt(nonce, plaintext.encode(), channel_id.encode())
    return base64.b64encode(nonce).decode() + "." + base64.b64encode(ciphertext).decode()


def decrypt_channel_secret(
    channel_id: str,
    secret_ref: str,
    master: bytes | None = None,
    settings: Settings | None = None,
) -> str:
    """解密渠道密钥；密文损坏/AAD 不匹配/主密钥已轮换均抛 RequestInvalidError（fail closed）。

    空串直接返回空串。
    """
    if not secret_ref:
        return ""

    mk = master if master is not None else _master_key(settings)
    try:
        nonce_b64, ct_b64 = secret_ref.split(".", 1)
        plaintext = AESGCM(mk).decrypt(
            base64.b64decode(nonce_b64), base64.b64decode(ct_b64), channel_id.encode()
        )
    except (InvalidTag, LookupError, ValueError, binascii.Error, TypeError) as exc:
        raise RequestInvalidError(
            f"渠道 {channel_id} 的密钥不可解（密文损坏或主密钥已轮换）"
        ) from exc
    return plaintext.decode()


def is_aes_ciphertext(secret_ref: str) -> bool:
    """判断密文是否为 AES-256-GCM 形态（含 "." 分隔符）。"""
    if not secret_ref:
        return False
    return "." in secret_ref


def decrypt_legacy_base64(secret_ref: str) -> str | None:
    """尝试用旧 base64 方式解密存量密钥；失败返回 None。"""
    if not secret_ref:
        return None
    # 已是 AES 密文形态则跳过
    if "." in secret_ref:
        return None
    try:
        return base64.b64decode(secret_ref.encode("utf-8")).decode("utf-8")
    except Exception:
        return None
