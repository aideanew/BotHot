"""STEP-04 S4.2.1：清单加规范键 `article_key` + JobItem 加关联 `manifest_id`（纯 DDL）。

**两列都可空，且不填默认值**——这是裁决 D-V9-04 的落点，不是随手选的：
- `""` 不是合法 `ArticleKey`（`app/contracts/collection.py:40-48` 要求 `b:`/`s:`/`h:` 前缀且 ≥8），
  给存量行灌 `""` 等于**造一个非法身份**：它会作为一个真实键参与 Diff 比较，
  于是所有未回填的行互相"撞"在同一个键上——比 NULL 表达的"尚无身份"坏得多。
- 唯一正确的回填值是 `canonical_article_key(url)`，而这支算法自 STEP-02 起只有一个真源（Python）。
  在 SQL 里用 `pgcrypto.digest()` 复刻它，就是再造一份实现——正是 S2.3.3 漂移守卫要消灭的那类东西
  （两份实现各自演化 ⇒ 同一 URL 算出两个键，是本仓库反复付费学到的那一课）。
⇒ 本迁移只建形状；存量回填归 **STEP-07**（用真函数跑），写侧从 S4.3 起对新行一律填。

索引只建非唯一的 `(source_id, article_key)`：卡面 S4.2.1 要求的就这个。
**不顺手加唯一约束**——存量里"同篇多行"是旧末段键非单射留下的既成事实，建约束会让迁移当场失败；
"同篇该不该唯一"要等 STEP-07 把存量读完才有资格判。

Revises: ab1005w5b
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "ab1006c1a"
down_revision: str | None = "ab1005w5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "article_manifests",
        sa.Column("article_key", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_manifest_source_article_key",
        "article_manifests",
        ["source_id", "article_key"],
    )
    op.add_column(
        "job_items",
        sa.Column("manifest_id", sa.String(length=36), nullable=True),
    )
    # SET NULL 而非 CASCADE：JobItem 的生命周期属于 Job，删清单不该连带删掉在途条目；
    # 反过来留一个指向已消失清单的 id 更糟——宁可让"未关联"成为可见状态。
    op.create_foreign_key(
        "fk_job_items_manifest_id",
        "job_items",
        "article_manifests",
        ["manifest_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_job_items_manifest_id", "job_items", ["manifest_id"])


def downgrade() -> None:
    """完全可逆：本迁移不触碰任何数据（没有 UPDATE/回填），所以降级只需按逆序拆形状。

    D-V2-02 的硬要求是 `upgrade → downgrade → upgrade` 在 CI ubuntu 上跑通，
    因此这里刻意**不**写成 `raise RuntimeError`（与 ab1005w5b 那类单向加固不同）。
    执行者：`.github/workflows/ci.yml` backend job 的 "Migration roundtrip" 步
    （只往返当前 head 那一个版本；此步跑在任何测试写入之前，判的是 DDL 可逆，不是"降级不丢数据"）。
    """
    op.drop_index("ix_job_items_manifest_id", table_name="job_items")
    op.drop_constraint("fk_job_items_manifest_id", "job_items", type_="foreignkey")
    op.drop_column("job_items", "manifest_id")
    op.drop_index("ix_manifest_source_article_key", table_name="article_manifests")
    op.drop_column("article_manifests", "article_key")
