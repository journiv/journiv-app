"""
SSRF regression tests for the Immich integration's base_url handling.

Two layers under test:
  1. Primary: only an admin may set a custom base_url at all (see
     TestConnectIntegrationBaseUrlAuthorization) - the shipped UI never sends
     one, so this removes the attacker-controlled-destination precondition
     entirely for regular users.
  2. Defense in depth: the asset-proxy client (the piece that follows
     redirects and streams the response back to the caller) re-validates its
     destination on every request - including each redirect hop - and
     connects to the validated address directly, so a compromised or
     DNS-rebound admin-configured host still can't be redirected into
     fetching and leaking a different internal address (see
     TestSSRFProtectedTransport).
"""
import ipaddress
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.ssrf_guard import (
    ALLOWED_HOST_EXTENSION,
    ALLOWED_SCHEME_EXTENSION,
    SSRFError,
    SSRFProtectedTransport,
    assert_host_is_safe,
)
from app.integrations.service import connect_integration
from app.models.enums import UserRole
from app.models.integration import IntegrationProvider


class TestSSRFGuard:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "host",
        [
            "127.0.0.1",
            "localhost",
            "169.254.169.254",  # AWS/GCP/Azure/DigitalOcean cloud metadata
            "169.254.170.2",  # ECS task metadata
            "::1",
            "0.0.0.0",
            "100.100.100.200",  # Alibaba Cloud metadata
        ],
    )
    async def test_blocks_loopback_link_local_and_metadata_hosts(self, host):
        """These stay blocked even if they happen to be the configured host."""
        with pytest.raises(SSRFError):
            await assert_host_is_safe(host, allowed_host=host)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "host",
        [
            "192.168.1.50", "10.0.0.5", "172.16.0.5",
            "100.64.0.1",  # CGNAT (RFC 6598) - not RFC1918, but still non-global
        ],
    )
    async def test_blocks_non_global_hosts_by_default(self, host):
        """A non-globally-routable address is only reachable via the
        configured host, never by default - otherwise a redirect could steer
        at any internal or non-routable address."""
        with pytest.raises(SSRFError):
            await assert_host_is_safe(host)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "host",
        ["192.168.1.50", "10.0.0.5", "172.16.0.5", "100.64.0.1"],
    )
    async def test_allows_non_global_host_when_it_is_the_configured_host(self, host):
        """Self-hosted Immich commonly lives on a LAN address - the specific
        host the integration was configured with must stay reachable."""
        ip = await assert_host_is_safe(host, allowed_host=host)
        assert str(ip) == host

    @pytest.mark.asyncio
    async def test_blocks_non_global_host_that_is_not_the_configured_host(self):
        """A redirect to a *different* non-global address than the configured
        host must still be blocked - this is what stops a compromised or
        redirect-happy upstream from reaching some other internal service."""
        with pytest.raises(SSRFError):
            await assert_host_is_safe("192.168.1.50", allowed_host="10.0.0.5")


class TestSSRFProtectedTransport:
    @pytest.mark.asyncio
    async def test_blocks_request_to_disallowed_host_without_connecting(self):
        """
        Every request the proxy client makes (including each hop of a
        redirect chain, since httpx re-enters the transport per hop) must be
        validated - this is what stops a compromised/rebound upstream from
        redirecting the fetch to an internal address, independent of who
        configured the original base_url.
        """
        transport = SSRFProtectedTransport()
        request = httpx.Request("GET", "http://127.0.0.1:6379/")

        with patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", new_callable=AsyncMock
        ) as mock_super:
            with pytest.raises(SSRFError):
                await transport.handle_async_request(request)
            mock_super.assert_not_called()

    @pytest.mark.asyncio
    async def test_allows_request_to_safe_host(self):
        transport = SSRFProtectedTransport()
        request = httpx.Request(
            "GET", "http://192.168.1.50:2283/api/users/me",
            extensions={ALLOWED_HOST_EXTENSION: "192.168.1.50"},
        )

        with patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", new_callable=AsyncMock
        ) as mock_super:
            mock_super.return_value = httpx.Response(200, request=request)
            response = await transport.handle_async_request(request)
            mock_super.assert_called_once()
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_pins_connection_to_the_validated_ip(self):
        """
        The connection must go to the address assert_host_is_safe validated,
        not let the transport re-resolve the hostname itself - otherwise DNS
        rebinding between the check and the connect would defeat the guard,
        since a second lookup could return a different (unvalidated) address.
        The original Host header and TLS SNI must still reflect the real
        hostname, not the pinned IP.
        """
        transport = SSRFProtectedTransport()
        request = httpx.Request(
            "GET", "http://photos.example.com:2283/api/users/me",
            extensions={ALLOWED_HOST_EXTENSION: "photos.example.com"},
        )

        with patch(
            "app.core.ssrf_guard.assert_host_is_safe",
            new_callable=AsyncMock,
            return_value=ipaddress.ip_address("203.0.113.10"),
        ) as mock_assert, patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", new_callable=AsyncMock
        ) as mock_super:
            mock_super.return_value = httpx.Response(200, request=request)

            await transport.handle_async_request(request)

            mock_assert.assert_awaited_once_with(
                "photos.example.com", allowed_host="photos.example.com"
            )
            sent_request = mock_super.call_args.args[0]
            assert sent_request.url.host == "203.0.113.10"
            assert sent_request.headers["host"] == "photos.example.com:2283"
            assert sent_request.extensions["sni_hostname"] == "photos.example.com"

    @pytest.mark.asyncio
    async def test_strips_credential_headers_on_cross_host_redirect(self):
        """
        A redirect to any host other than the configured one - a public one
        included, since that passes the destination check on its own - must
        not carry provider credentials with it, or a compromised/malicious
        upstream could redirect the request to its own server and read off
        the API key.
        """
        transport = SSRFProtectedTransport()
        request = httpx.Request(
            "GET", "http://8.8.8.8/collect",
            headers={"x-api-key": "super-secret", "accept": "application/json"},
            extensions={ALLOWED_HOST_EXTENSION: "photos.example.com"},
        )

        with patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", new_callable=AsyncMock
        ) as mock_super:
            mock_super.return_value = httpx.Response(200, request=request)
            await transport.handle_async_request(request)

            sent_request = mock_super.call_args.args[0]
            assert "x-api-key" not in sent_request.headers
            assert sent_request.headers["accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_preserves_credential_headers_on_same_host_redirect(self):
        """The legitimate case - a redirect that stays on the configured
        host - must still carry the API key, or every real request would
        break."""
        transport = SSRFProtectedTransport()
        request = httpx.Request(
            "GET", "http://192.168.1.50:2283/api/assets/1/original",
            headers={"x-api-key": "super-secret"},
            extensions={ALLOWED_HOST_EXTENSION: "192.168.1.50"},
        )

        with patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", new_callable=AsyncMock
        ) as mock_super:
            mock_super.return_value = httpx.Response(200, request=request)
            await transport.handle_async_request(request)

            sent_request = mock_super.call_args.args[0]
            assert sent_request.headers["x-api-key"] == "super-secret"

    @pytest.mark.asyncio
    async def test_strips_credential_headers_on_same_host_https_to_http_downgrade(self):
        """
        A same-host redirect that drops from https to plaintext http must not
        carry the API key either - otherwise a compromised/malicious upstream
        (or a network attacker forcing the downgrade) could read the key off
        the wire in cleartext even without changing host.
        """
        transport = SSRFProtectedTransport()
        request = httpx.Request(
            "GET", "http://192.168.1.50:2283/api/assets/1/original",
            headers={"x-api-key": "super-secret"},
            extensions={
                ALLOWED_HOST_EXTENSION: "192.168.1.50",
                ALLOWED_SCHEME_EXTENSION: "https",
            },
        )

        with patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", new_callable=AsyncMock
        ) as mock_super:
            mock_super.return_value = httpx.Response(200, request=request)
            await transport.handle_async_request(request)

            sent_request = mock_super.call_args.args[0]
            assert "x-api-key" not in sent_request.headers

    @pytest.mark.asyncio
    async def test_preserves_credential_headers_when_configured_for_http(self):
        """A configured host that was always plain http (common for a LAN
        Immich instance with no TLS) is not itself a downgrade - the key
        must still be sent."""
        transport = SSRFProtectedTransport()
        request = httpx.Request(
            "GET", "http://192.168.1.50:2283/api/assets/1/original",
            headers={"x-api-key": "super-secret"},
            extensions={
                ALLOWED_HOST_EXTENSION: "192.168.1.50",
                ALLOWED_SCHEME_EXTENSION: "http",
            },
        )

        with patch.object(
            httpx.AsyncHTTPTransport, "handle_async_request", new_callable=AsyncMock
        ) as mock_super:
            mock_super.return_value = httpx.Response(200, request=request)
            await transport.handle_async_request(request)

            sent_request = mock_super.call_args.args[0]
            assert sent_request.headers["x-api-key"] == "super-secret"


class TestConnectIntegrationBaseUrlAuthorization:
    """A regular user overriding base_url is what lets them point the server
    at an arbitrary host - the shipped frontend never does this, so
    rejecting it outright for non-admins costs no real functionality."""

    @pytest.mark.asyncio
    async def test_non_admin_base_url_override_is_rejected(self):
        mock_session = MagicMock()
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.role = UserRole.USER

        with patch("app.integrations.immich.connect", new_callable=AsyncMock) as mock_connect:
            with pytest.raises(ValueError):
                await connect_integration(
                    session=mock_session,
                    user=mock_user,
                    provider=IntegrationProvider.IMMICH,
                    credentials={"api_key": "any-value"},
                    base_url="https://attacker.example",
                )

            mock_connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_admin_base_url_override_is_allowed(self):
        """An administrator's custom base_url is accepted - authorization
        only, destination validation is covered separately by the
        TestSSRFProtectedTransport tests."""
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = None
        mock_user = MagicMock()
        mock_user.id = "admin-123"
        mock_user.role = UserRole.ADMIN

        with patch("app.integrations.immich.connect", new_callable=AsyncMock) as mock_connect, \
             patch("app.integrations.immich.ensure_album_exists", new_callable=AsyncMock) as mock_ensure_album:
            mock_connect.return_value = "immich-user-456"
            mock_ensure_album.return_value = "album-789"

            response = await connect_integration(
                session=mock_session,
                user=mock_user,
                provider=IntegrationProvider.IMMICH,
                credentials={"api_key": "any-value"},
                base_url="https://photos.example.com",
            )

            assert response.status == "connected"
            mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_admin_without_base_url_uses_instance_default(self):
        """Regular users connecting without an override (the only path the
        real UI uses) must be unaffected by the admin-only restriction."""
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = None
        mock_user = MagicMock()
        mock_user.id = "user-123"
        mock_user.role = UserRole.USER

        with patch("app.integrations.immich.connect", new_callable=AsyncMock) as mock_connect, \
             patch("app.integrations.immich.ensure_album_exists", new_callable=AsyncMock) as mock_ensure_album, \
             patch("app.integrations.service.get_default_base_url", return_value="https://instance-immich.example.com"):
            mock_connect.return_value = "immich-user-456"
            mock_ensure_album.return_value = "album-789"

            response = await connect_integration(
                session=mock_session,
                user=mock_user,
                provider=IntegrationProvider.IMMICH,
                credentials={"api_key": "any-value"},
                base_url=None,
            )

            assert response.status == "connected"
            mock_connect.assert_called_once()
