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

# Webhook event types of API spec 19.6 (`ping` is the test event, sent on request only).
EVENT_TYPES = (
    "organization.created", "organization.updated", "organization.archived",
    "contact.created", "contact.updated", "contact.archived", "contact.anonymized",
    "lead.created", "lead.updated", "lead.status_changed", "lead.converted",
    "opportunity.created", "opportunity.updated", "opportunity.stage_changed",
    "opportunity.closed_won", "opportunity.closed_lost", "opportunity.reopened",
    "external_reference.updated",
)  # fmt: skip
_EVENT_PATTERNS = frozenset({"*", *EVENT_TYPES, *(f"{t.split('.')[0]}.*" for t in EVENT_TYPES)})
DeliveryStatus = Literal["pending", "retrying", "succeeded", "failed"]


def _cidr(value: str) -> str:
    return str(ipaddress.ip_network(value.strip(), strict=False))


def _https(value: str) -> str:
    if not value.startswith("https://") or len(value) <= len("https://"):
        raise ValueError("https only")
    return value


def _event_pattern(value: str) -> str:
    if value not in _EVENT_PATTERNS:
        raise ValueError("unknown event type")
    return value


Cidr = Annotated[str, Field(max_length=50), AfterValidator(_cidr)]
EventPattern = Annotated[
    str,
    Field(max_length=60, description="An event type, `<record>.*` or `*`"),
    AfterValidator(_event_pattern),
]
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


class WebhookFigures(BaseModel):
    subscriptions: int
    failing_deliveries: int = Field(
        description="Deliveries now retrying, or failed in the last 24 hours (FR-INT-08)"
    )
    suspended_subscriptions: int


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
    webhooks: WebhookFigures
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
    is_active: bool = Field(
        default=False, description="Clients start inactive until the data flow is confirmed"
    )


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


class WebhookSubscriptionCreate(_Request):
    url: Annotated[str, Field(min_length=1, max_length=500)]
    event_types: Annotated[list[EventPattern], Field(min_length=1, max_length=40)]
    is_active: bool = True


class WebhookSubscriptionUpdate(_Request):
    url: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    event_types: Annotated[list[EventPattern], Field(min_length=1, max_length=40)] | None = None
    is_active: bool | None = Field(
        default=None, description="true also lifts an automatic suspension"
    )


class DeliveryCounts(BaseModel):
    succeeded: int
    pending: int
    retrying: int
    failed: int


class WebhookSubscriptionOut(BaseModel):
    id: UUID
    client_id: UUID
    url: str
    event_types: list[str]
    is_active: bool
    suspended_at: datetime | None
    failing_since: datetime | None
    previous_secret_valid_until: datetime | None
    deliveries_24h: DeliveryCounts
    created_at: datetime
    updated_at: datetime


class WebhookSubscriptionCreated(WebhookSubscriptionOut):
    secret: str = Field(description="The signing secret, shown only in this response")


class WebhookSecret(BaseModel):
    secret: str = Field(description="The new signing secret, shown only in this response")
    previous_secret_valid_until: datetime


class WebhookAttemptOut(BaseModel):
    number: int
    attempted_at: datetime
    duration_ms: int
    status_code: int | None
    error: str | None
    response_excerpt: str | None


class WebhookDeliveryOut(BaseModel):
    id: UUID
    subscription_id: UUID
    client_id: UUID
    event_id: str = Field(description="evt_<hex>, as sent in X-CRM-Event-Id")
    event_type: str
    entity_type: str | None
    entity_id: UUID | None
    occurred_at: datetime
    status: DeliveryStatus
    attempt_count: int
    next_attempt_at: datetime | None
    last_status_code: int | None
    last_error: str | None
    delivered_at: datetime | None
    created_at: datetime


class WebhookDeliveryDetail(WebhookDeliveryOut):
    url: str
    attempts: list[WebhookAttemptOut]


class WebhookDeliveryPage(BaseModel):
    items: list[WebhookDeliveryOut]
    total: int
    page: int
    page_size: int
