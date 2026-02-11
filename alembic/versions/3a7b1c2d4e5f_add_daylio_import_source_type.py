"""add daylio import source type

Revision ID: 3a7b1c2d4e5f
Revises: aa9a7125186b
Create Date: 2026-02-11 06:18:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "3a7b1c2d4e5f"
down_revision = "aa9a7125186b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE import_source_type_enum ADD VALUE IF NOT EXISTS 'daylio'"
        )


def downgrade() -> None:
    # Downgrading enums in Postgres requires type recreation. Skip for safety.
    pass
