"""Gate-1 Quill Delta compatibility through the public Moment/Entry API."""

import json
from pathlib import Path

import pytest

from tests.lib import ApiUser, JournivApiClient

FIXTURE_DIR = (
    Path(__file__).parents[2] / "frontend/src/features/editor/fixtures"
)
FIXTURE_PATHS = sorted(
    path for path in FIXTURE_DIR.glob("*.json") if path.name != "index.ts"
)


def _without_null_attributes(delta: dict) -> dict:
    return {
        "ops": [
            {
                key: value
                for key, value in operation.items()
                if not (key == "attributes" and value is None)
            }
            for operation in delta["ops"]
        ]
    }


def _plain_text(delta: dict) -> str:
    return "".join(
        operation["insert"]
        for operation in delta["ops"]
        if isinstance(operation["insert"], str)
    )


@pytest.mark.parametrize("fixture_path", FIXTURE_PATHS, ids=lambda path: path.stem)
def test_gate1_delta_create_update_fetch_and_derivations(
    fixture_path: Path,
    api_client: JournivApiClient,
    api_user: ApiUser,
    journal_factory,
):
    fixture = json.loads(fixture_path.read_text())
    journal = journal_factory(title=f"Gate 1 {fixture_path.stem}")
    moment = api_client.request(
        "POST",
        "/moments",
        token=api_user.access_token,
        json={
            "entry": {
                "title": fixture_path.stem,
                "journal_id": journal["id"],
                "content_delta": fixture,
            },
            "logged_timezone": "UTC",
        },
        expected=(200,),
    ).json()
    entry_id = moment["entry"]["id"]

    created = api_client.get_entry(api_user.access_token, entry_id)
    assert _without_null_attributes(created["content_delta"]) == fixture

    api_client.request(
        "PUT",
        f"/moments/{moment['id']}",
        token=api_user.access_token,
        json={
            "entry_update": {
                "title": fixture_path.stem,
                "content_delta": fixture,
            }
        },
        expected=(200,),
    )
    fetched = api_client.get_entry(api_user.access_token, entry_id)
    assert _without_null_attributes(fetched["content_delta"]) == fixture

    expected_plain_text = _plain_text(fixture)
    assert fetched["content_plain_text"] == expected_plain_text
    assert fetched["word_count"] == len(expected_plain_text.split())
