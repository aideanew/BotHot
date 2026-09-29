"""R4.4（F-11）：knowledge_documents 加 content_hash——跨空间 stale 判定的内容指纹。

Revises: ab1004m3b

F-11：`content_assets` 按 `uq_asset_source_external` 全局共享（无 user_id、无空间列），
号主改文时覆写的是所有空间共用的那一行。旧 `mark_stale_docs(asset_id, space_id)` 按
**调用方**空间过滤，他人空间的 doc 会静默指向已变正文（无错误、无告警、无 stale 标记）。
本列让判定轴从「谁的 doc」换成「该 doc 入库时的正文是否仍是当前正文」。

server_default 只用于通过 NOT NULL 约束，回填后立即 DROP：此后任何不写指纹的插入直接
失败，防止「静默空指纹」把跨空间判定整体废掉。
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1004f11a"
down_revision: str | None = "ab1004m3b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("content_hash", sa.String(length=64), nullable=False, server_default=""),
    )
    # 回填假设：存量 doc 与其资产的当前正文同步（迁移前该分叉窗口从未被观测到）。
    # 代价诚实记录：若确有存量已分叉的 doc，本次迁移不会替它标 stale——不静默销毁索引。
    op.execute(
        "UPDATE knowledge_documents d SET content_hash = a.content_hash "
        "FROM content_assets a WHERE a.id = d.asset_id"
    )
    op.execute("ALTER TABLE knowledge_documents ALTER COLUMN content_hash DROP DEFAULT")


def downgrade() -> None:
    op.drop_column("knowledge_documents", "content_hash")
