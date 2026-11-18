"""Pydantic request and response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.dataimport.fields import EntityType
from app.modules.sales.schemas import LinkSummary, UserSummary

BatchStatus = Literal["uploaded", "mapped", "validated", "committed", "rolled_back"]
RowOutcome = Literal["valid", "invalid", "duplicate"]
DuplicateMode = Literal["skip", "update"]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldInfo(BaseModel):
    key: str
    name_en: str
    name_bg: str
    required: bool


class BatchCounts(BaseModel):
    rows: int
    valid: int
    invalid: int
    duplicate: int
    created: int
    updated: int
    skipped: int


class ImportBatchOut(BaseModel):
    id: UUID
    entity_type: EntityType
    file_name: str
    status: BatchStatus
    columns: list[str]
    mapping: dict[str, str | None] = Field(
        description="Column → field; on upload, the suggested mapping"
    )
    duplicate_mode: DuplicateMode | None
    fields: list[FieldInfo]
    counts: BatchCounts
    created_by: UserSummary | None
    created_at: datetime
    committed_at: datetime | None
    rolled_back_at: datetime | None
    expires_at: datetime


class MappingRequest(_Request):
    mapping: dict[str, str | None] = Field(description="Column → field key, or null to ignore")
    duplicates: DuplicateMode = "skip"


class CommitRequest(_Request):
    mode: Literal["strict", "skip_invalid"] = "strict"


class RowError(BaseModel):
    field: str
    code: str


class ImportRowOut(BaseModel):
    row_number: int
    outcome: RowOutcome | None
    values: dict[str, str | None]
    errors: list[RowError]
    match: LinkSummary | None
    action: Literal["created", "updated", "skipped"] | None
    record_id: UUID | None
    rollback_result: str | None


class RollbackReport(BaseModel):
    batch: ImportBatchOut
    archived: int
    reverted: int
    kept: list[ImportRowOut] = Field(
        description="Rows whose record was not rolled back, with the reason in rollback_result"
    )
