"""Database queries. Called only by this module's service."""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, Delete, Select, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import PasswordToken, Role, User, UserSession


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --- Roles --------------------------------------------------------------------


async def list_roles(session: AsyncSession) -> list[Role]:
    return list((await session.execute(select(Role).order_by(Role.code))).scalars())


async def get_role_by_code(session: AsyncSession, code: str) -> Role | None:
    return (await session.execute(select(Role).where(Role.code == code))).scalar_one_or_none()


# --- Users --------------------------------------------------------------------


async def get_user(
    session: AsyncSession, user_id: UUID, *, for_update: bool = False
) -> User | None:
    statement = select(User).where(User.id == user_id)
    if for_update:
        statement = statement.with_for_update(of=User)
    return (await session.execute(statement)).scalar_one_or_none()


async def get_users(session: AsyncSession, user_ids: set[UUID]) -> list[User]:
    if not user_ids:
        return []
    return list((await session.execute(select(User).where(User.id.in_(user_ids)))).scalars())


async def get_user_by_email(
    session: AsyncSession, email: str, *, for_update: bool = False
) -> User | None:
    statement = select(User).where(func.lower(User.email) == email.lower())
    if for_update:
        statement = statement.with_for_update(of=User)
    return (await session.execute(statement)).scalar_one_or_none()


async def _delete(session: AsyncSession, statement: Delete) -> int:
    result = cast(CursorResult[Any], await session.execute(statement))
    return result.rowcount


def _user_search(statement: Select[User], q: str | None) -> Select[User]:
    if q:
        pattern = f"%{_escape_like(q)}%"
        statement = statement.where(
            or_(User.full_name.ilike(pattern, escape="\\"), User.email.ilike(pattern, escape="\\"))
        )
    return statement


async def list_users(
    session: AsyncSession,
    *,
    q: str | None,
    role_code: str | None,
    is_active: bool | None,
    include_service: bool,
    offset: int,
    limit: int,
) -> tuple[list[User], int]:
    statement = _user_search(select(User).join(User.role), q)
    if role_code is not None:
        statement = statement.where(Role.code == role_code)
    if is_active is not None:
        statement = statement.where(User.is_active == is_active)
    if not include_service:
        statement = statement.where(User.user_type == "human")
    total = (
        await session.execute(select(func.count()).select_from(statement.subquery()))
    ).scalar_one()
    rows = await session.execute(
        statement.order_by(func.lower(User.full_name), User.id).offset(offset).limit(limit)
    )
    users: list[User] = list(rows.scalars())
    return users, total


async def count_active_admins(session: AsyncSession) -> int:
    statement = (
        select(func.count())
        .select_from(User)
        .join(User.role)
        .where(Role.code == "admin", User.is_active.is_(True), User.user_type == "human")
    )
    return (await session.execute(statement)).scalar_one()


# --- Sessions -----------------------------------------------------------------


async def get_session_by_token_hash(session: AsyncSession, token_hash: str) -> UserSession | None:
    statement = select(UserSession).where(UserSession.token_hash == token_hash)
    return (await session.execute(statement)).scalar_one_or_none()


async def list_user_sessions(
    session: AsyncSession, user_id: UUID, now: datetime
) -> list[UserSession]:
    statement = (
        select(UserSession)
        .where(UserSession.user_id == user_id, UserSession.expires_at > now)
        .order_by(UserSession.last_seen_at.desc())
    )
    return list((await session.execute(statement)).scalars())


async def delete_session(session: AsyncSession, session_id: UUID) -> None:
    await session.execute(delete(UserSession).where(UserSession.id == session_id))


async def delete_user_sessions(
    session: AsyncSession, user_id: UUID, *, except_session_id: UUID | None = None
) -> int:
    statement = delete(UserSession).where(UserSession.user_id == user_id)
    if except_session_id is not None:
        statement = statement.where(UserSession.id != except_session_id)
    return await _delete(session, statement)


async def delete_expired_sessions(session: AsyncSession, now: datetime) -> int:
    statement = delete(UserSession).where(UserSession.expires_at <= now)
    return await _delete(session, statement)


# --- Password tokens ----------------------------------------------------------


async def get_password_token(session: AsyncSession, token_hash: str) -> PasswordToken | None:
    statement = select(PasswordToken).where(PasswordToken.token_hash == token_hash)
    return (await session.execute(statement)).scalar_one_or_none()


async def expire_open_password_tokens(session: AsyncSession, user_id: UUID, now: datetime) -> None:
    """A new link replaces older unused ones."""
    await session.execute(
        update(PasswordToken)
        .where(PasswordToken.user_id == user_id, PasswordToken.used_at.is_(None))
        .values(used_at=now)
    )


async def delete_stale_password_tokens(session: AsyncSession, before: datetime) -> int:
    statement = delete(PasswordToken).where(PasswordToken.expires_at < before)
    return await _delete(session, statement)
