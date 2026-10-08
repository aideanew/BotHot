"""WB（审查补完）：推送投递重试字段 + 4 个无索引 FK 补索引。

- push_tasks 加 retry_count / next_retry_at：重试态挂任务而非日志——PushLog 只记
  投递事实，调度语义（下次重投时点）归任务行；claim 谓词按 next_retry_at 拾取。
- FK 索引补齐（audit 发现 4 个无索引外键，JOIN/按外键过滤全表扫）：
  push_tasks.space_id / push_tasks.created_by / push_logs.push_task_id /
  hot_topics.center_asset_id。索引命名对齐 SQLAlchemy 默认约定（ix_<表>_<列>），
  与模型侧 index=True 声明一一对应。

Revision ID: ab1004w4a
Revises: ab1004w3a（链序 w1a → w2a → w3a → w4a）
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1004w4a"
down_revision: str | None = "ab1004w3a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "push_tasks",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "push_tasks",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_push_tasks_space_id", "push_tasks", ["space_id"])
    op.create_index("ix_push_tasks_created_by", "push_tasks", ["created_by"])
    op.create_index("ix_push_logs_push_task_id", "push_logs", ["push_task_id"])
    op.create_index("ix_hot_topics_center_asset_id", "hot_topics", ["center_asset_id"])


def downgrade() -> None:
    op.drop_index("ix_hot_topics_center_asset_id", table_name="hot_topics")
    op.drop_index("ix_push_logs_push_task_id", table_name="push_logs")
    op.drop_index("ix_push_tasks_created_by", table_name="push_tasks")
    op.drop_index("ix_push_tasks_space_id", table_name="push_tasks")
    op.drop_column("push_tasks", "next_retry_at")
    op.drop_column("push_tasks", "retry_count")
