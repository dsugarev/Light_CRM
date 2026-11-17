"""Application settings, read from environment variables only (twelve-factor)."""

from enum import StrEnum
from functools import lru_cache
from typing import Self

from pydantic import Field, PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder marker used in .env.example and in local defaults. The application
# refuses to start in production while any secret still contains it.
INSECURE_PLACEHOLDER = "change-me"


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    env: Environment = Environment.DEVELOPMENT
    app_version: str = "0.1.0"
    log_level: str = "INFO"

    # The application connects with a DML-only role; migrations use a separate
    # DDL role (architecture section 7, "Database").
    database_url: PostgresDsn = PostgresDsn(
        f"postgresql+asyncpg://crm_app:{INSECURE_PLACEHOLDER}@localhost:5432/crm"
    )
    migration_database_url: PostgresDsn | None = None
    database_pool_size: int = Field(default=10, ge=1)
    database_connect_timeout_seconds: float = Field(default=5.0, gt=0)

    health_check_timeout_seconds: float = Field(default=2.0, gt=0)
    worker_poll_interval_seconds: float = Field(default=5.0, gt=0)

    @property
    def is_production(self) -> bool:
        return self.env is Environment.PRODUCTION

    @property
    def effective_migration_database_url(self) -> str:
        return str(self.migration_database_url or self.database_url)

    @model_validator(mode="after")
    def _refuse_default_secrets_in_production(self) -> Self:
        if not self.is_production:
            return self
        secrets = {
            "DATABASE_URL": str(self.database_url),
            "MIGRATION_DATABASE_URL": str(self.migration_database_url or ""),
        }
        insecure = sorted(name for name, value in secrets.items() if INSECURE_PLACEHOLDER in value)
        if insecure:
            raise ValueError(
                "Refusing to start with default secrets in production: " + ", ".join(insecure)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
