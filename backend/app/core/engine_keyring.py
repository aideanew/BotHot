"""T5.4（SPEC-M3 批次 3）引擎 Key 登记表：落库加密 + 凭据解析单一来源 + 进程内快照。

三件单一来源，避免「同一份数据、两个谓词」再次漂移（F-3 / R0.3.2 的根因）：

1. 落库加密——AES-256-GCM，AAD 绑定引擎名，密文形态 base64(nonce).base64(ct+tag)。
   注册表里零明文（全局规则「不提交敏感信息」覆盖运行时数据面）。
2. 凭据解析——resolve_engine_key() 是唯一判定「哪个引擎有凭据、凭据来自哪」的谓词。
   engines.py 的状态上报与 engine_port.py 的路由判定必须都走它；main 需 base **且** key
   （历史 bug：engines.py 只查 base，engine_port.py 查 base 且 key，两份拷贝结论相反）。
3. 进程内快照——EngineRouter / make_engine 是 sync 且无 DB session（5 处构造点，含模块
   级单例），同步取密文只能靠写路径刷新这里。GET /engines 与管理端 CRUD **直接读库**，
   不走快照，故状态上报永不陈旧；快照陈旧最坏只影响尚未实接的骨架位（ENGINE_IMPLEMENTED
   全为 False 时不可路由），且回落 env 行为，不引入新的静默分歧。
"""

from __future__ import annotations

import base64
import binascii
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings, get_settings
from app.core.errors import DependencyUnavailableError, RequestInvalidError

# GCM 推荐 96 bit nonce；AES-256 需 32 字节主密钥
_NONCE_BYTES = 12
_KEY_BYTES = 32

# settings 字段 → 对外展示的 env 变量名（错误提示指向真名，不指字段名）
_ENV_VARS: dict[str, str] = {
    "main": "MAIN_KB_API_KEY",
    "coze": "COZE_API_KEY",
    "dify": "DIFY_API_KEY",
    "fastgpt": "FASTGPT_API_KEY",
}

# 引擎位 → Settings 属性名。main 是 main_kb_api_key 而非 main_api_key，
# 泛化 f"{engine}_api_key" 会漏掉它（曾因此把已配置的 main 误判为未配置）。
_SETTINGS_ATTRS: dict[str, str] = {
    "main": "main_kb_api_key",
    "coze": "coze_api_key",
    "dify": "dify_api_key",
    "fastgpt": "fastgpt_api_key",
}

# 可登记引擎位（builtin 是内置回退通道，无需 Key，不入登记表）
KEYABLE_ENGINES: tuple[str, ...] = tuple(_ENV_VARS)


@dataclass(frozen=True)
class KeyResolution:
    """一个引擎位的凭据解析结果（唯一判定形状）。"""

    engine: str
    configured: bool
    key: str  # 明文 Key；未配置或 builtin 为空串（builtin 无需 Key）
    source: str | None  # "env" | "registered" | None（builtin / 未配置）
    env_var: str  # 供错误提示指明应配置的 env 变量


def master_key(settings: Settings | None = None) -> bytes:
    """主密钥解析：32 字节 base64，缺失/畸形一律拒绝——绝不回落明文。

    回落明文是最坏结局：界面显示「已加密登记」而库里其实是明文，
    比一开始就写明文更难被发现。畸形同样拒：静默按截断处理会把「配置错了」
    伪装成「配置对了」。
    """
    raw = str(getattr(settings or get_settings(), "engine_key_master_key", "") or "")
    if not raw:
        raise DependencyUnavailableError(
            "ENGINE_KEY_MASTER_KEY 未配置（需 32 字节密钥的 base64），无法登记或读取引擎 Key"
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DependencyUnavailableError(
            "ENGINE_KEY_MASTER_KEY 不是合法 base64，无法登记或读取引擎 Key"
        ) from exc
    if len(key) != _KEY_BYTES:
        raise DependencyUnavailableError(
            f"ENGINE_KEY_MASTER_KEY 需 {_KEY_BYTES} 字节（AES-256），当前 {len(key)} 字节"
        )
    return key


def encrypt_secret(engine: str, plaintext: str, master: bytes | None = None, settings: Settings | None = None) -> str:
    """AES-256-GCM 加密。AAD = 引擎名：密文无法在引擎位之间搬移（换行解密必失败）。

    返回 b64(nonce).b64(ciphertext+tag)。两段各自编码——直接拼一个 base64 串再按
    字节切 nonce 会因 padding 把切点错位 1~2 字节。
    """
    if not plaintext:
        raise RequestInvalidError("引擎 Key 不能为空")
    aes = AESGCM(master if master is not None else master_key(settings))
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = aes.encrypt(nonce, plaintext.encode(), engine.encode())
    return base64.b64encode(nonce).decode() + "." + base64.b64encode(ciphertext).decode()


def decrypt_secret(engine: str, secret_ref: str, master: bytes) -> str:
    """解密；密文损坏 / AAD 不匹配 / 主密钥已轮换均抛 RequestInvalidError（fail closed）。

    调用方决定后果：状态上报按「未配置」处理并显式标注，绝不当作已配置。
    """
    try:
        nonce_b64, ct_b64 = secret_ref.split(".", 1)
        plaintext = AESGCM(master).decrypt(
            base64.b64decode(nonce_b64), base64.b64decode(ct_b64), engine.encode()
        )
    except (InvalidTag, LookupError, ValueError, binascii.Error, TypeError) as exc:
        # InvalidTag 直连 Exception（不继承 ValueError）：AAD 不匹配时若漏接，
        # 搬移密文的攻击会以未处理异常(500)而非 fail-closed 告终，必须显式列入。
        raise RequestInvalidError(f"引擎 {engine} 的已登记 Key 不可解（密文损坏或主密钥已轮换）") from exc
    return plaintext.decode()


def resolve_engine_key(
    engine: str,
    settings: Settings | None = None,
    registered: Mapping[str, str] | None = None,
) -> KeyResolution:
    """凭据解析单一谓词：有凭据 / 无凭据 / 凭据来自 env 还是登记表。

    优先级 **registered > env**，并由 source 显式回报哪个生效——登记覆盖 env 必须是
    可见的，「存了但没生效」是最差的失败形态（F-4 教训）。

    位级规则：
      builtin   → 无需 Key，恒 configured（回退通道，不随登记表/env 判定）
      main      → 需 base **且** key（base 永远只认 env，无登记表项）
      coze/dify/fastgpt → 只需 key
      未知引擎位 → 不配置（不臆造，交由调用方走 10005 校验）
    """
    settings = settings or get_settings()
    env_var = _ENV_VARS.get(engine, "")
    if engine == "builtin":
        return KeyResolution("builtin", True, "", None, "")

    key = ""
    source: str | None = None
    if registered:
        candidate = str(registered.get(engine) or "")
        if candidate:
            key, source = candidate, "registered"
    if not key:
        attr = _SETTINGS_ATTRS.get(engine, f"{engine}_api_key")
        candidate = str(getattr(settings, attr, "") or "")
        if candidate:
            key, source = candidate, "env"

    if engine == "main":
        # base 是端点不是凭据，永远只认 env：只有 base 时绝不可判为已配置
        if not str(getattr(settings, "main_kb_api_base", "") or ""):
            key, source = "", None
    return KeyResolution(engine, bool(key), key, source, env_var)


# ---------------------------------------------------------------- 进程内快照（写路径刷新）

_snapshot: dict[str, str] = {}
_snapshot_at: float = 0.0


def snapshot() -> dict[str, str]:
    """当前已登记 Key 快照（engine → 明文）。读时拷贝，防调用方就地改写。"""
    return dict(_snapshot)


def set_snapshot(mapping: Mapping[str, str]) -> None:
    """由服务层在登记/撤销写库后刷新（同一进程内立即可见）。"""
    global _snapshot, _snapshot_at
    _snapshot = {k: str(v) for k, v in mapping.items() if str(v)}
    _snapshot_at = time.monotonic()


def snapshot_age() -> float:
    """快照距上次刷新的秒数（从未刷新 → inf）。多进程部署需外部刷新，本值供观测。"""
    if not _snapshot_at:
        return float("inf")
    return time.monotonic() - _snapshot_at
