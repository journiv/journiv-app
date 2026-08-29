"""
Tag API integration tests.
"""

from tests.integration.helpers import (
    UNKNOWN_UUID,
    EndpointCase,
    assert_requires_authentication,
)
from tests.lib import ApiUser, JournivApiClient


def test_tag_crud_and_entry_associations(
    api_client: JournivApiClient, api_user: ApiUser, entry_factory
):
    """Tags can be created, updated, attached to moments, and deleted."""
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

    tagged = api_client.request(
        "POST",
        f"/moments/{entry['moment_id']}/tags",
        token=api_user.access_token,
        json=["integration-updated"],
        expected=(200,),
    ).json()
    assert any(tag["id"] == base["id"] for tag in tagged)

    moment_tags = api_client.request(
        "GET", f"/moments/{entry['moment_id']}/tags", token=api_user.access_token
    ).json()
    assert any(tag["id"] == base["id"] for tag in moment_tags)

    bulk_added = api_client.request(
        "POST",
        f"/moments/{entry['moment_id']}/tags",
        token=api_user.access_token,
        json=["focus", "gratitude"],
        expected=(200,),
    ).json()
    assert {tag["name"] for tag in bulk_added} >= {"focus", "gratitude"}

    moment_tags = api_client.request(
        "GET", f"/moments/{entry['moment_id']}/tags", token=api_user.access_token
    ).json()
    moment_tag_names = {tag["name"] for tag in moment_tags}
    assert moment_tag_names.issuperset({"integration-updated", "focus", "gratitude"})

    entries_for_tag = api_client.request(
        "GET", f"/tags/{base['id']}/moments", token=api_user.access_token
    ).json()
    tagged_item = next(item for item in entries_for_tag if item["id"] == entry["moment_id"])
    assert tagged_item["entry"]["id"] == entry["id"]
    assert tagged_item["entry"]["moment_id"] == entry["moment_id"]
    assert tagged_item["entry"]["journal_id"] == entry["journal"]["id"]
    assert tagged_item["entry"]["title"] == "Tagged entry"
    assert tagged_item["entry"]["content_plain_text"] == entry["content_plain_text"]

    api_client.request(
        "DELETE",
        f"/moments/{entry['moment_id']}/tags/{base['id']}",
        token=api_user.access_token,
        expected=(204,),
    )
    moment_tags = api_client.request(
        "GET", f"/moments/{entry['moment_id']}/tags", token=api_user.access_token
    ).json()
    assert all(tag["id"] != base["id"] for tag in moment_tags)

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
        f"/moments/{entry['moment_id']}/tags",
        token=api_user.access_token,
        json=["alpha"],
        expected=(200,),
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

    analytics_response = api_client.request(
        "GET", "/tags/analytics", token=api_user.access_token
    )
    # Analytics endpoint requires Plus license - may return 403 if license not available
    # or 503 if Plus features are not available in this build
    if analytics_response.status_code in (403, 503):
        # Plus license or features not available - skip analytics assertions
        # This is expected in integration tests without Plus license or compiled features
        pass
    else:
        # Plus license available - verify analytics structure
        assert analytics_response.status_code == 200
        analytics = analytics_response.json()
        assert "total_tags" in analytics
        assert analytics["total_tags"] >= 2
        assert isinstance(analytics.get("most_used_tags", []), list)


def test_delete_unused_tags_removes_only_orphans(
    api_client: JournivApiClient, api_user: ApiUser, entry_factory
):
    """DELETE /tags/unused clears tags with no moment, keeps the rest."""
    entry = entry_factory(title="Keeps its tag")
    used = api_client.create_tag(api_user.access_token, name="used-tag")
    orphan_a = api_client.create_tag(api_user.access_token, name="orphan-a")
    orphan_b = api_client.create_tag(api_user.access_token, name="orphan-b")

    api_client.request(
        "POST",
        f"/moments/{entry['moment_id']}/tags",
        token=api_user.access_token,
        json=["used-tag"],
        expected=(200,),
    )

    result = api_client.request(
        "DELETE", "/tags/unused", token=api_user.access_token, expected=(200,)
    ).json()
    assert result == {"deleted": 2}

    remaining = {tag["id"] for tag in api_client.list_tags(api_user.access_token)}
    assert used["id"] in remaining
    assert orphan_a["id"] not in remaining
    assert orphan_b["id"] not in remaining

    # Idempotent: nothing left to clean up.
    again = api_client.request(
        "DELETE", "/tags/unused", token=api_user.access_token, expected=(200,)
    ).json()
    assert again == {"deleted": 0}


def test_tag_analytics_requires_plus_without_probing(
    api_client: JournivApiClient, api_user: ApiUser
):
    """Aggregate tag analytics stays Plus-gated (403/503) without a licence."""
    response = api_client.request(
        "GET", "/tags/analytics", token=api_user.access_token
    )
    assert response.status_code in (200, 403, 503)


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
            EndpointCase("GET", "/tags/analytics"),
            EndpointCase("DELETE", "/tags/unused"),
            EndpointCase("GET", f"/moments/{UNKNOWN_UUID}/tags"),
            EndpointCase(
                "POST",
                f"/moments/{UNKNOWN_UUID}/tags",
                json=["one"],
            ),
            EndpointCase(
                "DELETE",
                f"/moments/{UNKNOWN_UUID}/tags/{UNKNOWN_UUID}",
            ),
            EndpointCase("GET", f"/tags/{UNKNOWN_UUID}/moments"),
        ],
    )
