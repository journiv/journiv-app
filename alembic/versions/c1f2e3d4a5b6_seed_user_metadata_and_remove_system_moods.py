"""seed user starter metadata and remove legacy system moods

Revision ID: c1f2e3d4a5b6
Revises: b8c9d0e1f2a3
Create Date: 2026-02-21 11:00:00.000000

"""

from __future__ import annotations

import re
import uuid
from typing import Dict, Optional

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c1f2e3d4a5b6"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


STARTER_MOOD_GROUP = {
    "stable_key": "moodgroup_core_moods",
    "name": "Daily Moods",
    "icon": "mood",
    "color_value": 4282400832,
    "position": 10,
}

STARTER_MOODS = [
    {
        "stable_key": "mood_awesome",
        "key": "awesome",
        "name": "Awesome",
        "icon": "sentiment_very_satisfied",
        "score": 5,
        "category": "positive",
        "color_value": 4280391411,
        "position": 10,
    },
    {
        "stable_key": "mood_good",
        "key": "good",
        "name": "Good",
        "icon": "sentiment_satisfied",
        "score": 4,
        "category": "positive",
        "color_value": 4283215696,
        "position": 20,
    },
    {
        "stable_key": "mood_meh",
        "key": "meh",
        "name": "Meh",
        "icon": "sentiment_neutral",
        "score": 3,
        "category": "neutral",
        "color_value": 4294924066,
        "position": 30,
    },
    {
        "stable_key": "mood_bad",
        "key": "bad",
        "name": "Bad",
        "icon": "sentiment_dissatisfied",
        "score": 2,
        "category": "negative",
        "color_value": 4293467747,
        "position": 40,
    },
    {
        "stable_key": "mood_awful",
        "key": "awful",
        "name": "Awful",
        "icon": "sentiment_very_dissatisfied",
        "score": 1,
        "category": "negative",
        "color_value": 4293023059,
        "position": 50,
    },
]

STARTER_ACTIVITY_GROUPS = [
    {
        "stable_key": "activitygroup_wellness",
        "name": "Wellness",
        "icon": "heartPulse",
        "color_value": 4280391411,
        "position": 10,
        "activities": [
            {
                "stable_key": "activity_wellness_steps",
                "name": "Steps",
                "icon": "footprints",
                "color": "#3DBE5D",
                "position": 10,
            },
            {
                "stable_key": "activity_wellness_sleep",
                "name": "Sleep",
                "icon": "bedDouble",
                "color": "#4F8DF5",
                "position": 20,
            },
            {
                "stable_key": "activity_wellness_exercise",
                "name": "Exercise",
                "icon": "dumbbell",
                "color": "#F39C12",
                "position": 30,
            },
        ],
    },
    {
        "stable_key": "activitygroup_life_flow",
        "name": "Life Flow",
        "icon": "sparkles",
        "color_value": 4283215696,
        "position": 20,
        "activities": [
            {
                "stable_key": "activity_lifeflow_work",
                "name": "Work",
                "icon": "briefcase",
                "color": "#607D8B",
                "position": 10,
            },
            {
                "stable_key": "activity_lifeflow_family",
                "name": "Family",
                "icon": "house",
                "color": "#E91E63",
                "position": 20,
            },
            {
                "stable_key": "activity_lifeflow_journaling",
                "name": "Journaling",
                "icon": "notebookPen",
                "color": "#8E44AD",
                "position": 30,
            },
        ],
    },
]

STARTER_GOAL_CATEGORY = {
    "stable_key": "goalcat_mindfulness",
    "name": "Mindfulness",
    "icon": "brain",
    "color_value": 4282400832,
    "position": 10,
}

STARTER_GOAL = {
    "stable_key": "goal_mindfulness_journal_5d_week",
    "title": "Journal 5 days this week",
    "icon": "bookOpen",
    "goal_type": "achieve",
    "frequency_type": "weekly",
    "target_count": 5,
    "position": 10,
}

_BACKFILL_TABLE_LABEL_COLUMN_ALLOWLIST: dict[str, set[str]] = {
    "activity_group": {"name"},
    "activity": {"name"},
    "goal_category": {"name"},
    "goal": {"title"},
    "mood_group": {"name"},
    "mood": {"name"},
}


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(conn)
    return any(c["name"] == column_name for c in inspector.get_columns(table_name))


def _index_exists(conn, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(conn)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table_name))


def _constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(conn)
    return any(
        constraint.get("name") == constraint_name
        for constraint in inspector.get_unique_constraints(table_name)
    )


def _slugify(value: Optional[str]) -> str:
    raw = (value or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw or "item"


def _stable_key_for(prefix: str, name: Optional[str]) -> str:
    return f"{prefix}_{_slugify(name)}"


def _next_unique_key(
    seen: set[str],
    base_key: str,
) -> str:
    if base_key not in seen:
        seen.add(base_key)
        return base_key
    i = 2
    while True:
        candidate = f"{base_key}_{i}"
        if candidate not in seen:
            seen.add(candidate)
            return candidate
        i += 1


def _backfill_table_stable_keys(
    conn,
    *,
    table_name: str,
    prefix: str,
    label_column: str = "name",
) -> None:
    allowed_label_columns = _BACKFILL_TABLE_LABEL_COLUMN_ALLOWLIST.get(table_name)
    if allowed_label_columns is None or label_column not in allowed_label_columns:
        raise ValueError(
            f"Unsupported backfill target: table={table_name!r}, label_column={label_column!r}"
        )

    table = sa.table(
        table_name,
        sa.column("id"),
        sa.column("user_id"),
        sa.column(label_column),
        sa.column("stable_key"),
        sa.column("created_at"),
    )
    label_expr = getattr(table.c, label_column).label("label_value")
    stmt = (
        sa.select(table.c.id, table.c.user_id, label_expr, table.c.stable_key)
        .order_by(table.c.user_id, table.c.created_at, table.c.id)
    )

    rows = conn.execute(stmt).fetchall()
    user_seen: Dict[str, set[str]] = {}
    for row in rows:
        user_id = str(row.user_id)
        seen = user_seen.setdefault(user_id, set())
        if row.stable_key:
            seen.add(str(row.stable_key))

    for row in rows:
        if row.stable_key:
            continue
        user_id = str(row.user_id)
        seen = user_seen.setdefault(user_id, set())
        base_key = _stable_key_for(prefix, row.label_value)
        stable_key = _next_unique_key(seen, base_key)
        conn.execute(
            sa.update(table)
            .where(table.c.id == sa.bindparam("row_id_param"))
            .values(stable_key=sa.bindparam("stable_key_param")),
            {"stable_key_param": stable_key, "row_id_param": row.id},
        )


def _ensure_starter_moods_for_user(conn, user_id: str) -> None:
    group = conn.execute(
        sa.text(
            """
            SELECT id
            FROM mood_group
            WHERE user_id = :user_id AND stable_key = :stable_key
            LIMIT 1
            """
        ),
        {"user_id": user_id, "stable_key": STARTER_MOOD_GROUP["stable_key"]},
    ).fetchone()

    if group:
        mood_group_id = str(group.id)
    else:
        mood_group_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                """
                INSERT INTO mood_group (id, created_at, updated_at, user_id, name, icon, color_value, position, stable_key)
                VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :user_id, :name, :icon, :color_value, :position, :stable_key)
                """
            ),
            {
                "id": mood_group_id,
                "user_id": user_id,
                "name": STARTER_MOOD_GROUP["name"],
                "icon": STARTER_MOOD_GROUP["icon"],
                "color_value": STARTER_MOOD_GROUP["color_value"],
                "position": STARTER_MOOD_GROUP["position"],
                "stable_key": STARTER_MOOD_GROUP["stable_key"],
            },
        )

    for mood_data in STARTER_MOODS:
        mood = conn.execute(
            sa.text(
                """
                SELECT id
                FROM mood
                WHERE user_id = :user_id AND stable_key = :stable_key
                LIMIT 1
                """
            ),
            {"user_id": user_id, "stable_key": mood_data["stable_key"]},
        ).fetchone()

        if mood:
            mood_id = str(mood.id)
        else:
            mood_id = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    """
                    INSERT INTO mood (
                        id,
                        created_at,
                        updated_at,
                        user_id,
                        name,
                        key,
                        icon,
                        color_value,
                        category,
                        score,
                        position,
                        is_active,
                        stable_key
                    )
                    VALUES (
                        :id,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        :user_id,
                        :name,
                        :key,
                        :icon,
                        :color_value,
                        :category,
                        :score,
                        :position,
                        TRUE,
                        :stable_key
                    )
                    """
                ),
                {
                    "id": mood_id,
                    "user_id": user_id,
                    "name": mood_data["name"],
                    "key": mood_data["key"],
                    "icon": mood_data["icon"],
                    "color_value": mood_data["color_value"],
                    "category": mood_data["category"],
                    "score": mood_data["score"],
                    "position": mood_data["position"],
                    "stable_key": mood_data["stable_key"],
                },
            )

        link_exists = conn.execute(
            sa.text(
                """
                SELECT 1
                FROM mood_group_link
                WHERE mood_group_id = :mood_group_id AND mood_id = :mood_id
                LIMIT 1
                """
            ),
            {"mood_group_id": mood_group_id, "mood_id": mood_id},
        ).fetchone()
        if not link_exists:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO mood_group_link (id, created_at, updated_at, mood_group_id, mood_id, position)
                    VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :mood_group_id, :mood_id, :position)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "mood_group_id": mood_group_id,
                    "mood_id": mood_id,
                    "position": mood_data["position"],
                },
            )


def _ensure_starter_activity_data_for_user(conn, user_id: str) -> None:
    for group_data in STARTER_ACTIVITY_GROUPS:
        group = conn.execute(
            sa.text(
                """
                SELECT id
                FROM activity_group
                WHERE user_id = :user_id AND stable_key = :stable_key
                LIMIT 1
                """
            ),
            {"user_id": user_id, "stable_key": group_data["stable_key"]},
        ).fetchone()
        if group:
            group_id = str(group.id)
        else:
            group_id = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    """
                    INSERT INTO activity_group (id, created_at, updated_at, user_id, name, icon, color_value, position, stable_key)
                    VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :user_id, :name, :icon, :color_value, :position, :stable_key)
                    """
                ),
                {
                    "id": group_id,
                    "user_id": user_id,
                    "name": group_data["name"],
                    "icon": group_data["icon"],
                    "color_value": group_data["color_value"],
                    "position": group_data["position"],
                    "stable_key": group_data["stable_key"],
                },
            )

        for activity_data in group_data["activities"]:
            activity_exists = conn.execute(
                sa.text(
                    """
                    SELECT 1
                    FROM activity
                    WHERE user_id = :user_id AND stable_key = :stable_key
                    LIMIT 1
                    """
                ),
                {"user_id": user_id, "stable_key": activity_data["stable_key"]},
            ).fetchone()
            if activity_exists:
                continue
            conn.execute(
                sa.text(
                    """
                    INSERT INTO activity (
                        id,
                        created_at,
                        updated_at,
                        name,
                        user_id,
                        icon,
                        color,
                        position,
                        stable_key,
                        group_id
                    )
                    VALUES (
                        :id,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP,
                        :name,
                        :user_id,
                        :icon,
                        :color,
                        :position,
                        :stable_key,
                        :group_id
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "name": activity_data["name"],
                    "user_id": user_id,
                    "icon": activity_data["icon"],
                    "color": activity_data["color"],
                    "position": activity_data["position"],
                    "stable_key": activity_data["stable_key"],
                    "group_id": group_id,
                },
            )


def _ensure_starter_goal_data_for_user(conn, user_id: str) -> None:
    category = conn.execute(
        sa.text(
            """
            SELECT id
            FROM goal_category
            WHERE user_id = :user_id AND stable_key = :stable_key
            LIMIT 1
            """
        ),
        {"user_id": user_id, "stable_key": STARTER_GOAL_CATEGORY["stable_key"]},
    ).fetchone()

    if category:
        category_id = str(category.id)
    else:
        category_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                """
                INSERT INTO goal_category (id, created_at, updated_at, name, user_id, color_value, icon, position, stable_key)
                VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :name, :user_id, :color_value, :icon, :position, :stable_key)
                """
            ),
            {
                "id": category_id,
                "name": STARTER_GOAL_CATEGORY["name"],
                "user_id": user_id,
                "color_value": STARTER_GOAL_CATEGORY["color_value"],
                "icon": STARTER_GOAL_CATEGORY["icon"],
                "position": STARTER_GOAL_CATEGORY["position"],
                "stable_key": STARTER_GOAL_CATEGORY["stable_key"],
            },
        )

    goal_exists = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM goal
            WHERE user_id = :user_id AND stable_key = :stable_key
            LIMIT 1
            """
        ),
        {"user_id": user_id, "stable_key": STARTER_GOAL["stable_key"]},
    ).fetchone()
    if goal_exists:
        return

    conn.execute(
        sa.text(
            """
            INSERT INTO goal (
                id,
                created_at,
                updated_at,
                user_id,
                activity_id,
                category_id,
                title,
                goal_type,
                frequency_type,
                target_count,
                reminder_time,
                is_paused,
                icon,
                color_value,
                position,
                stable_key,
                archived_at
            )
            VALUES (
                :id,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP,
                :user_id,
                NULL,
                :category_id,
                :title,
                :goal_type,
                :frequency_type,
                :target_count,
                NULL,
                FALSE,
                :icon,
                NULL,
                :position,
                :stable_key,
                NULL
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "category_id": category_id,
            "title": STARTER_GOAL["title"],
            "icon": STARTER_GOAL.get("icon"),
            "goal_type": STARTER_GOAL["goal_type"],
            "frequency_type": STARTER_GOAL["frequency_type"],
            "target_count": STARTER_GOAL["target_count"],
            "position": STARTER_GOAL["position"],
            "stable_key": STARTER_GOAL["stable_key"],
        },
    )


def _ensure_starter_data_for_users(conn) -> None:
    user_ids = [str(row.id) for row in conn.execute(sa.text('SELECT id FROM "user"')).fetchall()]
    for user_id in user_ids:
        _ensure_starter_moods_for_user(conn, user_id)
        _ensure_starter_activity_data_for_user(conn, user_id)
        _ensure_starter_goal_data_for_user(conn, user_id)


def _legacy_mood_stable_key(key: Optional[str], name: Optional[str]) -> Optional[str]:
    lookup = (key or "").strip().lower()
    name_lookup = (name or "").strip().lower()
    if lookup in {"awesome", "very_positive", "verypositive"} or name_lookup in {"awesome", "very positive"}:
        return "mood_awesome"
    if lookup in {"good", "positive"} or name_lookup in {"good", "positive"}:
        return "mood_good"
    if lookup in {"meh", "neutral"} or name_lookup in {"meh", "neutral"}:
        return "mood_meh"
    if lookup in {"bad", "negative"} or name_lookup in {"bad", "negative"}:
        return "mood_bad"
    if lookup in {"awful", "very_negative", "verynegative"} or name_lookup in {"awful", "very negative"}:
        return "mood_awful"
    return None


def _remap_and_remove_system_moods(conn) -> None:
    system_moods = conn.execute(
        sa.text("SELECT id, key, name FROM mood WHERE user_id IS NULL")
    ).fetchall()
    if not system_moods:
        return

    user_ids = [str(row.id) for row in conn.execute(sa.text('SELECT id FROM "user"')).fetchall()]

    for legacy_mood in system_moods:
        old_mood_id = str(legacy_mood.id)
        stable_key = _legacy_mood_stable_key(legacy_mood.key, legacy_mood.name)
        if stable_key is None:
            continue

        for user_id in user_ids:
            target_row = conn.execute(
                sa.text(
                    """
                    SELECT id
                    FROM mood
                    WHERE user_id = :user_id AND stable_key = :stable_key
                    LIMIT 1
                    """
                ),
                {"user_id": user_id, "stable_key": stable_key},
            ).fetchone()
            if not target_row:
                continue
            new_mood_id = str(target_row.id)

            conn.execute(
                sa.text(
                    """
                    DELETE FROM user_mood_preference
                    WHERE user_id = :user_id
                      AND mood_id = :old_mood_id
                      AND EXISTS (
                        SELECT 1
                        FROM user_mood_preference p2
                        WHERE p2.user_id = :user_id
                          AND p2.mood_id = :new_mood_id
                          AND p2.id != user_mood_preference.id
                      )
                    """
                ),
                {
                    "user_id": user_id,
                    "old_mood_id": old_mood_id,
                    "new_mood_id": new_mood_id,
                },
            )
            conn.execute(
                sa.text(
                    """
                    UPDATE user_mood_preference
                    SET mood_id = :new_mood_id
                    WHERE user_id = :user_id
                      AND mood_id = :old_mood_id
                    """
                ),
                {
                    "user_id": user_id,
                    "old_mood_id": old_mood_id,
                    "new_mood_id": new_mood_id,
                },
            )

            conn.execute(
                sa.text(
                    """
                    DELETE FROM mood_group_link
                    WHERE mood_id = :old_mood_id
                      AND EXISTS (
                        SELECT 1
                        FROM mood_group g
                        JOIN mood_group_link l2 ON l2.mood_group_id = g.id
                        WHERE g.user_id = :user_id
                          AND l2.mood_id = :new_mood_id
                          AND l2.mood_group_id = mood_group_link.mood_group_id
                          AND l2.id != mood_group_link.id
                      )
                    """
                ),
                {
                    "user_id": user_id,
                    "old_mood_id": old_mood_id,
                    "new_mood_id": new_mood_id,
                },
            )
            conn.execute(
                sa.text(
                    """
                    UPDATE mood_group_link
                    SET mood_id = :new_mood_id
                    WHERE mood_id = :old_mood_id
                      AND EXISTS (
                        SELECT 1
                        FROM mood_group g
                        WHERE g.id = mood_group_link.mood_group_id
                          AND g.user_id = :user_id
                      )
                    """
                ),
                {
                    "user_id": user_id,
                    "old_mood_id": old_mood_id,
                    "new_mood_id": new_mood_id,
                },
            )

            conn.execute(
                sa.text(
                    """
                    DELETE FROM moment_mood_activity
                    WHERE mood_id = :old_mood_id
                      AND EXISTS (
                        SELECT 1
                        FROM moment m
                        JOIN moment_mood_activity m2 ON m2.moment_id = m.id
                        WHERE m.user_id = :user_id
                          AND m2.mood_id = :new_mood_id
                          AND m2.moment_id = moment_mood_activity.moment_id
                          AND (
                            (m2.activity_id = moment_mood_activity.activity_id)
                            OR (
                                m2.activity_id IS NULL
                                AND moment_mood_activity.activity_id IS NULL
                            )
                          )
                          AND m2.id != moment_mood_activity.id
                      )
                    """
                ),
                {
                    "user_id": user_id,
                    "old_mood_id": old_mood_id,
                    "new_mood_id": new_mood_id,
                },
            )
            conn.execute(
                sa.text(
                    """
                    UPDATE moment_mood_activity
                    SET mood_id = :new_mood_id
                    WHERE mood_id = :old_mood_id
                      AND EXISTS (
                        SELECT 1
                        FROM moment m
                        WHERE m.id = moment_mood_activity.moment_id
                          AND m.user_id = :user_id
                      )
                    """
                ),
                {
                    "user_id": user_id,
                    "old_mood_id": old_mood_id,
                    "new_mood_id": new_mood_id,
                },
            )

            conn.execute(
                sa.text(
                    """
                    UPDATE moment
                    SET primary_mood_id = :new_mood_id
                    WHERE user_id = :user_id
                      AND primary_mood_id = :old_mood_id
                    """
                ),
                {
                    "user_id": user_id,
                    "old_mood_id": old_mood_id,
                    "new_mood_id": new_mood_id,
                },
            )

    conn.execute(
        sa.text(
            """
            DELETE FROM user_mood_group_preference
            WHERE mood_group_id IN (
                SELECT id FROM mood_group WHERE user_id IS NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            DELETE FROM mood_group_link
            WHERE mood_group_id IN (
                SELECT id FROM mood_group WHERE user_id IS NULL
            )
            """
        )
    )

    conn.execute(
        sa.text(
            """
            DELETE FROM mood_group_link
            WHERE mood_id IN (
                SELECT id FROM mood WHERE user_id IS NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            DELETE FROM user_mood_preference
            WHERE mood_id IN (
                SELECT id FROM mood WHERE user_id IS NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            DELETE FROM moment_mood_activity
            WHERE mood_id IN (
                SELECT id FROM mood WHERE user_id IS NULL
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE moment
            SET primary_mood_id = NULL
            WHERE primary_mood_id IN (
                SELECT id FROM mood WHERE user_id IS NULL
            )
            """
        )
    )

    conn.execute(sa.text("DELETE FROM mood_group WHERE user_id IS NULL"))
    conn.execute(sa.text("DELETE FROM mood WHERE user_id IS NULL"))


def _ensure_not_null_user_ids(conn) -> None:
    null_mood_count = conn.execute(
        sa.text("SELECT COUNT(*) FROM mood WHERE user_id IS NULL")
    ).scalar() or 0
    null_group_count = conn.execute(
        sa.text("SELECT COUNT(*) FROM mood_group WHERE user_id IS NULL")
    ).scalar() or 0
    if null_mood_count or null_group_count:
        raise RuntimeError(
            "Cannot enforce non-null user_id on mood/mood_group while NULL rows remain"
        )


def _add_columns(conn) -> None:
    if not _column_exists(conn, "activity_group", "stable_key"):
        op.add_column("activity_group", sa.Column("stable_key", sa.String(length=100), nullable=True))
    if not _column_exists(conn, "activity", "stable_key"):
        op.add_column("activity", sa.Column("stable_key", sa.String(length=100), nullable=True))
    if not _column_exists(conn, "goal_category", "stable_key"):
        op.add_column("goal_category", sa.Column("stable_key", sa.String(length=100), nullable=True))
    if not _column_exists(conn, "goal", "stable_key"):
        op.add_column("goal", sa.Column("stable_key", sa.String(length=100), nullable=True))
    if not _column_exists(conn, "mood_group", "stable_key"):
        op.add_column("mood_group", sa.Column("stable_key", sa.String(length=100), nullable=True))
    if not _column_exists(conn, "mood", "stable_key"):
        op.add_column("mood", sa.Column("stable_key", sa.String(length=100), nullable=True))


def _add_constraints(conn) -> None:
    is_sqlite = conn.dialect.name == "sqlite"
    if is_sqlite:
        if not _index_exists(conn, "activity_group", "uq_activity_group_user_stable_key"):
            op.create_index(
                "uq_activity_group_user_stable_key",
                "activity_group",
                ["user_id", "stable_key"],
                unique=True,
            )
        if not _index_exists(conn, "activity", "uq_activity_user_stable_key"):
            op.create_index(
                "uq_activity_user_stable_key",
                "activity",
                ["user_id", "stable_key"],
                unique=True,
            )
        if not _index_exists(conn, "goal_category", "uq_goal_category_user_stable_key"):
            op.create_index(
                "uq_goal_category_user_stable_key",
                "goal_category",
                ["user_id", "stable_key"],
                unique=True,
            )
        if not _index_exists(conn, "goal", "uq_goal_user_stable_key"):
            op.create_index(
                "uq_goal_user_stable_key",
                "goal",
                ["user_id", "stable_key"],
                unique=True,
            )
    else:
        if not _constraint_exists(conn, "activity_group", "uq_activity_group_user_stable_key"):
            op.create_unique_constraint(
                "uq_activity_group_user_stable_key",
                "activity_group",
                ["user_id", "stable_key"],
            )
        if not _constraint_exists(conn, "activity", "uq_activity_user_stable_key"):
            op.create_unique_constraint(
                "uq_activity_user_stable_key",
                "activity",
                ["user_id", "stable_key"],
            )
        if not _constraint_exists(conn, "goal_category", "uq_goal_category_user_stable_key"):
            op.create_unique_constraint(
                "uq_goal_category_user_stable_key",
                "goal_category",
                ["user_id", "stable_key"],
            )
        if not _constraint_exists(conn, "goal", "uq_goal_user_stable_key"):
            op.create_unique_constraint(
                "uq_goal_user_stable_key",
                "goal",
                ["user_id", "stable_key"],
            )

    if not _index_exists(conn, "mood", "uq_mood_user_stable_key"):
        op.create_index(
            "uq_mood_user_stable_key",
            "mood",
            ["user_id", "stable_key"],
            unique=True,
        )
    if not _index_exists(conn, "mood_group", "uq_mood_group_user_stable_key"):
        op.create_index(
            "uq_mood_group_user_stable_key",
            "mood_group",
            ["user_id", "stable_key"],
            unique=True,
        )


def _enforce_non_nullable_user_id(conn) -> None:
    is_sqlite = conn.dialect.name == "sqlite"
    if is_sqlite:
        with op.batch_alter_table("mood") as batch_op:
            batch_op.alter_column("user_id", nullable=False)
        with op.batch_alter_table("mood_group") as batch_op:
            batch_op.alter_column("user_id", nullable=False)
    else:
        op.alter_column("mood", "user_id", nullable=False)
        op.alter_column("mood_group", "user_id", nullable=False)


def upgrade() -> None:
    conn = op.get_bind()

    _add_columns(conn)

    _backfill_table_stable_keys(conn, table_name="activity_group", prefix="activitygroup")
    _backfill_table_stable_keys(conn, table_name="activity", prefix="activity")
    _backfill_table_stable_keys(conn, table_name="goal_category", prefix="goalcat")
    _backfill_table_stable_keys(conn, table_name="goal", prefix="goal", label_column="title")
    _backfill_table_stable_keys(conn, table_name="mood_group", prefix="moodgroup")
    _backfill_table_stable_keys(conn, table_name="mood", prefix="mood")

    _ensure_starter_data_for_users(conn)
    _remap_and_remove_system_moods(conn)

    _ensure_not_null_user_ids(conn)
    _enforce_non_nullable_user_id(conn)

    _add_constraints(conn)


def _drop_constraints(conn) -> None:
    is_sqlite = conn.dialect.name == "sqlite"
    if is_sqlite:
        if _index_exists(conn, "goal", "uq_goal_user_stable_key"):
            op.drop_index("uq_goal_user_stable_key", table_name="goal")
        if _index_exists(conn, "goal_category", "uq_goal_category_user_stable_key"):
            op.drop_index("uq_goal_category_user_stable_key", table_name="goal_category")
        if _index_exists(conn, "activity", "uq_activity_user_stable_key"):
            op.drop_index("uq_activity_user_stable_key", table_name="activity")
        if _index_exists(conn, "activity_group", "uq_activity_group_user_stable_key"):
            op.drop_index("uq_activity_group_user_stable_key", table_name="activity_group")
    else:
        if _constraint_exists(conn, "goal", "uq_goal_user_stable_key"):
            op.drop_constraint("uq_goal_user_stable_key", "goal", type_="unique")
        if _constraint_exists(conn, "goal_category", "uq_goal_category_user_stable_key"):
            op.drop_constraint("uq_goal_category_user_stable_key", "goal_category", type_="unique")
        if _constraint_exists(conn, "activity", "uq_activity_user_stable_key"):
            op.drop_constraint("uq_activity_user_stable_key", "activity", type_="unique")
        if _constraint_exists(conn, "activity_group", "uq_activity_group_user_stable_key"):
            op.drop_constraint("uq_activity_group_user_stable_key", "activity_group", type_="unique")
    if _index_exists(conn, "mood_group", "uq_mood_group_user_stable_key"):
        op.drop_index("uq_mood_group_user_stable_key", table_name="mood_group")
    if _index_exists(conn, "mood", "uq_mood_user_stable_key"):
        op.drop_index("uq_mood_user_stable_key", table_name="mood")


def _allow_nullable_user_id(conn) -> None:
    is_sqlite = conn.dialect.name == "sqlite"
    if is_sqlite:
        with op.batch_alter_table("mood") as batch_op:
            batch_op.alter_column("user_id", nullable=True)
        with op.batch_alter_table("mood_group") as batch_op:
            batch_op.alter_column("user_id", nullable=True)
    else:
        op.alter_column("mood", "user_id", nullable=True)
        op.alter_column("mood_group", "user_id", nullable=True)


def downgrade() -> None:
    conn = op.get_bind()

    _drop_constraints(conn)
    _allow_nullable_user_id(conn)

    if _column_exists(conn, "mood", "stable_key"):
        op.drop_column("mood", "stable_key")
    if _column_exists(conn, "mood_group", "stable_key"):
        op.drop_column("mood_group", "stable_key")
    if _column_exists(conn, "goal", "stable_key"):
        op.drop_column("goal", "stable_key")
    if _column_exists(conn, "goal_category", "stable_key"):
        op.drop_column("goal_category", "stable_key")
    if _column_exists(conn, "activity", "stable_key"):
        op.drop_column("activity", "stable_key")
    if _column_exists(conn, "activity_group", "stable_key"):
        op.drop_column("activity_group", "stable_key")
