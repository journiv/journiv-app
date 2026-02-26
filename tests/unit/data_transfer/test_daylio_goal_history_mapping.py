from datetime import datetime, timezone

from app.data_transfer.daylio.mappers import DaylioToJournivMapper
from app.data_transfer.daylio.models import (
    DaylioBackup,
    DaylioDayEntry,
    DaylioGoal,
    DaylioGoalEntry,
    DaylioGoalSuccessWeek,
)
from app.models.enums import GoalFrequency


def test_map_goal_success_weeks_to_weekly_goal_logs():
    backup = DaylioBackup(
        version=15,
        goalSuccessWeeks=[
            DaylioGoalSuccessWeek(goal_id=99, week=7, year=2026),
        ],
    )
    logs = DaylioToJournivMapper._map_goal_success_weeks(
        backup,
        import_timestamp=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )

    assert len(logs) == 1
    log = logs[0]
    assert log.goal_external_id == "99"
    assert log.period_start.isoformat() == "2026-02-09"  # ISO week 7, Monday
    assert log.period_end.isoformat() == "2026-02-15"
    assert log.logged_date.isoformat() == "2026-02-15"
    assert log.count == 1
    assert log.external_id == "daylio-week-99-2026-7"


def test_merge_goal_logs_prefers_daily_when_period_start_collides():
    backup = DaylioBackup(
        version=15,
        goalEntries=[
            DaylioGoalEntry(
                id=1,
                goalId=77,
                createdAt=1739318400000,  # 2025-02-12 UTC
                year=2025,
                month=1,  # Feb
                day=10,   # Monday
                hour=10,
                minute=0,
            ),
        ],
        goalSuccessWeeks=[
            DaylioGoalSuccessWeek(goal_id=77, week=7, year=2025),  # starts 2025-02-10
        ],
    )
    daily_logs = DaylioToJournivMapper._map_goal_logs(
        backup,
        import_timestamp=datetime(2025, 2, 12, tzinfo=timezone.utc),
    )
    weekly_logs = DaylioToJournivMapper._map_goal_success_weeks(
        backup,
        import_timestamp=datetime(2025, 2, 12, tzinfo=timezone.utc),
    )
    merged = DaylioToJournivMapper._merge_goal_logs(
        daily_logs=daily_logs,
        weekly_logs=weekly_logs,
    )

    assert len(daily_logs) == 1
    assert len(weekly_logs) == 1
    assert len(merged) == 1
    assert merged[0].external_id == "1"


def test_map_goal_logs_links_to_day_entry_moment_external_id_with_month_normalization():
    backup = DaylioBackup(
        version=19,
        dayEntries=[
            # Day entry month is 0-based (Feb -> 1)
            DaylioDayEntry(
                datetime=1770577260000,
                year=2026,
                month=1,
                day=8,
                hour=11,
                minute=1,
            ),
        ],
        goalEntries=[
            # Goal entry month is 1-based in this fixture style (Feb -> 2)
            DaylioGoalEntry(
                id=3,
                goalId=1,
                createdAt=1770594609002,
                year=2026,
                month=2,
                day=8,
                hour=15,
                minute=50,
                second=6,
            ),
        ],
    )

    logs = DaylioToJournivMapper._map_goal_logs(
        backup,
        import_timestamp=datetime(2026, 2, 20, tzinfo=timezone.utc),
    )

    assert len(logs) == 1
    assert logs[0].moment_external_id == "daylio-moment-1770577260000"


def test_map_goal_success_weeks_handles_one_based_month_without_fallback():
    backup = DaylioBackup(
        version=19,
        goalSuccessWeeks=[
            DaylioGoalSuccessWeek(
                goal_id=1,
                week=52,
                year=2024,
                create_at_year=2024,
                create_at_month=12,  # One-based month (December)
                create_at_day=29,
            ),
        ],
    )
    import_timestamp = datetime(2026, 2, 20, tzinfo=timezone.utc)

    logs = DaylioToJournivMapper._map_goal_success_weeks(
        backup,
        import_timestamp=import_timestamp,
    )

    assert len(logs) == 1
    assert logs[0].created_at == datetime(2024, 12, 29, tzinfo=timezone.utc)


def test_map_goal_success_weeks_handles_month_one_day_thirty_without_fallback():
    # Intentional mismatch: ISO week/year metadata may disagree with raw created_at
    # components in real Daylio exports. Mapper should preserve create_at_* timestamp
    # (after month normalization), not clamp it into the ISO week window.
    backup = DaylioBackup(
        version=19,
        goalSuccessWeeks=[
            DaylioGoalSuccessWeek(
                goal_id=1,
                week=5,
                year=2022,
                create_at_year=2022,
                create_at_month=1,
                create_at_day=30,
            ),
        ],
    )
    import_timestamp = datetime(2026, 2, 20, tzinfo=timezone.utc)

    logs = DaylioToJournivMapper._map_goal_success_weeks(
        backup,
        import_timestamp=import_timestamp,
    )

    assert len(logs) == 1
    assert logs[0].created_at == datetime(2022, 1, 30, tzinfo=timezone.utc)


def test_map_goals_uses_unit_target_for_daily_repeat_bitmask():
    backup = DaylioBackup(
        version=19,
        goals=[
            DaylioGoal(
                goal_id=1,
                name="short exercise",
                repeat_type=1,
                repeat_value=127,  # Daylio daily schedule bitmask (all days of the week selected)
            ),
        ],
    )
    import_timestamp = datetime(2026, 2, 20, tzinfo=timezone.utc)
    ctx = DaylioToJournivMapper._build_context(backup)

    goals = DaylioToJournivMapper._map_goals(
        backup,
        import_timestamp=import_timestamp,
        ctx=ctx,
    )

    assert len(goals) == 1
    assert goals[0].frequency_type == GoalFrequency.DAILY
    assert goals[0].target_count == 1


def test_map_goals_uses_repeat_value_for_weekly_target():
    backup = DaylioBackup(
        version=19,
        goals=[
            DaylioGoal(
                goal_id=2,
                name="Journal 3 days this week",
                repeat_type=2,
                repeat_value=3,
            ),
        ],
    )
    import_timestamp = datetime(2026, 2, 20, tzinfo=timezone.utc)
    ctx = DaylioToJournivMapper._build_context(backup)

    goals = DaylioToJournivMapper._map_goals(
        backup,
        import_timestamp=import_timestamp,
        ctx=ctx,
    )

    assert len(goals) == 1
    assert goals[0].frequency_type == GoalFrequency.WEEKLY
    assert goals[0].target_count == 3


def test_map_goals_marks_daylio_archived_goal_with_archived_at():
    end_date_ms = 1772036346918
    backup = DaylioBackup(
        version=19,
        goals=[
            DaylioGoal(
                goal_id=3,
                name="Archived goal",
                repeat_type=1,
                repeat_value=127,
                state=1,
                end_date=end_date_ms,
            ),
        ],
    )
    import_timestamp = datetime(2026, 2, 20, tzinfo=timezone.utc)
    ctx = DaylioToJournivMapper._build_context(backup)

    goals = DaylioToJournivMapper._map_goals(
        backup,
        import_timestamp=import_timestamp,
        ctx=ctx,
    )

    assert len(goals) == 1
    assert goals[0].archived_at == datetime.fromtimestamp(end_date_ms / 1000, tz=timezone.utc)
    assert goals[0].is_paused is False


def test_map_goals_archives_from_state_when_end_date_missing():
    backup = DaylioBackup(
        version=19,
        goals=[
            DaylioGoal(
                goal_id=4,
                name="Archived from state",
                repeat_type=1,
                repeat_value=127,
                state=1,
                end_date=-1,
            ),
        ],
    )
    import_timestamp = datetime(2026, 2, 20, tzinfo=timezone.utc)
    ctx = DaylioToJournivMapper._build_context(backup)

    goals = DaylioToJournivMapper._map_goals(
        backup,
        import_timestamp=import_timestamp,
        ctx=ctx,
    )

    assert len(goals) == 1
    assert goals[0].archived_at == import_timestamp
    assert goals[0].is_paused is False


def test_map_goals_archives_from_end_date_even_when_state_active():
    end_date_ms = 1772036346918
    backup = DaylioBackup(
        version=19,
        goals=[
            DaylioGoal(
                goal_id=5,
                name="Archived from end date",
                repeat_type=1,
                repeat_value=127,
                state=0,
                end_date=end_date_ms,
            ),
        ],
    )
    import_timestamp = datetime(2026, 2, 20, tzinfo=timezone.utc)
    ctx = DaylioToJournivMapper._build_context(backup)

    goals = DaylioToJournivMapper._map_goals(
        backup,
        import_timestamp=import_timestamp,
        ctx=ctx,
    )

    assert len(goals) == 1
    assert goals[0].archived_at == datetime.fromtimestamp(end_date_ms / 1000, tz=timezone.utc)
    assert goals[0].is_paused is False
