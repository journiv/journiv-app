"""Add UTC datetime + timezone tracking to entries and mood logs

Revision ID: c3ea6c0f0a1d
Revises: 4fbf758e7995
Create Date: 2025-02-14 12:00:00.000000

"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3ea6c0f0a1d"
down_revision = "4fbf758e7995"
branch_labels = None
depends_on = None


def _ensure_utc(dt: datetime | None) -> datetime:
    """Ensure datetime has UTC tzinfo."""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    is_sqlite = connection.dialect.name == "sqlite"

    entry_columns = {col["name"] for col in inspector.get_columns("entry")}
    mood_columns = {col["name"] for col in inspector.get_columns("mood_log")}

    if "entry_datetime_utc" not in entry_columns:
        op.add_column(
            "entry",
            sa.Column("entry_datetime_utc", sa.DateTime(timezone=True), nullable=True),
        )
    if "entry_timezone" not in entry_columns:
        op.add_column(
            "entry",
            sa.Column(
                "entry_timezone",
                sa.String(length=100),
                nullable=False,
                server_default="UTC",
            ),
        )
    if "user_id" not in entry_columns:
        op.add_column("entry", sa.Column("user_id", sa.Uuid(), nullable=True))

    if "logged_datetime_utc" not in mood_columns:
        op.add_column(
            "mood_log",
            sa.Column("logged_datetime_utc", sa.DateTime(timezone=True), nullable=True),
        )
    if "logged_timezone" not in mood_columns:
        op.add_column(
            "mood_log",
            sa.Column(
                "logged_timezone",
                sa.String(length=100),
                nullable=False,
                server_default="UTC",
            ),
        )

    if not is_sqlite:
        op.create_foreign_key(
            "fk_entry_user_id_user",
            "entry",
            "user",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
    metadata = sa.MetaData()
    metadata.reflect(
        bind=connection,
        only=("entry", "journal", "user_settings", "mood_log"),
    )

    entry_table = metadata.tables["entry"]
    journal_table = metadata.tables["journal"]
    settings_table = metadata.tables["user_settings"]
    mood_log_table = metadata.tables["mood_log"]

    journal_user_map: Dict[uuid.UUID, uuid.UUID] = {
        row.id: row.user_id
        for row in connection.execute(
            sa.select(journal_table.c.id, journal_table.c.user_id)
        )
    }

    user_timezone_map: Dict[uuid.UUID, str] = {
        row.user_id: (row.time_zone or "UTC")
        for row in connection.execute(
            sa.select(settings_table.c.user_id, settings_table.c.time_zone)
        )
    }

    # Backfill entries
    entry_rows = connection.execute(
        sa.select(
            entry_table.c.id,
            entry_table.c.created_at,
            entry_table.c.journal_id,
        )
    ).fetchall()

    for entry_row in entry_rows:
        entry_id = entry_row.id
        journal_id = entry_row.journal_id
        created_at = _ensure_utc(entry_row.created_at)
        user_id = journal_user_map.get(journal_id)
        timezone_name = (user_timezone_map.get(user_id, "UTC") or "UTC").strip() or "UTC"
        local_date = created_at.astimezone(ZoneInfo(timezone_name)).date()

        connection.execute(
            entry_table.update()
            .where(entry_table.c.id == entry_id)
            .values(
                entry_datetime_utc=created_at,
                entry_timezone=timezone_name,
                user_id=user_id,
                entry_date=local_date,
            )
        )

    # Prepare entry lookup for mood logs linked to entries
    entry_lookup = {
        row.id: (row.entry_datetime_utc, row.entry_timezone, row.entry_date)
        for row in connection.execute(
            sa.select(
                entry_table.c.id,
                entry_table.c.entry_datetime_utc,
                entry_table.c.entry_timezone,
                entry_table.c.entry_date,
            )
        )
    }

    mood_rows = connection.execute(
        sa.select(
            mood_log_table.c.id,
            mood_log_table.c.created_at,
            mood_log_table.c.entry_id,
            mood_log_table.c.user_id,
        )
    ).fetchall()

    for mood_row in mood_rows:
        mood_id = mood_row.id
        created_at = _ensure_utc(mood_row.created_at)
        entry_id = mood_row.entry_id
        user_id = mood_row.user_id

        if entry_id and entry_id in entry_lookup:
            entry_dt, entry_tz, entry_date = entry_lookup[entry_id]
            logged_dt = _ensure_utc(entry_dt)
            timezone_name = entry_tz or "UTC"
            logged_date = entry_date
        else:
            timezone_name = (
                user_timezone_map.get(user_id, "UTC") or "UTC"
            ).strip() or "UTC"
            logged_dt = created_at
            logged_date = logged_dt.astimezone(ZoneInfo(timezone_name)).date()

        connection.execute(
            mood_log_table.update()
            .where(mood_log_table.c.id == mood_id)
            .values(
                logged_datetime_utc=logged_dt,
                logged_timezone=timezone_name,
                logged_date=logged_date,
            )
        )

    if not is_sqlite:
        op.alter_column("entry", "entry_datetime_utc", nullable=False)
        op.alter_column("entry", "user_id", nullable=False)
        op.alter_column("mood_log", "logged_datetime_utc", nullable=False)
        op.alter_column("mood_log", "logged_timezone", nullable=False)

    existing_entry_indexes = {idx["name"] for idx in inspector.get_indexes("entry")}
    existing_mood_indexes = {idx["name"] for idx in inspector.get_indexes("mood_log")}

    if "idx_entry_user_datetime" not in existing_entry_indexes:
        op.create_index(
            "idx_entry_user_datetime",
            "entry",
            ["user_id", "entry_datetime_utc"],
            unique=False,
        )
    if "idx_mood_logs_user_datetime" not in existing_mood_indexes:
        op.create_index(
            "idx_mood_logs_user_datetime",
            "mood_log",
            ["user_id", "logged_datetime_utc"],
            unique=False,
        )


def downgrade() -> None:
    connection = op.get_bind()
    is_sqlite = connection.dialect.name == "sqlite"

    op.drop_index("idx_mood_logs_user_datetime", table_name="mood_log")
    op.drop_index("idx_entry_user_datetime", table_name="entry")

    op.alter_column("mood_log", "logged_timezone", nullable=True)
    op.alter_column("mood_log", "logged_datetime_utc", nullable=True)
    op.alter_column("entry", "user_id", nullable=True)
    op.alter_column("entry", "entry_datetime_utc", nullable=True)

    op.drop_column("mood_log", "logged_timezone")
    op.drop_column("mood_log", "logged_datetime_utc")

    if not is_sqlite:
        op.drop_constraint("fk_entry_user_id_user", "entry", type_="foreignkey")
    op.drop_column("entry", "user_id")
    op.drop_column("entry", "entry_timezone")
    op.drop_column("entry", "entry_datetime_utc")
