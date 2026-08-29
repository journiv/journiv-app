"""
Unit tests for the admin-protection guards in UserService.

These cover the "there must always be at least one admin who can sign in"
invariant across deletion, demotion and deactivation, including the case where
a stale deactivated admin row must not count towards the quota.
"""

import uuid

import pytest
from sqlmodel import Session, create_engine

from app.models.base import BaseModel
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import AdminUserUpdate
from app.services.user_service import UserService

pytestmark = pytest.mark.unit


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _make_user(
    session: Session,
    *,
    role: UserRole = UserRole.USER,
    is_active: bool = True,
) -> User:
    user = User(
        email=f"user_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed",
        name="Test User",
        role=role,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_count_admin_users_can_exclude_deactivated(test_db: Session):
    service = UserService(test_db)
    _make_user(test_db, role=UserRole.ADMIN, is_active=True)
    _make_user(test_db, role=UserRole.ADMIN, is_active=False)
    _make_user(test_db, role=UserRole.USER, is_active=True)

    assert service.count_admin_users() == 2
    assert service.count_admin_users(active_only=True) == 1


def test_cannot_deactivate_last_active_admin(test_db: Session):
    service = UserService(test_db)
    admin = _make_user(test_db, role=UserRole.ADMIN, is_active=True)

    can_change, message = service.can_change_active_status(str(admin.id), False)

    assert can_change is False
    assert "last admin" in message.lower()


def test_can_deactivate_admin_when_another_active_admin_exists(test_db: Session):
    service = UserService(test_db)
    admin_a = _make_user(test_db, role=UserRole.ADMIN, is_active=True)
    _make_user(test_db, role=UserRole.ADMIN, is_active=True)

    can_change, message = service.can_change_active_status(str(admin_a.id), False)

    assert can_change is True
    assert message is None


def test_deactivating_regular_user_is_always_allowed(test_db: Session):
    service = UserService(test_db)
    _make_user(test_db, role=UserRole.ADMIN, is_active=True)
    member = _make_user(test_db, role=UserRole.USER, is_active=True)

    can_change, _ = service.can_change_active_status(str(member.id), False)

    assert can_change is True


def test_reactivating_an_admin_is_allowed(test_db: Session):
    service = UserService(test_db)
    admin = _make_user(test_db, role=UserRole.ADMIN, is_active=False)

    can_change, _ = service.can_change_active_status(str(admin.id), True)

    assert can_change is True


def test_deactivated_admin_does_not_shield_the_last_active_admin(test_db: Session):
    """A stale deactivated admin row must not satisfy the delete/demote quota."""
    service = UserService(test_db)
    active_admin = _make_user(test_db, role=UserRole.ADMIN, is_active=True)
    _make_user(test_db, role=UserRole.ADMIN, is_active=False)

    can_delete, delete_msg = service.can_delete_user(str(active_admin.id))
    can_demote, demote_msg = service.can_update_user_role(
        str(active_admin.id), UserRole.USER
    )

    assert can_delete is False
    assert "active admin" in delete_msg.lower()
    assert can_demote is False
    assert "active admin" in demote_msg.lower()


def test_update_user_as_admin_refuses_deactivating_last_admin(test_db: Session):
    service = UserService(test_db)
    admin = _make_user(test_db, role=UserRole.ADMIN, is_active=True)

    with pytest.raises(ValueError, match="last admin"):
        service.update_user_as_admin(
            str(admin.id), AdminUserUpdate(is_active=False)
        )

    test_db.refresh(admin)
    assert admin.is_active is True
