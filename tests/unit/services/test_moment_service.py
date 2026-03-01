"""
Unit tests for MomentService.
"""

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlmodel import Session, create_engine, select

from app.core.exceptions import JournalNotFoundError
from app.models.base import BaseModel
from app.models.entry import Entry
from app.models.journal import Journal
from app.models.moment import Moment, MomentMoodActivity
from app.models.user import User, UserSettings
from app.schemas.entry import EntryUpdate
from app.schemas.moment import (
    MemoriesAppliedFilter,
    MemoriesFilter,
    MomentCreate,
    MomentEntryCreate,
    MomentUpdate,
)
from app.services.moment_service import MomentService


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def test_user(test_db: Session) -> User:
    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="Test User",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_moment_service(test_db: Session) -> MomentService:
    return MomentService(session=test_db)


@pytest.fixture
def test_journal(test_db: Session, test_user: User) -> Journal:
    journal = Journal(user_id=test_user.id, title="Test Journal")
    test_db.add(journal)
    test_db.commit()
    test_db.refresh(journal)
    return journal


def test_get_moments_filter_by_mood_ids(test_db, test_user, test_moment_service):
    # Setup
    mood1_id = uuid.uuid4()
    mood2_id = uuid.uuid4()

    # Moment with mood1
    m1 = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime.utcnow(),
        primary_mood_id=mood1_id,
        note="Moment 1",
    )
    test_db.add(m1)
    test_db.commit()  # Commit to get ID

    # Link mood1
    mma1 = MomentMoodActivity(moment_id=m1.id, mood_id=mood1_id)
    test_db.add(mma1)

    # Moment with mood2
    m2 = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime.utcnow(),
        primary_mood_id=mood2_id,
        note="Moment 2",
    )
    test_db.add(m2)
    test_db.commit()

    # Link mood2
    mma2 = MomentMoodActivity(moment_id=m2.id, mood_id=mood2_id)
    test_db.add(mma2)
    test_db.commit()

    # Test filtering by mood1
    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id, mood_ids=[mood1_id]
    )
    assert len(items) == 1
    assert items[0].id == m1.id

    # Test filtering by mood1 OR mood2
    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id, mood_ids=[mood1_id, mood2_id]
    )
    assert len(items) == 2


def test_get_moments_search_note(test_db, test_user, test_moment_service):
    m1 = Moment(
        user_id=test_user.id, logged_at_utc=datetime.utcnow(), note="FoundMe in the note"
    )
    test_db.add(m1)

    m2 = Moment(user_id=test_user.id, logged_at_utc=datetime.utcnow(), note="Hidden")
    test_db.add(m2)
    test_db.commit()

    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id, search="FoundMe"
    )
    assert len(items) == 1
    assert items[0].id == m1.id


def test_get_moments_search_entry_content(test_db, test_user, test_journal, test_moment_service):
    # Moment linked to entry
    m1 = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime.utcnow(),
        note="Basic note",
    )
    test_db.add(m1)
    test_db.commit()
    test_db.refresh(m1)

    # Entry with specific content
    entry = Entry(
        user_id=test_user.id,
        journal_id=test_journal.id,
        moment_id=m1.id,
        title="Entry Title",
        content_delta={"ops": [{"insert": "SecretValue content"}]},
    )
    test_db.add(entry)
    test_db.commit()

    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id, search="SecretValue"
    )
    assert len(items) == 1
    assert items[0].id == m1.id


def test_get_moments_search_entry_title(test_db, test_user, test_journal, test_moment_service):
    m1 = Moment(user_id=test_user.id, logged_at_utc=datetime.utcnow())
    test_db.add(m1)
    test_db.commit()
    test_db.refresh(m1)

    entry = Entry(
        user_id=test_user.id,
        journal_id=test_journal.id,
        moment_id=m1.id,
        title="UniqueTitle finding",
        content_plain_text="Content",
    )
    test_db.add(entry)
    test_db.commit()

    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id, search="UniqueTitle"
    )
    assert len(items) == 1
    assert items[0].id == m1.id


def test_get_moments_filter_by_date_range(test_db, test_user, test_moment_service):
    # Old moment
    m1 = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime(2023, 1, 1, 12, 0, 0),
        logged_date_tz=date(2023, 1, 1),
        note="Old",
    )
    test_db.add(m1)

    # Middle moment
    m2 = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime(2023, 6, 15, 12, 0, 0),
        logged_date_tz=date(2023, 6, 15),
        note="Middle",
    )
    test_db.add(m2)

    # Future moment
    m3 = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime(2023, 12, 31, 12, 0, 0),
        logged_date_tz=date(2023, 12, 31),
        note="Future",
    )
    test_db.add(m3)
    test_db.commit()

    # Filter for middle range
    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id,
        start_date=date(2023, 6, 1),
        end_date=date(2023, 6, 30),
    )
    assert len(items) == 1
    assert items[0].id == m2.id

    # Filter for start date inclusive
    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id,
        start_date=date(2023, 1, 1),
    )
    assert len(items) == 3

    # Filter for end date inclusive
    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id,
        end_date=date(2023, 1, 1),
    )
    assert len(items) == 1
    assert items[0].id == m1.id


def test_get_moments_exclude_drafts_by_default(test_db, test_user, test_journal, test_moment_service):
    # Published entry
    m1 = Moment(user_id=test_user.id, logged_at_utc=datetime.utcnow())
    test_db.add(m1)
    test_db.commit()
    test_db.refresh(m1)

    entry1 = Entry(
        user_id=test_user.id,
        journal_id=test_journal.id,
        moment_id=m1.id,
        title="Published",
        is_draft=False,
    )
    test_db.add(entry1)
    test_db.commit()

    # Draft entry
    m2 = Moment(user_id=test_user.id, logged_at_utc=datetime.utcnow())
    test_db.add(m2)
    test_db.commit()
    test_db.refresh(m2)

    entry2 = Entry(
        user_id=test_user.id,
        journal_id=test_journal.id,
        moment_id=m2.id,
        title="Draft",
        is_draft=True,
    )
    test_db.add(entry2)
    test_db.commit()

    # Default should exclude drafts
    items, _, _ = test_moment_service.get_moments(user_id=test_user.id)
    assert len(items) == 1
    assert items[0].id == m1.id


def test_get_moments_include_drafts(test_db, test_user, test_journal, test_moment_service):
    m1 = Moment(user_id=test_user.id, logged_at_utc=datetime.utcnow())
    test_db.add(m1)
    test_db.commit()
    test_db.refresh(m1)

    # Draft entry
    entry = Entry(
        user_id=test_user.id,
        journal_id=test_journal.id,
        moment_id=m1.id,
        title="Draft",
        is_draft=True,
    )
    test_db.add(entry)
    test_db.commit()

    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id, include_drafts=True
    )
    assert len(items) == 1
    assert items[0].id == m1.id


def test_get_moments_standalone_always_included(test_db, test_user, test_moment_service):
    # Standalone moment (no entry)
    m1 = Moment(user_id=test_user.id, logged_at_utc=datetime.utcnow(), note="Standalone")
    test_db.add(m1)
    test_db.commit()

    # Should be included even with include_drafts=False (default)
    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id, include_drafts=False
    )
    assert len(items) == 1
    assert items[0].id == m1.id


def test_create_moment_with_invalid_inline_entry_rolls_back(
    test_db: Session, test_user: User, test_moment_service: MomentService
):
    payload = MomentCreate(
        note="Should rollback",
        entry={
            "title": "Inline entry",
            "journal_id": uuid.uuid4(),
        },
    )

    with pytest.raises(JournalNotFoundError):
        test_moment_service.create_moment(test_user.id, payload)

    remaining = test_db.exec(
        select(Moment).where(Moment.user_id == test_user.id, Moment.note == "Should rollback")
    ).all()
    assert remaining == []


def test_update_moment_allows_clearing_nullable_metadata(
    test_db: Session, test_user: User, test_moment_service: MomentService
):
    moment = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime.utcnow(),
        note="Has metadata",
        location_json={"name": "HQ", "latitude": 12.3, "longitude": 45.6},
        latitude=12.3,
        longitude=45.6,
        weather_json={"condition": "sunny"},
        weather_summary="Sunny",
        primary_mood_id=uuid.uuid4(),
    )
    test_db.add(moment)
    test_db.commit()
    test_db.refresh(moment)

    updated = test_moment_service.update_moment(
        moment.id,
        test_user.id,
        MomentUpdate(
            note=None,
            location_json=None,
            latitude=None,
            longitude=None,
            weather_json=None,
            weather_summary=None,
            primary_mood_id=None,
        ),
    )

    assert updated.note is None
    assert updated.location_json is None
    assert updated.latitude is None
    assert updated.longitude is None
    assert updated.weather_json is None
    assert updated.weather_summary is None
    assert updated.primary_mood_id is None


def test_create_moment_creates_entry(
    test_db: Session, test_user: User, test_journal: Journal, test_moment_service: MomentService
):
    """Creating a moment with 'entry' payload creates an associated Entry."""
    payload = MomentCreate(
        note="Moment with entry",
        entry=MomentEntryCreate(
            title="My Entry",
            content_delta={"ops": [{"insert": "Hello world"}]},
            journal_id=test_journal.id
        )
    )

    moment = test_moment_service.create_moment(test_user.id, payload)

    assert moment.id is not None
    assert moment.entry is not None
    assert moment.entry.title == "My Entry"
    assert moment.entry.journal_id == test_journal.id
    # Verify DB state
    db_entry = test_db.get(Entry, moment.entry.id)
    assert db_entry is not None
    assert db_entry.moment_id == moment.id


def test_update_moment_creates_entry_if_missing(
    test_db: Session, test_user: User, test_journal: Journal, test_moment_service: MomentService
):
    """Updating a moment to add an entry creates it if it didn't exist."""
    # Create standalone moment
    moment = Moment(user_id=test_user.id, logged_at_utc=datetime.utcnow(), note="Standalone")
    test_db.add(moment)
    test_db.commit()

    update_payload = MomentUpdate(
        entry_create=MomentEntryCreate(
            title="New Entry",
            content_delta={"ops": [{"insert": "New content"}]},
            journal_id=test_journal.id
        )
    )

    updated_moment = test_moment_service.update_moment(moment.id, test_user.id, update_payload)

    assert updated_moment.entry is not None
    assert updated_moment.entry.title == "New Entry"
    assert updated_moment.entry.moment_id == moment.id


def test_update_moment_updates_existing_entry(
    test_db: Session, test_user: User, test_journal: Journal, test_moment_service: MomentService
):
    """Updating a moment with existing entry updates the entry content."""
    # Create moment with entry
    moment = Moment(user_id=test_user.id, logged_at_utc=datetime.utcnow(), note="Original")
    test_db.add(moment)
    test_db.commit()
    test_db.refresh(moment)

    entry = Entry(
        user_id=test_user.id,
        journal_id=test_journal.id,
        moment_id=moment.id,
        title="Original Title",
        content_plain_text="Old content",
    )
    test_db.add(entry)
    test_db.commit()

    update_payload = MomentUpdate(
        entry_update=EntryUpdate(
            title="Updated Title"
        )
    )

    updated_moment = test_moment_service.update_moment(moment.id, test_user.id, update_payload)

    # Refresh to ensure latest state loaded
    test_db.refresh(updated_moment)
    # Access entry via relationship, assuming joinedload or lazy load works in session
    assert updated_moment.entry is not None
    assert updated_moment.entry.title == "Updated Title"
    # Verify DB
    db_entry = test_db.get(Entry, entry.id)
    assert db_entry.title == "Updated Title"


def test_get_memories_auto_prefers_last_years(
    test_db: Session,
    test_user: User,
    test_moment_service: MomentService,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_now = datetime(2026, 2, 23, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.moment_service.utc_now", lambda: fake_now)

    memory = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime(2025, 2, 23, 8, 0, 0, tzinfo=timezone.utc),
        logged_date_tz=date(2025, 2, 23),
        note="Last year memory",
    )
    test_db.add(memory)
    test_db.commit()

    items, applied_filter = test_moment_service.get_memories(
        test_user.id,
        memories_filter=MemoriesFilter.auto,
    )
    assert applied_filter == MemoriesAppliedFilter.last_years
    assert [item.id for item in items] == [memory.id]


def test_get_memories_auto_falls_back_to_last_month(
    test_db: Session,
    test_user: User,
    test_moment_service: MomentService,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_now = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.moment_service.utc_now", lambda: fake_now)

    memory = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc),
        logged_date_tz=date(2026, 2, 20),
        note="Last month memory",
    )
    test_db.add(memory)
    test_db.commit()

    items, applied_filter = test_moment_service.get_memories(
        test_user.id,
        memories_filter=MemoriesFilter.auto,
    )
    assert applied_filter == MemoriesAppliedFilter.last_month
    assert [item.id for item in items] == [memory.id]


def test_get_memories_auto_falls_back_to_last_year_and_caps_to_three(
    test_db: Session,
    test_user: User,
    test_moment_service: MomentService,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_now = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.moment_service.utc_now", lambda: fake_now)

    moments = [
        Moment(
            user_id=test_user.id,
            logged_at_utc=datetime(2025, 12, 31, 10, 0, 0, tzinfo=timezone.utc),
            logged_date_tz=date(2025, 12, 31),
            note="Last year A",
        ),
        Moment(
            user_id=test_user.id,
            logged_at_utc=datetime(2025, 9, 12, 10, 0, 0, tzinfo=timezone.utc),
            logged_date_tz=date(2025, 9, 12),
            note="Last year B",
        ),
        Moment(
            user_id=test_user.id,
            logged_at_utc=datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
            logged_date_tz=date(2025, 6, 1),
            note="Last year C",
        ),
        Moment(
            user_id=test_user.id,
            logged_at_utc=datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            logged_date_tz=date(2025, 1, 1),
            note="Last year D",
        ),
    ]
    for memory in moments:
        test_db.add(memory)
    test_db.commit()

    items, applied_filter = test_moment_service.get_memories(
        test_user.id,
        memories_filter=MemoriesFilter.auto,
        limit=20,
    )
    assert applied_filter == MemoriesAppliedFilter.last_year
    assert len(items) == 3
    assert [item.logged_date_tz for item in items] == [date(2025, 12, 31), date(2025, 9, 12), date(2025, 6, 1)]


def test_get_memories_explicit_last_year_uses_requested_limit(
    test_db: Session,
    test_user: User,
    test_moment_service: MomentService,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_now = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.moment_service.utc_now", lambda: fake_now)

    moments = [
        Moment(
            user_id=test_user.id,
            logged_at_utc=datetime(2025, 12, 31, 10, 0, 0, tzinfo=timezone.utc),
            logged_date_tz=date(2025, 12, 31),
            note="Last year A",
        ),
        Moment(
            user_id=test_user.id,
            logged_at_utc=datetime(2025, 9, 12, 10, 0, 0, tzinfo=timezone.utc),
            logged_date_tz=date(2025, 9, 12),
            note="Last year B",
        ),
        Moment(
            user_id=test_user.id,
            logged_at_utc=datetime(2025, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
            logged_date_tz=date(2025, 6, 1),
            note="Last year C",
        ),
        Moment(
            user_id=test_user.id,
            logged_at_utc=datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            logged_date_tz=date(2025, 1, 1),
            note="Last year D",
        ),
    ]
    for memory in moments:
        test_db.add(memory)
    test_db.commit()

    items, applied_filter = test_moment_service.get_memories(
        test_user.id,
        memories_filter=MemoriesFilter.last_year,
        limit=4,
    )
    assert applied_filter == MemoriesAppliedFilter.last_year
    assert len(items) == 4
    assert [item.logged_date_tz for item in items] == [
        date(2025, 12, 31),
        date(2025, 9, 12),
        date(2025, 6, 1),
        date(2025, 1, 1),
    ]


def test_get_memories_auto_falls_back_to_last_week(
    test_db: Session,
    test_user: User,
    test_moment_service: MomentService,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_now = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.moment_service.utc_now", lambda: fake_now)

    memory = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime(2026, 3, 5, 10, 0, 0, tzinfo=timezone.utc),
        logged_date_tz=date(2026, 3, 5),
        note="Last week memory",
    )
    test_db.add(memory)
    test_db.commit()

    items, applied_filter = test_moment_service.get_memories(
        test_user.id,
        memories_filter=MemoriesFilter.auto,
    )
    assert applied_filter == MemoriesAppliedFilter.last_week
    assert [item.id for item in items] == [memory.id]


def test_get_memories_excludes_draft_entries(
    test_db: Session,
    test_user: User,
    test_journal: Journal,
    test_moment_service: MomentService,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_now = datetime(2026, 2, 23, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.moment_service.utc_now", lambda: fake_now)

    draft_moment = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime(2025, 2, 23, 9, 0, 0, tzinfo=timezone.utc),
        logged_date_tz=date(2025, 2, 23),
        note="Draft memory",
    )
    published_moment = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime(2025, 2, 23, 10, 0, 0, tzinfo=timezone.utc),
        logged_date_tz=date(2025, 2, 23),
        note="Published memory",
    )
    test_db.add(draft_moment)
    test_db.add(published_moment)
    test_db.commit()
    test_db.refresh(draft_moment)
    test_db.refresh(published_moment)

    test_db.add(
        Entry(
            user_id=test_user.id,
            journal_id=test_journal.id,
            moment_id=draft_moment.id,
            title="Draft entry",
            is_draft=True,
        )
    )
    test_db.add(
        Entry(
            user_id=test_user.id,
            journal_id=test_journal.id,
            moment_id=published_moment.id,
            title="Published entry",
            is_draft=False,
        )
    )
    test_db.commit()

    items, applied_filter = test_moment_service.get_memories(
        test_user.id,
        memories_filter=MemoriesFilter.auto,
    )
    assert applied_filter == MemoriesAppliedFilter.last_years
    assert [item.id for item in items] == [published_moment.id]


def test_get_memories_invalid_timezone_falls_back_to_utc(
    test_db: Session,
    test_user: User,
    test_moment_service: MomentService,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_now = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.services.moment_service.utc_now", lambda: fake_now)

    test_db.add(UserSettings(user_id=test_user.id, time_zone="Invalid/Timezone"))

    memory = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime(2026, 3, 7, 10, 0, 0, tzinfo=timezone.utc),
        logged_date_tz=date(2026, 3, 7),
        note="UTC fallback memory",
    )
    test_db.add(memory)
    test_db.commit()

    items, applied_filter = test_moment_service.get_memories(
        test_user.id,
        memories_filter=MemoriesFilter.auto,
    )
    assert applied_filter == MemoriesAppliedFilter.last_week
    assert [item.id for item in items] == [memory.id]
