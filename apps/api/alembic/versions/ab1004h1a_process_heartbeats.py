"""R7.7：process_heartbeats 常驻进程心跳表（scheduler / worker 存活可观测）。

Revises: ab1004s1a
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1004h1a"
down_revision: str | None = "ab1004s1a"
branch_labels = None
depends_on = None

TABLE = "process_heartbeats"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in set(inspector.get_table_names()):
        op.create_table(
            TABLE,
            sa.Column("process_key", sa.String(length=32), nullable=False),
            sa.Column(
                "last_heartbeat_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "last_detail",
                sa.String(length=512),
                server_default=sa.text("''"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("process_key"),
        )
    else:
        # 幂等：表已存在（如早前手工建过）时确保 NOT NULL 与默认值到位，
        # 否则 upsert 的 EXCLUDED 语义与读侧的 age 计算都会在缺列时静默失真。
        cols = {c["name"]: c for c in inspector.get_columns(TABLE)}
        for col in ("process_key", "last_heartbeat_at", "last_detail"):
            if col not in cols:
                raise sa.exc.InvalidRequestError(f"{TABLE} 缺列 {col}：手工建表版本过旧")


def downgrade() -> None:
    # 纯运维观测数据，无业务含义；删除后读侧对每个进程报「从未启动」，不会误判为健康。
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE in set(inspector.get_table_names()):
        op.drop_table(TABLE)
