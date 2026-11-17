"""Import file parsing and mapping suggestions (FR-IMP-01; architecture 7)."""

import io
from datetime import date, datetime

import pytest
from openpyxl import Workbook

from app.core.errors import AppError
from app.modules.dataimport.fields import suggest_mapping
from app.modules.dataimport.parsing import parse


def _xlsx(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_FR_IMP_01_csv_utf8_with_bom_and_commas() -> None:
    content = '﻿Name,City\r\n"Акме, ЕООД",София\r\n'.encode()
    assert parse("a.csv", content) == (["Name", "City"], [{"Name": "Акме, ЕООД", "City": "София"}])


def test_FR_IMP_01_csv_windows_1251_and_semicolons() -> None:
    content = "Име;Град\r\nБета АД;Варна\r\n".encode("cp1251")
    assert parse("a.csv", content) == (["Име", "Град"], [{"Име": "Бета АД", "Град": "Варна"}])


def test_FR_IMP_01_xlsx_values_are_text_and_formulas_are_not_run() -> None:
    content = _xlsx(
        [
            ["Name", "Amount", "Close", "Name", None],
            ["A", 1000.0, datetime(2027, 3, 31), "dup", None],  # noqa: DTZ001 - Excel dates are naive
            ["=1+1", 12.5, date(2027, 4, 1), "", None],
            [None, None, None, None, None],
        ]
    )
    headers, rows = parse("a.xlsx", content)
    assert headers == ["Name", "Amount", "Close", "Name (4)"]
    assert rows[0] == {"Name": "A", "Amount": "1000", "Close": "2027-03-31", "Name (4)": "dup"}
    # A formula is stored as text without a computed value; it is never evaluated.
    assert rows[1]["Name"] in ("=1+1", "")
    assert rows[1]["Amount"] == "12.5"
    assert len(rows) == 2


@pytest.mark.parametrize(
    ("name", "content"),
    [("a.txt", b"x"), ("a.xlsx", b"not a zip"), ("a.csv", b""), ("a.csv", b",,\r\n1,2\r\n")],
)
def test_FR_IMP_01_unreadable_files(name: str, content: bytes) -> None:
    with pytest.raises(AppError) as raised:
        parse(name, content)
    assert raised.value.code == "import.invalid_file"


def test_FR_IMP_01_mapping_suggestion_by_key_and_both_languages() -> None:
    assert suggest_mapping(
        "opportunities", ["name", "Организация", "AMOUNT (EUR)", "Етап", "Extra", "Име"]
    ) == {
        "name": "name",
        "Организация": "organization",
        "AMOUNT (EUR)": "amount",
        "Етап": "stage",
        "Extra": None,
        "Име": None,  # "name" is already mapped
    }
