"""Index job history for keyset pagination.

Revision ID: d5e6f7a8b9c0
Revises: c2d4e6f8a0b1
Create Date: 2026-09-06
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "d5e6f7a8b9c0"
down_revision = "c2d4e6f8a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_export_jobs_user_created_id",
        "export_jobs",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_import_jobs_user_created_id",
        "import_jobs",
        ["user_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_import_jobs_user_created_id", table_name="import_jobs")
    op.drop_index("ix_export_jobs_user_created_id", table_name="export_jobs")
