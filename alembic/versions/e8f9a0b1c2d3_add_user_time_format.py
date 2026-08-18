"""add user time format preference

Revision ID: e8f9a0b1c2d3
Revises: f4a8b9c0d1e2
Create Date: 2026-08-18
"""

import sqlalchemy as sa

from alembic import op


revision = "e8f9a0b1c2d3"
down_revision = "f4a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.add_column(
            sa.Column("time_format", sa.String(length=20), nullable=False, server_default="system")
        )
        batch_op.create_check_constraint(
            "check_time_format_valid",
            "time_format IN ('system', 'twelve_hour', 'twenty_four_hour')",
        )


def downgrade() -> None:
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.drop_constraint("check_time_format_valid", type_="check")
        batch_op.drop_column("time_format")
