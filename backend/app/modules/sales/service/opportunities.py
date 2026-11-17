"""Opportunities (FR-OPP-01..06): rules, stages, closing, board.

Changes require the `version` the caller loaded. Stage changes go through
`move` (between open stages), `close` (won/lost) and `reopen` (Manager+), each
recorded in the stage history (FR-OPP-02 AC2). Probability follows the stage
default unless the user overrode it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from http import HTTPStatus
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import runtime_settings
from app.core.errors import AppError, ErrorCode
from app.core.listing import ListQuery, Page, SyncPage, encode_cursor, fetch_page, fetch_sync
from app.core.policy import can_edit_owned, check_owner
from app.core.principal import Principal
from app.core.reference import ReferenceList, is_active_item
from app.core.search import SearchHit, SearchProvider
from app.core.text import search_terms, search_text
from app.modules.identity import service as identity
from app.modules.party import service as party
from app.modules.sales import repository
from app.modules.sales.models import (
    LossReason,
    Opportunity,
    OpportunityStageHistory,
    Pipeline,
    PipelineStage,
)
from app.modules.sales.schemas import (
    Board,
    BoardCard,
    BoardColumn,
    CloseRequest,
    LinkSummary,
    MoveRequest,
    OpportunityCreate,
    OpportunityOut,
    OpportunityUpdate,
    ReopenRequest,
    StageChange,
    StageSummary,
)
from app.modules.sales.service.common import (
    Context,
    check_owner_choice,
    invalid,
    not_found,
    publish,
    reference,
    use_action_endpoint,
    user,
    version_conflict,
)
from app.modules.sales.service.pipelines import default_pipeline, first_stage, stage_summary

SOFIA = ZoneInfo("Europe/Sofia")
BOARD_CARD_LIMIT = 500
OPPORTUNITY_SORT = {
    "amount": Opportunity.amount,
    "expected_close_date": Opportunity.expected_close_date,
    "updated_at": Opportunity.updated_at,
    "name": Opportunity.name,
}


@dataclass(frozen=True, slots=True)
class OpportunityFilters:
    stage_ids: tuple[UUID, ...] = ()
    stage_types: tuple[str, ...] = ()
    owner_ids: tuple[UUID, ...] = ()
    organization_ids: tuple[UUID, ...] = ()
    pipeline_ids: tuple[UUID, ...] = ()
    close_from: date | None = None
    close_to: date | None = None
    amount_from: Decimal | None = None
    amount_to: Decimal | None = None
    is_stale: bool | None = None


# --- Helpers ------------------------------------------------------------------------------


def today(ctx: Context) -> date:
    """Business date in Sofia (FR-I18N-03)."""
    return ctx.now.astimezone(SOFIA).date()


async def _stale_cutoff(ctx: Context) -> datetime:
    settings = await runtime_settings.load(ctx.session)
    return ctx.now - timedelta(days=settings.stale_opportunity_days)


def _is_stale(opp: Opportunity, stale_before: datetime, on: date) -> bool:
    if opp.stage.stage_type != "open":
        return False
    last = opp.last_activity_at or opp.created_at
    overdue = opp.expected_close_date is not None and opp.expected_close_date < on
    return last < stale_before or overdue


def _weighted(opp: Opportunity) -> Decimal | None:
    if opp.amount is None:
        return None
    return (opp.amount * opp.probability / 100).quantize(Decimal("0.01"))


def _view(opp: Opportunity) -> dict[str, Any]:
    """Fields recorded in the audit log and compared for changes."""
    return {
        "name": opp.name,
        "organization_id": str(opp.organization_id),
        "primary_contact_id": str(opp.primary_contact_id) if opp.primary_contact_id else None,
        "owner_id": str(opp.owner_id),
        "stage_id": str(opp.stage_id),
        "amount": f"{opp.amount:.2f}" if opp.amount is not None else None,
        "probability": opp.probability,
        "probability_overridden": opp.probability_overridden,
        "expected_close_date": opp.expected_close_date.isoformat()
        if opp.expected_close_date
        else None,
        "actual_close_date": opp.actual_close_date.isoformat() if opp.actual_close_date else None,
        "next_step": opp.next_step,
        "description": opp.description,
        "loss_reason_id": str(opp.loss_reason_id) if opp.loss_reason_id else None,
        "competitor": opp.competitor,
    }


def _search_text(opp: Opportunity, organization_name: str) -> str:
    return search_text(opp.name, organization_name, opp.competitor)


async def _outs(ctx: Context, opps: list[Opportunity]) -> list[OpportunityOut]:
    names = await identity.user_names(
        ctx.session, {o.owner_id for o in opps} | {o.created_by for o in opps if o.created_by}
    )
    orgs = {
        i: await party.organization_summary(ctx.session, i)
        for i in {o.organization_id for o in opps}
    }
    contacts = {
        o.primary_contact_id: await party.contact_link(
            ctx.session, o.primary_contact_id, include_archived=True
        )
        for o in opps
        if o.primary_contact_id
    }
    leads = {
        o.source_lead_id: await repository.get_lead(ctx.session, o.source_lead_id)
        for o in opps
        if o.source_lead_id
    }
    stale_before, on = await _stale_cutoff(ctx), today(ctx)
    out: list[OpportunityOut] = []
    for o in opps:
        org = orgs[o.organization_id]
        contact = contacts.get(o.primary_contact_id) if o.primary_contact_id else None
        lead = leads.get(o.source_lead_id) if o.source_lead_id else None
        owner = user(names, o.owner_id)
        assert owner is not None  # noqa: S101 - owner_id is NOT NULL
        out.append(
            OpportunityOut(
                id=o.id,
                name=o.name,
                organization=LinkSummary(id=o.organization_id, name=org.name if org else ""),
                primary_contact=LinkSummary(id=contact.id, name=contact.full_name)
                if contact
                else None,
                owner=owner,
                pipeline_id=o.pipeline_id,
                stage=stage_summary(o.stage),
                amount=o.amount,
                currency=o.currency,
                probability=o.probability,
                probability_overridden=o.probability_overridden,
                weighted_amount=_weighted(o),
                expected_close_date=o.expected_close_date,
                actual_close_date=o.actual_close_date,
                next_step=o.next_step,
                description=o.description,
                source_lead=LinkSummary(id=lead.id, name=lead.title) if lead else None,
                loss_reason=reference(o.loss_reason),
                competitor=o.competitor,
                is_stale=_is_stale(o, stale_before, on),
                last_activity_at=o.last_activity_at,
                created_at=o.created_at,
                updated_at=o.updated_at,
                created_by=user(names, o.created_by),
                archived_at=o.archived_at,
                version=o.version,
            )
        )
    return out


async def _fresh(ctx: Context, opp_id: UUID) -> OpportunityOut:
    ctx.session.expire_all()
    opp = await repository.get_opportunity(ctx.session, opp_id)
    assert opp is not None  # noqa: S101 - exists
    return (await _outs(ctx, [opp]))[0]


async def _check_contact(ctx: Context, organization_id: UUID, contact_id: UUID | None) -> None:
    if contact_id is None:
        return
    contact = await party.contact_link(ctx.session, contact_id)
    if contact is None:
        raise invalid("primary_contact_id", "contact.not_found")
    if contact.organization_id not in (None, organization_id):
        raise invalid("primary_contact_id", "contact.organization_mismatch")


def _open_stage(pipeline: Pipeline, stage_id: UUID, field: str = "stage_id") -> PipelineStage:
    stage = next((s for s in pipeline.stages if s.id == stage_id), None)
    if stage is None or not stage.is_active or stage.stage_type != "open":
        raise invalid(field, "stage.not_open")
    return stage


async def _pipeline_of(ctx: Context, opp: Opportunity) -> Pipeline:
    pipeline = await repository.get_pipeline(ctx.session, opp.pipeline_id)
    assert pipeline is not None  # noqa: S101 - FK
    return pipeline


def _record_stage(
    ctx: Context, principal: Principal, opp: Opportunity, from_stage: UUID | None
) -> None:
    ctx.session.add(
        OpportunityStageHistory(
            opportunity_id=opp.id,
            from_stage_id=from_stage,
            to_stage_id=opp.stage_id,
            changed_by=principal.user_id,
            changed_at=ctx.now,
        )
    )


async def _load(ctx: Context, opp_id: UUID, version: int | None = None) -> Opportunity:
    opp = await repository.get_opportunity(ctx.session, opp_id, for_update=True)
    if opp is None:
        raise not_found()
    if version is not None and opp.version != version:
        raise version_conflict((await _outs(ctx, [opp]))[0].model_dump(mode="json"))
    return opp


def _ensure_open(opp: Opportunity) -> None:
    if opp.archived_at is not None:
        raise AppError(ErrorCode.RESOURCE_ARCHIVED, HTTPStatus.CONFLICT)
    if opp.stage.stage_type != "open":
        raise AppError(ErrorCode.OPPORTUNITY_CLOSED, HTTPStatus.CONFLICT)


async def _commit(
    ctx: Context,
    principal: Principal,
    opp: Opportunity,
    action: str,
    before: Mapping[str, Any],
    *,
    details: Mapping[str, Any] | None = None,
) -> OpportunityOut:
    org = await party.organization_summary(ctx.session, opp.organization_id)
    opp.search_text = _search_text(opp, org.name if org else "")
    opp.updated_by = principal.user_id
    after = _view(opp)
    if after != before:
        opp.version += 1
        await publish(
            ctx,
            action,
            "opportunity",
            opp.id,
            principal,
            before=before,
            after=after,
            details=details,
        )
    await ctx.session.commit()
    return await _fresh(ctx, opp.id)


async def default_first_stage(ctx: Context) -> StageSummary:
    """Where a new opportunity starts unless a stage is chosen (FR-OPP-01)."""
    stage = first_stage(await default_pipeline(ctx), "open")
    assert stage is not None  # noqa: S101 - guarded by stage.required
    return stage_summary(stage)


# --- Create and read ----------------------------------------------------------------------


async def create_opportunity(
    ctx: Context,
    principal: Principal,
    data: OpportunityCreate,
    *,
    source_lead_id: UUID | None = None,
    commit: bool = True,
) -> Opportunity:
    """FR-OPP-01: stage defaults to the first open stage, probability to its default."""
    owner_id = data.owner_id or principal.user_id
    await check_owner_choice(ctx, principal, owner_id)
    problem = await party.check_organization_link(ctx.session, data.organization_id)
    if problem:
        raise invalid("organization_id", problem)
    await _check_contact(ctx, data.organization_id, data.primary_contact_id)
    pipeline = await default_pipeline(ctx)
    if data.stage_id is not None:
        stage = _open_stage(pipeline, data.stage_id)
    else:
        found = first_stage(pipeline, "open")
        if found is None:  # pragma: no cover - guarded by stage.required
            raise invalid("stage_id", "stage.not_open")
        stage = found
    org = await party.organization_summary(ctx.session, data.organization_id)
    opp = Opportunity(
        **data.model_dump(exclude={"owner_id", "stage_id", "probability"}),
        owner_id=owner_id,
        pipeline_id=pipeline.id,
        stage_id=stage.id,
        probability=data.probability if data.probability is not None else stage.default_probability,
        probability_overridden=data.probability is not None,
        source_lead_id=source_lead_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
    )
    opp.search_text = _search_text(opp, org.name if org else "")
    ctx.session.add(opp)
    await ctx.session.flush()
    _record_stage(ctx, principal, opp, None)
    await ctx.session.refresh(opp)
    await publish(ctx, "opportunity.created", "opportunity", opp.id, principal, after=_view(opp))
    if commit:
        await ctx.session.commit()
    return opp


async def create(ctx: Context, principal: Principal, data: OpportunityCreate) -> OpportunityOut:
    opp = await create_opportunity(ctx, principal, data)
    return await _fresh(ctx, opp.id)


async def get(ctx: Context, opp_id: UUID) -> OpportunityOut:
    opp = await repository.get_opportunity(ctx.session, opp_id)
    if opp is None:
        raise not_found()
    return (await _outs(ctx, [opp]))[0]


async def _statement(ctx: Context, query: ListQuery | None, filters: OpportunityFilters) -> Any:
    stale = None
    if filters.is_stale is not None:
        stale = (filters.is_stale, await _stale_cutoff(ctx), today(ctx))
    return repository.opportunities_statement(
        search=search_terms(query.q) if query and query.q else None,
        include_archived=query.include_archived if query else False,
        stage_ids=filters.stage_ids,
        stage_types=filters.stage_types,
        owner_ids=filters.owner_ids,
        organization_ids=filters.organization_ids,
        pipeline_ids=filters.pipeline_ids,
        close_from=filters.close_from,
        close_to=filters.close_to,
        amount_from=filters.amount_from,
        amount_to=filters.amount_to,
        stale=stale,
    )


async def list_opportunities(
    ctx: Context, query: ListQuery, filters: OpportunityFilters
) -> Page[OpportunityOut] | SyncPage[OpportunityOut]:
    """FR-OPP-04."""
    statement = await _statement(ctx, query, filters)
    if query.sync:
        rows, cursor = await fetch_sync(
            ctx.session, statement, query, Opportunity.updated_at, Opportunity.id,
            safety_lag_seconds=ctx.settings.sync_safety_lag_seconds,
        )  # fmt: skip
        return SyncPage[OpportunityOut](
            items=await _outs(ctx, rows),
            next_cursor=encode_cursor(ctx.settings.app_secret_key, query.resource, cursor)
            if cursor
            else None,
        )
    rows, total = await fetch_page(ctx.session, statement, query, OPPORTUNITY_SORT, Opportunity.id)
    return Page[OpportunityOut](
        items=await _outs(ctx, rows), total=total, page=query.page, page_size=query.page_size
    )


# --- Update and stage changes ---------------------------------------------------------------


async def update(
    ctx: Context, principal: Principal, opp_id: UUID, data: OpportunityUpdate
) -> OpportunityOut:
    for field in ("stage_id", "owner_id", "organization_id"):
        if field in data.model_fields_set:
            raise use_action_endpoint(field)
    opp = await _load(ctx, opp_id, data.version)
    check_owner(principal, opp.owner_id)
    _ensure_open(opp)
    changes = data.model_dump(
        exclude_unset=True, exclude={"version", "stage_id", "owner_id", "organization_id"}
    )
    if "name" in changes and changes["name"] is None:
        raise invalid("name", "validation.missing")
    if "primary_contact_id" in changes:
        await _check_contact(ctx, opp.organization_id, changes["primary_contact_id"])
    before = _view(opp)
    if "probability" in changes:
        probability = changes.pop("probability")
        if probability is None:  # back to the stage default
            opp.probability = opp.stage.default_probability
            opp.probability_overridden = False
        else:
            opp.probability = probability
            opp.probability_overridden = True
    for key, value in changes.items():
        setattr(opp, key, value)
    return await _commit(ctx, principal, opp, "opportunity.updated", before)


async def move(
    ctx: Context, principal: Principal, opp_id: UUID, data: MoveRequest
) -> OpportunityOut:
    """FR-OPP-02/03: change between open stages; closing goes through `close`."""
    opp = await _load(ctx, opp_id, data.version)
    check_owner(principal, opp.owner_id)
    _ensure_open(opp)
    stage = _open_stage(await _pipeline_of(ctx, opp), data.stage_id)
    if stage.id == opp.stage_id:
        return (await _outs(ctx, [opp]))[0]
    before = _view(opp)
    from_stage = opp.stage_id
    opp.stage_id = stage.id
    opp.stage = stage
    if not opp.probability_overridden:
        opp.probability = stage.default_probability
    _record_stage(ctx, principal, opp, from_stage)
    return await _commit(ctx, principal, opp, "opportunity.stage_changed", before)


async def close(
    ctx: Context, principal: Principal, opp_id: UUID, data: CloseRequest
) -> OpportunityOut:
    """FR-OPP-05: won or lost with the actual close date; lost needs a loss reason."""
    if data.outcome == "lost":
        if data.loss_reason_id is None:
            raise AppError(
                ErrorCode.OPPORTUNITY_LOSS_REASON_REQUIRED, HTTPStatus.UNPROCESSABLE_CONTENT
            )
        if not await is_active_item(ctx.session, LossReason, data.loss_reason_id):
            raise invalid("loss_reason_id", "reference.invalid")
    opp = await _load(ctx, opp_id, data.version)
    check_owner(principal, opp.owner_id)
    _ensure_open(opp)
    stage = first_stage(await _pipeline_of(ctx, opp), data.outcome)
    if stage is None:  # pragma: no cover - guarded by stage.required
        raise AppError(ErrorCode.STAGE_REQUIRED, HTTPStatus.CONFLICT)
    before = _view(opp)
    from_stage = opp.stage_id
    opp.stage_id = stage.id
    opp.stage = stage
    opp.probability = stage.default_probability
    opp.probability_overridden = False
    opp.actual_close_date = data.actual_close_date or today(ctx)
    opp.loss_reason_id = data.loss_reason_id if data.outcome == "lost" else None
    if data.competitor is not None:
        opp.competitor = data.competitor or None
    _record_stage(ctx, principal, opp, from_stage)
    action = "opportunity.closed_won" if data.outcome == "won" else "opportunity.closed_lost"
    return await _commit(ctx, principal, opp, action, before)


async def reopen(
    ctx: Context, principal: Principal, opp_id: UUID, data: ReopenRequest
) -> OpportunityOut:
    """FR-OPP-05: Managers+ reopen a closed opportunity into an open stage (route is Manager+)."""
    opp = await _load(ctx, opp_id, data.version)
    if opp.archived_at is not None:
        raise AppError(ErrorCode.RESOURCE_ARCHIVED, HTTPStatus.CONFLICT)
    if opp.stage.stage_type == "open":
        raise AppError(ErrorCode.OPPORTUNITY_NOT_CLOSED, HTTPStatus.CONFLICT)
    stage = _open_stage(await _pipeline_of(ctx, opp), data.stage_id)
    before = _view(opp)
    from_stage = opp.stage_id
    opp.stage_id = stage.id
    opp.stage = stage
    opp.probability = stage.default_probability
    opp.probability_overridden = False
    opp.actual_close_date = None
    opp.loss_reason_id = None
    _record_stage(ctx, principal, opp, from_stage)
    return await _commit(ctx, principal, opp, "opportunity.reopened", before)


async def assign(
    ctx: Context, principal: Principal, opp_id: UUID, owner_id: UUID, version: int
) -> OpportunityOut:
    """Same rules as leads (FR-LEAD-06)."""
    opp = await _load(ctx, opp_id, version)
    _ensure_open(opp)
    await check_owner_choice(ctx, principal, owner_id)
    before = _view(opp)
    opp.owner_id = owner_id
    return await _commit(ctx, principal, opp, "opportunity.owner_changed", before)


async def archive(ctx: Context, principal: Principal, opp_id: UUID) -> None:
    opp = await _load(ctx, opp_id)
    check_owner(principal, opp.owner_id)
    if opp.archived_at is None:
        opp.archived_at = ctx.now
        opp.updated_by = principal.user_id
        opp.version += 1
        await publish(ctx, "opportunity.archived", "opportunity", opp.id, principal)
    await ctx.session.commit()


async def restore(ctx: Context, principal: Principal, opp_id: UUID) -> OpportunityOut:
    opp = await _load(ctx, opp_id)
    if opp.archived_at is not None:
        opp.archived_at = None
        opp.updated_by = principal.user_id
        opp.version += 1
        await publish(ctx, "opportunity.restored", "opportunity", opp.id, principal)
    await ctx.session.commit()
    return await _fresh(ctx, opp.id)


async def stage_history(ctx: Context, opp_id: UUID) -> list[StageChange]:
    """FR-OPP-02 AC2."""
    if await repository.get_opportunity(ctx.session, opp_id) is None:
        raise not_found()
    rows = await repository.stage_history(ctx.session, opp_id)
    names = await identity.user_names(ctx.session, {r.changed_by for r in rows if r.changed_by})
    return [
        StageChange(
            id=r.id,
            from_stage=stage_summary(r.from_stage) if r.from_stage else None,
            to_stage=stage_summary(r.to_stage),
            changed_by=user(names, r.changed_by),
            changed_at=r.changed_at,
        )
        for r in rows
    ]


# --- Board (FR-OPP-03) --------------------------------------------------------------------


async def board(ctx: Context, principal: Principal, filters: OpportunityFilters) -> Board:
    """One column per active open stage with count, total, weighted amount and cards."""
    pipeline = (
        await repository.get_pipeline(ctx.session, filters.pipeline_ids[0])
        if filters.pipeline_ids
        else await default_pipeline(ctx)
    )
    if pipeline is None:
        raise not_found()
    columns_stages = sorted(
        (s for s in pipeline.stages if s.is_active and s.stage_type == "open"),
        key=lambda s: s.position,
    )
    scoped = OpportunityFilters(
        owner_ids=filters.owner_ids,
        pipeline_ids=(pipeline.id,),
        close_from=filters.close_from,
        close_to=filters.close_to,
        stage_types=("open",),
    )
    statement = await _statement(ctx, None, scoped)
    totals = await repository.column_totals(ctx.session, statement)
    rows = list(
        (
            await ctx.session.execute(
                statement.order_by(
                    Opportunity.expected_close_date.asc().nulls_last(), Opportunity.id
                ).limit(BOARD_CARD_LIMIT + 1)
            )
        )
        .unique()
        .scalars()
    )
    truncated = len(rows) > BOARD_CARD_LIMIT
    rows = rows[:BOARD_CARD_LIMIT]
    outs = {o.id: o for o in await _outs(ctx, rows)}
    columns: list[BoardColumn] = []
    for stage in columns_stages:
        count, total, weighted = totals.get(stage.id, (0, Decimal(0), Decimal(0)))
        cards = [
            BoardCard(
                id=o.id,
                name=o.name,
                organization=outs[o.id].organization,
                amount=o.amount,
                expected_close_date=o.expected_close_date,
                owner=outs[o.id].owner,
                is_stale=outs[o.id].is_stale,
                can_edit=can_edit_owned(principal, o.owner_id),
                version=o.version,
            )
            for o in rows
            if o.stage_id == stage.id
        ]
        columns.append(
            BoardColumn(
                stage=stage_summary(stage),
                count=count,
                total_amount=total.quantize(Decimal("0.01")),
                weighted_amount=weighted.quantize(Decimal("0.01")),
                cards=cards,
            )
        )
    return Board(pipeline_id=pipeline.id, columns=columns, truncated=truncated)


# --- Contributions to other modules (ADR 0018) ---------------------------------------------


async def organization_opportunity_stats(
    session: AsyncSession, organization_id: UUID
) -> dict[str, Any]:
    count, total = await repository.open_opportunity_figures(session, organization_id)
    return {"open_opportunities": count, "open_pipeline_value": f"{total:.2f}"}


async def organization_archive_guard(
    session: AsyncSession, organization_id: UUID
) -> ErrorCode | None:
    """FR-PARTY-01 / API spec 7: archiving is blocked while open opportunities exist."""
    count, _ = await repository.open_opportunity_figures(session, organization_id)
    return ErrorCode.ORGANIZATION_HAS_OPEN_OPPORTUNITIES if count else None


async def search_opportunities(
    session: AsyncSession, terms: list[list[str]], limit: int
) -> list[SearchHit]:
    statement = (
        repository.opportunities_statement(search=terms, include_archived=False)
        .order_by(Opportunity.updated_at.desc())
        .limit(limit)
    )
    hits: list[SearchHit] = []
    for opp in (await session.execute(statement)).unique().scalars():
        org = await party.organization_summary(session, opp.organization_id)
        hits.append(
            SearchHit(
                type="opportunity", id=opp.id, label=opp.name, detail=org.name if org else None
            )
        )
    return hits


async def _loss_reason_usage(session: AsyncSession, item_id: UUID) -> int:
    return await repository.count_with_loss_reason(session, item_id)


REFERENCE_LISTS = (ReferenceList("loss-reasons", "loss_reason", LossReason, _loss_reason_usage),)
SEARCH_PROVIDERS = (SearchProvider("opportunity", search_opportunities),)
