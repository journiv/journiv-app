from datetime import datetime, timezone

import pytest

from app.data_transfer.dayone.mappers import DayOneToJournivMapper
from app.data_transfer.dayone.models import DayOneEntry


def test_dayone_entry_accepts_epoch_milliseconds():
    entry = DayOneEntry(
        uuid="entry-epoch-ms",
        creationDate=1_700_000_000_000,
    )

    assert entry.creation_date.tzinfo is not None
    assert entry.creation_date.year == 2023


def test_dayone_entry_rejects_out_of_range_datetime():
    with pytest.raises(ValueError, match="out of supported range"):
        DayOneEntry(
            uuid="entry-out-of-range",
            creationDate="0001-01-01T00:00:00Z",
        )


def test_dayone_entry_rejects_boolean_datetime():
    with pytest.raises(ValueError, match="Invalid datetime value type"):
        DayOneEntry(
            uuid="entry-bool-date",
            creationDate=True,
        )


def test_dayone_entry_rejects_non_finite_epoch_datetime():
    with pytest.raises(ValueError, match="Invalid non-finite datetime value"):
        DayOneEntry(
            uuid="entry-nan-date",
            creationDate=float("nan"),
        )


def test_map_moment_falls_back_to_utc_date_on_local_date_error(monkeypatch):
    entry = DayOneEntry(
        uuid="entry-overflow-fallback",
        creationDate=datetime(2026, 2, 25, 20, 44, 52, tzinfo=timezone.utc),
        timeZone="America/New_York",
    )

    def _raise_overflow(*args, **kwargs):
        raise OverflowError("date value out of range")

    monkeypatch.setattr(
        "app.data_transfer.dayone.mappers.local_date_for_user",
        _raise_overflow,
    )

    moment = DayOneToJournivMapper.map_moment(entry)
    assert moment.logged_timezone == "UTC"
    assert moment.logged_date_tz == datetime(2026, 2, 25, tzinfo=timezone.utc).date()
