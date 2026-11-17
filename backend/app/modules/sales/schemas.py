"""Pydantic request and response schemas."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer

LeadStatus = Literal["new", "contacted", "qualified", "converted", "disqualified"]
BantStatus = Literal["unknown", "no", "partial", "yes"]

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email(value: str) -> str:
    if not _EMAIL.fullmatch(value):
        raise ValueError("invalid email")
    return value.lower()


EmailAddress = Annotated[str, Field(max_length=320), AfterValidator(_email)]
# Money travels as a decimal string (API spec 1.1) so no precision is lost.
Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=14, decimal_places=2),
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json"),
]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class UserSummary(BaseModel):
    id: UUID
    full_name: str


class ReferenceSummary(BaseModel):
    id: UUID
    code: str
    name_en: str
    name_bg: str


class LinkSummary(BaseModel):
    id: UUID
    name: str


# --- Qualification (BANT) ----------------------------------------------------------------


class BantItem(BaseModel):
    status: BantStatus
    note: str


class Qualification(BaseModel):
    budget: BantItem
    authority: BantItem
    need: BantItem
    timeline: BantItem
    fits_target_profile: bool
    score: int


class BantItemUpdate(_Request):
    status: BantStatus | None = None
    note: Annotated[str, Field(max_length=2000)] | None = None


class QualificationUpdate(_Request):
    budget: BantItemUpdate | None = None
    authority: BantItemUpdate | None = None
    need: BantItemUpdate | None = None
    timeline: BantItemUpdate | None = None
    fits_target_profile: bool | None = None


# --- Lead -------------------------------------------------------------------------------


class LeadFields(_Request):
    contact_name: Annotated[str, Field(max_length=200)] | None = None
    email: EmailAddress | None = None
    phone: Annotated[str, Field(max_length=50)] | None = None
    source_id: UUID | None = None
    description: Annotated[str, Field(max_length=5000)] | None = None
    estimated_value: Money | None = None
    organization_id: UUID | None = None
    contact_id: UUID | None = None
    qualification: QualificationUpdate | None = None


class LeadCreate(LeadFields):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    company_name: Annotated[str, Field(min_length=1, max_length=200)]
    owner_id: UUID | None = None


class LeadUpdate(LeadFields):
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    company_name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    version: int = Field(ge=1, description="The version you loaded; a stale one returns 409")
    # Present only to answer with validation.use_action_endpoint (API spec 1.4).
    status: Any = Field(default=None, description="Not changeable here; use the action endpoints")
    owner_id: Any = Field(default=None, description="Not changeable here; use POST /assign")


class Disqualification(BaseModel):
    reason: ReferenceSummary | None
    note: str | None
    disqualified_at: datetime | None


class LeadOut(BaseModel):
    id: UUID
    title: str
    company_name: str
    contact_name: str | None
    email: str | None
    phone: str | None
    source: ReferenceSummary | None
    status: LeadStatus
    description: str | None
    estimated_value: Money | None
    currency: str
    owner: UserSummary
    qualification: Qualification
    organization: LinkSummary | None
    contact: LinkSummary | None
    converted_opportunity: LinkSummary | None
    converted_at: datetime | None
    disqualification: Disqualification | None
    created_at: datetime
    updated_at: datetime
    created_by: UserSummary | None
    archived_at: datetime | None
    version: int


# --- Actions ----------------------------------------------------------------------------


class VersionOnly(_Request):
    version: int = Field(ge=1)


class DisqualifyRequest(_Request):
    reason_id: UUID
    note: Annotated[str, Field(max_length=2000)] | None = None
    version: int = Field(ge=1)


class AssignRequest(_Request):
    owner_id: UUID
    version: int = Field(ge=1)
