"""Unit tests for journal-sharing recipient lookup."""

import uuid

import pytest
from sqlmodel import Session, create_engine

from app.models.base import BaseModel
from app.models.user import User
from app.services.user_service import UserService

pytestmark = pytest.mark.unit


@pytest.fixture
def test_db() -> Session:
    """Provide an isolated database for user search behavior."""
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def _make_user(
    session: Session,
    *,
    name: str,
    email: str,
    is_active: bool = True,
) -> User:
    """Create a test user with the requested search attributes."""
    user = User(
        email=email,
        password="hashed",
        name=name,
        is_active=is_active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_search_active_users_returns_ordered_matches_without_requester(
    test_db: Session,
) -> None:
    """A recipient search must not expose the requester or inactive users."""
    requester = _make_user(
        test_db, name="Alex Owner", email="alex.owner@example.com"
    )
    alex = _make_user(test_db, name="Alex Reader", email="reader@example.com")
    email_match = _make_user(
        test_db, name="Bea Writer", email="alex.writer@example.com"
    )
    _make_user(
        test_db,
        name="Alex Inactive",
        email="inactive@example.com",
        is_active=False,
    )

    results = UserService(test_db).search_active_users(
        "ALEX", exclude_user_id=requester.id, limit=10
    )

    assert [user.id for user in results] == [alex.id, email_match.id]


def test_search_active_users_applies_limit(test_db: Session) -> None:
    """A recipient search must bound its result set before returning it."""
    requester = _make_user(
        test_db, name="Owner", email=f"owner-{uuid.uuid4().hex}@example.com"
    )
    first = _make_user(test_db, name="Ada", email="ada@example.com")
    _make_user(test_db, name="Alan", email="alan@example.com")

    results = UserService(test_db).search_active_users(
        "a", exclude_user_id=requester.id, limit=1
    )

    assert [user.id for user in results] == [first.id]


@pytest.mark.parametrize("query", ["%%", "__", r"\%", r"\_", r"\\"])
def test_search_treats_like_metacharacters_as_literals(test_db: Session, query: str) -> None:
    """Wildcard and escape characters match literal text, not arbitrary users."""
    requester = _make_user(test_db, name="Owner", email="owner@example.com")
    expected = _make_user(test_db, name=f"Match {query} person", email="match@example.com")
    _make_user(test_db, name="Other person", email="other@example.com")

    results = UserService(test_db).search_active_users(query, exclude_user_id=requester.id, limit=10)

    assert [user.id for user in results] == [expected.id]
