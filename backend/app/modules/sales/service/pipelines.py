"""Pipelines and stages (FR-OPP-02, API spec section 6.3).

One default pipeline in R1. Admins add, rename, reprice, reorder and
(de)activate stages; a stage in use is deactivated rather than deleted
(`409 stage.in_use`). Every pipeline keeps at least one active stage of each
type (open, won, lost), otherwise opportunities could not be created or closed
(`409 stage.required`).
"""

from http import HTTPStatus
from typing import Any
from uuid import UUID

from app.core.errors import AppError, ErrorCode, FieldError
from app.core.principal import Principal
from app.modules.sales import repository
from app.modules.sales.models import Pipeline, PipelineStage
from app.modules.sales.schemas import PipelineOut, StageCreate, StageOut, StageSummary, StageUpdate
from app.modules.sales.service.common import Context, not_found, publish


def stage_out(stage: PipelineStage) -> StageOut:
    return StageOut(
        id=stage.id,
        name_en=stage.name_en,
        name_bg=stage.name_bg,
        position=stage.position,
        default_probability=stage.default_probability,
        stage_type=stage.stage_type,  # type: ignore[arg-type]
        is_active=stage.is_active,
    )


def stage_summary(stage: PipelineStage) -> StageSummary:
    return StageSummary(
        id=stage.id,
        name_en=stage.name_en,
        name_bg=stage.name_bg,
        stage_type=stage.stage_type,  # type: ignore[arg-type]
        position=stage.position,
        default_probability=stage.default_probability,
    )


def _pipeline_out(pipeline: Pipeline) -> PipelineOut:
    return PipelineOut(
        id=pipeline.id,
        name=pipeline.name,
        is_default=pipeline.is_default,
        stages=[
            stage_out(s) for s in sorted(pipeline.stages, key=lambda s: (s.position, s.name_en))
        ],
    )


def _view(stage: PipelineStage) -> dict[str, Any]:
    return stage_out(stage).model_dump(mode="json", exclude={"id"})


async def list_pipelines(ctx: Context) -> list[PipelineOut]:
    return [_pipeline_out(p) for p in await repository.list_pipelines(ctx.session)]


async def _pipeline(ctx: Context, pipeline_id: UUID) -> Pipeline:
    pipeline = await repository.get_pipeline(ctx.session, pipeline_id)
    if pipeline is None:
        raise not_found()
    return pipeline


async def get_pipeline(ctx: Context, pipeline_id: UUID) -> PipelineOut:
    return _pipeline_out(await _pipeline(ctx, pipeline_id))


async def _stage(ctx: Context, pipeline: Pipeline, stage_id: UUID) -> PipelineStage:
    stage = next((s for s in pipeline.stages if s.id == stage_id), None)
    if stage is None:
        raise not_found()
    return stage


def _ensure_type_remains(pipeline: Pipeline, leaving: PipelineStage) -> None:
    others = [
        s
        for s in pipeline.stages
        if s.id != leaving.id and s.is_active and s.stage_type == leaving.stage_type
    ]
    if leaving.is_active and not others:
        raise AppError(
            ErrorCode.STAGE_REQUIRED, HTTPStatus.CONFLICT, extra={"stage_type": leaving.stage_type}
        )


async def add_stage(
    ctx: Context, principal: Principal, pipeline_id: UUID, data: StageCreate
) -> PipelineOut:
    pipeline = await _pipeline(ctx, pipeline_id)
    position = max((s.position for s in pipeline.stages), default=0) + 1
    stage = PipelineStage(
        pipeline_id=pipeline.id, position=position, is_active=True, **data.model_dump()
    )
    ctx.session.add(stage)
    await ctx.session.flush()
    await publish(
        ctx, "pipeline_stage.created", "pipeline_stage", stage.id, principal, after=_view(stage)
    )
    await ctx.session.commit()
    ctx.session.expire_all()
    return await get_pipeline(ctx, pipeline_id)


async def update_stage(
    ctx: Context, principal: Principal, pipeline_id: UUID, stage_id: UUID, data: StageUpdate
) -> PipelineOut:
    pipeline = await _pipeline(ctx, pipeline_id)
    stage = await _stage(ctx, pipeline, stage_id)
    if data.is_active is False:
        _ensure_type_remains(pipeline, stage)
    before = _view(stage)
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(stage, key, value)
    after = _view(stage)
    if after != before:
        await publish(
            ctx,
            "pipeline_stage.updated",
            "pipeline_stage",
            stage.id,
            principal,
            before=before,
            after=after,
        )
    await ctx.session.commit()
    ctx.session.expire_all()
    return await get_pipeline(ctx, pipeline_id)


async def reorder_stages(
    ctx: Context, principal: Principal, pipeline_id: UUID, order: list[UUID]
) -> PipelineOut:
    pipeline = await _pipeline(ctx, pipeline_id)
    stages = {s.id: s for s in pipeline.stages}
    if len(order) != len(set(order)) or set(order) != set(stages):
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            HTTPStatus.UNPROCESSABLE_CONTENT,
            errors=[FieldError("body", "stage.order_incomplete")],
        )
    before = [str(s.id) for s in sorted(stages.values(), key=lambda s: s.position)]
    for position, stage_id in enumerate(order, start=1):
        stages[stage_id].position = position
    await publish(
        ctx, "pipeline_stage.reordered", "pipeline", pipeline.id, principal,
        before={"order": before}, after={"order": [str(i) for i in order]},
    )  # fmt: skip
    await ctx.session.commit()
    ctx.session.expire_all()
    return await get_pipeline(ctx, pipeline_id)


async def delete_stage(
    ctx: Context, principal: Principal, pipeline_id: UUID, stage_id: UUID
) -> None:
    """FR-OPP-02 AC1: a stage in use cannot be deleted, only deactivated."""
    pipeline = await _pipeline(ctx, pipeline_id)
    stage = await _stage(ctx, pipeline, stage_id)
    if await repository.stage_usage(ctx.session, stage.id) > 0:
        raise AppError(ErrorCode.STAGE_IN_USE, HTTPStatus.CONFLICT)
    _ensure_type_remains(pipeline, stage)
    before = _view(stage)
    await ctx.session.delete(stage)
    await publish(
        ctx, "pipeline_stage.deleted", "pipeline_stage", stage_id, principal, before=before
    )
    await ctx.session.commit()


async def default_pipeline(ctx: Context) -> Pipeline:
    pipeline = await repository.get_default_pipeline(ctx.session)
    if pipeline is None:  # pragma: no cover - seeded by migration 0005
        raise not_found()
    return pipeline


def first_stage(pipeline: Pipeline, stage_type: str) -> PipelineStage | None:
    """The first active stage of a type, in pipeline order."""
    candidates = [s for s in pipeline.stages if s.is_active and s.stage_type == stage_type]
    return min(candidates, key=lambda s: s.position) if candidates else None
