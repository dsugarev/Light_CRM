"""Pydantic request and response schemas."""

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.errors import FieldError

SizeBand = Literal["1-9", "10-49", "50-249", "250+"]
Locale = Literal["en", "bg"]

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)


def _email(value: str) -> str:
    if not _EMAIL.fullmatch(value):
        raise ValueError("invalid email")
    return value.lower()


def _registration(value: str) -> str:
    digits = re.sub(r"\s+", "", value)
    if not re.fullmatch(r"\d{9}|\d{13}", digits):
        raise ValueError("EIK/UIC has 9 or 13 digits")
    return digits


def _vat(value: str) -> str:
    compact = re.sub(r"\s+", "", value).upper()
    if not re.fullmatch(r"BG\d{9,10}", compact):
        raise ValueError("VAT number is BG followed by 9 or 10 digits")
    return compact


def _url(value: str) -> str:
    if not _URL.fullmatch(value):
        raise ValueError("website must start with http:// or https://")
    return value


def _country(value: str) -> str:
    upper = value.upper()
    if not re.fullmatch(r"[A-Z]{2}", upper):
        raise ValueError("ISO 3166-1 alpha-2 country code")
    return upper


EmailAddress = Annotated[str, Field(max_length=320), AfterValidator(_email)]
RegistrationNumber = Annotated[str, Field(max_length=20), AfterValidator(_registration)]
VatNumber = Annotated[str, Field(max_length=20), AfterValidator(_vat)]
Website = Annotated[str, Field(max_length=300), AfterValidator(_url)]
Country = Annotated[str, Field(min_length=2, max_length=2), AfterValidator(_country)]
Text200 = Annotated[str, Field(min_length=1, max_length=200)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- Embedded summaries (API spec 1.5) -------------------------------------------------


class UserSummary(BaseModel):
    id: UUID
    full_name: str


class ReferenceSummary(BaseModel):
    """Reference value with both names; the UI picks the user's language."""

    id: UUID
    code: str
    name_en: str
    name_bg: str


class OrganizationSummary(BaseModel):
    id: UUID
    name: str


class Match(BaseModel):
    """A possible duplicate (FR-PARTY-01 AC1)."""

    id: UUID
    name: str
    registration_number: str | None = None
    email: str | None = None
    city: str | None = None
    archived: bool
    reason: Literal["registration_number", "name", "similar_name", "email"]


# --- Organizations ----------------------------------------------------------------------


class OrganizationFields(_Request):
    registration_number: RegistrationNumber | None = None
    vat_number: VatNumber | None = None
    industry_id: UUID | None = None
    size_band: SizeBand | None = None
    website: Website | None = None
    address_line: Annotated[str, Field(max_length=200)] | None = None
    postal_code: Annotated[str, Field(max_length=20)] | None = None
    city: Annotated[str, Field(max_length=100)] | None = None
    notes: Annotated[str, Field(max_length=5000)] | None = None


class OrganizationCreate(OrganizationFields):
    name: Text200
    country: Country = "BG"
    owner_id: UUID | None = None
    confirm_duplicate: bool = False


class OrganizationUpdate(OrganizationFields):
    name: Text200 | None = None
    country: Country | None = None
    owner_id: UUID | None = None
    confirm_duplicate: bool = False


class OrganizationOut(BaseModel):
    id: UUID
    name: str
    registration_number: str | None
    vat_number: str | None
    industry: ReferenceSummary | None
    size_band: SizeBand | None
    website: str | None
    address_line: str | None
    postal_code: str | None
    city: str | None
    country: str
    owner: UserSummary
    notes: str | None
    created_at: datetime
    updated_at: datetime
    created_by: UserSummary | None
    archived_at: datetime | None
    # Non-blocking findings, e.g. a registration number with a wrong checksum.
    warnings: list[FieldError] = []


class OrganizationCounts(BaseModel):
    contacts: int
    open_leads: int
    open_opportunities: int
    open_pipeline_value: str
    currency: Literal["EUR"] = "EUR"


class OrganizationDetail(OrganizationOut):
    counts: OrganizationCounts


class DuplicateCheck(BaseModel):
    matches: list[Match]


# --- Contacts ---------------------------------------------------------------------------


class ContactFields(_Request):
    job_title: Annotated[str, Field(max_length=150)] | None = None
    email: EmailAddress | None = None
    phone: Annotated[str, Field(max_length=50)] | None = None
    preferred_locale: Locale | None = None
    organization_id: UUID | None = None
    notes: Annotated[str, Field(max_length=5000)] | None = None


class ContactCreate(ContactFields):
    first_name: Annotated[str, Field(min_length=1, max_length=100)]
    last_name: Annotated[str, Field(min_length=1, max_length=100)]
    confirm_duplicate: bool = False


class ContactUpdate(ContactFields):
    first_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    last_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    confirm_duplicate: bool = False


class ContactOut(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    full_name: str
    job_title: str | None
    email: str | None
    phone: str | None
    preferred_locale: Locale | None
    organization: OrganizationSummary | None
    owner: UserSummary
    notes: str | None
    created_at: datetime
    updated_at: datetime
    created_by: UserSummary | None
    archived_at: datetime | None
    anonymized_at: datetime | None


# --- Search -----------------------------------------------------------------------------


class SearchHit(BaseModel):
    type: Literal["organization", "contact"]
    id: UUID
    label: str
    detail: str | None


class SearchResults(BaseModel):
    items: list[SearchHit]
