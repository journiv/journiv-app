import uuid

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

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


def test_create_user_mood_reactivates_matching_inactive_mood():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        service = MoodService(session)

        original = service.create_user_mood(
            user.id,
            {
                "name": "Test",
                "score": 2,
                "icon": "cloud",
                "color_value": 0x111111,
            },
        )
        service.delete_user_mood(user.id, original)

        recreated = service.create_user_mood(
            user.id,
            {
                "name": "Test",
                "score": 5,
                "icon": "sun",
                "color_value": 0x222222,
            },
        )

        assert recreated.id == original.id
        assert recreated.is_active is True
        assert recreated.score == 5
        assert recreated.icon == "sun"
        assert recreated.color_value == 0x222222

        persisted = session.exec(
            select(Mood).where(Mood.user_id == user.id, Mood.name == "Test")
        ).all()
        assert len(persisted) == 1
        assert persisted[0].id == original.id
        assert persisted[0].is_active is True


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


def test_reorder_moods_updates_core_group_link_positions():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        mood_first = _create_mood(session, user.id, "First", 0)
        mood_second = _create_mood(session, user.id, "Second", 1)
        core_group = _create_group(session, user.id, "Core Moods", 0)
        core_group.stable_key = "moodgroup_core_moods"
        session.add(core_group)
        session.add(
            MoodGroupLink(
                mood_group_id=core_group.id,
                mood_id=mood_first.id,
                position=0,
            )
        )
        session.add(
            MoodGroupLink(
                mood_group_id=core_group.id,
                mood_id=mood_second.id,
                position=1,
            )
        )
        session.commit()

        service = MoodService(session)
        service.reorder_moods(user.id, [mood_second.id, mood_first.id])

        links = session.exec(
            select(MoodGroupLink).where(MoodGroupLink.mood_group_id == core_group.id)
        ).all()
        positions = {link.mood_id: link.position for link in links}
        assert positions[mood_second.id] == 0
        assert positions[mood_first.id] == 1
