"""
Unit tests for PersonGroupService.
"""

import uuid

import pytest
from sqlmodel import Session, create_engine, select

from app.models.base import BaseModel
from app.models.person_group import PersonGroup
from app.models.user import User
from app.schemas.person import PersonGroupCreate, PersonGroupUpdate
from app.services.person_group_service import (
    PersonGroupNotFoundError,
    PersonGroupService,
)


def _create_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    return Session(engine)


def _create_user(session: Session) -> User:
    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="Test User",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_person_group_crud_and_reorder():
    session = _create_session()
    try:
        user = _create_user(session)
        service = PersonGroupService(session)

        family = service.create_group(user.id, PersonGroupCreate(name="Family"))
        friends = service.create_group(user.id, PersonGroupCreate(name="Friends"))

        groups = service.get_user_groups(user.id)
        assert {group.id for group in groups} == {family.id, friends.id}

        updated = service.update_group(
            family.id,
            user.id,
            PersonGroupUpdate(name="Close Family", position=50),
        )
        assert updated.name == "Close Family"
        assert updated.position == 50

        service.reorder_groups(
            user.id,
            [
                (friends.id, 10),
                (family.id, 20),
            ],
        )
        ordered = session.exec(
            select(PersonGroup)
            .where(PersonGroup.user_id == user.id)
            .order_by(PersonGroup.position, PersonGroup.name)
        ).all()
        assert [group.id for group in ordered] == [friends.id, family.id]

        service.delete_group(friends.id, user.id)
        remaining = service.get_user_groups(user.id)
        assert {group.id for group in remaining} == {family.id}
    finally:
        session.close()


def test_update_nonexistent_group_raises():
    session = _create_session()
    try:
        user = _create_user(session)
        service = PersonGroupService(session)

        missing_group_id = uuid.uuid4()
        with pytest.raises(PersonGroupNotFoundError):
            service.update_group(missing_group_id, user.id, PersonGroupUpdate(name="Missing"))
    finally:
        session.close()


def test_group_name_is_trimmed_on_create_and_update():
    session = _create_session()
    try:
        user = _create_user(session)
        service = PersonGroupService(session)

        created = service.create_group(user.id, PersonGroupCreate(name="  Family  "))
        assert created.name == "Family"

        updated = service.update_group(
            created.id,
            user.id,
            PersonGroupUpdate(name="  Close Family  "),
        )
        assert updated.name == "Close Family"
    finally:
        session.close()


def test_reorder_groups_raises_for_unknown_group_id():
    session = _create_session()
    try:
        user = _create_user(session)
        service = PersonGroupService(session)
        created = service.create_group(user.id, PersonGroupCreate(name="Friends"))
        original_position = created.position

        with pytest.raises(PersonGroupNotFoundError, match="not found"):
            service.reorder_groups(
                user.id,
                [
                    (created.id, 10),
                    (uuid.uuid4(), 20),
                ],
            )

        created_after = session.exec(
            select(PersonGroup).where(PersonGroup.id == created.id)
        ).first()
        assert created_after is not None
        assert created_after.position == original_position
    finally:
        session.close()
