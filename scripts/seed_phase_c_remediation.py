#!/usr/bin/env python3
"""Seed the reusable Phase C browser-test account through the public API."""

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_API_URL = "http://127.0.0.1:8011/api/v1"
DEFAULT_EMAIL = "phase-c-remediation@example.com"
DEFAULT_PASSWORD = "PhaseC-Remediation-2026!"


def api_request(
    api_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}{path}", body, headers, method=method
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def login(api_url: str, email: str, password: str) -> str:
    response = api_request(
        api_url,
        "POST",
        "/auth/login",
        {"email": email, "password": password},
    )
    return str(response["access_token"])


def ensure_account(api_url: str, email: str, password: str) -> tuple[str, bool]:
    try:
        return login(api_url, email, password), False
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise

    try:
        api_request(
            api_url,
            "POST",
            "/auth/register",
            {"email": email, "password": password, "name": "Phase C Remediation"},
        )
    except urllib.error.HTTPError as error:
        if error.code == 400:
            raise SystemExit(
                "The account already exists but the configured password was rejected. "
                "Use the database that was originally seeded or choose another --email."
            ) from error
        raise
    return login(api_url, email, password), True


def ensure_journal(
    api_url: str,
    token: str,
    journals: list[dict[str, Any]],
    title: str,
) -> tuple[dict[str, Any], bool]:
    existing = next((journal for journal in journals if journal["title"] == title), None)
    if existing:
        return existing, False
    journal = api_request(api_url, "POST", "/journals/", {"title": title}, token)
    journals.append(journal)
    return journal, True


def fixture_entries() -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            "Gate 1 valid document",
            {
                "ops": [
                    {"insert": "Gate 1 heading"},
                    {"insert": "\n", "attributes": {"header": 1}},
                    {"insert": "Editable bold text", "attributes": {"bold": True}},
                    {"insert": "\n"},
                    {"insert": "A quotation"},
                    {"insert": "\n", "attributes": {"blockquote": True}},
                ]
            },
        ),
        (
            "Unsupported image embed",
            {
                "ops": [
                    {"insert": "Plain text before image.\n"},
                    {"insert": {"image": "legacy-image-id"}},
                    {"insert": "\n"},
                ]
            },
        ),
        (
            "Unsupported colored text",
            {
                "ops": [
                    {
                        "insert": "Legacy colored text",
                        "attributes": {"color": "#ff0000"},
                    },
                    {"insert": "\n"},
                ]
            },
        ),
    ]


def seed(api_url: str, email: str, password: str, timezone: str) -> None:
    token, account_created = ensure_account(api_url, email, password)
    journals = api_request(api_url, "GET", "/journals/", token=token)
    source, source_created = ensure_journal(
        api_url, token, journals, "Phase C Source"
    )
    _, destination_created = ensure_journal(
        api_url, token, journals, "Phase C Destination"
    )

    query = urllib.parse.urlencode({"limit": 200, "include_empty": "true"})
    moments = api_request(api_url, "GET", f"/moments?{query}", token=token)["items"]
    existing_titles = {
        moment["entry"]["title"]
        for moment in moments
        if moment.get("entry") and moment["entry"].get("title")
    }

    created_entries: list[str] = []
    for title, delta in fixture_entries():
        if title in existing_titles:
            continue
        api_request(
            api_url,
            "POST",
            "/moments",
            {
                "logged_timezone": timezone,
                "entry": {
                    "title": title,
                    "journal_id": source["id"],
                    "content_delta": delta,
                },
            },
            token,
        )
        created_entries.append(title)

    print(f"Account: {'created' if account_created else 'already present'}")
    print(
        "Journals: "
        f"Phase C Source ({'created' if source_created else 'present'}), "
        f"Phase C Destination ({'created' if destination_created else 'present'})"
    )
    print(
        "Entries: "
        + (", ".join(created_entries) if created_entries else "all already present")
    )
    print(f"Login verified for {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--timezone", default="America/Los_Angeles")
    args = parser.parse_args()
    try:
        seed(args.api_url, args.email, args.password, args.timezone)
    except urllib.error.HTTPError as error:
        raise SystemExit(
            f"Journiv API request failed with HTTP {error.code}. "
            "Check the backend terminal for details."
        ) from None
    except urllib.error.URLError as error:
        raise SystemExit(
            f"Cannot connect to the Journiv API at {args.api_url}. "
            "Start the backend on port 8011 first, then rerun this command. "
            f"Connection error: {error.reason}"
        ) from None


if __name__ == "__main__":
    main()
