"""add activities moods goals moments (squashed)

Revision ID: aa9a7125186b
Revises: c9d2e1f0a1b2
Create Date: 2026-02-09 17:14:24.413472

"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "aa9a7125186b"
down_revision = "c9d2e1f0a1b2"
branch_labels = None
depends_on = None


TIER_GROUPS = [
    (5, "Very Positive", 10),
    (4, "Positive", 20),
    (3, "Neutral", 30),
    (2, "Negative", 40),
    (1, "Very Negative", 50),
]


def _as_uuid(value: Optional[uuid.UUID]) -> Optional[uuid.UUID]:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _create_enum_types(dialect_name: str) -> None:
    if dialect_name != "postgresql":
        return
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'goal_type_enum') THEN
                CREATE TYPE goal_type_enum AS ENUM ('achieve', 'avoid');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'goal_frequency_enum') THEN
                CREATE TYPE goal_frequency_enum AS ENUM ('daily', 'weekly', 'monthly');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'goal_log_status_enum') THEN
                CREATE TYPE goal_log_status_enum AS ENUM ('success', 'fail', 'skipped');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'goal_log_source_enum') THEN
                CREATE TYPE goal_log_source_enum AS ENUM ('auto', 'manual');
            END IF;
        END$$;
        """
    )


def upgrade() -> None:
    # --- d1e2f3a4b5c6_add_activity_tracking.py ---
    connection = op.get_bind()
    is_sqlite = connection.dialect.name == "sqlite"

    if is_sqlite:
        conn = connection

        def _normalize_uuid_column(table: str, column: str) -> None:
            has_column = conn.execute(
                sa.text(
                    "SELECT 1 FROM pragma_table_info(:table) WHERE name = :column"
                ),
                {"table": table, "column": column},
            ).fetchone()
            if not has_column:
                return
            conn.execute(
                sa.text(
                    f"UPDATE {table} SET {column} = replace({column}, '-', '') "
                    f"WHERE {column} LIKE '%-%'"
                )
            )

        conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
        _normalize_uuid_column("user", "id")
        _normalize_uuid_column("mood", "id")
        _normalize_uuid_column("journal", "id")
        _normalize_uuid_column("journal", "user_id")
        _normalize_uuid_column("prompt", "id")
        _normalize_uuid_column("prompt", "user_id")
        _normalize_uuid_column("tag", "id")
        _normalize_uuid_column("tag", "user_id")
        _normalize_uuid_column("entry", "id")
        _normalize_uuid_column("entry", "user_id")
        _normalize_uuid_column("entry", "journal_id")
        _normalize_uuid_column("entry", "prompt_id")
        _normalize_uuid_column("entry_media", "id")
        _normalize_uuid_column("entry_media", "entry_id")
        _normalize_uuid_column("entry_tag_link", "entry_id")
        _normalize_uuid_column("entry_tag_link", "tag_id")
        _normalize_uuid_column("user_settings", "user_id")
        _normalize_uuid_column("writing_streak", "id")
        _normalize_uuid_column("writing_streak", "user_id")
        _normalize_uuid_column("external_identities", "id")
        _normalize_uuid_column("external_identities", "user_id")
        _normalize_uuid_column("export_jobs", "id")
        _normalize_uuid_column("export_jobs", "user_id")
        _normalize_uuid_column("import_jobs", "id")
        _normalize_uuid_column("import_jobs", "user_id")
        _normalize_uuid_column("import_jobs", "entry_id")
        _normalize_uuid_column("integration", "id")
        _normalize_uuid_column("integration", "user_id")
        _normalize_uuid_column("instance_details", "id")
        _normalize_uuid_column("mood_log", "id")
        _normalize_uuid_column("mood_log", "user_id")
        _normalize_uuid_column("mood_log", "entry_id")
        _normalize_uuid_column("mood_log", "mood_id")
        _normalize_uuid_column("activity", "id")
        _normalize_uuid_column("activity", "user_id")
        _normalize_uuid_column("activity_log", "id")
        _normalize_uuid_column("activity_log", "user_id")
        _normalize_uuid_column("activity_log", "activity_id")
        _normalize_uuid_column("entry_activity_link", "entry_id")
        _normalize_uuid_column("entry_activity_link", "activity_id")
        _normalize_uuid_column("mood_log_activity_link", "mood_log_id")
        _normalize_uuid_column("mood_log_activity_link", "activity_id")
        conn.execute(sa.text("PRAGMA foreign_keys=ON"))

    # Create activity table
    op.create_table(
        "activity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column("color", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name="fk_activity_user_id_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(name) > 0", name="check_activity_name_not_empty"),
    )

    # Create indexes for activity table
    op.create_index(
        "idx_activity_user_name", "activity", ["user_id", "name"], unique=True
    )

    # Create activity_log table
    op.create_table(
        "activity_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("logged_date", sa.Date(), nullable=False),
        sa.Column("logged_datetime_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "logged_timezone",
            sa.String(length=100),
            nullable=False,
            server_default="UTC",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name="fk_activity_log_user_id_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activity.id"],
            name="fk_activity_log_activity_id_activity",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for activity_log table
    op.create_index(
        "idx_activity_log_user_date",
        "activity_log",
        ["user_id", "logged_date"],
        unique=False,
    )
    op.create_index(
        "idx_activity_log_user_datetime",
        "activity_log",
        ["user_id", "logged_datetime_utc"],
        unique=False,
    )
    op.create_index(
        "idx_activity_log_activity_id",
        "activity_log",
        ["activity_id"],
        unique=False,
    )

    # Create entry_activity_link table
    op.create_table(
        "entry_activity_link",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["entry.id"],
            name="fk_entry_activity_link_entry_id_entry",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activity.id"],
            name="fk_entry_activity_link_activity_id_activity",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("entry_id", "activity_id"),
    )

    # Create index for entry_activity_link table
    op.create_index(
        "idx_entry_activity_link_activity_id",
        "entry_activity_link",
        ["activity_id"],
        unique=False,
    )

    # Create mood_log_activity_link table
    op.create_table(
        "mood_log_activity_link",
        sa.Column("mood_log_id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["mood_log_id"],
            ["mood_log.id"],
            name="fk_mood_log_activity_link_mood_log_id_mood_log",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activity.id"],
            name="fk_mood_log_activity_link_activity_id_activity",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("mood_log_id", "activity_id"),
    )

    # Create index for mood_log_activity_link table
    op.create_index(
        "idx_mood_log_activity_link_activity_id",
        "mood_log_activity_link",
        ["activity_id"],
        unique=False,
    )

    # --- abc2f3a4b5c6_add_activity_groups.py ---
    # ### commands auto generated by Alembic - adjusted manually ###
    op.create_table(
        "activity_group",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("color_hex", sa.String(length=7), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_activity_group_user_name",
        "activity_group",
        ["user_id", "name"],
        unique=True,
    )

    if is_sqlite:
        with op.batch_alter_table("activity") as batch_op:
            batch_op.add_column(sa.Column("group_id", sa.Uuid(), nullable=True))
            batch_op.create_index(
                "idx_activity_group_id", ["group_id"], unique=False
            )
            batch_op.create_foreign_key(
                "fk_activity_group_id",
                "activity_group",
                ["group_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.add_column("activity", sa.Column("group_id", sa.Uuid(), nullable=True))
        op.create_index(
            op.f("idx_activity_group_id"), "activity", ["group_id"], unique=False
        )
        op.create_foreign_key(
            "fk_activity_group_id",
            "activity",
            "activity_group",
            ["group_id"],
            ["id"],
            ondelete="SET NULL",
        )
    # ### end Alembic commands ###

    # --- f2a3b4c5d6e7_add_moment_architecture.py ---
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    json_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(
        sa.JSON(), "sqlite"
    )

    op.create_table(
        "moment",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=True),
        sa.Column("primary_mood_id", sa.Uuid(), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("logged_date", sa.Date(), nullable=False),
        sa.Column("logged_timezone", sa.String(length=100), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("location_data", json_type, nullable=True),
        sa.Column("weather_data", json_type, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entry_id"], ["entry.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["primary_mood_id"], ["mood.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_id", name="uq_moment_entry_id"),
    )
    op.create_index(
        "idx_moment_user_logged_at",
        "moment",
        ["user_id", "logged_at", "id"],
        unique=False,
    )
    op.create_index(
        "idx_moment_user_logged_date",
        "moment",
        ["user_id", "logged_date"],
        unique=False,
    )
    op.create_index(op.f("ix_moment_id"), "moment", ["id"], unique=False)

    op.create_table(
        "moment_mood_activity",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("moment_id", sa.Uuid(), nullable=False),
        sa.Column("mood_id", sa.Uuid(), nullable=True),
        sa.Column("activity_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["moment_id"], ["moment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mood_id"], ["mood.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activity_id"], ["activity.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(mood_id IS NOT NULL OR activity_id IS NOT NULL)",
            name="check_moment_mood_activity_not_empty",
        ),
    )
    op.create_index(
        "idx_moment_mood_activity_moment_id",
        "moment_mood_activity",
        ["moment_id"],
        unique=False,
    )
    op.create_index(
        "idx_moment_mood_activity_mood_id",
        "moment_mood_activity",
        ["mood_id"],
        unique=False,
    )
    op.create_index(
        "idx_moment_mood_activity_activity_id",
        "moment_mood_activity",
        ["activity_id"],
        unique=False,
    )

    op.create_index(
        "uq_moment_activity_only",
        "moment_mood_activity",
        ["moment_id", "activity_id"],
        unique=True,
        postgresql_where=sa.text("mood_id IS NULL"),
        sqlite_where=sa.text("mood_id IS NULL"),
    )
    op.create_index(
        "uq_moment_mood_only",
        "moment_mood_activity",
        ["moment_id", "mood_id"],
        unique=True,
        postgresql_where=sa.text("activity_id IS NULL"),
        sqlite_where=sa.text("activity_id IS NULL"),
    )
    op.create_index(
        "uq_moment_mood_activity",
        "moment_mood_activity",
        ["moment_id", "mood_id", "activity_id"],
        unique=True,
        postgresql_where=sa.text("mood_id IS NOT NULL AND activity_id IS NOT NULL"),
        sqlite_where=sa.text("mood_id IS NOT NULL AND activity_id IS NOT NULL"),
    )

    if is_sqlite:
        with op.batch_alter_table("entry_media") as batch_op:
            batch_op.add_column(sa.Column("moment_id", sa.Uuid(), nullable=True))
            batch_op.alter_column("entry_id", existing_type=sa.Uuid(), nullable=True)
            batch_op.create_index(
                "idx_entry_media_moment_id", ["moment_id"], unique=False
            )
            batch_op.create_foreign_key(
                "fk_entry_media_moment_id_moment",
                "moment",
                ["moment_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_check_constraint(
                "check_media_entry_or_moment",
                "(entry_id IS NOT NULL) OR (moment_id IS NOT NULL)",
            )
            batch_op.create_unique_constraint(
                "uq_entry_media_moment_checksum",
                ["moment_id", "checksum"],
            )
    else:
        op.add_column("entry_media", sa.Column("moment_id", sa.Uuid(), nullable=True))
        op.alter_column(
            "entry_media", "entry_id", existing_type=sa.Uuid(), nullable=True
        )
        op.create_index(
            "idx_entry_media_moment_id", "entry_media", ["moment_id"], unique=False
        )
        op.create_foreign_key(
            "fk_entry_media_moment_id_moment",
            "entry_media",
            "moment",
            ["moment_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_check_constraint(
            "check_media_entry_or_moment",
            "entry_media",
            "(entry_id IS NOT NULL) OR (moment_id IS NOT NULL)",
        )
        op.create_unique_constraint(
            "uq_entry_media_moment_checksum",
            "entry_media",
            ["moment_id", "checksum"],
        )

    # Data migration: backfill moments and link tables
    entry = sa.table(
        "entry",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("entry_date", sa.Date()),
        sa.column("entry_datetime_utc", sa.DateTime(timezone=True)),
        sa.column("entry_timezone", sa.String()),
        sa.column("location_json", json_type),
        sa.column("weather_json", json_type),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    mood_log = sa.table(
        "mood_log",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("entry_id", sa.Uuid()),
        sa.column("mood_id", sa.Uuid()),
        sa.column("note", sa.String()),
        sa.column("logged_date", sa.Date()),
        sa.column("logged_datetime_utc", sa.DateTime(timezone=True)),
        sa.column("logged_timezone", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    activity_log = sa.table(
        "activity_log",
        sa.column("id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("activity_id", sa.Uuid()),
        sa.column("note", sa.String()),
        sa.column("logged_date", sa.Date()),
        sa.column("logged_datetime_utc", sa.DateTime(timezone=True)),
        sa.column("logged_timezone", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    entry_activity_link = sa.table(
        "entry_activity_link",
        sa.column("entry_id", sa.Uuid()),
        sa.column("activity_id", sa.Uuid()),
    )
    mood_log_activity_link = sa.table(
        "mood_log_activity_link",
        sa.column("mood_log_id", sa.Uuid()),
        sa.column("activity_id", sa.Uuid()),
    )
    entry_media = sa.table(
        "entry_media",
        sa.column("id", sa.Uuid()),
        sa.column("entry_id", sa.Uuid()),
        sa.column("moment_id", sa.Uuid()),
    )
    moment = sa.table(
        "moment",
        sa.column("id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("user_id", sa.Uuid()),
        sa.column("entry_id", sa.Uuid()),
        sa.column("primary_mood_id", sa.Uuid()),
        sa.column("logged_at", sa.DateTime(timezone=True)),
        sa.column("logged_date", sa.Date()),
        sa.column("logged_timezone", sa.String()),
        sa.column("note", sa.String()),
        sa.column("location_data", json_type),
        sa.column("weather_data", json_type),
    )
    moment_mood_activity = sa.table(
        "moment_mood_activity",
        sa.column("id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("moment_id", sa.Uuid()),
        sa.column("mood_id", sa.Uuid()),
        sa.column("activity_id", sa.Uuid()),
    )

    entry_to_moment: Dict[uuid.UUID, uuid.UUID] = {}

    entries = conn.execute(sa.select(entry)).fetchall()
    for row in entries:
        moment_id = uuid.uuid4()
        entry_id = _as_uuid(row.id)
        entry_to_moment[entry_id] = moment_id
        conn.execute(
            moment.insert().values(
                id=moment_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
                user_id=row.user_id,
                entry_id=entry_id,
                primary_mood_id=None,
                logged_at=row.entry_datetime_utc,
                logged_date=row.entry_date,
                logged_timezone=row.entry_timezone or "UTC",
                note=None,
                location_data=row.location_json,
                weather_data=row.weather_json,
            )
        )

    mood_log_links: Dict[uuid.UUID, List[uuid.UUID]] = {}
    for link in conn.execute(sa.select(mood_log_activity_link)).fetchall():
        mood_log_id = _as_uuid(link.mood_log_id)
        activity_id = _as_uuid(link.activity_id)
        mood_log_links.setdefault(mood_log_id, []).append(activity_id)

    mood_logs = conn.execute(sa.select(mood_log)).fetchall()
    inserted_mood_only: set[Tuple[uuid.UUID, uuid.UUID]] = set()
    inserted_mood_activity: set[Tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = set()
    for row in mood_logs:
        entry_id = _as_uuid(row.entry_id)
        mood_id = _as_uuid(row.mood_id)
        activities = mood_log_links.get(_as_uuid(row.id), [])

        if entry_id and entry_id in entry_to_moment:
            moment_id = entry_to_moment[entry_id]
            update_values = {"primary_mood_id": mood_id}
            if row.note is not None:
                update_values["note"] = row.note
            conn.execute(
                moment.update()
                .where(moment.c.id == moment_id)
                .values(**update_values)
            )
        else:
            moment_id = uuid.uuid4()
            conn.execute(
                moment.insert().values(
                    id=moment_id,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    user_id=row.user_id,
                    entry_id=None,
                    primary_mood_id=mood_id,
                    logged_at=row.logged_datetime_utc,
                    logged_date=row.logged_date,
                    logged_timezone=row.logged_timezone or "UTC",
                    note=row.note,
                    location_data=None,
                    weather_data=None,
                )
            )

        if activities:
            for activity_id in activities:
                mood_activity_key = (moment_id, mood_id, activity_id)
                if mood_activity_key in inserted_mood_activity:
                    continue
                conn.execute(
                    moment_mood_activity.insert().values(
                        id=uuid.uuid4(),
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                        moment_id=moment_id,
                        mood_id=mood_id,
                        activity_id=activity_id,
                    )
                )
                inserted_mood_activity.add(mood_activity_key)
        else:
            mood_only_key = (moment_id, mood_id)
            if mood_only_key not in inserted_mood_only:
                conn.execute(
                    moment_mood_activity.insert().values(
                        id=uuid.uuid4(),
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                        moment_id=moment_id,
                        mood_id=mood_id,
                        activity_id=None,
                    )
                )
                inserted_mood_only.add(mood_only_key)

    entry_activities = conn.execute(sa.select(entry_activity_link)).fetchall()
    for row in entry_activities:
        entry_id = _as_uuid(row.entry_id)
        activity_id = _as_uuid(row.activity_id)
        moment_id = entry_to_moment.get(entry_id)
        if moment_id is None:
            continue
        conn.execute(
            moment_mood_activity.insert().values(
                id=uuid.uuid4(),
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
                moment_id=moment_id,
                mood_id=None,
                activity_id=activity_id,
            )
        )

    activity_logs = conn.execute(sa.select(activity_log)).fetchall()
    for row in activity_logs:
        moment_id = uuid.uuid4()
        conn.execute(
            moment.insert().values(
                id=moment_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
                user_id=row.user_id,
                entry_id=None,
                primary_mood_id=None,
                logged_at=row.logged_datetime_utc,
                logged_date=row.logged_date,
                logged_timezone=row.logged_timezone or "UTC",
                note=row.note,
                location_data=None,
                weather_data=None,
            )
        )
        conn.execute(
            moment_mood_activity.insert().values(
                id=uuid.uuid4(),
                created_at=row.created_at,
                updated_at=row.updated_at,
                moment_id=moment_id,
                mood_id=None,
                activity_id=row.activity_id,
            )
        )

    for row in conn.execute(sa.select(entry_media)).fetchall():
        entry_id = _as_uuid(row.entry_id)
        moment_id = entry_to_moment.get(entry_id)
        if moment_id is None:
            continue
        conn.execute(
            entry_media.update()
            .where(entry_media.c.id == row.id)
            .values(moment_id=moment_id)
        )

    # --- g1h2i3j4k5l6_drop_legacy_mood_activity_logs.py ---
    op.drop_table("mood_log_activity_link")
    op.drop_table("entry_activity_link")
    op.drop_table("activity_log")
    op.drop_table("mood_log")

    # --- h3i4j5k6l7m8_add_goals_and_week_start.py ---
    if is_sqlite:
        with op.batch_alter_table("user_settings") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "start_of_week_day", sa.Integer(), nullable=False, server_default="0"
                ),
            )
            batch_op.create_check_constraint(
                "check_start_of_week_day_valid",
                "start_of_week_day >= 0 AND start_of_week_day <= 6",
            )
    else:
        op.add_column(
            "user_settings",
            sa.Column(
                "start_of_week_day", sa.Integer(), nullable=False, server_default="0"
            ),
        )
        op.create_check_constraint(
            "check_start_of_week_day_valid",
            "user_settings",
            "start_of_week_day >= 0 AND start_of_week_day <= 6",
        )

    op.create_table(
        "goal",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "target_days_per_week", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["activity_id"], ["activity.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_goal_user_active", "goal", ["user_id", "archived_at"], unique=False
    )
    op.create_index("ix_goal_activity_id", "goal", ["activity_id"], unique=False)
    op.create_index("ix_goal_user_id", "goal", ["user_id"], unique=False)
    if is_sqlite:
        with op.batch_alter_table("goal") as batch_op:
            batch_op.create_check_constraint(
                "check_goal_target_days_per_week",
                "target_days_per_week >= 1 AND target_days_per_week <= 7",
            )
    else:
        op.create_check_constraint(
            "check_goal_target_days_per_week",
            "goal",
            "target_days_per_week >= 1 AND target_days_per_week <= 7",
        )

    op.create_table(
        "goal_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("logged_date", sa.Date(), nullable=False),
        sa.Column("moment_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["goal_id"], ["goal.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["moment_id"], ["moment.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("goal_id", "logged_date", name="uq_goal_log_goal_date"),
    )
    op.create_index(
        "idx_goal_log_goal_date", "goal_log", ["goal_id", "logged_date"], unique=False
    )
    op.create_index(
        "idx_goal_log_user_date", "goal_log", ["user_id", "logged_date"], unique=False
    )
    op.create_index("ix_goal_log_goal_id", "goal_log", ["goal_id"], unique=False)
    op.create_index("ix_goal_log_user_id", "goal_log", ["user_id"], unique=False)
    op.create_index(
        "ix_goal_log_logged_date", "goal_log", ["logged_date"], unique=False
    )
    op.create_index("ix_goal_log_moment_id", "goal_log", ["moment_id"], unique=False)

    # --- i9k0l1m2n3o4_add_activity_group_icon_and_color_value.py ---
    # --- l2m3n4o5p6q7_alter_activity_group_color_value_bigint.py ---
    # Combined: add icon, replace color_hex with color_value (BigInteger)
    if is_sqlite:
        with op.batch_alter_table("activity_group") as batch_op:
            batch_op.add_column(sa.Column("icon", sa.String(length=50), nullable=True))
            batch_op.add_column(sa.Column("color_value", sa.BigInteger(), nullable=True))
            batch_op.drop_column("color_hex")
    else:
        op.add_column(
            "activity_group",
            sa.Column("icon", sa.String(length=50), nullable=True),
        )
        op.add_column(
            "activity_group",
            sa.Column("color_value", sa.Integer(), nullable=True),
        )
        op.drop_column("activity_group", "color_hex")
        op.alter_column(
            "activity_group",
            "color_value",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=True,
        )

    # --- m3n4o5p6q7r8_add_activity_position.py ---
    if is_sqlite:
        with op.batch_alter_table("activity") as batch_op:
            batch_op.add_column(
                sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            )
        # SQLite doesn't enforce server_default removal the same way; just create the index
    else:
        op.add_column(
            "activity",
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        )
        op.alter_column("activity", "position", server_default=None)
    op.create_index(
        "idx_activity_user_group_position",
        "activity",
        ["user_id", "group_id", "position"],
        unique=False,
    )

    # --- n4o5p6q7r8s9_add_custom_moods_and_preferences.py ---
    if is_sqlite:
        with op.batch_alter_table("mood") as batch_op:
            batch_op.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
            batch_op.add_column(sa.Column("key", sa.String(length=50), nullable=True))
            batch_op.add_column(
                sa.Column("score", sa.Integer(), nullable=False, server_default="3"),
            )
            batch_op.add_column(
                sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            )
            batch_op.add_column(
                sa.Column(
                    "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
                ),
            )
            batch_op.create_foreign_key(
                "fk_mood_user_id",
                "user",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_check_constraint(
                "check_mood_score_range",
                "score >= 1 AND score <= 5",
            )
    else:
        op.add_column("mood", sa.Column("user_id", sa.Uuid(), nullable=True))
        op.add_column("mood", sa.Column("key", sa.String(length=50), nullable=True))
        op.add_column(
            "mood",
            sa.Column("score", sa.Integer(), nullable=False, server_default="3"),
        )
        op.add_column(
            "mood",
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        )
        op.add_column(
            "mood",
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
            ),
        )
        op.create_foreign_key(
            "fk_mood_user_id",
            "mood",
            "user",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_check_constraint(
            "check_mood_score_range",
            "mood",
            "score >= 1 AND score <= 5",
        )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'mood_name_key'
                ) THEN
                    ALTER TABLE mood DROP CONSTRAINT mood_name_key;
                END IF;
            END
            $$;
            """
        )
    else:
        op.execute("DROP INDEX IF EXISTS mood_name_key")

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mood_user_name
        ON mood (user_id, lower(name))
        WHERE user_id IS NOT NULL;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mood_system_key
        ON mood (key)
        WHERE user_id IS NULL AND key IS NOT NULL;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mood_user_position
        ON mood (user_id, position);
        """
    )

    op.create_table(
        "user_mood_preference",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("mood_id", sa.Uuid(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mood_id"], ["mood.id"], ondelete="CASCADE"),
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

    system_moods: List[Tuple[str, str, str, int, int]] = [
        ("Happy", "happy", "smile", 5, 10),
        ("Excited", "excited", "laugh", 5, 20),
        ("Grateful", "grateful", "heart", 5, 30),
        ("Calm", "calm", "wind", 4, 40),
        ("Focused", "focused", "target", 4, 50),
        ("Sad", "sad", "frown", 2, 60),
        ("Angry", "angry", "angry", 1, 70),
        ("Stressed", "stressed", "zap", 2, 80),
        ("Lonely", "lonely", "moon", 2, 90),
        ("Tired", "tired", "coffee", 2, 100),
        ("Neutral", "neutral", "meh", 3, 110),
        ("Confused", "confused", "triangle", 3, 120),
        ("Curious", "curious", "star", 3, 130),
        ("Surprised", "surprised", "sparkles", 4, 140),
        ("Anxious", "anxious", "triangleAlert", 2, 150),
        ("Proud", "proud", "trophy", 4, 160),
        ("Hopeful", "hopeful", "sun", 4, 170),
        ("Disappointed", "disappointed", "thumbsDown", 2, 180),
        ("Relaxed", "relaxed", "cloud", 4, 190),
        ("Motivated", "motivated", "thumbsUp", 4, 200),
    ]

    for name, key, icon, score, position in system_moods:
        op.execute(
            sa.text(
                """
                UPDATE mood
                SET key = :key,
                    icon = :icon,
                    score = :score,
                    position = :position,
                    is_active = true
                WHERE name = :name AND user_id IS NULL;
                """
            ).bindparams(name=name, key=key, icon=icon, score=score, position=position)
        )

    # --- o5p6q7r8s9t0_add_mood_color_and_simplify_system.py ---
    op.add_column("mood", sa.Column("color_value", sa.BigInteger(), nullable=True))

    # Simplified system mood set with lucide icon names and colors.
    system_moods = [
        # name, key, icon, score, color_value, position
        ("Awesome", "awesome", "smilePlus", 5, 0xFF00C853, 10),
        ("Good", "good", "smile", 4, 0xFF43A047, 20),
        ("Meh", "meh", "meh", 3, 0xFFF1C40F, 30),
        ("Bad", "bad", "frown", 2, 0xFFFB8C00, 40),
        ("Awful", "awful", "angry", 1, 0xFFE53935, 50),
    ]

    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        now = datetime.now(timezone.utc)
        for name, key, icon, score, color_value, position in system_moods:
            bind.execute(
                sa.text(
                    """
                    UPDATE mood
                    SET name = :name,
                        icon = :icon,
                        color_value = :color_value,
                        score = :score,
                        position = :position,
                        category = CASE WHEN :score >= 4 THEN 'positive'
                                        WHEN :score <= 2 THEN 'negative'
                                        ELSE 'neutral'
                                   END,
                        is_active = true
                    WHERE key = :key AND user_id IS NULL;
                    """
                ),
                {
                    "name": name,
                    "key": key,
                    "icon": icon,
                    "score": score,
                    "color_value": color_value,
                    "position": position,
                },
            )
            exists = bind.execute(
                sa.text("SELECT 1 FROM mood WHERE key = :key AND user_id IS NULL"),
                {"key": key},
            ).fetchone()
            if not exists:
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO mood (
                            id, created_at, updated_at, name, key, icon, color_value,
                            category, score, position, is_active, user_id
                        )
                        VALUES (
                            :id, :created_at, :updated_at, :name, :key, :icon, :color_value,
                            CASE WHEN :score >= 4 THEN 'positive'
                                 WHEN :score <= 2 THEN 'negative'
                                 ELSE 'neutral'
                            END,
                            :score, :position, 1, NULL
                        );
                        """
                    ),
                    {
                        "id": uuid.uuid4().hex,
                        "created_at": now,
                        "updated_at": now,
                        "name": name,
                        "key": key,
                        "icon": icon,
                        "color_value": color_value,
                        "score": score,
                        "position": position,
                    },
                )

        bind.execute(
            sa.text(
                """
                UPDATE mood
                SET is_active = 0
                WHERE user_id IS NULL
                  AND (key IS NULL OR key NOT IN ('awesome', 'good', 'meh', 'bad', 'awful'));
                """
            )
        )

        deprecated_moods = bind.execute(
            sa.text(
                """
                SELECT id, position
                FROM mood
                WHERE user_id IS NULL
                  AND (key IS NULL OR key NOT IN ('awesome', 'good', 'meh', 'bad', 'awful'));
                """
            )
        ).fetchall()
        user_rows = bind.execute(sa.text('SELECT id FROM "user"')).fetchall()
        for (user_id,) in user_rows:
            for mood_id, position in deprecated_moods:
                bind.execute(
                    sa.text(
                        """
                        UPDATE user_mood_preference
                        SET is_hidden = 1
                        WHERE user_id = :user_id AND mood_id = :mood_id;
                        """
                    ),
                    {"user_id": user_id, "mood_id": mood_id},
                )
                exists = bind.execute(
                    sa.text(
                        """
                        SELECT 1 FROM user_mood_preference
                        WHERE user_id = :user_id AND mood_id = :mood_id;
                        """
                    ),
                    {"user_id": user_id, "mood_id": mood_id},
                ).fetchone()
                if not exists:
                    bind.execute(
                        sa.text(
                            """
                            INSERT INTO user_mood_preference (
                                id, created_at, updated_at, user_id, mood_id, sort_order, is_hidden
                            )
                            VALUES (
                                :id, :created_at, :updated_at, :user_id, :mood_id, :sort_order, 1
                            );
                            """
                        ),
                        {
                            "id": uuid.uuid4().hex,
                            "created_at": now,
                            "updated_at": now,
                            "user_id": user_id,
                            "mood_id": mood_id,
                            "sort_order": int(position or 0),
                        },
                    )
    else:
        for name, key, icon, score, color_value, position in system_moods:
            op.execute(
                sa.text(
                    """
                    UPDATE mood
                    SET name = :name,
                        icon = :icon,
                        color_value = :color_value,
                        score = :score,
                        position = :position,
                        category = CASE WHEN :score >= 4 THEN 'positive'
                                        WHEN :score <= 2 THEN 'negative'
                                        ELSE 'neutral'
                                   END,
                        is_active = true
                    WHERE key = :key AND user_id IS NULL;
                    """
                ).bindparams(
                    name=name,
                    key=key,
                    icon=icon,
                    score=score,
                    color_value=color_value,
                    position=position,
                )
            )
            op.execute(
                sa.text(
                    """
                    INSERT INTO mood (id, created_at, updated_at, name, key, icon, color_value, category, score, position, is_active, user_id)
                    SELECT gen_random_uuid(), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :name, :key, :icon, :color_value,
                           CASE WHEN :score >= 4 THEN 'positive'
                                WHEN :score <= 2 THEN 'negative'
                                ELSE 'neutral'
                           END,
                           :score, :position, true, NULL
                    WHERE NOT EXISTS (
                        SELECT 1 FROM mood WHERE key = :key AND user_id IS NULL
                    );
                    """
                ).bindparams(
                    name=name,
                    key=key,
                    icon=icon,
                    score=score,
                    color_value=color_value,
                    position=position,
                )
            )

        # Hide deprecated system moods for all users (do not delete; keep for history).
        op.execute(
            """
            UPDATE mood
            SET is_active = false
            WHERE user_id IS NULL
              AND (key IS NULL OR key NOT IN ('awesome', 'good', 'meh', 'bad', 'awful'));

            INSERT INTO user_mood_preference (id, created_at, updated_at, user_id, mood_id, sort_order, is_hidden)
            SELECT gen_random_uuid(),
                   CURRENT_TIMESTAMP,
                   CURRENT_TIMESTAMP,
                   u.id,
                   m.id,
                   m.position,
                   true
            FROM "user" u
            CROSS JOIN mood m
            WHERE m.user_id IS NULL
              AND (m.key IS NULL OR m.key NOT IN ('awesome', 'good', 'meh', 'bad', 'awful'))
            ON CONFLICT (user_id, mood_id) DO UPDATE
            SET is_hidden = EXCLUDED.is_hidden;
            """
        )

    # --- p6q7r8s9t0u1_add_goal_period_tracking.py ---
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    _create_enum_types(dialect_name)

    if dialect_name == "postgresql":
        from sqlalchemy.dialects.postgresql import ENUM

        goal_type = ENUM("achieve", "avoid", name="goal_type_enum", create_type=False)
        goal_frequency = ENUM(
            "daily", "weekly", "monthly", name="goal_frequency_enum", create_type=False
        )
        goal_log_status = ENUM(
            "success", "fail", "skipped", name="goal_log_status_enum", create_type=False
        )
        goal_log_source = ENUM(
            "auto", "manual", name="goal_log_source_enum", create_type=False
        )
    else:
        goal_type = sa.String(length=20)
        goal_frequency = sa.String(length=20)
        goal_log_status = sa.String(length=20)
        goal_log_source = sa.String(length=20)

    op.add_column(
        "goal",
        sa.Column("goal_type", goal_type, nullable=False, server_default="achieve"),
    )
    op.add_column(
        "goal",
        sa.Column(
            "frequency_type", goal_frequency, nullable=False, server_default="daily"
        ),
    )
    op.add_column(
        "goal",
        sa.Column("target_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "goal",
        sa.Column("reminder_time", sa.String(length=5), nullable=True),
    )
    op.add_column(
        "goal",
        sa.Column(
            "is_paused", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "goal",
        sa.Column("icon", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "goal",
        sa.Column("color_value", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "goal",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )

    op.execute(
        """
        UPDATE goal
        SET target_count = COALESCE(target_days_per_week, 1),
            frequency_type = 'weekly',
            goal_type = 'achieve'
        WHERE target_days_per_week IS NOT NULL;
        """
    )

    if is_sqlite:
        with op.batch_alter_table("goal") as batch_op:
            batch_op.drop_constraint(
                "check_goal_target_days_per_week", type_="check"
            )
            batch_op.drop_column("target_days_per_week")
            batch_op.create_check_constraint(
                "check_goal_target_count", "target_count >= 1"
            )
    else:
        op.drop_column("goal", "target_days_per_week")
        op.create_check_constraint("check_goal_target_count", "goal", "target_count >= 1")
    op.create_index(
        "idx_goal_user_position", "goal", ["user_id", "position"], unique=False
    )

    op.add_column(
        "goal_log",
        sa.Column("period_start", sa.Date(), nullable=True),
    )
    op.add_column(
        "goal_log",
        sa.Column("period_end", sa.Date(), nullable=True),
    )
    op.add_column(
        "goal_log",
        sa.Column("status", goal_log_status, nullable=False, server_default="success"),
    )
    op.add_column(
        "goal_log",
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "goal_log",
        sa.Column("source", goal_log_source, nullable=False, server_default="auto"),
    )
    op.add_column(
        "goal_log",
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.execute(
        """
        UPDATE goal_log
        SET period_start = logged_date,
            period_end = logged_date,
            count = 1,
            status = 'success',
            source = 'auto',
            last_updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP);
        """
    )

    if is_sqlite:
        with op.batch_alter_table("goal_log") as batch_op:
            batch_op.alter_column("period_start", nullable=False)
            batch_op.alter_column("period_end", nullable=False)
    else:
        op.alter_column("goal_log", "period_start", nullable=False)
        op.alter_column("goal_log", "period_end", nullable=False)

    # Deduplicate existing logs before enforcing uniqueness.
    if not is_sqlite:
        op.execute(
            """
            DELETE FROM goal_log
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY goal_id, period_start
                               ORDER BY last_updated_at DESC, id DESC
                           ) AS rn
                    FROM goal_log
                ) dedup
                WHERE dedup.rn > 1
            )
            """
        )
    else:
        op.execute(
            """
            DELETE FROM goal_log
            WHERE rowid IN (
                SELECT rowid FROM (
                    SELECT rowid,
                           ROW_NUMBER() OVER (
                               PARTITION BY goal_id, period_start
                               ORDER BY last_updated_at DESC, id DESC
                           ) AS rn
                    FROM goal_log
                ) dedup
                WHERE dedup.rn > 1
            )
            """
        )

    if not is_sqlite:
        op.execute(
            """
            DO $$ BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_goal_log_goal_date'
                ) THEN
                    ALTER TABLE goal_log DROP CONSTRAINT uq_goal_log_goal_date;
                END IF;
                IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'uq_goal_log_goal_period'
                ) THEN
                    ALTER TABLE goal_log DROP CONSTRAINT uq_goal_log_goal_period;
                END IF;
            END $$;
            """
        )
        op.execute("DROP INDEX IF EXISTS idx_goal_log_goal_period")
        op.create_unique_constraint(
            "uq_goal_log_goal_period", "goal_log", ["goal_id", "period_start"]
        )
        op.create_index(
            "idx_goal_log_goal_period",
            "goal_log",
            ["goal_id", "period_start"],
            unique=False,
        )
    else:
        with op.batch_alter_table("goal_log") as batch_op:
            batch_op.drop_constraint("uq_goal_log_goal_date", type_="unique")
            batch_op.create_unique_constraint(
                "uq_goal_log_goal_period", ["goal_id", "period_start"]
            )
            batch_op.create_index(
                "idx_goal_log_goal_period", ["goal_id", "period_start"], unique=False
            )

    if not is_sqlite:
        op.execute(
            """
            DO $$ BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_name = 'goal_manual_log'
                ) THEN
                    DELETE FROM goal_manual_log
                    WHERE id IN (
                        SELECT id FROM (
                            SELECT id,
                                   ROW_NUMBER() OVER (
                                       PARTITION BY goal_id, logged_date
                                       ORDER BY updated_at DESC, id DESC
                                   ) AS rn
                            FROM goal_manual_log
                        ) dedup
                        WHERE dedup.rn > 1
                    );
                END IF;
            END $$;
            """
        )

    op.create_table(
        "goal_manual_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("goal_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("logged_date", sa.Date(), nullable=False),
        sa.Column("status", goal_log_status, nullable=False, server_default="success"),
        sa.ForeignKeyConstraint(["goal_id"], ["goal.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "goal_id", "logged_date", name="uq_goal_manual_log_goal_date"
        ),
    )
    op.create_index(
        "idx_goal_manual_log_goal_date",
        "goal_manual_log",
        ["goal_id", "logged_date"],
        unique=False,
    )
    op.create_index(
        "idx_goal_manual_log_user_date",
        "goal_manual_log",
        ["user_id", "logged_date"],
        unique=False,
    )

    # --- q7r8s9t0u1v2_add_mood_groups.py ---
    op.create_table(
        "mood_group",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("color_value", sa.BigInteger(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_mood_group_user_position", "mood_group", ["user_id", "position"]
    )
    op.create_index("idx_mood_group_user_id", "mood_group", ["user_id"])

    op.create_table(
        "mood_group_link",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mood_group_id", sa.Uuid(), nullable=False),
        sa.Column("mood_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["mood_group_id"], ["mood_group.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["mood_id"], ["mood.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_mood_group_link_group_id", "mood_group_link", ["mood_group_id"]
    )
    op.create_index("idx_mood_group_link_mood_id", "mood_group_link", ["mood_id"])
    op.create_index(
        "idx_mood_group_link_group_position",
        "mood_group_link",
        ["mood_group_id", "position"],
    )
    op.create_index(
        "uq_mood_group_link_group_mood",
        "mood_group_link",
        ["mood_group_id", "mood_id"],
        unique=True,
    )

    op.create_table(
        "user_mood_group_preference",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("mood_group_id", sa.Uuid(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["mood_group_id"], ["mood_group.id"], ondelete="CASCADE"
        ),
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
    )

    bind = op.get_bind()
    mood_group_table = sa.table(
        "mood_group",
        sa.column("id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("user_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("icon", sa.String()),
        sa.column("color_value", sa.BigInteger()),
        sa.column("position", sa.Integer()),
    )
    mood_group_link_table = sa.table(
        "mood_group_link",
        sa.column("id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("mood_group_id", sa.Uuid()),
        sa.column("mood_id", sa.Uuid()),
        sa.column("position", sa.Integer()),
    )

    now = datetime.now(timezone.utc)
    group_rows = []
    score_to_group_id: dict[int, uuid.UUID] = {}
    for score, name, position in TIER_GROUPS:
        group_id = uuid.uuid4()
        score_to_group_id[score] = group_id
        group_rows.append(
            {
                "id": group_id,
                "created_at": now,
                "updated_at": now,
                "user_id": None,
                "name": name,
                "icon": None,
                "color_value": None,
                "position": position,
            }
        )
    op.bulk_insert(mood_group_table, group_rows)

    mood_rows = bind.execute(
        sa.text("SELECT id, score, position FROM mood WHERE is_active = true")
    ).fetchall()
    link_rows = []
    for mood_id, score, position in mood_rows:
        group_id = score_to_group_id.get(int(score))
        if not group_id:
            continue
        link_rows.append(
            {
                "id": uuid.uuid4(),
                "created_at": now,
                "updated_at": now,
                "mood_group_id": group_id,
                "mood_id": _as_uuid(mood_id),
                "position": int(position or 0),
            }
        )
    if link_rows:
        op.bulk_insert(mood_group_link_table, link_rows)

    # --- r8s9t0u1v2w3_add_goal_categories.py ---
    op.create_table(
        "goal_category",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("color_value", sa.BigInteger(), nullable=True),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_goal_category_user_name",
        "goal_category",
        ["user_id", "name"],
        unique=True,
    )
    op.create_index(
        "ix_goal_category_user_id",
        "goal_category",
        ["user_id"],
    )

    if is_sqlite:
        with op.batch_alter_table("goal") as batch_op:
            batch_op.add_column(sa.Column("category_id", sa.Uuid(), nullable=True))
            batch_op.create_index(
                "ix_goal_category_id",
                ["category_id"],
            )
            batch_op.create_foreign_key(
                "fk_goal_category_id_goal_category",
                "goal_category",
                ["category_id"],
                ["id"],
                ondelete="SET NULL",
            )
    else:
        op.add_column(
            "goal",
            sa.Column("category_id", sa.Uuid(), nullable=True),
        )
        op.create_index(
            "ix_goal_category_id",
            "goal",
            ["category_id"],
        )
        op.create_foreign_key(
            "fk_goal_category_id_goal_category",
            "goal",
            "goal_category",
            ["category_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "idx_goal_user_category_position",
        "goal",
        ["user_id", "category_id", "position"],
    )


def downgrade() -> None:
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    # --- r8s9t0u1v2w3_add_goal_categories.py ---
    op.drop_index("idx_goal_user_category_position", table_name="goal")
    if is_sqlite:
        with op.batch_alter_table("goal") as batch_op:
            batch_op.drop_constraint("fk_goal_category_id_goal_category", type_="foreignkey")
            batch_op.drop_index("ix_goal_category_id")
            batch_op.drop_column("category_id")
    else:
        op.drop_constraint("fk_goal_category_id_goal_category", "goal", type_="foreignkey")
        op.drop_index("ix_goal_category_id", table_name="goal")
        op.drop_column("goal", "category_id")

    op.drop_index("idx_goal_category_user_name", table_name="goal_category")
    op.drop_index("ix_goal_category_user_id", table_name="goal_category")
    op.drop_table("goal_category")

    # --- q7r8s9t0u1v2_add_mood_groups.py ---
    op.drop_index(
        "idx_user_mood_group_preference_user_sort_order",
        table_name="user_mood_group_preference",
    )
    op.drop_index(
        "uq_user_mood_group_preference_user_group",
        table_name="user_mood_group_preference",
    )
    op.drop_table("user_mood_group_preference")

    op.drop_index("uq_mood_group_link_group_mood", table_name="mood_group_link")
    op.drop_index("idx_mood_group_link_group_position", table_name="mood_group_link")
    op.drop_index("idx_mood_group_link_mood_id", table_name="mood_group_link")
    op.drop_index("idx_mood_group_link_group_id", table_name="mood_group_link")
    op.drop_table("mood_group_link")

    op.drop_index("idx_mood_group_user_id", table_name="mood_group")
    op.drop_index("idx_mood_group_user_position", table_name="mood_group")
    op.drop_table("mood_group")

    # --- p6q7r8s9t0u1_add_goal_period_tracking.py ---
    op.drop_index("idx_goal_manual_log_user_date", table_name="goal_manual_log")
    op.drop_index("idx_goal_manual_log_goal_date", table_name="goal_manual_log")
    op.drop_table("goal_manual_log")

    op.drop_index("idx_goal_log_goal_period", table_name="goal_log")
    if is_sqlite:
        with op.batch_alter_table("goal_log") as batch_op:
            batch_op.drop_constraint("uq_goal_log_goal_period", type_="unique")
            batch_op.create_unique_constraint(
                "uq_goal_log_goal_date", ["goal_id", "logged_date"]
            )
            batch_op.drop_column("last_updated_at")
            batch_op.drop_column("source")
            batch_op.drop_column("count")
            batch_op.drop_column("status")
            batch_op.drop_column("period_end")
            batch_op.drop_column("period_start")
    else:
        op.drop_constraint("uq_goal_log_goal_period", "goal_log", type_="unique")
        op.create_unique_constraint(
            "uq_goal_log_goal_date", "goal_log", ["goal_id", "logged_date"]
        )
        op.drop_column("goal_log", "last_updated_at")
        op.drop_column("goal_log", "source")
        op.drop_column("goal_log", "count")
        op.drop_column("goal_log", "status")
        op.drop_column("goal_log", "period_end")
        op.drop_column("goal_log", "period_start")

    op.drop_index("idx_goal_user_position", table_name="goal")
    if is_sqlite:
        with op.batch_alter_table("goal") as batch_op:
            batch_op.drop_constraint("check_goal_target_count", type_="check")
            batch_op.add_column(
                sa.Column(
                    "target_days_per_week", sa.Integer(), nullable=False, server_default="1"
                ),
            )
            batch_op.create_check_constraint(
                "check_goal_target_days_per_week",
                "target_days_per_week >= 1 AND target_days_per_week <= 7",
            )
            batch_op.drop_column("position")
            batch_op.drop_column("color_value")
            batch_op.drop_column("icon")
            batch_op.drop_column("is_paused")
            batch_op.drop_column("reminder_time")
            batch_op.drop_column("target_count")
            batch_op.drop_column("frequency_type")
            batch_op.drop_column("goal_type")
    else:
        op.drop_constraint("check_goal_target_count", "goal", type_="check")
        op.add_column(
            "goal",
            sa.Column(
                "target_days_per_week", sa.Integer(), nullable=False, server_default="1"
            ),
        )
        op.create_check_constraint(
            "check_goal_target_days_per_week",
            "goal",
            "target_days_per_week >= 1 AND target_days_per_week <= 7",
        )
        op.drop_column("goal", "position")
        op.drop_column("goal", "color_value")
        op.drop_column("goal", "icon")
        op.drop_column("goal", "is_paused")
        op.drop_column("goal", "reminder_time")
        op.drop_column("goal", "target_count")
        op.drop_column("goal", "frequency_type")
        op.drop_column("goal", "goal_type")

    # --- o5p6q7r8s9t0_add_mood_color_and_simplify_system.py ---
    # --- n4o5p6q7r8s9_add_custom_moods_and_preferences.py ---
    op.drop_index(
        "idx_user_mood_preference_user_sort_order", table_name="user_mood_preference"
    )
    op.drop_index(
        "uq_user_mood_preference_user_mood", table_name="user_mood_preference"
    )
    op.drop_table("user_mood_preference")

    op.execute("DROP INDEX IF EXISTS uq_mood_system_key")
    op.execute("DROP INDEX IF EXISTS uq_mood_user_name")
    op.execute("DROP INDEX IF EXISTS idx_mood_user_position")

    if is_sqlite:
        with op.batch_alter_table("mood") as batch_op:
            batch_op.drop_constraint("check_mood_score_range", type_="check")
            batch_op.drop_constraint("fk_mood_user_id", type_="foreignkey")
            batch_op.drop_column("color_value")
            batch_op.drop_column("is_active")
            batch_op.drop_column("position")
            batch_op.drop_column("score")
            batch_op.drop_column("key")
            batch_op.drop_column("user_id")
    else:
        op.drop_column("mood", "color_value")
        op.drop_constraint("check_mood_score_range", "mood", type_="check")
        op.drop_constraint("fk_mood_user_id", "mood", type_="foreignkey")
        op.drop_column("mood", "is_active")
        op.drop_column("mood", "position")
        op.drop_column("mood", "score")
        op.drop_column("mood", "key")
        op.drop_column("mood", "user_id")

    # --- m3n4o5p6q7r8_add_activity_position.py ---
    op.drop_index("idx_activity_user_group_position", table_name="activity")
    op.drop_column("activity", "position")

    # --- l2m3n4o5p6q7_alter_activity_group_color_value_bigint.py ---
    # --- i9k0l1m2n3o4_add_activity_group_icon_and_color_value.py ---
    if is_sqlite:
        with op.batch_alter_table("activity_group") as batch_op:
            batch_op.add_column(sa.Column("color_hex", sa.String(length=7), nullable=True))
            batch_op.drop_column("color_value")
            batch_op.drop_column("icon")
    else:
        op.alter_column(
            "activity_group",
            "color_value",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
        op.add_column(
            "activity_group",
            sa.Column("color_hex", sa.String(length=7), nullable=True),
        )
        op.drop_column("activity_group", "color_value")
        op.drop_column("activity_group", "icon")

    # --- h3i4j5k6l7m8_add_goals_and_week_start.py ---
    op.drop_index("ix_goal_log_moment_id", table_name="goal_log")
    op.drop_index("ix_goal_log_logged_date", table_name="goal_log")
    op.drop_index("ix_goal_log_user_id", table_name="goal_log")
    op.drop_index("ix_goal_log_goal_id", table_name="goal_log")
    op.drop_index("idx_goal_log_user_date", table_name="goal_log")
    op.drop_index("idx_goal_log_goal_date", table_name="goal_log")
    op.drop_table("goal_log")

    op.drop_index("ix_goal_user_id", table_name="goal")
    op.drop_index("ix_goal_activity_id", table_name="goal")
    op.drop_index("idx_goal_user_active", table_name="goal")
    op.drop_table("goal")

    if is_sqlite:
        with op.batch_alter_table("user_settings") as batch_op:
            batch_op.drop_constraint("check_start_of_week_day_valid", type_="check")
            batch_op.drop_column("start_of_week_day")
    else:
        op.drop_constraint("check_start_of_week_day_valid", "user_settings", type_="check")
        op.drop_column("user_settings", "start_of_week_day")

    # --- g1h2i3j4k5l6_drop_legacy_mood_activity_logs.py ---
    # WARNING (downgrade): This downgrade only recreates legacy tables like mood_log
    # and activity_log but does not restore rows migrated into moment and
    # moment_mood_activity. Downgrading will permanently lose mood/activity log
    # data for users. Avoid running downgrade in production environments.
    # (downgrade: mood_log, activity_log, moment, moment_mood_activity)
    # Recreate legacy tables (minimal schema for downgrade compatibility)
    op.create_table(
        "mood_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=True),
        sa.Column("mood_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("logged_date", sa.Date(), nullable=False),
        sa.Column("logged_datetime_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("logged_timezone", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["entry_id"], ["entry.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mood_id"], ["mood.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_id"),
    )
    op.create_index(
        "idx_mood_logs_user_id_logged_date",
        "mood_log",
        ["user_id", "logged_date"],
        unique=False,
    )
    op.create_index(
        "idx_mood_logs_user_datetime",
        "mood_log",
        ["user_id", "logged_datetime_utc"],
        unique=False,
    )
    op.create_index(
        "idx_mood_logs_logged_date", "mood_log", ["logged_date"], unique=False
    )
    op.create_index("idx_mood_logs_mood_id", "mood_log", ["mood_id"], unique=False)
    op.create_index(
        "idx_mood_logs_user_mood", "mood_log", ["user_id", "mood_id"], unique=False
    )

    op.create_table(
        "activity_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("logged_date", sa.Date(), nullable=False),
        sa.Column("logged_datetime_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("logged_timezone", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activity_id"], ["activity.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_activity_log_user_date",
        "activity_log",
        ["user_id", "logged_date"],
        unique=False,
    )
    op.create_index(
        "idx_activity_log_user_datetime",
        "activity_log",
        ["user_id", "logged_datetime_utc"],
        unique=False,
    )
    op.create_index(
        "idx_activity_log_activity_id", "activity_log", ["activity_id"], unique=False
    )

    op.create_table(
        "entry_activity_link",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["entry.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activity_id"], ["activity.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entry_id", "activity_id"),
    )
    op.create_index(
        "idx_entry_activity_link_activity_id",
        "entry_activity_link",
        ["activity_id"],
        unique=False,
    )

    op.create_table(
        "mood_log_activity_link",
        sa.Column("mood_log_id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["mood_log_id"], ["mood_log.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["activity_id"], ["activity.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("mood_log_id", "activity_id"),
    )
    op.create_index(
        "idx_mood_log_activity_link_activity_id",
        "mood_log_activity_link",
        ["activity_id"],
        unique=False,
    )

    # --- f2a3b4c5d6e7_add_moment_architecture.py ---
    if is_sqlite:
        with op.batch_alter_table("entry_media") as batch_op:
            batch_op.drop_constraint("uq_entry_media_moment_checksum", type_="unique")
            batch_op.drop_constraint("check_media_entry_or_moment", type_="check")
            batch_op.drop_constraint(
                "fk_entry_media_moment_id_moment", type_="foreignkey"
            )
            batch_op.drop_index("idx_entry_media_moment_id")
            batch_op.drop_column("moment_id")
            batch_op.alter_column("entry_id", existing_type=sa.Uuid(), nullable=False)
    else:
        op.drop_constraint(
            "uq_entry_media_moment_checksum", "entry_media", type_="unique"
        )
        op.drop_constraint("check_media_entry_or_moment", "entry_media", type_="check")
        op.drop_constraint(
            "fk_entry_media_moment_id_moment", "entry_media", type_="foreignkey"
        )
        op.drop_index("idx_entry_media_moment_id", table_name="entry_media")
        op.drop_column("entry_media", "moment_id")
        op.alter_column(
            "entry_media", "entry_id", existing_type=sa.Uuid(), nullable=False
        )

    op.drop_index("uq_moment_mood_activity", table_name="moment_mood_activity")
    op.drop_index("uq_moment_mood_only", table_name="moment_mood_activity")
    op.drop_index("uq_moment_activity_only", table_name="moment_mood_activity")
    op.drop_index(
        "idx_moment_mood_activity_activity_id", table_name="moment_mood_activity"
    )
    op.drop_index("idx_moment_mood_activity_mood_id", table_name="moment_mood_activity")
    op.drop_index(
        "idx_moment_mood_activity_moment_id", table_name="moment_mood_activity"
    )
    op.drop_table("moment_mood_activity")

    op.drop_index("idx_moment_user_logged_date", table_name="moment")
    op.drop_index("idx_moment_user_logged_at", table_name="moment")
    op.drop_index(op.f("ix_moment_id"), table_name="moment")
    op.drop_table("moment")

    # --- abc2f3a4b5c6_add_activity_groups.py ---
    # ### commands auto generated by Alembic - adjusted manually ###
    if is_sqlite:
        with op.batch_alter_table("activity") as batch_op:
            batch_op.drop_constraint("fk_activity_group_id", type_="foreignkey")
            batch_op.drop_index("idx_activity_group_id")
            batch_op.drop_column("group_id")
    else:
        op.drop_constraint("fk_activity_group_id", "activity", type_="foreignkey")
        op.drop_index(op.f("idx_activity_group_id"), table_name="activity")
        op.drop_column("activity", "group_id")
    op.drop_index("idx_activity_group_user_name", table_name="activity_group")
    op.drop_table("activity_group")
    # ### end Alembic commands ###

    # --- d1e2f3a4b5c6_add_activity_tracking.py ---
    op.drop_index("idx_activity_user_name", table_name="activity")
    op.drop_table("activity")
