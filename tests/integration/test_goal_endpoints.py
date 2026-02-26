"""
Goal API integration coverage.
"""

from tests.integration.helpers import UNKNOWN_UUID, EndpointCase, assert_not_found
from tests.lib import ApiUser, JournivApiClient


def test_archiving_controls_visibility_and_unarchive(
    api_client: JournivApiClient,
    api_user: ApiUser,
) -> None:
    active_goal = api_client.create_goal(
        api_user.access_token,
        title="Active goal",
        goal_type="achieve",
        frequency_type="daily",
        target_count=1,
    )
    archived_goal = api_client.create_goal(
        api_user.access_token,
        title="Archived goal",
        goal_type="achieve",
        frequency_type="daily",
        target_count=1,
    )

    archive_response = api_client.archive_goal(
        api_user.access_token,
        archived_goal["id"],
    )
    assert archive_response.get("archived_at") is not None

    active_only = api_client.list_goals(api_user.access_token)
    assert any(goal["id"] == active_goal["id"] for goal in active_only)
    assert all(goal["id"] != archived_goal["id"] for goal in active_only)

    with_archived = api_client.list_goals(api_user.access_token, include_archived=True)
    matching_archived = [goal for goal in with_archived if goal["id"] == archived_goal["id"]]
    assert len(matching_archived) == 1
    assert matching_archived[0].get("archived_at") is not None

    unarchived = api_client.unarchive_goal(api_user.access_token, archived_goal["id"])
    assert unarchived.get("archived_at") is None

    refreshed = api_client.list_goals(api_user.access_token)
    assert any(goal["id"] == archived_goal["id"] for goal in refreshed)


def test_goal_unarchive_not_found(
    api_client: JournivApiClient,
    api_user: ApiUser,
) -> None:
    assert_not_found(
        api_client,
        api_user.access_token,
        [
            EndpointCase("POST", f"/goals/{UNKNOWN_UUID}/unarchive"),
            EndpointCase("DELETE", f"/goals/{UNKNOWN_UUID}"),
            EndpointCase("PATCH", f"/goals/{UNKNOWN_UUID}/archive"),
        ],
    )


def test_goal_permanent_delete_removes_archived_goal(
    api_client: JournivApiClient,
    api_user: ApiUser,
) -> None:
    goal = api_client.create_goal(
        api_user.access_token,
        title="Delete me",
        goal_type="achieve",
        frequency_type="daily",
        target_count=1,
    )
    api_client.archive_goal(api_user.access_token, goal["id"])

    api_client.delete_goal_permanently(api_user.access_token, goal["id"])

    goals_with_archived = api_client.list_goals(
        api_user.access_token,
        include_archived=True,
    )
    assert all(item["id"] != goal["id"] for item in goals_with_archived)
