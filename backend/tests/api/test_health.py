"""Health endpoints and API documentation (API spec section 2, NFR-08)."""

import httpx
import pytest
from pydantic import PostgresDsn

from app.core import health
from app.core.config import Environment, Settings
from app.main import create_app
from tests.helpers import app_client


async def test_NFR_08_live_is_ok_without_dependencies(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_NFR_08_ready_is_ok_when_database_is_at_head(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]


async def test_NFR_08_ready_is_503_when_migrations_are_behind(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "head_revisions", lambda: frozenset({"9999"}))
    response = await client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


async def test_NFR_08_ready_is_503_when_database_is_unreachable(settings: Settings) -> None:
    unreachable = settings.model_copy(
        update={
            "database_url": PostgresDsn("postgresql+asyncpg://crm_app:x@127.0.0.1:1/crm"),
            "health_check_timeout_seconds": 1.0,
        }
    )
    async with app_client(create_app(unreachable)) as client:
        response = await client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


async def test_NFR_08_health_reveals_status_only(client: httpx.AsyncClient) -> None:
    for path in ("/api/health/live", "/api/health/ready"):
        assert set((await client.get(path)).json()) == {"status"}


async def test_FR_INT_10_openapi_document_is_public_outside_production(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    document = response.json()
    assert document["paths"]["/api/health/ready"]["get"]["x-access-level"] == "Public"
    assert (await client.get("/api/docs")).status_code == 200


async def test_openapi_and_docs_are_not_published_in_production(settings: Settings) -> None:
    production = settings.model_copy(
        update={
            "env": Environment.PRODUCTION,
            "database_url": PostgresDsn("postgresql+asyncpg://crm_app:real@127.0.0.1:1/crm"),
        }
    )
    async with app_client(create_app(production)) as client:
        assert (await client.get("/api/v1/openapi.json")).status_code == 404
        assert (await client.get("/api/docs")).status_code == 404
