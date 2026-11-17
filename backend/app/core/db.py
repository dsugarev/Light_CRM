"""Async database engine, session factory and the declarative base."""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import DateTime, FetchedValue, ForeignKey, MetaData, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from app.core.config import Settings
from app.core.ids import new_id

# Deterministic constraint names so Alembic migrations stay reviewable and stable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=new_id)


class TimestampMixin:
    """created_at/updated_at in UTC. updated_at is maintained by a database trigger
    (`set_updated_at`, migration 0002), so every change, however made, moves it."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        server_onupdate=FetchedValue(),
        nullable=False,
    )


class AuthorshipMixin:
    """created_by/updated_by reference the acting user (human or service user)."""

    @declared_attr
    def created_by(cls) -> Mapped[UUID | None]:  # noqa: N805 - declared_attr receives the class
        return mapped_column(ForeignKey("app_user.id"), nullable=True)

    @declared_attr
    def updated_by(cls) -> Mapped[UUID | None]:  # noqa: N805
        return mapped_column(ForeignKey("app_user.id"), nullable=True)


class ArchiveMixin:
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImportedMixin:
    """`import_batch_id` on records an import can create (FR-IMP-01 AC4): rollback finds them."""

    @declared_attr
    def import_batch_id(cls) -> Mapped[UUID | None]:  # noqa: N805
        return mapped_column(ForeignKey("import_batch.id"), nullable=True, index=True)


class BusinessTableMixin(IdMixin, TimestampMixin, AuthorshipMixin, ArchiveMixin):
    """Columns every business table carries (architecture 4.1)."""


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        str(settings.database_url),
        pool_size=settings.database_pool_size,
        pool_pre_ping=True,
        connect_args={"timeout": settings.database_connect_timeout_seconds},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, closed afterwards.

    Services own transactions (commit/rollback); routers only pass the session on.
    """
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_session)]
