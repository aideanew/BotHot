"""AB-P004 P1 公共库拷贝式：knowledge_spaces 加 is_public/owner_type/engine/engine_kb_id，
knowledge_documents 加 source(copy默认|link预留)。

Revises: ab1004p0a
回滚纪律：alembic downgrade -1 删全部 5 列；公共库数据（is_public=1 行）回滚后需手工清理。
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1004p1a"
down_revision: str = "ab1004p0a"
branch_labels = None
depends_on = None


def _has_cols(bind, table: str, names: list[str]) -> set[str]:
    import sqlalchemy

    inspector = sqlalchemy.inspect(bind)
    return {c["name"] for c in inspector.get_columns(table)} & set(names)


def upgrade() -> None:
    bind = op.get_bind()
    sp = _has_cols(bind, "knowledge_spaces", ["is_public", "owner_type", "engine", "engine_kb_id"])
    doc = _has_cols(bind, "knowledge_documents", ["source"])
    if "is_public" not in sp:
        op.add_column(
            "knowledge_spaces",
            sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    if "owner_type" not in sp:
        op.add_column(
            "knowledge_spaces",
            sa.Column("owner_type", sa.String(length=16), nullable=False, server_default="user"),
        )
    if "engine" not in sp:
        op.add_column(
            "knowledge_spaces",
            sa.Column("engine", sa.String(length=32), nullable=False, server_default="builtin"),
        )
    if "engine_kb_id" not in sp:
        op.add_column(
            "knowledge_spaces",
            sa.Column("engine_kb_id", sa.String(length=128), nullable=False, server_default=""),
        )
    if "source" not in doc:
        op.add_column(
            "knowledge_documents",
            sa.Column("source", sa.String(length=16), nullable=False, server_default="copy"),
        )


def downgrade() -> None:
    op.drop_column("knowledge_documents", "source")
    op.drop_column("knowledge_spaces", "engine_kb_id")
    op.drop_column("knowledge_spaces", "engine")
    op.drop_column("knowledge_spaces", "owner_type")
    op.drop_column("knowledge_spaces", "is_public")
