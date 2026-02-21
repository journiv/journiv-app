"""
Integration coverage for starter metadata seeding.
"""
import uuid

from tests.lib import JournivApiClient


def _unique_credentials(prefix: str = "starter") -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    email = f"{prefix}-{suffix}@example.com"
    password = f"Pass-{suffix}-Aa1!"
    return email, password


def test_registration_seeds_starter_metadata(api_client: JournivApiClient):
    email, password = _unique_credentials()
    api_client.register_user(
        email=email,
        password=password,
        name="Starter Seed Test",
    )
    tokens = api_client.login(email, password)
    token = tokens["access_token"]

    moods = api_client.list_moods(token)
    mood_names = {mood["name"] for mood in moods}
    assert {"Awesome", "Good", "Meh", "Bad", "Awful"}.issubset(mood_names)

    mood_groups = api_client.list_mood_groups(token)
    daily_group = next((group for group in mood_groups if group.get("name") == "Daily Moods"), None)
    assert daily_group is not None
    assert daily_group["name"] == "Daily Moods"
    group_mood_names = {mood["name"] for mood in daily_group.get("moods", [])}
    assert {"Awesome", "Good", "Meh", "Bad", "Awful"}.issubset(group_mood_names)

    activity_groups = api_client.list_activity_groups(token)
    activity_group_names = {group["name"] for group in activity_groups}
    assert {"Wellness", "Life Flow"}.issubset(activity_group_names)

    activities = api_client.list_activities(token)
    activity_names = {activity["name"] for activity in activities}
    assert {
        "Steps",
        "Sleep",
        "Exercise",
        "Work",
        "Family",
        "Journaling",
    }.issubset(activity_names)

    goal_categories = api_client.list_goal_categories(token)
    mindfulness = next(
        (category for category in goal_categories if category.get("name") == "Mindfulness"),
        None,
    )
    assert mindfulness is not None
    assert mindfulness["name"] == "Mindfulness"

    goals = api_client.list_goals(token)
    journaling_goal = next(
        (
            goal for goal in goals
            if goal.get("title") == "Journal 5 days this week"
            and goal.get("frequency_type") == "weekly"
            and goal.get("target_count") == 5
        ),
        None,
    )
    assert journaling_goal is not None
    assert journaling_goal["title"] == "Journal 5 days this week"
    assert journaling_goal["frequency_type"] == "weekly"
    assert journaling_goal["target_count"] == 5


def test_deleted_seeded_mood_is_not_restored_by_login(api_client: JournivApiClient):
    email, password = _unique_credentials("starter-delete")
    api_client.register_user(
        email=email,
        password=password,
        name="Starter Seed Delete Test",
    )
    tokens = api_client.login(email, password)
    token = tokens["access_token"]

    good_mood = next((mood for mood in api_client.list_moods(token) if mood.get("key") == "good"), None)
    assert good_mood is not None

    delete_response = api_client.request(
        "DELETE",
        f"/moods/{good_mood['id']}",
        token=token,
        expected=(204,),
    )
    assert delete_response.status_code == 204

    moods_after_delete = api_client.list_moods(token)
    assert all(mood["id"] != good_mood["id"] for mood in moods_after_delete)

    relogin = api_client.login(email, password)
    relogin_token = relogin["access_token"]
    api_client.current_user(relogin_token)
    moods_after_relogin = api_client.list_moods(relogin_token)
    assert all(mood["id"] != good_mood["id"] for mood in moods_after_relogin)
