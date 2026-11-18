"""List and report exports to XLSX or CSV (FR-REP-02; API spec section 14).

Modules describe their columns (key plus English and Bulgarian header) and turn
their response models into rows; this module writes the file. Exports are
synchronous, capped at 50,000 rows, protected against spreadsheet formula
injection (architecture section 7) and audited by the calling service.
"""

import csv
import io
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from http import HTTPStatus
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import Query, Response
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import AppError, ErrorCode, FieldError
from app.core.events import DomainEvent
from app.core.listing import ListQuery
from app.core.principal import Principal

EXPORT_ROW_CAP = 50_000
SOFIA = ZoneInfo("Europe/Sofia")
# Characters that make a spreadsheet treat text as a formula (OWASP CSV injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_BOOLEANS = {"en": ("Yes", "No"), "bg": ("Да", "Не")}

Locale = Literal["en", "bg"]


class ExportFormat(StrEnum):
    XLSX = "xlsx"
    CSV = "csv"


_MEDIA_TYPES = {
    ExportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ExportFormat.CSV: "text/csv; charset=utf-8",
}


@dataclass(frozen=True, slots=True)
class ExportColumn:
    key: str
    en: str
    bg: str

    def header(self, locale: Locale) -> str:
        return self.bg if locale == "bg" else self.en


@dataclass(frozen=True, slots=True)
class ExportOptions:
    format: ExportFormat
    columns: tuple[str, ...] | None
    locale: Locale | None


def export_options(
    format: ExportFormat = ExportFormat.XLSX,  # the documented parameter name
    columns: Annotated[str | None, Query(max_length=1000)] = None,
    locale: Locale | None = None,
) -> ExportOptions:
    """FastAPI dependency for the export parameters (API spec 14)."""
    keys = tuple(c.strip() for c in columns.split(",") if c.strip()) if columns else None
    return ExportOptions(format=format, columns=keys or None, locale=locale)


def select_columns(
    available: Sequence[ExportColumn], wanted: Sequence[str] | None
) -> list[ExportColumn]:
    """The requested columns in the requested order; unknown keys are refused (400)."""
    if not wanted:
        return list(available)
    by_key = {c.key: c for c in available}
    unknown = [key for key in wanted if key not in by_key]
    if unknown:
        raise AppError(
            ErrorCode.VALIDATION_FAILED,
            HTTPStatus.BAD_REQUEST,
            errors=[FieldError("columns", "export.unknown_column")],
            extra={"unknown": unknown},
        )
    return [by_key[key] for key in wanted]


def check_row_count(count: int) -> None:
    if count > EXPORT_ROW_CAP:
        raise AppError(
            ErrorCode.EXPORT_TOO_MANY_ROWS,
            HTTPStatus.UNPROCESSABLE_CONTENT,
            extra={"rows": count, "limit": EXPORT_ROW_CAP},
        )


def neutralize(value: str) -> str:
    """Prefix text a spreadsheet would run as a formula with an apostrophe."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


def _cell(value: Any, locale: Locale) -> Any:
    """A value as written to the sheet: numbers and dates stay typed, text is neutralized."""
    if value is None:
        return None
    if isinstance(value, bool):
        yes, no = _BOOLEANS[locale]
        return yes if value else no
    if isinstance(value, datetime):
        return value.astimezone(SOFIA).replace(tzinfo=None, microsecond=0)
    if isinstance(value, (int, float, Decimal, date)):
        return value
    if isinstance(value, UUID):
        return str(value)
    return neutralize(str(value))


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def render(
    columns: Sequence[ExportColumn],
    rows: Iterable[Mapping[str, Any]],
    fmt: ExportFormat,
    locale: Locale,
    *,
    sheet: str,
) -> bytes:
    headers = [c.header(locale) for c in columns]
    if fmt is ExportFormat.CSV:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow([neutralize(h) for h in headers])
        for row in rows:
            writer.writerow([_csv_text(_cell(row.get(c.key), locale)) for c in columns])
        # UTF-8 with BOM so Excel shows Cyrillic correctly (API spec 14).
        return ("﻿" + buffer.getvalue()).encode("utf-8")
    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet(title=sheet[:31])
    for index in range(1, len(columns) + 1):  # write-only sheets need widths first
        worksheet.column_dimensions[get_column_letter(index)].width = 22
    worksheet.append(headers)
    for row in rows:
        worksheet.append([_cell(row.get(c.key), locale) for c in columns])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def file_response(content: bytes, fmt: ExportFormat, name: str, today: date) -> Response:
    filename = f"{name}-{today.isoformat()}.{fmt.value}"
    return Response(
        content=content,
        media_type=_MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@dataclass(frozen=True, slots=True)
class ExportFile:
    """What an export service returns to its router."""

    content: bytes
    format: ExportFormat
    name: str
    day: date

    def response(self) -> Response:
        return file_response(self.content, self.format, self.name, self.day)


def _json(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def exported_event(
    entity_type: str,
    principal: Principal,
    now: datetime,
    *,
    rows: int,
    options: ExportOptions,
    filters: Mapping[str, Any],
) -> DomainEvent:
    """Audit entry for an export (FR-REP-02: exports are audited)."""
    return DomainEvent(
        action=f"{entity_type}.exported",
        entity_type=entity_type,
        entity_id=None,
        actor=principal,
        occurred_at=now,
        details={
            "format": options.format.value,
            "rows": rows,
            "columns": list(options.columns) if options.columns else None,
            "filters": {k: _json(v) for k, v in filters.items() if v not in (None, (), [], False)},
        },
    )


RowBuilder = Callable[[Any, Locale], Mapping[str, Any]]
EXPORT_PARAMS = ("format", "columns", "locale")
EXPORT_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "The file (Content-Disposition: attachment)",
        "content": {media: {} for media in _MEDIA_TYPES.values()},
    }
}
_CHUNK = 500


async def build_export[M](
    session: AsyncSession,
    statement: Select[M],
    query: ListQuery,
    sort_columns: Mapping[str, InstrumentedAttribute[Any]],
    id_column: InstrumentedAttribute[UUID],
    outs: Callable[[list[M]], Awaitable[Sequence[Any]]],
    row: RowBuilder,
    available: Sequence[ExportColumn],
    options: ExportOptions,
    locale: Locale,
    *,
    name: str,
    day: date,
) -> tuple[ExportFile, int]:
    """Every row of a list with its filters and sort, as a file (API spec 14)."""
    columns = select_columns(available, options.columns)
    total = (
        await session.execute(select(func.count()).select_from(statement.order_by(None).subquery()))
    ).scalar_one()
    check_row_count(total)
    order = [
        (sort_columns[key].desc() if descending else sort_columns[key].asc()).nulls_last()
        for key, descending in query.sort
    ]
    records = list(
        (await session.execute(statement.order_by(*order, id_column))).unique().scalars()
    )
    rows: list[Mapping[str, Any]] = []
    for start in range(0, len(records), _CHUNK):
        rows.extend(row(item, locale) for item in await outs(records[start : start + _CHUNK]))
    content = render(columns, rows, options.format, locale, sheet=name)
    return ExportFile(content=content, format=options.format, name=name, day=day), total


def reference_name(item: Any, locale: Locale) -> str | None:
    """Name of a reference value (name_en/name_bg) in the export language."""
    if item is None:
        return None
    return str(item.name_bg if locale == "bg" else item.name_en)
