"""add import metadata fields

Revision ID: e7c4a1b2c3d4
Revises: d8f3a9e2b1c4
Create Date: 2026-01-07 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "e7c4a1b2c3d4"
down_revision = "d8f3a9e2b1c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()
    op.add_column("entry", sa.Column("import_metadata", json_type, nullable=True))
    op.add_column("journal", sa.Column("import_metadata", json_type, nullable=True))


def downgrade() -> None:
    op.drop_column("journal", "import_metadata")
    op.drop_column("entry", "import_metadata")
