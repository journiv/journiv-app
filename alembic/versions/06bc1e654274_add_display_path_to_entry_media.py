"""add_display_path_to_entry_media

Revision ID: 06bc1e654274
Revises: b8c9d0e1f2a3
Create Date: 2026-02-14 13:58:09.911695

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '06bc1e654274'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add display_path column to entry_media table
    # This column stores the path to a web-compatible display version (e.g., WebP for HEIC)
    op.add_column('entry_media', sa.Column('display_path', sa.String(length=500), nullable=True))


def downgrade() -> None:
    # Remove display_path column from entry_media table
    op.drop_column('entry_media', 'display_path')
