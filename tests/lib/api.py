"""
Shared HTTP client utilities for integration and upgrade tests.

Provides a small wrapper around httpx with high level helpers for the
resources that the integration and upgrade suites exercise.
"""
from __future__ import annotations

import io
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.utils.quill_delta import wrap_plain_text


DEFAULT_BASE_URL = "http://localhost:8000/api/v1"


def _wrap_content_to_delta(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convert plain 'content' field to 'content_delta' Quill format if present."""
    if "content" in payload:
        content = payload.pop("content")
        payload["content_delta"] = wrap_plain_text(content)
    return payload


def _normalize_base_url(value: str | None) -> str:
    """Ensure the API base URL never contains a trailing slash."""
    if not value:
        return DEFAULT_BASE_URL
    return value.rstrip("/")


class JournivApiError(RuntimeError):
    """Raised when an API call does not return an expected status code."""

    def __init__(self, method: str, path: str, status: int, body: str):
        super().__init__(f"{method} {path} returned {status}: {body}")
        self.method = method
        self.path = path
        self.status = status
        self.body = body


@dataclass
class ApiUser:
    """Represents a user created via the API."""

    email: str
    password: str
    access_token: str
    refresh_token: Optional[str]
    user_id: str

    def auth_header(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


class JournivApiClient:
    """
    Thin wrapper around httpx.Client that provides ergonomic helpers.

    Tests should stick to these helpers instead of hand crafting requests.
    This keeps assertions consistent and drastically simplifies rewrites.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = _normalize_base_url(
            base_url or os.getenv("JOURNIV_API_BASE_URL")
        )
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        parsed = urlsplit(self.base_url)
        self._service_root = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

    # ------------------------------------------------------------------ #
    # Generic request helpers
    # ------------------------------------------------------------------ #
    def close(self) -> None:
        self._client.close()

    def wait_for_health(self, endpoint: str = "/health", *, timeout: int = 60) -> None:
        """
        Poll the health endpoint until the application is ready.

        Upgrade tests invoke this before seeding/verifying data to avoid
        spurious failures while the containers are still booting.
        """
        deadline = time.time() + timeout
        last_exc: Optional[Exception] = None
        target = self._absolute_url(endpoint)
        while time.time() < deadline:
            try:
                response = self._client.get(target)
                if response.status_code == 200:
                    return
            except Exception as exc:
                last_exc = exc
            time.sleep(1)

        raise RuntimeError(
            f"Health check {endpoint} did not succeed within {timeout}s"
        ) from last_exc

    def request(
        self,
        method: str,
        path: str,
        *,
        token: Optional[str] = None,
        expected: Iterable[int] | None = None,
        absolute: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = self._absolute_url(path) if absolute else path
        response = self._client.request(method, url, headers=headers, **kwargs)
        if expected and response.status_code not in expected:
            raise JournivApiError(method, path, response.status_code, response.text)
        return response

    def _absolute_url(self, endpoint: str) -> str:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        return f"{self._service_root}{endpoint}"

    # ------------------------------------------------------------------ #
    # Authentication helpers
    # ------------------------------------------------------------------ #
    def register_user(
        self,
        email: str,
        password: str,
        *,
        name: str = "Test User",
    ) -> Dict[str, Any]:
        response = self.request(
            "POST",
            "/auth/register",
            json={
                "email": email,
                "password": password,
                "name": name,
            },
            expected=(200, 201),
        )
        return response.json()

    def login(self, email: str, password: str) -> Dict[str, Any]:
        response = self.request(
            "POST",
            "/auth/login",
            json={"email": email, "password": password},
            expected=(200,),
        )
        return response.json()

    def refresh(self, refresh_token: str) -> Dict[str, Any]:
        response = self.request(
            "POST",
            "/auth/refresh",
            json={"refresh_token": refresh_token},
            expected=(200,),
        )
        return response.json()

    def current_user(self, token: str) -> Dict[str, Any]:
        return self.request("GET", "/users/me", token=token, expected=(200,)).json()

    def update_profile(self, token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.request(
            "PUT", "/users/me", token=token, json=payload, expected=(200,)
        ).json()

    def delete_account(self, token: str) -> Dict[str, Any]:
        return self.request(
            "DELETE", "/users/me", token=token, expected=(200,)
        ).json()

    def get_user_settings(self, token: str) -> Dict[str, Any]:
        return self.request(
            "GET", "/users/me/settings", token=token, expected=(200,)
        ).json()

    def update_user_settings(self, token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.request(
            "PUT",
            "/users/me/settings",
            token=token,
            json=payload,
            expected=(200,),
        ).json()

    # ------------------------------------------------------------------ #
    # Journal helpers
    # ------------------------------------------------------------------ #
    def create_journal(
        self,
        token: str,
        *,
        title: str,
        color: str = "#3B82F6",
        description: str = "Created from tests",
        icon: str = "📝",
    ) -> Dict[str, Any]:
        response = self.request(
            "POST",
            "/journals/",
            token=token,
            json={
                "title": title,
                "description": description,
                "color": color,
                "icon": icon,
            },
            expected=(201,),
        )
        return response.json()

    def list_journals(self, token: str, **params: Any) -> list[Dict[str, Any]]:
        response = self.request("GET", "/journals/", token=token, params=params, expected=(200,))
        return response.json()

    def get_journal(self, token: str, journal_id: str) -> Dict[str, Any]:
        response = self.request(
            "GET", f"/journals/{journal_id}", token=token, expected=(200,)
        )
        return response.json()

    def update_journal(
        self,
        token: str,
        journal_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        response = self.request(
            "PUT",
            f"/journals/{journal_id}",
            token=token,
            json=payload,
            expected=(200,),
        )
        return response.json()

    def archive_journal(self, token: str, journal_id: str) -> Dict[str, Any]:
        response = self.request(
            "POST",
            f"/journals/{journal_id}/archive",
            token=token,
            expected=(200,),
        )
        return response.json()

    def unarchive_journal(self, token: str, journal_id: str) -> Dict[str, Any]:
        response = self.request(
            "POST",
            f"/journals/{journal_id}/unarchive",
            token=token,
            expected=(200,),
        )
        return response.json()

    def delete_journal(self, token: str, journal_id: str) -> None:
        self.request(
            "DELETE",
            f"/journals/{journal_id}",
            token=token,
            expected=(200, 204),
        )

    # ------------------------------------------------------------------ #
    # Entry helpers
    # ------------------------------------------------------------------ #
    def create_entry(
        self,
        token: str,
        *,
        journal_id: str,
        title: str,
        content: str,
        entry_date: str,
        **extra: Any,
    ) -> Dict[str, Any]:
        payload = {
            "title": title,
            "content": content,
            "journal_id": journal_id,
            "entry_date": entry_date,
        }
        payload.update(extra)
        payload = _wrap_content_to_delta(payload)
        response = self.request(
            "POST",
            "/entries/",
            token=token,
            json=payload,
            expected=(201,),
        )
        return response.json()

    def list_entries(self, token: str, **params: Any) -> list[Dict[str, Any]]:
        response = self.request(
            "GET", "/entries/", token=token, params=params, expected=(200,)
        )
        data = response.json()
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        return data

    def get_entry(self, token: str, entry_id: str) -> Dict[str, Any]:
        return self.request(
            "GET", f"/entries/{entry_id}", token=token, expected=(200,)
        ).json()

    def update_entry(
        self, token: str, entry_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        payload = _wrap_content_to_delta(payload.copy())
        return self.request(
            "PUT",
            f"/entries/{entry_id}",
            token=token,
            json=payload,
            expected=(200,),
        ).json()

    def delete_entry(self, token: str, entry_id: str) -> None:
        self.request(
            "DELETE",
            f"/entries/{entry_id}",
            token=token,
            expected=(200, 204),
        )

    def pin_entry(self, token: str, entry_id: str) -> Dict[str, Any]:
        return self.request(
            "POST",
            f"/entries/{entry_id}/pin",
            token=token,
            expected=(200,),
        ).json()

    def unpin_entry(self, token: str, entry_id: str) -> Dict[str, Any]:
        return self.request(
            "POST",
            f"/entries/{entry_id}/pin",
            token=token,
            expected=(200,),
        ).json()

    # ------------------------------------------------------------------ #
    # Tag helpers
    # ------------------------------------------------------------------ #
    def create_tag(self, token: str, *, name: str, color: str = "#22C55E") -> Dict[str, Any]:
        return self.request(
            "POST",
            "/tags/",
            token=token,
            json={"name": name, "color": color},
            expected=(201,),
        ).json()

    def list_tags(self, token: str, **params: Any) -> list[Dict[str, Any]]:
        return self.request(
            "GET", "/tags/", token=token, params=params, expected=(200,)
        ).json()

    def update_tag(self, token: str, tag_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.request(
            "PUT",
            f"/tags/{tag_id}",
            token=token,
            json=payload,
            expected=(200,),
        ).json()

    def delete_tag(self, token: str, tag_id: str) -> None:
        self.request("DELETE", f"/tags/{tag_id}", token=token, expected=(200, 204))

    def search_tags(self, token: str, query: str) -> list[Dict[str, Any]]:
        return self.request(
            "GET",
            "/tags/search",
            token=token,
            params={"q": query},
            expected=(200,),
        ).json()

    def popular_tags(self, token: str, limit: int = 5) -> list[Dict[str, Any]]:
        return self.request(
            "GET",
            "/tags/popular",
            token=token,
            params={"limit": limit},
            expected=(200,),
        ).json()

    # ------------------------------------------------------------------ #
    # Activity group helpers
    # ------------------------------------------------------------------ #
    def create_activity_group(
        self,
        token: str,
        *,
        name: str,
        color_value: Optional[int] = None,
        icon: Optional[str] = None,
        position: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"name": name}
        if color_value is not None:
            payload["color_value"] = color_value
        if icon is not None:
            payload["icon"] = icon
        if position is not None:
            payload["position"] = position
        return self.request(
            "POST",
            "/activity-groups/",
            token=token,
            json=payload,
            expected=(201,),
        ).json()

    def list_activity_groups(self, token: str) -> list[Dict[str, Any]]:
        return self.request(
            "GET",
            "/activity-groups/",
            token=token,
            expected=(200,),
        ).json()

    def reorder_activity_groups(
        self, token: str, updates: list[Dict[str, Any]]
    ) -> None:
        self.request(
            "PUT",
            "/activity-groups/reorder",
            token=token,
            json={"updates": updates},
            expected=(204,),
        )

    # ------------------------------------------------------------------ #
    # Activity helpers
    # ------------------------------------------------------------------ #
    def create_activity(
        self,
        token: str,
        *,
        name: str,
        group_id: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        position: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"name": name}
        if group_id is not None:
            payload["group_id"] = group_id
        if icon is not None:
            payload["icon"] = icon
        if color is not None:
            payload["color"] = color
        if position is not None:
            payload["position"] = position
        return self.request(
            "POST",
            "/activities",
            token=token,
            json=payload,
            expected=(200, 201),
        ).json()

    def list_activities(
        self, token: str, *, limit: int = 50, offset: int = 0
    ) -> list[Dict[str, Any]]:
        return self.request(
            "GET",
            "/activities",
            token=token,
            params={"limit": limit, "offset": offset},
            expected=(200,),
        ).json()

    # ------------------------------------------------------------------ #
    # Mood helpers
    # ------------------------------------------------------------------ #
    def list_moods(
        self,
        token: str,
        *,
        category: Optional[str] = None,
        include_hidden: bool = False,
    ) -> list[Dict[str, Any]]:
        params: Dict[str, Any] = {"include_hidden": include_hidden}
        if category is not None:
            params["category"] = category
        return self.request(
            "GET",
            "/moods/",
            token=token,
            params=params,
            expected=(200,),
        ).json()

    def get_moods_by_name(
        self,
        token: str,
        *,
        name: str,
        include_hidden: bool = False,
    ) -> list[Dict[str, Any]]:
        moods = self.list_moods(token, include_hidden=include_hidden)
        return [mood for mood in moods if mood.get("name") == name]

    def get_mood_by_name(
        self,
        token: str,
        *,
        name: str,
        include_hidden: bool = False,
    ) -> Optional[Dict[str, Any]]:
        matches = self.get_moods_by_name(
            token,
            name=name,
            include_hidden=include_hidden,
        )
        return matches[0] if matches else None

    def create_mood(
        self,
        token: str,
        *,
        name: str,
        score: int = 3,
        icon: Optional[str] = None,
        color_value: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"name": name, "score": score}
        if icon is not None:
            payload["icon"] = icon
        if color_value is not None:
            payload["color_value"] = color_value
        return self.request(
            "POST",
            "/moods/",
            token=token,
            json=payload,
            expected=(201,),
        ).json()

    def reorder_moods(self, token: str, mood_ids: list[str]) -> None:
        self.request(
            "PUT",
            "/moods/reorder",
            token=token,
            json={"mood_ids": mood_ids},
            expected=(204,),
        )

    def set_mood_visibility(self, token: str, mood_id: str, *, is_hidden: bool) -> None:
        self.request(
            "POST",
            f"/moods/{mood_id}/visibility",
            token=token,
            json={"is_hidden": is_hidden},
            expected=(204,),
        )

    # ------------------------------------------------------------------ #
    # Mood group helpers
    # ------------------------------------------------------------------ #
    def create_mood_group(
        self,
        token: str,
        *,
        name: str,
        mood_ids: Optional[list[str]] = None,
        icon: Optional[str] = None,
        color_value: Optional[int] = None,
        position: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"name": name}
        if mood_ids is not None:
            payload["mood_ids"] = mood_ids
        if icon is not None:
            payload["icon"] = icon
        if color_value is not None:
            payload["color_value"] = color_value
        if position is not None:
            payload["position"] = position
        return self.request(
            "POST",
            "/moods/groups",
            token=token,
            json=payload,
            expected=(201,),
        ).json()

    def list_mood_groups(
        self, token: str, *, include_hidden: bool = False
    ) -> list[Dict[str, Any]]:
        return self.request(
            "GET",
            "/moods/groups",
            token=token,
            params={"include_hidden": include_hidden},
            expected=(200,),
        ).json()

    def get_mood_groups_by_name(
        self,
        token: str,
        *,
        name: str,
        include_hidden: bool = False,
    ) -> list[Dict[str, Any]]:
        groups = self.list_mood_groups(token, include_hidden=include_hidden)
        return [group for group in groups if group.get("name") == name]

    def get_mood_group_by_name(
        self,
        token: str,
        *,
        name: str,
        include_hidden: bool = False,
    ) -> Optional[Dict[str, Any]]:
        matches = self.get_mood_groups_by_name(
            token,
            name=name,
            include_hidden=include_hidden,
        )
        return matches[0] if matches else None

    def reorder_mood_groups(self, token: str, updates: list[Dict[str, Any]]) -> None:
        self.request(
            "PUT",
            "/moods/groups/reorder",
            token=token,
            json={"updates": updates},
            expected=(204,),
        )

    def reorder_mood_group_moods(
        self, token: str, group_id: str, mood_ids: list[str]
    ) -> None:
        self.request(
            "PUT",
            f"/moods/groups/{group_id}/moods/reorder",
            token=token,
            json={"mood_ids": mood_ids},
            expected=(204,),
        )

    def set_mood_group_visibility(
        self, token: str, group_id: str, *, is_hidden: bool
    ) -> None:
        self.request(
            "PUT",
            f"/moods/groups/{group_id}/visibility",
            token=token,
            json={"is_hidden": is_hidden},
            expected=(204,),
        )

    # ------------------------------------------------------------------ #
    # Moment helpers
    # ------------------------------------------------------------------ #
    def create_moment(
        self,
        token: str,
        *,
        logged_date: Optional[str] = None,
        primary_mood_id: Optional[str] = None,
        note: str | None = None,
        mood_activity: Optional[list[Dict[str, Any]]] = None,
        logged_timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if logged_date is not None:
            payload["logged_date"] = logged_date
        if logged_timezone is not None:
            payload["logged_timezone"] = logged_timezone
        if note is not None:
            payload["note"] = note
        if primary_mood_id is not None:
            payload["primary_mood_id"] = primary_mood_id
            if mood_activity is None:
                mood_activity = [{"mood_id": primary_mood_id}]
        if mood_activity is not None:
            payload["mood_activity"] = mood_activity
        return self.request(
            "POST",
            "/moments",
            token=token,
            json=payload,
            expected=(200, 201),
        ).json()

    def list_moments(self, token: str, **params: Any) -> list[Dict[str, Any]]:
        response = self.request(
            "GET",
            "/moments",
            token=token,
            params=params,
            expected=(200,),
        ).json()
        return response.get("items", [])

    # ------------------------------------------------------------------ #
    # Goal helpers
    # ------------------------------------------------------------------ #
    def create_goal_category(
        self,
        token: str,
        *,
        name: str,
        color_value: Optional[int] = None,
        icon: Optional[str] = None,
        position: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"name": name}
        if color_value is not None:
            payload["color_value"] = color_value
        if icon is not None:
            payload["icon"] = icon
        if position is not None:
            payload["position"] = position
        return self.request(
            "POST",
            "/goal-categories",
            token=token,
            json=payload,
            expected=(200, 201),
        ).json()

    def list_goal_categories(self, token: str) -> list[Dict[str, Any]]:
        return self.request(
            "GET",
            "/goal-categories",
            token=token,
            expected=(200,),
        ).json()

    def create_goal(
        self,
        token: str,
        *,
        title: str,
        activity_id: Optional[str] = None,
        category_id: Optional[str] = None,
        goal_type: str = "achieve",
        frequency_type: str = "daily",
        target_count: int = 1,
        reminder_time: Optional[str] = None,
        is_paused: bool = False,
        icon: Optional[str] = None,
        color_value: Optional[int] = None,
        position: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "title": title,
            "goal_type": goal_type,
            "frequency_type": frequency_type,
            "target_count": target_count,
            "is_paused": is_paused,
        }
        if activity_id is not None:
            payload["activity_id"] = activity_id
        if category_id is not None:
            payload["category_id"] = category_id
        if reminder_time is not None:
            payload["reminder_time"] = reminder_time
        if icon is not None:
            payload["icon"] = icon
        if color_value is not None:
            payload["color_value"] = color_value
        if position is not None:
            payload["position"] = position
        return self.request(
            "POST",
            "/goals",
            token=token,
            json=payload,
            expected=(200, 201),
        ).json()

    def list_goals(
        self, token: str, *, include_archived: bool = False
    ) -> list[Dict[str, Any]]:
        return self.request(
            "GET",
            "/goals",
            token=token,
            params={"include_archived": include_archived},
            expected=(200,),
        ).json()

    def toggle_goal(
        self,
        token: str,
        goal_id: str,
        *,
        logged_date: str,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"logged_date": logged_date}
        if status is not None:
            payload["status"] = status
        return self.request(
            "POST",
            f"/goals/{goal_id}/toggle",
            token=token,
            json=payload,
            expected=(200,),
        ).json()

    # ------------------------------------------------------------------ #
    # Prompt helpers
    # ------------------------------------------------------------------ #
    def create_prompt(
        self,
        token: str,
        *,
        text: str,
        category: str = "general",
        difficulty_level: str = "easy",
        estimated_time_minutes: int = 5,
    ) -> Dict[str, Any]:
        payload = {
            "text": text,
            "category": category,
            "difficulty_level": difficulty_level,
            "estimated_time_minutes": estimated_time_minutes,
            "is_active": True,
        }
        return self.request(
            "POST", "/prompts/", token=token, json=payload, expected=(201,)
        ).json()

    def list_prompts(self, token: str, **params: Any) -> list[Dict[str, Any]]:
        return self.request(
            "GET", "/prompts/", token=token, params=params, expected=(200,)
        ).json()

    def update_prompt(
        self, token: str, prompt_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        return self.request(
            "PUT",
            f"/prompts/{prompt_id}",
            token=token,
            json=payload,
            expected=(200,),
        ).json()

    def delete_prompt(self, token: str, prompt_id: str) -> None:
        self.request("DELETE", f"/prompts/{prompt_id}", token=token, expected=(200, 204))

    # ------------------------------------------------------------------ #
    # Media helpers
    # ------------------------------------------------------------------ #
    def upload_media(
        self,
        token: str,
        *,
        entry_id: str,
        filename: str,
        content: bytes,
        content_type: str,
        alt_text: str = "",
    ) -> Dict[str, Any]:
        files = {
            "file": (filename, io.BytesIO(content), content_type),
        }
        data = {"entry_id": entry_id, "alt_text": alt_text}
        return self.request(
            "POST",
            "/media/upload",
            token=token,
            files=files,
            data=data,
            expected=(201,),
        ).json()

    def wait_for_media_ready(self, token: str, media_id: str, *, timeout: int = 10) -> None:
        """
        Poll the media endpoint until upload_status is COMPLETED.

        Media processing happens asynchronously, so tests need to wait
        for the media to be ready before attempting to fetch it.

        Args:
            token: Authentication token
            media_id: UUID of the media to wait for
            timeout: Maximum seconds to wait (default: 10)

        Raises:
            RuntimeError: If media doesn't become ready within timeout
        """
        deadline = time.time() + timeout
        last_status = None

        while time.time() < deadline:
            try:
                # Try to get signed URL - this will fail if media is not ready
                response = self.request(
                    "GET", f"/media/{media_id}/sign", token=token, expected=(200, 400)
                )

                if response.status_code == 200:
                    # Media is ready
                    return

                # Parse error to check if it's "Media not ready"
                if response.status_code == 400:
                    error_data = response.json()
                    if "not ready" in error_data.get("detail", "").lower():
                        last_status = "pending"
                        time.sleep(0.1)  # Wait 100ms before retrying
                        continue
                    # Some other 400 error - raise it
                    raise JournivApiError("GET", f"/media/{media_id}/sign", 400, response.text)

            except JournivApiError:
                raise

        raise RuntimeError(
            f"Media {media_id} did not become ready within {timeout}s (last status: {last_status})"
        )

    def get_media(self, token: str, media_id: str, *, wait_for_ready: bool = True) -> httpx.Response:
        """
        Get media file content.

        Args:
            token: Authentication token
            media_id: UUID of the media to fetch
            wait_for_ready: If True, wait for media processing to complete before fetching

        Returns:
            HTTP response with media file content
        """
        # Wait for media to be ready if requested
        if wait_for_ready:
            self.wait_for_media_ready(token, media_id)

        # Get signed URL
        sign_response = self.request(
            "GET", f"/media/{media_id}/sign", token=token, expected=(200,)
        ).json()
        signed_url = sign_response["signed_url"]

        # Convert to absolute URL properly
        full_url = self._absolute_url(signed_url)

        # Use underlying client to fetch signed URL (no auth header needed)
        # Using absolute URL overrides the client's base_url
        return self._client.get(full_url)

    # ------------------------------------------------------------------ #
    # Import / export helpers
    # ------------------------------------------------------------------ #
    def request_export(
        self,
        token: str,
        *,
        export_type: str = "full",
        journal_ids: Optional[list[str]] = None,
        include_media: bool = False,
        expected: Iterable[int] | None = (202,),
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "export_type": export_type,
            "include_media": include_media,
        }
        if journal_ids:
            payload["journal_ids"] = journal_ids
        return self.request(
            "POST",
            "/export/",
            token=token,
            json=payload,
            expected=expected,
        ).json()

    def export_status(self, token: str, job_id: str) -> Dict[str, Any]:
        return self.request(
            "GET", f"/export/{job_id}", token=token, expected=(200,)
        ).json()

    def upload_import(
        self,
        token: str,
        *,
        file_bytes: bytes,
        filename: str = "import.zip",
        source_type: str = "journiv",
        expected: Iterable[int] | None = None,
    ) -> httpx.Response:
        files = {"file": (filename, io.BytesIO(file_bytes), "application/zip")}
        data = {"source_type": source_type}
        return self.request(
            "POST",
            "/import/upload",
            token=token,
            files=files,
            data=data,
            expected=expected,
        )

    def import_status(self, token: str, job_id: str) -> Dict[str, Any]:
        return self.request(
            "GET", f"/import/{job_id}", token=token, expected=(200,)
        ).json()

    def list_imports(self, token: str, **params: Any) -> list[Dict[str, Any]]:
        return self.request(
            "GET", "/import/", token=token, params=params, expected=(200,)
        ).json()

    def delete_import(self, token: str, job_id: str) -> None:
        self.request(
            "DELETE",
            f"/import/{job_id}",
            token=token,
            expected=(204,),
        )


def make_api_user(api: JournivApiClient) -> ApiUser:
    """
    Register and log in a brand new user for a test case.
    """
    unique_suffix = uuid.uuid4().hex[:10]
    email = f"pytest-{unique_suffix}@example.com"
    password = f"Test-{unique_suffix}-Aa1!"

    api.register_user(email, password)
    token_payload = api.login(email, password)
    access_token = token_payload["access_token"]
    refresh_token = token_payload.get("refresh_token")
    profile = api.current_user(access_token)

    return ApiUser(
        email=email,
        password=password,
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=profile["id"],
    )
