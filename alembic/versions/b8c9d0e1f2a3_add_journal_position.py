"""add journal position

Revision ID: b8c9d0e1f2a3
Revises: 3a7b1c2d4e5f
Create Date: 2026-02-11 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = '3a7b1c2d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add position column
    op.add_column('journal', sa.Column('position', sa.Integer(), nullable=True))

    # Set initial positions based on creation order (per user AND favorite status)
    # This ensures favorites have positions 0,1,2... and regular journals also have 0,1,2... separately
    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY user_id, is_favorite
                ORDER BY created_at DESC
            ) - 1 as pos
            FROM journal
        )
        UPDATE journal
        SET position = ranked.pos
        FROM ranked
        WHERE journal.id = ranked.id
    """)

    # Create composite index for efficient ordering queries
    # Note: PostgreSQL-specific index with DESC/ASC NULLS LAST operators
    op.execute("""
        CREATE INDEX idx_journal_user_ordering
        ON journal(user_id, is_favorite DESC, position ASC NULLS LAST)
    """)


def downgrade() -> None:
    # Drop index
    op.drop_index('idx_journal_user_ordering', table_name='journal')

    # Drop column
    op.drop_column('journal', 'position')
