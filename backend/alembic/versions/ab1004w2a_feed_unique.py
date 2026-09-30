"""W2：feed_items 加 (item_type, ref_id) 唯一约束（upsert 语义基础）。

热点聚簇/日报重跑时由 feed_service 覆盖更新同 (item_type, ref_id) 行，不产生重复。
feed_items 此前为死表（无任何写入路径），不存在历史重复行，直接建约束安全。

Revises: ab1004w1a（审查者重连：并行三迁移原均 off ab1004bh01 成 multi-head，链序 w1a → w2a → w3a）
"""
from alembic import op

revision: str = "ab1004w2a"
down_revision: str | None = "ab1004w1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_feed_item_type_ref", "feed_items", ["item_type", "ref_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_feed_item_type_ref", "feed_items", type_="unique")
