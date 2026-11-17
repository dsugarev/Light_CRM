"""Import from XLSX and CSV (FR-IMP-01; API spec 15). Fictional data only."""

import io
from datetime import timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from openpyxl import Workbook, load_workbook
from sqlalchemy import select

from app.core.principal import RoleCode
from app.modules.dataimport import parsing
from app.modules.dataimport import service as dataimport
from app.modules.party.models import Organization
from app.modules.sales.models import Opportunity
from tests.api.test_opportunities import create_org
from tests.helpers import TestApp

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def xlsx(rows: list[list[Any]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


async def upload(
    client: httpx.AsyncClient, entity: str, content: bytes, name: str = "data.xlsx"
) -> httpx.Response:
    return await client.post(
        "/api/v1/imports",
        data={"entity_type": entity},
        files={"file": (name, content, XLSX if name.endswith(".xlsx") else "text/csv")},
    )


async def run(
    client: httpx.AsyncClient,
    entity: str,
    content: bytes,
    *,
    name: str = "data.xlsx",
    duplicates: str = "skip",
    mapping: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Upload, map (suggested unless given) and validate; returns the validated batch."""
    response = await upload(client, entity, content, name)
    assert response.status_code == 201, response.text
    batch = response.json()
    response = await client.put(
        f"/api/v1/imports/{batch['id']}/mapping",
        json={"mapping": mapping or batch["mapping"], "duplicates": duplicates},
    )
    assert response.status_code == 200, response.text
    response = await client.post(f"/api/v1/imports/{batch['id']}/validate")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def rows(client: httpx.AsyncClient, batch: dict[str, Any], query: str = "") -> list[Any]:
    response = await client.get(f"/api/v1/imports/{batch['id']}/rows{query}")
    assert response.status_code == 200, response.text
    items: list[Any] = response.json()["items"]
    return items


# --- Templates, upload and mapping --------------------------------------------------------------


async def test_FR_IMP_01_templates_in_both_languages(test_app: TestApp) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    response = await manager.get("/api/v1/imports/templates/opportunities?locale=bg")
    assert response.status_code == 200
    assert response.headers["content-type"] == XLSX
    workbook = load_workbook(io.BytesIO(response.content), read_only=True)
    assert workbook.sheetnames == ["Данни", "Указания"]
    header = next(workbook["Данни"].iter_rows(values_only=True))
    assert header[:3] == ("Име", "Организация", "Етап")
    help_rows = list(workbook["Указания"].iter_rows(values_only=True))
    assert help_rows[0] == ("Колона", "Задължителна", "Формат")
    assert help_rows[2][:2] == ("Организация", "Да")
    english = await manager.get("/api/v1/imports/templates/contacts")
    header = next(load_workbook(io.BytesIO(english.content)).active.iter_rows(values_only=True))  # type: ignore[union-attr]
    assert header[:2] == ("First name", "Last name")


async def test_FR_IMP_01_AC1_csv_upload_detects_encoding_delimiter_and_mapping(
    test_app: TestApp,
) -> None:
    manager, user = await test_app.signed_in(RoleCode.SALES_MANAGER)
    content = "Име;Град;Колона без поле\r\nАкме ЕООД;София;x\r\n;;\r\nБета АД;Варна;y\r\n".encode(
        "cp1251"
    )
    response = await upload(manager, "organizations", content, "орг.csv")
    assert response.status_code == 201, response.text
    batch = response.json()
    assert response.headers["location"] == f"/api/v1/imports/{batch['id']}"
    assert batch["status"] == "uploaded"
    assert batch["columns"] == ["Име", "Град", "Колона без поле"]
    assert batch["mapping"] == {"Име": "name", "Град": "city", "Колона без поле": None}
    assert batch["counts"]["rows"] == 2  # the blank line is not a row
    assert batch["created_by"]["id"] == str(user.id)
    assert batch["expires_at"] == "2026-11-24T09:00:00Z"
    assert {"key": "name", "name_en": "Name", "name_bg": "Име", "required": True} in batch["fields"]
    [entry] = await test_app.audit("import.uploaded")
    assert entry.details is not None
    assert entry.details["rows"] == 2


async def test_FR_IMP_01_mapping_rules(test_app: TestApp) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    batch = (await upload(manager, "contacts", xlsx([["A", "B", "C"], ["x", "y", "z"]]))).json()
    path = f"/api/v1/imports/{batch['id']}/mapping"
    response = await manager.put(
        path, json={"mapping": {"A": "first_name", "B": "first_name", "C": "salary", "Z": None}}
    )
    assert response.status_code == 422
    assert {(e["field"], e["code"]) for e in response.json()["errors"]} == {
        ("mapping.B", "import.field_mapped_twice"),
        ("mapping.C", "import.unknown_field"),
        ("mapping.Z", "import.unknown_column"),
        ("field.last_name", "import.required_field"),
    }
    early = await manager.post(f"/api/v1/imports/{batch['id']}/validate")
    assert (early.status_code, early.json()["code"]) == (409, "import.invalid_state")


async def test_FR_IMP_01_file_checks(test_app: TestApp, monkeypatch: pytest.MonkeyPatch) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    response = await upload(manager, "leads", b"hello", "notes.txt")
    assert (response.status_code, response.json()["code"]) == (415, "import.invalid_file")
    response = await upload(manager, "leads", b"not really a workbook", "broken.xlsx")
    assert response.json()["code"] == "import.invalid_file"
    monkeypatch.setattr(parsing, "MAX_FILE_BYTES", 10)
    response = await upload(manager, "leads", b"Title,Company\r\nA,B\r\n", "big.csv")
    assert (response.status_code, response.json()["code"]) == (413, "import.too_large")
    monkeypatch.setattr(parsing, "MAX_FILE_BYTES", 10 * 1024 * 1024)
    monkeypatch.setattr(parsing, "MAX_ROWS", 1)
    response = await upload(manager, "leads", b"Title,Company\r\nA,B\r\nC,D\r\n", "rows.csv")
    assert response.json()["code"] == "import.too_large"
    assert response.json()["max_rows"] == 1
    bad_type = await manager.post(
        "/api/v1/imports", data={"entity_type": "invoices"}, files={"file": ("a.csv", b"x")}
    )
    assert bad_type.status_code == 422


# --- Organizations: validation, duplicates, commit, rollback ------------------------------------


ORGANIZATIONS = [
    ["Name", "Registration number (EIK)", "Industry", "City", "Size"],
    ["Нова Фирма ООД", "121212126", "Telecommunications", "Пловдив", "10-49"],
    ["ACME e.o.o.d.", "", "Финанси и банково дело", "Варна", ""],  # duplicate of Акме ЕООД
    ["Грешна ЕООД", "12345", "", "", ""],  # registration number too short
    ["Неизвестна ЕООД", "", "Space travel", "", ""],  # unknown industry
    ["Нова Фирма ООД", "121212126", "", "", ""],  # repeats row 2
    ["Втора ЕООД", "", "", "Русе", "huge"],  # invalid size band
]


async def test_FR_IMP_01_AC1_AC3_validation_preview_with_reasons(test_app: TestApp) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    existing = await create_org(manager, "Акме ЕООД")
    batch = await run(manager, "organizations", xlsx(ORGANIZATIONS))
    assert batch["status"] == "validated"
    assert (batch["counts"]["valid"], batch["counts"]["invalid"], batch["counts"]["duplicate"]) == (
        1,
        4,
        1,
    )
    invalid = await rows(manager, batch, "?outcome=invalid")
    assert {r["row_number"]: [(e["field"], e["code"]) for e in r["errors"]] for r in invalid} == {
        4: [("registration_number", "validation.value_error")],
        5: [("industry", "reference.invalid")],
        6: [("row", "import.duplicate_in_file")],
        7: [("size_band", "validation.literal_error")],
    }
    [duplicate] = await rows(manager, batch, "?outcome=duplicate")
    assert duplicate["row_number"] == 3
    assert duplicate["match"] == {"id": existing["id"], "name": "Акме ЕООД"}
    assert duplicate["values"]["city"] == "Варна"
    async with test_app.sessions() as session:
        assert len(list((await session.execute(select(Organization))).scalars())) == 1


async def test_FR_IMP_01_AC2_strict_commit_writes_nothing_while_rows_are_invalid(
    test_app: TestApp,
) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    batch = await run(manager, "organizations", xlsx(ORGANIZATIONS))
    response = await manager.post(f"/api/v1/imports/{batch['id']}/commit", json={"mode": "strict"})
    assert (response.status_code, response.json()["code"]) == (409, "import.has_errors")
    assert response.json()["invalid"] == 4
    async with test_app.sessions() as session:
        assert list((await session.execute(select(Organization))).scalars()) == []


async def test_FR_IMP_01_AC2_AC3_AC4_commit_update_duplicates_and_roll_back(
    test_app: TestApp,
) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    existing = await create_org(manager, "Акме ЕООД")
    batch = await run(manager, "organizations", xlsx(ORGANIZATIONS), duplicates="update")
    response = await manager.post(
        f"/api/v1/imports/{batch['id']}/commit", json={"mode": "skip_invalid"}
    )
    assert response.status_code == 200, response.text
    committed = response.json()
    assert committed["status"] == "committed"
    assert (committed["counts"]["created"], committed["counts"]["updated"],
            committed["counts"]["skipped"]) == (1, 1, 4)  # fmt: skip
    async with test_app.sessions() as session:
        orgs = {o.name: o for o in (await session.execute(select(Organization))).scalars()}
    assert orgs["Нова Фирма ООД"].import_batch_id == UUID(batch["id"])  # AC4 tag
    assert orgs["Нова Фирма ООД"].city == "Пловдив"
    assert orgs["Акме ЕООД"].city == "Варна"  # duplicate updated (AC3)
    assert orgs["Акме ЕООД"].import_batch_id is None  # updated, not created by the batch
    done = await rows(manager, batch)
    assert {r["row_number"]: r["action"] for r in done} == {
        2: "created", 3: "updated", 4: "skipped", 5: "skipped", 6: "skipped", 7: "skipped",
    }  # fmt: skip
    assert all(v is None for v in done[0]["values"].values())  # uploaded contents dropped
    assert len(await test_app.audit("organization.created")) == 2  # existing + imported
    assert len(await test_app.audit("import.committed")) == 1
    again = await manager.post(f"/api/v1/imports/{batch['id']}/commit", json={"mode": "strict"})
    assert again.json()["code"] == "import.invalid_state"
    assert (await manager.delete(f"/api/v1/imports/{batch['id']}")).status_code == 409

    # Rollback (Admin only): the created one is archived, the update reverted.
    assert (await manager.post(f"/api/v1/imports/{batch['id']}/rollback")).status_code == 403
    response = await admin.post(f"/api/v1/imports/{batch['id']}/rollback")
    assert response.status_code == 200, response.text
    report = response.json()
    assert (report["archived"], report["reverted"], report["kept"]) == (1, 1, [])
    assert report["batch"]["status"] == "rolled_back"
    async with test_app.sessions() as session:
        orgs = {o.name: o for o in (await session.execute(select(Organization))).scalars()}
    assert orgs["Нова Фирма ООД"].archived_at is not None
    assert orgs["Акме ЕООД"].city is None
    assert (await admin.get(f"/api/v1/organizations/{existing['id']}")).json()["city"] is None
    assert len(await test_app.audit("import.rolled_back")) == 1


async def test_FR_IMP_01_AC4_rollback_keeps_records_changed_since_import(
    test_app: TestApp,
) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    content = xlsx([["Name"], ["Първа ЕООД"], ["Втора ЕООД"]])
    batch = await run(admin, "organizations", content)
    await admin.post(f"/api/v1/imports/{batch['id']}/commit", json={"mode": "strict"})
    async with test_app.sessions() as session:
        second = (
            await session.execute(select(Organization).where(Organization.name == "Втора ЕООД"))
        ).scalar_one()
    test_app.clock.advance(timedelta(minutes=5))
    await admin.patch(f"/api/v1/organizations/{second.id}", json={"city": "Бургас"})
    report = (await admin.post(f"/api/v1/imports/{batch['id']}/rollback")).json()
    assert report["archived"] == 1
    [kept] = report["kept"]
    assert (kept["row_number"], kept["rollback_result"]) == (3, "changed_since_import")
    assert kept["record_id"] == str(second.id)


async def test_FR_IMP_01_AC2_commit_is_all_or_nothing_when_a_row_fails_late(
    test_app: TestApp,
) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    content = xlsx([["Name", "Industry"], ["Първа ЕООД", "Media"], ["Втора ЕООД", "Education"]])
    batch = await run(admin, "organizations", content)
    # Between validation and commit, an Admin retires a list value the second row uses.
    industries = (await admin.get("/api/v1/reference/industries")).json()
    education = next(i for i in industries if i["code"] == "education")
    await admin.patch(f"/api/v1/reference/industries/{education['id']}", json={"is_active": False})
    response = await admin.post(f"/api/v1/imports/{batch['id']}/commit", json={"mode": "strict"})
    assert (response.status_code, response.json()["code"]) == (409, "import.has_errors")
    assert response.json()["row_number"] == 3
    async with test_app.sessions() as session:
        assert list((await session.execute(select(Organization))).scalars()) == []
    assert (await admin.get(f"/api/v1/imports/{batch['id']}")).json()["status"] == "validated"


# --- Contacts, leads, opportunities ---------------------------------------------------------------


async def test_FR_IMP_01_contacts_link_organizations_and_skip_duplicates(
    test_app: TestApp,
) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    org = await create_org(manager, "Гама ООД")
    await manager.post(
        "/api/v1/contacts",
        json={"first_name": "Петя", "last_name": "Колева", "email": "petya@gama.example"},
    )
    content = xlsx(
        [
            ["First name", "Last name", "Email", "Organization"],
            ["Мария", "Иванова", "maria@gama.example", "gama"],  # transliterated name
            ["Петя", "Колева", "PETYA@gama.example", ""],  # duplicate by email
            ["Иван", "Петров", "", "Няма Такава"],
        ]
    )
    batch = await run(manager, "contacts", content)
    assert (batch["counts"]["valid"], batch["counts"]["duplicate"], batch["counts"]["invalid"]) == (
        1, 1, 1,
    )  # fmt: skip
    [invalid] = await rows(manager, batch, "?outcome=invalid")
    assert invalid["errors"] == [{"field": "organization", "code": "organization.not_found"}]
    await manager.post(f"/api/v1/imports/{batch['id']}/commit", json={"mode": "skip_invalid"})
    contacts = (await manager.get(f"/api/v1/organizations/{org['id']}/contacts")).json()
    assert [c["full_name"] for c in contacts["items"]] == ["Мария Иванова"]


async def test_FR_IMP_01_leads_with_sources_and_owners(test_app: TestApp) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    rep = await test_app.create_user(email="rep.one@example.test")
    content = (
        "Title,Company,Source,Owner email,Estimated value (EUR)\r\n"
        'Fibre,Делта ЕООД,Препоръка,REP.ONE@example.test,"12 500,50"\r\n'
        "Cloud,Ета АД,Unknown source,nobody@example.test,abc\r\n"
    ).encode()
    batch = await run(manager, "leads", content, name="leads.csv")
    [invalid] = await rows(manager, batch, "?outcome=invalid")
    assert {(e["field"], e["code"]) for e in invalid["errors"]} == {
        ("source", "reference.invalid"),
        ("owner", "owner.invalid"),
        ("estimated_value", "validation.decimal_parsing"),
    }
    await manager.post(f"/api/v1/imports/{batch['id']}/commit", json={"mode": "skip_invalid"})
    [lead] = (await manager.get("/api/v1/leads")).json()["items"]
    assert (lead["title"], lead["estimated_value"], lead["owner"]["id"]) == (
        "Fibre",
        "12500.50",
        str(rep.id),
    )
    assert lead["source"]["code"] == "referral"


async def test_FR_IMP_01_opportunities_with_lookups(test_app: TestApp) -> None:
    manager, user = await test_app.signed_in(RoleCode.SALES_MANAGER)
    await manager.post(
        "/api/v1/organizations", json={"name": "Зета ЕАД", "registration_number": "121212126"}
    )
    await create_org(manager, "Тета ООД")
    content = xlsx(
        [
            ["Name", "Organization", "Stage", "Amount (EUR)", "Expected close date"],
            ["Deal A", "121 212 126", "Преговори", "10000,5", "31.03.2027"],
            ["Deal B", "Тета ООД", "", "", "2027-04-30"],
            ["Deal C", "Тета ООД", "Closed Won", "", ""],
            ["Deal D", "", "", "", ""],
        ]
    )
    batch = await run(manager, "opportunities", content)
    invalid = {r["row_number"]: r["errors"] for r in await rows(manager, batch, "?outcome=invalid")}
    assert invalid == {
        4: [{"field": "stage", "code": "stage.not_open"}],
        5: [{"field": "organization", "code": "validation.missing"}],
    }
    await manager.post(f"/api/v1/imports/{batch['id']}/commit", json={"mode": "skip_invalid"})
    items = (await manager.get("/api/v1/opportunities?sort=name")).json()["items"]
    first, second = items
    assert (first["name"], first["stage"]["name_en"], first["amount"],
            first["expected_close_date"], first["probability"]) == (
        "Deal A", "Negotiation", "10000.50", "2027-03-31", 75,
    )  # fmt: skip
    assert (second["stage"]["name_en"], second["owner"]["id"]) == ("Prospecting", str(user.id))
    async with test_app.sessions() as session:
        tagged = (await session.execute(select(Opportunity.import_batch_id))).scalars().all()
    assert set(tagged) == {UUID(batch["id"])}


# --- Discard and housekeeping ---------------------------------------------------------------------


async def test_discard_and_expiry(test_app: TestApp) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    batch = (await upload(manager, "leads", xlsx([["Title", "Company"], ["A", "B"]]))).json()
    assert (await manager.delete(f"/api/v1/imports/{batch['id']}")).status_code == 204
    assert (await manager.get(f"/api/v1/imports/{batch['id']}")).status_code == 404
    assert len(await test_app.audit("import.discarded")) == 1
    old = (await upload(manager, "leads", xlsx([["Title", "Company"], ["A", "B"]]))).json()
    async with test_app.sessions() as session:
        removed = await dataimport.purge_expired(session, test_app.clock.now() + timedelta(days=8))
    assert removed == {"import_batches": 1}
    assert (await manager.get(f"/api/v1/imports/{old['id']}")).status_code == 404
    listing = (await manager.get("/api/v1/imports")).json()
    assert listing["total"] == 0
