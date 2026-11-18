"""Pydantic request and response schemas."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer, model_validator

from app.modules.party.schemas import (
    ContactCreate,
    ContactOut,
    Match,
    OrganizationCreate,
    OrganizationOut,
)

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


# --- Pipelines and stages (API spec section 6.3) -----------------------------------------

StageType = Literal["open", "won", "lost"]
Probability = Annotated[int, Field(ge=0, le=100)]


class StageOut(BaseModel):
    id: UUID
    name_en: str
    name_bg: str
    position: int
    default_probability: int
    stage_type: StageType
    is_active: bool


class PipelineOut(BaseModel):
    id: UUID
    name: str
    is_default: bool
    stages: list[StageOut]


class StageCreate(_Request):
    name_en: Annotated[str, Field(min_length=1, max_length=100)]
    name_bg: Annotated[str, Field(min_length=1, max_length=100)]
    default_probability: Probability
    stage_type: StageType


class StageUpdate(_Request):
    name_en: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    name_bg: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    default_probability: Probability | None = None
    is_active: bool | None = None


# --- Opportunities (API spec section 10) --------------------------------------------------


class StageSummary(BaseModel):
    id: UUID
    name_en: str
    name_bg: str
    stage_type: StageType
    position: int
    default_probability: int


class OpportunityFields(_Request):
    primary_contact_id: UUID | None = None
    amount: Money | None = None
    expected_close_date: date | None = None
    next_step: Annotated[str, Field(max_length=2000)] | None = None
    description: Annotated[str, Field(max_length=5000)] | None = None
    competitor: Annotated[str, Field(max_length=200)] | None = None
    probability: Probability | None = None


class OpportunityCreate(OpportunityFields):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    organization_id: UUID
    stage_id: UUID | None = None
    owner_id: UUID | None = None


class OpportunityUpdate(OpportunityFields):
    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    version: int = Field(ge=1, description="The version you loaded; a stale one returns 409")
    # Present only to answer with validation.use_action_endpoint (API spec 1.4).
    stage_id: Any = Field(default=None, description="Not changeable here; use /move or /close")
    owner_id: Any = Field(default=None, description="Not changeable here; use POST /assign")
    organization_id: Any = Field(
        default=None, description="An opportunity stays with its organization"
    )


class OpportunityOut(BaseModel):
    id: UUID
    name: str
    organization: LinkSummary
    primary_contact: LinkSummary | None
    owner: UserSummary
    pipeline_id: UUID
    stage: StageSummary
    amount: Money | None
    currency: str
    probability: int
    probability_overridden: bool
    weighted_amount: Money | None
    expected_close_date: date | None
    actual_close_date: date | None
    next_step: str | None
    description: str | None
    source_lead: LinkSummary | None
    loss_reason: ReferenceSummary | None
    competitor: str | None
    is_stale: bool
    last_activity_at: datetime | None
    created_at: datetime
    updated_at: datetime
    created_by: UserSummary | None
    archived_at: datetime | None
    version: int


class MoveRequest(_Request):
    stage_id: UUID
    version: int = Field(ge=1)


class CloseRequest(_Request):
    outcome: Literal["won", "lost"]
    loss_reason_id: UUID | None = None
    competitor: Annotated[str, Field(max_length=200)] | None = None
    actual_close_date: date | None = None
    version: int = Field(ge=1)


class ReopenRequest(_Request):
    stage_id: UUID
    version: int = Field(ge=1)


class StageChange(BaseModel):
    id: UUID
    from_stage: StageSummary | None
    to_stage: StageSummary
    changed_by: UserSummary | None
    changed_at: datetime


class BoardCard(BaseModel):
    id: UUID
    name: str
    organization: LinkSummary
    amount: Money | None
    expected_close_date: date | None
    owner: UserSummary
    is_stale: bool
    can_edit: bool
    version: int


class BoardColumn(BaseModel):
    stage: StageSummary
    count: int
    total_amount: Money
    weighted_amount: Money
    cards: list[BoardCard]


class Board(BaseModel):
    pipeline_id: UUID
    currency: Literal["EUR"] = "EUR"
    columns: list[BoardColumn]
    truncated: bool


# --- Lead conversion (FR-LEAD-04, API spec section 9) ---------------------------------------


class _ExistingOrNew[T: BaseModel](_Request):
    existing_id: UUID | None = None
    new: T | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> _ExistingOrNew[T]:
        if (self.existing_id is None) == (self.new is None):
            raise ValueError("exactly one of existing_id and new")
        return self


class ConversionOrganization(_ExistingOrNew[OrganizationCreate]):
    pass


class ConversionContact(_ExistingOrNew[ContactCreate]):
    """A new contact always belongs to the conversion's organization."""


class ConversionOpportunity(_Request):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    amount: Money | None = None
    expected_close_date: date | None = None
    stage_id: UUID | None = None
    owner_id: UUID | None = None


class ConvertRequest(_Request):
    version: int = Field(ge=1)
    organization: ConversionOrganization
    contact: ConversionContact | None = None
    opportunity: ConversionOpportunity


class ConversionResult(BaseModel):
    lead: LeadOut
    organization: OrganizationOut
    contact: ContactOut | None
    opportunity: OpportunityOut


class SuggestedOrganization(BaseModel):
    name: str


class SuggestedContact(BaseModel):
    first_name: str
    last_name: str
    email: str | None
    phone: str | None


class OrganizationChoice(BaseModel):
    linked: LinkSummary | None
    matches: list[Match]
    suggested: SuggestedOrganization


class ContactChoice(BaseModel):
    linked: LinkSummary | None
    matches: list[Match]
    suggested: SuggestedContact | None


class SuggestedOpportunity(BaseModel):
    name: str
    amount: Money | None
    stage: StageSummary


class ConversionPreview(BaseModel):
    """What the conversion screen offers before the user decides (FR-LEAD-04)."""

    organization: OrganizationChoice
    contact: ContactChoice
    opportunity: SuggestedOpportunity


# --- Reports (FR-REP-01, FR-REP-03; API spec section 13) -------------------------------------

Rate = Annotated[float, Field(ge=0, le=1, description="Share between 0 and 1")]


class StageFigures(BaseModel):
    stage: StageSummary
    count: int
    total_amount: Money
    weighted_amount: Money


class PipelineReport(BaseModel):
    currency: Literal["EUR"] = "EUR"
    stages: list[StageFigures]
    count: int
    total_amount: Money
    weighted_amount: Money


class ForecastMonth(BaseModel):
    month: str = Field(description="YYYY-MM")
    count: int
    total_amount: Money
    weighted_amount: Money


class ForecastReport(BaseModel):
    currency: Literal["EUR"] = "EUR"
    months: list[ForecastMonth]
    weighted_amount: Money


class GroupKey(BaseModel):
    """What a report row is grouped by: a source, owner, loss reason or month."""

    key: str = Field(description="ID, YYYY-MM, or `none`")
    name_en: str | None
    name_bg: str | None


class ConversionFigures(BaseModel):
    created: int
    qualified: int = Field(description="Leads that reached qualified (including converted)")
    converted: int
    disqualified: int
    conversion_rate: Rate | None = Field(description="converted / created; null without leads")


class ConversionGroup(ConversionFigures):
    group: GroupKey


class LeadConversionReport(BaseModel):
    from_date: date
    to_date: date
    group_by: Literal["source", "owner"] | None
    totals: ConversionFigures
    groups: list[ConversionGroup]


class WinLossFigures(BaseModel):
    won_count: int
    won_amount: Money
    lost_count: int
    lost_amount: Money
    win_rate: Rate | None = Field(description="won / (won + lost); null without closed deals")


class WinLossGroup(WinLossFigures):
    group: GroupKey


class WinLossReport(BaseModel):
    currency: Literal["EUR"] = "EUR"
    from_date: date
    to_date: date
    group_by: Literal["loss_reason", "owner", "month"] | None
    totals: WinLossFigures
    groups: list[WinLossGroup]
