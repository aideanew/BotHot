"""SPEC-M3 批次 3 / T5.4：engine_key_registrations 引擎 Key 登记表（密文落库）。

Revises: ab1004m3a
"""
import sqlalchemy as sa

from alembic import op

revision: str = "ab1004m3b"
down_revision: str | None = "ab1004m3a"
branch_labels = None
depends_on = None

TABLE = "engine_key_registrations"
FK = "fk_engine_key_registrations_registered_by_users_id"
UQ_KEY_ID = "uq_engine_key_registration_key_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # 沿用 ab1004d04a 的 get_table_names() 惯例（PGInspector 无 get_tables()）
    if "users" not in set(inspector.get_table_names()):
        raise sa.exc.InvalidRequestError(
            "users 表不存在：ab1004m3b 依赖初始 schema 05a5a856c37b（registered_by 外键锚点）"
        )

    if TABLE not in set(inspector.get_table_names()):
        op.create_table(
            TABLE,
            sa.Column("engine", sa.String(length=32), nullable=False),
            sa.Column("secret_ref", sa.Text(), nullable=False),
            sa.Column("key_id", sa.String(length=32), nullable=False),
            sa.Column("registered_by", sa.String(length=36), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("engine"),
            sa.ForeignKeyConstraint(["registered_by"], ["users.id"], ondelete="CASCADE", name=FK),
            sa.UniqueConstraint("key_id", name=UQ_KEY_ID),
        )
    else:
        # 幂等补约束：表已存在（如早前手工建过）时仍保证 FK 与唯一键到位
        if not _has_fk(inspector):
            op.create_foreign_key(FK, TABLE, "users", ["registered_by"], ["id"], ondelete="CASCADE")
        indexes = {i["name"] for i in inspector.get_indexes(TABLE)}
        if UQ_KEY_ID not in indexes:
            op.create_unique_constraint(UQ_KEY_ID, TABLE, ["key_id"])


def _has_fk(inspector: sa.engine.reflection.Inspector) -> bool:
    """表是否已有指向 users.id 的外键（按约束名或目标表识别）。"""
    return any(f.get("referred_table") == "users" for f in inspector.get_foreign_keys(TABLE))


def downgrade() -> None:
    # 登记行持有第三方 Key，downgrade 前须人工导出/撤销——不静默丢密文
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE in set(inspector.get_table_names()):
        op.drop_table(TABLE)
