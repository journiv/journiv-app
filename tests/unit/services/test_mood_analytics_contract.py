import uuid
from datetime import date, timedelta

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app import models as _models  # noqa: F401
from app.models.base import BaseModel
from app.models.moment import Moment, MomentMoodActivity
from app.models.mood import Mood
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


def _create_mood(
    session: Session,
    user_id: uuid.UUID,
    name: str,
    category: str = "neutral",
    *,
    is_active: bool = True,
) -> Mood:
    mood = Mood(
        user_id=user_id,
        name=name,
        key=f"{name.lower()}-{uuid.uuid4().hex[:6]}",
        icon=":)",
        category=category,
        score=3,
        position=0,
        is_active=is_active,
    )
    session.add(mood)
    session.commit()
    session.refresh(mood)
    return mood


def _log_moment(
    session: Session,
    user_id: uuid.UUID,
    *,
    on: date,
    primary_mood_id: uuid.UUID | None,
) -> Moment:
    """A moment as the journal editor writes it: mood carried only by
    ``primary_mood_id``, never a ``moment_mood_activity`` row."""
    moment = Moment(
        user_id=user_id,
        primary_mood_id=primary_mood_id,
        logged_timezone="UTC",
        logged_date_tz=on,
    )
    session.add(moment)
    session.commit()
    session.refresh(moment)
    return moment


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


def test_mood_statistics_counts_primary_mood_only_moments():
    """Regression: an entry whose mood is set the normal way (only
    ``primary_mood_id``, no link row) must show up in every section of the
    statistics payload."""
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        happy = _create_mood(session, user.id, "Happy", "positive")
        low = _create_mood(session, user.id, "Low", "negative")

        end = date(2026, 3, 17)
        # Three positive logs, one negative — spread across three days.
        _log_moment(session, user.id, on=end - timedelta(days=1), primary_mood_id=happy.id)
        _log_moment(session, user.id, on=end - timedelta(days=1), primary_mood_id=happy.id)
        _log_moment(session, user.id, on=end - timedelta(days=5), primary_mood_id=happy.id)
        _log_moment(session, user.id, on=end - timedelta(days=8), primary_mood_id=low.id)

        stats = MoodService(session).get_mood_statistics(
            user.id, start_date=end - timedelta(days=30), end_date=end
        )

        assert stats["total_logs"] == 4

        assert stats["mood_distribution"] == {"positive": 75.0, "negative": 25.0}

        counts = {row["mood"]: row for row in stats["mood_counts"]}
        assert counts["Happy"]["count"] == 3
        assert counts["Happy"]["category"] == "positive"
        assert counts["Low"]["count"] == 1

        assert stats["most_frequent_mood"] == {
            "name": "Happy",
            "category": "positive",
            "count": 3,
        }

        trend = {(row["date"], row["category"]): row["count"] for row in stats["daily_trends"]}
        assert trend[(str(end - timedelta(days=1)), "positive")] == 2
        assert trend[(str(end - timedelta(days=5)), "positive")] == 1
        assert trend[(str(end - timedelta(days=8)), "negative")] == 1


def test_mood_statistics_excludes_moments_without_a_primary_mood():
    """Moments with a NULL ``primary_mood_id`` (a note, a photo, an
    activity-only quick log) contribute nothing to the statistics."""
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        happy = _create_mood(session, user.id, "Happy", "positive")
        end = date(2026, 3, 17)

        _log_moment(session, user.id, on=end, primary_mood_id=happy.id)
        moodless = _log_moment(session, user.id, on=end, primary_mood_id=None)
        # A secondary mood carried only as a link row is the multi-mood path,
        # not a primary mood — it must not leak into the statistics either.
        session.add(MomentMoodActivity(moment_id=moodless.id, mood_id=happy.id))
        session.commit()

        stats = MoodService(session).get_mood_statistics(
            user.id, start_date=end - timedelta(days=30), end_date=end
        )

        assert stats["total_logs"] == 1
        assert stats["mood_counts"] == [
            {"mood": "Happy", "category": "positive", "count": 1}
        ]


def test_mood_statistics_windows_on_the_date_range():
    """Only moments inside the inclusive ``[start_date, end_date]`` window count."""
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        happy = _create_mood(session, user.id, "Happy", "positive")
        end = date(2026, 3, 17)
        start = end - timedelta(days=7)

        _log_moment(session, user.id, on=start, primary_mood_id=happy.id)  # on the edge
        _log_moment(session, user.id, on=end, primary_mood_id=happy.id)  # on the edge
        _log_moment(session, user.id, on=start - timedelta(days=1), primary_mood_id=happy.id)
        _log_moment(session, user.id, on=end + timedelta(days=1), primary_mood_id=happy.id)

        stats = MoodService(session).get_mood_statistics(
            user.id, start_date=start, end_date=end
        )

        assert stats["total_logs"] == 2


def test_mood_statistics_ignores_inactive_moods():
    """A soft-deleted mood is excluded consistently from every statistic."""
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        active = _create_mood(session, user.id, "Happy", "positive")
        retired = _create_mood(session, user.id, "Old", "neutral", is_active=False)
        end = date(2026, 3, 17)

        _log_moment(session, user.id, on=end, primary_mood_id=active.id)
        _log_moment(session, user.id, on=end, primary_mood_id=retired.id)

        stats = MoodService(session).get_mood_statistics(
            user.id, start_date=end - timedelta(days=30), end_date=end
        )

        assert stats["total_logs"] == 1
        assert [row["mood"] for row in stats["mood_counts"]] == ["Happy"]
        assert stats["daily_trends"] == [
            {"date": str(end), "category": "positive", "count": 1}
        ]
