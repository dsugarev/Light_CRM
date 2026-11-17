"""Application factory and router registration."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app.core import health, runtime_settings, system
from app.core.auth import csrf_protect
from app.core.clock import Clock, SystemClock
from app.core.config import Settings, get_settings
from app.core.db import create_engine, create_session_factory
from app.core.errors import ErrorCode, problem_response, register_error_handlers
from app.core.events import EventBus
from app.core.logging import configure_logging
from app.core.mailer import Mailer, create_mailer
from app.core.middleware import RequestContextMiddleware
from app.modules.audit import router as audit_router
from app.modules.audit import service as audit_service
from app.modules.identity import router as identity_router
from app.modules.identity import service as identity_service

API_V1_PREFIX = "/api/v1"
OPENAPI_PATH = f"{API_V1_PREFIX}/openapi.json"


def create_event_bus() -> EventBus:
    """Subscribers to domain events. Phase 6 adds the integration outbox here."""
    bus = EventBus()
    bus.subscribe(audit_service.record)
    return bus


def create_app(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    mailer: Mailer | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    # Outside production the OpenAPI document and docs are public; in production
    # the document is served to signed-in callers only (API spec section 2).
    publish_docs = not settings.is_production
    app = FastAPI(
        title="Light CRM API",
        version=settings.app_version,
        openapi_url=OPENAPI_PATH if publish_docs else None,
        docs_url="/api/docs" if publish_docs else None,
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.clock = clock or SystemClock()
    app.state.mailer = mailer or create_mailer(settings)
    app.state.event_bus = create_event_bus()
    app.state.authenticator = identity_service.authenticate_request

    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)

    api_v1 = APIRouter(prefix=API_V1_PREFIX, dependencies=[Depends(csrf_protect)])
    api_v1.include_router(system.router)
    for router in identity_router.routers:
        api_v1.include_router(router)
    api_v1.include_router(runtime_settings.router)
    api_v1.include_router(audit_router.router)
    app.include_router(api_v1)

    if not publish_docs:
        app.add_route(OPENAPI_PATH, _signed_in_openapi(app), methods=["GET"])

    return app


def _signed_in_openapi(app: FastAPI) -> Callable[[Request], Awaitable[Response]]:
    async def openapi(request: Request) -> Response:
        async with request.app.state.session_factory() as session:
            principal = await request.app.state.authenticator(request, session)
        if principal is None:
            return problem_response(ErrorCode.AUTH_SESSION_EXPIRED, HTTPStatus.UNAUTHORIZED)
        return JSONResponse(app.openapi())

    return openapi


app = create_app()
