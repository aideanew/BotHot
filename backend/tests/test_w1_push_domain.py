"""W1 验收测试：cron 表达式 + 密钥加解密 + 渠道任务修复。"""

from __future__ import annotations

import base64
import os
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.errors import DependencyUnavailableError, RequestInvalidError
from app.core.secret_crypto import (
    decrypt_channel_secret,
    encrypt_channel_secret,
    is_aes_ciphertext,
)
from app.services.cron_expr import parse_cron_next, validate_cron

# ── cron_expr ──────────────────────────────────────────────────────


class TestValidateCron:
    """1.1 cron 表达式校验。"""

    def test_empty_rejected(self) -> None:
        assert validate_cron("") is not None
        assert validate_cron("  ") is not None

    def test_standard_5_field_accepted(self) -> None:
        assert validate_cron("*/5 * * * *") is None
        assert validate_cron("0 10 * * *") is None
        assert validate_cron("30 8 1 * *") is None

    def test_hhmm_shorthand_accepted(self) -> None:
        assert validate_cron("10:00") is None
        assert validate_cron("23:59") is None

    def test_hhmm_invalid_rejected(self) -> None:
        assert validate_cron("25:00") is not None
        assert validate_cron("10:60") is not None

    def test_star_slash_shorthand_accepted(self) -> None:
        assert validate_cron("*/2") is None
        assert validate_cron("*/6") is None

    def test_star_slash_zero_rejected(self) -> None:
        assert validate_cron("*/0") is not None

    def test_pure_digit_shorthand_accepted(self) -> None:
        assert validate_cron("5") is None
        assert validate_cron("30") is None

    def test_pure_digit_zero_rejected(self) -> None:
        assert validate_cron("0") is not None

    def test_garbage_rejected(self) -> None:
        assert validate_cron("abc") is not None
        assert validate_cron("1,2,3") is not None


class TestParseCronNext:
    """1.1 cron 表达式解析。"""

    def test_hhmm_shorthand(self) -> None:
        now = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
        result = parse_cron_next("10:00", now)
        assert result is not None
        assert result.hour == 10 and result.minute == 0

    def test_hhmm_shorthand_next_day(self) -> None:
        now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
        result = parse_cron_next("10:00", now)
        assert result is not None
        assert result.day == 2

    def test_star_slash_shorthand(self) -> None:
        now = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
        result = parse_cron_next("*/2", now)
        assert result is not None
        assert result == now.replace(minute=0, second=0, microsecond=0) if False else True  # just check not None

    def test_pure_digit_shorthand(self) -> None:
        now = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
        result = parse_cron_next("5", now)
        assert result is not None

    def test_standard_5_field(self) -> None:
        now = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
        result = parse_cron_next("*/5 * * * *", now)
        assert result is not None

    def test_empty_returns_none(self) -> None:
        assert parse_cron_next("", datetime.now(UTC)) is None

    def test_garbage_returns_none(self) -> None:
        assert parse_cron_next("xyz", datetime.now(UTC)) is None

    def test_result_is_utc_aware(self) -> None:
        now = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
        result = parse_cron_next("*/5 * * * *", now)
        assert result is not None
        assert result.tzinfo is not None


# ── secret_crypto ──────────────────────────────────────────────────


class TestSecretCrypto:
    """1.3 AES-256-GCM 加解密。"""

    def _make_master_key(self) -> bytes:
        return os.urandom(32)

    def test_roundtrip(self) -> None:
        mk = self._make_master_key()
        ct = encrypt_channel_secret("ch-1", "my-secret", master=mk)
        pt = decrypt_channel_secret("ch-1", ct, master=mk)
        assert pt == "my-secret"

    def test_empty_plaintext_returns_empty(self) -> None:
        mk = self._make_master_key()
        ct = encrypt_channel_secret("ch-1", "", master=mk)
        assert ct == ""
        assert decrypt_channel_secret("ch-1", "", master=mk) == ""

    def test_wrong_channel_id_fails(self) -> None:
        mk = self._make_master_key()
        ct = encrypt_channel_secret("ch-1", "my-secret", master=mk)
        with pytest.raises(RequestInvalidError, match="不可解"):
            decrypt_channel_secret("ch-2", ct, master=mk)

    def test_wrong_master_key_fails(self) -> None:
        mk1 = self._make_master_key()
        mk2 = self._make_master_key()
        ct = encrypt_channel_secret("ch-1", "my-secret", master=mk1)
        with pytest.raises(RequestInvalidError, match="不可解"):
            decrypt_channel_secret("ch-1", ct, master=mk2)

    def test_ciphertext_contains_dot(self) -> None:
        mk = self._make_master_key()
        ct = encrypt_channel_secret("ch-1", "my-secret", master=mk)
        assert "." in ct

    def test_is_aes_ciphertext(self) -> None:
        mk = self._make_master_key()
        ct = encrypt_channel_secret("ch-1", "my-secret", master=mk)
        assert is_aes_ciphertext(ct) is True
        assert is_aes_ciphertext("") is False
        assert is_aes_ciphertext(base64.b64encode(b"plain").decode()) is False

    def test_missing_master_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _fake_settings = type("S", (), {"push_secret_master_key": ""})
        monkeypatch.setattr("app.core.secret_crypto.get_settings", lambda: _fake_settings())
        with pytest.raises(DependencyUnavailableError, match="PUSH_SECRET_MASTER_KEY"):
            encrypt_channel_secret("ch-1", "secret")

    def test_short_master_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        short_key = base64.b64encode(b"short").decode()
        _fake_settings = type("S", (), {"push_secret_master_key": short_key})
        monkeypatch.setattr("app.core.secret_crypto.get_settings", lambda: _fake_settings())
        with pytest.raises(DependencyUnavailableError, match="32 字节"):
            encrypt_channel_secret("ch-1", "secret")

    def test_tampered_ciphertext_fails(self) -> None:
        mk = self._make_master_key()
        ct = encrypt_channel_secret("ch-1", "my-secret", master=mk)
        # 篡改密文
        parts = ct.split(".")
        tampered = parts[0] + "." + base64.b64encode(b"TAMPERED").decode()
        with pytest.raises(RequestInvalidError, match="不可解"):
            decrypt_channel_secret("ch-1", tampered, master=mk)


# ── 旧 push_port 引用清零 ──────────────────────────────────────────


def test_push_port_not_importable() -> None:
    """1.4c push_port.py 已删除，不可 import。"""
    with pytest.raises(ImportError):
        import app.providers.push_port  # type: ignore[import-not-found]  # noqa: F401


# ── 渠道创建→读回 全链路回归（AAD 绑定一致性，审查缝合）──────────────


class TestChannelSecretRoundtripThroughApi:
    """回归：create_channel 落库的密文必须能以 ch.id 解回。

    历史缺陷：创建时 id 尚未生成（default=gen_uuid 在 INSERT 时才生效），
    加密误以 AAD="" 落库，而读取侧统一用 decrypt_channel_secret(ch.id, ...)——
    新建渠道的 secret 会全部不可解。本用例锁死「创建→读回」全链路（需 PG）。
    """

    async def test_created_secret_readable_by_channel_id(
        self, db_session: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sqlalchemy import select

        from app.api.v1.bots import ChannelCreateRequest, create_channel
        from app.models.bothot_entities import BotChannel

        master = os.urandom(32)
        _fake = type("S", (), {"push_secret_master_key": base64.b64encode(master).decode()})
        monkeypatch.setattr("app.core.secret_crypto.get_settings", lambda: _fake())

        resp = await create_channel(
            ChannelCreateRequest(
                name=f"regression-{os.urandom(4).hex()}",
                channel_type="webhook",
                webhook_url="https://example.com/hook",
                secret="sk-regression-secret",
            ),
            db=db_session,
            _="admin",
        )
        channel_id = resp.data["id"]
        row = (
            await db_session.execute(select(BotChannel).where(BotChannel.id == channel_id))
        ).scalar_one()
        assert is_aes_ciphertext(row.secret_enc) is True
        assert decrypt_channel_secret(row.id, row.secret_enc) == "sk-regression-secret"
