"""Recount moment.media_count from moment_media.

Media deletes used to decrement media_count twice (the moment_media DELETE
trigger plus a manual decrement in MediaService), leaving moments that still
have media reporting fewer, often 0. The reader hides media for a count of 0,
and the Timeline filters on it. The code no longer double counts; this repairs
rows written before that.

Revision ID: e7a1c9d3b5f2
Revises: d5e6f7a8b9c0
Create Date: 2026-09-22
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "e7a1c9d3b5f2"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE moment
        SET media_count = (
            SELECT COUNT(*) FROM moment_media
            WHERE moment_media.moment_id = moment.id
        )
        WHERE media_count <> (
            SELECT COUNT(*) FROM moment_media
            WHERE moment_media.moment_id = moment.id
        )
        """
    )


def downgrade() -> None:
    # A data repair: the previous, wrong counts are not worth restoring.
    pass
