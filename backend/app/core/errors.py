"""RFC 9457 problem details and the stable error-code catalog.

Codes mirror the table in docs/05-api-specification.md section 1.6. The backend
returns codes, never translated text; the frontend maps codes to messages.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = "https://crm.internal/errors/"


class ErrorCode(StrEnum):
    """Error codes in use. Add a code here only together with the spec table."""

    AUTH_ACCOUNT_LOCKED = "auth.account_locked"
    AUTH_API_KEY_INVALID = "auth.api_key_invalid"
    AUTH_CSRF_FAILED = "auth.csrf_failed"
    AUTH_INVALID_CREDENTIALS = "auth.invalid_credentials"
    AUTH_MIXED_CREDENTIALS = "auth.mixed_credentials"
    AUTH_PASSWORD_POLICY = "auth.password_policy"
    AUTH_SESSION_EXPIRED = "auth.session_expired"
    AUTH_TOKEN_INVALID = "auth.token_invalid"
    CONFLICT_DUPLICATE = "conflict.duplicate"
    CONFLICT_VERSION_MISMATCH = "conflict.version_mismatch"
    LEAD_BANT_INCOMPLETE = "lead.bant_incomplete"
    LEAD_INVALID_TRANSITION = "lead.invalid_transition"
    LEAD_READ_ONLY = "lead.read_only"
    PERMISSION_DENIED = "permission.denied"
    PERMISSION_LAST_ADMIN = "permission.last_admin"
    PERMISSION_NOT_FOR_INTEGRATIONS = "permission.not_for_integrations"
    PERMISSION_SCOPE_MISSING = "permission.scope_missing"
    RATE_LIMIT_EXCEEDED = "rate_limit.exceeded"
    REFERENCE_IN_USE = "reference.in_use"
    RESOURCE_ARCHIVED = "resource.archived"
    REQUEST_METHOD_NOT_ALLOWED = "request.method_not_allowed"
    RESOURCE_NOT_FOUND = "resource.not_found"
    SERVER_INTERNAL_ERROR = "server.internal_error"
    VALIDATION_FAILED = "validation.failed"
    VALIDATION_USE_ACTION_ENDPOINT = "validation.use_action_endpoint"


@dataclass(frozen=True, slots=True)
class FieldError:
    field: str
    code: str


class AppError(Exception):
    """Raised by services; converted to a problem-details response."""

    def __init__(
        self,
        code: ErrorCode,
        status: int,
        *,
        detail: str | None = None,
        errors: Sequence[FieldError] = (),
        extra: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.status = status
        self.detail = detail
        self.errors = list(errors)
        self.extra = dict(extra or {})
        self.headers = dict(headers or {})


def problem_body(
    code: ErrorCode,
    status: int,
    *,
    detail: str | None = None,
    errors: Sequence[FieldError] = (),
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": PROBLEM_TYPE_BASE + code.value,
        "title": HTTPStatus(status).phrase,
        "status": status,
        "code": code.value,
        "request_id": request_id_var.get(),
    }
    if detail is not None:
        body["detail"] = detail
    if errors:
        body["errors"] = [{"field": e.field, "code": e.code} for e in errors]
    if extra:
        body.update(extra)
    return body


def problem_response(
    code: ErrorCode,
    status: int,
    *,
    detail: str | None = None,
    errors: Sequence[FieldError] = (),
    extra: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        problem_body(code, status, detail=detail, errors=errors, extra=extra),
        status_code=status,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=dict(headers or {}),
    )


def _field_name(loc: Sequence[int | str]) -> str:
    # Drop the request part ("body", "query", "path", "header") from the location.
    parts = [str(p) for p in loc]
    if parts and parts[0] in {"body", "query", "path", "header", "cookie"}:
        parts = parts[1:]
    return ".".join(parts) or "body"


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(AppError, exc)
    return problem_response(
        exc.code,
        exc.status,
        detail=exc.detail,
        errors=exc.errors,
        extra=exc.extra,
        headers=exc.headers,
    )


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    raw = cast(RequestValidationError, exc).errors()
    # A body that is not valid JSON is a malformed request (400), not a field error.
    if any(err.get("type") == "json_invalid" for err in raw):
        return problem_response(
            ErrorCode.VALIDATION_FAILED,
            HTTPStatus.BAD_REQUEST,
            errors=[FieldError("body", "validation.json_invalid")],
        )
    errors = [FieldError(_field_name(err["loc"]), f"validation.{err['type']}") for err in raw]
    return problem_response(
        ErrorCode.VALIDATION_FAILED, HTTPStatus.UNPROCESSABLE_CONTENT, errors=errors
    )


async def _handle_http_exception(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, exc)
    status = exc.status_code
    if status == HTTPStatus.NOT_FOUND:
        code = ErrorCode.RESOURCE_NOT_FOUND
    elif status == HTTPStatus.METHOD_NOT_ALLOWED:
        code = ErrorCode.REQUEST_METHOD_NOT_ALLOWED
    elif status < HTTPStatus.INTERNAL_SERVER_ERROR:
        code = ErrorCode.VALIDATION_FAILED
    else:
        code = ErrorCode.SERVER_INTERNAL_ERROR
    return problem_response(code, status, headers=exc.headers)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
