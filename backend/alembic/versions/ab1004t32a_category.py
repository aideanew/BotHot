"""T3.2.1（C-8/G6）：content_assets 加 category 分类标签（站内筛选；规则版赋值）。

Revises: ab1004d04a
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1004t32a"
down_revision: str | None = "ab1004d04a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_assets",
        sa.Column("category", sa.String(length=32), nullable=False, server_default=""),
    )
    op.create_index("ix_content_assets_category", "content_assets", ["category"])


def downgrade() -> None:
    op.drop_index("ix_content_assets_category", table_name="content_assets")
    op.drop_column("content_assets", "category")
