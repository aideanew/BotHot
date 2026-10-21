"""STEP-08 S8.1.1：一源多标识的存储底座 `source_identifiers` + 一次性回填 biz。

形状与取舍的理由在 **ADR-0014**（`docs/03_solution/decisions/adr-0014-source-identifiers.md`），
这里只写迁移必须自己回答的四件事：

1. **为什么把标识从 `sources` 的一列拆成一张表。** 渠道要的标识不止 biz：
   Dajiala/JustOneAPI/TikHub 要 ghid、Wellbyte 要一篇文章的 URL 做入口、RSS 要 feed_url
   （现读锚 `providers/article_sources/base.py:74`、`wellbyte.py:21`）。今天这件事由每个调用点
   各自注释约定"identifier 该传什么"，猜错的表现是清单为空而不是报错。展平成列则每加一类
   要发一次 DDL，而且多值那一类（一个源可能有多个入口 URL）根本展不了。
2. **为什么 `(kind, value)` 唯一。** 同一个标识属于两个源 = 号主身份坍缩，本仓为此付过学费
   （P0-1 缓存命中却是另一篇、D-01b 的 `biz`/`__biz` 锚）。唯一性放 DB 侧而不是应用层查重，
   因为并发写路径不止一条。
3. **为什么 `kind`/`origin` 是 `String(16)` 而不是 DB enum。** AGENTS.md 关键约束 3 的同一口径
   （加值不发 DDL）。封闭集合改由应用侧 `IDENTIFIER_KINDS` 把关，读侧不认未知 kind——
   宁可少选一个渠道，也不要拿猜错的标识去打付费接口。
4. **回填只做 biz、且只做一次。** `sources.external_id` 非空的行写成 `(kind='biz', origin='source')`。
   不播种 ghid/URL：那些只能从真实解析或映射来，凭空造就是假标识。

链序：`... → ab1006c1a → ab1006c4a → ab1006c2a`（单头）。STEP-09 条件持 `ab1006c3a`，
两卡**禁止并行**，所以这里的 `down_revision` 以合入时 `alembic heads` 为准（现读 `ab1006c4a`）。

`downgrade()` 是真的删表：CI 的迁移往返步会升 head 再降回来，并在 `information_schema` /
`pg_indexes` 里探列与索引（`scripts/migration_roundtrip_probe.py` 的 `SHAPES`，
新头不登记就直接判红）。留一个 `pass` 就是留一张"降不回去"的表。
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "ab1006c2a"
down_revision: str | None = "ab1006c4a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_identifiers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.String(length=512), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_source_identifiers"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name="fk_source_identifiers_source_id", ondelete="CASCADE"
        ),
        # `(kind, value)` 全列唯一：同一个标识不能属于两个源（ADR-0014 不变量 1）。
        # 不需要前缀截断——PG btree 的键上限约 2704 字节，而 `varchar(512)` 的 UTF-8 上界是
        # 2048 字节，整列唯一在预算内；截断反而会放过"前 96 字符相同、实为两个入口 URL"的碰撞。
        sa.UniqueConstraint("kind", "value", name="uq_source_identifier_kind_value"),
    )
    op.create_index("ix_source_identifiers_source_id", "source_identifiers", ["source_id"])
    op.create_index("ix_source_identifiers_kind", "source_identifiers", ["kind"])

    # 一次性回填：源自己的 biz。`origin='source'` 说的是"这条标识来自源记录本身"，
    # 与 S8.2 resolver 推导出来的 `'resolver'` 相对——两者必须在库里可区分（ADR-0014 §3）。
    op.execute(
        """
        insert into source_identifiers (id, source_id, kind, value, origin, created_at)
        select gen_random_uuid()::text, s.id, 'biz', s.external_id, 'source', now()
        from sources as s
        where s.external_id is not null and s.external_id <> ''
        """
    )


def downgrade() -> None:
    op.drop_index("ix_source_identifiers_kind", table_name="source_identifiers")
    op.drop_index("ix_source_identifiers_source_id", table_name="source_identifiers")
    op.drop_table("source_identifiers")
