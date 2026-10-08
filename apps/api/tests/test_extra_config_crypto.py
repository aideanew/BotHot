"""S2.1 extra_config 加密测试：域分隔 roundtrip / 存量明文兼容 / 接线与迁移纪律。

纯单元（master 显式传参，不依赖 env/PG）+ 迁移文件静态断言（fail-closed 纪律）。
"""

from __future__ import annotations

import base64
import os

import pytest

from app.core.errors import RequestInvalidError
from app.core.secret_crypto import (
    decrypt_channel_secret,
    decrypt_extra_config,
    encrypt_channel_secret,
    encrypt_extra_config,
)

_MASTER = base64.b64encode(os.urandom(32)).decode()


def _master() -> bytes:
    return base64.b64decode(_MASTER)


def test_roundtrip_preserves_json_payload():
    raw = '{"app_secret":"sec-abc","token":"t1"}'
    ct = encrypt_extra_config("ch-1", raw, master=_master())
    assert ct != raw and "." in ct and not ct.startswith("{")
    assert decrypt_extra_config("ch-1", ct, master=_master()) == raw


def test_domain_separation_from_secret_enc():
    """extra_config 密文用 secret_enc 的 AAD（channel_id）解密必须失败——两列不可互搬。"""
    raw = '{"k":"v"}'
    ct_extra = encrypt_extra_config("ch-1", raw, master=_master())
    ct_secret = encrypt_channel_secret("ch-1", raw, master=_master())
    assert ct_extra != ct_secret  # nonce 随机 + AAD 不同（确定性断言靠下方解密失败）
    with pytest.raises(RequestInvalidError):
        decrypt_channel_secret("ch-1", ct_extra, master=_master())
    with pytest.raises(RequestInvalidError):
        decrypt_extra_config("ch-1", encrypt_channel_secret("ch-1", raw, master=_master()), master=_master())


def test_aad_binds_channel_id():
    ct = encrypt_extra_config("ch-1", '{"k":"v"}', master=_master())
    with pytest.raises(RequestInvalidError):
        decrypt_extra_config("ch-2", ct, master=_master())


def test_legacy_plaintext_passthrough():
    """存量明文 JSON（含默认 "{}"）兼容读原样返回——迁移前/回滚场景不受影响。"""
    for raw in ('{}', '{"app_secret":"x"}', '{"v":"1.2"}', '{"url":"http://a.b/c"}'):
        assert decrypt_extra_config("ch-1", raw, master=_master()) == raw


def test_empty_short_circuits():
    assert encrypt_extra_config("ch-1", "", master=_master()) == ""
    assert decrypt_extra_config("ch-1", "", master=_master()) == ""


def test_wrong_master_fails_closed():
    other = base64.b64encode(os.urandom(32)).decode()
    ct = encrypt_extra_config("ch-1", '{"k":"v"}', master=_master())
    with pytest.raises(RequestInvalidError):
        decrypt_extra_config("ch-1", ct, master=base64.b64decode(other))


def test_migration_discipline_static_asserts():
    """迁移文件静态纪律：fail-closed 中止 + 域分隔 AAD + 拒绝降级。"""
    import pathlib

    src = (
        pathlib.Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "ab1005w5b_extra_config_encrypt.py"
    ).read_text(encoding="utf-8")
    assert 'os.environ.get("PUSH_SECRET_MASTER_KEY"' in src  # 读主密钥
    assert "fail-closed" in src and "中止" in src  # 缺钥中止而非跳过
    assert 'f"{channel_id}:extra_config".encode()' in src  # 域分隔 AAD
    assert "不支持降级" in src  # 单向加固
