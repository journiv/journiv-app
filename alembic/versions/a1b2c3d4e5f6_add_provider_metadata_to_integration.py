"""add provider_metadata to integration

Revision ID: a1b2c3d4e5f6
Revises: 885e3d7a9b2c
Create Date: 2026-01-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '885e3d7a9b2c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add provider_metadata column to integration table
    # Using Text type for JSON string storage (SQLite/PostgreSQL)
    op.add_column('integration', sa.Column('provider_metadata', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove provider_metadata column
    op.drop_column('integration', 'provider_metadata')
