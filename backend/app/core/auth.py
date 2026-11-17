"""Request authentication, CSRF protection and the permission dependency.

Core does not know how sessions are stored: the identity module provides the
`Authenticator` (wired in app.main), which turns a request into a `Principal`.
Every route declares its access with `**endpoint(level, scope=...)`, which both
documents the level in OpenAPI and enforces it.
"""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from http import HTTPStatus
from typing import Annotated, Any, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core import ratelimit
from app.core.access import AccessLevel, access
from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import get_session
from app.core.errors import AppError, ErrorCode
from app.core.policy import check_access
from app.core.principal import Principal

SESSION_COOKIE = "session"
CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "XMLHttpRequest"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_UNSET = object()

Authenticator = Callable[[Request, AsyncSession], Awaitable[Principal | None]]


async def csrf_protect(request: Request) -> None:
    """Cookie-authenticated browsers must send the custom header and a trusted Origin.

    Integration clients authenticate with an Authorization header and send no
    cookies, so the check does not apply to them (architecture section 7).
    """
    if request.method in _SAFE_METHODS or "authorization" in request.headers:
        return
    if request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE:
        raise AppError(ErrorCode.AUTH_CSRF_FAILED, HTTPStatus.FORBIDDEN)
    origin = request.headers.get("origin")
    settings: Settings = request.app.state.settings
    if origin is not None and origin.rstrip("/") not in settings.trusted_origins:
        raise AppError(ErrorCode.AUTH_CSRF_FAILED, HTTPStatus.FORBIDDEN)


async def optional_principal(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> Principal | None:
    # Authenticate once per request; later dependencies reuse the result.
    cached = getattr(request.state, "principal", _UNSET)
    if cached is not _UNSET:
        return cast(Principal | None, cached)
    authenticate: Authenticator = request.app.state.authenticator
    principal = await authenticate(request, session)
    request.state.principal = principal
    return principal


async def required_principal(
    principal: Annotated[Principal | None, Depends(optional_principal)],
) -> Principal:
    if principal is None:
        raise AppError(ErrorCode.AUTH_SESSION_EXPIRED, HTTPStatus.UNAUTHORIZED)
    return principal


OptionalPrincipal = Annotated[Principal | None, Depends(optional_principal)]
CurrentPrincipal = Annotated[Principal, Depends(required_principal)]


def _requirement(level: AccessLevel, scope: str | None) -> Callable[..., Awaitable[None]]:
    async def require(request: Request, principal: OptionalPrincipal) -> None:
        check_access(principal, level, scope)
        if principal is not None:
            settings: Settings = request.app.state.settings
            engine: AsyncEngine = request.app.state.engine
            clock: Clock = request.app.state.clock
            await ratelimit.hit(
                engine,
                f"user:{principal.user_id}",
                limit=settings.rate_limit_user_per_minute,
                window=timedelta(minutes=1),
                now=clock.now(),
            )

    return require


def endpoint(level: AccessLevel, *, scope: str | None = None) -> dict[str, Any]:
    """Keyword arguments for a route decorator: declared level + its enforcement."""
    return {
        "openapi_extra": access(level, scope),
        "dependencies": [Depends(_requirement(level, scope))],
    }
