from datetime import date
import uuid

from sqlmodel import Session, create_engine

from app.models.base import BaseModel
from app.models.entry import Entry
from app.models.journal import Journal
from app.models.user import User
from app.schemas.entry import EntryCreate
from app.core.time_utils import utc_now
from app.services.entry_service import EntryService


def _setup_session():
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    return Session(engine)


def _create_user(session: Session) -> User:
    user = User(
        email=f"draft_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="Draft User",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _create_journal(session: Session, user_id: uuid.UUID) -> Journal:
    journal = Journal(
        user_id=user_id,
        title="Draft Journal",
    )
    session.add(journal)
    session.commit()
    session.refresh(journal)
    return journal


def test_get_user_drafts_returns_only_drafts():
    session = _setup_session()
    user = _create_user(session)
    journal = _create_journal(session, user.id)
    service = EntryService(session)

    draft_entry = service.create_entry(
        user.id,
        EntryCreate(journal_id=journal.id, title="Draft"),
        is_draft=True,
    )

    published = Entry(
        user_id=user.id,
        journal_id=journal.id,
        title="Published",
        entry_date=date.today(),
        entry_timezone="UTC",
        entry_datetime_utc=utc_now(),
        is_draft=False,
    )
    session.add(published)
    session.commit()

    drafts = service.get_user_drafts(user_id=user.id, limit=10, offset=0)

    draft_ids = {entry.id for entry in drafts}
    assert draft_entry.id in draft_ids
    assert published.id not in draft_ids


def test_finalize_entry_updates_draft_flag():
    session = _setup_session()
    user = _create_user(session)
    journal = _create_journal(session, user.id)
    service = EntryService(session)

    draft_entry = service.create_entry(
        user.id,
        EntryCreate(journal_id=journal.id, title="Draft to finalize"),
        is_draft=True,
    )

    finalized = service.finalize_entry(draft_entry.id, user.id)

    assert finalized.is_draft is False
