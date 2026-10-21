"""STEP-28 S28.1.1：运营可配置项的存储底座 `system_settings`（纯 DDL，不播种）。

形状与取舍的理由在 **ADR-0013**（`docs/03_solution/decisions/adr-0013-system-settings-store.md`），
这里只写迁移必须自己回答的三件事：

1. **为什么只建表、不 INSERT 任何默认行。** 本表的语义是"有行才覆盖，无行走环境变量兜底"。
   播种一行等于把今天的 env 默认值**固化成第二个真源**：以后改 `config.py` 的默认渠道，
   库里那行还在，行为就悄悄分叉了。"删掉这行 = 回到今天的行为"才是可回退的定义。
2. **为什么 `value` 是 jsonb 而本仓库此前从未用过 jsonb。** 最接近的先例是
   `bot_channels.extra_config`（`Text`），那列是 `Text` 有它自己的理由——它存**加密后的字节**，
   DB 侧本来不该解析它。配置值不是密文，用 jsonb 换来写进去即被 DB 验一遍 JSON 合法性，
   以及出事时可以 `select jsonb_typeof(value)` / 按路径查，而不是把整列捞进 Python 再解析。
3. **为什么 `updated_by` 可空还带外键。** `users.id` 是 `String(36)`（实测
   `app/models/entities.py:22`），所以这里用 `VARCHAR(36)` 对齐类型；可空表达"这行不是人写的"，
   外键保证它不会指向一个不存在的操作者——本仓库在"操作者锚点"上付过学费（P-26、STEP-31 的 9 字段审计负载）。

链序：`... → ab1005w5b → ab1006c1a → ab1006c4a`（单头）。STEP-08 持 `ab1006c2a`、STEP-09 条件持
`ab1006c3a`，三卡**禁止并行**，所以这里的 `down_revision` 以合入时 `alembic heads` 为准。

`downgrade()` 是真的删表：CI 的迁移往返步会把 head 升上去再降回来，并在 `information_schema`
里探列与索引（见 `.github/workflows/ci.yml` 的 Migration roundtrip 步）——留下一个
`pass` 就是留下一张"降不回去"的表。

Revision ID: ab1006c4a
Revises: ab1006c1a
Create Date: 2026-10-21
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "ab1006c4a"
down_revision: str | None = "ab1006c1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_system_settings"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], name="fk_system_settings_updated_by_users"),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
