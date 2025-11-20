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


DEFAULT_BASE_URL = "http://localhost:8000/api/v1"


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

    def tag_statistics(self, token: str) -> Dict[str, Any]:
        return self.request(
            "GET", "/tags/statistics", token=token, expected=(200,)
        ).json()

    # ------------------------------------------------------------------ #
    # Mood helpers
    # ------------------------------------------------------------------ #
    def list_moods(self, token: str) -> list[Dict[str, Any]]:
        return self.request("GET", "/moods/", token=token, expected=(200,)).json()

    def create_mood_log(
        self,
        token: str,
        *,
        entry_id: str,
        mood_id: str,
        logged_date: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        return self.request(
            "POST",
            "/moods/log",
            token=token,
            json={
                "entry_id": entry_id,
                "mood_id": mood_id,
                "logged_date": logged_date,
                "notes": notes,
            },
            expected=(201,),
        ).json()

    def list_mood_logs(self, token: str) -> list[Dict[str, Any]]:
        data = self.request("GET", "/moods/logs", token=token, expected=(200,)).json()
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        return data

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

    def get_media(self, token: str, media_id: str) -> httpx.Response:
        return self.request(
            "GET", f"/media/{media_id}", token=token, expected=(200,)
        )

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
