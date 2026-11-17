"""Settings: secrets come from the environment; defaults are refused in production."""

import pytest
from pydantic import PostgresDsn, ValidationError

from app.core.config import Environment, Settings

REAL_URL = PostgresDsn("postgresql+asyncpg://crm_app:s3cr3t-from-vault@db:5432/crm")


def test_NFR_04_production_refuses_default_database_secret() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(env=Environment.PRODUCTION)


def test_NFR_04_production_refuses_default_migration_secret() -> None:
    with pytest.raises(ValidationError, match="MIGRATION_DATABASE_URL"):
        Settings(
            env=Environment.PRODUCTION,
            database_url=REAL_URL,
            migration_database_url=PostgresDsn(
                "postgresql+asyncpg://crm_migrator:change-me@db:5432/crm"
            ),
        )


def test_NFR_04_production_starts_with_real_secrets() -> None:
    settings = Settings(env=Environment.PRODUCTION, database_url=REAL_URL)
    assert settings.is_production


def test_development_allows_placeholder_secrets() -> None:
    assert not Settings(env=Environment.DEVELOPMENT).is_production


def test_settings_are_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    settings = Settings()
    assert settings.env is Environment.TEST
    assert settings.log_level == "DEBUG"


def test_migration_url_falls_back_to_database_url() -> None:
    settings = Settings(database_url=REAL_URL)
    assert settings.effective_migration_database_url == str(REAL_URL)
