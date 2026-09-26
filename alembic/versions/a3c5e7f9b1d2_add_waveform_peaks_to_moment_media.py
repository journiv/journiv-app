"""Add waveform peaks to moment media.

Revision ID: a3c5e7f9b1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-09-19
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "a3c5e7f9b1d2"
down_revision = "e7a1c9d3b5f2"
branch_labels = None
depends_on = None


def _json_type():
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    # Nullable, no default: NULL means "not computed", so existing audio keeps
    # falling back to the plain player until it is reprocessed.
    op.add_column(
        "moment_media",
        sa.Column("waveform_peaks", _json_type(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("moment_media", "waveform_peaks")
