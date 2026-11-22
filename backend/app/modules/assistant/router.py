"""HTTP layer only: parse requests, call the service, shape responses."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock
from app.core.db import DbSession
from app.core.listing import ListQuery, Page, list_query
from app.modules.activity.schemas import ActivityOut
from app.modules.assistant import service
from app.modules.assistant.schemas import (
    ActionConfirmed,
    AssistantStatus,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationRename,
    MessageCreate,
    SaveAsNote,
)

router = APIRouter(prefix="/assistant", tags=["assistant"])
EVENT_STREAM = "text/event-stream"


async def context(request: Request, session: DbSession) -> service.Context:
    clock: Clock = request.app.state.clock
    state = request.app.state
    return service.Context(
        session=session,
        events=state.event_bus,
        settings=state.settings,
        now=clock.now(),
        llm=state.llm,
        engine=state.engine,
        session_factory=state.session_factory,
        organization_stats=state.organization_stats,
        reference_lists=getattr(state, "reference_lists", {}),
        mailer=getattr(state, "mailer", None),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        external_filter=getattr(state, "external_filter", None),
        organization_archive_guards=getattr(state, "organization_archive_guards", ()),
        personal_data_providers=getattr(state, "personal_data_providers", ()),
        contact_anonymizers=getattr(state, "contact_anonymizers", ()),
    )


Ctx = Annotated[service.Context, Depends(context)]
ConversationList = Annotated[
    ListQuery,
    Depends(
        list_query("assistant-conversations", sortable=("updated_at",), default_sort="-updated_at")
    ),
]


@router.get(
    "/status",
    summary="Whether the assistant is enabled, and the caller's remaining daily token budget",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def get_status(ctx: Ctx, principal: CurrentPrincipal) -> AssistantStatus:
    return await service.status(ctx, principal)


@router.get(
    "/conversations",
    summary="Own conversations, newest first",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def list_conversations(
    ctx: Ctx, principal: CurrentPrincipal, query: ConversationList
) -> Page[ConversationOut]:
    return await service.list_conversations(ctx, principal, query)


@router.post(
    "/conversations",
    status_code=status.HTTP_201_CREATED,
    summary="Start a conversation, optionally with record context",
    **endpoint(AccessLevel.SIGNED_IN),
)
async def create_conversation(
    body: ConversationCreate, ctx: Ctx, principal: CurrentPrincipal, response: Response
) -> ConversationOut:
    conversation = await service.create_conversation(ctx, principal, body)
    response.headers["Location"] = f"/api/v1/assistant/conversations/{conversation.id}"
    return conversation


@router.get(
    "/conversations/{conversation_id}",
    summary="Conversation with its messages (tools named, results not included)",
    **endpoint(AccessLevel.SIGNED_IN_OWN),
)
async def get_conversation(
    conversation_id: UUID, ctx: Ctx, principal: CurrentPrincipal
) -> ConversationDetail:
    return await service.get_conversation(ctx, principal, conversation_id)


@router.patch(
    "/conversations/{conversation_id}",
    summary="Rename",
    **endpoint(AccessLevel.SIGNED_IN_OWN),
)
async def rename_conversation(
    conversation_id: UUID, body: ConversationRename, ctx: Ctx, principal: CurrentPrincipal
) -> ConversationOut:
    return await service.rename_conversation(ctx, principal, conversation_id, body)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete permanently with its messages",
    **endpoint(AccessLevel.SIGNED_IN_OWN),
)
async def delete_conversation(conversation_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> None:
    await service.delete_conversation(ctx, principal, conversation_id)


@router.post(
    "/conversations/{conversation_id}/messages",
    summary="Send a message; the answer is a Server-Sent Events stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Events message_start, tool_call, delta, record_ref, message_end, "
            "error (API spec 17)",
            "content": {EVENT_STREAM: {"schema": {"type": "string"}}},
        }
    },
    **endpoint(AccessLevel.SIGNED_IN_OWN),
)
async def send_message(
    conversation_id: UUID, body: MessageCreate, ctx: Ctx, principal: CurrentPrincipal
) -> StreamingResponse:
    turn = await service.prepare_message(ctx, principal, conversation_id, body)
    return StreamingResponse(
        service.stream_answer(ctx, principal, turn),
        media_type=EVENT_STREAM,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/stop",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop a running generation",
    **endpoint(AccessLevel.SIGNED_IN_OWN),
)
async def stop_message(
    conversation_id: UUID, message_id: UUID, ctx: Ctx, principal: CurrentPrincipal
) -> None:
    await service.stop(ctx, principal, conversation_id, message_id)


@router.post(
    "/messages/{message_id}/save-as-note",
    status_code=status.HTTP_201_CREATED,
    summary="Save an assistant draft as a note activity on a record",
    **endpoint(AccessLevel.CONTRIBUTOR),
)
async def save_as_note(
    message_id: UUID, body: SaveAsNote, ctx: Ctx, principal: CurrentPrincipal
) -> ActivityOut:
    return await service.save_as_note(ctx, principal, message_id, body)


@router.post(
    "/actions/{action_id}/confirm",
    summary="Execute a proposed action exactly as shown (FR-AI-09)",
    **endpoint(AccessLevel.SIGNED_IN_OWN),
)
async def confirm_action(action_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> ActionConfirmed:
    return await service.confirm_action(ctx, principal, action_id)


@router.post(
    "/actions/{action_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Discard a proposed action (FR-AI-09)",
    **endpoint(AccessLevel.SIGNED_IN_OWN),
)
async def cancel_action(action_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> None:
    await service.cancel_action(ctx, principal, action_id)
