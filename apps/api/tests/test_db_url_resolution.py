"""迁移目标库解析契约（compose `migrate` 服务前置）。

锁定：`DATABASE_URL` 必须压过 `alembic.ini` 里只有宿主裸跑时成立的硬编码 `localhost:5433`，
否则容器内迁移会指向不存在的主机而静默失败。
"""

from app.db import resolve_database_url

CONTAINER_URL = "postgresql+psycopg://bothot:bothot@postgres:5432/bothot"
HOST_URL = "postgresql+psycopg://bothot:bothot@localhost:5433/bothot"


def test_database_url_env_wins_over_ini_default() -> None:
    assert resolve_database_url(HOST_URL, environ={"DATABASE_URL": CONTAINER_URL}) == CONTAINER_URL


def test_empty_database_url_falls_back_to_ini_default() -> None:
    """空串视为未设置（compose `${VAR:-}` 展开的空值不得击穿到宿主硬编码之外）。"""
    assert resolve_database_url(HOST_URL, environ={"DATABASE_URL": ""}) == HOST_URL


def test_falls_back_to_settings_when_no_env_and_no_default() -> None:
    assert resolve_database_url(None, environ={})


def test_explicit_default_wins_without_env() -> None:
    assert resolve_database_url(HOST_URL, environ={}) == HOST_URL
