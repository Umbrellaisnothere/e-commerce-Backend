"""Add token_blocklist for JWT jti revocation.

Revision ID: 002_token_blocklist
Revises: 001_widen_password
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa


revision = "002_token_blocklist"
down_revision = "001_widen_password"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "token_blocklist",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jti", sa.String(length=36), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_token_blocklist_jti", "token_blocklist", ["jti"], unique=True)


def downgrade():
    op.drop_index("ix_token_blocklist_jti", table_name="token_blocklist")
    op.drop_table("token_blocklist")
