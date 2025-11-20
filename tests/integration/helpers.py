"""
Utility helpers shared across the integration test suite.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from tests.lib import JournivApiClient


UNKNOWN_UUID = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True)
class EndpointCase:
    """
    Declarative representation of an endpoint invocation used by helpers.
    """

    method: str
    path: str
    json: dict[str, Any] | None = None
    params: dict[str, Any] | None = None
    data: dict[str, Any] | None = None
    files: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    description: str | None = None

    def label(self) -> str:
        return self.description or f"{self.method} {self.path}"


def _exercise_cases(
    api_client: JournivApiClient,
    cases: Iterable[EndpointCase],
    *,
    token: str | None = None,
):
    for case in cases:
        request_kwargs: dict[str, Any] = {}
        if case.json is not None:
            request_kwargs["json"] = case.json
        if case.params is not None:
            request_kwargs["params"] = case.params
        if case.data is not None:
            request_kwargs["data"] = case.data
        if case.files is not None:
            request_kwargs["files"] = case.files
        if case.headers is not None:
            request_kwargs["headers"] = case.headers

        response = api_client.request(
            case.method,
            case.path,
            token=token,
            **request_kwargs,
        )
        yield case, response


def _format_failure(case: EndpointCase, received: int, expected: Sequence[int]) -> str:
    return f"{case.label()} returned {received}, expected one of {tuple(expected)}"


def assert_status_codes(
    api_client: JournivApiClient,
    cases: Iterable[EndpointCase],
    *,
    token: str | None = None,
    expected_status: Sequence[int] = (200,),
):
    """
    Execute a batch of endpoint cases asserting their HTTP status codes.
    """
    responses = []
    for case, response in _exercise_cases(api_client, cases, token=token):
        assert (
            response.status_code in expected_status
        ), _format_failure(case, response.status_code, expected_status)
        responses.append(response)
    return responses


def assert_requires_authentication(
    api_client: JournivApiClient, cases: Iterable[EndpointCase]
) -> None:
    """
    Assert that each endpoint rejects anonymous callers with HTTP 401.
    """
    assert_status_codes(api_client, cases, expected_status=(401,))


def assert_not_found(
    api_client: JournivApiClient,
    token: str,
    cases: Iterable[EndpointCase],
) -> None:
    """
    Assert that each endpoint returns HTTP 404 for missing identifiers.
    """
    assert_status_codes(api_client, cases, token=token, expected_status=(404,))


def sample_jpeg_bytes() -> bytes:
    """Provide a valid, tiny JPEG payload accepted by the media endpoints."""
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07"
        b"\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
        b"\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        b"\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00?\x00\xff\xd9"
    )
