"""
SSRF protection for the Immich asset/thumbnail proxy client.

The proxy client follows redirects and streams the response straight back
to the caller, so SSRFProtectedTransport re-resolves and checks the
destination on every request - including each redirect hop - to stop a
compromised or DNS-rebound upstream from steering the fetch to an internal
address (cloud metadata, another internal service). Non-globally-routable
addresses are blocked by default; one is only reachable when it's the
specific host the integration was configured with, since self-hosted Immich
commonly lives on a LAN address.
"""
from __future__ import annotations

import asyncio
import ipaddress
from typing import Optional, Union

import httpx

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]

# Request extension keys carrying the integration's configured host/scheme
# through to the transport. httpx preserves `extensions` across redirect-built
# requests, so these values stay pinned to the original configuration for
# every hop - scoping private-address access, and credential headers, to it
# rather than to wherever a redirect points.
ALLOWED_HOST_EXTENSION = "ssrf_allowed_host"
ALLOWED_SCHEME_EXTENSION = "ssrf_allowed_scheme"

# Single-IP cloud metadata endpoints that aren't already covered by
# is_link_local (169.254.0.0/16 / fe80::/10 catches the AWS/GCP/Azure/DO ones).
_EXTRA_BLOCKED_NETWORKS = (
    ipaddress.ip_network("100.100.100.200/32"),  # Alibaba Cloud metadata
    ipaddress.ip_network("fd00:ec2::254/128"),  # AWS IMDSv2 (IPv6)
)

# Provider-credential headers that must never follow a redirect to a host
# other than the one the integration was configured with, or a downgrade
# from https to plaintext http on that same host.
_CROSS_HOST_STRIPPED_HEADERS = ("x-api-key",)


class SSRFError(ValueError):
    """Raised when a proxy request's destination resolves to a disallowed address."""


def _normalize(ip: IPAddress) -> IPAddress:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def _is_blocked_ip(ip: IPAddress) -> bool:
    """Addresses that are never a valid destination, even for the configured host."""
    if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return True
    return any(ip in network for network in _EXTRA_BLOCKED_NETWORKS)


async def assert_host_is_safe(host: str, *, allowed_host: Optional[str] = None) -> IPAddress:
    """
    Resolve `host`, reject it if any candidate address is disallowed, and
    return the address the caller should connect to.

    Non-globally-routable addresses (RFC1918, CGNAT, and similar) are only
    permitted when `host` matches `allowed_host` - the specific host the
    integration was configured with - so a redirect can't steer the request
    at some other internal or non-routable address. Fails closed: an
    unresolvable host or an unparseable address is treated as unsafe rather
    than silently allowed through.
    """
    if not host:
        raise SSRFError("Missing host")

    is_configured_host = allowed_host is not None and host.lower() == allowed_host.lower()

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None)
    except OSError as e:
        raise SSRFError(f"Could not resolve host '{host}'") from e

    if not infos:
        raise SSRFError(f"Could not resolve host '{host}'")

    safe_ips: list[IPAddress] = []
    for _family, _type, _proto, _canonname, sockaddr in infos:
        try:
            ip = _normalize(ipaddress.ip_address(sockaddr[0]))
        except ValueError as e:
            raise SSRFError(f"Host '{host}' resolved to an unparseable address") from e
        if _is_blocked_ip(ip):
            raise SSRFError(f"Host '{host}' resolves to a disallowed address ({ip})")
        if not ip.is_global and not is_configured_host:
            raise SSRFError(
                f"Host '{host}' resolves to a non-routable address ({ip}) that isn't the configured integration host"
            )
        safe_ips.append(ip)

    return safe_ips[0]


class SSRFProtectedTransport(httpx.AsyncHTTPTransport):
    """
    httpx transport that re-resolves and validates the destination host
    immediately before every connection attempt, then connects to that
    validated address directly - rather than handing the original hostname
    to the connection, which would let it re-resolve (and potentially get a
    different, unvalidated answer) between the check and the connect.

    httpx re-enters the transport for each hop of a redirect chain, so this
    also protects against a malicious/compromised upstream redirecting the
    request to an internal host. A redirect to a host other than the one
    configured, or a downgrade from https to plaintext http, also has its
    provider-credential headers stripped, so a compromised/malicious host
    can't redirect the request to a different (even public) host, or to a
    cleartext hop, and walk away with the API key.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        allowed_host = request.extensions.get(ALLOWED_HOST_EXTENSION)
        allowed_scheme = request.extensions.get(ALLOWED_SCHEME_EXTENSION)
        safe_ip = await assert_host_is_safe(host, allowed_host=allowed_host)

        is_cross_host = allowed_host is not None and host.lower() != allowed_host.lower()
        is_https_downgrade = allowed_scheme == "https" and request.url.scheme != "https"

        headers = request.headers
        if is_cross_host or is_https_downgrade:
            headers = headers.copy()
            for name in _CROSS_HOST_STRIPPED_HEADERS:
                headers.pop(name, None)

        # Pin the connection to the validated IP while keeping the original
        # Host header (already set on `request.headers`) and TLS SNI so the
        # upstream still sees the intended hostname.
        extensions = dict(request.extensions)
        extensions.setdefault("sni_hostname", host)
        pinned_request = httpx.Request(
            method=request.method,
            url=request.url.copy_with(host=str(safe_ip)),
            headers=headers,
            stream=request.stream,
            extensions=extensions,
        )
        return await super().handle_async_request(pinned_request)
