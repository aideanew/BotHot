"""push_events outbox 表。

Revision ID: ab1004w3a
Revises: ab1004w2a（审查者重连：链序 w1a → w2a → w3a）
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1004w3a"
down_revision: str | None = "ab1004w2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False, server_default=""),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_push_events_event_type", "push_events", ["event_type"])
    op.create_index("ix_push_events_consumed_at", "push_events", ["consumed_at"])


def downgrade() -> None:
    op.drop_table("push_events")
