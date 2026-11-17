"""HTTP layer only: parse requests, call the service, shape responses."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock
from app.core.db import DbSession
from app.core.listing import PAGE_SIZE_DEFAULT, PAGE_SIZE_MAX, ListQuery, Page, list_query
from app.modules.dataimport import service
from app.modules.dataimport.fields import EntityType
from app.modules.dataimport.parsing import MAX_FILE_BYTES
from app.modules.dataimport.schemas import (
    CommitRequest,
    ImportBatchOut,
    ImportRowOut,
    MappingRequest,
    RollbackReport,
    RowOutcome,
)
from app.modules.identity import service as identity

router = APIRouter(prefix="/imports", tags=["imports"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def context(request: Request, session: DbSession) -> service.Context:
    clock: Clock = request.app.state.clock
    return service.Context(
        session=session,
        events=request.app.state.event_bus,
        settings=request.app.state.settings,
        now=clock.now(),
    )


Ctx = Annotated[service.Context, Depends(context)]
BatchList = Annotated[
    ListQuery,
    Depends(list_query("imports", sortable=tuple(service.BATCH_SORT), default_sort="-created_at")),
]


@router.get(
    "/templates/{entity_type}",
    summary="Download the XLSX template with headers and an instructions sheet",
    response_class=Response,
    responses={200: {"content": {XLSX: {}}}},
    **endpoint(AccessLevel.MANAGER_PLUS),
)
async def download_template(
    entity_type: EntityType,
    ctx: Ctx,
    principal: CurrentPrincipal,
    locale: Literal["en", "bg"] | None = None,
) -> Response:
    language = locale or await identity.user_locale(ctx.session, principal.user_id)
    return Response(
        content=service.download_template(entity_type, language),
        media_type=XLSX,
        headers={
            "Content-Disposition": f'attachment; filename="import-{entity_type}-{language}.xlsx"'
        },
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file; returns the batch with detected columns and a suggested mapping",
    **endpoint(AccessLevel.MANAGER_PLUS),
)
async def upload(
    ctx: Ctx,
    principal: CurrentPrincipal,
    response: Response,
    file: Annotated[UploadFile, File(description="XLSX or CSV, at most 10 MB")],
    entity_type: Annotated[EntityType, Form()],
) -> ImportBatchOut:
    content = await file.read(MAX_FILE_BYTES + 1)
    batch = await service.upload(ctx, principal, entity_type, file.filename or "upload", content)
    response.headers["Location"] = f"/api/v1/imports/{batch.id}"
    return batch


@router.get("", summary="List batches with status and counts", **endpoint(AccessLevel.MANAGER_PLUS))
async def list_batches(ctx: Ctx, query: BatchList) -> Page[ImportBatchOut]:
    return await service.list_batches(ctx, query)


@router.get("/{batch_id}", summary="Batch detail", **endpoint(AccessLevel.MANAGER_PLUS))
async def get_batch(batch_id: UUID, ctx: Ctx) -> ImportBatchOut:
    return await service.get_batch(ctx, batch_id)


@router.put(
    "/{batch_id}/mapping",
    summary="Set column-to-field mapping and duplicate handling (skip or update)",
    **endpoint(AccessLevel.MANAGER_PLUS),
)
async def set_mapping(
    batch_id: UUID, body: MappingRequest, ctx: Ctx, principal: CurrentPrincipal
) -> ImportBatchOut:
    return await service.set_mapping(ctx, principal, batch_id, body)


@router.post(
    "/{batch_id}/validate",
    summary="Validate all rows; counts of valid, invalid and duplicate rows",
    **endpoint(AccessLevel.MANAGER_PLUS),
)
async def validate(batch_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> ImportBatchOut:
    return await service.validate(ctx, principal, batch_id)


@router.get(
    "/{batch_id}/rows",
    summary="Paginated preview; filter outcome; each row lists field errors",
    **endpoint(AccessLevel.MANAGER_PLUS),
)
async def list_rows(
    batch_id: UUID,
    ctx: Ctx,
    outcome: Annotated[list[RowOutcome] | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=PAGE_SIZE_MAX)] = PAGE_SIZE_DEFAULT,
) -> Page[ImportRowOut]:
    return await service.list_rows(ctx, batch_id, tuple(outcome or ()), page, page_size)


@router.post(
    "/{batch_id}/commit",
    summary="Write records; strict fails with 409 import.has_errors if any row is invalid",
    **endpoint(AccessLevel.MANAGER_PLUS),
)
async def commit(
    batch_id: UUID, body: CommitRequest, ctx: Ctx, principal: CurrentPrincipal
) -> ImportBatchOut:
    return await service.commit(ctx, principal, batch_id, body)


@router.post(
    "/{batch_id}/rollback",
    summary="Archive records created by the batch and revert its updates",
    **endpoint(AccessLevel.ADMIN),
)
async def rollback(batch_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> RollbackReport:
    return await service.rollback(ctx, principal, batch_id)


@router.delete(
    "/{batch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Discard a batch that was not committed, including its uploaded data",
    **endpoint(AccessLevel.MANAGER_PLUS),
)
async def discard(batch_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> None:
    await service.discard(ctx, principal, batch_id)
