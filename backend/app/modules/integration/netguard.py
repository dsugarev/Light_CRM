"""Outbound webhook safety (API spec 19.6, architecture 7): URL rules, the host
allowlist, and address checks after DNS resolution, so the CRM cannot be used to
reach arbitrary internal services.

The delivery connects to the address that passed the check (no second lookup), while
TLS still verifies the certificate against the URL's host name.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpcore
import httpx

from app.core.config import Settings

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

# Cloud metadata endpoints that are not link-local (link-local ones are refused anyway).
_METADATA = frozenset(
    ipaddress.ip_address(a) for a in ("fd00:ec2::254", "100.100.100.200", "192.0.0.192")
)


def host_allowed(host: str, patterns: Sequence[str]) -> bool:
    """Exact host names, or "*.suffix" for any subdomain of suffix (not suffix itself)."""
    host = host.lower().rstrip(".")
    for pattern in patterns:
        if pattern.startswith("*."):
            if host.endswith(pattern[1:]) and len(host) > len(pattern) - 1:
                return True
        elif host == pattern:
            return True
    return False


def url_allowed(url: str, settings: Settings) -> bool:
    """HTTPS (HTTP only outside production), no credentials, host on the allowlist."""
    try:
        parts = urlsplit(url)
        port = parts.port  # raises for an invalid port
    except ValueError:
        return False
    schemes = {"https"} if settings.is_production else {"https", "http"}
    return (
        parts.scheme in schemes
        and not parts.username
        and not parts.password
        and bool(parts.hostname)
        and (port is None or 0 < port < 65536)
        and host_allowed(parts.hostname or "", settings.webhook_host_patterns)
    )


def address_allowed(address: IpAddress) -> bool:
    """Private ranges are fine (on-premises systems); loopback, link-local, metadata
    and other special addresses are always refused."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return not (
        address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_multicast
        or address.is_reserved
        or address in _METADATA
    )


async def resolve(host: str, port: int) -> list[IpAddress]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
    )
    return [ipaddress.ip_address(info[4][0]) for info in infos]


@dataclass(frozen=True, slots=True)
class Network:
    """What a delivery may connect to; tests replace it to reach a local receiver."""

    resolve: Callable[[str, int], Awaitable[list[IpAddress]]] = resolve
    address_allowed: Callable[[IpAddress], bool] = address_allowed


class _PinnedBackend(httpcore.AsyncNetworkBackend):
    """Connects every TCP stream to one vetted address, whatever the URL's host."""

    def __init__(self, address: str) -> None:
        self._address = address
        self._inner = httpcore.AnyIOBackend()

    # httpcore's backend interface takes `timeout` parameters (ASYNC109 does not apply).
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._inner.connect_tcp(
            self._address, port, timeout, local_address, socket_options
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("unix sockets are not used for webhooks")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def pinned_client(address: IpAddress, timeout_seconds: float) -> httpx.AsyncClient:
    """An HTTP client that never follows redirects and only reaches `address`."""
    transport = httpx.AsyncHTTPTransport(retries=0)
    # httpx has no public hook for the network backend; replace the transport's pool,
    # keeping its TLS context (certificate verification against the URL's host name).
    pool = transport._pool
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=pool._ssl_context,
        max_connections=1,
        network_backend=_PinnedBackend(str(address)),
    )
    return httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
        timeout=httpx.Timeout(timeout_seconds),
        trust_env=False,
    )
