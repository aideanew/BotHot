"""需求「每天 10 点整号采集」：source_subscriptions 加固定时点锚 sync_anchor_hour。

Revises: ab1004f11a

可空列：NULL = 滑动窗口（now + interval × 退避，历史行为），非 NULL = 每天该小时触发
（调度器时区口径，见 app.services.scheduler）。可空而非带默认值，是为了让既有订阅
**保持原语义**——若给 server_default，历史行的 NULL 会被填成某个小时，等于静默把
所有订阅改成定点触发。
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1004s1a"
down_revision: str | None = "ab1004f11a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_subscriptions",
        sa.Column("sync_anchor_hour", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_subscriptions", "sync_anchor_hour")
