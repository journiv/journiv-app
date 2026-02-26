"""make integration timestamps timezone aware

Revision ID: f3b4c5d6e7f8
Revises: e5f6a7b8c9d0, 3a7b1c2d4e5f
Create Date: 2026-02-26 10:15:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = ("e5f6a7b8c9d0", "3a7b1c2d4e5f")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _to_timestamptz(column_name: str, nullable: bool) -> None:
    op.alter_column(
        "integration",
        column_name,
        existing_type=sa.DateTime(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=nullable,
        postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
    )


def _to_timestamp(column_name: str, nullable: bool) -> None:
    op.alter_column(
        "integration",
        column_name,
        existing_type=sa.DateTime(timezone=True),
        type_=sa.DateTime(),
        existing_nullable=nullable,
        postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
    )


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        _to_timestamptz("created_at", nullable=False)
        _to_timestamptz("updated_at", nullable=False)
        _to_timestamptz("token_expires_at", nullable=True)
        _to_timestamptz("last_synced_at", nullable=True)
        _to_timestamptz("last_error_at", nullable=True)
        _to_timestamptz("connected_at", nullable=False)
        return

    with op.batch_alter_table("integration") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "token_expires_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "last_synced_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "last_error_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "connected_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        _to_timestamp("created_at", nullable=False)
        _to_timestamp("updated_at", nullable=False)
        _to_timestamp("token_expires_at", nullable=True)
        _to_timestamp("last_synced_at", nullable=True)
        _to_timestamp("last_error_at", nullable=True)
        _to_timestamp("connected_at", nullable=False)
        return

    with op.batch_alter_table("integration") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "token_expires_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "last_synced_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "last_error_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "connected_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
        )
