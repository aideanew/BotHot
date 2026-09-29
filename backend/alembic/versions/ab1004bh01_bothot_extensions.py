"""BotHot 扩展表：多渠道机器人、推送任务/日志、热点聚簇、日报、Feed 流。

Revises: ab1004h1a
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1004bh01"
down_revision: str | None = "ab1004h1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. bot_channels
    op.create_table(
        "bot_channels",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("webhook_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("secret_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("extra_config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("total_push_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_push_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_bot_channel_name"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_bot_channels_channel_type", "bot_channels", ["channel_type"])
    op.create_index("ix_bot_channels_status", "bot_channels", ["status"])
    op.create_index("ix_bot_channels_user_id", "bot_channels", ["user_id"])

    # 2. push_tasks
    op.create_table(
        "push_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("bot_channel_id", sa.String(length=36), nullable=False),
        sa.Column("trigger_type", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("cron_expr", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("trigger_event", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("content_template", sa.Text(), nullable=False, server_default=""),
        sa.Column("space_id", sa.String(length=36), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["bot_channel_id"], ["bot_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["space_id"], ["knowledge_spaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_push_tasks_bot_channel_id", "push_tasks", ["bot_channel_id"])
    op.create_index("ix_push_tasks_trigger_type", "push_tasks", ["trigger_type"])
    op.create_index("ix_push_tasks_next_run_at", "push_tasks", ["next_run_at"])
    op.create_index("ix_push_tasks_status", "push_tasks", ["status"])

    # 3. push_logs
    op.create_table(
        "push_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("bot_channel_id", sa.String(length=36), nullable=False),
        sa.Column("push_task_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("content_preview", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("response_summary", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["bot_channel_id"], ["bot_channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["push_task_id"], ["push_tasks.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_push_logs_bot_channel_id", "push_logs", ["bot_channel_id"])
    op.create_index("ix_push_logs_status", "push_logs", ["status"])

    # 4. hot_topics
    op.create_table(
        "hot_topics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("center_asset_id", sa.String(length=36), nullable=True),
        sa.Column("hot_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="rising"),
        sa.Column("topic_date", sa.String(length=10), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["center_asset_id"], ["content_assets.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_hot_topics_hot_score", "hot_topics", ["hot_score"])
    op.create_index("ix_hot_topics_status", "hot_topics", ["status"])
    op.create_index("ix_hot_topics_topic_date", "hot_topics", ["topic_date"])
    op.create_index("ix_hot_topics_category", "hot_topics", ["category"])

    # 5. hot_topic_articles
    op.create_table(
        "hot_topic_articles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("hot_topic_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["hot_topic_id"], ["hot_topics.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["content_assets.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("hot_topic_id", "asset_id", name="uq_hot_topic_asset"),
    )
    op.create_index("ix_hot_topic_articles_hot_topic_id", "hot_topic_articles", ["hot_topic_id"])
    op.create_index("ix_hot_topic_articles_asset_id", "hot_topic_articles", ["asset_id"])

    # 6. daily_reports
    op.create_table(
        "daily_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("report_date", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("content_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("topic_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("generated_by", sa.String(length=16), nullable=False, server_default="auto"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("report_date", name="uq_daily_report_date"),
    )
    op.create_index("ix_daily_reports_report_date", "daily_reports", ["report_date"])
    op.create_index("ix_daily_reports_status", "daily_reports", ["status"])

    # 7. feed_items
    op.create_table(
        "feed_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("item_type", sa.String(length=16), nullable=False, server_default="article"),
        sa.Column("ref_id", sa.String(length=36), nullable=False, server_default=""),
        sa.Column("title", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("category", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_feed_items_item_type", "feed_items", ["item_type"])
    op.create_index("ix_feed_items_ref_id", "feed_items", ["ref_id"])
    op.create_index("ix_feed_items_score", "feed_items", ["score"])
    op.create_index("ix_feed_items_category", "feed_items", ["category"])


def downgrade() -> None:
    op.drop_table("feed_items")
    op.drop_table("daily_reports")
    op.drop_table("hot_topic_articles")
    op.drop_table("hot_topics")
    op.drop_table("push_logs")
    op.drop_table("push_tasks")
    op.drop_table("bot_channels")
