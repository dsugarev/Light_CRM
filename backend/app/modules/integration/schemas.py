"""Pydantic request and response schemas."""

import ipaddress
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.modules.sales.schemas import UserSummary

# Scopes of API spec 19.3.
Scope = Literal[
    "organizations:read",
    "organizations:write",
    "contacts:read",
    "contacts:write",
    "leads:read",
    "leads:write",
    "opportunities:read",
    "opportunities:write",
    "activities:read",
    "activities:write",
    "reference:read",
    "reports:read",
    "external-references:write",
]
Resource = Literal["organizations", "contacts", "leads", "opportunities"]
EntityType = Literal["organization", "contact", "lead", "opportunity"]


def _cidr(value: str) -> str:
    return str(ipaddress.ip_network(value.strip(), strict=False))


def _https(value: str) -> str:
    if not value.startswith("https://") or len(value) <= len("https://"):
        raise ValueError("https only")
    return value


Cidr = Annotated[str, Field(max_length=50), AfterValidator(_cidr)]
HttpsUrl = Annotated[str, Field(max_length=500), AfterValidator(_https)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SystemSummary(BaseModel):
    id: UUID
    code: str
    name_en: str
    name_bg: str


class UsageFigures(BaseModel):
    requests_24h: int
    errors_24h: int


class IntegrationClientOut(BaseModel):
    id: UUID
    name: str
    system: SystemSummary
    scopes: list[Scope]
    default_owner: UserSummary | None
    ip_allowlist: list[str]
    technical_contact: str | None
    rate_limit_per_minute: int
    is_active: bool
    last_used_at: datetime | None
    usage: UsageFigures
    active_keys: int
    created_at: datetime
    updated_at: datetime


class IntegrationClientCreate(_Request):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    system: Annotated[str, Field(min_length=1, max_length=50)]
    scopes: list[Scope] = []
    default_owner_id: UUID | None = None
    ip_allowlist: Annotated[list[Cidr], Field(max_length=50)] = []
    technical_contact: Annotated[str, Field(max_length=300)] | None = None
    rate_limit_per_minute: Annotated[int, Field(ge=1, le=100_000)] = 300
    is_active: bool = True


class IntegrationClientUpdate(_Request):
    name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    scopes: list[Scope] | None = None
    default_owner_id: UUID | None = None
    ip_allowlist: Annotated[list[Cidr], Field(max_length=50)] | None = None
    technical_contact: Annotated[str, Field(max_length=300)] | None = None
    rate_limit_per_minute: Annotated[int, Field(ge=1, le=100_000)] | None = None


class ApiKeyOut(BaseModel):
    id: UUID
    prefix: str = Field(description="crm_<env>_<key_id>; the secret is never shown again")
    label: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None
    last_used_ip: str | None
    created_by: UserSummary | None


class ApiKeyCreate(_Request):
    label: Annotated[str, Field(min_length=1, max_length=100)]
    expires_at: datetime | None = Field(
        default=None, description="Default 12 months from now, at most 24"
    )


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="The full key, shown only in this response (FR-INT-02 AC1)")


class ExternalReferenceOut(BaseModel):
    entity_type: EntityType
    entity_id: UUID
    system: SystemSummary
    external_id: str
    url: str | None
    updated_at: datetime
    updated_by: UserSummary | None


class ExternalReferencePut(_Request):
    external_id: Annotated[str, Field(min_length=1, max_length=200)]
    url: HttpsUrl | None = None
