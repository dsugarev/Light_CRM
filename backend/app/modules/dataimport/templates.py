"""Downloadable XLSX templates (FR-IMP-01): headers plus an instructions sheet."""

import io

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.modules.dataimport.fields import FIELDS, EntityType

_SHEETS = {
    "en": ("Data", "Instructions", ("Column", "Required", "Format")),
    "bg": ("Данни", "Указания", ("Колона", "Задължителна", "Формат")),
}
_YES_NO = {"en": ("Yes", "No"), "bg": ("Да", "Не")}


def template(entity: EntityType, locale: str) -> bytes:
    data_name, help_name, help_headers = _SHEETS["bg" if locale == "bg" else "en"]
    yes, no = _YES_NO["bg" if locale == "bg" else "en"]
    workbook = Workbook()
    data = workbook.active
    assert data is not None  # noqa: S101 - a new workbook has one sheet
    data.title = data_name
    data.append([f.header(locale) for f in FIELDS[entity]])
    for cell in data[1]:
        cell.font = Font(bold=True)
    help_sheet = workbook.create_sheet(help_name)
    help_sheet.append(list(help_headers))
    for field in FIELDS[entity]:
        note = field.note_bg if locale == "bg" else field.note_en
        help_sheet.append([field.header(locale), yes if field.required else no, note])
    for sheet in (data, help_sheet):
        for index in range(1, sheet.max_column + 1):
            sheet.column_dimensions[get_column_letter(index)].width = 28
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()
