"""Importable fields per record type (FR-IMP-01; API spec section 15).

Each field has a key (used in mappings and row errors), headers in English and
Bulgarian (the template's columns, also recognized when suggesting a mapping),
whether it is required, and a short format note for the template's instructions.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

EntityType = Literal["organizations", "contacts", "leads", "opportunities"]


@dataclass(frozen=True, slots=True)
class ImportField:
    key: str
    en: str
    bg: str
    required: bool = False
    note_en: str = ""
    note_bg: str = ""

    def header(self, locale: str) -> str:
        return self.bg if locale == "bg" else self.en


_OWNER = ImportField(
    "owner", "Owner email", "Имейл на отговорника",
    note_en="Email of an active user; empty: the person importing",
    note_bg="Имейл на активен потребител; празно: импортиращият",
)  # fmt: skip
_ORGANIZATION = ImportField(
    "organization", "Organization", "Организация",
    note_en="Registration number (EIK) or exact name of an existing organization",
    note_bg="ЕИК или точно име на съществуваща организация",
)  # fmt: skip

FIELDS: Mapping[EntityType, Sequence[ImportField]] = {
    "organizations": (
        ImportField("name", "Name", "Име", required=True),
        ImportField("registration_number", "Registration number (EIK)", "ЕИК",
                    note_en="9 or 13 digits", note_bg="9 или 13 цифри"),
        ImportField("vat_number", "VAT number", "ДДС номер",
                    note_en="BG followed by 9 or 10 digits", note_bg="BG и 9 или 10 цифри"),
        ImportField("industry", "Industry", "Отрасъл",
                    note_en="Name or code from the Industries list",
                    note_bg="Име или код от списъка с отрасли"),
        ImportField("size_band", "Size", "Размер", note_en="1-9, 10-49, 50-249 or 250+",
                    note_bg="1-9, 10-49, 50-249 или 250+"),
        ImportField("website", "Website", "Уебсайт", note_en="http(s)://…", note_bg="http(s)://…"),
        ImportField("address_line", "Address", "Адрес"),
        ImportField("postal_code", "Postal code", "Пощенски код"),
        ImportField("city", "City", "Град"),
        ImportField("country", "Country", "Държава", note_en="Two letters, default BG",
                    note_bg="Две букви, по подразбиране BG"),
        _OWNER,
        ImportField("notes", "Notes", "Бележки"),
    ),
    "contacts": (
        ImportField("first_name", "First name", "Име", required=True),
        ImportField("last_name", "Last name", "Фамилия", required=True),
        ImportField("job_title", "Job title", "Длъжност"),
        ImportField("email", "Email", "Имейл", note_en="Duplicates are found by email",
                    note_bg="Дубликатите се откриват по имейл"),
        ImportField("phone", "Phone", "Телефон"),
        _ORGANIZATION,
        ImportField("notes", "Notes", "Бележки"),
    ),
    "leads": (
        ImportField("title", "Title", "Заглавие", required=True),
        ImportField("company_name", "Company", "Фирма", required=True),
        ImportField("contact_name", "Contact person", "Лице за контакт"),
        ImportField("email", "Email", "Имейл"),
        ImportField("phone", "Phone", "Телефон"),
        ImportField("source", "Source", "Източник",
                    note_en="Name or code from the Lead sources list",
                    note_bg="Име или код от списъка с източници"),
        ImportField("estimated_value", "Estimated value (EUR)", "Очаквана стойност (EUR)",
                    note_en="e.g. 48000 or 48000.50", note_bg="напр. 48000 или 48000,50"),
        ImportField("description", "Description", "Описание"),
        _OWNER,
        _ORGANIZATION,
    ),
    "opportunities": (
        ImportField("name", "Name", "Име", required=True),
        ImportField(
            "organization", "Organization", "Организация", required=True,
            note_en=_ORGANIZATION.note_en, note_bg=_ORGANIZATION.note_bg,
        ),
        ImportField("stage", "Stage", "Етап",
                    note_en="Name of an open stage; empty: the first stage",
                    note_bg="Име на отворен етап; празно: първият етап"),
        ImportField("amount", "Amount (EUR)", "Сума (EUR)", note_en="e.g. 48000 or 48000.50",
                    note_bg="напр. 48000 или 48000,50"),
        ImportField("probability", "Probability (%)", "Вероятност (%)",
                    note_en="0-100; empty: the stage default",
                    note_bg="0-100; празно: по подразбиране за етапа"),
        ImportField("expected_close_date", "Expected close date", "Очаквана дата на приключване",
                    note_en="YYYY-MM-DD or DD.MM.YYYY", note_bg="ГГГГ-ММ-ДД или ДД.ММ.ГГГГ"),
        ImportField("next_step", "Next step", "Следваща стъпка"),
        ImportField("competitor", "Competitor", "Конкурент"),
        ImportField("description", "Description", "Описание"),
        _OWNER,
    ),
}  # fmt: skip


def field_keys(entity: EntityType) -> set[str]:
    return {f.key for f in FIELDS[entity]}


def required_keys(entity: EntityType) -> list[str]:
    return [f.key for f in FIELDS[entity] if f.required]


def _normal(text: str) -> str:
    return " ".join(text.casefold().replace("_", " ").split())


def suggest_mapping(entity: EntityType, columns: Sequence[str]) -> dict[str, str | None]:
    """Map each column whose header is a field key or its English or Bulgarian header."""
    names: dict[str, str] = {}
    for field in FIELDS[entity]:
        for label in (field.key, field.en, field.bg):
            names.setdefault(_normal(label), field.key)
    mapping: dict[str, str | None] = {}
    used: set[str] = set()
    for column in columns:
        key = names.get(_normal(column))
        mapping[column] = key if key and key not in used else None
        if key:
            used.add(key)
    return mapping
