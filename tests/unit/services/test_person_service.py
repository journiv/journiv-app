"""
Unit tests for PersonService.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlmodel import Session, create_engine, select

from app.core.config import settings
from app.models.base import BaseModel
from app.models.moment import Moment
from app.models.moment_person_link import MomentPersonLink
from app.models.person_group import PersonGroup
from app.models.person_group_link import PersonGroupLink
from app.models.user import User
from app.schemas.person import PersonCreate, PersonUpdate
from app.services.person_service import PersonService


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


@pytest.fixture
def test_user(test_db: Session) -> User:
    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="Test User",
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def person_service(test_db: Session) -> PersonService:
    return PersonService(test_db)


@pytest.fixture
def test_moment(test_db: Session, test_user: User) -> Moment:
    moment = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime.now(UTC),
        logged_date_tz=datetime.now(UTC).date(),
        note="Test moment",
    )
    test_db.add(moment)
    test_db.commit()
    test_db.refresh(moment)
    return moment


def test_create_person_normalizes_name_and_prevents_duplicates(
    person_service: PersonService, test_user: User
):
    created = person_service.create_person(
        test_user.id,
        PersonCreate(name="  Alice   Smith "),
    )
    assert created.name == "Alice Smith"

    with pytest.raises(ValueError, match="already exists"):
        person_service.create_person(
            test_user.id,
            PersonCreate(name="alice smith"),
        )


def test_archive_and_restore_person(person_service: PersonService, test_user: User):
    created = person_service.create_person(test_user.id, PersonCreate(name="Bob"))

    person_service.archive_person(test_user.id, created.id)
    active_people = person_service.list_people(test_user.id)
    assert all(person.id != created.id for person in active_people)

    including_archived = person_service.list_people(test_user.id, include_archived=True)
    archived = next(person for person in including_archived if person.id == created.id)
    assert archived.archived_at is not None

    restored = person_service.restore_person(test_user.id, created.id)
    assert restored.archived_at is None

    active_after_restore = person_service.list_people(test_user.id)
    assert any(person.id == created.id for person in active_after_restore)


def test_update_person_fields(person_service: PersonService, test_user: User):
    friends_group = PersonGroup(user_id=test_user.id, name="Friends", position=10)
    family_group = PersonGroup(user_id=test_user.id, name="Family", position=20)
    person_service.session.add(friends_group)
    person_service.session.add(family_group)
    person_service.session.commit()
    person_service.session.refresh(friends_group)
    person_service.session.refresh(family_group)

    created = person_service.create_person(test_user.id, PersonCreate(name="Carol"))

    updated = person_service.update_person(
        test_user.id,
        created.id,
        PersonUpdate(
            name="Carol Jones",
            nickname="CJ",
            note="Friend",
            group_ids=[friends_group.id, family_group.id],
        ),
    )
    assert updated.name == "Carol Jones"
    assert updated.nickname == "CJ"
    assert updated.note == "Friend"
    assert updated.profile_image_url is None
    assert {group.id for group in updated.groups} == {friends_group.id, family_group.id}


def test_upload_profile_image_restores_existing_file_when_commit_fails(
    person_service: PersonService,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
):
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    created = person_service.create_person(test_user.id, PersonCreate(name="Carol Photo"))
    person = person_service._get_owned_person(test_user.id, created.id)
    original_path = PersonService._write_profile_image(
        user_id=test_user.id,
        person_id=created.id,
        image_bytes=b"original-image",
        extension=".jpg",
    )
    person.profile_image_path = original_path
    person_service.session.add(person)
    person_service.session.commit()

    target_path = PersonService._profile_image_absolute_path(original_path)
    monkeypatch.setattr(
        PersonService,
        "_validate_profile_image_bytes",
        classmethod(lambda cls, _image_bytes: (".jpg", (1, 1))),
    )
    monkeypatch.setattr(
        person_service,
        "_commit",
        lambda: (_ for _ in ()).throw(RuntimeError("commit failed")),
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        person_service.upload_profile_image(test_user.id, created.id, b"new-image")

    assert target_path.read_bytes() == b"original-image"


def test_create_and_replace_person_groups(person_service: PersonService, test_user: User):
    friends_group = PersonGroup(user_id=test_user.id, name="Friends", position=10)
    family_group = PersonGroup(user_id=test_user.id, name="Family", position=20)
    person_service.session.add(friends_group)
    person_service.session.add(family_group)
    person_service.session.commit()
    person_service.session.refresh(friends_group)
    person_service.session.refresh(family_group)

    created = person_service.create_person(
        test_user.id,
        PersonCreate(name="Dana", group_ids=[friends_group.id]),
    )
    assert {group.id for group in created.groups} == {friends_group.id}

    updated = person_service.update_person(
        test_user.id,
        created.id,
        PersonUpdate(group_ids=[family_group.id]),
    )
    assert {group.id for group in updated.groups} == {family_group.id}

    links = person_service.session.exec(
        select(PersonGroupLink).where(PersonGroupLink.person_id == created.id)
    ).all()
    assert len(links) == 1
    assert links[0].person_group_id == family_group.id


def test_replace_moment_people_is_idempotent(
    test_db: Session,
    person_service: PersonService,
    test_user: User,
    test_moment: Moment,
):
    p1 = person_service.create_person(test_user.id, PersonCreate(name="Alice"))
    p2 = person_service.create_person(test_user.id, PersonCreate(name="Bob"))

    person_service.replace_moment_people(test_moment.id, [p1.id, p2.id], test_user.id)
    person_service.replace_moment_people(test_moment.id, [p1.id, p2.id], test_user.id)

    links = test_db.exec(
        select(MomentPersonLink).where(MomentPersonLink.moment_id == test_moment.id)
    ).all()
    assert len(links) == 2

    removed = person_service.remove_person_from_moment(test_moment.id, p1.id, test_user.id)
    assert removed is True
    removed_again = person_service.remove_person_from_moment(test_moment.id, p1.id, test_user.id)
    assert removed_again is False


def test_merge_people_moves_links_and_archives_source(
    test_db: Session,
    person_service: PersonService,
    test_user: User,
):
    source_group = PersonGroup(user_id=test_user.id, name="Source Group", position=10)
    target_group = PersonGroup(user_id=test_user.id, name="Target Group", position=20)
    test_db.add(source_group)
    test_db.add(target_group)

    moment_one = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime.now(UTC),
        logged_date_tz=datetime.now(UTC).date(),
        note="One",
    )
    moment_two = Moment(
        user_id=test_user.id,
        logged_at_utc=datetime.now(UTC),
        logged_date_tz=datetime.now(UTC).date(),
        note="Two",
    )
    test_db.add(moment_one)
    test_db.add(moment_two)
    test_db.commit()
    test_db.refresh(moment_one)
    test_db.refresh(moment_two)
    test_db.refresh(source_group)
    test_db.refresh(target_group)

    source = person_service.create_person(test_user.id, PersonCreate(name="Source Person"))
    target = person_service.create_person(
        test_user.id,
        PersonCreate(name="Target Person", group_ids=[target_group.id]),
    )

    person_service.update_person(
        test_user.id,
        source.id,
        PersonUpdate(group_ids=[source_group.id]),
    )

    person_service.replace_moment_people(moment_one.id, [source.id], test_user.id)
    person_service.replace_moment_people(moment_two.id, [source.id, target.id], test_user.id)

    merged = person_service.merge_people(test_user.id, source.id, target.id)
    assert merged.id == target.id

    source_after = person_service.get_person(test_user.id, source.id, include_archived=True)
    assert source_after.archived_at is not None

    links_for_source = test_db.exec(
        select(MomentPersonLink).where(MomentPersonLink.person_id == source.id)
    ).all()
    assert links_for_source == []

    links_for_target = test_db.exec(
        select(MomentPersonLink).where(MomentPersonLink.person_id == target.id)
    ).all()
    assert {link.moment_id for link in links_for_target} == {moment_one.id, moment_two.id}

    target_after = person_service.get_person(test_user.id, target.id, include_archived=True)
    assert {group.id for group in target_after.groups} == {source_group.id, target_group.id}
