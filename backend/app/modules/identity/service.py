"""Identity business rules: sign-in, sessions, passwords, profile and user administration.

Public API of the module. Every change publishes a domain event (audited) and
commits here; routers only translate HTTP to calls on these functions.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any, Literal
from uuid import UUID

from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto, runtime_settings
from app.core.auth import SESSION_COOKIE
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.events import DomainEvent, EventBus
from app.core.ids import new_id
from app.core.mailer import Mailer
from app.core.policy import CONTRIBUTOR_ROLES, permissions_for
from app.core.principal import Principal, PrincipalType, RoleCode
from app.modules.identity import mfa, repository
from app.modules.identity.emails import password_link_email
from app.modules.identity.models import PasswordToken, User, UserSession
from app.modules.identity.passwords import (
    burn_verification_time,
    hash_password,
    needs_rehash,
    policy_violations,
)
from app.modules.identity.providers import PROVIDERS
from app.modules.identity.schemas import (
    Me,
    MeUpdate,
    MfaRecoveryCodes,
    MfaSetup,
    PasswordLink,
    PasswordTokenInfo,
    RoleOut,
    SessionInfo,
    UserCreate,
    UserCreated,
    UserLookupItem,
    UserLookupPage,
    UserOut,
    UserPage,
    UserUpdate,
)
from app.modules.identity.tokens import hash_token, new_token

# last_seen_at is written at most this often, to avoid a write on every request.
_TOUCH_INTERVAL = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class Context:
    """What every service call needs besides its arguments."""

    session: AsyncSession
    events: EventBus
    settings: Settings
    mailer: Mailer
    now: datetime
    ip: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class NewSession:
    user: User
    token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class MfaChallenge:
    """The password was right; sign-in continues at POST /auth/login/mfa (FR-AUTH-07)."""

    token: str


# --- Helpers ------------------------------------------------------------------


def _audit_view(user: User) -> dict[str, Any]:
    """User fields recorded in the audit log. Never secrets (hash, tokens, MFA)."""
    return {
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.code,
        "locale": user.locale,
        "is_active": user.is_active,
        "user_type": user.user_type,
    }


def principal_for(
    user: User, session_id: UUID | None = None, *, mfa_required_for_admins: bool = False
) -> Principal:
    role = RoleCode(user.role.code)
    return Principal(
        type=PrincipalType.USER,
        user_id=user.id,
        role=role,
        display_name=user.full_name,
        session_id=session_id,
        # FR-AUTH-07: an Admin without MFA, where it is required, may only set it up.
        mfa_setup_required=(
            mfa_required_for_admins and role is RoleCode.ADMIN and user.mfa_enabled_at is None
        ),
    )


async def _publish(
    ctx: Context,
    action: str,
    *,
    actor: Principal | None,
    entity_id: UUID | None,
    entity_type: str = "user",
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    await ctx.events.publish(
        ctx.session,
        DomainEvent(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            occurred_at=ctx.now,
            before=before,
            after=after,
            details=details or {},
        ),
    )


def _is_locked(user: User, now: datetime) -> bool:
    return user.locked_until is not None and user.locked_until > now


def _user_out(user: User, now: datetime) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=RoleCode(user.role.code),
        locale=user.locale,  # type: ignore[arg-type]
        user_type=user.user_type,  # type: ignore[arg-type]
        is_active=user.is_active,
        is_locked=_is_locked(user, now),
        locked_until=user.locked_until if _is_locked(user, now) else None,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


async def _committed_user_out(ctx: Context, user: User) -> UserOut:
    """Commit, then reload: updated_at is set by a database trigger."""
    await ctx.session.commit()
    await ctx.session.refresh(user)
    return _user_out(user, ctx.now)


def _not_found() -> AppError:
    return AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)


def _check_password_policy(password: str, field: str) -> None:
    violations = policy_violations(password)
    if violations:
        raise AppError(
            ErrorCode.AUTH_PASSWORD_POLICY,
            HTTPStatus.UNPROCESSABLE_CONTENT,
            errors=[FieldError(field, code) for code in violations],
        )


async def _set_password(ctx: Context, user: User, password: str) -> None:
    user.password_hash = await hash_password(password)
    user.password_changed_at = ctx.now
    user.failed_login_count = 0
    user.locked_until = None


# --- Authentication -----------------------------------------------------------


async def authenticate_request(request: Request, session: AsyncSession) -> Principal | None:
    """Resolve the caller from the session cookie. Bearer API keys are handled by the
    integration module; app.main combines both (core.auth.combined_authenticator)."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None

    now = request.app.state.clock.now()
    user_session = await repository.get_session_by_token_hash(session, hash_token(cookie))
    if user_session is None:
        return None
    user = user_session.user
    timeouts = await runtime_settings.load(session)
    idle_limit = timedelta(minutes=timeouts.session_idle_timeout_minutes)
    expired = (
        now >= user_session.expires_at
        or now - user_session.last_seen_at > idle_limit
        or not user.is_active
        or not user.is_human
    )
    if expired:
        await repository.delete_session(session, user_session.id)
        await session.commit()
        return None
    if now - user_session.last_seen_at >= _TOUCH_INTERVAL:
        user_session.last_seen_at = now
        await session.commit()
    return principal_for(
        user, user_session.id, mfa_required_for_admins=timeouts.mfa_required_for_admins
    )


async def login(ctx: Context, email: str, password: str) -> NewSession | MfaChallenge:
    """FR-AUTH-01: generic errors, lockout after repeated failures, audit of every attempt."""
    user = await repository.get_user_by_email(ctx.session, email.strip(), for_update=True)
    provider = PROVIDERS.get(user.auth_provider) if user is not None else None
    if user is None or provider is None or not user.is_active or not user.is_human:
        await burn_verification_time(password)
        await _publish(
            ctx,
            "auth.login_failed",
            actor=None,
            entity_id=user.id if user else None,
            details={"email": email.strip().lower(), "reason": "unknown_or_inactive"},
        )
        await ctx.session.commit()
        raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS, HTTPStatus.UNAUTHORIZED)

    if _is_locked(user, ctx.now):
        await _publish(
            ctx,
            "auth.login_failed",
            actor=None,
            entity_id=user.id,
            details={"email": user.email, "reason": "locked"},
        )
        await ctx.session.commit()
        assert user.locked_until is not None  # noqa: S101 - guaranteed by _is_locked
        raise AppError(
            ErrorCode.AUTH_ACCOUNT_LOCKED,
            HTTPStatus.LOCKED,
            extra={"locked_until": user.locked_until.isoformat()},
        )

    if not await provider.verify_credentials(user, password):
        await _failed_attempt(ctx, user, "bad_password")
        raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS, HTTPStatus.UNAUTHORIZED)

    if user.password_hash is not None and needs_rehash(user.password_hash):
        user.password_hash = await hash_password(password)
    if user.mfa_enabled_at is not None:
        # FR-AUTH-07: the password is right; the session waits for the code.
        await ctx.session.commit()
        return MfaChallenge(token=mfa.pending_token(ctx.settings.app_secret_key, user.id, ctx.now))
    return await _start_session(ctx, user)


async def _failed_attempt(ctx: Context, user: User, reason: str) -> None:
    """Count a failed password or code; lock the account after too many (FR-AUTH-01)."""
    user.failed_login_count += 1
    await _publish(
        ctx,
        "auth.login_failed",
        actor=None,
        entity_id=user.id,
        details={"email": user.email, "reason": reason},
    )
    if user.failed_login_count >= ctx.settings.login_max_failed_attempts:
        user.locked_until = ctx.now + timedelta(minutes=ctx.settings.login_lockout_minutes)
        user.failed_login_count = 0
        await _publish(
            ctx,
            "auth.account_locked",
            actor=None,
            entity_id=user.id,
            details={"locked_until": user.locked_until.isoformat()},
        )
    await ctx.session.commit()


async def _start_session(ctx: Context, user: User) -> NewSession:
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = ctx.now
    timeouts = await runtime_settings.load(ctx.session)
    raw, token_hash = new_token()
    expires_at = ctx.now + timedelta(minutes=timeouts.session_absolute_timeout_minutes)
    user_session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        created_at=ctx.now,
        last_seen_at=ctx.now,
        expires_at=expires_at,
        ip=ctx.ip,
        user_agent=(ctx.user_agent or "")[:512] or None,
    )
    ctx.session.add(user_session)
    await ctx.session.flush()
    await _publish(
        ctx,
        "auth.login_succeeded",
        actor=principal_for(user, user_session.id),
        entity_id=user.id,
        details={"mfa": user.mfa_enabled_at is not None},
    )
    await ctx.session.commit()
    return NewSession(user=user, token=raw, expires_at=expires_at)


async def login_mfa(ctx: Context, pending: str | None, code: str) -> NewSession:
    """FR-AUTH-07: finish sign-in with a TOTP code or a recovery code."""
    user_id = mfa.read_pending_token(ctx.settings.app_secret_key, pending, ctx.now)
    user = await repository.get_user(ctx.session, user_id, for_update=True) if user_id else None
    if (
        user is None
        or not user.is_active
        or not user.is_human
        or user.mfa_enabled_at is None
        or user.mfa_secret is None
    ):
        raise AppError(ErrorCode.AUTH_SESSION_EXPIRED, HTTPStatus.UNAUTHORIZED)
    if _is_locked(user, ctx.now):
        assert user.locked_until is not None  # noqa: S101 - guaranteed by _is_locked
        raise AppError(
            ErrorCode.AUTH_ACCOUNT_LOCKED,
            HTTPStatus.LOCKED,
            extra={"locked_until": user.locked_until.isoformat()},
        )
    secret = crypto.decrypt(ctx.settings, user.mfa_secret)
    counter = mfa.verify_code(secret, code, ctx.now, user.mfa_last_counter)
    if counter is not None:
        user.mfa_last_counter = counter
    else:
        remaining = mfa.use_recovery_code(user.mfa_recovery_codes or [], code)
        if remaining is None:
            await _failed_attempt(ctx, user, "bad_mfa_code")
            raise AppError(ErrorCode.AUTH_MFA_CODE_INVALID, HTTPStatus.UNAUTHORIZED)
        user.mfa_recovery_codes = remaining
        await _publish(
            ctx,
            "user.mfa_recovery_code_used",
            actor=principal_for(user),
            entity_id=user.id,
            details={"remaining": len(remaining)},
        )
    return await _start_session(ctx, user)


async def logout(ctx: Context, principal: Principal) -> None:
    if principal.session_id is not None:
        await repository.delete_session(ctx.session, principal.session_id)
    await _publish(ctx, "auth.logout", actor=principal, entity_id=principal.user_id)
    await ctx.session.commit()


# --- Password tokens ----------------------------------------------------------


async def _issue_password_token(
    ctx: Context, user: User, purpose: str, created_by: UUID | None
) -> PasswordLink:
    hours = (
        ctx.settings.password_set_token_hours
        if purpose == "set"
        else ctx.settings.password_reset_token_hours
    )
    await repository.expire_open_password_tokens(ctx.session, user.id, ctx.now)
    raw, token_hash = new_token()
    expires_at = ctx.now + timedelta(hours=hours)
    ctx.session.add(
        PasswordToken(
            user_id=user.id,
            token_hash=token_hash,
            purpose=purpose,
            expires_at=expires_at,
            created_at=ctx.now,
            created_by=created_by,
        )
    )
    # The token travels in the URL fragment, which browsers never send to servers.
    url = f"{ctx.settings.public_url.rstrip('/')}/set-password#token={raw}"
    return PasswordLink(url=url, expires_at=expires_at, emailed=False)


async def _email_link(ctx: Context, user: User, purpose: str, link: PasswordLink) -> PasswordLink:
    if not ctx.mailer.enabled:
        return link
    sent = await ctx.mailer.send(
        password_link_email(
            to=user.email,
            name=user.full_name,
            locale=user.locale,
            purpose=purpose,
            url=link.url,
            expires_at=link.expires_at,
        )
    )
    return link.model_copy(update={"emailed": sent})


async def _valid_token(ctx: Context, raw: str) -> PasswordToken:
    token = await repository.get_password_token(ctx.session, hash_token(raw))
    if (
        token is None
        or token.used_at is not None
        or token.expires_at <= ctx.now
        or not token.user.is_active
        or not token.user.is_human
    ):
        raise AppError(ErrorCode.AUTH_TOKEN_INVALID, HTTPStatus.BAD_REQUEST)
    return token


async def check_password_token(ctx: Context, raw: str) -> PasswordTokenInfo:
    token = await _valid_token(ctx, raw)
    return PasswordTokenInfo(email=token.user.email, purpose=token.purpose)  # type: ignore[arg-type]


async def set_password_with_token(ctx: Context, raw: str, password: str) -> None:
    """FR-AUTH-02/03/04: one-time token; all of the user's sessions end."""
    token = await _valid_token(ctx, raw)
    _check_password_policy(password, "password")
    user = token.user
    await _set_password(ctx, user, password)
    token.used_at = ctx.now
    await repository.delete_user_sessions(ctx.session, user.id)
    await _publish(
        ctx,
        "auth.password_set",
        actor=principal_for(user),
        entity_id=user.id,
        details={"purpose": token.purpose},
    )
    await ctx.session.commit()


async def request_password_reset(ctx: Context, email: str) -> None:
    """Always succeeds for the caller (202); sends a link only when SMTP is configured."""
    if not ctx.mailer.enabled:
        return
    user = await repository.get_user_by_email(ctx.session, email.strip())
    if user is None or not user.is_active or not user.is_human or user.auth_provider != "local":
        return
    link = await _issue_password_token(ctx, user, "reset", created_by=None)
    await _publish(ctx, "auth.password_reset_requested", actor=None, entity_id=user.id)
    await ctx.session.commit()
    await _email_link(ctx, user, "reset", link)


async def change_password(
    ctx: Context, principal: Principal, current_password: str, new_password: str
) -> None:
    """FR-AUTH-04: changing the password ends the user's other sessions."""
    user = await repository.get_user(ctx.session, principal.user_id, for_update=True)
    if user is None:
        raise _not_found()
    provider = PROVIDERS.get(user.auth_provider)
    if provider is None or not await provider.verify_credentials(user, current_password):
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            HTTPStatus.UNPROCESSABLE_CONTENT,
            errors=[FieldError("current_password", "password.current_incorrect")],
        )
    _check_password_policy(new_password, "new_password")
    await _set_password(ctx, user, new_password)
    await repository.delete_user_sessions(
        ctx.session, user.id, except_session_id=principal.session_id
    )
    await _publish(ctx, "auth.password_changed", actor=principal, entity_id=user.id)
    await ctx.session.commit()


# --- Current user -------------------------------------------------------------


async def get_me(ctx: Context, principal: Principal) -> Me:
    user = await repository.get_user(ctx.session, principal.user_id)
    if user is None:
        raise _not_found()
    return Me(
        principal_type="integration" if principal.is_integration else "user",
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=RoleCode(user.role.code),
        locale=user.locale,  # type: ignore[arg-type]
        permissions=sorted(permissions_for(RoleCode(user.role.code))),
        system=principal.system,
        scopes=sorted(principal.scopes),
        mfa_enabled=user.mfa_enabled_at is not None,
        mfa_setup_required=principal.mfa_setup_required,
    )


# --- Two-factor sign-in (FR-AUTH-07) ---------------------------------------------


async def _own_user(ctx: Context, principal: Principal) -> User:
    user = await repository.get_user(ctx.session, principal.user_id, for_update=True)
    if user is None or not user.is_human:
        raise _not_found()
    return user


async def mfa_setup(ctx: Context, principal: Principal) -> MfaSetup:
    """Start (or restart) enrolment: a new secret, kept pending until a code confirms it."""
    user = await _own_user(ctx, principal)
    if user.mfa_enabled_at is not None:
        raise AppError(ErrorCode.AUTH_MFA_ALREADY_ENABLED, HTTPStatus.CONFLICT)
    secret = mfa.new_secret()
    user.mfa_pending_secret = crypto.encrypt(ctx.settings, secret)
    await ctx.session.commit()
    return MfaSetup(secret=secret, provisioning_uri=mfa.provisioning_uri(secret, user.email))


async def mfa_confirm(ctx: Context, principal: Principal, code: str) -> MfaRecoveryCodes:
    user = await _own_user(ctx, principal)
    if user.mfa_enabled_at is not None:
        raise AppError(ErrorCode.AUTH_MFA_ALREADY_ENABLED, HTTPStatus.CONFLICT)
    if user.mfa_pending_secret is None:
        raise AppError(ErrorCode.AUTH_MFA_NOT_ENABLED, HTTPStatus.CONFLICT)
    secret = crypto.decrypt(ctx.settings, user.mfa_pending_secret)
    counter = mfa.verify_code(secret, code, ctx.now, None)
    if counter is None:
        raise AppError(
            ErrorCode.AUTH_MFA_CODE_INVALID,
            HTTPStatus.UNPROCESSABLE_CONTENT,
            errors=[FieldError("code", "auth.mfa_code_invalid")],
        )
    codes, hashes = mfa.new_recovery_codes()
    user.mfa_secret = user.mfa_pending_secret
    user.mfa_pending_secret = None
    user.mfa_enabled_at = ctx.now
    user.mfa_recovery_codes = hashes
    user.mfa_last_counter = counter
    await _publish(ctx, "user.mfa_enabled", actor=principal, entity_id=user.id)
    await ctx.session.commit()
    return MfaRecoveryCodes(recovery_codes=codes)


async def mfa_disable(ctx: Context, principal: Principal, password: str) -> None:
    user = await _own_user(ctx, principal)
    if user.mfa_enabled_at is None:
        raise AppError(ErrorCode.AUTH_MFA_NOT_ENABLED, HTTPStatus.CONFLICT)
    provider = PROVIDERS.get(user.auth_provider)
    if provider is None or not await provider.verify_credentials(user, password):
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            HTTPStatus.UNPROCESSABLE_CONTENT,
            errors=[FieldError("password", "password.current_incorrect")],
        )
    timeouts = await runtime_settings.load(ctx.session)
    if timeouts.mfa_required_for_admins and principal.role is RoleCode.ADMIN:
        raise AppError(ErrorCode.AUTH_MFA_ENFORCED, HTTPStatus.FORBIDDEN)
    _clear_mfa(user)
    await _publish(ctx, "user.mfa_disabled", actor=principal, entity_id=user.id)
    await ctx.session.commit()


def _clear_mfa(user: User) -> None:
    user.mfa_secret = None
    user.mfa_pending_secret = None
    user.mfa_enabled_at = None
    user.mfa_recovery_codes = None
    user.mfa_last_counter = None


async def reset_mfa(session: AsyncSession, events: EventBus, now: datetime, email: str) -> bool:
    """CLI only (operations guide): switch MFA off for a user who lost the device and the
    recovery codes. Their sessions end; audited with no actor (the operator)."""
    user = await repository.get_user_by_email(session, email.strip(), for_update=True)
    if user is None or not user.is_human:
        return False
    _clear_mfa(user)
    await repository.delete_user_sessions(session, user.id)
    await events.publish(
        session,
        DomainEvent(
            action="user.mfa_reset",
            entity_type="user",
            entity_id=user.id,
            actor=None,
            occurred_at=now,
            details={"via": "cli"},
        ),
    )
    await session.commit()
    return True


async def update_me(ctx: Context, principal: Principal, changes: MeUpdate) -> Me:
    user = await repository.get_user(ctx.session, principal.user_id, for_update=True)
    if user is None:
        raise _not_found()
    before = _audit_view(user)
    for key, value in changes.model_dump(exclude_none=True).items():
        setattr(user, key, value)
    user.updated_by = principal.user_id
    after = _audit_view(user)
    if after != before:
        await _publish(
            ctx, "user.updated", actor=principal, entity_id=user.id, before=before, after=after
        )
    await ctx.session.commit()
    return await get_me(ctx, principal)


async def list_my_sessions(ctx: Context, principal: Principal) -> list[SessionInfo]:
    sessions = await repository.list_user_sessions(ctx.session, principal.user_id, ctx.now)
    return [
        SessionInfo(
            id=s.id,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            expires_at=s.expires_at,
            ip=s.ip,
            user_agent=s.user_agent,
            current=s.id == principal.session_id,
        )
        for s in sessions
    ]


async def revoke_my_session(ctx: Context, principal: Principal, session_id: UUID) -> None:
    sessions = await repository.list_user_sessions(ctx.session, principal.user_id, ctx.now)
    if session_id not in {s.id for s in sessions}:
        raise _not_found()
    await repository.delete_session(ctx.session, session_id)
    await _publish(
        ctx,
        "session.revoked",
        actor=principal,
        entity_type="session",
        entity_id=session_id,
        details={"user_id": str(principal.user_id)},
    )
    await ctx.session.commit()


# --- Users (administration) ---------------------------------------------------


async def lookup_users(
    ctx: Context, *, q: str | None, email: str | None, page: int, page_size: int
) -> UserLookupPage:
    """Active human users for owner and assignee pickers (FR-LEAD-06)."""
    if email:
        user = await repository.get_user_by_email(ctx.session, email.strip())
        found = [user] if user is not None and user.is_active and user.is_human else []
        items = [UserLookupItem(id=u.id, full_name=u.full_name, email=u.email) for u in found]
        return UserLookupPage(items=items, total=len(items), page=1, page_size=page_size)
    users, total = await repository.list_users(
        ctx.session,
        q=q,
        role_code=None,
        is_active=True,
        include_service=False,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return UserLookupPage(
        items=[UserLookupItem(id=u.id, full_name=u.full_name, email=u.email) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


async def list_users(
    ctx: Context,
    *,
    q: str | None,
    role: RoleCode | None,
    is_active: bool | None,
    page: int,
    page_size: int,
) -> UserPage:
    users, total = await repository.list_users(
        ctx.session,
        q=q,
        role_code=role.value if role else None,
        is_active=is_active,
        include_service=False,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return UserPage(
        items=[_user_out(u, ctx.now) for u in users], total=total, page=page, page_size=page_size
    )


async def get_user(ctx: Context, user_id: UUID) -> UserOut:
    user = await repository.get_user(ctx.session, user_id)
    if user is None or not user.is_human:
        raise _not_found()
    return _user_out(user, ctx.now)


async def _role_id(ctx: Context, code: str) -> UUID:
    role = await repository.get_role_by_code(ctx.session, code)
    if role is None:  # pragma: no cover - roles are seeded by migration
        raise AppError(ErrorCode.VALIDATION_FAILED, HTTPStatus.UNPROCESSABLE_CONTENT)
    return role.id


async def _ensure_email_free(ctx: Context, email: str, except_user: UUID | None = None) -> None:
    existing = await repository.get_user_by_email(ctx.session, email)
    if existing is not None and existing.id != except_user:
        raise AppError(
            ErrorCode.CONFLICT_DUPLICATE,
            HTTPStatus.CONFLICT,
            errors=[FieldError("email", "user.email_taken")],
            extra={"matches": [{"id": str(existing.id), "entity_type": "user"}]},
        )


async def create_user(ctx: Context, principal: Principal | None, data: UserCreate) -> UserCreated:
    """FR-AUTH-02, FR-ADM-01: no self-registration; the new user gets a one-time link."""
    await _ensure_email_free(ctx, data.email)
    actor_id = principal.user_id if principal else None
    user = User(
        user_type="human",
        email=data.email,
        full_name=data.full_name,
        role_id=await _role_id(ctx, data.role),
        locale=data.locale,
        created_by=actor_id,
        updated_by=actor_id,
    )
    ctx.session.add(user)
    try:
        await ctx.session.flush()
    except IntegrityError as error:
        # Two requests for the same email at once: the second loses the race at the
        # unique index and gets the same answer as the check above.
        await ctx.session.rollback()
        if "uq_app_user_email_lower" not in str(error.orig):
            raise
        raise AppError(
            ErrorCode.CONFLICT_DUPLICATE,
            HTTPStatus.CONFLICT,
            errors=[FieldError("email", "user.email_taken")],
        ) from None
    await ctx.session.refresh(user)
    link = await _issue_password_token(ctx, user, "set", created_by=actor_id)
    await _publish(ctx, "user.created", actor=principal, entity_id=user.id, after=_audit_view(user))
    out = await _committed_user_out(ctx, user)
    link = await _email_link(ctx, user, "set", link)
    return UserCreated(user=out, set_password=link)


async def _load_for_admin(ctx: Context, user_id: UUID) -> User:
    user = await repository.get_user(ctx.session, user_id, for_update=True)
    if user is None or not user.is_human:
        raise _not_found()
    return user


async def _ensure_not_last_admin(ctx: Context, user: User) -> None:
    is_active_admin = user.role.code == RoleCode.ADMIN and user.is_active
    if is_active_admin and await repository.count_active_admins(ctx.session) <= 1:
        raise AppError(ErrorCode.PERMISSION_LAST_ADMIN, HTTPStatus.CONFLICT)


async def update_user(
    ctx: Context, principal: Principal, user_id: UUID, changes: UserUpdate
) -> UserOut:
    user = await _load_for_admin(ctx, user_id)
    before = _audit_view(user)
    values = changes.model_dump(exclude_none=True)
    if "email" in values:
        await _ensure_email_free(ctx, values["email"], except_user=user.id)
    if "role" in values and values["role"] != user.role.code:
        await _ensure_not_last_admin(ctx, user)
        user.role_id = await _role_id(ctx, values.pop("role"))
    else:
        values.pop("role", None)
    for key, value in values.items():
        setattr(user, key, value)
    user.updated_by = principal.user_id
    await ctx.session.flush()
    await ctx.session.refresh(user)
    after = _audit_view(user)
    if after != before:
        action = "user.role_changed" if after["role"] != before["role"] else "user.updated"
        await _publish(ctx, action, actor=principal, entity_id=user.id, before=before, after=after)
    return await _committed_user_out(ctx, user)


async def deactivate_user(ctx: Context, principal: Principal, user_id: UUID) -> UserOut:
    """FR-ADM-01: sessions end, records stay. Not oneself, never the last Admin."""
    user = await _load_for_admin(ctx, user_id)
    if user.id == principal.user_id:
        raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)
    await _ensure_not_last_admin(ctx, user)
    if user.is_active:
        before = _audit_view(user)
        user.is_active = False
        user.updated_by = principal.user_id
        await repository.delete_user_sessions(ctx.session, user.id)
        await _publish(
            ctx,
            "user.deactivated",
            actor=principal,
            entity_id=user.id,
            before=before,
            after=_audit_view(user),
        )
    return await _committed_user_out(ctx, user)


async def activate_user(ctx: Context, principal: Principal, user_id: UUID) -> UserOut:
    user = await _load_for_admin(ctx, user_id)
    if not user.is_active:
        before = _audit_view(user)
        user.is_active = True
        user.updated_by = principal.user_id
        await _publish(
            ctx,
            "user.activated",
            actor=principal,
            entity_id=user.id,
            before=before,
            after=_audit_view(user),
        )
    return await _committed_user_out(ctx, user)


async def issue_password_reset(ctx: Context, principal: Principal, user_id: UUID) -> PasswordLink:
    user = await _load_for_admin(ctx, user_id)
    if not user.is_active:
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            HTTPStatus.UNPROCESSABLE_CONTENT,
            errors=[FieldError("user_id", "user.inactive")],
        )
    purpose = "reset" if user.password_hash else "set"
    link = await _issue_password_token(ctx, user, purpose, created_by=principal.user_id)
    await _publish(ctx, "user.password_reset_issued", actor=principal, entity_id=user.id)
    await ctx.session.commit()
    return await _email_link(ctx, user, purpose, link)


async def unlock_user(ctx: Context, principal: Principal, user_id: UUID) -> UserOut:
    user = await _load_for_admin(ctx, user_id)
    user.locked_until = None
    user.failed_login_count = 0
    await _publish(ctx, "user.unlocked", actor=principal, entity_id=user.id)
    return await _committed_user_out(ctx, user)


async def revoke_user_sessions(ctx: Context, principal: Principal, user_id: UUID) -> None:
    user = await _load_for_admin(ctx, user_id)
    count = await repository.delete_user_sessions(ctx.session, user.id)
    await _publish(
        ctx,
        "user.sessions_revoked",
        actor=principal,
        entity_id=user.id,
        details={"sessions": count},
    )
    await ctx.session.commit()


async def list_roles(ctx: Context) -> list[RoleOut]:
    roles = await repository.list_roles(ctx.session)
    return [
        RoleOut(
            code=RoleCode(r.code),
            name=r.name,
            permissions=sorted(permissions_for(RoleCode(r.code))),
        )
        for r in roles
        if r.code != RoleCode.INTEGRATION
    ]


# --- For other modules ----------------------------------------------------------


async def user_names(session: AsyncSession, user_ids: set[UUID]) -> dict[UUID, str]:
    """Display names for embedded owner/author summaries (API spec 1.5)."""
    return {u.id: u.full_name for u in await repository.get_users(session, user_ids)}


async def is_assignable_owner(session: AsyncSession, user_id: UUID) -> bool:
    """Records may be owned only by active human users (FR-INT-03 AC4 relies on this too)."""
    user = await repository.get_user(session, user_id)
    return user is not None and user.is_active and user.is_human


async def owner_id_by_email(session: AsyncSession, email: str) -> UUID | None:
    """An active human user by email, e.g. the owner column of an import (FR-IMP-01)."""
    user = await repository.get_user_by_email(session, email.strip())
    return user.id if user is not None and user.is_active and user.is_human else None


async def user_locale(session: AsyncSession, user_id: UUID) -> Literal["en", "bg"]:
    """The user's interface language (exports default to it, API spec 14)."""
    user = await repository.get_user(session, user_id)
    return "bg" if user is not None and user.locale == "bg" else "en"


async def is_contributor(session: AsyncSession, user_id: UUID) -> bool:
    """Active human who may change records (Admin, Sales Manager, Sales Rep): task assignees."""
    user = await repository.get_user(session, user_id)
    return (
        user is not None
        and user.is_active
        and user.is_human
        and principal_for(user).role in CONTRIBUTOR_ROLES
    )


# --- Operations (CLI and worker) ----------------------------------------------


async def create_admin(
    ctx: Context, *, email: str, full_name: str, locale: str, password: str | None
) -> UserCreated:
    """First-run bootstrap (`python -m app.cli create-admin`); there is no default account."""
    if password is not None:
        _check_password_policy(password, "password")
    created = await create_user(
        ctx,
        None,
        UserCreate(email=email, full_name=full_name, role="admin", locale=locale),  # type: ignore[arg-type]
    )
    if password is not None:
        user = await repository.get_user(ctx.session, created.user.id, for_update=True)
        assert user is not None  # noqa: S101 - just created
        await _set_password(ctx, user, password)
        await repository.expire_open_password_tokens(ctx.session, user.id, ctx.now)
        await _publish(
            ctx,
            "auth.password_set",
            actor=None,
            entity_id=user.id,
            details={"purpose": "bootstrap"},
        )
        await ctx.session.commit()
    return created


async def purge_expired(session: AsyncSession, now: datetime) -> dict[str, int]:
    """Housekeeping: expired sessions and password tokens older than a week."""
    sessions = await repository.delete_expired_sessions(session, now)
    tokens = await repository.delete_stale_password_tokens(session, now - timedelta(days=7))
    await session.commit()
    return {"sessions": sessions, "password_tokens": tokens}


# --- Service users for integration clients (FR-INT-01) -----------------------------------------


async def create_service_user(session: AsyncSession, name: str, system: str) -> UUID:
    """A non-human user that represents an integration client: it has no password, cannot
    sign in or own records, and is shown as the actor (e.g. "ERP (integration)")."""
    role = await repository.get_role_by_code(session, RoleCode.INTEGRATION.value)
    assert role is not None  # noqa: S101 - roles are seeded by migration 0002
    user = User(
        email=f"{system}-{new_id().hex[:12]}@integration.invalid",
        full_name=f"{name} (integration)",
        user_type="service",
        role_id=role.id,
        locale="en",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user.id


async def update_service_user(
    session: AsyncSession, user_id: UUID, *, name: str | None = None, active: bool | None = None
) -> None:
    user = await repository.get_user(session, user_id)
    if user is None or user.is_human:
        return
    if name is not None:
        user.full_name = f"{name} (integration)"
    if active is not None:
        user.is_active = active
