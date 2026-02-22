from datetime import datetime, timezone

from app.data_transfer.daylio.mappers import DaylioToJournivMapper
from app.data_transfer.daylio.models import (
    DaylioBackup,
    DaylioGoalEntry,
    DaylioGoalSuccessWeek,
)


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
