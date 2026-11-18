"""Application settings, read from environment variables only (twelve-factor)."""

from enum import StrEnum
from functools import lru_cache
from typing import Self

from pydantic import Field, PostgresDsn, SecretStr, model_validator
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
    app_build: str = "dev"
    log_level: str = "INFO"

    # Origin users open the application on. Used for links in emails and for the
    # CSRF Origin check; extra trusted origins (e.g. the Vite dev server) can be added.
    public_url: str = "https://localhost"
    csrf_trusted_origins: list[str] = []

    # Signs opaque tokens such as sync cursors. Must be a long random value in production.
    app_secret_key: str = f"{INSECURE_PLACEHOLDER}-secret-key"
    # Encrypts secrets the application must read back, such as webhook signing secrets
    # (architecture 4.5). Changing it makes stored webhook secrets unreadable.
    app_encryption_key: str = f"{INSECURE_PLACEHOLDER}-encryption-key"

    # The application connects with a DML-only role; migrations use a separate
    # DDL role (architecture section 7, "Database").
    database_url: PostgresDsn = PostgresDsn(
        f"postgresql+asyncpg://crm_app:{INSECURE_PLACEHOLDER}@localhost:5432/crm"
    )
    migration_database_url: PostgresDsn | None = None
    database_pool_size: int = Field(default=10, ge=1)
    database_connect_timeout_seconds: float = Field(default=5.0, gt=0)

    health_check_timeout_seconds: float = Field(default=2.0, gt=0)

    # Sync mode only returns rows older than this, so a transaction that commits
    # late cannot slip behind a client's cursor (FR-INT-05 AC2).
    sync_safety_lag_seconds: float = Field(default=5.0, ge=0)
    worker_poll_interval_seconds: float = Field(default=5.0, gt=0)

    # Authentication (FR-AUTH-01..04). Session timeouts are runtime settings
    # (GET/PATCH /settings); these are fixed policy values.
    login_max_failed_attempts: int = Field(default=5, ge=1)
    login_lockout_minutes: int = Field(default=15, ge=1)
    password_set_token_hours: int = Field(default=72, ge=1)
    password_reset_token_hours: int = Field(default=2, ge=1)

    # Rate limits (API spec section 18).
    rate_limit_login_per_minute: int = Field(default=10, ge=1)
    rate_limit_password_per_15_minutes: int = Field(default=5, ge=1)
    rate_limit_user_per_minute: int = Field(default=600, ge=1)

    # Webhooks (API spec 19.6): hosts subscriptions may target, as exact names or
    # "*.suffix", separated by commas or spaces. Empty: no webhook URL is allowed.
    webhook_allowed_hosts: str = ""

    # AI assistant (architecture section 8, FR-AI-07/08). Off until the owner confirms the
    # LLM data flow (requirements section 8, question 1).
    ai_enabled: bool = False
    openrouter_api_key: SecretStr | None = None
    llm_model: str = "openrouter/openai/gpt-oss-120b"
    llm_provider: str = "cerebras"
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    # Development and end-to-end tests only: a scripted model instead of the provider.
    llm_fake: bool = False
    ai_daily_token_budget: int = Field(default=200_000, ge=1)
    ai_history_tokens: int = Field(default=8_000, ge=500)
    rate_limit_assistant_per_10_minutes: int = Field(default=20, ge=1)

    # Optional SMTP (A6): every flow works without it.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "crm@localhost"
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = Field(default=10.0, gt=0)

    @property
    def smtp_enabled(self) -> bool:
        return bool(self.smtp_host)

    @property
    def trusted_origins(self) -> frozenset[str]:
        return frozenset(
            {self.public_url.rstrip("/"), *(o.rstrip("/") for o in self.csrf_trusted_origins)}
        )

    @property
    def webhook_host_patterns(self) -> tuple[str, ...]:
        return tuple(
            h.strip().lower().rstrip(".")
            for h in self.webhook_allowed_hosts.replace(",", " ").split()
            if h.strip()
        )

    @property
    def is_production(self) -> bool:
        return self.env is Environment.PRODUCTION

    @property
    def effective_migration_database_url(self) -> str:
        return str(self.migration_database_url or self.database_url)

    @model_validator(mode="after")
    def _assistant_needs_a_model(self) -> Self:
        if self.llm_fake and self.is_production:
            raise ValueError("LLM_FAKE is for development and tests; refusing it in production")
        if self.ai_enabled and not self.llm_fake and not self.openrouter_api_key:
            raise ValueError("AI_ENABLED needs OPENROUTER_API_KEY")
        return self

    @model_validator(mode="after")
    def _refuse_default_secrets_in_production(self) -> Self:
        if not self.is_production:
            return self
        secrets = {
            "DATABASE_URL": str(self.database_url),
            "MIGRATION_DATABASE_URL": str(self.migration_database_url or ""),
            "SMTP_PASSWORD": self.smtp_password or "",
            "APP_SECRET_KEY": self.app_secret_key,
            "APP_ENCRYPTION_KEY": self.app_encryption_key,
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
