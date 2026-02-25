from datetime import datetime, timezone
import uuid

from sqlmodel import Session, create_engine, select

from app.models.activity import Activity
from app.models.goal import Goal
from app.models.user import User
from app.schemas.dto import ActivityDTO, GoalDTO, ImportResultSummary
from app.services.import_service import ImportService


def _create_test_user(db: Session) -> User:
    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="Test User",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_import_activities_keeps_distinct_same_name_when_external_ids_differ():
    engine = create_engine("sqlite:///:memory:")
    from app.models.base import BaseModel

    BaseModel.metadata.create_all(engine)
    with Session(engine) as db:
        user = _create_test_user(db)
        service = ImportService(db)
        now = datetime.now(timezone.utc)

        activities = [
            ActivityDTO(
                name="Exercise",
                icon=None,
                color=None,
                position=0,
                group_external_id=None,
                created_at=now,
                updated_at=now,
                external_id="daylio-activity-1",
            ),
            ActivityDTO(
                name="Exercise",
                icon=None,
                color=None,
                position=1,
                group_external_id=None,
                created_at=now,
                updated_at=now,
                external_id="daylio-activity-2",
            ),
        ]

        summary = ImportResultSummary()
        mapping = service._import_activities(
            user_id=user.id,
            activities=activities,
            activity_group_id_map={},
            summary=summary,
            record_mapping=lambda *args, **kwargs: None,
        )

        persisted = db.exec(select(Activity).where(Activity.user_id == user.id)).all()
        assert len(persisted) == 2
        assert mapping["daylio-activity-1"] != mapping["daylio-activity-2"]

        # Re-import should be idempotent through stable keys.
        summary_second = ImportResultSummary()
        service._import_activities(
            user_id=user.id,
            activities=activities,
            activity_group_id_map={},
            summary=summary_second,
            record_mapping=lambda *args, **kwargs: None,
        )
        persisted_after_second = db.exec(select(Activity).where(Activity.user_id == user.id)).all()
        assert len(persisted_after_second) == 2


def test_import_goals_keeps_distinct_same_title_when_external_ids_differ():
    engine = create_engine("sqlite:///:memory:")
    from app.models.base import BaseModel

    BaseModel.metadata.create_all(engine)
    with Session(engine) as db:
        user = _create_test_user(db)
        service = ImportService(db)
        now = datetime.now(timezone.utc)

        goals = [
            GoalDTO(
                title="Hydrate",
                created_at=now,
                updated_at=now,
                external_id="daylio-goal-1",
            ),
            GoalDTO(
                title="Hydrate",
                created_at=now,
                updated_at=now,
                external_id="daylio-goal-2",
            ),
        ]

        summary = ImportResultSummary()
        mapping = service._import_goals(
            user_id=user.id,
            goals=goals,
            activity_id_map={},
            goal_category_id_map={},
            summary=summary,
            record_mapping=lambda *args, **kwargs: None,
        )

        persisted = db.exec(select(Goal).where(Goal.user_id == user.id)).all()
        assert len(persisted) == 2
        assert mapping["daylio-goal-1"] != mapping["daylio-goal-2"]

        # Re-import should be idempotent through stable keys.
        summary_second = ImportResultSummary()
        service._import_goals(
            user_id=user.id,
            goals=goals,
            activity_id_map={},
            goal_category_id_map={},
            summary=summary_second,
            record_mapping=lambda *args, **kwargs: None,
        )
        persisted_after_second = db.exec(select(Goal).where(Goal.user_id == user.id)).all()
        assert len(persisted_after_second) == 2
