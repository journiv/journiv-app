"""Add is_draft to entry.

Revision ID: c9d2e1f0a1b2
Revises: b7a1c2d3e4f5
Create Date: 2026-01-26
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c9d2e1f0a1b2'
down_revision = 'b7a1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('entry', sa.Column('is_draft', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_index('ix_entry_is_draft', 'entry', ['is_draft'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_entry_is_draft', table_name='entry')
    op.drop_column('entry', 'is_draft')
