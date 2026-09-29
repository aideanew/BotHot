"""R0.5.1（F-4）：knowledge_spaces 加 description 空间简介。

Revises: ab1004t32a

编号避让：SPEC-M3 已把 users.role 列迁移定为 ab1004m3a（SPEC 起草，代码零开工），
本批取 ab1004m5a 避让。

列定义为 nullable 且**不设 server_default**：
- 契约语义上「未填写简介」是合法状态（前端空态显示「（未填写简介）」，
  与「能力未实现」区分），历史行无需回填即合法；
- PG 下 nullable 且无 server_default 的 add_column 是元数据级操作，不重写全表
  （若设 server_default="" 则需回填扫描全表，且会把「从未填写」与「显式清空」压成同值）。
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1004m5a"
down_revision: str | None = "ab1004t32a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_spaces",
        sa.Column("description", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_spaces", "description")
