"""Alembic environment (async, asyncpg).

Uses the migration (DDL) role: MIGRATION_DATABASE_URL, or DATABASE_URL when it is
not set. A URL set on the Alembic config (as the tests do) takes precedence.
"""

import asyncio
import importlib
import pkgutil

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.core.ratelimit  # registers core tables
import app.core.runtime_settings
import app.modules
from app.core.config import get_settings
from app.core.db import Base

# Import every module's models so autogenerate and the drift test see all tables.
for module in pkgutil.iter_modules(app.modules.__path__):
    importlib.import_module(f"app.modules.{module.name}.models")

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    return (
        config.get_main_option("sqlalchemy.url") or get_settings().effective_migration_database_url
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
