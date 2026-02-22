from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from app.core.time_utils import utc_now
from tests.lib import ApiUser, JournivApiClient


def test_get_goal_logs_returns_recent_periods(
    api_client: JournivApiClient,
    api_user: ApiUser,
) -> None:
    goal = api_client.create_goal(
        api_user.access_token,
        title="Read daily",
        goal_type="achieve",
        frequency_type="daily",
        target_count=1,
    )

    older_date = (utc_now().date() - timedelta(days=2)).isoformat()
    newer_date = (utc_now().date() - timedelta(days=1)).isoformat()
    api_client.toggle_goal(api_user.access_token, goal["id"], logged_date=older_date)
    api_client.toggle_goal(api_user.access_token, goal["id"], logged_date=newer_date)

    all_logs = api_client.list_goal_logs(api_user.access_token, goal["id"], limit=12)
    assert len(all_logs) >= 2
    assert all_logs[0]["period_start"] >= all_logs[1]["period_start"]

    limited_logs = api_client.list_goal_logs(api_user.access_token, goal["id"], limit=1)
    assert len(limited_logs) == 1
    assert limited_logs[0]["period_start"] == newer_date


def test_get_goal_logs_requires_auth(api_client: JournivApiClient) -> None:
    response = api_client.request(
        "GET",
        f"/goals/{uuid4()}/logs",
        expected=(401,),
    )
    assert response.status_code == 401


def test_get_goal_logs_returns_404_for_unknown_goal(
    api_client: JournivApiClient,
    api_user: ApiUser,
) -> None:
    response = api_client.request(
        "GET",
        f"/goals/{uuid4()}/logs",
        token=api_user.access_token,
        expected=(404,),
    )
    assert response.status_code == 404
