"""AB-P004 D-04/L-01：short_link_maps 短链→长链 article_key 映射（幂等加列+回滚）。

Revises: ab1004p1a
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1004d04a"
down_revision: str = "ab1004p1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    import sqlalchemy

    inspector = sqlalchemy.inspect(bind)
    # 修复（2026-09-22，全新库首跑暴露）：PGInspector 无 get_tables()，
    # 正确 API 是 get_table_names()（直接返回表名列表，非 dict 行）
    tables = set(inspector.get_table_names())
    if "short_link_maps" not in tables:
        op.create_table(
            "short_link_maps",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("short_key", sa.String(length=128), nullable=False),
            sa.Column("article_key", sa.String(length=128), nullable=False),
            sa.Column("biz", sa.String(length=128), nullable=False, server_default=""),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("short_key", name="uq_shortlink_key"),
        )
        op.create_index(op.f("ix_short_link_maps_short_key"), "short_link_maps", ["short_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_short_link_maps_short_key"), table_name="short_link_maps")
    op.drop_table("short_link_maps")
