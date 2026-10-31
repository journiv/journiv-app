"""Add entry template to journal.

Revision ID: b7d2e4f6a8c1
Revises: a3c5e7f9b1d2
Create Date: 2026-10-31
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7d2e4f6a8c1"
down_revision = "a3c5e7f9b1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, no default: NULL means the journal has no template, which is
    # every existing journal, so new entries keep opening on a blank page.
    op.add_column(
        "journal",
        sa.Column("entry_template", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    with op.batch_alter_table("journal") as batch_op:
        batch_op.drop_column("entry_template")
