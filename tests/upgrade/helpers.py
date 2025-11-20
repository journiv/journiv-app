"""
Shared helper functions for upgrade tests built on top of the HTTP API client.

This module provides a singleton API client instance and convenience functions
for upgrade tests. The client is automatically managed and reused across calls.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict, Optional

from tests.lib import JournivApiClient


API_BASE_URL = os.getenv("JOURNIV_API_BASE_URL", "http://localhost:8000/api/v1")
_api_client: Optional[JournivApiClient] = None


def get_client() -> JournivApiClient:
    """Get or create the singleton API client instance."""
    global _api_client
    if _api_client is None:
        _api_client = JournivApiClient(base_url=API_BASE_URL)
    return _api_client


def refresh_client() -> None:
    """Force creation of a fresh API client (closes existing connections)."""
    global _api_client
    if _api_client is not None:
        _api_client.close()
    _api_client = None


def wait_for_ready(max_attempts: int = 60, delay: int = 2) -> None:
    """Block until the Journiv stack is healthy."""
    refresh_client()
    get_client().wait_for_health("/api/v1/health", timeout=max_attempts * delay)


def register_user(email: str, password: str, name: str) -> Dict[str, Any]:
    """Register a new user. Returns user data."""
    return get_client().register_user(email, password, name=name)


def login(email: str, password: str) -> str:
    """Login and return access token."""
    tokens = get_client().login(email, password)
    return tokens["access_token"]


def create_journal(token: str, title: str, color: str = "#3B82F6") -> Dict[str, Any]:
    """Create a journal. Returns journal data."""
    return get_client().create_journal(token, title=title, color=color)


def get_journals(token: str) -> list[Dict[str, Any]]:
    """Get all journals including archived ones."""
    return get_client().list_journals(token, include_archived=True)


def create_entry(
    token: str,
    journal_id: str,
    title: str,
    content: str,
    entry_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an entry. Defaults entry_date to today if not provided."""
    return get_client().create_entry(
        token,
        journal_id=journal_id,
        title=title,
        content=content,
        entry_date=entry_date or date.today().isoformat(),
    )


def get_entries(token: str) -> list[Dict[str, Any]]:
    """Get entries with a limit of 100."""
    return get_client().list_entries(token, limit=100)


def create_tag(token: str, name: str, color: str = "#10B981") -> Dict[str, Any]:
    """Create a tag. Returns tag data."""
    return get_client().create_tag(token, name=name, color=color)


def get_tags(token: str) -> list[Dict[str, Any]]:
    """Get all tags."""
    return get_client().list_tags(token)


def get_moods(token: str) -> list[Dict[str, Any]]:
    """Get all system moods."""
    return get_client().list_moods(token)


def create_mood_log(
    token: str,
    entry_id: str,
    mood_id: str,
    notes: str,
    logged_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a mood log. Defaults logged_date to today if not provided."""
    return get_client().create_mood_log(
        token,
        entry_id=entry_id,
        mood_id=mood_id,
        notes=notes,
        logged_date=logged_date or date.today().isoformat(),
    )


def get_mood_logs(token: str) -> list[Dict[str, Any]]:
    """Get all mood logs."""
    return get_client().list_mood_logs(token)


def upload_media(
    token: str,
    entry_id: str,
    filename: str,
    content: bytes,
    alt_text: str = "",
) -> Dict[str, Any]:
    """Upload media file. Defaults to image/jpeg content type."""
    return get_client().upload_media(
        token,
        entry_id=entry_id,
        filename=filename,
        content=content,
        content_type="image/jpeg",
        alt_text=alt_text,
    )


def get_user_settings(token: str) -> Dict[str, Any]:
    """Get current user settings/profile."""
    return get_client().current_user(token)


def http_get(endpoint: str, token: Optional[str] = None, params: Optional[Dict[str, Any]] = None):
    """Make a GET request. Returns httpx.Response."""
    return get_client().request("GET", endpoint, token=token, params=params)


def http_post(endpoint: str, data: Dict[str, Any], token: Optional[str] = None):
    """Make a POST request. Returns httpx.Response."""
    return get_client().request("POST", endpoint, token=token, json=data)


def http_put(endpoint: str, data: Dict[str, Any], token: Optional[str] = None):
    """Make a PUT request. Returns httpx.Response."""
    return get_client().request("PUT", endpoint, token=token, json=data)


def http_delete(endpoint: str, token: Optional[str] = None):
    """Make a DELETE request. Returns httpx.Response."""
    return get_client().request("DELETE", endpoint, token=token)
