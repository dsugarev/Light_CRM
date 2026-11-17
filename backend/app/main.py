"""Application factory and router registration."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core import health
from app.core.config import Settings, get_settings
from app.core.db import create_engine, create_session_factory
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

API_V1_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
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

    # Phase 0 has no authentication, so the OpenAPI document and the interactive
    # docs are published only outside production. Phase 1 serves the document to
    # signed-in users and integration clients in production (API spec section 2).
    publish_docs = not settings.is_production
    app = FastAPI(
        title="Light CRM API",
        version=settings.app_version,
        openapi_url=f"{API_V1_PREFIX}/openapi.json" if publish_docs else None,
        docs_url="/api/docs" if publish_docs else None,
        redoc_url=None,
        swagger_ui_oauth2_redirect_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)

    return app


app = create_app()
