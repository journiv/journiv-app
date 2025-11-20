"""
Tag API integration tests.
"""

from tests.integration.helpers import (
    EndpointCase,
    UNKNOWN_UUID,
    assert_requires_authentication,
)
from tests.lib import ApiUser, JournivApiClient


def test_tag_crud_and_entry_associations(
    api_client: JournivApiClient, api_user: ApiUser, entry_factory
):
    """Tags can be created, updated, attached to entries, and deleted."""
    entry = entry_factory(title="Tagged entry")
    base = api_client.create_tag(api_user.access_token, name="integration", color="#3B82F6")

    fetched = api_client.request(
        "GET", f"/tags/{base['id']}", token=api_user.access_token
    ).json()
    assert fetched["name"] == "integration"

    updated = api_client.update_tag(
        api_user.access_token, base["id"], {"name": "integration-updated", "color": "#F97316"}
    )
    assert updated["name"] == "integration-updated"

    link = api_client.request(
        "POST",
        f"/tags/entry/{entry['id']}/tag/{base['id']}",
        token=api_user.access_token,
        expected=(201,),
    ).json()
    assert link["entry_id"] == entry["id"]
    assert link["tag_id"] == base["id"]

    entry_tags = api_client.request(
        "GET", f"/tags/entry/{entry['id']}", token=api_user.access_token
    ).json()
    assert any(tag["id"] == base["id"] for tag in entry_tags)

    bulk_added = api_client.request(
        "POST",
        f"/tags/entry/{entry['id']}/bulk",
        token=api_user.access_token,
        json=["focus", "gratitude"],
        expected=(200,),
    ).json()
    assert {tag["name"] for tag in bulk_added} >= {"focus", "gratitude"}

    entry_tags = api_client.request(
        "GET", f"/tags/entry/{entry['id']}", token=api_user.access_token
    ).json()
    entry_tag_names = {tag["name"] for tag in entry_tags}
    assert entry_tag_names.issuperset({"integration-updated", "focus", "gratitude"})

    entries_for_tag = api_client.request(
        "GET", f"/tags/{base['id']}/entries", token=api_user.access_token
    ).json()
    assert any(item["id"] == entry["id"] for item in entries_for_tag)

    api_client.request(
        "DELETE",
        f"/tags/entry/{entry['id']}/tag/{base['id']}",
        token=api_user.access_token,
        expected=(204,),
    )
    entry_tags = api_client.request(
        "GET", f"/tags/entry/{entry['id']}", token=api_user.access_token
    ).json()
    assert all(tag["id"] != base["id"] for tag in entry_tags)

    api_client.delete_tag(api_user.access_token, base["id"])
    missing = api_client.request("GET", f"/tags/{base['id']}", token=api_user.access_token)
    assert missing.status_code == 404


def test_tag_listing_search_and_statistics(
    api_client: JournivApiClient,
    api_user: ApiUser,
    entry_factory,
):
    """Listing, search, popular, and statistics endpoints should be consistent."""
    entry = entry_factory(title="Stats entry")
    alpha = api_client.create_tag(api_user.access_token, name="alpha", color="#22C55E")
    beta = api_client.create_tag(api_user.access_token, name="beta", color="#64748B")

    api_client.request(
        "POST",
        f"/tags/entry/{entry['id']}/tag/{alpha['id']}",
        token=api_user.access_token,
        expected=(201,),
    )

    filtered = api_client.request(
        "GET",
        "/tags/",
        token=api_user.access_token,
        params={"search": "alp"},
    ).json()
    assert all("alp" in tag["name"] for tag in filtered)

    search = api_client.request(
        "GET",
        "/tags/search",
        token=api_user.access_token,
        params={"q": "beta"},
    ).json()
    assert any(tag["id"] == beta["id"] for tag in search)

    popular = api_client.request(
        "GET",
        "/tags/popular",
        token=api_user.access_token,
        params={"limit": 1},
    ).json()
    assert len(popular) == 1

    stats = api_client.tag_statistics(api_user.access_token)
    assert stats["total_tags"] >= 2

    analytics = api_client.request(
        "GET", "/tags/analytics/statistics", token=api_user.access_token
    ).json()
    assert analytics["total_tags"] >= 2
    assert isinstance(analytics.get("most_used_tags", []), list)


def test_tag_endpoints_require_auth(api_client: JournivApiClient):
    """All tag routes must enforce authentication."""
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("GET", "/tags/"),
            EndpointCase(
                "POST",
                "/tags/",
                json={"name": "no-auth", "color": "#22C55E"},
            ),
            EndpointCase("GET", "/tags/popular"),
            EndpointCase("GET", "/tags/search", params={"q": "focus"}),
            EndpointCase("GET", "/tags/statistics"),
            EndpointCase("GET", "/tags/analytics/statistics"),
            EndpointCase("GET", f"/tags/entry/{UNKNOWN_UUID}"),
            EndpointCase(
                "POST",
                f"/tags/entry/{UNKNOWN_UUID}/bulk",
                json=["one"],
            ),
            EndpointCase(
                "POST",
                f"/tags/entry/{UNKNOWN_UUID}/tag/{UNKNOWN_UUID}",
            ),
            EndpointCase(
                "DELETE",
                f"/tags/entry/{UNKNOWN_UUID}/tag/{UNKNOWN_UUID}",
            ),
            EndpointCase("GET", f"/tags/{UNKNOWN_UUID}/entries"),
        ],
    )
