"""
Pytest fixtures shared across the integration and upgrade suites.

All integration tests must exercise the running Journiv stack through the
public HTTP API.
"""
from __future__ import annotations

import os
import uuid
from datetime import date
from typing import Callable, Dict

import pytest

from tests.lib import ApiUser, JournivApiClient, make_api_user


@pytest.fixture(scope="session")
def api_client() -> JournivApiClient:
    """
    Session scoped API client against the running Journiv instance.

    The base URL can be overridden through JOURNIV_API_BASE_URL.  CI sets
    it to http://localhost:8000/api/v1 which points to the docker compose
    stack started in the workflows.
    """
    base_url = os.getenv("JOURNIV_API_BASE_URL")
    client = JournivApiClient(base_url=base_url)

    # Wait for health once per session to fail fast if the stack is broken.
    client.wait_for_health("/api/v1/health")

    yield client
    client.close()


@pytest.fixture
def api_user(api_client: JournivApiClient) -> ApiUser:
    """
    Create a unique test user via the public API.
    """
    return make_api_user(api_client)


@pytest.fixture
def journal_factory(
    api_client: JournivApiClient, api_user: ApiUser
) -> Callable[..., Dict]:
    """
    Factory that creates journals owned by the current test user.
    """

    def _create(**overrides: Dict) -> Dict:
        title = overrides.pop("title", f"Journal {uuid.uuid4().hex[:6]}")
        journal = api_client.create_journal(
            api_user.access_token,
            title=title,
            color=overrides.pop("color", "#3B82F6"),
            description=overrides.pop(
                "description", "Journal created during integration tests"
            ),
            icon=overrides.pop("icon", "📝"),
        )
        return journal

    return _create


@pytest.fixture
def entry_factory(
    api_client: JournivApiClient, api_user: ApiUser, journal_factory: Callable[..., Dict]
) -> Callable[..., Dict]:
    """
    Factory that creates entries ensuring the journal exists.
    """

    def _create(**overrides: Dict) -> Dict:
        journal = overrides.pop("journal", None)
        if journal is None:
            journal = journal_factory()

        entry = api_client.create_entry(
            api_user.access_token,
            journal_id=journal["id"],
            title=overrides.pop("title", f"Entry {uuid.uuid4().hex[:6]}"),
            content=overrides.pop(
                "content", "Content written by the integration test suite."
            ),
            entry_date=overrides.pop(
                "entry_date", date.today().isoformat()
            ),
            **overrides,
        )
        entry["journal"] = journal
        return entry

    return _create
