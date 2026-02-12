"""
Unit tests for MomentService.
"""

import uuid
from datetime import date, datetime

import pytest
from sqlmodel import Session, create_engine

from app.models.base import BaseModel
from app.models.entry import Entry
from app.models.journal import Journal
from app.models.moment import Moment, MomentMoodActivity
from app.models.user import User
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


def test_get_moments_filter_by_mood_ids(test_db, test_user, test_moment_service):
    # Setup
    mood1_id = uuid.uuid4()
    mood2_id = uuid.uuid4()

    # Moment with mood1
    m1 = Moment(
        user_id=test_user.id,
        logged_at=datetime.utcnow(),
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
        logged_at=datetime.utcnow(),
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
        user_id=test_user.id, logged_at=datetime.utcnow(), note="FoundMe in the note"
    )
    test_db.add(m1)

    m2 = Moment(user_id=test_user.id, logged_at=datetime.utcnow(), note="Hidden")
    test_db.add(m2)
    test_db.commit()

    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id, search="FoundMe"
    )
    assert len(items) == 1
    assert items[0].id == m1.id


def test_get_moments_search_entry_content(test_db, test_user, test_moment_service):
    # Entry with specific content
    entry = Entry(
        user_id=test_user.id,
        journal_id=uuid.uuid4(),  # Mock journal ID
        entry_date=date.today(),
        title="Entry Title",
        content_delta={"ops": [{"insert": "SecretValue content"}]},
    )
    test_db.add(entry)
    test_db.commit()

    # Moment linked to entry
    m1 = Moment(
        user_id=test_user.id,
        logged_at=datetime.utcnow(),
        entry_id=entry.id,
        note="Basic note",
    )
    test_db.add(m1)
    test_db.commit()

    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id, search="SecretValue"
    )
    assert len(items) == 1
    assert items[0].id == m1.id


def test_get_moments_search_entry_title(test_db, test_user, test_moment_service):
    entry = Entry(
        user_id=test_user.id,
        journal_id=uuid.uuid4(),
        entry_date=date.today(),
        title="UniqueTitle finding",
        content_plain_text="Content",
    )
    test_db.add(entry)
    test_db.commit()

    m1 = Moment(user_id=test_user.id, logged_at=datetime.utcnow(), entry_id=entry.id)
    test_db.add(m1)
    test_db.commit()

    items, _, _ = test_moment_service.get_moments(
        user_id=test_user.id, search="UniqueTitle"
    )
    assert len(items) == 1
    assert items[0].id == m1.id
