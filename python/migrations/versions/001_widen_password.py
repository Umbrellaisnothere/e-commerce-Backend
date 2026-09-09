"""Baseline schema and widen users.password to 255 characters.

Revision ID: 001_widen_password
Revises:
Create Date: 2026-09-01

Existing SQLite databases already created with create_all() are preserved:
the password column is only altered on engines that enforce VARCHAR length.
On SQLite, VARCHAR(50) does not truncate, so no table rewrite is performed.
"""
from alembic import op
import sqlalchemy as sa


revision = "001_widen_password"
down_revision = None
branch_labels = None
depends_on = None


def _table_names():
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade():
    tables = _table_names()
    bind = op.get_bind()

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("user_id", sa.Integer(), primary_key=True),
            sa.Column("username", sa.String(length=50), nullable=False),
            sa.Column("password", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=50), nullable=False),
            sa.UniqueConstraint("username"),
            sa.UniqueConstraint("email"),
        )
    elif bind.dialect.name != "sqlite":
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "password",
                existing_type=sa.String(length=50),
                type_=sa.String(length=255),
                existing_nullable=False,
            )

    if "products" not in tables:
        op.create_table(
            "products",
            sa.Column("product_id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("price", sa.Float(), nullable=False),
            sa.Column("description", sa.String(length=200)),
            sa.Column("category", sa.String(length=50)),
            sa.Column("photo_url", sa.String(length=200)),
        )

    if "carts" not in tables:
        op.create_table(
            "carts",
            sa.Column("cart_id", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.product_id"), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column(
                "password",
                existing_type=sa.String(length=255),
                type_=sa.String(length=50),
                existing_nullable=False,
            )
