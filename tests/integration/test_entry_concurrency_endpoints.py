"""
The 409 must reach the wire, through both routes that update an entry.

The editor saves either through `PUT /entries/{id}` or, when it is finalising a
draft Moment, through `PUT /moments/{id}` with `entry_update`. Both must refuse
a stale save, or a save takes whichever path happens to apply that day and the
protection is only sometimes there.
"""
from datetime import date

from tests.lib import ApiUser, JournivApiClient


def _entry(api_client: JournivApiClient, api_user: ApiUser, journal_id: str):
    return api_client.create_entry_with_moment(
        api_user.access_token,
        journal_id=journal_id,
        title="Opened on two devices",
        content="First device wrote this.",
        logged_date=date.today().isoformat(),
    )


def test_stale_save_is_refused_on_the_entry_route(
    api_client: JournivApiClient, api_user: ApiUser, journal_factory
):
    created = _entry(api_client, api_user, journal_factory()["id"])
    opened_at = api_client.get_entry(api_user.access_token, created["id"])["updated_at"]

    # The other device saves first.
    api_client.update_entry(
        api_user.access_token, created["id"], {"content": "Second device wrote this."}
    )

    refused = api_client.request(
        "PUT",
        f"/entries/{created['id']}",
        token=api_user.access_token,
        json={
            "content_delta": {"ops": [{"insert": "First device, saving late.\n"}]},
            "expected_updated_at": opened_at,
        },
        expected=(409,),
    )
    assert "changed somewhere else" in refused.json()["detail"]

    # And the other device's writing is still there.
    kept = api_client.get_entry(api_user.access_token, created["id"])
    assert "Second device wrote this." in kept["content_plain_text"]


def test_current_version_round_trips_through_the_entry_route(
    api_client: JournivApiClient, api_user: ApiUser, journal_factory
):
    """The value the API hands out must be the value it accepts back.

    This is the whole contract: serialise, send, parse, compare. A format or
    precision mismatch anywhere in that loop would refuse every honest save.
    """
    created = _entry(api_client, api_user, journal_factory()["id"])
    opened_at = api_client.get_entry(api_user.access_token, created["id"])["updated_at"]

    api_client.request(
        "PUT",
        f"/entries/{created['id']}",
        token=api_user.access_token,
        json={
            "content_delta": {"ops": [{"insert": "Saved from the version I read.\n"}]},
            "expected_updated_at": opened_at,
        },
        expected=(200,),
    )


def test_stale_save_is_refused_on_the_moment_route(
    api_client: JournivApiClient, api_user: ApiUser, journal_factory
):
    created = _entry(api_client, api_user, journal_factory()["id"])
    opened_at = api_client.get_entry(api_user.access_token, created["id"])["updated_at"]

    api_client.update_entry(
        api_user.access_token, created["id"], {"content": "Second device wrote this."}
    )

    api_client.request(
        "PUT",
        f"/moments/{created['moment_id']}",
        token=api_user.access_token,
        json={
            "entry_update": {
                "content_delta": {"ops": [{"insert": "Late save.\n"}]},
                "expected_updated_at": opened_at,
            }
        },
        expected=(409,),
    )


def test_omitting_the_version_still_saves(
    api_client: JournivApiClient, api_user: ApiUser, journal_factory
):
    """Existing clients — the Flutter app included — send nothing and must work."""
    created = _entry(api_client, api_user, journal_factory()["id"])
    api_client.update_entry(
        api_user.access_token, created["id"], {"content": "Anywhere."}
    )
    api_client.update_entry(
        api_user.access_token, created["id"], {"content": "Overwritten, as before."}
    )
    kept = api_client.get_entry(api_user.access_token, created["id"])
    assert "Overwritten, as before." in kept["content_plain_text"]
