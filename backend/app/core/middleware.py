"""Request ID, request logging and last-resort error handling (pure ASGI)."""

import logging
import re
import time
import uuid
from http import HTTPStatus

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import ErrorCode, problem_response
from app.core.logging import client_ip_var, request_id_var

REQUEST_ID_HEADER = "X-Request-ID"
# Client-supplied IDs are echoed back only when they are short and harmless.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

logger = logging.getLogger("app.request")


class RequestContextMiddleware:
    """Assigns a request ID, echoes it in every response, and logs each request.

    Unhandled exceptions are turned into a 500 problem response here, inside the
    request context, so that response also carries the request ID.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        client = scope.get("client")
        ip_token = client_ip_var.set(client[0] if client else None)
        started = time.perf_counter()
        status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("unhandled_error")
            if response_started:
                raise
            response = problem_response(
                ErrorCode.SERVER_INTERNAL_ERROR, HTTPStatus.INTERNAL_SERVER_ERROR
            )
            await response(scope, receive, send_wrapper)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "path": _loggable_path(scope["path"]),
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)
            client_ip_var.reset(ip_token)


def _loggable_path(path: str) -> str:
    """Hide one-time tokens that travel in the path (API spec section 3)."""
    marker = "/auth/password/token/"
    head, sep, _ = path.partition(marker)
    return f"{head}{sep}***" if sep else path


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.fullmatch(candidate) else None
    return None
