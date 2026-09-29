"""SPEC-M3 批次 1 / T5.0（D9=a 终底）：users 加 role 列（user/operator/admin 三态）。

Revises: ab1004m5a
"""
import sqlalchemy as sa
from sqlalchemy.exc import InvalidRequestError

from alembic import op

revision: str = "ab1004m3a"
down_revision: str | None = "ab1004m5a"
branch_labels = None
depends_on = None

ROLE_INDEX = "ix_users_role"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # 沿用 ab1004d04a 的 get_table_names() 惯例（PGInspector 无 get_tables()）
    if "users" not in set(inspector.get_table_names()):
        raise InvalidRequestError("users 表不存在：ab1004m3a 依赖初始 schema 05a5a856c37b")

    columns = {c["name"] for c in inspector.get_columns("users")}
    if "role" not in columns:
        # server_default='user'：存量行与新增行均落到最小权限态，不升权任何现有账号。
        # PG 11+（本栈 16）下 NOT NULL + server_default 的 ADD COLUMN 是元数据级操作，
        # 不重写全表。与 ab1004m5a 刻意不设 server_default 相反——role 无
        # 「从未设置 vs 显式置空」的语义区分需求，每行都必须有值。
        op.add_column(
            "users",
            sa.Column("role", sa.String(length=32), nullable=False, server_default="user"),
        )

    indexes = {i["name"] for i in inspector.get_indexes("users")}
    if ROLE_INDEX not in indexes:
        op.create_index(op.f(ROLE_INDEX), "users", ["role"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indexes = {i["name"] for i in inspector.get_indexes("users")}
    if ROLE_INDEX in indexes:
        op.drop_index(op.f(ROLE_INDEX), table_name="users")

    # 删列后所有账号回到「无角色」态，语义上等同默认 user；不升权任何现有账号
    columns = {c["name"] for c in inspector.get_columns("users")}
    if "role" in columns:
        op.drop_column("users", "role")
