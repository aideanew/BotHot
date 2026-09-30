"""WC 3.1 连接池参数化单测：默认值 / env 覆盖 / recycle 生效（配置断言）。"""

from __future__ import annotations

import importlib

from app import db


def test_pool_defaults_match_history() -> None:
    """默认 pool_size=5 / max_overflow=5 / pool_recycle=1800（与历史一致 + 新增 recycle）。"""
    assert db._DB_POOL_SIZE == 5
    assert db._DB_MAX_OVERFLOW == 5
    assert db._DB_POOL_RECYCLE == 1800  # 30 分钟前置回收防 idle 断连


def test_pool_env_override(monkeypatch) -> None:  # noqa: ANN001
    """DB_POOL_SIZE/MAX_OVERFLOW/POOL_RECYCLE 环境变量可覆盖（运维调参无需改代码）。"""
    monkeypatch.setenv("DB_POOL_SIZE", "10")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "20")
    monkeypatch.setenv("DB_POOL_RECYCLE", "600")
    importlib.reload(db)
    try:
        assert db._DB_POOL_SIZE == 10
        assert db._DB_MAX_OVERFLOW == 20
        assert db._DB_POOL_RECYCLE == 600
    finally:
        monkeypatch.delenv("DB_POOL_SIZE", raising=False)
        monkeypatch.delenv("DB_MAX_OVERFLOW", raising=False)
        monkeypatch.delenv("DB_POOL_RECYCLE", raising=False)
        importlib.reload(db)  # 恢复默认，避免污染同进程其他用例


def test_engine_pool_size_reflects_config() -> None:
    """create_engine_and_session 产出的引擎池 size 取模块常量（参数生效）。"""
    engine, _factory = db.create_engine_and_session()
    # AsyncEngine.pool 为底层连接池；QueuePool.size() 返回配置的 pool_size
    assert engine.pool.size() == db._DB_POOL_SIZE
