"""Business rules, permission checks and transactions. Public API of the module.

The AI assistant (FR-AI-01..08, architecture section 8). A message is answered in a
loop: the model may ask for read-only tools (tools.py), which run as the signed-in
user through the other modules' services; after at most `MAX_TOOL_ROUNDS` rounds the
model must answer. The answer is streamed as Server-Sent Events and stored with its
token counts. Chat content is never written to the application logs.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import ratelimit
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.events import DomainEvent, EventBus
from app.core.listing import ListQuery, Page, fetch_page
from app.core.principal import Principal
from app.llm.types import LLM, Completed, LLMUnavailableError, TextDelta, ToolCall
from app.modules.activity import service as activity
from app.modules.activity.schemas import ActivityCreate, ActivityOut
from app.modules.assistant import repository, tools
from app.modules.assistant.models import AssistantUsage, ChatConversation, ChatMessage
from app.modules.assistant.prompt import system_prompt
from app.modules.assistant.schemas import (
    AssistantStatus,
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationRename,
    MessageCreate,
    MessageOut,
    RecordContext,
    RecordRef,
    SaveAsNote,
)
from app.modules.identity import service as identity

logger = logging.getLogger(__name__)

SOFIA = ZoneInfo("Europe/Sofia")
MAX_TOOL_ROUNDS = 5
STOP_CHECK_SECONDS = 0.5
CONVERSATION_SORT = {"updated_at": ChatConversation.updated_at}
_TITLE_CHARS = 80


@dataclass(frozen=True, slots=True)
class Context:
    session: AsyncSession
    events: EventBus
    settings: Settings
    now: datetime
    llm: LLM | None
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    organization_stats: Sequence[Any] = ()


def _not_found() -> AppError:
    return AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)


def _require_enabled(ctx: Context) -> LLM:
    if not ctx.settings.ai_enabled or ctx.llm is None:
        raise AppError(ErrorCode.ASSISTANT_DISABLED, HTTPStatus.SERVICE_UNAVAILABLE)
    return ctx.llm


def _start_of_day(now: datetime) -> datetime:
    """Midnight in Sofia: the daily budget follows the users' working day."""
    local = now.astimezone(SOFIA)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


async def _publish(ctx: Context, action: str, conversation_id: UUID, principal: Principal) -> None:
    # Audit without content: titles and messages stay private to the user.
    await ctx.events.publish(
        ctx.session,
        DomainEvent(
            action=action,
            entity_type="chat_conversation",
            entity_id=conversation_id,
            actor=principal,
            occurred_at=ctx.now,
        ),
    )


# --- Status and budget (FR-AI-07, 08) --------------------------------------------------------


async def _used_today(ctx: Context, user_id: UUID) -> int:
    return await repository.tokens_used(ctx.session, user_id, _start_of_day(ctx.now))


async def status(ctx: Context, principal: Principal) -> AssistantStatus:
    budget = ctx.settings.ai_daily_token_budget
    used = await _used_today(ctx, principal.user_id)
    return AssistantStatus(
        enabled=ctx.settings.ai_enabled and ctx.llm is not None,
        daily_token_budget=budget,
        used_today=used,
        remaining_budget=max(0, budget - used),
    )


# --- Conversations (FR-AI-01) -----------------------------------------------------------------


def _context_of(conversation: ChatConversation) -> RecordContext | None:
    if conversation.context_entity_type is None or conversation.context_entity_id is None:
        return None
    return RecordContext.model_validate(
        {
            "entity_type": conversation.context_entity_type,
            "entity_id": conversation.context_entity_id,
        }
    )


def _conversation_out(conversation: ChatConversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        context=_context_of(conversation),
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message_out(message: ChatMessage) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,  # type: ignore[arg-type]
        content=message.content,
        status=message.status,  # type: ignore[arg-type]
        error_code=message.error_code,
        tools_used=[call["tool"] for call in message.tool_calls or []],
        record_refs=[RecordRef.model_validate(ref) for ref in message.record_refs or []],
        prompt_tokens=message.prompt_tokens,
        completion_tokens=message.completion_tokens,
        created_at=message.created_at,
    )


async def _own(ctx: Context, principal: Principal, conversation_id: UUID) -> ChatConversation:
    conversation = await repository.get_conversation(
        ctx.session, conversation_id, principal.user_id
    )
    if conversation is None:
        raise _not_found()
    return conversation


def _tool_context(
    ctx: Context, session: AsyncSession, principal: Principal, locale: str
) -> tools.ToolContext:
    return tools.ToolContext(
        session=session,
        events=ctx.events,
        settings=ctx.settings,
        now=ctx.now,
        principal=principal,
        locale="bg" if locale == "bg" else "en",
        organization_stats=ctx.organization_stats,
    )


async def _check_context(ctx: Context, principal: Principal, context: RecordContext) -> None:
    tctx = _tool_context(ctx, ctx.session, principal, "en")
    result = await tools.run(
        tctx, "get_record", {"entity_type": context.entity_type, "id": str(context.entity_id)}
    )
    if "error" in result:
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            HTTPStatus.UNPROCESSABLE_CONTENT,
            errors=[FieldError("context.entity_id", f"{context.entity_type}.not_found")],
        )


async def list_conversations(
    ctx: Context, principal: Principal, query: ListQuery
) -> Page[ConversationOut]:
    _require_enabled(ctx)
    rows, total = await fetch_page(
        ctx.session,
        repository.conversations_statement(principal.user_id),
        query,
        CONVERSATION_SORT,
        ChatConversation.id,
    )
    return Page[ConversationOut](
        items=[_conversation_out(c) for c in rows],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


async def create_conversation(
    ctx: Context, principal: Principal, data: ConversationCreate
) -> ConversationOut:
    _require_enabled(ctx)
    if data.context is not None:
        await _check_context(ctx, principal, data.context)
    conversation = ChatConversation(
        user_id=principal.user_id,
        title=data.title,
        context_entity_type=data.context.entity_type if data.context else None,
        context_entity_id=data.context.entity_id if data.context else None,
    )
    ctx.session.add(conversation)
    await ctx.session.flush()
    await _publish(ctx, "chat_conversation.created", conversation.id, principal)
    await ctx.session.commit()
    await ctx.session.refresh(conversation)
    return _conversation_out(conversation)


async def get_conversation(
    ctx: Context, principal: Principal, conversation_id: UUID
) -> ConversationDetail:
    _require_enabled(ctx)
    conversation = await _own(ctx, principal, conversation_id)
    messages = await repository.messages_of(ctx.session, conversation.id)
    return ConversationDetail(
        **_conversation_out(conversation).model_dump(),
        messages=[_message_out(m) for m in messages],
    )


async def rename_conversation(
    ctx: Context, principal: Principal, conversation_id: UUID, data: ConversationRename
) -> ConversationOut:
    _require_enabled(ctx)
    conversation = await _own(ctx, principal, conversation_id)
    conversation.title = data.title
    await _publish(ctx, "chat_conversation.renamed", conversation.id, principal)
    await ctx.session.commit()
    await ctx.session.refresh(conversation)
    return _conversation_out(conversation)


async def delete_conversation(ctx: Context, principal: Principal, conversation_id: UUID) -> None:
    """Permanently, with its messages. Token usage stays (FR-AI-08)."""
    _require_enabled(ctx)
    conversation = await _own(ctx, principal, conversation_id)
    await ctx.session.delete(conversation)
    await _publish(ctx, "chat_conversation.deleted", conversation_id, principal)
    await ctx.session.commit()


# --- Messages (FR-AI-01, 02, 03, 06) ----------------------------------------------------------


def _sse(event: str, data: Mapping[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def _history(messages: Sequence[ChatMessage], limit_tokens: int) -> list[dict[str, Any]]:
    """Earlier questions and answers, newest first until the token limit, in order."""
    kept: list[dict[str, Any]] = []
    used = 0
    for message in reversed(messages):
        if not message.content or message.status == "streaming":
            continue
        cost = _estimate_tokens(message.content)
        if used + cost > limit_tokens:
            break
        used += cost
        kept.append({"role": message.role, "content": message.content})
    kept.reverse()
    return kept


def _title(text: str) -> str:
    line = " ".join(text.split())
    return line if len(line) <= _TITLE_CHARS else line[: _TITLE_CHARS - 1] + "…"


@dataclass(frozen=True, slots=True)
class PreparedTurn:
    """A message accepted for answering: everything the stream needs."""

    conversation_id: UUID
    message_id: UUID
    prompt: list[dict[str, Any]]
    context: RecordContext | None
    locale: str
    remaining_budget: int


async def prepare_message(
    ctx: Context, principal: Principal, conversation_id: UUID, data: MessageCreate
) -> PreparedTurn:
    """Checks that come back as ordinary problem responses, before the stream starts:
    the assistant is on, the conversation is the caller's, the rate limit and the
    daily token budget allow another answer. Stores the question and an empty answer."""
    _require_enabled(ctx)
    conversation = await _own(ctx, principal, conversation_id)
    await ratelimit.hit(
        ctx.engine,
        f"assistant:{principal.user_id}",
        limit=ctx.settings.rate_limit_assistant_per_10_minutes,
        window=timedelta(minutes=10),
        now=ctx.now,
    )
    used = await _used_today(ctx, principal.user_id)
    remaining = ctx.settings.ai_daily_token_budget - used
    if remaining <= 0:
        raise AppError(ErrorCode.ASSISTANT_BUDGET_EXCEEDED, HTTPStatus.TOO_MANY_REQUESTS)
    context = data.context or _context_of(conversation)
    if data.context is not None:
        await _check_context(ctx, principal, data.context)

    earlier = await repository.messages_of(ctx.session, conversation.id)
    locale = await identity.user_locale(ctx.session, principal.user_id)
    prompt = [
        {
            "role": "system",
            "content": system_prompt(
                today=ctx.now.astimezone(SOFIA).date(),
                name=principal.display_name,
                role=principal.role.value,
                locale=locale,
            ),
        },
        *_history(earlier, ctx.settings.ai_history_tokens),
    ]
    question = ChatMessage(
        conversation_id=conversation.id,
        role="user",
        content=data.content,
        status="complete",
        created_at=ctx.now,
    )
    answer = ChatMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="",
        status="streaming",
        # One microsecond later keeps question-then-answer order under a frozen clock.
        created_at=ctx.now + timedelta(microseconds=1),
    )
    ctx.session.add_all([question, answer])
    if conversation.title is None:
        conversation.title = _title(data.content)
    await repository.touch_conversation(ctx.session, conversation.id, ctx.now)
    await ctx.session.commit()
    return PreparedTurn(
        conversation_id=conversation.id,
        message_id=answer.id,
        prompt=[*prompt, {"role": "user", "content": data.content}],
        context=context,
        locale=locale,
        remaining_budget=remaining,
    )


def _context_messages(context: RecordContext, result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The record in view, given to the model as a tool result (FR-AI-03). CRM text only
    ever reaches the model inside tool results (architecture 8.4)."""
    call_id = "context_record"
    arguments = json.dumps({"entity_type": context.entity_type, "id": str(context.entity_id)})
    return [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": "get_record", "arguments": arguments},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(
                {"note": "The record the user is looking at.", "record": result},
                ensure_ascii=False,
            ),
        },
    ]


def _cited(answer: str, seen: Mapping[tuple[str, UUID], str]) -> list[dict[str, Any]]:
    """Records the answer refers to, by ID (in a link) or by name, in order of mention."""
    found: list[tuple[int, dict[str, Any]]] = []
    for (entity_type, entity_id), label in seen.items():
        positions = [p for p in (answer.find(str(entity_id)), _find_label(answer, label)) if p >= 0]
        if positions:
            found.append(
                (
                    min(positions),
                    {"entity_type": entity_type, "entity_id": str(entity_id), "label": label},
                )
            )
    return [ref for _, ref in sorted(found, key=lambda item: item[0])]


def _find_label(answer: str, label: str) -> int:
    if len(label) < 3:
        return -1
    match = re.search(re.escape(label), answer, re.IGNORECASE)
    return match.start() if match else -1


@dataclass(slots=True)
class _Turn:
    """What happened while answering, saved at the end whatever the outcome."""

    text: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    rounds: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    status: Literal["complete", "stopped", "failed"] = "complete"
    error_code: str | None = None


async def stream_answer(
    ctx: Context, principal: Principal, turn: PreparedTurn
) -> AsyncIterator[str]:
    """The Server-Sent Events of one answer (API spec 17). Uses its own database session,
    since it outlives the request handler."""
    llm = _require_enabled(ctx)
    result = _Turn()
    yield _sse(
        "message_start",
        {"message_id": str(turn.message_id), "conversation_id": str(turn.conversation_id)},
    )
    async with ctx.session_factory() as session:
        tctx = _tool_context(ctx, session, principal, turn.locale)
        refs: list[dict[str, Any]] = []
        try:
            prompt = list(turn.prompt)
            if turn.context is not None:
                record = await tools.run(
                    tctx,
                    "get_record",
                    {"entity_type": turn.context.entity_type, "id": str(turn.context.entity_id)},
                )
                prompt[-1:-1] = _context_messages(turn.context, record)
            async for event in _answer(llm, session, turn.message_id, prompt, tctx, result):
                yield event
            refs = _cited(result.text, tctx.seen)
            for ref in refs:
                yield _sse("record_ref", ref)
        except LLMUnavailableError:
            result.status, result.error_code = "failed", ErrorCode.ASSISTANT_PROVIDER_UNAVAILABLE
            yield _sse("error", {"code": result.error_code})
        except asyncio.CancelledError, GeneratorExit:
            # The browser went away: keep what was written, as a stopped answer.
            result.status = "stopped"
            await asyncio.shield(_save(ctx, principal, turn, result, refs))
            raise
        except Exception:
            logger.exception("assistant_failed")  # no chat content in the log record
            result.status, result.error_code = "failed", ErrorCode.SERVER_INTERNAL_ERROR
            yield _sse("error", {"code": result.error_code})
    used = await _save(ctx, principal, turn, result, refs)
    if result.status != "failed":
        yield _sse(
            "message_end",
            {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "remaining_budget": max(0, turn.remaining_budget - used),
                "status": result.status,
            },
        )


async def _answer(
    llm: LLM,
    session: AsyncSession,
    message_id: UUID,
    prompt: list[dict[str, Any]],
    tctx: tools.ToolContext,
    result: _Turn,
) -> AsyncIterator[str]:
    """The tool loop. Fills `result` as it goes; yields `delta` and `tool_call` events."""
    schemas = tools.schemas()
    checked_at = time.monotonic()
    while True:
        offer_tools = result.rounds < MAX_TOOL_ROUNDS
        calls: tuple[ToolCall, ...] = ()
        round_text = ""
        async for item in llm.stream(prompt, schemas if offer_tools else None):
            if isinstance(item, TextDelta):
                round_text += item.text
                result.text += item.text
                yield _sse("delta", {"text": item.text})
                if time.monotonic() - checked_at >= STOP_CHECK_SECONDS:
                    checked_at = time.monotonic()
                    if await repository.stop_requested(session, message_id):
                        result.status = "stopped"
                        return
            elif isinstance(item, Completed):
                result.prompt_tokens += item.usage.prompt_tokens
                result.completion_tokens += item.usage.completion_tokens
                calls = item.tool_calls
        if not calls or not offer_tools:
            return
        if await repository.stop_requested(session, message_id):
            result.status = "stopped"
            return
        result.rounds += 1
        prompt.append(
            {
                "role": "assistant",
                "content": round_text or None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": call.arguments},
                    }
                    for call in calls
                ],
            }
        )
        for call in calls:
            yield _sse("tool_call", {"tool": call.name, "status": "running"})
            output = await tools.run(tctx, call.name, call.arguments)
            result.tool_calls.append({"tool": call.name, "arguments": _arguments(call.arguments)})
            prompt.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(output, ensure_ascii=False, default=str),
                }
            )
            yield _sse("tool_call", {"tool": call.name, "status": "done"})


def _arguments(raw: str) -> Any:
    try:
        return json.loads(raw or "{}")
    except ValueError:
        return {"unparsed": raw[:200]}


async def _save(
    ctx: Context,
    principal: Principal,
    turn: PreparedTurn,
    result: _Turn,
    refs: list[dict[str, Any]],
) -> int:
    """Store the answer and the usage row; returns the tokens this answer used."""
    tokens = result.prompt_tokens + result.completion_tokens
    async with ctx.session_factory() as session:
        message = await session.get(ChatMessage, turn.message_id)
        if message is not None:
            message.content = result.text
            message.status = result.status
            message.error_code = result.error_code
            message.tool_calls = result.tool_calls or None
            message.record_refs = refs or None
            message.prompt_tokens = result.prompt_tokens
            message.completion_tokens = result.completion_tokens
        session.add(
            AssistantUsage(
                user_id=principal.user_id,
                occurred_at=ctx.now,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                tool_rounds=result.rounds,
                outcome=result.status,
            )
        )
        await repository.touch_conversation(session, turn.conversation_id, ctx.now)
        await session.commit()
    return tokens


async def stop(ctx: Context, principal: Principal, conversation_id: UUID, message_id: UUID) -> None:
    """Ask a running answer to stop; the stream ends at its next check (within a second)."""
    _require_enabled(ctx)
    found = await repository.get_message(ctx.session, message_id, principal.user_id)
    if found is None or found[1].id != conversation_id or found[0].role != "assistant":
        raise _not_found()
    if found[0].status == "streaming":
        await repository.request_stop(ctx.session, message_id)
        await ctx.session.commit()


# --- Save as note (FR-AI-04) ------------------------------------------------------------------


def _note_subject(content: str) -> str:
    for line in content.splitlines():
        text = line.strip().lstrip("#>*-• ").strip()
        if text:
            return text if len(text) <= 200 else text[:199] + "…"
    return "—"


async def save_as_note(
    ctx: Context, principal: Principal, message_id: UUID, data: SaveAsNote
) -> ActivityOut:
    """An explicit user action: the draft becomes a note on the record, under the normal
    activity rules and audit (the assistant itself never writes)."""
    _require_enabled(ctx)
    found = await repository.get_message(ctx.session, message_id, principal.user_id)
    if found is None or found[0].role != "assistant":
        raise _not_found()
    link = {f"{data.entity_type}_id": data.entity_id}
    note = ActivityCreate.model_validate(
        {"type": "note", "subject": _note_subject(data.content), "body": data.content, **link}
    )
    return await activity.create_activity(
        activity.Context(ctx.session, ctx.events, ctx.settings, ctx.now), principal, note
    )
