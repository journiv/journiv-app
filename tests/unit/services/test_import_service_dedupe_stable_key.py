import io
import uuid
from datetime import datetime, timezone

from PIL import Image
from sqlmodel import Session, create_engine, select

from app.models.activity import Activity
from app.models.enums import ExportType
from app.models.goal import Goal
from app.models.person import Person
from app.models.person_group import PersonGroup
from app.models.person_group_link import PersonGroupLink
from app.models.user import User
from app.schemas.dto import (
    ActivityDTO,
    GoalDTO,
    ImportResultSummary,
    PersonDTO,
    PersonGroupDTO,
)
from app.services.export_service import ExportService
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


def _valid_profile_jpeg_bytes() -> bytes:
    image = Image.new("RGB", (1, 1), color=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


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


def test_export_collects_person_profile_image(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.export_service.settings.media_root", str(tmp_path))
    engine = create_engine("sqlite:///:memory:")
    from app.models.base import BaseModel

    BaseModel.metadata.create_all(engine)
    with Session(engine) as db:
        user = _create_test_user(db)
        now = datetime.now(timezone.utc)
        person = Person(
            user_id=user.id,
            name="Exported Person",
            normalized_name="exported person",
            created_at=now,
            updated_at=now,
        )
        group = PersonGroup(
            user_id=user.id,
            name="Family",
            color_value=123,
            icon="users",
            position=10,
            created_at=now,
            updated_at=now,
        )
        db.add(person)
        db.add(group)
        db.commit()
        db.refresh(person)
        db.refresh(group)
        db.add(PersonGroupLink(person_id=person.id, person_group_id=group.id))
        db.commit()

        profile_path = f"people/{user.id}/{person.id}/profile.jpg"
        absolute_profile_path = tmp_path / profile_path
        absolute_profile_path.parent.mkdir(parents=True)
        absolute_profile_path.write_bytes(_valid_profile_jpeg_bytes())
        person.profile_image_path = profile_path
        db.add(person)
        db.commit()

        service = ExportService(db)
        export_data = service.build_export_data(
            user_id=user.id,
            export_type=ExportType.FULL,
            include_media=True,
        )

        assert export_data.people[0].profile_image_path == f"people/{person.id}/profile.jpg"
        assert export_data.person_groups[0].external_id == str(group.id)
        assert export_data.people[0].person_group_external_ids == [str(group.id)]
        media_files = service._collect_media_files(export_data, user.id)
        assert media_files[export_data.people[0].profile_image_path] == absolute_profile_path


def test_prepare_people_lookup_imports_exported_profile_image_path(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.person_service.settings.media_root", str(tmp_path / "stored"))
    engine = create_engine("sqlite:///:memory:")
    from app.models.base import BaseModel

    BaseModel.metadata.create_all(engine)
    with Session(engine) as db:
        user = _create_test_user(db)
        service = ImportService(db)
        now = datetime.now(timezone.utc)
        media_dir = tmp_path / "extracted" / "media"
        source_profile = media_dir / "people" / "source-person" / "profile.jpg"
        source_profile.parent.mkdir(parents=True)
        source_profile.write_bytes(_valid_profile_jpeg_bytes())

        summary = ImportResultSummary()
        service._prepare_people_lookup(
            user_id=user.id,
            people=[
                PersonDTO(
                    name="Imported Person",
                    nickname=None,
                    note=None,
                    profile_image_path="people/source-person/profile.jpg",
                    archived_at=None,
                    created_at=now,
                    updated_at=now,
                    external_id="source-person",
                )
            ],
            media_dir=media_dir,
            person_group_id_map={},
            summary=summary,
        )

        persisted = db.exec(select(Person).where(Person.user_id == user.id)).one()
        assert persisted.profile_image_path == f"people/{user.id}/{persisted.id}/profile.jpg"
        assert (tmp_path / "stored" / persisted.profile_image_path).exists()
        assert summary.people_created == 1


def test_import_person_groups_links_imported_people():
    engine = create_engine("sqlite:///:memory:")
    from app.models.base import BaseModel

    BaseModel.metadata.create_all(engine)
    with Session(engine) as db:
        user = _create_test_user(db)
        service = ImportService(db)
        now = datetime.now(timezone.utc)
        summary = ImportResultSummary()

        group_map = service._import_person_groups(
            user_id=user.id,
            person_groups=[
                PersonGroupDTO(
                    name="Family",
                    color_value=123,
                    icon="users",
                    position=10,
                    created_at=now,
                    updated_at=now,
                    external_id="source-group",
                )
            ],
            summary=summary,
            record_mapping=lambda *args, **kwargs: None,
        )
        service._prepare_people_lookup(
            user_id=user.id,
            people=[
                PersonDTO(
                    name="Imported Person",
                    nickname=None,
                    note=None,
                    profile_image_path=None,
                    person_group_external_ids=["source-group"],
                    archived_at=None,
                    created_at=now,
                    updated_at=now,
                    external_id="source-person",
                )
            ],
            media_dir=None,
            person_group_id_map=group_map,
            summary=summary,
        )

        group = db.exec(select(PersonGroup).where(PersonGroup.user_id == user.id)).one()
        person = db.exec(select(Person).where(Person.user_id == user.id)).one()
        link = db.exec(
            select(PersonGroupLink).where(
                PersonGroupLink.person_id == person.id,
                PersonGroupLink.person_group_id == group.id,
            )
        ).one()
        assert group.name == "Family"
        assert link.person_id == person.id
        assert summary.person_groups_created == 1
        assert summary.people_created == 1


def test_prepare_people_lookup_reactivates_archived_name_match_for_active_import():
    engine = create_engine("sqlite:///:memory:")
    from app.models.base import BaseModel

    BaseModel.metadata.create_all(engine)
    with Session(engine) as db:
        user = _create_test_user(db)
        now = datetime.now(timezone.utc)
        archived_person = Person(
            user_id=user.id,
            name="Imported Person",
            normalized_name="imported person",
            archived_at=now,
        )
        db.add(archived_person)
        db.commit()
        db.refresh(archived_person)

        service = ImportService(db)
        summary = ImportResultSummary()
        external_id_map, _name_map = service._prepare_people_lookup(
            user_id=user.id,
            people=[
                PersonDTO(
                    name="Imported Person",
                    nickname="Imp",
                    note="Active again",
                    profile_image_path=None,
                    archived_at=None,
                    created_at=now,
                    updated_at=now,
                    external_id="source-person",
                )
            ],
            media_dir=None,
            person_group_id_map={},
            summary=summary,
        )

        db.refresh(archived_person)
        assert external_id_map["source-person"] == archived_person.id
        assert archived_person.archived_at is None
        assert archived_person.nickname == "Imp"
        assert archived_person.note == "Active again"
        assert summary.people_reused == 1
        assert summary.people_created == 0


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
