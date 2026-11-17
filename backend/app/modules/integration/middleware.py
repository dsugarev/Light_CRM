"""Idempotent creates and per-client usage counters (FR-INT-06, FR-INT-08).

Runs around the API for requests that carry a bearer API key:

- `POST` with `Idempotency-Key`: the first response for a key is stored for 24 hours
  per client and replayed for a retry with the same body (`Idempotent-Replayed: true`);
  the same key with another body is refused (`422 idempotency.key_reused`), and a retry
  while the first request still runs gets `409 idempotency.in_progress` (API spec 19.5).
- Every authenticated integration request is counted in the client's hour, and as an
  error when the response is 4xx or 5xx.
"""

import hashlib
import hmac
import json
from datetime import timedelta
from http import HTTPStatus
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import ErrorCode, FieldError, problem_response
from app.core.principal import Principal
from app.modules.integration import service
from app.modules.integration.models import ApiKey, IdempotencyRecord

RETENTION = timedelta(hours=24)
_KEY_HEADER = b"idempotency-key"
_REPLAYED = "Idempotent-Replayed"
_KEPT_HEADERS = ("location", "content-type")


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return str(value.decode("latin-1"))
    return None


async def _client_of(session: AsyncSession, authorization: str) -> UUID | None:
    """The client of a valid key (the request's own authentication repeats this check)."""
    scheme, _, token = authorization.partition(" ")
    match = service.KEY_PATTERN.match(token.strip()) if scheme.lower() == "bearer" else None
    if match is None:
        return None
    key = (
        await session.execute(select(ApiKey).where(ApiKey.key_id == match[2]))
    ).scalar_one_or_none()
    if (
        key is None
        or key.revoked_at is not None
        or not hmac.compare_digest(key.secret_hash, service.hash_secret(match[3]))
    ):
        return None
    return key.client_id


class IntegrationMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _header(scope, b"authorization") is None:
            await self.app(scope, receive, send)
            return
        state = scope["app"].state
        status_holder: dict[str, int] = {}

        async def counting_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            await send(message)

        key = _header(scope, _KEY_HEADER)
        if scope["method"] == "POST" and key is not None:
            await self._idempotent(scope, receive, counting_send, key)
        else:
            await self.app(scope, receive, counting_send)
        principal = scope.get("state", {}).get("principal")
        if isinstance(principal, Principal) and principal.client_id is not None:
            engine: AsyncEngine = state.engine
            await service.record_usage(
                engine, principal.client_id, state.clock.now(), status_holder.get("status", 500)
            )

    async def _idempotent(self, scope: Scope, receive: Receive, send: Send, key: str) -> None:
        state = scope["app"].state
        factory: async_sessionmaker[AsyncSession] = state.session_factory
        if not 1 <= len(key) <= 255:
            await problem_response(
                ErrorCode.VALIDATION_FAILED,
                HTTPStatus.UNPROCESSABLE_CONTENT,
                errors=[FieldError("Idempotency-Key", "validation.string_too_long")],
            )(scope, receive, send)
            return
        body = b""
        more = True
        while more:
            message = await receive()
            body += message.get("body", b"")
            more = message.get("more_body", False)
        request_hash = hashlib.sha256(
            scope["method"].encode() + b" " + scope["path"].encode() + b"\n" + body
        ).hexdigest()
        now = state.clock.now()
        async with factory() as session:
            client_id = await _client_of(session, _header(scope, b"authorization") or "")
            if client_id is None:  # authentication will refuse the request
                await self.app(scope, _replay_body(body), send)
                return
            existing = (
                await session.execute(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.client_id == client_id, IdempotencyRecord.key == key
                    )
                )
            ).scalar_one_or_none()
            if existing is not None and existing.expires_at <= now:
                await session.delete(existing)
                await session.commit()
                existing = None
            if existing is not None:
                await self._answer_existing(existing, request_hash, scope, receive, send)
                return
            record = IdempotencyRecord(
                client_id=client_id,
                key=key,
                request_hash=request_hash,
                status="in_progress",
                created_at=now,
                expires_at=now + RETENTION,
            )
            session.add(record)
            try:
                await session.commit()
            except IntegrityError:  # a parallel first request won the race
                await session.rollback()
                await _in_progress(scope, receive, send)
                return
            record_id = record.id

        captured = _Captured(send)
        try:
            await self.app(scope, _replay_body(body), captured)
        finally:
            async with factory() as session:
                stored = await session.get(IdempotencyRecord, record_id)
                if stored is not None:
                    if captured.status is not None and captured.status < 500:
                        stored.status = "completed"
                        stored.response_status = captured.status
                        stored.response_headers = captured.kept_headers()
                        stored.response_body = captured.json_body()
                    else:  # a server error or crash may be retried with the same key
                        await session.delete(stored)
                    await session.commit()

    async def _answer_existing(
        self,
        record: IdempotencyRecord,
        request_hash: str,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if record.request_hash != request_hash:
            await problem_response(
                ErrorCode.IDEMPOTENCY_KEY_REUSED, HTTPStatus.UNPROCESSABLE_CONTENT
            )(scope, receive, send)
            return
        if record.status != "completed":
            await _in_progress(scope, receive, send)
            return
        body = b"" if record.response_body is None else json.dumps(record.response_body).encode()
        stored = {k.lower(): str(v) for k, v in (record.response_headers or {}).items()}
        stored.setdefault("content-type", "application/json")
        headers = [(name.encode(), value.encode()) for name, value in stored.items()]
        headers.append((_REPLAYED.lower().encode(), b"true"))
        headers.append((b"content-length", str(len(body)).encode()))
        await send(
            {"type": "http.response.start", "status": record.response_status, "headers": headers}
        )
        await send({"type": "http.response.body", "body": body})


async def _in_progress(scope: Scope, receive: Receive, send: Send) -> None:
    await problem_response(ErrorCode.IDEMPOTENCY_IN_PROGRESS, HTTPStatus.CONFLICT)(
        scope, receive, send
    )


def _replay_body(body: bytes) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


class _Captured:
    """Passes the response through and keeps a copy for the idempotency record."""

    def __init__(self, send: Send) -> None:
        self._send = send
        self.status: int | None = None
        self.headers: list[tuple[bytes, bytes]] = []
        self.body = b""

    async def __call__(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
            self.headers = list(message.get("headers", []))
        elif message["type"] == "http.response.body":
            self.body += message.get("body", b"")
        await self._send(message)

    def kept_headers(self) -> dict[str, str]:
        return {
            name.decode("latin-1"): value.decode("latin-1")
            for name, value in self.headers
            if name.decode("latin-1").lower() in _KEPT_HEADERS
        }

    def json_body(self) -> Any:
        if not self.body:
            return None
        try:
            return json.loads(self.body)
        except ValueError:
            return None
