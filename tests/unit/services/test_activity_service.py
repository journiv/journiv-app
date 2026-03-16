import uuid
from datetime import date

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app import models as _models  # noqa: F401
from app.models.activity import Activity
from app.models.base import BaseModel
from app.models.moment import Moment, MomentMoodActivity
from app.models.user import User
from app.schemas.activity import ActivityCreate
from app.services.activity_service import ActivityService


def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _create_user(session: Session) -> User:
    user = User(
        email=f"activity-{uuid.uuid4().hex}@example.com",
        password="password123",
        name="Activity User",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_delete_activity_soft_deletes_and_preserves_historical_links():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        service = ActivityService(session)
        activity = service.create_activity(
            user.id,
            ActivityCreate(name="Run", icon="run", color="#111111"),
        )

        moment = Moment(
            user_id=user.id,
            logged_date_tz=date.today(),
            logged_timezone="UTC",
        )
        session.add(moment)
        session.commit()
        session.refresh(moment)

        link = MomentMoodActivity(moment_id=moment.id, activity_id=activity.id)
        session.add(link)
        session.commit()

        service.delete_activity(activity.id, user.id)

        persisted_activity = session.exec(
            select(Activity).where(Activity.id == activity.id)
        ).first()
        persisted_link = session.exec(
            select(MomentMoodActivity).where(MomentMoodActivity.activity_id == activity.id)
        ).first()

        assert persisted_activity is not None
        assert persisted_activity.is_active is False
        assert persisted_link is not None
        assert service.get_user_activities(user.id) == []


def test_create_activity_reactivates_matching_inactive_row():
    engine = _make_engine()
    BaseModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = _create_user(session)
        service = ActivityService(session)

        original = service.create_activity(
            user.id,
            ActivityCreate(name="Read", icon="book", color="#123456"),
        )
        service.delete_activity(original.id, user.id)

        recreated = service.create_activity(
            user.id,
            ActivityCreate(name="Read", icon="book-open", color="#654321"),
        )

        persisted = session.exec(
            select(Activity).where(Activity.user_id == user.id, Activity.name == "Read")
        ).all()

        assert recreated.id == original.id
        assert recreated.is_active is True
        assert recreated.icon == "book-open"
        assert recreated.color == "#654321"
        assert len(persisted) == 1
        assert persisted[0].id == original.id
        assert persisted[0].is_active is True
