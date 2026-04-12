"""normalize sqlite entry boolean flags

Revision ID: 5b6c7d8e9f0a
Revises: 4c5d6e7f8a9b
Create Date: 2026-04-12 13:45:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "5b6c7d8e9f0a"
down_revision = "4c5d6e7f8a9b"
branch_labels = None
depends_on = None


def _normalize_boolean_column(column_name: str) -> None:
    op.execute(
        f"""
        UPDATE entry
        SET {column_name} = 0
        WHERE typeof({column_name}) = 'text'
          AND lower(trim({column_name})) = 'false'
        """
    )
    op.execute(
        f"""
        UPDATE entry
        SET {column_name} = 1
        WHERE typeof({column_name}) = 'text'
          AND lower(trim({column_name})) = 'true'
        """
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return

    _normalize_boolean_column("is_draft")
    _normalize_boolean_column("is_published")
    _normalize_boolean_column("is_indexed")


def downgrade() -> None:
    pass
