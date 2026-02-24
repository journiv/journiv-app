"""normalize sqlite mood uuid formats after system-mood removal

Revision ID: e5f6a7b8c9d0
Revises: d2e4f6a8b0c1
Create Date: 2026-02-24 07:20:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d0"
down_revision = "d2e4f6a8b0c1"
branch_labels = None
depends_on = None

_STARTER_MOOD_STABLE_KEYS = [
    "mood_awesome",
    "mood_good",
    "mood_meh",
    "mood_bad",
    "mood_awful",
]


def _is_sqlite(conn) -> bool:
    return conn.dialect.name == "sqlite"


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    rows = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pragma_table_info(:table_name)
            WHERE name = :column_name
            LIMIT 1
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).fetchone()
    return rows is not None


def _normalize_uuid_column(conn, table_name: str, column_name: str) -> None:
    if not _column_exists(conn, table_name, column_name):
        return
    conn.execute(
        sa.text(
            f"""
            UPDATE {table_name}
            SET {column_name} = lower(replace({column_name}, '-', ''))
            WHERE {column_name} IS NOT NULL
              AND {column_name} != lower(replace({column_name}, '-', ''))
            """
        )
    )


def _ensure_core_group_links(conn) -> None:
    conn.execute(
        sa.text(
            """
            INSERT INTO mood_group_link (
                id,
                created_at,
                updated_at,
                mood_group_id,
                mood_id,
                position
            )
            SELECT
                lower(hex(randomblob(16))),
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                mg.id,
                m.id,
                m.position
            FROM mood_group AS mg
            JOIN mood AS m
              ON m.user_id = mg.user_id
            WHERE mg.stable_key = :core_group_stable_key
              AND m.stable_key IN :starter_mood_stable_keys
              AND COALESCE(m.is_active, 1) = 1
              AND NOT EXISTS (
                  SELECT 1
                  FROM mood_group_link AS l
                  WHERE l.mood_group_id = mg.id
                    AND l.mood_id = m.id
              )
            """
        ).bindparams(
            sa.bindparam("starter_mood_stable_keys", expanding=True),
        ),
        {
            "core_group_stable_key": "moodgroup_core_moods",
            "starter_mood_stable_keys": _STARTER_MOOD_STABLE_KEYS,
        },
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not _is_sqlite(conn):
        return

    with op.get_context().autocommit_block():
        conn.execute(sa.text("PRAGMA foreign_keys=OFF"))
    try:
        _normalize_uuid_column(conn, "mood", "id")
        _normalize_uuid_column(conn, "mood", "user_id")
        _normalize_uuid_column(conn, "mood_group", "id")
        _normalize_uuid_column(conn, "mood_group", "user_id")
        _normalize_uuid_column(conn, "mood_group_link", "id")
        _normalize_uuid_column(conn, "mood_group_link", "mood_group_id")
        _normalize_uuid_column(conn, "mood_group_link", "mood_id")
        _normalize_uuid_column(conn, "user_mood_preference", "mood_id")
        _normalize_uuid_column(conn, "user_mood_group_preference", "mood_group_id")
        _normalize_uuid_column(conn, "moment", "primary_mood_id")
        _normalize_uuid_column(conn, "moment_mood_activity", "mood_id")
        _ensure_core_group_links(conn)
    finally:
        with op.get_context().autocommit_block():
            conn.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    # Irreversible data normalization for SQLite UUID text representation.
    pass
