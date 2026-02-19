"""add activities moods goals moments (squashed)

Revision ID: aa9a7125186b
Revises: c9d2e1f0a1b2
Create Date: 2026-02-09 17:14:24.413472

"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

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


UUIDValue = uuid.UUID | str


def _as_uuid(value: Optional[UUIDValue], *, is_sqlite: bool) -> Optional[UUIDValue]:
    if value is None:
        return None
    parsed = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    return parsed


def _new_uuid(*, is_sqlite: bool) -> UUIDValue:
    return uuid.uuid4()


def _constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    """Check if a constraint exists in either PostgreSQL or SQLite."""
    if conn.dialect.name == "postgresql":
        result = conn.execute(
            sa.text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_constraint c
                    JOIN pg_class t ON c.conrelid = t.oid
                    WHERE c.conname = :constraint_name
                    AND t.relname = :table_name
                )
                """
            ),
            {"constraint_name": constraint_name, "table_name": table_name}
        ).scalar()
        return bool(result)
    else:
        # SQLite
        inspector = sa.inspect(conn)
        fks = inspector.get_foreign_keys(table_name)
        if any(fk.get("name") == constraint_name for fk in fks):
            return True
        ucs = inspector.get_unique_constraints(table_name)
        if any(uc.get("name") == constraint_name for uc in ucs):
            return True
        ccs = inspector.get_check_constraints(table_name)
        if any(cc.get("name") == constraint_name for cc in ccs):
            return True
        return False


def _index_exists(conn, index_name: str, table_name: Optional[str] = None) -> bool:
    """Check if an index exists in either PostgreSQL or SQLite."""
    if conn.dialect.name == "postgresql":
        result = conn.execute(
            sa.text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM pg_indexes
                    WHERE indexname = :index_name
                )
                """
            ),
            {"index_name": index_name}
        ).scalar()
        return bool(result)
    else:
        # SQLite
        if table_name:
            inspector = sa.inspect(conn)
            indexes = inspector.get_indexes(table_name)
            return any(idx.get("name") == index_name for idx in indexes)
        else:
            result = conn.execute(
                sa.text(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name=:index_name"
                ),
                {"index_name": index_name}
            ).fetchone()
            return result is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(conn)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _table_exists(conn, table_name: str) -> bool:
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def _derive_local_date(logged_at_utc, logged_timezone: Optional[str]):
    if logged_at_utc is None:
        return None
    if logged_at_utc.tzinfo is None:
        utc_dt = logged_at_utc.replace(tzinfo=timezone.utc)
    else:
        utc_dt = logged_at_utc.astimezone(timezone.utc)
    tz_name = (logged_timezone or "UTC").strip() or "UTC"
    fixed_offset_match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", tz_name)
    if fixed_offset_match:
        sign, hours, minutes = fixed_offset_match.groups()
        offset = timedelta(hours=int(hours), minutes=int(minutes))
        if sign == "-":
            offset = -offset
        tz = timezone(offset)
        return utc_dt.astimezone(tz).date()
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    return utc_dt.astimezone(tz).date()


def _backfill_moment_logged_date_tz(conn) -> None:
    if not _table_exists(conn, "moment"):
        return
    rows = conn.execute(
        sa.text(
            """
            SELECT id, logged_at_utc, logged_timezone
            FROM moment
            WHERE logged_date_tz IS NULL
            """
        )
    ).fetchall()
    for row in rows:
        derived_date = _derive_local_date(row.logged_at_utc, row.logged_timezone)
        if derived_date is None:
            continue
        conn.execute(
            sa.text("UPDATE moment SET logged_date_tz = :logged_date_tz WHERE id = :moment_id"),
            {"logged_date_tz": derived_date, "moment_id": row.id},
        )


def _rename_entry_media_to_moment_media(conn, is_sqlite: bool) -> None:
    if _table_exists(conn, "entry_media") and not _table_exists(conn, "moment_media"):
        op.rename_table("entry_media", "moment_media")

    if not _table_exists(conn, "moment_media"):
        return

    # Keep names aligned on PostgreSQL; SQLite can keep legacy object names safely.
    if is_sqlite:
        return

    rename_pairs = [
        ("idx_entry_media_moment_id", "idx_moment_media_moment_id"),
        ("idx_entry_media_type", "idx_moment_media_type"),
        ("idx_entry_media_status", "idx_moment_media_status"),
        ("idx_entry_media_checksum", "idx_moment_media_checksum"),
        ("idx_entry_media_external_provider", "idx_moment_media_external_provider"),
        ("ix_entry_media_id", "ix_moment_media_id"),
        ("ix_entry_media_external_provider", "ix_moment_media_external_provider"),
        ("ix_entry_media_external_asset_id", "ix_moment_media_external_asset_id"),
    ]
    for old_name, new_name in rename_pairs:
        if _index_exists(conn, old_name):
            op.execute(sa.text(f"ALTER INDEX {old_name} RENAME TO {new_name}"))

    if _constraint_exists(conn, "moment_media", "uq_entry_media_moment_checksum"):
        op.execute(
            sa.text(
                "ALTER TABLE moment_media "
                "RENAME CONSTRAINT uq_entry_media_moment_checksum "
                "TO uq_moment_media_moment_checksum"
            )
        )


def _rename_moment_media_to_entry_media(conn, is_sqlite: bool) -> None:
    if _table_exists(conn, "moment_media") and not _table_exists(conn, "entry_media"):
        op.rename_table("moment_media", "entry_media")

    if not _table_exists(conn, "entry_media"):
        return

    # Keep names aligned on PostgreSQL; SQLite can keep legacy object names safely.
    if is_sqlite:
        return

    rename_pairs = [
        ("idx_moment_media_moment_id", "idx_entry_media_moment_id"),
        ("idx_moment_media_type", "idx_entry_media_type"),
        ("idx_moment_media_status", "idx_entry_media_status"),
        ("idx_moment_media_checksum", "idx_entry_media_checksum"),
        ("idx_moment_media_external_provider", "idx_entry_media_external_provider"),
        ("ix_moment_media_id", "ix_entry_media_id"),
        ("ix_moment_media_external_provider", "ix_entry_media_external_provider"),
        ("ix_moment_media_external_asset_id", "ix_entry_media_external_asset_id"),
    ]
    for old_name, new_name in rename_pairs:
        if _index_exists(conn, old_name):
            op.execute(sa.text(f"ALTER INDEX {old_name} RENAME TO {new_name}"))

    if _constraint_exists(conn, "entry_media", "uq_moment_media_moment_checksum"):
        op.execute(
            sa.text(
                "ALTER TABLE entry_media "
                "RENAME CONSTRAINT uq_moment_media_moment_checksum "
                "TO uq_entry_media_moment_checksum"
            )
        )


def _find_fk_name_for_target(
    conn, table_name: str, constrained_column: str, referred_table: str
) -> Optional[str]:
    inspector = sa.inspect(conn)
    for fk in inspector.get_foreign_keys(table_name):
        constrained = fk.get("constrained_columns") or []
        if constrained == [constrained_column] and fk.get("referred_table") == referred_table:
            return fk.get("name")
    return None


def _migrate_import_jobs_to_moment_id(conn, is_sqlite: bool) -> None:
    """Switch import_jobs ownership from legacy entry_id to moment_id."""
    if not _column_exists(conn, "import_jobs", "moment_id"):
        op.add_column("import_jobs", sa.Column("moment_id", sa.Uuid(), nullable=True))

    if _column_exists(conn, "import_jobs", "entry_id"):
        if is_sqlite:
            op.execute(
                sa.text(
                    """
                    UPDATE import_jobs
                    SET moment_id = (
                        SELECT entry.moment_id
                        FROM entry
                        WHERE entry.id = import_jobs.entry_id
                    )
                    WHERE moment_id IS NULL
                      AND entry_id IS NOT NULL
                    """
                )
            )
        else:
            op.execute(
                sa.text(
                    """
                    UPDATE import_jobs AS ij
                    SET moment_id = e.moment_id
                    FROM entry AS e
                    WHERE ij.entry_id = e.id
                      AND ij.moment_id IS NULL
                    """
                )
            )

    if not _index_exists(conn, "ix_import_jobs_moment_id", table_name="import_jobs"):
        op.create_index("ix_import_jobs_moment_id", "import_jobs", ["moment_id"], unique=False)

    moment_fk_name = "fk_import_jobs_moment_id_moment"
    existing_moment_fk_name = _find_fk_name_for_target(
        conn, "import_jobs", "moment_id", "moment"
    )
    if (
        not _constraint_exists(conn, "import_jobs", moment_fk_name)
        and existing_moment_fk_name is None
    ):
        if is_sqlite:
            with op.batch_alter_table("import_jobs") as batch_op:
                batch_op.create_foreign_key(
                    moment_fk_name,
                    "moment",
                    ["moment_id"],
                    ["id"],
                    ondelete="CASCADE",
                )
        else:
            op.create_foreign_key(
                moment_fk_name,
                "import_jobs",
                "moment",
                ["moment_id"],
                ["id"],
                ondelete="CASCADE",
            )

    entry_fk_name = "fk_import_jobs_entry_id_entry"
    existing_entry_fk_name = _find_fk_name_for_target(
        conn, "import_jobs", "entry_id", "entry"
    )
    fk_to_drop = existing_entry_fk_name or (
        entry_fk_name if _constraint_exists(conn, "import_jobs", entry_fk_name) else None
    )
    if fk_to_drop:
        if is_sqlite:
            with op.batch_alter_table("import_jobs") as batch_op:
                batch_op.drop_constraint(fk_to_drop, type_="foreignkey")
        else:
            op.drop_constraint(fk_to_drop, "import_jobs", type_="foreignkey")

    if _index_exists(conn, "ix_import_jobs_entry_id", table_name="import_jobs"):
        op.drop_index("ix_import_jobs_entry_id", table_name="import_jobs")

    if _column_exists(conn, "import_jobs", "entry_id"):
        if is_sqlite:
            with op.batch_alter_table("import_jobs") as batch_op:
                batch_op.drop_column("entry_id")
        else:
            op.drop_column("import_jobs", "entry_id")


def _restore_import_jobs_entry_id(conn, is_sqlite: bool) -> None:
    """Restore legacy import_jobs.entry_id ownership for downgrade."""
    if not _column_exists(conn, "import_jobs", "entry_id"):
        op.add_column("import_jobs", sa.Column("entry_id", sa.Uuid(), nullable=True))

    if _column_exists(conn, "import_jobs", "moment_id"):
        if is_sqlite:
            op.execute(
                sa.text(
                    """
                    UPDATE import_jobs
                    SET entry_id = (
                        SELECT entry.id
                        FROM entry
                        WHERE entry.moment_id = import_jobs.moment_id
                    )
                    WHERE entry_id IS NULL
                      AND moment_id IS NOT NULL
                    """
                )
            )
        else:
            op.execute(
                sa.text(
                    """
                    UPDATE import_jobs AS ij
                    SET entry_id = e.id
                    FROM entry AS e
                    WHERE e.moment_id = ij.moment_id
                      AND ij.entry_id IS NULL
                    """
                )
            )

    if not _index_exists(conn, "ix_import_jobs_entry_id", table_name="import_jobs"):
        op.create_index("ix_import_jobs_entry_id", "import_jobs", ["entry_id"], unique=False)

    entry_fk_name = "fk_import_jobs_entry_id_entry"
    existing_entry_fk_name = _find_fk_name_for_target(
        conn, "import_jobs", "entry_id", "entry"
    )
    if (
        not _constraint_exists(conn, "import_jobs", entry_fk_name)
        and existing_entry_fk_name is None
    ):
        if is_sqlite:
            with op.batch_alter_table("import_jobs") as batch_op:
                batch_op.create_foreign_key(
                    entry_fk_name,
                    "entry",
                    ["entry_id"],
                    ["id"],
                    ondelete="CASCADE",
                )
        else:
            op.create_foreign_key(
                entry_fk_name,
                "import_jobs",
                "entry",
                ["entry_id"],
                ["id"],
                ondelete="CASCADE",
            )

    moment_fk_name = "fk_import_jobs_moment_id_moment"
    existing_moment_fk_name = _find_fk_name_for_target(
        conn, "import_jobs", "moment_id", "moment"
    )
    fk_to_drop = existing_moment_fk_name or (
        moment_fk_name if _constraint_exists(conn, "import_jobs", moment_fk_name) else None
    )
    if fk_to_drop:
        if is_sqlite:
            with op.batch_alter_table("import_jobs") as batch_op:
                batch_op.drop_constraint(fk_to_drop, type_="foreignkey")
        else:
            op.drop_constraint(fk_to_drop, "import_jobs", type_="foreignkey")

    if _index_exists(conn, "ix_import_jobs_moment_id", table_name="import_jobs"):
        op.drop_index("ix_import_jobs_moment_id", table_name="import_jobs")

    if _column_exists(conn, "import_jobs", "moment_id"):
        if is_sqlite:
            with op.batch_alter_table("import_jobs") as batch_op:
                batch_op.drop_column("moment_id")
        else:
            op.drop_column("import_jobs", "moment_id")


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


def _install_moment_media_count_triggers(dialect_name: str) -> None:
    """Install moment-first media_count triggers on entry_media."""
    if dialect_name == "postgresql":
        # Remove any legacy trigger/function that may reference entry_id.
        op.execute("DROP TRIGGER IF EXISTS entry_media_count_trigger ON entry_media")
        op.execute("DROP FUNCTION IF EXISTS update_entry_media_count()")

        op.execute(
            """
            CREATE OR REPLACE FUNCTION update_moment_media_count()
            RETURNS TRIGGER AS $$
            BEGIN
                IF (TG_OP = 'INSERT') THEN
                    UPDATE moment
                    SET media_count = media_count + 1
                    WHERE id = NEW.moment_id;
                    RETURN NEW;
                ELSIF (TG_OP = 'DELETE') THEN
                    UPDATE moment
                    SET media_count = GREATEST(media_count - 1, 0)
                    WHERE id = OLD.moment_id;
                    RETURN OLD;
                ELSIF (TG_OP = 'UPDATE') THEN
                    IF NEW.moment_id IS DISTINCT FROM OLD.moment_id THEN
                        UPDATE moment
                        SET media_count = GREATEST(media_count - 1, 0)
                        WHERE id = OLD.moment_id;

                        UPDATE moment
                        SET media_count = media_count + 1
                        WHERE id = NEW.moment_id;
                    END IF;
                    RETURN NEW;
                END IF;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER entry_media_count_trigger
            AFTER INSERT OR DELETE OR UPDATE OF moment_id ON entry_media
            FOR EACH ROW
            EXECUTE FUNCTION update_moment_media_count();
            """
        )
    elif dialect_name == "sqlite":
        # Remove old sqlite triggers (legacy and moment-first names) before recreating.
        op.execute("DROP TRIGGER IF EXISTS entry_media_insert_trigger")
        op.execute("DROP TRIGGER IF EXISTS entry_media_delete_trigger")
        op.execute("DROP TRIGGER IF EXISTS entry_media_count_insert_trigger")
        op.execute("DROP TRIGGER IF EXISTS entry_media_count_delete_trigger")
        op.execute("DROP TRIGGER IF EXISTS entry_media_count_update_trigger")

        op.execute(
            """
            CREATE TRIGGER entry_media_count_insert_trigger
            AFTER INSERT ON entry_media
            FOR EACH ROW
            BEGIN
                UPDATE moment
                SET media_count = media_count + 1
                WHERE id = NEW.moment_id;
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER entry_media_count_delete_trigger
            AFTER DELETE ON entry_media
            FOR EACH ROW
            BEGIN
                UPDATE moment
                SET media_count = MAX(media_count - 1, 0)
                WHERE id = OLD.moment_id;
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER entry_media_count_update_trigger
            AFTER UPDATE OF moment_id ON entry_media
            FOR EACH ROW
            -- Use a NULL-safe comparison for SQLite
            WHEN (NEW.moment_id IS NOT OLD.moment_id) OR (NEW.moment_id IS NULL AND OLD.moment_id IS NOT NULL) OR (NEW.moment_id IS NOT NULL AND OLD.moment_id IS NULL)
            BEGIN
                UPDATE moment
                SET media_count = MAX(media_count - 1, 0)
                WHERE id = OLD.moment_id;

                UPDATE moment
                SET media_count = media_count + 1
                WHERE id = NEW.moment_id;
            END;
            """
        )


def _remove_moment_media_count_triggers(dialect_name: str) -> None:
    """Remove moment-first media_count triggers on entry_media."""
    if dialect_name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS entry_media_count_trigger ON entry_media")
        op.execute("DROP FUNCTION IF EXISTS update_moment_media_count()")
    elif dialect_name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS entry_media_count_insert_trigger")
        op.execute("DROP TRIGGER IF EXISTS entry_media_count_delete_trigger")
        op.execute("DROP TRIGGER IF EXISTS entry_media_count_update_trigger")


def _install_legacy_entry_media_count_triggers(dialect_name: str) -> None:
    """Restore legacy entry-based media_count triggers for downgrade target schema."""
    if dialect_name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION update_entry_media_count()
            RETURNS TRIGGER AS $$
            BEGIN
                IF (TG_OP = 'INSERT') THEN
                    UPDATE entry
                    SET media_count = media_count + 1
                    WHERE id = NEW.entry_id;
                    RETURN NEW;
                ELSIF (TG_OP = 'DELETE') THEN
                    UPDATE entry
                    SET media_count = GREATEST(media_count - 1, 0)
                    WHERE id = OLD.entry_id;
                    RETURN OLD;
                END IF;
                RETURN NULL;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER entry_media_count_trigger
            AFTER INSERT OR DELETE ON entry_media
            FOR EACH ROW
            EXECUTE FUNCTION update_entry_media_count();
            """
        )
    elif dialect_name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER entry_media_count_insert_trigger
            AFTER INSERT ON entry_media
            FOR EACH ROW
            BEGIN
                UPDATE entry
                SET media_count = media_count + 1
                WHERE id = NEW.entry_id;
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER entry_media_count_delete_trigger
            AFTER DELETE ON entry_media
            FOR EACH ROW
            BEGIN
                UPDATE entry
                SET media_count = MAX(media_count - 1, 0)
                WHERE id = OLD.entry_id;
            END;
            """
        )


def _rebuild_mood_table_sqlite_without_unique_name() -> None:
    op.execute("PRAGMA foreign_keys=OFF")
    try:
        op.execute(
            """
            CREATE TABLE "mood_new" (
            \tid CHAR(32) NOT NULL,
            \tcreated_at DATETIME NOT NULL,
            \tupdated_at DATETIME NOT NULL,
            \tname VARCHAR(100) NOT NULL,
            \ticon VARCHAR(50),
            \tcategory VARCHAR(50) NOT NULL,
            \tuser_id CHAR(32),
            \t"key" VARCHAR(50),
            \tscore INTEGER DEFAULT '3' NOT NULL,
            \tposition INTEGER DEFAULT '0' NOT NULL,
            \tis_active BOOLEAN DEFAULT true NOT NULL,
            \tPRIMARY KEY (id),
            \tCONSTRAINT check_mood_name_not_empty CHECK (length(name) > 0),
            \tCONSTRAINT check_mood_category CHECK (category IN ('positive', 'negative', 'neutral')),
            \tCONSTRAINT fk_mood_user_id FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE,
            \tCONSTRAINT check_mood_score_range CHECK (score >= 1 AND score <= 5)
            )
            """
        )
        op.execute(
            """
            INSERT INTO mood_new (
                id,
                created_at,
                updated_at,
                name,
                icon,
                category,
                user_id,
                "key",
                score,
                position,
                is_active
            )
            SELECT
                id,
                created_at,
                updated_at,
                name,
                icon,
                category,
                user_id,
                "key",
                score,
                position,
                is_active
            FROM mood
            """
        )
        op.execute("DROP TABLE mood")
        op.execute("ALTER TABLE mood_new RENAME TO mood")
        op.execute("CREATE INDEX IF NOT EXISTS ix_mood_id ON mood (id)")
    finally:
        op.execute("PRAGMA foreign_keys=ON")


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
        try:
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
        finally:
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
        sa.Column("primary_mood_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_id", sa.Uuid(), nullable=True),
        sa.Column("logged_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("logged_date_tz", sa.Date(), nullable=True),
        sa.Column("logged_timezone", sa.String(length=100), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("location_json", json_type, nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("weather_json", json_type, nullable=True),
        sa.Column("weather_summary", sa.String(length=500), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("media_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["primary_mood_id"], ["mood.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompt.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_moment_user_logged_at_utc",
        "moment",
        ["user_id", "logged_at_utc", "id"],
        unique=False,
    )
    op.create_index(
        "idx_moment_user_logged_date_tz",
        "moment",
        ["user_id", "logged_date_tz"],
        unique=False,
    )
    op.create_index(
        "idx_moment_latitude_longitude",
        "moment",
        ["latitude", "longitude"],
        unique=False,
    )
    op.create_index(
        "idx_moment_prompt_id",
        "moment",
        ["prompt_id"],
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

    # Add moment_id to entry (nullable initially for data migration)
    if is_sqlite:
        with op.batch_alter_table("entry") as batch_op:
            batch_op.add_column(sa.Column("moment_id", sa.Uuid(), nullable=True))
    else:
        op.add_column("entry", sa.Column("moment_id", sa.Uuid(), nullable=True))

    # Add moment_id to entry_media (nullable initially for data migration)
    if is_sqlite:
        with op.batch_alter_table("entry_media") as batch_op:
            batch_op.add_column(sa.Column("moment_id", sa.Uuid(), nullable=True))
            batch_op.create_index(
                "idx_entry_media_moment_id", ["moment_id"], unique=False
            )
    else:
        op.add_column("entry_media", sa.Column("moment_id", sa.Uuid(), nullable=True))
        op.create_index(
            "idx_entry_media_moment_id", "entry_media", ["moment_id"], unique=False
        )

    # Create moment_tag_link table
    op.create_table(
        "moment_tag_link",
        sa.Column("moment_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["moment_id"], ["moment.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("moment_id", "tag_id"),
    )
    op.create_index(
        "idx_moment_tag_link_tag_id", "moment_tag_link", ["tag_id"], unique=False
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
        sa.column("latitude", sa.Float()),
        sa.column("longitude", sa.Float()),
        sa.column("weather_json", json_type),
        sa.column("weather_summary", sa.String()),
        sa.column("is_pinned", sa.Boolean()),
        sa.column("prompt_id", sa.Uuid()),
        sa.column("media_count", sa.Integer()),
        sa.column("moment_id", sa.Uuid()),
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
    moment = sa.table(
        "moment",
        sa.column("id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
        sa.column("user_id", sa.Uuid()),
        sa.column("primary_mood_id", sa.Uuid()),
        sa.column("prompt_id", sa.Uuid()),
        sa.column("logged_at_utc", sa.DateTime(timezone=True)),
        sa.column("logged_date_tz", sa.Date()),
        sa.column("logged_timezone", sa.String()),
        sa.column("note", sa.String()),
        sa.column("location_json", json_type),
        sa.column("latitude", sa.Float()),
        sa.column("longitude", sa.Float()),
        sa.column("weather_json", json_type),
        sa.column("weather_summary", sa.String()),
        sa.column("is_pinned", sa.Boolean()),
        sa.column("media_count", sa.Integer()),
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
    entry_to_moment: Dict[UUIDValue, UUIDValue] = {}

    # Step A: Create moments from entries, set entry.moment_id
    print("  - [Migrating] Step A: Creating moments from entries...")
    entries = conn.execute(sa.select(entry)).fetchall()
    for row in entries:
        moment_id = _new_uuid(is_sqlite=is_sqlite)
        entry_id = _as_uuid(row.id, is_sqlite=is_sqlite)
        entry_to_moment[entry_id] = moment_id
        conn.execute(
            moment.insert().values(
                id=moment_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
                user_id=row.user_id,
                primary_mood_id=None,
                prompt_id=_as_uuid(row.prompt_id, is_sqlite=is_sqlite),
                logged_at_utc=row.entry_datetime_utc,
                logged_date_tz=row.entry_date,
                logged_timezone=row.entry_timezone or "UTC",
                note=None,
                location_json=row.location_json,
                latitude=row.latitude,
                longitude=row.longitude,
                weather_json=row.weather_json,
                weather_summary=row.weather_summary,
                is_pinned=row.is_pinned if row.is_pinned is not None else False,
                media_count=row.media_count if row.media_count is not None else 0,
            )
        )
        # Set entry.moment_id
        conn.execute(
            entry.update()
            .where(entry.c.id == entry_id)
            .values(moment_id=moment_id)
        )

    # Step B: Migrate entry_tag_link → moment_tag_link (set-based)
    print("  - [Migrating] Step B: Migrating entry tags to moment tags...")
    if is_sqlite:
        conn.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO moment_tag_link (moment_id, tag_id, created_at, updated_at)
                SELECT e.moment_id, etl.tag_id, etl.created_at, etl.updated_at
                FROM entry_tag_link AS etl
                JOIN entry AS e ON e.id = etl.entry_id
                WHERE e.moment_id IS NOT NULL
                """
            )
        )
    else:
        conn.execute(
            sa.text(
                """
                INSERT INTO moment_tag_link (moment_id, tag_id, created_at, updated_at)
                SELECT e.moment_id, etl.tag_id, etl.created_at, etl.updated_at
                FROM entry_tag_link AS etl
                JOIN entry AS e ON e.id = etl.entry_id
                WHERE e.moment_id IS NOT NULL
                ON CONFLICT (moment_id, tag_id) DO NOTHING
                """
            )
        )

    # Step C: Migrate entry_media.entry_id → entry_media.moment_id (set-based)
    print("  - [Migrating] Step C: Migrating entry media to moment media...")
    if is_sqlite:
        conn.execute(
            sa.text(
                """
                UPDATE entry_media
                SET moment_id = (
                    SELECT e.moment_id
                    FROM entry AS e
                    WHERE e.id = entry_media.entry_id
                )
                WHERE moment_id IS NULL
                  AND entry_id IS NOT NULL
                """
            )
        )
    else:
        conn.execute(
            sa.text(
                """
                UPDATE entry_media AS em
                SET moment_id = e.moment_id
                FROM entry AS e
                WHERE em.entry_id = e.id
                  AND em.moment_id IS NULL
                """
            )
        )

    # Step D: Migrate mood_logs → moments
    print("  - [Migrating] Step D: Migrating mood logs to moments...")
    mood_log_links: Dict[UUIDValue, List[UUIDValue]] = {}
    for link in conn.execute(sa.select(mood_log_activity_link)).fetchall():
        mood_log_id = _as_uuid(link.mood_log_id, is_sqlite=is_sqlite)
        activity_id = _as_uuid(link.activity_id, is_sqlite=is_sqlite)
        mood_log_links.setdefault(mood_log_id, []).append(activity_id)

    mood_logs = conn.execute(sa.select(mood_log)).fetchall()
    inserted_mood_only: set[Tuple[UUIDValue, UUIDValue]] = set()
    inserted_mood_activity: set[Tuple[UUIDValue, UUIDValue, UUIDValue]] = set()
    for row in mood_logs:
        entry_id = _as_uuid(row.entry_id, is_sqlite=is_sqlite)
        mood_id = _as_uuid(row.mood_id, is_sqlite=is_sqlite)
        activities = mood_log_links.get(_as_uuid(row.id, is_sqlite=is_sqlite), [])

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
            moment_id = _new_uuid(is_sqlite=is_sqlite)
            conn.execute(
                moment.insert().values(
                    id=moment_id,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    user_id=row.user_id,
                    primary_mood_id=mood_id,
                    prompt_id=None,
                    logged_at_utc=row.logged_datetime_utc,
                    logged_date_tz=row.logged_date,
                    logged_timezone=row.logged_timezone or "UTC",
                    note=row.note,
                    location_json=None,
                    latitude=None,
                    longitude=None,
                    weather_json=None,
                    weather_summary=None,
                    is_pinned=False,
                    media_count=0,
                )
            )

        if activities:
            for activity_id in activities:
                mood_activity_key = (moment_id, mood_id, activity_id)
                if mood_activity_key in inserted_mood_activity:
                    continue
                conn.execute(
                    moment_mood_activity.insert().values(
                        id=_new_uuid(is_sqlite=is_sqlite),
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
                        id=_new_uuid(is_sqlite=is_sqlite),
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
        entry_id = _as_uuid(row.entry_id, is_sqlite=is_sqlite)
        activity_id = _as_uuid(row.activity_id, is_sqlite=is_sqlite)
        moment_id = entry_to_moment.get(entry_id)
        if moment_id is None:
            continue
        conn.execute(
            moment_mood_activity.insert().values(
                id=_new_uuid(is_sqlite=is_sqlite),
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
                moment_id=moment_id,
                mood_id=None,
                activity_id=activity_id,
            )
        )

    activity_logs = conn.execute(sa.select(activity_log)).fetchall()
    for row in activity_logs:
        moment_id = _new_uuid(is_sqlite=is_sqlite)
        conn.execute(
            moment.insert().values(
                id=moment_id,
                created_at=row.created_at,
                updated_at=row.updated_at,
                user_id=row.user_id,
                primary_mood_id=None,
                prompt_id=None,
                logged_at_utc=row.logged_datetime_utc,
                logged_date_tz=row.logged_date,
                logged_timezone=row.logged_timezone or "UTC",
                note=row.note,
                location_json=None,
                latitude=None,
                longitude=None,
                weather_json=None,
                weather_summary=None,
                is_pinned=False,
                media_count=0,
            )
        )
        conn.execute(
            moment_mood_activity.insert().values(
                id=_new_uuid(is_sqlite=is_sqlite),
                created_at=row.created_at,
                updated_at=row.updated_at,
                moment_id=moment_id,
                mood_id=None,
                activity_id=row.activity_id,
            )
        )

    # Step E: Backfill media_count on moment
    print("  - [Migrating] Step E: Backfilling media counts on moments...")
    conn.execute(
        sa.text(
            "UPDATE moment SET media_count = "
            "(SELECT count(*) FROM entry_media WHERE entry_media.moment_id = moment.id)"
        )
    )

    # Step F: Make entry.moment_id NOT NULL + add constraints
    print("  - [Migrating] Step F: Enforcing Moment ID on Entry...")
    if is_sqlite:
        with op.batch_alter_table("entry") as batch_op:
            batch_op.alter_column("moment_id", existing_type=sa.Uuid(), nullable=False)
            batch_op.create_index("idx_entry_moment_id", ["moment_id"], unique=False)
            batch_op.create_unique_constraint("uq_entry_moment_id", ["moment_id"])
            batch_op.create_foreign_key(
                "fk_entry_moment_id_moment",
                "moment",
                ["moment_id"],
                ["id"],
                ondelete="CASCADE",
            )
    else:
        op.alter_column("entry", "moment_id", existing_type=sa.Uuid(), nullable=False)
        op.create_index("idx_entry_moment_id", "entry", ["moment_id"], unique=False)
        op.create_unique_constraint("uq_entry_moment_id", "entry", ["moment_id"])
        op.create_foreign_key(
            "fk_entry_moment_id_moment",
            "entry",
            "moment",
            ["moment_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # Step G: Migrate import_jobs to moment ownership.
    print("  - [Migrating] Step G: Migrating import jobs...")
    _migrate_import_jobs_to_moment_id(connection, is_sqlite)

    # Step H: Finalize entry_media — drop entry_id, make moment_id NOT NULL
    print("  - [Migrating] Step H: Finalizing entry media schema...")
    if is_sqlite:
        conn = op.get_bind()
        has_fk = _constraint_exists(conn, "entry_media", "fk_entry_media_entry_id_entry")
        has_uq = _constraint_exists(conn, "entry_media", "uq_entry_media_entry_checksum")

        with op.batch_alter_table("entry_media") as batch_op:
            batch_op.alter_column("moment_id", existing_type=sa.Uuid(), nullable=False)
            batch_op.create_foreign_key(
                "fk_entry_media_moment_id_moment",
                "moment",
                ["moment_id"],
                ["id"],
                ondelete="CASCADE",
            )
            batch_op.create_unique_constraint(
                "uq_entry_media_moment_checksum",
                ["moment_id", "checksum"],
            )
            if has_fk:
                batch_op.drop_constraint("fk_entry_media_entry_id_entry", type_="foreignkey")

            # Drop ALL indexes related to entry_id
            for idx_name in ["idx_entry_media_entry_id", "ix_entry_media_entry_id"]:
                if _index_exists(conn, idx_name, table_name="entry_media"):
                    batch_op.drop_index(idx_name)

            if has_uq:
                batch_op.drop_constraint("uq_entry_media_entry_checksum", type_="unique")
            batch_op.drop_column("entry_id")
    else:
        op.alter_column("entry_media", "moment_id", existing_type=sa.Uuid(), nullable=False)
        op.create_foreign_key(
            "fk_entry_media_moment_id_moment",
            "entry_media",
            "moment",
            ["moment_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_unique_constraint(
            "uq_entry_media_moment_checksum",
            "entry_media",
            ["moment_id", "checksum"],
        )
        # Drop entry_id column and related constraints
        conn = op.get_bind()

        # Drop constraints only if they exist
        if _constraint_exists(conn, "entry_media", "fk_entry_media_entry_id_entry"):
            op.drop_constraint("fk_entry_media_entry_id_entry", "entry_media", type_="foreignkey")

        if _index_exists(conn, "idx_entry_media_entry_id"):
            op.drop_index("idx_entry_media_entry_id", table_name="entry_media")

        if _constraint_exists(conn, "entry_media", "uq_entry_media_entry_checksum"):
            op.drop_constraint("uq_entry_media_entry_checksum", "entry_media", type_="unique")

        if _constraint_exists(conn, "entry_media", "check_media_entry_or_moment"):
            op.drop_constraint("check_media_entry_or_moment", "entry_media", type_="check")

        op.drop_column("entry_media", "entry_id")

    # Step I: Drop entry columns that moved to moment
    print("  - [Migrating] Step I: Dropping legacy entry columns...")
    entry_columns_to_drop = [
        "entry_date", "entry_datetime_utc", "entry_timezone",
        "location_json", "latitude", "longitude",
        "weather_json", "weather_summary",
        "is_pinned", "prompt_id", "media_count",
    ]
    if is_sqlite:
        conn = op.get_bind()
        with op.batch_alter_table("entry") as batch_op:
            # Drop ALL indexes that reference removed columns
            # Based on schema discovery: entry_date, entry_datetime_utc, prompt_id, media_count, etc.
            for idx_name in [
                "idx_entries_journal_date",
                "idx_entries_prompt_id",
                "idx_entry_user_datetime",
                "idx_entry_latitude_longitude",
                "ix_entry_entry_date",
                "ix_entry_entry_datetime_utc",
                "ix_entry_media_count",
                "ix_entry_prompt_id",
            ]:
                if _index_exists(conn, idx_name, table_name="entry"):
                    batch_op.drop_index(idx_name)

            # Drop FK for prompt_id if it exists
            if _constraint_exists(conn, "entry", "fk_entry_prompt_id_prompt"):
                batch_op.drop_constraint("fk_entry_prompt_id_prompt", type_="foreignkey")

            for col_name in entry_columns_to_drop:
                batch_op.drop_column(col_name)
    else:
        conn = op.get_bind()

        # Drop indexes only if they exist
        for idx_name in [
            "idx_entries_journal_date", "idx_entries_prompt_id",
            "idx_entry_user_datetime", "idx_entry_latitude_longitude",
        ]:
            if _index_exists(conn, idx_name):
                op.drop_index(idx_name, table_name="entry")

        # Drop FK for prompt_id only if it exists
        if _constraint_exists(conn, "entry", "fk_entry_prompt_id_prompt"):
            op.drop_constraint("fk_entry_prompt_id_prompt", "entry", type_="foreignkey")

        for col_name in entry_columns_to_drop:
            op.drop_column("entry", col_name)

    # Step J: Install moment-first media_count triggers on entry_media.
    print("  - [Migrating] Step J: Installing moment media count triggers...")
    _install_moment_media_count_triggers(connection.dialect.name)

    # Step K: Drop entry_tag_link table
    print("  - [Migrating] Step K: Dropping legacy tables...")
    op.drop_index("idx_entry_tag_link_tag_id", table_name="entry_tag_link")
    op.drop_table("entry_tag_link")

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
        _rebuild_mood_table_sqlite_without_unique_name()

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
              AND (key IS NULL OR key NOT IN ('awesome', 'good', 'meh', 'bad', 'awful'))
            """
        )
        op.execute(
            """
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
            SET is_hidden = EXCLUDED.is_hidden
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
        conn = op.get_bind()
        has_ck = _constraint_exists(conn, "goal", "check_goal_target_days_per_week")
        with op.batch_alter_table("goal") as batch_op:
            if has_ck:
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
        conn = op.get_bind()
        has_uq = _constraint_exists(conn, "goal_log", "uq_goal_log_goal_date")
        with op.batch_alter_table("goal_log") as batch_op:
            if has_uq:
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
    score_to_group_id: dict[int, UUIDValue] = {}
    for score, name, position in TIER_GROUPS:
        group_id = _new_uuid(is_sqlite=is_sqlite)
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
                "id": _new_uuid(is_sqlite=is_sqlite),
                "created_at": now,
                "updated_at": now,
                "mood_group_id": group_id,
                "mood_id": _as_uuid(mood_id, is_sqlite=is_sqlite),
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

    # --- harden moment-first constraints (folded from 1c7f9e2a4b6d) ---
    _backfill_moment_logged_date_tz(connection)

    # Safety net: ensure no NULL values remain before enforcing NOT NULL.
    remaining_rows = connection.execute(
        sa.text(
            """
            SELECT id, logged_at_utc, logged_timezone
            FROM moment
            WHERE logged_date_tz IS NULL
            """
        )
    ).fetchall()
    for row in remaining_rows:
        fallback_date = _derive_local_date(row.logged_at_utc, row.logged_timezone)
        if fallback_date is None:
            fallback_date = datetime.now(timezone.utc).date()
        connection.execute(
            sa.text("UPDATE moment SET logged_date_tz = :logged_date_tz WHERE id = :moment_id"),
            {"logged_date_tz": fallback_date, "moment_id": row.id},
        )

    null_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM moment WHERE logged_date_tz IS NULL")
    ).scalar_one()
    if null_count:
        raise RuntimeError(
            f"Cannot enforce NOT NULL on moment.logged_date_tz: {null_count} rows still NULL after backfill"
        )

    reinstall_moment_media_triggers = False
    if is_sqlite:
        # SQLite batch_alter recreates the table under _alembic_tmp_*.
        # Drop media-count triggers that reference "moment" to avoid
        # trigger parse failures while the table is temporarily renamed.
        _remove_moment_media_count_triggers(connection.dialect.name)
        reinstall_moment_media_triggers = True
        with op.batch_alter_table("moment") as batch_op:
            batch_op.alter_column("logged_date_tz", existing_type=sa.Date(), nullable=False)
    else:
        op.alter_column("moment", "logged_date_tz", existing_type=sa.Date(), nullable=False)

    if reinstall_moment_media_triggers:
        _install_moment_media_count_triggers(connection.dialect.name)

    if not _index_exists(connection, "idx_moment_note", table_name="moment"):
        op.create_index("idx_moment_note", "moment", ["note"], unique=False)

    if not _constraint_exists(connection, "tag", "check_tag_name_lowercase"):
        # Normalize historical rows before enforcing lowercase check constraint.
        connection.execute(sa.text("UPDATE tag SET name = lower(name) WHERE name IS NOT NULL"))
        if is_sqlite:
            with op.batch_alter_table("tag") as batch_op:
                batch_op.create_check_constraint(
                    "check_tag_name_lowercase",
                    "name = lower(name)",
                )
        else:
            op.create_check_constraint(
                "check_tag_name_lowercase",
                "tag",
                "name = lower(name)",
            )

    # --- rename entry_media -> moment_media (folded from 2e9b1a4c6d7f) ---
    _rename_entry_media_to_moment_media(connection, is_sqlite)

    # --- add display_path on moment media (folded from 06bc1e654274) ---
    if _table_exists(connection, "moment_media") and not _column_exists(
        connection, "moment_media", "display_path"
    ):
        op.add_column(
            "moment_media",
            sa.Column("display_path", sa.String(length=500), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    # Reverse display_path addition before table rename reversal.
    if _table_exists(conn, "moment_media") and _column_exists(
        conn, "moment_media", "display_path"
    ):
        op.drop_column("moment_media", "display_path")

    # Reverse folded table rename before any legacy downgrade logic touches media table names.
    _rename_moment_media_to_entry_media(conn, is_sqlite)

    if _constraint_exists(conn, "tag", "check_tag_name_lowercase"):
        if is_sqlite:
            with op.batch_alter_table("tag") as batch_op:
                batch_op.drop_constraint("check_tag_name_lowercase", type_="check")
        else:
            op.drop_constraint("check_tag_name_lowercase", "tag", type_="check")

    # --- r8s9t0u1v2w3_add_goal_categories.py ---
    op.drop_index("idx_goal_user_category_position", table_name="goal")
    if is_sqlite:
        conn = op.get_bind()
        has_fk = _constraint_exists(conn, "goal", "fk_goal_category_id_goal_category")
        has_idx = _index_exists(conn, "ix_goal_category_id", table_name="goal")
        with op.batch_alter_table("goal") as batch_op:
            if has_fk:
                batch_op.drop_constraint("fk_goal_category_id_goal_category", type_="foreignkey")
            if has_idx:
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
        conn = op.get_bind()
        has_uq = _constraint_exists(conn, "goal_log", "uq_goal_log_goal_period")
        with op.batch_alter_table("goal_log") as batch_op:
            if has_uq:
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
        conn = op.get_bind()
        has_ck = _constraint_exists(conn, "goal", "check_goal_target_count")
        with op.batch_alter_table("goal") as batch_op:
            if has_ck:
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
        conn = op.get_bind()
        has_ck = _constraint_exists(conn, "mood", "check_mood_score_range")
        has_fk = _constraint_exists(conn, "mood", "fk_mood_user_id")
        with op.batch_alter_table("mood") as batch_op:
            if has_ck:
                batch_op.drop_constraint("check_mood_score_range", type_="check")
            if has_fk:
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
        conn = op.get_bind()
        has_ck = _constraint_exists(conn, "user_settings", "check_start_of_week_day_valid")
        with op.batch_alter_table("user_settings") as batch_op:
            if has_ck:
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
    json_type = postgresql.JSONB(astext_type=sa.Text()).with_variant(
        sa.JSON(), "sqlite"
    )

    # Recreate entry_tag_link
    op.create_table(
        "entry_tag_link",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("tag_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entry_id"], ["entry.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("entry_id", "tag_id"),
    )
    op.create_index(
        "idx_entry_tag_link_tag_id", "entry_tag_link", ["tag_id"], unique=False
    )

    # Add back entry columns that moved to moment
    entry_columns_to_restore = [
        sa.Column("entry_date", sa.Date(), nullable=True),
        sa.Column("entry_datetime_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entry_timezone", sa.String(length=100), nullable=True),
        sa.Column("location_json", json_type, nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("weather_json", json_type, nullable=True),
        sa.Column("weather_summary", sa.String(length=500), nullable=True),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("prompt_id", sa.Uuid(), nullable=True),
        sa.Column("media_count", sa.Integer(), nullable=False, server_default="0"),
    ]
    if is_sqlite:
        with op.batch_alter_table("entry") as batch_op:
            for col in entry_columns_to_restore:
                batch_op.add_column(col)
    else:
        for col in entry_columns_to_restore:
            op.add_column("entry", col)

    # Restore data from moment to entry
    op.execute("""
        UPDATE entry
        SET
            entry_date = (SELECT logged_date_tz FROM moment WHERE moment.id = entry.moment_id),
            entry_datetime_utc = (SELECT logged_at_utc FROM moment WHERE moment.id = entry.moment_id),
            entry_timezone = (SELECT logged_timezone FROM moment WHERE moment.id = entry.moment_id),
            latitude = (SELECT latitude FROM moment WHERE moment.id = entry.moment_id),
            longitude = (SELECT longitude FROM moment WHERE moment.id = entry.moment_id),
            weather_summary = (SELECT weather_summary FROM moment WHERE moment.id = entry.moment_id),
            is_pinned = (SELECT is_pinned FROM moment WHERE moment.id = entry.moment_id),
            location_json = (SELECT location_json FROM moment WHERE moment.id = entry.moment_id),
            weather_json = (SELECT weather_json FROM moment WHERE moment.id = entry.moment_id),
            prompt_id = (SELECT prompt_id FROM moment WHERE moment.id = entry.moment_id),
            media_count = (SELECT media_count FROM moment WHERE moment.id = entry.moment_id)
        WHERE moment_id IS NOT NULL
    """)

    # Restore legacy indexes for entry
    if is_sqlite:
        with op.batch_alter_table("entry") as batch_op:
            batch_op.create_index("idx_entries_journal_date", ["journal_id", "entry_date"])
            batch_op.create_index("idx_entries_prompt_id", ["prompt_id"])
            batch_op.create_index("idx_entry_user_datetime", ["user_id", "entry_datetime_utc"])
            batch_op.create_index("idx_entry_latitude_longitude", ["latitude", "longitude"])
    else:
        op.create_index("idx_entries_journal_date", "entry", ["journal_id", "entry_date"])
        op.create_index("idx_entries_prompt_id", "entry", ["prompt_id"])
        op.create_index("idx_entry_user_datetime", "entry", ["user_id", "entry_datetime_utc"])
        op.create_index("idx_entry_latitude_longitude", "entry", ["latitude", "longitude"])

    # Backfill data from moment_tag_link to entry_tag_link (conflict-safe)
    if is_sqlite:
        op.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO entry_tag_link (entry_id, tag_id, created_at, updated_at)
                SELECT e.id, mtl.tag_id, mtl.created_at, mtl.updated_at
                FROM entry e
                JOIN moment_tag_link mtl ON e.moment_id = mtl.moment_id
                WHERE e.moment_id IS NOT NULL
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                INSERT INTO entry_tag_link (entry_id, tag_id, created_at, updated_at)
                SELECT e.id, mtl.tag_id, mtl.created_at, mtl.updated_at
                FROM entry e
                JOIN moment_tag_link mtl ON e.moment_id = mtl.moment_id
                WHERE e.moment_id IS NOT NULL
                ON CONFLICT DO NOTHING
                """
            )
        )

    # Restore entry_media.entry_id, backfill from entry.moment_id, drop moment_id
    if is_sqlite:
        conn = op.get_bind()
        has_uq = _constraint_exists(conn, "entry_media", "uq_entry_media_moment_checksum")
        has_fk = _constraint_exists(conn, "entry_media", "fk_entry_media_moment_id_moment")
        has_idx = _index_exists(conn, "idx_entry_media_moment_id", table_name="entry_media")
        has_legacy_idx = _index_exists(conn, "idx_entry_media_entry_id", table_name="entry_media")
        has_legacy_uq = _constraint_exists(conn, "entry_media", "uq_entry_media_entry_checksum")

        with op.batch_alter_table("entry_media") as batch_op:
            batch_op.add_column(sa.Column("entry_id", sa.Uuid(), nullable=True))

        op.execute(
            sa.text(
                """
                UPDATE entry_media
                SET entry_id = (
                    SELECT e.id
                    FROM entry AS e
                    WHERE e.moment_id = entry_media.moment_id
                )
                WHERE entry_id IS NULL
                  AND moment_id IS NOT NULL
                """
            )
        )

        with op.batch_alter_table("entry_media") as batch_op:
            if has_uq:
                batch_op.drop_constraint("uq_entry_media_moment_checksum", type_="unique")
            if has_fk:
                batch_op.drop_constraint("fk_entry_media_moment_id_moment", type_="foreignkey")
            if has_idx:
                batch_op.drop_index("idx_entry_media_moment_id")
            batch_op.create_foreign_key(
                "fk_entry_media_entry_id_entry",
                "entry",
                ["entry_id"],
                ["id"],
                ondelete="CASCADE",
            )
            if not has_legacy_idx:
                batch_op.create_index("idx_entry_media_entry_id", ["entry_id"], unique=False)
            if not has_legacy_uq:
                batch_op.create_unique_constraint(
                    "uq_entry_media_entry_checksum",
                    ["entry_id", "checksum"],
                )
            batch_op.drop_column("moment_id")
            batch_op.alter_column("entry_id", existing_type=sa.Uuid(), nullable=False)
    else:
        op.add_column("entry_media", sa.Column("entry_id", sa.Uuid(), nullable=True))

        op.execute(
            sa.text(
                """
                UPDATE entry_media AS em
                SET entry_id = e.id
                FROM entry AS e
                WHERE e.moment_id = em.moment_id
                  AND em.entry_id IS NULL
                """
            )
        )
        # Use IF EXISTS for PostgreSQL
        op.execute("ALTER TABLE entry_media DROP CONSTRAINT IF EXISTS uq_entry_media_moment_checksum")
        op.execute("ALTER TABLE entry_media DROP CONSTRAINT IF EXISTS fk_entry_media_moment_id_moment")
        op.execute("DROP INDEX IF EXISTS idx_entry_media_moment_id")

        op.create_foreign_key(
            "fk_entry_media_entry_id_entry",
            "entry_media",
            "entry",
            ["entry_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index("idx_entry_media_entry_id", "entry_media", ["entry_id"], unique=False)
        op.create_unique_constraint(
            "uq_entry_media_entry_checksum",
            "entry_media",
            ["entry_id", "checksum"],
        )
        op.drop_column("entry_media", "moment_id")
        op.alter_column("entry_media", "entry_id", existing_type=sa.Uuid(), nullable=False)

    # Restore legacy import_jobs.entry_id ownership while entry.moment_id still exists.
    _restore_import_jobs_entry_id(conn, is_sqlite)

    # Drop entry.moment_id
    if is_sqlite:
        conn = op.get_bind()
        has_uq = _constraint_exists(conn, "entry", "uq_entry_moment_id")
        has_fk = _constraint_exists(conn, "entry", "fk_entry_moment_id_moment")
        has_idx = _index_exists(conn, "idx_entry_moment_id", table_name="entry")
        with op.batch_alter_table("entry") as batch_op:
            if has_uq:
                batch_op.drop_constraint("uq_entry_moment_id", type_="unique")
            if has_fk:
                batch_op.drop_constraint("fk_entry_moment_id_moment", type_="foreignkey")
            if has_idx:
                batch_op.drop_index("idx_entry_moment_id")
            batch_op.drop_column("moment_id")
    else:
        # Use IF EXISTS for PostgreSQL
        op.execute("ALTER TABLE entry DROP CONSTRAINT IF EXISTS uq_entry_moment_id")
        op.execute("ALTER TABLE entry DROP CONSTRAINT IF EXISTS fk_entry_moment_id_moment")
        op.execute("DROP INDEX IF EXISTS idx_entry_moment_id")
        op.execute("ALTER TABLE entry DROP COLUMN IF EXISTS moment_id")

    # Remove moment-first entry_media triggers and restore legacy entry-based triggers.
    _remove_moment_media_count_triggers(conn.dialect.name)
    _install_legacy_entry_media_count_triggers(conn.dialect.name)

    # Drop moment_tag_link
    op.drop_index("idx_moment_tag_link_tag_id", table_name="moment_tag_link")
    op.drop_table("moment_tag_link")

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

    op.drop_index("idx_moment_prompt_id", table_name="moment")
    op.drop_index("idx_moment_latitude_longitude", table_name="moment")
    op.drop_index("idx_moment_user_logged_date_tz", table_name="moment")
    op.drop_index("idx_moment_user_logged_at_utc", table_name="moment")
    op.drop_index(op.f("ix_moment_id"), table_name="moment")
    op.drop_table("moment")

    # --- abc2f3a4b5c6_add_activity_groups.py ---
    # ### commands auto generated by Alembic - adjusted manually ###
    if is_sqlite:
        conn = op.get_bind()
        has_fk = _constraint_exists(conn, "activity", "fk_activity_group_id")
        has_idx = _index_exists(conn, "idx_activity_group_id", table_name="activity")
        with op.batch_alter_table("activity") as batch_op:
            if has_fk:
                batch_op.drop_constraint("fk_activity_group_id", type_="foreignkey")
            if has_idx:
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
