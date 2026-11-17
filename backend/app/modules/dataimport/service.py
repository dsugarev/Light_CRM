"""Import from XLSX or CSV (FR-IMP-01; API spec section 15). Public API of the module.

A batch goes uploaded → mapped → validated → committed (→ rolled_back). Rows are
validated with the owning modules' own create schemas and lookups, duplicates
follow the FR-PARTY-01 rules, the commit is one transaction (AC2), every created
record carries the batch ID and an Admin can roll the batch back (AC4).
"""

from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ErrorCode, FieldError
from app.core.events import DomainEvent
from app.core.listing import ListQuery, Page, fetch_page
from app.core.principal import Principal
from app.modules.dataimport import repository
from app.modules.dataimport.adapters import ADAPTERS, ImportContext, Lookups
from app.modules.dataimport.fields import (
    FIELDS,
    EntityType,
    field_keys,
    required_keys,
    suggest_mapping,
)
from app.modules.dataimport.models import ImportBatch, ImportRow
from app.modules.dataimport.parsing import parse
from app.modules.dataimport.schemas import (
    BatchCounts,
    CommitRequest,
    FieldInfo,
    ImportBatchOut,
    ImportRowOut,
    MappingRequest,
    RollbackReport,
    RowError,
)
from app.modules.dataimport.templates import template
from app.modules.identity import service as identity
from app.modules.sales.schemas import LinkSummary, UserSummary

Context = ImportContext
RETENTION = timedelta(days=7)
BATCH_SORT = {"created_at": ImportBatch.created_at}
_EDITABLE = ("uploaded", "mapped", "validated")


def _state_error(batch: ImportBatch) -> AppError:
    return AppError(
        ErrorCode.IMPORT_INVALID_STATE, HTTPStatus.CONFLICT, extra={"status": batch.status}
    )


def _invalid(field: str, code: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_FAILED,
        HTTPStatus.UNPROCESSABLE_CONTENT,
        errors=[FieldError(field, code)],
    )


async def _publish(
    ctx: Context, action: str, batch: ImportBatch, principal: Principal, **details: Any
) -> None:
    await ctx.events.publish(
        ctx.session,
        DomainEvent(
            action=f"import.{action}",
            entity_type="import_batch",
            entity_id=batch.id,
            actor=principal,
            occurred_at=ctx.now,
            details={"entity_type": batch.entity_type, "file_name": batch.file_name, **details},
        ),
    )


def _fields(entity: str) -> list[FieldInfo]:
    return [
        FieldInfo(key=f.key, name_en=f.en, name_bg=f.bg, required=f.required)
        for f in FIELDS[entity]  # type: ignore[index]
    ]


async def _out(ctx: Context, batch: ImportBatch) -> ImportBatchOut:
    names = await identity.user_names(
        ctx.session, {batch.created_by} if batch.created_by else set()
    )
    return ImportBatchOut(
        id=batch.id,
        entity_type=batch.entity_type,  # type: ignore[arg-type]
        file_name=batch.file_name,
        status=batch.status,  # type: ignore[arg-type]
        columns=batch.columns,
        mapping=batch.mapping or {},
        duplicate_mode=batch.duplicate_mode,  # type: ignore[arg-type]
        fields=_fields(batch.entity_type),
        counts=BatchCounts(
            rows=batch.row_count,
            valid=batch.valid_count,
            invalid=batch.invalid_count,
            duplicate=batch.duplicate_count,
            created=batch.created_count,
            updated=batch.updated_count,
            skipped=batch.skipped_count,
        ),
        created_by=UserSummary(id=batch.created_by, full_name=names.get(batch.created_by, ""))
        if batch.created_by
        else None,
        created_at=batch.created_at,
        committed_at=batch.committed_at,
        rolled_back_at=batch.rolled_back_at,
        expires_at=batch.expires_at,
    )


async def _fresh(ctx: Context, batch_id: UUID) -> ImportBatchOut:
    ctx.session.expire_all()
    batch = await repository.get_batch(ctx.session, batch_id)
    assert batch is not None  # noqa: S101 - exists
    return await _out(ctx, batch)


async def _load(ctx: Context, batch_id: UUID) -> ImportBatch:
    batch = await repository.get_batch(ctx.session, batch_id, for_update=True)
    if batch is None:
        raise AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)
    return batch


def _values(batch: ImportBatch, row: ImportRow) -> dict[str, str | None]:
    """The row's values by field key, through the batch's mapping."""
    values: dict[str, str | None] = {}
    for column, key in (batch.mapping or {}).items():
        if key and row.raw is not None:
            values[key] = (row.raw.get(column) or "").strip() or None
    return values


def _row_out(batch: ImportBatch, row: ImportRow) -> ImportRowOut:
    return ImportRowOut(
        row_number=row.row_number,
        outcome=row.outcome,  # type: ignore[arg-type]
        values=_values(batch, row),
        errors=[RowError(**e) for e in row.errors],
        match=LinkSummary(id=row.match_id, name=row.match_name or "") if row.match_id else None,
        action=row.action,  # type: ignore[arg-type]
        record_id=row.record_id,
        rollback_result=row.rollback_result,
    )


# --- Templates and upload -------------------------------------------------------------------


def download_template(entity: EntityType, locale: Literal["en", "bg"]) -> bytes:
    return template(entity, locale)


async def upload(
    ctx: Context, principal: Principal, entity: EntityType, file_name: str, content: bytes
) -> ImportBatchOut:
    """FR-IMP-01 AC1 step 1: read the file, keep its rows, suggest a mapping."""
    columns, rows = parse(file_name, content)
    batch = ImportBatch(
        entity_type=entity,
        file_name=file_name[:255],
        status="uploaded",
        columns=columns,
        mapping=suggest_mapping(entity, columns),
        row_count=len(rows),
        expires_at=ctx.now + RETENTION,
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    ctx.session.add(batch)
    await ctx.session.flush()
    ctx.session.add_all(
        ImportRow(batch_id=batch.id, row_number=index, raw=raw)
        for index, raw in enumerate(rows, start=2)  # row 1 holds the headers
    )
    await _publish(ctx, "uploaded", batch, principal, rows=len(rows))
    await ctx.session.commit()
    return await _fresh(ctx, batch.id)


async def get_batch(ctx: Context, batch_id: UUID) -> ImportBatchOut:
    batch = await repository.get_batch(ctx.session, batch_id)
    if batch is None:
        raise AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)
    return await _out(ctx, batch)


async def list_batches(ctx: Context, query: ListQuery) -> Page[ImportBatchOut]:
    batches, total = await fetch_page(
        ctx.session, repository.batches_statement(), query, BATCH_SORT, ImportBatch.id
    )
    return Page[ImportBatchOut](
        items=[await _out(ctx, b) for b in batches],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


# --- Mapping and validation -----------------------------------------------------------------


async def set_mapping(
    ctx: Context, principal: Principal, batch_id: UUID, data: MappingRequest
) -> ImportBatchOut:
    """FR-IMP-01 AC1 step 2 and AC3: columns to fields, and what to do with duplicates."""
    batch = await _load(ctx, batch_id)
    if batch.status not in _EDITABLE:
        raise _state_error(batch)
    entity: EntityType = batch.entity_type  # type: ignore[assignment]
    known = field_keys(entity)
    used: set[str] = set()
    errors: list[FieldError] = []
    for column, key in data.mapping.items():
        if column not in batch.columns:
            errors.append(FieldError(f"mapping.{column}", "import.unknown_column"))
        elif key is not None and key not in known:
            errors.append(FieldError(f"mapping.{column}", "import.unknown_field"))
        elif key is not None and key in used:
            errors.append(FieldError(f"mapping.{column}", "import.field_mapped_twice"))
        elif key is not None:
            used.add(key)
    errors.extend(
        FieldError(f"field.{key}", "import.required_field") for key in required_keys(entity)
        if key not in used
    )  # fmt: skip
    if errors:
        raise AppError(ErrorCode.VALIDATION_FAILED, HTTPStatus.UNPROCESSABLE_CONTENT, errors=errors)
    batch.mapping = {column: data.mapping.get(column) for column in batch.columns}
    batch.duplicate_mode = data.duplicates
    batch.status = "mapped"
    batch.valid_count = batch.invalid_count = batch.duplicate_count = 0
    batch.updated_by = principal.user_id
    for row in await repository.rows(ctx.session, batch.id):
        row.outcome, row.errors, row.match_id, row.match_name = None, [], None, None
    await _publish(
        ctx, "mapped", batch, principal, mapping=batch.mapping, duplicates=data.duplicates
    )
    await ctx.session.commit()
    return await _fresh(ctx, batch.id)


async def validate(ctx: Context, principal: Principal, batch_id: UUID) -> ImportBatchOut:
    """FR-IMP-01 AC1 step 3 and AC3: check every row; nothing is written to the records."""
    batch = await _load(ctx, batch_id)
    if batch.status not in ("mapped", "validated"):
        raise _state_error(batch)
    adapter = ADAPTERS[batch.entity_type]  # type: ignore[index]
    lookups = Lookups()
    seen: dict[str, int] = {}
    counts = {"valid": 0, "invalid": 0, "duplicate": 0}
    for row in await repository.rows(ctx.session, batch.id):
        prepared = await adapter.prepare(ctx, lookups, _values(batch, row))
        row.match_id, row.match_name = None, None
        errors = list(prepared.errors)
        if prepared.file_key and not errors:
            first = seen.setdefault(prepared.file_key, row.row_number)
            if first != row.row_number:
                errors.append({"field": "row", "code": "import.duplicate_in_file"})
        if errors:
            row.outcome, row.errors = "invalid", errors
        else:
            row.errors = []
            assert prepared.payload is not None  # noqa: S101 - no errors
            match = await adapter.duplicate(ctx, prepared.payload)
            if match:
                row.outcome, (row.match_id, row.match_name) = "duplicate", match
            else:
                row.outcome = "valid"
        counts[row.outcome] += 1
    batch.valid_count = counts["valid"]
    batch.invalid_count = counts["invalid"]
    batch.duplicate_count = counts["duplicate"]
    batch.status = "validated"
    batch.updated_by = principal.user_id
    await _publish(ctx, "validated", batch, principal, **counts)
    await ctx.session.commit()
    return await _fresh(ctx, batch.id)


async def list_rows(
    ctx: Context, batch_id: UUID, outcomes: tuple[str, ...], page: int, page_size: int
) -> Page[ImportRowOut]:
    """FR-IMP-01 AC1: the validation preview, each invalid row with its reasons."""
    batch = await repository.get_batch(ctx.session, batch_id)
    if batch is None:
        raise AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)
    statement = repository.rows_statement(batch.id, outcomes)
    total = await repository.count(ctx.session, statement)
    items = await repository.page(ctx.session, statement, (page - 1) * page_size, page_size)
    return Page[ImportRowOut](
        items=[_row_out(batch, r) for r in items], total=total, page=page, page_size=page_size
    )


# --- Commit, rollback, discard ----------------------------------------------------------------


async def commit(
    ctx: Context, principal: Principal, batch_id: UUID, data: CommitRequest
) -> ImportBatchOut:
    """FR-IMP-01 AC2: all or nothing, unless the user chose to skip invalid rows."""
    batch = await _load(ctx, batch_id)
    if batch.status != "validated":
        raise _state_error(batch)
    if data.mode == "strict" and batch.invalid_count:
        raise AppError(
            ErrorCode.IMPORT_HAS_ERRORS,
            HTTPStatus.CONFLICT,
            extra={"invalid": batch.invalid_count},
        )
    adapter = ADAPTERS[batch.entity_type]  # type: ignore[index]
    lookups = Lookups()
    created = updated = skipped = 0
    rows = await repository.rows(ctx.session, batch.id)
    for row in rows:
        if row.outcome == "invalid" or (
            row.outcome == "duplicate" and batch.duplicate_mode != "update"
        ):
            row.action = "skipped"
            skipped += 1
            continue
        prepared = await adapter.prepare(ctx, lookups, _values(batch, row))
        if prepared.payload is None:  # changed since validation (e.g. a list value retired)
            raise AppError(
                ErrorCode.IMPORT_HAS_ERRORS,
                HTTPStatus.CONFLICT,
                extra={"row_number": row.row_number, "errors": prepared.errors},
            )
        if row.outcome == "duplicate" and row.match_id is not None:
            row.before = await adapter.update(ctx, principal, row.match_id, prepared.payload)
            row.record_id, row.action = row.match_id, "updated"
            updated += 1
        else:
            row.record_id = await adapter.create(ctx, principal, prepared.payload, batch.id)
            row.action = "created"
            created += 1
    await ctx.session.flush()
    stamps = await adapter.stamps(ctx.session, {r.record_id for r in rows if r.record_id})
    for row in rows:
        if row.record_id is not None:
            row.stamp = stamps.get(row.record_id)
    batch.created_count, batch.updated_count, batch.skipped_count = created, updated, skipped
    batch.status = "committed"
    batch.committed_at = ctx.now
    batch.updated_by = principal.user_id
    await repository.clear_raw(ctx.session, batch.id)
    await _publish(
        ctx, "committed", batch, principal, mode=data.mode, created=created, updated=updated,
        skipped=skipped,
    )  # fmt: skip
    await ctx.session.commit()
    return await _fresh(ctx, batch.id)


async def rollback(ctx: Context, principal: Principal, batch_id: UUID) -> RollbackReport:
    """FR-IMP-01 AC4 (Admin): archive what the batch created and revert what it updated,
    except records changed since the import, which are reported and kept."""
    batch = await _load(ctx, batch_id)
    if batch.status != "committed":
        raise _state_error(batch)
    adapter = ADAPTERS[batch.entity_type]  # type: ignore[index]
    rows = [r for r in await repository.rows(ctx.session, batch.id) if r.record_id is not None]
    current = await adapter.stamps(ctx.session, {r.record_id for r in rows if r.record_id})
    archived = reverted = 0
    for row in rows:
        assert row.record_id is not None  # noqa: S101 - filtered above
        if current.get(row.record_id) != row.stamp:
            row.rollback_result = "changed_since_import"
            continue
        try:
            if row.action == "updated":
                await adapter.restore(ctx, principal, row.record_id, row.before or {})
                row.rollback_result = "reverted"
                reverted += 1
            else:
                await adapter.archive(ctx, principal, row.record_id)
                row.rollback_result = "archived"
                archived += 1
        except AppError as error:  # e.g. organization.has_open_opportunities
            row.rollback_result = f"blocked:{error.code.value}"
    batch.status = "rolled_back"
    batch.rolled_back_at = ctx.now
    batch.updated_by = principal.user_id
    await _publish(ctx, "rolled_back", batch, principal, archived=archived, reverted=reverted)
    await ctx.session.commit()
    kept = [_row_out(batch, r) for r in rows if r.rollback_result not in ("archived", "reverted")]
    return RollbackReport(
        batch=await _fresh(ctx, batch.id), archived=archived, reverted=reverted, kept=kept
    )


async def discard(ctx: Context, principal: Principal, batch_id: UUID) -> None:
    """Delete a batch that was not committed, with its uploaded rows."""
    batch = await _load(ctx, batch_id)
    if batch.status not in _EDITABLE:
        raise _state_error(batch)
    await _publish(ctx, "discarded", batch, principal)
    await repository.delete_batch(ctx.session, batch.id)
    await ctx.session.commit()


async def purge_expired(session: AsyncSession, now: datetime) -> dict[str, int]:
    """Housekeeping (worker): uncommitted batches older than 7 days."""
    removed = await repository.delete_expired(session, now)
    await session.commit()
    return {"import_batches": removed}
