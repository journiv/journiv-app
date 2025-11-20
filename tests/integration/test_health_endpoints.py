"""
Health check verification against the running stack.
"""
import time

import pytest

from tests.lib import JournivApiClient


def _get_health(api_client: JournivApiClient):
    response = api_client.request("GET", "/health")
    assert response.status_code == 200
    payload = response.json()
    assert "status" in payload
    assert "database" in payload
    assert "version" in payload
    return payload


def _get_memory(api_client: JournivApiClient):
    response = api_client.request("GET", "/memory")
    assert response.status_code == 200
    payload = response.json()
    assert "status" in payload
    assert "timestamp" in payload
    assert "system_memory" in payload
    assert "process_memory" in payload
    return payload

def test_health_endpoint_reports_status(api_client: JournivApiClient):
    """The exposed health endpoint should report healthy status."""
    payload = _get_health(api_client)
    assert payload["status"] in {"healthy", "degraded"}
    assert "connected" in payload["database"]


def test_health_endpoint_is_fast(api_client: JournivApiClient):
    """Response time should stay within a snappy SLA."""
    start = time.time()
    _get_health(api_client)
    duration = time.time() - start
    assert duration < 2.0


def test_health_timestamp_format(api_client: JournivApiClient):
    """Timestamp should be ISO 8601 formatted."""
    payload = _get_health(api_client)
    timestamp = payload["timestamp"]
    assert "T" in timestamp
    assert timestamp.endswith("Z") or "+" in timestamp



@pytest.mark.parametrize("path", ["/health", "/memory"])
def test_health_endpoints_accessible_without_auth(api_client: JournivApiClient, path: str):
    """Public health checks should not require authentication."""
    response = api_client.request("GET", path)
    assert response.status_code == 200
