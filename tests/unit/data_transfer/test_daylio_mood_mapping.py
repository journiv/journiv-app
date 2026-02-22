from datetime import datetime, timezone

import pytest

from app.data_transfer.daylio.mappers import DaylioMappingContext, DaylioToJournivMapper
from app.data_transfer.daylio.models import DaylioDayEntry


def _day_entry_with_mood(mood: int) -> DaylioDayEntry:
    return DaylioDayEntry(
        datetime=1704067200000,
        year=2024,
        month=0,
        day=1,
        hour=0,
        minute=0,
        mood=mood,
        tags=[],
        assets=[],
        note=None,
        note_title=None,
    )


@pytest.mark.parametrize(
    ("daylio_mood", "expected_name"),
    [
        (1, "Awesome"),  # Daylio "Rad" is mapped to Journiv "Awesome"
        (2, "Good"),
        (3, "Meh"),
        (4, "Bad"),
        (5, "Awful"),
    ],
)
def test_map_moment_uses_predefined_mood_name_when_custom_mood_missing(
    daylio_mood: int,
    expected_name: str,
):
    day_entry = _day_entry_with_mood(daylio_mood)
    ctx = DaylioMappingContext(
        assets_by_id={},
        tags_by_id={},
        tag_groups_by_id={},
        moods_by_id={},
    )

    moment = DaylioToJournivMapper._map_moment(
        day_entry,
        ctx,
        import_timestamp=datetime.now(timezone.utc),
        media_dir=None,
        attach_media=False,
    )

    assert moment.primary_mood_name == expected_name
    assert moment.primary_mood_external_id is None
    assert moment.mood_activity
    assert moment.mood_activity[0].mood_name == expected_name
    assert moment.mood_activity[0].mood_external_id is None


def test_map_moment_uses_custom_mood_external_id_when_available():
    day_entry = _day_entry_with_mood(42)
    ctx = DaylioMappingContext(
        assets_by_id={},
        tags_by_id={},
        tag_groups_by_id={},
        moods_by_id={
            42: {
                "id": 42,
                "custom_name": "Calm",
                "predefined_name_id": 3,
            }
        },
    )

    moment = DaylioToJournivMapper._map_moment(
        day_entry,
        ctx,
        import_timestamp=datetime.now(timezone.utc),
        media_dir=None,
        attach_media=False,
    )

    assert moment.primary_mood_name == "Calm"
    assert moment.primary_mood_external_id == "42"
    assert moment.mood_activity
    assert moment.mood_activity[0].mood_name == "Calm"
    assert moment.mood_activity[0].mood_external_id == "42"
