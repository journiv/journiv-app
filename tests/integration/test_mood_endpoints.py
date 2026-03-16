"""
Mood API coverage.
"""
import uuid
from datetime import date, timedelta

from tests.integration.helpers import (
    UNKNOWN_UUID,
    EndpointCase,
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


def test_mood_streak_omits_null_fields_for_empty_history(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    """Fresh users should not receive null map values in streak payload."""
    streak_response = api_client.request(
        "GET", "/moods/analytics/streak", token=api_user.access_token
    )
    assert streak_response.status_code == 200
    streak = streak_response.json()
    assert streak["current_streak"] == 0
    assert streak["total_days_logged"] == 0
    assert "last_logged_date" not in streak


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


def test_reorder_moods_rejects_duplicate_ids(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    mood = _pick_mood(api_client, api_user.access_token)
    response = api_client.request(
        "PUT",
        "/moods/reorder",
        token=api_user.access_token,
        json={"mood_ids": [mood["id"], mood["id"]]},
        expected=(400,),
    )
    assert "duplicate" in response.json()["detail"].lower()


def test_reorder_mood_groups_rejects_unknown_group(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    response = api_client.request(
        "PUT",
        "/moods/groups/reorder",
        token=api_user.access_token,
        json={"updates": [{"id": str(uuid.uuid4()), "position": 0}]},
        expected=(400,),
    )
    assert "not found" in response.json()["detail"].lower()


def test_reorder_mood_group_moods_rejects_non_member_moods(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    mood_in_group = api_client.create_mood(
        api_user.access_token,
        name=f"Mood In Group {uuid.uuid4().hex[:6]}",
        score=4,
    )
    mood_outside_group = api_client.create_mood(
        api_user.access_token,
        name=f"Mood Outside Group {uuid.uuid4().hex[:6]}",
        score=2,
    )
    group = api_client.create_mood_group(
        api_user.access_token,
        name=f"Group {uuid.uuid4().hex[:6]}",
        mood_ids=[mood_in_group["id"]],
    )

    response = api_client.request(
        "PUT",
        f"/moods/groups/{group['id']}/moods/reorder",
        token=api_user.access_token,
        json={"mood_ids": [mood_outside_group["id"]]},
        expected=(400,),
    )
    assert "do not belong" in response.json()["detail"].lower()


def test_recreating_deleted_mood_reactivates_existing_row(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    name = f"Recreate Mood {uuid.uuid4().hex[:6]}"
    original = api_client.create_mood(
        api_user.access_token,
        name=name,
        score=2,
        icon="cloud",
        color_value=0x111111,
    )

    delete_response = api_client.request(
        "DELETE",
        f"/moods/{original['id']}",
        token=api_user.access_token,
        expected=(204,),
    )
    assert delete_response.status_code == 204

    recreated = api_client.create_mood(
        api_user.access_token,
        name=name,
        score=5,
        icon="sun",
        color_value=0x222222,
    )

    assert recreated["id"] == original["id"]
    assert recreated["name"] == name
    assert recreated["score"] == 5
    assert recreated["icon"] == "sun"
    assert recreated["color_value"] == 0x222222

    moods = api_client.get_moods_by_name(api_user.access_token, name=name)
    assert len(moods) == 1
    assert moods[0]["id"] == original["id"]
