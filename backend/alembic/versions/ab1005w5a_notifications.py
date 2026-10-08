"""R1.2a：站内通知持久化底座（离线补投存储层）。

web provider（providers/push/web.py）走 Redis pub/sub 是 fire-and-forget——用户离线
（无 SSE 订阅者）时通知永久丢失。本迁移建 notifications 表，把每条站内通知落库，
作为后续 GET /system/notifications/history（R1.2b）离线补投的存储底座；SSE 实时侧不变。

- 收件人锚 = sub（SSO 身份锚点，与 get_current_sub / 主频道命名一致）；广播通知 sub=""
  且 is_broadcast=True，历史查询按 (sub == 当前用户 OR is_broadcast) 覆盖定向 + 广播两类。
- (sub, created_at) 复合索引支撑「按用户取最近 N 条倒序」热查询走索引。
- channel_type / 各业务字段用 String 不枚举，未来扩渠道或加载荷零迁移。
- NOT NULL 标量列给 server_default，保证裸 SQL 插入与 ORM Python 默认两侧一致。

Revision ID: ab1005w5a
Revises: ab1004w4a（链序 ...w3a → w4a → w5a，保持单头）
Create Date: 2026-10-08
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1005w5a"
down_revision: str | None = "ab1004w4a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sub", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("is_broadcast", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("channel_type", sa.String(length=32), nullable=False, server_default="web"),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("space_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("doc_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
    )
    op.create_index("ix_notifications_sub_created", "notifications", ["sub", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_sub_created", table_name="notifications")
    op.drop_table("notifications")
