"""HTTP layer only: parse requests, call the service, shape responses."""

from datetime import timedelta
from http import HTTPStatus
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core import ratelimit
from app.core.access import AccessLevel
from app.core.auth import SESSION_COOKIE, CurrentPrincipal, endpoint
from app.core.clock import Clock
from app.core.config import Settings
from app.core.db import DbSession
from app.core.errors import AppError, ErrorCode
from app.core.principal import RoleCode
from app.modules.identity import mfa, service
from app.modules.identity.schemas import (
    Locale,
    LoginMfaRequest,
    LoginRequest,
    LoginResponse,
    Me,
    MeUpdate,
    MfaConfirmRequest,
    MfaDisableRequest,
    MfaRecoveryCodes,
    MfaSetup,
    PasswordChangeRequest,
    PasswordForgotRequest,
    PasswordLink,
    PasswordSetRequest,
    PasswordTokenInfo,
    RoleOut,
    SessionInfo,
    SessionUser,
    UserCreate,
    UserCreated,
    UserLookupPage,
    UserOut,
    UserPage,
    UserSort,
    UserUpdate,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])
# The pending-MFA cookie reaches only the sign-in endpoints.
MFA_COOKIE_PATH = "/api/v1/auth/login"
me_router = APIRouter(prefix="/me", tags=["me"])
users_router = APIRouter(prefix="/users", tags=["users"])
roles_router = APIRouter(prefix="/roles", tags=["users"])

PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


async def context(request: Request, session: DbSession) -> service.Context:
    clock: Clock = request.app.state.clock
    return service.Context(
        session=session,
        events=request.app.state.event_bus,
        settings=request.app.state.settings,
        mailer=request.app.state.mailer,
        now=clock.now(),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


Ctx = Annotated[service.Context, Depends(context)]


async def _limit(
    ctx: service.Context, request: Request, name: str, limit: int, window: timedelta
) -> None:
    await ratelimit.hit(
        request.app.state.engine,
        f"{name}:ip:{ctx.ip}",
        limit=limit,
        window=window,
        now=ctx.now,
    )


def _set_session_cookie(
    response: Response, settings: Settings, new: service.NewSession, ctx: service.Context
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        new.token,
        max_age=int((new.expires_at - ctx.now).total_seconds()),
        path="/api",
        secure=True,
        httponly=True,
        samesite="strict",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE, path="/api", secure=True, httponly=True, samesite="strict"
    )


# --- Authentication (API spec section 3) ---------------------------------------


@auth_router.post(
    "/login",
    summary="Sign in with email and password; sets the session cookie",
    **endpoint(AccessLevel.PUBLIC),
)
async def login(
    body: LoginRequest, request: Request, response: Response, ctx: Ctx
) -> LoginResponse:
    await _limit(
        ctx, request, "login", ctx.settings.rate_limit_login_per_minute, timedelta(minutes=1)
    )
    new = await service.login(ctx, body.email, body.password)
    if isinstance(new, service.MfaChallenge):
        # FR-AUTH-07: the code step follows; only that step can use this cookie.
        raise AppError(
            ErrorCode.AUTH_MFA_REQUIRED,
            HTTPStatus.UNAUTHORIZED,
            headers={
                "Set-Cookie": mfa.cookie_header(
                    new.token, int(mfa.PENDING_LIFETIME.total_seconds()), MFA_COOKIE_PATH
                )
            },
        )
    return _signed_in(response, new, ctx)


def _signed_in(response: Response, new: service.NewSession, ctx: service.Context) -> LoginResponse:
    _set_session_cookie(response, ctx.settings, new, ctx)
    user = new.user
    return LoginResponse(
        user=SessionUser(
            id=user.id,
            full_name=user.full_name,
            role=RoleCode(user.role.code),
            locale=cast(Locale, user.locale),
        )
    )


@auth_router.post(
    "/login/mfa",
    summary="Complete sign-in with a TOTP code (or a recovery code) when MFA is enabled",
    **endpoint(AccessLevel.PUBLIC),
)
async def login_mfa(
    body: LoginMfaRequest, request: Request, response: Response, ctx: Ctx
) -> LoginResponse:
    await _limit(
        ctx, request, "login", ctx.settings.rate_limit_login_per_minute, timedelta(minutes=1)
    )
    new = await service.login_mfa(ctx, request.cookies.get(mfa.PENDING_COOKIE), body.code)
    response.delete_cookie(
        mfa.PENDING_COOKIE, path=MFA_COOKIE_PATH, secure=True, httponly=True, samesite="strict"
    )
    return _signed_in(response, new, ctx)


@auth_router.post(
    "/mfa/setup",
    summary="Start TOTP enrolment; returns the secret and provisioning URI",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def mfa_setup(ctx: Ctx, principal: CurrentPrincipal) -> MfaSetup:
    return await service.mfa_setup(ctx, principal)


@auth_router.post(
    "/mfa/confirm",
    summary="Confirm enrolment with a code; returns recovery codes once",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def mfa_confirm(
    body: MfaConfirmRequest, ctx: Ctx, principal: CurrentPrincipal
) -> MfaRecoveryCodes:
    return await service.mfa_confirm(ctx, principal, body.code)


@auth_router.post(
    "/mfa/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable own MFA (requires password); not allowed where enforced",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def mfa_disable(body: MfaDisableRequest, ctx: Ctx, principal: CurrentPrincipal) -> None:
    await service.mfa_disable(ctx, principal, body.password)


@auth_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End the current session and clear the cookie",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def logout(principal: CurrentPrincipal, response: Response, ctx: Ctx) -> None:
    await service.logout(ctx, principal)
    _clear_session_cookie(response)


@auth_router.post(
    "/password/set",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set a password using a one-time token",
    **endpoint(AccessLevel.PUBLIC),
)
async def password_set(body: PasswordSetRequest, request: Request, ctx: Ctx) -> None:
    await _limit(
        ctx,
        request,
        "password",
        ctx.settings.rate_limit_password_per_15_minutes,
        timedelta(minutes=15),
    )
    await service.set_password_with_token(ctx, body.token, body.password)


@auth_router.get(
    "/password/token/{token}",
    summary="Check a token is valid before showing the form",
    **endpoint(AccessLevel.PUBLIC),
)
async def password_token(token: str, request: Request, ctx: Ctx) -> PasswordTokenInfo:
    await _limit(
        ctx,
        request,
        "password",
        ctx.settings.rate_limit_password_per_15_minutes,
        timedelta(minutes=15),
    )
    return await service.check_password_token(ctx, token)


@auth_router.post(
    "/password/forgot",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a reset email; always 202",
    **endpoint(AccessLevel.PUBLIC),
)
async def password_forgot(body: PasswordForgotRequest, request: Request, ctx: Ctx) -> None:
    await _limit(
        ctx,
        request,
        "password",
        ctx.settings.rate_limit_password_per_15_minutes,
        timedelta(minutes=15),
    )
    await service.request_password_reset(ctx, body.email)


@auth_router.post(
    "/password/change",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change own password; revokes other sessions",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def password_change(
    body: PasswordChangeRequest, principal: CurrentPrincipal, request: Request, ctx: Ctx
) -> None:
    await _limit(
        ctx,
        request,
        "password",
        ctx.settings.rate_limit_password_per_15_minutes,
        timedelta(minutes=15),
    )
    await service.change_password(ctx, principal, body.current_password, body.new_password)


# --- Current user (section 4) --------------------------------------------------


@me_router.get(
    "",
    summary="Profile, role, locale and permissions",
    **endpoint(AccessLevel.SIGNED_IN_OR_ANY_CLIENT),
)
async def get_me(principal: CurrentPrincipal, ctx: Ctx) -> Me:
    return await service.get_me(ctx, principal)


@me_router.patch("", summary="Update own full_name and locale", **endpoint(AccessLevel.SIGNED_IN))
async def patch_me(body: MeUpdate, principal: CurrentPrincipal, ctx: Ctx) -> Me:
    return await service.update_me(ctx, principal, body)


@me_router.get("/sessions", summary="Own active sessions", **endpoint(AccessLevel.SIGNED_IN))
async def my_sessions(principal: CurrentPrincipal, ctx: Ctx) -> list[SessionInfo]:
    return await service.list_my_sessions(ctx, principal)


@me_router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke one of own sessions",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def revoke_my_session(
    session_id: UUID, principal: CurrentPrincipal, response: Response, ctx: Ctx
) -> None:
    await service.revoke_my_session(ctx, principal, session_id)
    if session_id == principal.session_id:
        _clear_session_cookie(response)


# --- Users (section 5) ---------------------------------------------------------


@users_router.get(
    "/lookup",
    summary="Active human users for owner and assignee pickers",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def lookup_users(
    ctx: Ctx,
    q: Annotated[str | None, Query(max_length=200)] = None,
    email: Annotated[str | None, Query(max_length=320)] = None,
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> UserLookupPage:
    return await service.lookup_users(ctx, q=q, email=email, page=page, page_size=page_size)


@users_router.get(
    "",
    summary="Full user list with role, status, last sign-in and lock state",
    **endpoint(AccessLevel.ADMIN),
)
async def list_users(
    ctx: Ctx,
    q: Annotated[str | None, Query(max_length=200)] = None,
    role: RoleCode | None = None,
    is_active: bool | None = None,
    sort: UserSort = "name",
    page: PageNumber = 1,
    page_size: PageSize = 25,
) -> UserPage:
    return await service.list_users(
        ctx, q=q, role=role, is_active=is_active, sort=sort, page=page, page_size=page_size
    )


@users_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a user; returns a one-time set-password link",
    **endpoint(AccessLevel.ADMIN),
)
async def create_user(
    body: UserCreate, principal: CurrentPrincipal, response: Response, ctx: Ctx
) -> UserCreated:
    created = await service.create_user(ctx, principal, body)
    response.headers["Location"] = f"/api/v1/users/{created.user.id}"
    return created


@users_router.get("/{user_id}", summary="User detail", **endpoint(AccessLevel.ADMIN))
async def get_user(user_id: UUID, ctx: Ctx) -> UserOut:
    return await service.get_user(ctx, user_id)


@users_router.patch(
    "/{user_id}", summary="Change name, email, role, locale", **endpoint(AccessLevel.ADMIN)
)
async def update_user(
    user_id: UUID, body: UserUpdate, principal: CurrentPrincipal, ctx: Ctx
) -> UserOut:
    return await service.update_user(ctx, principal, user_id, body)


@users_router.post(
    "/{user_id}/deactivate",
    summary="Deactivate and revoke all sessions; records stay",
    **endpoint(AccessLevel.ADMIN),
)
async def deactivate_user(user_id: UUID, principal: CurrentPrincipal, ctx: Ctx) -> UserOut:
    return await service.deactivate_user(ctx, principal, user_id)


@users_router.post("/{user_id}/activate", summary="Reactivate", **endpoint(AccessLevel.ADMIN))
async def activate_user(user_id: UUID, principal: CurrentPrincipal, ctx: Ctx) -> UserOut:
    return await service.activate_user(ctx, principal, user_id)


@users_router.post(
    "/{user_id}/password-reset", summary="Issue a reset link", **endpoint(AccessLevel.ADMIN)
)
async def password_reset(user_id: UUID, principal: CurrentPrincipal, ctx: Ctx) -> PasswordLink:
    return await service.issue_password_reset(ctx, principal, user_id)


@users_router.post("/{user_id}/unlock", summary="Clear a lockout", **endpoint(AccessLevel.ADMIN))
async def unlock_user(user_id: UUID, principal: CurrentPrincipal, ctx: Ctx) -> UserOut:
    return await service.unlock_user(ctx, principal, user_id)


@users_router.delete(
    "/{user_id}/sessions",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke all of a user's sessions",
    **endpoint(AccessLevel.ADMIN),
)
async def revoke_user_sessions(user_id: UUID, principal: CurrentPrincipal, ctx: Ctx) -> None:
    await service.revoke_user_sessions(ctx, principal, user_id)


@roles_router.get("", summary="Roles with their permission lists", **endpoint(AccessLevel.ADMIN))
async def list_roles(ctx: Ctx) -> list[RoleOut]:
    return await service.list_roles(ctx)


routers = [auth_router, me_router, users_router, roles_router]
