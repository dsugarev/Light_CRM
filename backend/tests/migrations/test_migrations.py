"""Migration tests (test strategy section 2; architecture 4.2).

- Every migration upgrades and has a working downgrade, step by step.
- The SQLAlchemy models match the schema the migrations produce, so no table
  or column exists that did not come through Alembic.
- The application role cannot run DDL.
"""

import asyncio
import importlib
import pkgutil

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine

import app.core.ratelimit  # registers core tables
import app.core.runtime_settings
import app.modules
from app.core.db import Base
from app.core.migrations import alembic_config
from tests.conftest import TEST_APP_DATABASE_URL


def _revisions_base_to_head(database_url: str) -> list[str]:
    script = ScriptDirectory.from_config(alembic_config(database_url))
    return [rev.revision for rev in reversed(list(script.walk_revisions()))]


def test_NFR_12_every_migration_upgrades_and_downgrades(migrated_database: str) -> None:
    config = alembic_config(migrated_database)
    command.downgrade(config, "base")
    for revision in _revisions_base_to_head(migrated_database):
        command.upgrade(config, revision)
        command.downgrade(config, "-1")
        command.upgrade(config, revision)
    command.upgrade(config, "head")


def _schema_diff(connection: Connection) -> list[object]:
    for module in pkgutil.iter_modules(app.modules.__path__):
        importlib.import_module(f"app.modules.{module.name}.models")
    context = MigrationContext.configure(connection, opts={"compare_type": True})
    return list(compare_metadata(context, Base.metadata))


def test_NFR_12_models_match_migrations(migrated_database: str) -> None:
    async def diff() -> list[object]:
        engine = create_async_engine(migrated_database)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(_schema_diff)
        finally:
            await engine.dispose()

    assert asyncio.run(diff()) == []


def test_pg_trgm_is_installed(migrated_database: str) -> None:
    async def installed() -> bool:
        engine = create_async_engine(migrated_database)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
                )
                return result.scalar() == 1
        finally:
            await engine.dispose()

    assert asyncio.run(installed())


def test_NFR_04_application_role_cannot_run_ddl(migrated_database: str) -> None:
    async def create_table() -> None:
        engine = create_async_engine(TEST_APP_DATABASE_URL)
        try:
            async with engine.connect() as connection:
                await connection.execute(text("CREATE TABLE should_not_exist (id int)"))
        finally:
            await engine.dispose()

    with pytest.raises(ProgrammingError, match="permission denied"):
        asyncio.run(create_table())
