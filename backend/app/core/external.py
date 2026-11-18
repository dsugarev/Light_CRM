"""List filters on external references (API spec 19.4), as an extension point.

The integration module owns `external_reference`; party and sales lists accept
`external_system`, `external_id` and `has_external_reference` and apply the
condition the integration module provides (registered in app.main, ADR 0018).
"""

from collections.abc import Callable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import ColumnElement, Select

from app.core.errors import AppError, ErrorCode, FieldError

ExternalFilter = Callable[
    [str, ColumnElement[UUID], str, str | None, bool | None], ColumnElement[bool]
]
EXTERNAL_PARAMS = ("external_system", "external_id", "has_external_reference")


@dataclass(frozen=True, slots=True)
class ExternalQuery:
    system: str
    external_id: str | None
    has_reference: bool | None


def external_query(
    system: str | None, external_id: str | None, has_reference: bool | None
) -> ExternalQuery | None:
    """Parse the filter parameters; the other two need `external_system` (400)."""
    if system is None:
        if external_id is not None or has_reference is not None:
            raise AppError(
                ErrorCode.VALIDATION_FAILED,
                HTTPStatus.BAD_REQUEST,
                errors=[FieldError("external_system", "validation.missing")],
            )
        return None
    return ExternalQuery(system, external_id, has_reference)


def apply_external[M](
    statement: Select[M],
    hook: ExternalFilter | None,
    entity_type: str,
    id_column: Any,
    query: ExternalQuery | None,
) -> Select[M]:
    if query is None or hook is None:
        return statement
    return statement.where(
        hook(entity_type, id_column, query.system, query.external_id, query.has_reference)
    )


def external_params(
    external_system: Annotated[str | None, Query(max_length=50)] = None,
    external_id: Annotated[str | None, Query(max_length=200)] = None,
    has_external_reference: bool | None = None,
) -> ExternalQuery | None:
    """FastAPI dependency for the three list parameters."""
    return external_query(external_system, external_id, has_external_reference)


External = Annotated[ExternalQuery | None, Depends(external_params)]
