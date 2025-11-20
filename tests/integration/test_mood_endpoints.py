"""
Mood API coverage.
"""
import uuid
from datetime import date, timedelta

import pytest

from tests.integration.helpers import (
    EndpointCase,
    UNKNOWN_UUID,
    assert_requires_authentication,
)
from tests.lib import ApiUser, JournivApiClient


def _pick_mood(api_client: JournivApiClient, token: str) -> dict:
    moods = api_client.list_moods(token)
    if not moods:
        pytest.skip("No moods available in the system.")
    return moods[0]


def test_mood_logging_update_and_recent(
    api_client: JournivApiClient, api_user: ApiUser, entry_factory
):
    """Covers mood listing, logging, updating, deleting, and recent logs."""
    mood = _pick_mood(api_client, api_user.access_token)
    entry = entry_factory()
    logged = api_client.create_mood_log(
        api_user.access_token,
        entry_id=entry["id"],
        mood_id=mood["id"],
        logged_date=date.today().isoformat(),
        notes="Initial log",
    )
    assert logged["entry_id"] == entry["id"]

    fetched = api_client.request(
        "GET", f"/moods/log/{logged['id']}", token=api_user.access_token
    ).json()
    assert fetched["id"] == logged["id"]

    updated = api_client.request(
        "PUT",
        f"/moods/log/{logged['id']}",
        token=api_user.access_token,
        json={"note": "Updated note"},
    ).json()
    assert updated["note"] == "Updated note"

    recent = api_client.request(
        "GET", "/moods/log/recent", token=api_user.access_token
    ).json()
    assert any(log["id"] == logged["id"] for log in recent)

    logs = api_client.list_mood_logs(api_user.access_token)
    assert any(log["id"] == logged["id"] for log in logs)

    api_client.request(
        "DELETE",
        f"/moods/log/{logged['id']}",
        token=api_user.access_token,
        expected=(204,),
    )
    missing = api_client.request(
        "GET", f"/moods/log/{logged['id']}", token=api_user.access_token
    )
    assert missing.status_code == 404


def test_mood_lists_support_filters_and_analytics(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Mood logs listing with filters and analytics endpoints should return data."""
    mood = _pick_mood(api_client, api_user.access_token)
    log_date = (date.today() - timedelta(days=1)).isoformat()
    entry = entry_factory(entry_date=log_date)
    logged = api_client.create_mood_log(
        api_user.access_token,
        entry_id=entry["id"],
        mood_id=mood["id"],
        logged_date=log_date,
        notes="Analytics test",
    )

    filtered_logs = api_client.request(
        "GET",
        "/moods/logs",
        token=api_user.access_token,
        params={
            "limit": 5,
            "mood_id": mood["id"],
            "entry_id": entry["id"],
            "start_date": log_date,
            "end_date": log_date,
        },
    ).json()
    assert any(item["id"] == logged["id"] for item in filtered_logs)

    stats_response = api_client.request(
        "GET",
        "/moods/analytics/statistics",
        token=api_user.access_token,
        params={
            "start_date": (date.today() - timedelta(days=7)).isoformat(),
            "end_date": date.today().isoformat(),
        },
    )
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert isinstance(stats, dict)

    streak_response = api_client.request(
        "GET", "/moods/analytics/streak", token=api_user.access_token
    )
    assert streak_response.status_code in (200, 404)
    if streak_response.status_code == 200:
        streak = streak_response.json()
        assert isinstance(streak, dict)


def test_mood_log_rejects_unknown_ids(api_client: JournivApiClient, api_user: ApiUser):
    """Logging a mood with unknown IDs should return 404."""
    response = api_client.request(
        "POST",
        "/moods/log",
        token=api_user.access_token,
        json={
            "entry_id": str(uuid.uuid4()),
            "mood_id": str(uuid.uuid4()),
            "logged_date": date.today().isoformat(),
            "notes": "Unknown mood",
        },
    )
    assert response.status_code == 404


def test_mood_endpoints_require_authentication(api_client: JournivApiClient):
    """Anonymous callers should be rejected for all mood endpoints."""
    today = date.today().isoformat()
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("GET", "/moods/"),
            EndpointCase(
                "POST",
                "/moods/log",
                json={
                    "entry_id": str(uuid.uuid4()),
                    "mood_id": str(uuid.uuid4()),
                    "logged_date": today,
                },
            ),
            EndpointCase("GET", "/moods/logs"),
            EndpointCase("GET", "/moods/log/recent"),
            EndpointCase("GET", f"/moods/log/{UNKNOWN_UUID}"),
            EndpointCase(
                "PUT",
                f"/moods/log/{UNKNOWN_UUID}",
                json={"note": "unauth"},
            ),
            EndpointCase("DELETE", f"/moods/log/{UNKNOWN_UUID}"),
            EndpointCase("GET", "/moods/analytics/statistics"),
            EndpointCase("GET", "/moods/analytics/streak"),
        ],
    )
