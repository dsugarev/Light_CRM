"""Health endpoints (docs/05-api-specification.md section 2, NFR-08).

Responses contain a status only: never versions, hostnames or configuration.
"""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.access import AccessLevel, access
from app.core.config import Settings
from app.core.migrations import current_revisions, head_revisions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok", "unavailable"]


@router.get(
    "/live",
    summary="Process is running; no dependencies checked",
    response_model=HealthStatus,
    openapi_extra=access(AccessLevel.PUBLIC),
)
async def live() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get(
    "/ready",
    summary="Database reachable and migrations at head",
    response_model=HealthStatus,
    responses={503: {"model": HealthStatus, "description": "A dependency is not ready"}},
    openapi_extra=access(AccessLevel.PUBLIC),
)
async def ready(request: Request, response: Response) -> HealthStatus:
    settings: Settings = request.app.state.settings
    engine: AsyncEngine = request.app.state.engine
    try:
        async with asyncio.timeout(settings.health_check_timeout_seconds):
            is_ready = await _database_ready(engine)
    except Exception:
        logger.warning("readiness_check_failed", exc_info=True)
        is_ready = False
    if not is_ready:
        response.status_code = 503
        return HealthStatus(status="unavailable")
    return HealthStatus(status="ok")


async def _database_ready(engine: AsyncEngine) -> bool:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        current = await current_revisions(connection)
    at_head = current == head_revisions()
    if not at_head:
        logger.warning("migrations_not_at_head", extra={"current": sorted(current)})
    return at_head
