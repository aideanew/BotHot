"""启动期生产配置守卫（R4.3.3）。

锁定两条方向相反的性质，缺一即出事：
- 生产红线**必须**在 production 生效（占位密钥/明文 cookie/内存会话带着病上线）；
- 生产红线**不得**卡住本地开发（这些占位值在 development 是设计内默认）。

WB（审查补完）：新增两把落库加密主密钥守卫——PUSH_SECRET_MASTER_KEY（渠道密钥
AES）与 ENGINE_KEY_MASTER_KEY（引擎 Key 登记 AES）。运行时本就 fail-closed，
守卫只是把失败从「首次投递/首次登记」提前到「启动时」显式暴露。
"""

from __future__ import annotations

import base64

import pytest

from app.core.config import Settings, assert_production_ready

# 守卫覆盖的 env 判据（与 core.config.production_guard_violations 一一对应）
GUARDED_ENV = (
    "OIDC_CLIENT_SECRET",
    "SESSION_COOKIE_SECURE",
    "SESSION_STORE_BACKEND",
    "OIDC_ISSUER_EXPECTED",
    "OIDC_AUDIENCE_EXPECTED",
    "PUSH_SECRET_MASTER_KEY",
    "ENGINE_KEY_MASTER_KEY",
)

_VALID_PUSH_KEY = base64.b64encode(b"p" * 32).decode()
_VALID_ENGINE_KEY = base64.b64encode(b"e" * 32).decode()


def _prod(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    """构造 production 配置：先清掉守卫相关 env，再按用例覆盖。"""
    for key in GUARDED_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]  # pydantic-settings 运行时合法


def test_dev_mode_ignores_production_redlines() -> None:
    """开发期全占位值 → 零违规：不能拿生产红线让本地起不来。"""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.app_env == "development"
    assert settings.production_guard_violations() == []


@pytest.mark.parametrize(
    ("env", "name"),
    [
        ({"OIDC_CLIENT_SECRET": "change-me"}, "OIDC_CLIENT_SECRET"),
        ({"SESSION_COOKIE_SECURE": "false"}, "SESSION_COOKIE_SECURE"),
        ({"SESSION_STORE_BACKEND": "memory"}, "SESSION_STORE_BACKEND"),
        ({"OIDC_ISSUER_EXPECTED": ""}, "OIDC_ISSUER_EXPECTED"),
        ({"OIDC_AUDIENCE_EXPECTED": ""}, "OIDC_AUDIENCE_EXPECTED"),
        ({"PUSH_SECRET_MASTER_KEY": ""}, "PUSH_SECRET_MASTER_KEY"),
        ({"ENGINE_KEY_MASTER_KEY": ""}, "ENGINE_KEY_MASTER_KEY"),
    ],
)
def test_each_production_violation_is_reported(monkeypatch: pytest.MonkeyPatch, env: dict[str, str], name: str) -> None:
    """逐条独立触发——漏报任意一项等于留一个上线口子。

    其余项显式给合格值（含两把合法 32 字节主密钥），确保本用例只坏那一项。
    """
    settings = _prod(
        monkeypatch,
        **{
            "OIDC_CLIENT_SECRET": "s3cret-not-change-me",
            "SESSION_COOKIE_SECURE": "true",
            "SESSION_STORE_BACKEND": "redis",
            "OIDC_ISSUER_EXPECTED": "https://issuer.example.com",
            "OIDC_AUDIENCE_EXPECTED": "bothot",
            "PUSH_SECRET_MASTER_KEY": _VALID_PUSH_KEY,
            "ENGINE_KEY_MASTER_KEY": _VALID_ENGINE_KEY,
            **env,
        },
    )
    violations = settings.production_guard_violations()
    assert len(violations) == 1
    assert name in violations[0], violations


def test_production_all_default_is_seven_violation(monkeypatch: pytest.MonkeyPatch) -> None:
    """生产照抄默认值 → 七项全中（含两把空主密钥——最常见的误配形态）。"""
    settings = _prod(monkeypatch)
    assert len(settings.production_guard_violations()) == 7


def test_production_fully_configured_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _prod(
        monkeypatch,
        OIDC_CLIENT_SECRET="s3cret-not-change-me",
        SESSION_COOKIE_SECURE="true",
        SESSION_STORE_BACKEND="redis",
        OIDC_ISSUER_EXPECTED="https://issuer.example.com",
        OIDC_AUDIENCE_EXPECTED="bothot",
        PUSH_SECRET_MASTER_KEY=_VALID_PUSH_KEY,
        ENGINE_KEY_MASTER_KEY=_VALID_ENGINE_KEY,
    )
    assert settings.production_guard_violations() == []
    assert_production_ready(settings)


def test_empty_client_secret_also_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """空串同占位值同罪：都等于「没有密钥」。"""
    settings = _prod(
        monkeypatch,
        OIDC_CLIENT_SECRET="",
        SESSION_COOKIE_SECURE="true",
        SESSION_STORE_BACKEND="redis",
        PUSH_SECRET_MASTER_KEY=_VALID_PUSH_KEY,
        ENGINE_KEY_MASTER_KEY=_VALID_ENGINE_KEY,
    )
    assert "OIDC_CLIENT_SECRET" in settings.production_guard_violations()[0]


def test_app_env_is_case_and_whitespace_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    """` Production ` / `PRODUCTION` 都算生产——大小写与空格差异不该成为绕过通道。"""
    for value in ("PRODUCTION", " Production ", "Production"):
        monkeypatch.setenv("APP_ENV", value)
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        assert settings.production_guard_violations(), f"app_env={value!r} 未被识别为生产"


def test_assert_production_ready_raises_with_all_violations(monkeypatch: pytest.MonkeyPatch) -> None:
    """fail fast 的错误信息必须列出**全部**违规项（逐条修比改一次重启一次快）。"""
    settings = _prod(monkeypatch)
    with pytest.raises(RuntimeError) as exc:
        assert_production_ready(settings)
    message = str(exc.value)
    assert "OIDC_CLIENT_SECRET" in message
    assert "SESSION_COOKIE_SECURE" in message
    assert "SESSION_STORE_BACKEND" in message
    assert "OIDC_ISSUER_EXPECTED" in message
    assert "OIDC_AUDIENCE_EXPECTED" in message
    assert "PUSH_SECRET_MASTER_KEY" in message
    assert "ENGINE_KEY_MASTER_KEY" in message
