"""add activity soft delete flag

Revision ID: 4c5d6e7f8a9b
Revises: a1a2b3c4d5e6
Create Date: 2026-03-15 12:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "4c5d6e7f8a9b"
down_revision = "a1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activity",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "idx_activity_user_active",
        "activity",
        ["user_id", "is_active"],
        unique=False,
    )
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("activity", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_activity_user_active", table_name="activity")
    op.drop_column("activity", "is_active")
