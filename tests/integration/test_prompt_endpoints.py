"""
Prompt API integration coverage.
"""
import pytest

from tests.integration.helpers import EndpointCase, assert_requires_authentication
from tests.lib import ApiUser, JournivApiClient


def _first_prompt(api_client: JournivApiClient, token: str) -> dict:
    prompts = api_client.list_prompts(token, limit=5)
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

    params = {"category": prompt.get("category"), "difficulty_level": prompt.get("difficulty_level")}
    listing = api_client.list_prompts(
        api_user.access_token, limit=3, **{k: v for k, v in params.items() if v}
    )
    assert isinstance(listing, list)

    search_term = (prompt.get("text") or prompt.get("category") or "prompt").split()[0]
    search = api_client.request(
        "GET",
        "/prompts/search",
        token=api_user.access_token,
        params={"q": search_term[:5]},
    ).json()
    assert isinstance(search, list)


def test_prompt_random_daily_and_statistics(api_client: JournivApiClient, api_user: ApiUser):
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
    assert "total_prompts" in stats


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
