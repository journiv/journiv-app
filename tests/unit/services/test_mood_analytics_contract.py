import uuid

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app import models as _models  # noqa: F401
from app.models.base import BaseModel
from app.models.mood import Mood
from app.models.moment import Moment
from app.models.user import User
from app.services.mood_service import MoodService


def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _create_user(session: Session) -> User:
    user = User(
        email=f"mood-analytics-{uuid.uuid4().hex}@example.com",
        password="password123",
        name="Mood Analytics User",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _create_mood(session: Session, user_id: uuid.UUID, name: str) -> Mood:
    mood = Mood(
        user_id=user_id,
        name=name,
        key=f"{name.lower()}-{uuid.uuid4().hex[:6]}",
        icon=":)",
        category="neutral",
        score=3,
        position=0,
        is_active=True,
    )
    session.add(mood)
    session.commit()
    session.refresh(mood)
    return mood


def test_mood_streak_omits_last_logged_date_when_empty():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        service = MoodService(session)

        streak = service.get_mood_streak(user.id)

        assert streak["current_streak"] == 0
        assert streak["total_days_logged"] == 0
        assert "last_logged_date" not in streak


def test_mood_statistics_omits_most_frequent_mood_when_empty():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        service = MoodService(session)

        stats = service.get_mood_statistics(user.id)

        assert stats["total_logs"] == 0
        assert "most_frequent_mood" not in stats


def test_mood_streak_includes_last_logged_date_when_data_exists():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        mood = _create_mood(session, user.id, "Okay")
        session.add(
            Moment(
                user_id=user.id,
                primary_mood_id=mood.id,
                logged_timezone="UTC",
            )
        )
        session.commit()

        service = MoodService(session)
        streak = service.get_mood_streak(user.id)

        assert streak["current_streak"] >= 1
        assert streak["total_days_logged"] >= 1
        assert streak.get("last_logged_date") is not None
