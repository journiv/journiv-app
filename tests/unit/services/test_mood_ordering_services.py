import uuid

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app import models as _models  # noqa: F401
from app.core.exceptions import ValidationError
from app.models.base import BaseModel
from app.models.mood import Mood
from app.models.mood_group import MoodGroup, MoodGroupLink
from app.models.user import User
from app.services.mood_group_service import MoodGroupNotFoundError, MoodGroupService
from app.services.mood_service import MoodService


def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _create_user(session: Session) -> User:
    user = User(
        email=f"mood-ordering-{uuid.uuid4().hex}@example.com",
        password="password123",
        name="Ordering User",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _create_mood(session: Session, user_id: uuid.UUID, name: str, position: int) -> Mood:
    mood = Mood(
        user_id=user_id,
        name=name,
        key=f"{name.lower()}-{uuid.uuid4().hex[:6]}",
        icon=":)",
        category="neutral",
        score=3,
        position=position,
        is_active=True,
    )
    session.add(mood)
    session.commit()
    session.refresh(mood)
    return mood


def _create_group(session: Session, user_id: uuid.UUID, name: str, position: int) -> MoodGroup:
    group = MoodGroup(
        user_id=user_id,
        name=name,
        icon="group",
        position=position,
    )
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


def test_reorder_moods_rejects_duplicate_ids():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        mood = _create_mood(session, user.id, "Okay", 10)
        service = MoodService(session)

        with pytest.raises(ValidationError):
            service.reorder_moods(user.id, [mood.id, mood.id])


def test_reorder_groups_rejects_unknown_group_ids():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        _create_group(session, user.id, "Core", 0)
        service = MoodGroupService(session)

        with pytest.raises(MoodGroupNotFoundError):
            service.reorder_groups(user.id, [(uuid.uuid4(), 1)])


def test_reorder_group_moods_rejects_moods_not_in_group():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        mood_in_group = _create_mood(session, user.id, "Focus", 0)
        mood_outside_group = _create_mood(session, user.id, "Calm", 1)
        group = _create_group(session, user.id, "Daily", 0)
        session.add(
            MoodGroupLink(
                mood_group_id=group.id,
                mood_id=mood_in_group.id,
                position=0,
            )
        )
        session.commit()

        service = MoodGroupService(session)
        with pytest.raises(ValueError, match="do not belong"):
            service.reorder_group_moods(user.id, group.id, [mood_outside_group.id])
