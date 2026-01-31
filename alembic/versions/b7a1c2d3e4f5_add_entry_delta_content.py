"""add entry delta content fields

Revision ID: b7a1c2d3e4f5
Revises: a1b2c3d4e5f6
Create Date: 2026-01-25 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b7a1c2d3e4f5"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    is_postgres = connection.dialect.name == "postgresql"

    entry_columns = {col["name"] for col in inspector.get_columns("entry")}

    if "content_delta" not in entry_columns:
        if is_postgres:
            op.add_column("entry", sa.Column("content_delta", postgresql.JSONB, nullable=True))
        else:
            op.add_column("entry", sa.Column("content_delta", sa.JSON, nullable=True))

    if "content_plain_text" not in entry_columns:
        op.add_column("entry", sa.Column("content_plain_text", sa.Text, nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    entry_columns = {col["name"] for col in inspector.get_columns("entry")}

    if "content_plain_text" in entry_columns:
        op.drop_column("entry", "content_plain_text")

    if "content_delta" in entry_columns:
        op.drop_column("entry", "content_delta")
