"""Shared fixtures. Tests run against a real PostgreSQL database, never SQLite.

TEST_DATABASE_URL      migration (DDL) role, used to migrate the test database
TEST_APP_DATABASE_URL  application (DML) role, used by the app under test
"""

import os
from collections.abc import AsyncIterator

import httpx
import pytest
from alembic import command
from pydantic import PostgresDsn
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import runtime_settings
from app.core.clock import FrozenClock
from app.core.config import Environment, Settings
from app.core.migrations import alembic_config
from app.main import create_app
from tests.helpers import START, RecordingMailer, TestApp, app_client

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://crm_migrator:change-me@localhost:5432/crm_test"
)
TEST_APP_DATABASE_URL = os.environ.get(
    "TEST_APP_DATABASE_URL", "postgresql+asyncpg://crm_app:change-me@localhost:5432/crm_test"
)


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """Bring the test database to the latest migration once per test run."""
    command.upgrade(alembic_config(TEST_DATABASE_URL), "head")
    return TEST_DATABASE_URL


# Reference data seeded by migrations, restored after each API test.
_SEEDED_TABLES = (
    "industry",
    "lead_source",
    "disqualification_reason",
    "loss_reason",
    "pipeline",
    "pipeline_stage",
)


@pytest.fixture(scope="session")
async def seed_snapshot(migrated_database: str) -> dict[str, list[dict[str, object]]]:
    engine = create_async_engine(migrated_database)
    try:
        async with engine.connect() as connection:
            return {
                table: [
                    dict(row._mapping)
                    for row in await connection.execute(text(f"SELECT * FROM {table}"))  # noqa: S608
                ]
                for table in _SEEDED_TABLES
            }
    finally:
        await engine.dispose()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env=Environment.TEST,
        database_url=PostgresDsn(TEST_APP_DATABASE_URL),
        migration_database_url=PostgresDsn(TEST_DATABASE_URL),
        database_pool_size=2,
        health_check_timeout_seconds=2.0,
        public_url="https://crm.example.test",
        sync_safety_lag_seconds=0,
    )


# Tables emptied before each API test. TRUNCATE needs the migration role: the
# application role may not truncate the append-only audit_log.
_DATA_TABLES = (
    "audit_log, user_session, password_token, app_user, rate_limit_bucket, app_setting, "
    "contact, organization, industry, lead, lead_source, disqualification_reason, "
    "opportunity_stage_history, opportunity, pipeline_stage, pipeline, loss_reason"
)


@pytest.fixture
async def clean_database(
    migrated_database: str, seed_snapshot: dict[str, list[dict[str, object]]]
) -> None:
    engine = create_async_engine(migrated_database)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"TRUNCATE {_DATA_TABLES} CASCADE"))
            await connection.execute(text("INSERT INTO app_setting (id) VALUES (1)"))
            for table, rows in seed_snapshot.items():
                if rows:
                    columns = ", ".join(rows[0])
                    values = ", ".join(f":{c}" for c in rows[0])
                    await connection.execute(
                        text(f"INSERT INTO {table} ({columns}) VALUES ({values})"),  # noqa: S608
                        rows,
                    )
    finally:
        await engine.dispose()
    runtime_settings.invalidate_cache()


@pytest.fixture
async def test_app(clean_database: None, settings: Settings) -> AsyncIterator[TestApp]:
    """A running app on a clean database, with a frozen clock and a recording mailer."""
    clock = FrozenClock(START)
    mailer = RecordingMailer()
    app = create_app(settings, clock=clock, mailer=mailer)
    async with app.router.lifespan_context(app):
        harness = TestApp(app, clock, mailer)
        try:
            yield harness
        finally:
            await harness.close()


@pytest.fixture
async def client(clean_database: None, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client for an app connected to the migrated test database."""
    async with app_client(create_app(settings)) as c:
        yield c
