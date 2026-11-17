"""RFC 9457 problem details and request IDs (API spec sections 1.2 and 1.6)."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.errors import (
    PROBLEM_CONTENT_TYPE,
    AppError,
    ErrorCode,
    FieldError,
    register_error_handlers,
)
from app.core.middleware import RequestContextMiddleware


class Payload(BaseModel):
    name: str
    count: int


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.post("/items")
    async def create(payload: Payload) -> Payload:
        return payload

    @app.get("/conflict")
    async def conflict() -> None:
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            409,
            detail="Changed elsewhere",
            errors=[FieldError("version", "validation.stale")],
            extra={"current": {"version": 2}},
            headers={"Retry-After": "1"},
        )

    @app.get("/crash")
    async def crash() -> None:
        raise RuntimeError("database password is hunter2")

    return app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(), raise_app_exceptions=False),
        base_url="http://testserver",
    ) as c:
        yield c


async def test_validation_errors_are_problem_details_with_field_codes(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/items", json={"count": "many"})
    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    body = response.json()
    assert body["code"] == "validation.failed"
    assert body["type"] == "https://crm.internal/errors/validation.failed"
    assert body["status"] == 422
    assert body["request_id"] == response.headers["x-request-id"]
    assert {(e["field"], e["code"]) for e in body["errors"]} == {
        ("name", "validation.missing"),
        ("count", "validation.int_parsing"),
    }


async def test_malformed_json_is_400(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/items", content=b"{not json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["errors"] == [{"field": "body", "code": "validation.json_invalid"}]


async def test_unknown_route_is_resource_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_CONTENT_TYPE
    assert response.json()["code"] == "resource.not_found"


async def test_wrong_method_is_method_not_allowed(client: httpx.AsyncClient) -> None:
    response = await client.delete("/items")
    assert response.status_code == 405
    assert response.json()["code"] == "request.method_not_allowed"


async def test_app_error_carries_detail_errors_extra_and_headers(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/conflict")
    assert response.status_code == 409
    assert response.headers["retry-after"] == "1"
    body = response.json()
    assert body["detail"] == "Changed elsewhere"
    assert body["errors"] == [{"field": "version", "code": "validation.stale"}]
    assert body["current"] == {"version": 2}


async def test_NFR_08_unhandled_error_is_generic_500_with_request_id(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    response = await client.get("/crash", headers={"X-Request-ID": "trace-1"})
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "trace-1"
    body = response.json()
    assert body["code"] == "server.internal_error"
    assert body["request_id"] == "trace-1"
    # Internal details never reach the caller.
    assert "hunter2" not in response.text
    assert any(r.message == "unhandled_error" for r in caplog.records)


async def test_client_request_id_is_echoed(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


async def test_unsafe_client_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope", headers={"X-Request-ID": "bad id\twith spaces"})
    generated = response.headers["x-request-id"]
    assert generated != "bad id\twith spaces"
    assert len(generated) == 32


async def test_request_id_is_generated_when_absent(client: httpx.AsyncClient) -> None:
    first = (await client.get("/nope")).headers["x-request-id"]
    second = (await client.get("/nope")).headers["x-request-id"]
    assert first != second
