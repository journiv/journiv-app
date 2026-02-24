"""remove mood preference tables and inline ordering

Revision ID: d2e4f6a8b0c1
Revises: c1f2e3d4a5b6
Create Date: 2026-02-23 12:30:00.000000

"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2e4f6a8b0c1"
down_revision: Union[str, None] = "c1f2e3d4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name)


def _uuid_hex(value: object) -> str:
    if isinstance(value, uuid.UUID):
        return value.hex
    return str(value).replace("-", "")


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # Inline per-user mood ordering into mood.position.
    if _table_exists("user_mood_preference"):
        if is_sqlite:
            op.execute(
                sa.text(
                    """
                    UPDATE mood
                    SET position = (
                        SELECT ump.sort_order
                        FROM user_mood_preference AS ump
                        WHERE ump.mood_id = mood.id
                          AND ump.user_id = mood.user_id
                        LIMIT 1
                    )
                    WHERE EXISTS (
                        SELECT 1
                        FROM user_mood_preference AS ump
                        WHERE ump.mood_id = mood.id
                          AND ump.user_id = mood.user_id
                    )
                    """
                )
            )
        else:
            op.execute(
                sa.text(
                    """
                    UPDATE mood AS m
                    SET position = ump.sort_order
                    FROM user_mood_preference AS ump
                    WHERE ump.mood_id = m.id
                      AND ump.user_id = m.user_id
                    """
                )
            )

        op.drop_table("user_mood_preference")

    # Inline per-user mood-group ordering into mood_group.position.
    if _table_exists("user_mood_group_preference"):
        if is_sqlite:
            op.execute(
                sa.text(
                    """
                    UPDATE mood_group
                    SET position = (
                        SELECT umgp.sort_order
                        FROM user_mood_group_preference AS umgp
                        WHERE umgp.mood_group_id = mood_group.id
                          AND umgp.user_id = mood_group.user_id
                        LIMIT 1
                    )
                    WHERE EXISTS (
                        SELECT 1
                        FROM user_mood_group_preference AS umgp
                        WHERE umgp.mood_group_id = mood_group.id
                          AND umgp.user_id = mood_group.user_id
                    )
                    """
                )
            )
        else:
            op.execute(
                sa.text(
                    """
                    UPDATE mood_group AS mg
                    SET position = umgp.sort_order
                    FROM user_mood_group_preference AS umgp
                    WHERE umgp.mood_group_id = mg.id
                      AND umgp.user_id = mg.user_id
                    """
                )
            )

        op.drop_table("user_mood_group_preference")


def downgrade() -> None:
    bind = op.get_bind()

    if not _table_exists("user_mood_preference"):
        op.create_table(
            "user_mood_preference",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("mood_id", sa.Uuid(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.ForeignKeyConstraint(["mood_id"], ["mood.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "uq_user_mood_preference_user_mood",
            "user_mood_preference",
            ["user_id", "mood_id"],
            unique=True,
        )
        op.create_index(
            "idx_user_mood_preference_user_sort_order",
            "user_mood_preference",
            ["user_id", "sort_order"],
            unique=False,
        )
        mood_rows = bind.execute(
            sa.text(
                """
                SELECT user_id, id AS mood_id, position AS sort_order
                FROM mood
                WHERE user_id IS NOT NULL
                """
            )
        ).mappings().all()
        now = datetime.now(timezone.utc)
        if mood_rows:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO user_mood_preference (
                        id, created_at, updated_at, user_id, mood_id, sort_order, is_hidden
                    ) VALUES (
                        :id, :created_at, :updated_at, :user_id, :mood_id, :sort_order, :is_hidden
                    )
                    """
                ),
                [
                    {
                        "id": uuid.uuid4().hex,
                        "created_at": now,
                        "updated_at": now,
                        "user_id": _uuid_hex(row["user_id"]),
                        "mood_id": _uuid_hex(row["mood_id"]),
                        "sort_order": int(row["sort_order"] or 0),
                        "is_hidden": False,
                    }
                    for row in mood_rows
                ],
            )

    if not _table_exists("user_mood_group_preference"):
        op.create_table(
            "user_mood_group_preference",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("mood_group_id", sa.Uuid(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.ForeignKeyConstraint(["mood_group_id"], ["mood_group.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "uq_user_mood_group_preference_user_group",
            "user_mood_group_preference",
            ["user_id", "mood_group_id"],
            unique=True,
        )
        op.create_index(
            "idx_user_mood_group_preference_user_sort_order",
            "user_mood_group_preference",
            ["user_id", "sort_order"],
            unique=False,
        )
        group_rows = bind.execute(
            sa.text(
                """
                SELECT user_id, id AS mood_group_id, position AS sort_order
                FROM mood_group
                WHERE user_id IS NOT NULL
                """
            )
        ).mappings().all()
        now = datetime.now(timezone.utc)
        if group_rows:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO user_mood_group_preference (
                        id, created_at, updated_at, user_id, mood_group_id, sort_order, is_hidden
                    ) VALUES (
                        :id, :created_at, :updated_at, :user_id, :mood_group_id, :sort_order, :is_hidden
                    )
                    """
                ),
                [
                    {
                        "id": uuid.uuid4().hex,
                        "created_at": now,
                        "updated_at": now,
                        "user_id": _uuid_hex(row["user_id"]),
                        "mood_group_id": _uuid_hex(row["mood_group_id"]),
                        "sort_order": int(row["sort_order"] or 0),
                        "is_hidden": False,
                    }
                    for row in group_rows
                ],
            )
