"""
People API integration tests.
"""
import io

from tests.integration.helpers import (
    UNKNOWN_UUID,
    EndpointCase,
    assert_requires_authentication,
)
from tests.lib import ApiUser, JournivApiClient


def _create_person(api_client: JournivApiClient, token: str, *, name: str) -> dict:
    return _create_person_with_groups(api_client, token, name=name, group_ids=[])


def _create_person_with_groups(
    api_client: JournivApiClient,
    token: str,
    *,
    name: str,
    group_ids: list[str],
) -> dict:
    return api_client.request(
        "POST",
        "/people/",
        token=token,
        json={"name": name, "group_ids": group_ids},
        expected=(201,),
    ).json()


def _create_person_group(api_client: JournivApiClient, token: str, *, name: str) -> dict:
    return api_client.request(
        "POST",
        "/people-groups/",
        token=token,
        json={"name": name},
        expected=(201,),
    ).json()


def test_people_crud_archive_restore_merge_and_moment_links(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    family = _create_person_group(api_client, api_user.access_token, name="Family")
    friends = _create_person_group(api_client, api_user.access_token, name="Friends")

    first_moment = moment_factory(note="First people moment")
    second_moment = moment_factory(note="Second people moment")

    alice = _create_person_with_groups(
        api_client,
        api_user.access_token,
        name="Alice",
        group_ids=[str(family["id"])],
    )
    bob = _create_person_with_groups(
        api_client,
        api_user.access_token,
        name="Bob",
        group_ids=[str(friends["id"])],
    )
    assert {group["id"] for group in alice["groups"]} == {family["id"]}

    listed = api_client.request(
        "GET",
        "/people/",
        token=api_user.access_token,
        params={"q": "ali"},
        expected=(200,),
    ).json()
    assert any(person["id"] == alice["id"] for person in listed)
    listed_with_search = api_client.request(
        "GET",
        "/people/",
        token=api_user.access_token,
        params={"search": "ali"},
        expected=(200,),
    ).json()
    assert any(person["id"] == alice["id"] for person in listed_with_search)

    updated = api_client.request(
        "PUT",
        f"/people/{alice['id']}",
        token=api_user.access_token,
        json={"nickname": "Al", "group_ids": [family["id"], friends["id"]]},
        expected=(200,),
    ).json()
    assert updated["nickname"] == "Al"
    assert {group["id"] for group in updated["groups"]} == {family["id"], friends["id"]}

    first_links = api_client.request(
        "PUT",
        f"/moments/{first_moment['id']}/people",
        token=api_user.access_token,
        json={"person_ids": [alice["id"], bob["id"]]},
        expected=(200,),
    ).json()
    assert {item["id"] for item in first_links} == {alice["id"], bob["id"]}

    first_links_repeat = api_client.request(
        "PUT",
        f"/moments/{first_moment['id']}/people",
        token=api_user.access_token,
        json={"person_ids": [alice["id"], bob["id"]]},
        expected=(200,),
    ).json()
    assert len(first_links_repeat) == 2

    api_client.request(
        "PUT",
        f"/moments/{second_moment['id']}/people",
        token=api_user.access_token,
        json={"person_ids": [alice["id"]]},
        expected=(200,),
    )

    merged = api_client.request(
        "POST",
        f"/people/{alice['id']}/merge/{bob['id']}",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    assert merged["id"] == bob["id"]

    second_links_after_merge = api_client.request(
        "GET",
        f"/moments/{second_moment['id']}/people",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    assert [item["id"] for item in second_links_after_merge] == [bob["id"]]

    archived_source = api_client.request(
        "GET",
        f"/people/{alice['id']}",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    assert archived_source["archived_at"] is not None

    api_client.request(
        "DELETE",
        f"/moments/{first_moment['id']}/people/{bob['id']}",
        token=api_user.access_token,
        expected=(204,),
    )
    first_links_after_delete = api_client.request(
        "GET",
        f"/moments/{first_moment['id']}/people",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    assert first_links_after_delete == []

    api_client.request(
        "DELETE",
        f"/people/{bob['id']}",
        token=api_user.access_token,
        expected=(204,),
    )
    people_default = api_client.request(
        "GET",
        "/people/",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    assert all(person["id"] != bob["id"] for person in people_default)

    restored = api_client.request(
        "POST",
        f"/people/{bob['id']}/restore",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    assert restored["archived_at"] is None

    all_people = api_client.request(
        "GET",
        "/people/",
        token=api_user.access_token,
        params={"include_archived": "true"},
        expected=(200,),
    ).json()
    assert any(person["id"] == alice["id"] and person["archived_at"] is not None for person in all_people)
    assert any(person["id"] == bob["id"] and person["archived_at"] is None for person in all_people)


def test_moment_listing_supports_people_any_and_all_filters(
    api_client: JournivApiClient,
    api_user: ApiUser,
    moment_factory,
):
    person_one = _create_person(api_client, api_user.access_token, name="Person One")
    person_two = _create_person(api_client, api_user.access_token, name="Person Two")

    moment_one = moment_factory(note="Only person one")
    moment_two = moment_factory(note="Only person two")
    moment_three = moment_factory(note="Both people")

    api_client.request(
        "PUT",
        f"/moments/{moment_one['id']}/people",
        token=api_user.access_token,
        json={"person_ids": [person_one["id"]]},
        expected=(200,),
    )
    api_client.request(
        "PUT",
        f"/moments/{moment_two['id']}/people",
        token=api_user.access_token,
        json={"person_ids": [person_two["id"]]},
        expected=(200,),
    )
    api_client.request(
        "PUT",
        f"/moments/{moment_three['id']}/people",
        token=api_user.access_token,
        json={"person_ids": [person_one["id"], person_two["id"]]},
        expected=(200,),
    )

    any_filtered = api_client.request(
        "GET",
        "/moments",
        token=api_user.access_token,
        params=[
            ("person_ids", person_one["id"]),
            ("person_ids", person_two["id"]),
            ("people_match", "any"),
        ],
        expected=(200,),
    ).json()["items"]
    any_ids = {item["id"] for item in any_filtered}
    assert any_ids.issuperset({moment_one["id"], moment_two["id"], moment_three["id"]})

    all_filtered = api_client.request(
        "GET",
        "/moments",
        token=api_user.access_token,
        params=[
            ("person_ids", person_one["id"]),
            ("person_ids", person_two["id"]),
            ("people_match", "all"),
        ],
        expected=(200,),
    ).json()["items"]
    all_ids = {item["id"] for item in all_filtered}
    assert all_ids == {moment_three["id"]}


def test_people_groups_crud_reorder_and_membership(
    api_client: JournivApiClient,
    api_user: ApiUser,
):
    family = _create_person_group(api_client, api_user.access_token, name="Family")
    friends = _create_person_group(api_client, api_user.access_token, name="Friends")

    groups = api_client.request(
        "GET",
        "/people-groups/",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    group_ids = {group["id"] for group in groups}
    assert {family["id"], friends["id"]}.issubset(group_ids)

    updated_family = api_client.request(
        "PUT",
        f"/people-groups/{family['id']}",
        token=api_user.access_token,
        json={"name": "Close Family"},
        expected=(200,),
    ).json()
    assert updated_family["name"] == "Close Family"

    api_client.request(
        "PUT",
        "/people-groups/reorder",
        token=api_user.access_token,
        json={
            "updates": [
                {"id": friends["id"], "position": 10},
                {"id": family["id"], "position": 20},
            ]
        },
        expected=(204,),
    )
    groups_after_reorder = api_client.request(
        "GET",
        "/people-groups/",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    group_by_id = {group["id"]: group for group in groups_after_reorder}
    assert group_by_id[friends["id"]]["position"] == 10
    assert group_by_id[family["id"]]["position"] == 20
    ordered_ids = [group["id"] for group in groups_after_reorder]
    assert ordered_ids.index(friends["id"]) < ordered_ids.index(family["id"])

    person = _create_person_with_groups(
        api_client,
        api_user.access_token,
        name="Charlie",
        group_ids=[friends["id"]],
    )
    assert {group["id"] for group in person["groups"]} == {friends["id"]}

    friends_group = api_client.request(
        "GET",
        f"/people-groups/{friends['id']}",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    assert any(member["id"] == person["id"] for member in friends_group["people"])

    api_client.request(
        "DELETE",
        f"/people-groups/{friends['id']}",
        token=api_user.access_token,
        expected=(204,),
    )
    api_client.request(
        "GET",
        f"/people-groups/{friends['id']}",
        token=api_user.access_token,
        expected=(404,),
    )

    person_after_group_delete = api_client.request(
        "GET",
        f"/people/{person['id']}",
        token=api_user.access_token,
        expected=(200,),
    ).json()
    assert person_after_group_delete["groups"] == []


def test_people_endpoints_require_auth(api_client: JournivApiClient):
    assert_requires_authentication(
        api_client,
        [
            EndpointCase("GET", "/people/"),
            EndpointCase("POST", "/people/", json={"name": "No Auth"}),
            EndpointCase("GET", f"/people/{UNKNOWN_UUID}"),
            EndpointCase("PUT", f"/people/{UNKNOWN_UUID}", json={"name": "No Auth"}),
            EndpointCase(
                "POST",
                f"/people/{UNKNOWN_UUID}/profile-image",
                files={"file": ("profile.jpg", io.BytesIO(b"not-authenticated"), "image/jpeg")},
            ),
            EndpointCase("DELETE", f"/people/{UNKNOWN_UUID}/profile-image"),
            EndpointCase("DELETE", f"/people/{UNKNOWN_UUID}"),
            EndpointCase("POST", f"/people/{UNKNOWN_UUID}/restore"),
            EndpointCase("POST", f"/people/{UNKNOWN_UUID}/merge/{UNKNOWN_UUID}"),
            EndpointCase("GET", "/people-groups/"),
            EndpointCase("POST", "/people-groups/", json={"name": "No Auth"}),
            EndpointCase("GET", f"/people-groups/{UNKNOWN_UUID}"),
            EndpointCase("PUT", "/people-groups/reorder", json={"updates": []}),
            EndpointCase("PUT", f"/people-groups/{UNKNOWN_UUID}", json={"name": "No Auth"}),
            EndpointCase("DELETE", f"/people-groups/{UNKNOWN_UUID}"),
            EndpointCase("GET", f"/moments/{UNKNOWN_UUID}/people"),
            EndpointCase(
                "PUT",
                f"/moments/{UNKNOWN_UUID}/people",
                json={"person_ids": [UNKNOWN_UUID]},
            ),
            EndpointCase("DELETE", f"/moments/{UNKNOWN_UUID}/people/{UNKNOWN_UUID}"),
        ],
    )
