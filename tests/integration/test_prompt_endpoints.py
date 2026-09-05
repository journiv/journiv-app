"""
Prompt API integration coverage.
"""

import pytest

from tests.integration.helpers import EndpointCase, assert_requires_authentication
from tests.lib import ApiUser, JournivApiClient


def _first_prompt(api_client: JournivApiClient, token: str) -> dict:
    page = api_client.list_prompts(token, limit=5)
    prompts = page["items"]
    if not prompts:
        pytest.skip("No prompts available in the system")
    return prompts[0]


def test_prompt_catalog_and_details(api_client: JournivApiClient, api_user: ApiUser):
    """System prompts should support filtering, detail fetching, and searching."""
    prompt = _first_prompt(api_client, api_user.access_token)
    detail = api_client.request(
        "GET", f"/prompts/{prompt['id']}", token=api_user.access_token
    ).json()
    assert detail["id"] == prompt["id"]
    assert detail["answered_count"] >= 0

    params = {
        "category": prompt.get("category"),
        "difficulty_level": prompt.get("difficulty_level"),
    }
    listing = api_client.list_prompts(
        api_user.access_token, limit=3, **{k: v for k, v in params.items() if v}
    )
    assert isinstance(listing["items"], list)
    assert all(item["answered_count"] >= 0 for item in listing["items"])
    assert listing["total"] >= len(listing["items"])
    assert listing["all_count"] >= listing["total"]
    assert isinstance(listing["category_counts"], dict)

    text_query = (prompt.get("text") or "prompt").split()[0]
    searched_listing = api_client.list_prompts(
        api_user.access_token, q=text_query, limit=3
    )
    assert searched_listing["total"] >= len(searched_listing["items"])
    assert all(
        text_query.lower() in item["text"].lower()
        or text_query.lower() in (item.get("category") or "").lower()
        or text_query.lower() in (item.get("category") or "").replace("_", "-").lower()
        for item in searched_listing["items"]
    )

    invalid_category = api_client.request(
        "GET",
        "/prompts/",
        token=api_user.access_token,
        params={"category": "not-a-prompt-category"},
        expected=(422,),
    )
    assert (
        invalid_category.json()["detail"]
        == "Invalid prompt category 'not-a-prompt-category'"
    )

    if isinstance(prompt.get("estimated_time_minutes"), int):
        minutes = prompt["estimated_time_minutes"]
        duration_listing = api_client.list_prompts(
            api_user.access_token,
            min_minutes=minutes,
            max_minutes=minutes,
            limit=3,
        )
        assert all(
            item["estimated_time_minutes"] == minutes
            for item in duration_listing["items"]
        )

    search_term = (prompt.get("text") or prompt.get("category") or "prompt").split()[0]
    search = api_client.request(
        "GET",
        "/prompts/search",
        token=api_user.access_token,
        params={"q": search_term[:5]},
    ).json()
    assert isinstance(search, list)


def test_prompt_catalog_paginates_with_total(
    api_client: JournivApiClient, api_user: ApiUser
):
    """Offset pages are stable and expose a deterministic continuation."""
    first = api_client.list_prompts(api_user.access_token, limit=1, offset=0)
    assert first["total"] >= len(first["items"])
    if first["next_offset"] is None:
        return

    second = api_client.list_prompts(
        api_user.access_token, limit=1, offset=first["next_offset"]
    )
    assert second["items"]
    assert second["items"][0]["id"] != first["items"][0]["id"]


def test_prompt_random_daily_and_statistics(
    api_client: JournivApiClient, api_user: ApiUser
):
    """Random, daily, and analytics endpoints should respond with structured data."""
    random_prompt = api_client.request(
        "GET",
        "/prompts/random",
        token=api_user.access_token,
    )
    assert random_prompt.status_code in (200, 404)

    daily_prompt = api_client.request(
        "GET", "/prompts/daily", token=api_user.access_token
    )
    assert daily_prompt.status_code in (200, 204)

    stats = api_client.request(
        "GET", "/prompts/analytics/statistics", token=api_user.access_token
    ).json()
    assert isinstance(stats["prompts_answered"], int)
    assert isinstance(stats["current_streak"], int)
    assert isinstance(stats["favorite_categories"], list)
    assert isinstance(stats["completion_trend"], list)


def test_prompt_endpoints_require_auth(api_client: JournivApiClient):
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("GET", "/prompts/"),
            EndpointCase("GET", "/prompts/random"),
            EndpointCase("GET", "/prompts/daily"),
            EndpointCase("GET", "/prompts/search", params={"q": "test"}),
            EndpointCase("GET", "/prompts/analytics/statistics"),
        ],
    )
