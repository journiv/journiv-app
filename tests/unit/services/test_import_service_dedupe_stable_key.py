import uuid
from datetime import datetime, timezone

from sqlmodel import Session, create_engine, select

from app.models.activity import Activity
from app.models.goal import Goal
from app.models.person import Person
from app.models.user import User
from app.schemas.dto import ActivityDTO, GoalDTO, ImportResultSummary, PersonDTO
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


def test_import_activities_reuses_same_name_when_external_ids_differ():
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
        assert len(persisted) == 1
        assert mapping["daylio-activity-1"] == mapping["daylio-activity-2"]

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
        assert len(persisted_after_second) == 1


def test_prepare_people_lookup_drops_exported_profile_image_path():
    engine = create_engine("sqlite:///:memory:")
    from app.models.base import BaseModel

    BaseModel.metadata.create_all(engine)
    with Session(engine) as db:
        user = _create_test_user(db)
        service = ImportService(db)
        now = datetime.now(timezone.utc)

        summary = ImportResultSummary()
        service._prepare_people_lookup(
            user_id=user.id,
            people=[
                PersonDTO(
                    name="Imported Person",
                    nickname=None,
                    note=None,
                    profile_image_path="people/source-user/source-person/profile.jpg",
                    archived_at=None,
                    created_at=now,
                    updated_at=now,
                    external_id="source-person",
                )
            ],
            summary=summary,
        )

        persisted = db.exec(select(Person).where(Person.user_id == user.id)).one()
        assert persisted.profile_image_path is None
        assert summary.people_created == 1


def test_import_goals_reuses_same_title_when_external_ids_differ():
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
        assert len(persisted) == 1
        assert mapping["daylio-goal-1"] == mapping["daylio-goal-2"]

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
        assert len(persisted_after_second) == 1


def test_import_activities_reuses_existing_starter_name_even_with_stable_key():
    engine = create_engine("sqlite:///:memory:")
    from app.models.base import BaseModel

    BaseModel.metadata.create_all(engine)
    with Session(engine) as db:
        user = _create_test_user(db)
        service = ImportService(db)
        now = datetime.now(timezone.utc)

        existing = Activity(
            user_id=user.id,
            name="Steps",
            icon="footprints",
            color="#3DBE5D",
            position=1,
            stable_key="activity_steps",
            created_at=now,
            updated_at=now,
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)

        activities = [
            ActivityDTO(
                name="Steps",
                icon="footprints",
                color="#3DBE5D",
                position=10,
                group_external_id=None,
                created_at=now,
                updated_at=now,
                external_id="import-steps-1",
            )
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
        assert len(persisted) == 1
        assert mapping["import-steps-1"] == existing.id
