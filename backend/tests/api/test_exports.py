"""List exports to XLSX and CSV (FR-REP-02; API spec 14). Fictional data only."""

import csv
import io
from typing import Any

import httpx
import pytest
from openpyxl import load_workbook

from app.core import export
from app.core.principal import RoleCode
from tests.api.test_opportunities import act, create_opp, create_org, loss_reason
from tests.helpers import TestApp

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def sheet_rows(response: httpx.Response) -> list[list[Any]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == XLSX
    workbook = load_workbook(io.BytesIO(response.content), read_only=True)
    return [list(row) for row in workbook.active.iter_rows(values_only=True)]  # type: ignore[union-attr]


def csv_rows(response: httpx.Response) -> list[list[str]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.content.startswith("﻿".encode())  # BOM for Excel
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


async def test_FR_REP_02_organizations_xlsx_with_filters_and_audit(test_app: TestApp) -> None:
    rep, user = await test_app.signed_in()
    await create_org(rep, "Акме ЕООД")
    await create_org(rep, "Бета АД")
    await create_org(rep, '=HYPERLINK("http://evil.example")')
    response = await rep.get("/api/v1/organizations/export?q=акме")
    assert response.headers["content-disposition"] == (
        'attachment; filename="organizations-2026-11-17.xlsx"'
    )
    rows = sheet_rows(response)
    assert rows[0][:3] == ["Name", "Registration number (EIK)", "VAT number"]
    assert [r[0] for r in rows[1:]] == ["Акме ЕООД"]
    [entry] = await test_app.audit("organization.exported")
    assert entry.actor_id == user.id
    assert entry.details == {
        "format": "xlsx",
        "rows": 1,
        "columns": None,
        "filters": {"q": "акме"},
    }
    # Formula injection (architecture 7): text that would run as a formula is neutralized.
    rows = sheet_rows(await rep.get("/api/v1/organizations/export?sort=name"))
    assert '\'=HYPERLINK("http://evil.example")' in [r[0] for r in rows[1:]]


async def test_FR_REP_02_leads_csv_in_bulgarian_with_chosen_columns(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    await rep.post(
        "/api/v1/leads",
        json={"title": "Оптика", "company_name": "Гама ООД", "phone": "+359 2 000 0000"},
    )
    response = await rep.get(
        "/api/v1/leads/export?format=csv&locale=bg&columns=title,status,phone,estimated_value"
    )
    rows = csv_rows(response)
    assert rows == [
        ["Заглавие", "Състояние", "Телефон", "Очаквана стойност (EUR)"],
        ["Оптика", "Нов", "'+359 2 000 0000", ""],
    ]
    unknown = await rep.get("/api/v1/leads/export?columns=title,salary")
    assert unknown.status_code == 400
    assert unknown.json()["errors"] == [{"field": "columns", "code": "export.unknown_column"}]


async def test_FR_REP_02_export_defaults_to_the_users_language(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in(locale="bg")
    await create_org(rep)
    rows = sheet_rows(await rep.get("/api/v1/organizations/export"))
    assert rows[0][0] == "Име"


async def test_FR_REP_02_opportunities_and_activities(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    opp = await create_opp(rep, org, name="Deal", amount="1000.50")
    await act(rep, opp, "close", outcome="lost", loss_reason_id=await loss_reason(rep))
    rows = sheet_rows(
        await rep.get(
            "/api/v1/opportunities/export?locale=bg"
            "&columns=name,organization,stage,amount,probability,loss_reason,is_stale"
        )
    )
    assert rows == [
        ["Възможност", "Организация", "Етап", "Сума (EUR)", "Вероятност (%)",
         "Причина за загуба", "Изисква внимание"],
        ["Deal", "Акме ЕООД", "Загубена", 1000.5, 0, "Цена", "Не"],
    ]  # fmt: skip
    await rep.post(
        "/api/v1/activities",
        json={"type": "call", "subject": "Follow-up", "organization_id": org["id"]},
    )
    rows = sheet_rows(await rep.get("/api/v1/activities/export?columns=type,subject,organization"))
    assert rows == [["Type", "Subject", "Organization"], ["Call", "Follow-up", "Акме ЕООД"]]


async def test_FR_REP_02_contacts_and_audit_log(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    await admin.post("/api/v1/contacts", json={"first_name": "Мария", "last_name": "Иванова"})
    rows = csv_rows(
        await admin.get("/api/v1/contacts/export?format=csv&columns=first_name,last_name")
    )
    assert rows == [["First name", "Last name"], ["Мария", "Иванова"]]
    rows = csv_rows(
        await admin.get("/api/v1/audit-log/export?format=csv&action=contact.created&columns=action")
    )
    assert rows == [["Action"], ["contact.created"]]
    assert len(await test_app.audit("audit_log.exported")) == 1


async def test_FR_REP_02_row_cap(test_app: TestApp, monkeypatch: pytest.MonkeyPatch) -> None:
    rep, _ = await test_app.signed_in()
    await create_org(rep, "Едно")
    await create_org(rep, "Две")
    monkeypatch.setattr(export, "EXPORT_ROW_CAP", 1)
    response = await rep.get("/api/v1/organizations/export")
    assert response.status_code == 422
    assert response.json()["code"] == "export.too_many_rows"
    assert response.json()["limit"] == 1
    assert await test_app.audit("organization.exported") == []


def test_neutralize_formula_prefixes() -> None:
    for text in ("=1+1", "+359", "-2", "@SUM(A1)", "\tx", "\rx"):
        assert export.neutralize(text) == f"'{text}"
    assert export.neutralize("Acme =") == "Acme ="
