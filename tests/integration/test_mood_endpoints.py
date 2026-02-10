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
    if moods:
        return moods[0]
    return api_client.create_mood(
        token,
        name=f"Test Mood {uuid.uuid4().hex[:6]}",
        score=3,
        icon=":)",
        color_value=0x3B82F6,
    )


def test_mood_logging_update_and_recent(
    api_client: JournivApiClient, api_user: ApiUser
):
    """Covers mood listing, moment logging, updating, and listing."""
    mood = _pick_mood(api_client, api_user.access_token)
    logged = api_client.create_moment(
        api_user.access_token,
        primary_mood_id=mood["id"],
        logged_date=date.today().isoformat(),
        note="Initial log",
    )

    updated = api_client.request(
        "PUT",
        f"/moments/{logged['id']}",
        token=api_user.access_token,
        json={"note": "Updated note"},
    ).json()
    assert updated["note"] == "Updated note"

    moments = api_client.list_moments(api_user.access_token, limit=10)
    assert any(moment["id"] == logged["id"] for moment in moments)


def test_mood_lists_support_filters_and_analytics(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """Moment listing with filters and analytics endpoints should return data."""
    mood = _pick_mood(api_client, api_user.access_token)
    log_date = (date.today() - timedelta(days=1)).isoformat()
    logged = api_client.create_moment(
        api_user.access_token,
        primary_mood_id=mood["id"],
        logged_date=log_date,
        note="Analytics test",
    )

    filtered_moments = api_client.list_moments(
        api_user.access_token,
        limit=5,
        start_date=log_date,
        end_date=log_date,
    )
    assert any(item["id"] == logged["id"] for item in filtered_moments)

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
    """Logging a moment with unknown mood IDs should return 400."""
    unknown_mood = str(uuid.uuid4())
    response = api_client.request(
        "POST",
        "/moments",
        token=api_user.access_token,
        json={
            "logged_date": date.today().isoformat(),
            "primary_mood_id": unknown_mood,
            "mood_activity": [{"mood_id": unknown_mood}],
            "note": "Unknown mood",
        },
    )
    assert response.status_code == 400


def test_mood_endpoints_require_authentication(api_client: JournivApiClient):
    """Anonymous callers should be rejected for all mood endpoints."""
    today = date.today().isoformat()
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("GET", "/moods/"),
            EndpointCase(
                "POST",
                "/moments",
                json={
                    "logged_date": today,
                    "primary_mood_id": str(uuid.uuid4()),
                    "mood_activity": [{"mood_id": str(uuid.uuid4())}],
                },
            ),
            EndpointCase(
                "PUT",
                f"/moments/{UNKNOWN_UUID}",
                json={"note": "unauth"},
            ),
            EndpointCase("GET", "/moments"),
            EndpointCase("GET", "/moments/calendar"),
            EndpointCase("GET", "/moods/analytics/statistics"),
            EndpointCase("GET", "/moods/analytics/streak"),
        ],
    )
