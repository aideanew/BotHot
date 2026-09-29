"""AB-P004 P0 资产缓存：content_assets 加 hit_count（复用命中计数）。

Revises: 05a5a856c37b
"""
import sqlalchemy as sa

from alembic import op

revision: str = 'ab1004p0a'
down_revision: str | None = '05a5a856c37b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 列缺失时幂等补列（PG 无 ADD COLUMN IF NOT EXISTS，按列名探测）
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("content_assets")}
    if "hit_count" not in cols:
        op.add_column(
            "content_assets",
            sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        )
    # 回滚纪律：drop hit_count 即回滚；本列只增不改语义，无数据迁移


def downgrade() -> None:
    op.drop_column("content_assets", "hit_count")
