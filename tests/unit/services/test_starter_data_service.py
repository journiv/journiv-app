import uuid

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app import models as _models  # noqa: F401
from app.core.starter_data import STARTER_ACTIVITY_GROUPS, STARTER_MOODS
from app.models.activity import Activity
from app.models.activity_group import ActivityGroup
from app.models.base import BaseModel
from app.models.goal import Goal
from app.models.goal_category import GoalCategory
from app.models.mood import Mood
from app.models.mood_group import MoodGroup, MoodGroupLink
from app.models.user import User
from app.services.starter_data_service import StarterDataService


def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _create_user(session: Session) -> User:
    user = User(
        email=f"seed-{uuid.uuid4().hex}@example.com",
        password="password123",
        name="Seed User",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_ensure_user_seeded_is_idempotent():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = _create_user(session)
        service = StarterDataService(session)

        service.ensure_user_seeded(user.id)
        first_counts = {
            "mood_groups": len(session.exec(select(MoodGroup).where(MoodGroup.user_id == user.id)).all()),
            "moods": len(session.exec(select(Mood).where(Mood.user_id == user.id)).all()),
            "mood_links": len(
                session.exec(
                    select(MoodGroupLink).join(Mood, Mood.id == MoodGroupLink.mood_id).where(
                        Mood.user_id == user.id
                    )
                ).all()
            ),
            "activity_groups": len(session.exec(select(ActivityGroup).where(ActivityGroup.user_id == user.id)).all()),
            "activities": len(session.exec(select(Activity).where(Activity.user_id == user.id)).all()),
            "goal_categories": len(
                session.exec(select(GoalCategory).where(GoalCategory.user_id == user.id)).all()
            ),
            "goals": len(session.exec(select(Goal).where(Goal.user_id == user.id)).all()),
        }

        service.ensure_user_seeded(user.id)
        second_counts = {
            "mood_groups": len(session.exec(select(MoodGroup).where(MoodGroup.user_id == user.id)).all()),
            "moods": len(session.exec(select(Mood).where(Mood.user_id == user.id)).all()),
            "mood_links": len(
                session.exec(
                    select(MoodGroupLink).join(Mood, Mood.id == MoodGroupLink.mood_id).where(
                        Mood.user_id == user.id
                    )
                ).all()
            ),
            "activity_groups": len(session.exec(select(ActivityGroup).where(ActivityGroup.user_id == user.id)).all()),
            "activities": len(session.exec(select(Activity).where(Activity.user_id == user.id)).all()),
            "goal_categories": len(
                session.exec(select(GoalCategory).where(GoalCategory.user_id == user.id)).all()
            ),
            "goals": len(session.exec(select(Goal).where(Goal.user_id == user.id)).all()),
        }

        assert first_counts == second_counts
        assert first_counts["moods"] == len(STARTER_MOODS)
        assert first_counts["activities"] == sum(len(group["activities"]) for group in STARTER_ACTIVITY_GROUPS)


def test_ensure_user_seeded_does_not_overwrite_existing_seeded_items():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = _create_user(session)
        service = StarterDataService(session)
        service.ensure_user_seeded(user.id)

        mood = session.exec(
            select(Mood).where(
                Mood.user_id == user.id,
                Mood.stable_key == "mood_good",
            )
        ).one()
        mood.name = "Great"
        session.add(mood)
        session.commit()

        service.ensure_user_seeded(user.id)
        updated = session.exec(select(Mood).where(Mood.id == mood.id)).one()
        assert updated.name == "Great"


def test_ensure_user_seeded_with_commit_false_requires_outer_commit():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = _create_user(session)
        service = StarterDataService(session)
        service.ensure_user_seeded(user.id, commit=False)
        session.rollback()

    with Session(engine) as verify_session:
        persisted_moods = verify_session.exec(select(Mood)).all()
        assert persisted_moods == []
