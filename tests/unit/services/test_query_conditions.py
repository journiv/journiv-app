import uuid

import pytest
from sqlalchemy import create_engine, literal, select, text, true

from app.models.entry import Entry
from app.services.moment_lookup import (
    entry_draft_visibility_condition,
    moment_draft_visibility_condition,
    moment_without_draft_condition,
)


@pytest.mark.parametrize(
    ("is_draft", "creator", "owner", "visible", "without_draft"),
    [
        (False, "other", "other", True, True),
        (True, "viewer", "other", True, False),
        (True, "other", "viewer", False, False),
        (True, None, "viewer", False, False),
        (True, None, "other", False, False),
    ],
)
def test_draft_conditions(is_draft, creator, owner, visible, without_draft):
    """Check published entries and fail closed for unknown authors."""
    viewer, other = uuid.uuid4(), uuid.uuid4()
    users = {"viewer": viewer.hex, "other": other.hex, None: None}
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE entry (id TEXT, is_draft BOOLEAN, created_by_user_id TEXT, user_id TEXT)"
        ))
        connection.execute(
            text("INSERT INTO entry VALUES (:id, :draft, :creator, :owner)"),
            {"id": uuid.uuid4().hex, "draft": is_draft, "creator": users[creator], "owner": users[owner]},
        )
        result = connection.execute(select(
            entry_draft_visibility_condition(viewer),
            moment_draft_visibility_condition(viewer),
            moment_without_draft_condition(),
        )).one()
        assert tuple(result) == (visible, visible, without_draft)
