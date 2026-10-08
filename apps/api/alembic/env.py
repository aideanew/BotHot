from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.db import resolve_database_url
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 迁移目标库：`DATABASE_URL` 优先，缺省回落 alembic.ini（宿主裸跑的 localhost:5433）。
# 容器内该硬编码不可达——compose `migrate` 服务注入 postgres:5432 的连接串。
config.set_main_option(
    "sqlalchemy.url",
    resolve_database_url(config.get_main_option("sqlalchemy.url")),
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
