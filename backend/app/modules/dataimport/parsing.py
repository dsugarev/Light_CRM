"""Reading uploaded XLSX and CSV files into header + rows (architecture section 7).

Files are parsed in memory and never stored on a served path; formulas are not
evaluated (XLSX cells give their stored value, CSV is plain text). CSV encoding
(UTF-8 with or without BOM, else Windows-1251) and delimiter (comma, semicolon or
tab) are detected.
"""

import csv
import io
import zipfile
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from http import HTTPStatus
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app.core.errors import AppError, ErrorCode

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 20_000
_DELIMITERS = ",;\t"


def _too_large(**extra: Any) -> AppError:
    return AppError(ErrorCode.IMPORT_TOO_LARGE, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, extra=extra)


def _invalid() -> AppError:
    return AppError(ErrorCode.IMPORT_INVALID_FILE, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return (
            value.date().isoformat() if value.time() == datetime.min.time() else value.isoformat()
        )
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value).strip()


def _table(rows: Iterable[Iterable[Any]]) -> tuple[list[str], list[dict[str, str]]]:
    iterator = iter(rows)
    try:
        header_cells = [_text(c) for c in next(iterator)]
    except StopIteration:
        raise _invalid() from None
    while header_cells and not header_cells[-1]:
        header_cells.pop()
    if not any(header_cells):
        raise _invalid()
    headers: list[str] = []
    for index, name in enumerate(header_cells, start=1):
        label = name or f"Column {index}"
        while label in headers:  # repeated headers stay distinguishable
            label = f"{label} ({index})"
        headers.append(label)
    data: list[dict[str, str]] = []
    for cells in iterator:
        values = [_text(c) for c in cells][: len(headers)]
        if not any(values):
            continue  # blank lines are not rows
        if len(data) == MAX_ROWS:
            raise _too_large(max_rows=MAX_ROWS)
        data.append({h: (values[i] if i < len(values) else "") for i, h in enumerate(headers)})
    return headers, data


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1251")


def parse(file_name: str, content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Headers and non-empty rows of the first sheet (XLSX) or the file (CSV)."""
    if len(content) > MAX_FILE_BYTES:
        raise _too_large(max_bytes=MAX_FILE_BYTES)
    name = file_name.lower()
    if name.endswith(".xlsx"):
        try:
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except InvalidFileException, zipfile.BadZipFile, KeyError, ValueError, OSError:
            raise _invalid() from None
        sheet = workbook.worksheets[0]
        try:
            return _table(sheet.iter_rows(values_only=True))
        finally:
            workbook.close()
    if name.endswith(".csv"):
        text = _decode(content)
        sample = text[:4096]
        try:
            dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(sample, _DELIMITERS)
        except csv.Error:
            dialect = csv.excel
        return _table(csv.reader(io.StringIO(text), dialect))
    raise _invalid()
