"""Test helpers shared across suites."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any
from uuid import UUID

import httpx
from argon2 import PasswordHasher
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import CSRF_HEADER, CSRF_HEADER_VALUE
from app.core.clock import FrozenClock
from app.core.mailer import Email
from app.core.principal import Principal, PrincipalType, RoleCode
from app.modules.audit.models import AuditLog
from app.modules.identity.models import Role, User, UserSession
from app.modules.identity.tokens import new_token
from app.modules.integration.models import IntegrationClient
from tests.factories import UserFactory

BASE_URL = "https://testserver"
DEFAULT_PASSWORD = "Tuesday-Orchard-Lantern-42"
START = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)


@cache
def default_password_hash() -> str:
    """Hash once per run: Argon2 is deliberately slow."""
    return PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1).hash(DEFAULT_PASSWORD)


@asynccontextmanager
async def app_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Run the app's lifespan and yield an HTTP client bound to it."""
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client,
    ):
        yield client


class RecordingMailer:
    """Collects emails instead of sending them."""

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled
        self.sent: list[Email] = []

    async def send(self, email: Email) -> bool:
        self.sent.append(email)
        return True


class TestApp:
    """A running app with a controllable clock and mailer, plus data helpers."""

    __test__ = False  # not a pytest test class

    def __init__(self, app: FastAPI, clock: FrozenClock, mailer: RecordingMailer) -> None:
        self.app = app
        self.clock = clock
        self.mailer = mailer
        self._clients: list[httpx.AsyncClient] = []

    @property
    def sessions(self) -> async_sessionmaker[AsyncSession]:
        factory: async_sessionmaker[AsyncSession] = self.app.state.session_factory
        return factory

    def client(
        self, *, csrf: bool = True, headers: dict[str, str] | None = None, **kwargs: Any
    ) -> httpx.AsyncClient:
        headers = {**({CSRF_HEADER: CSRF_HEADER_VALUE} if csrf else {}), **(headers or {})}
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url=BASE_URL,
            headers=headers,
            **kwargs,
        )
        self._clients.append(client)
        return client

    async def close(self) -> None:
        for client in self._clients:
            await client.aclose()

    async def create_user(
        self,
        role: RoleCode | str = RoleCode.SALES_REP,
        *,
        password: str | None = DEFAULT_PASSWORD,
        **fields: Any,
    ) -> User:
        async with self.sessions() as session:
            role_row = (
                await session.execute(select(Role).where(Role.code == str(role)))
            ).scalar_one()
            user: User = UserFactory.build(role_id=role_row.id, **fields)
            if password == DEFAULT_PASSWORD:
                user.password_hash = default_password_hash()
            elif password is not None:
                user.password_hash = PasswordHasher().hash(password)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def login(
        self, client: httpx.AsyncClient, email: str, password: str = DEFAULT_PASSWORD
    ) -> httpx.Response:
        return await client.post("/api/v1/auth/login", json={"email": email, "password": password})

    async def signed_in(
        self, role: RoleCode | str = RoleCode.SALES_REP, **fields: Any
    ) -> tuple[httpx.AsyncClient, User]:
        user = await self.create_user(role, **fields)
        client = self.client()
        response = await self.login(client, user.email)
        assert response.status_code == 200, response.text
        return client, user

    async def session_client(self, user: User) -> httpx.AsyncClient:
        """A client with a session created directly in the database (no sign-in request)."""
        raw, token_hash = new_token()
        now = self.clock.now()
        async with self.sessions() as session:
            session.add(
                UserSession(
                    user_id=user.id,
                    token_hash=token_hash,
                    created_at=now,
                    last_seen_at=now,
                    expires_at=now + timedelta(days=1),
                )
            )
            await session.commit()
        return self.client(cookies={"session": raw})

    async def integration_client(
        self,
        scopes: Sequence[str] = (),
        *,
        system: str = "erp",
        name: str = "ERP",
        default_owner_id: UUID | None = None,
        rate_limit_per_minute: int = 300,
        ip_allowlist: Sequence[str] = (),
    ) -> IntegrationCaller:
        """Register a client (FR-INT-01), issue a key, and return a client using only it."""
        return await _register_integration(
            self, scopes, system=system, name=name, default_owner_id=default_owner_id,
            rate_limit_per_minute=rate_limit_per_minute, ip_allowlist=ip_allowlist,
        )  # fmt: skip

    async def audit(self, action: str | None = None) -> list[AuditLog]:
        async with self.sessions() as session:
            statement = select(AuditLog).order_by(AuditLog.occurred_at, AuditLog.id)
            if action is not None:
                statement = statement.where(AuditLog.action == action)
            return list((await session.execute(statement)).scalars())


@dataclass(frozen=True, slots=True)
class IntegrationCaller:
    """An integration client registered for a test and an HTTP client using its key."""

    http: httpx.AsyncClient
    client_id: UUID
    service_user_id: UUID
    key: str


async def _register_integration(
    test_app: TestApp,
    scopes: Sequence[str],
    *,
    system: str,
    name: str,
    default_owner_id: UUID | None,
    rate_limit_per_minute: int,
    ip_allowlist: Sequence[str],
) -> IntegrationCaller:
    from app.main import create_event_bus
    from app.modules.integration import service as integration
    from app.modules.integration.schemas import ApiKeyCreate, IntegrationClientCreate

    admin = await test_app.create_user(RoleCode.ADMIN)
    async with test_app.sessions() as session:
        ctx = integration.Context(
            session=session,
            events=create_event_bus(),
            settings=test_app.app.state.settings,
            now=test_app.clock.now(),
        )
        principal = Principal(
            type=PrincipalType.USER, user_id=admin.id, role=RoleCode.ADMIN,
            display_name=admin.full_name,
        )  # fmt: skip
        created = await integration.create_client(
            ctx,
            principal,
            IntegrationClientCreate.model_validate(
                {
                    "name": name,
                    "system": system,
                    "scopes": list(scopes),
                    "default_owner_id": default_owner_id,
                    "rate_limit_per_minute": rate_limit_per_minute,
                    "ip_allowlist": list(ip_allowlist),
                    "is_active": True,
                }
            ),
        )
        key = await integration.create_key(ctx, principal, created.id, ApiKeyCreate(label="test"))
        client_row = await session.get(IntegrationClient, created.id)
        assert client_row is not None
        service_user_id = client_row.service_user_id
    http = test_app.client(csrf=False, headers={"Authorization": f"Bearer {key.key}"})
    return IntegrationCaller(http, created.id, service_user_id, key.key)
