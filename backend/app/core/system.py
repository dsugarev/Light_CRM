"""System information for the frontend (API spec section 2)."""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.access import AccessLevel
from app.core.auth import endpoint
from app.core.config import Settings

router = APIRouter(prefix="/system", tags=["system"])


class FeatureFlags(BaseModel):
    ai_enabled: bool
    mfa_available: bool


class SystemInfo(BaseModel):
    version: str
    build: str
    supported_locales: list[str]
    features: FeatureFlags


@router.get(
    "/info",
    summary="App version, build, supported locales and feature flags",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def system_info(request: Request) -> SystemInfo:
    settings: Settings = request.app.state.settings
    return SystemInfo(
        version=settings.app_version,
        build=settings.app_build,
        supported_locales=["en", "bg"],
        # The assistant shows only while AI_ENABLED is on (FR-AI-07); MFA (FR-AUTH-07)
        # arrives in Phase 8.
        features=FeatureFlags(
            ai_enabled=settings.ai_enabled and request.app.state.llm is not None,
            mfa_available=False,
        ),
    )
