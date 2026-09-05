"""Add a per-writer prompt lookup index.

Revision ID: c2d4e6f8a0b1
Revises: e8f9a0b1c2d3
Create Date: 2026-09-03
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c2d4e6f8a0b1"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_moment_user_prompt_id",
        "moment",
        ["user_id", "prompt_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_moment_user_prompt_id", table_name="moment")
