"""
Unit tests for moment endpoint response builders.
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Session, create_engine

from app.api.v1.endpoints.moments import _build_moment_response
from app.models.base import BaseModel
from app.models.moment import Moment
from app.models.moment_person_link import MomentPersonLink
from app.models.moment_tag_link import MomentTagLink
from app.models.person import Person
from app.models.tag import Tag
from app.models.user import User


def test_build_moment_response_includes_tags() -> None:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)

    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="Test User",
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    moment = Moment(
        user_id=user.id,
        logged_at_utc=datetime.now(UTC),
        logged_date_tz=datetime.now(UTC).date(),
        note="Tagged moment",
    )
    session.add(moment)
    session.commit()
    session.refresh(moment)

    tag = Tag(name="focus", user_id=user.id)
    session.add(tag)
    session.commit()
    session.refresh(tag)

    session.add(MomentTagLink(moment_id=moment.id, tag_id=tag.id))
    session.commit()

    response = _build_moment_response(session, moment, user)

    assert len(response.tags) == 1
    assert response.tags[0].id == tag.id
    assert response.tags[0].name == "focus"

    session.close()


def test_build_moment_response_includes_active_people_only() -> None:
    engine = create_engine("sqlite:///:memory:")
    BaseModel.metadata.create_all(engine)
    session = Session(engine)

    user = User(
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password="hashed_password",
        name="Test User",
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    moment = Moment(
        user_id=user.id,
        logged_at_utc=datetime.now(UTC),
        logged_date_tz=datetime.now(UTC).date(),
        note="People moment",
    )
    session.add(moment)
    session.commit()
    session.refresh(moment)

    active_person = Person(
        user_id=user.id,
        name="Alice",
        normalized_name="alice",
    )
    archived_person = Person(
        user_id=user.id,
        name="Bob",
        normalized_name="bob",
        archived_at=datetime.now(UTC),
    )
    session.add(active_person)
    session.add(archived_person)
    session.commit()
    session.refresh(active_person)
    session.refresh(archived_person)

    session.add(MomentPersonLink(moment_id=moment.id, person_id=active_person.id))
    session.add(MomentPersonLink(moment_id=moment.id, person_id=archived_person.id))
    session.commit()

    response = _build_moment_response(session, moment, user)

    assert len(response.people) == 1
    assert response.people[0].id == active_person.id
    assert response.people[0].name == "Alice"

    session.close()
