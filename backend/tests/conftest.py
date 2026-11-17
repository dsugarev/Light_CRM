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

from app.core.config import Environment, Settings
from app.core.migrations import alembic_config
from app.main import create_app
from tests.helpers import app_client

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


@pytest.fixture
def settings() -> Settings:
    return Settings(
        env=Environment.TEST,
        database_url=PostgresDsn(TEST_APP_DATABASE_URL),
        migration_database_url=PostgresDsn(TEST_DATABASE_URL),
        database_pool_size=2,
        health_check_timeout_seconds=2.0,
    )


@pytest.fixture
async def client(migrated_database: str, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client for an app connected to the migrated test database."""
    async with app_client(create_app(settings)) as c:
        yield c
