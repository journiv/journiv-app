"""
An update built on a stale version must be refused, not silently applied.

Journiv has no autosave: an editor holds a whole entry in memory and writes it
back on Done. Two devices open on the same entry therefore mean the second Done
replaces everything the first one wrote, with nothing to show that it happened.

`EntryUpdate.expected_updated_at` closes that: a client that sends the version
it edited gets a `ConcurrentModificationError` instead of a silent overwrite.
Sending nothing keeps the old last-write-wins behaviour, so existing clients —
the Flutter app among them — are unaffected.
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlmodel import Session, create_engine

from app.core.exceptions import ConcurrentModificationError
from app.core.time_utils import ensure_utc
from app.models.analytics import WritingStreak
from app.models.base import BaseModel
from app.models.entry import Entry
from app.models.journal import Journal
from app.models.moment import Moment
from app.models.user import User
from app.schemas.entry import EntryUpdate, QuillDelta
from app.services.analytics_service import AnalyticsService
from app.services.entry_service import EntryService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    return Session(engine)


def _fixtures(session: Session):
    user = User(email=f"c_{uuid.uuid4().hex[:8]}@example.com", password="x", name="C")
    session.add(user)
    session.commit()
    session.refresh(user)

    journal = Journal(user_id=user.id, title="J")
    moment = Moment(user_id=user.id)
    session.add(journal)
    session.add(moment)
    session.commit()
    session.refresh(journal)
    session.refresh(moment)

    entry = Entry(
        user_id=user.id,
        journal_id=journal.id,
        moment_id=moment.id,
        title="First",
        content_delta={"ops": [{"insert": "one\n"}]},
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return user, entry


def _delta(text: str) -> QuillDelta:
    return QuillDelta(ops=[{"insert": text}])


def test_matching_version_is_accepted():
    session = _session()
    user, entry = _fixtures(session)
    service = EntryService(session)

    # Captured before the update: `entry` is the live ORM object and moves with it.
    opened_at = ensure_utc(entry.updated_at)

    updated = service.update_entry(
        entry.id,
        user.id,
        EntryUpdate(
            title="Second",
            content_delta=_delta("two\n"),
            expected_updated_at=opened_at,
        ),
    )

    assert updated.title == "Second"
    # And the version moves on, so the same save cannot be replayed — which is
    # what makes the check worth anything at all.
    assert ensure_utc(updated.updated_at) > opened_at
    with pytest.raises(ConcurrentModificationError):
        service.update_entry(
            entry.id, user.id, EntryUpdate(title="Third", expected_updated_at=opened_at)
        )


def test_drafting_published_entry_recalculates_writing_streak():
    session = _session()
    user, entry = _fixtures(session)
    entry.word_count = 1
    entry.moment.logged_date_tz = date.today()

    earlier_moment = Moment(
        user_id=user.id,
        logged_date_tz=date.today() - timedelta(days=1),
    )
    session.add(earlier_moment)
    session.flush()
    session.add(
        Entry(
            user_id=user.id,
            journal_id=entry.journal_id,
            moment_id=earlier_moment.id,
            content_delta={"ops": [{"insert": "two\n"}]},
            word_count=1,
        )
    )
    session.add(WritingStreak(user_id=user.id))
    session.commit()

    streak = AnalyticsService(session).recalculate_writing_streak_stats(user.id)
    assert streak is not None
    assert streak.current_streak == 2

    updated = EntryService(session).update_entry(
        entry.id, user.id, EntryUpdate(is_draft=True)
    )

    session.refresh(streak)
    assert updated.is_draft is True
    assert streak.current_streak == 1
    assert streak.total_entries == 1


def test_stale_version_is_refused_and_nothing_is_written():
    session = _session()
    user, entry = _fixtures(session)
    service = EntryService(session)
    stale = ensure_utc(entry.updated_at) - timedelta(seconds=5)

    with pytest.raises(ConcurrentModificationError):
        service.update_entry(
            entry.id,
            user.id,
            EntryUpdate(title="Second", content_delta=_delta("two\n"),
                        expected_updated_at=stale),
        )

    session.expire_all()
    unchanged = session.get(Entry, entry.id)
    assert unchanged.title == "First"
    assert unchanged.content_delta == {"ops": [{"insert": "one\n"}]}


def test_omitting_the_version_keeps_last_write_wins():
    session = _session()
    user, entry = _fixtures(session)
    service = EntryService(session)

    updated = service.update_entry(
        entry.id, user.id, EntryUpdate(title="Second", content_delta=_delta("two\n"))
    )

    assert updated.title == "Second"


def test_a_naive_timestamp_is_still_the_same_instant():
    """The column may come back naive; the client always sends an offset.

    Comparing those as strings would refuse every save. They are compared as
    instants for exactly this reason.
    """
    session = _session()
    user, entry = _fixtures(session)
    service = EntryService(session)
    naive = ensure_utc(entry.updated_at).replace(tzinfo=None)

    updated = service.update_entry(
        entry.id, user.id, EntryUpdate(title="Second", expected_updated_at=naive)
    )

    assert updated.title == "Second"


def test_the_error_carries_the_version_that_is_actually_current():
    session = _session()
    user, entry = _fixtures(session)
    service = EntryService(session)
    stale = ensure_utc(entry.updated_at) - timedelta(minutes=1)

    with pytest.raises(ConcurrentModificationError) as caught:
        service.update_entry(
            entry.id, user.id, EntryUpdate(title="x", expected_updated_at=stale)
        )

    assert caught.value.current_updated_at == ensure_utc(entry.updated_at)
