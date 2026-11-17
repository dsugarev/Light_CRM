"""Organisations (FR-PARTY-01, 03, 04; API spec section 7). Fictional companies only."""

from typing import Any
from uuid import uuid4

import httpx

from app.core.principal import RoleCode
from tests.helpers import TestApp

ACME = {"name": "Акме ЕООД", "registration_number": "123456786", "city": "София"}


async def create_org(client: httpx.AsyncClient, **fields: Any) -> dict[str, Any]:
    response = await client.post("/api/v1/organizations", json={**ACME, **fields})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def industry_id(client: httpx.AsyncClient, code: str = "telecommunications") -> str:
    items: list[dict[str, str]] = (await client.get("/api/v1/reference/industries")).json()
    return next(i["id"] for i in items if i["code"] == code)


# --- Create and read ------------------------------------------------------------------------


async def test_FR_PARTY_01_create_with_all_fields(test_app: TestApp) -> None:
    rep, user = await test_app.signed_in(RoleCode.SALES_REP, full_name="Rep One")
    telecom = await industry_id(rep)
    response = await rep.post(
        "/api/v1/organizations",
        json={
            "name": "Сиела Нет ООД",
            "registration_number": "1234567860001",
            "vat_number": "bg 123456786",
            "industry_id": telecom,
            "size_band": "50-249",
            "website": "https://siela.example",
            "address_line": "бул. Витоша 1",
            "postal_code": "1000",
            "city": "София",
            "country": "bg",
            "notes": "Met at the fair",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"/api/v1/organizations/{body['id']}"
    assert body["vat_number"] == "BG123456786"
    assert body["country"] == "BG"
    assert body["owner"] == {"id": str(user.id), "full_name": "Rep One"}
    assert body["created_by"] == {"id": str(user.id), "full_name": "Rep One"}
    assert body["industry"]["code"] == "telecommunications"
    assert body["industry"]["name_bg"] == "Телекомуникации"
    assert body["warnings"] == []
    [entry] = await test_app.audit("organization.created")
    assert entry.after is not None
    assert entry.after["name"] == "Сиела Нет ООД"


async def test_FR_PARTY_01_validation(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    response = await rep.post(
        "/api/v1/organizations",
        json={
            "name": "",
            "registration_number": "12345",
            "vat_number": "DE123",
            "website": "siela.example",
            "size_band": "huge",
            "country": "Bulgaria",
            "unknown": 1,
        },
    )
    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["errors"]}
    assert fields == {
        "name", "registration_number", "vat_number", "website", "size_band", "country", "unknown"
    }  # fmt: skip


async def test_FR_PARTY_01_wrong_eik_checksum_is_a_warning(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    body = await create_org(rep, registration_number="123456789")
    assert body["warnings"] == [
        {"field": "registration_number", "code": "organization.registration_checksum"}
    ]


async def test_inactive_or_unknown_industry_is_rejected(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    media = await industry_id(admin, "media")
    await admin.patch(f"/api/v1/reference/industries/{media}", json={"is_active": False})
    for bad in (media, str(uuid4())):
        response = await admin.post("/api/v1/organizations", json={**ACME, "industry_id": bad})
        assert response.status_code == 422
        assert response.json()["errors"] == [{"field": "industry_id", "code": "reference.invalid"}]


async def test_FR_PARTY_03_detail_with_counts(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    for name in ("Мария", "Петър"):
        await rep.post(
            "/api/v1/contacts",
            json={"first_name": name, "last_name": "Тестова", "organization_id": org["id"]},
        )
    detail = (await rep.get(f"/api/v1/organizations/{org['id']}")).json()
    assert detail["counts"] == {
        "contacts": 2,
        "open_leads": 0,
        "open_opportunities": 0,
        "open_pipeline_value": "0.00",
        "currency": "EUR",
    }
    contacts = (await rep.get(f"/api/v1/organizations/{org['id']}/contacts")).json()
    assert [c["first_name"] for c in contacts["items"]] == ["Мария", "Петър"]
    assert (await rep.get(f"/api/v1/organizations/{uuid4()}")).status_code == 404
    assert (await rep.get(f"/api/v1/organizations/{uuid4()}/contacts")).status_code == 404


# --- Duplicates (FR-PARTY-01 AC1) --------------------------------------------------------


async def test_FR_PARTY_01_AC1_duplicate_name_across_scripts_is_flagged(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    existing = await create_org(rep, registration_number=None)
    response = await rep.post("/api/v1/organizations", json={"name": "ACME e.o.o.d."})
    assert response.status_code == 409
    assert response.json()["code"] == "conflict.duplicate"
    [match] = response.json()["matches"]
    assert match["id"] == existing["id"]
    assert match["reason"] == "name"

    confirmed = await rep.post(
        "/api/v1/organizations", json={"name": "ACME e.o.o.d.", "confirm_duplicate": True}
    )
    assert confirmed.status_code == 201


async def test_FR_PARTY_01_AC1_duplicate_registration_number_is_flagged(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    await create_org(rep)
    response = await rep.post(
        "/api/v1/organizations", json={"name": "Different name", "registration_number": "123456786"}
    )
    assert response.status_code == 409
    assert response.json()["matches"][0]["reason"] == "registration_number"


async def test_FR_PARTY_01_AC1_duplicate_check_endpoint_includes_similar_names(
    test_app: TestApp,
) -> None:
    rep, _ = await test_app.signed_in()
    await create_org(rep, name="Телекомуникационни Системи АД", registration_number=None)
    await create_org(rep, name="Archived Co", registration_number="000000000")
    archived = (await rep.get("/api/v1/organizations", params={"q": "Archived"})).json()["items"][0]
    await rep.delete(f"/api/v1/organizations/{archived['id']}")

    similar = await rep.get(
        "/api/v1/organizations/duplicate-check", params={"name": "Telekomunikatsionni Sistemi"}
    )
    assert [(m["name"], m["reason"]) for m in similar.json()["matches"]] == [
        ("Телекомуникационни Системи АД", "name")
    ]
    near = await rep.get(
        "/api/v1/organizations/duplicate-check", params={"name": "Телекомуникационни Систем"}
    )
    assert near.json()["matches"][0]["reason"] == "similar_name"
    by_number = await rep.get(
        "/api/v1/organizations/duplicate-check", params={"registration_number": "000 000 000"}
    )
    assert by_number.json()["matches"][0]["archived"] is True
    nothing = await rep.get("/api/v1/organizations/duplicate-check", params={"name": "Zzz Unique"})
    assert nothing.json() == {"matches": []}


async def test_renaming_into_a_duplicate_needs_confirmation(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    await create_org(rep)
    other = await create_org(rep, name="Other", registration_number=None)
    response = await rep.patch(f"/api/v1/organizations/{other['id']}", json={"name": "Acme"})
    assert response.status_code == 409
    confirmed = await rep.patch(
        f"/api/v1/organizations/{other['id']}", json={"name": "Acme", "confirm_duplicate": True}
    )
    assert confirmed.status_code == 200


# --- Update, ownership, archive (FR-PARTY-01, FR-AUTH-05) ---------------------------------


async def test_FR_PARTY_01_update_is_audited_with_before_and_after(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    response = await rep.patch(
        f"/api/v1/organizations/{org['id']}", json={"city": "Пловдив", "website": None}
    )
    assert response.status_code == 200
    assert response.json()["city"] == "Пловдив"
    [entry] = await test_app.audit("organization.updated")
    assert entry.before is not None
    assert entry.after is not None
    assert (entry.before["city"], entry.after["city"]) == ("София", "Пловдив")
    found = await rep.get("/api/v1/organizations", params={"q": "plovdiv"})
    assert found.json()["total"] == 1


async def test_FR_AUTH_05_AC1_rep_cannot_edit_another_reps_organization(test_app: TestApp) -> None:
    owner, _ = await test_app.signed_in()
    org = await create_org(owner)
    other_rep, _ = await test_app.signed_in()
    for response in (
        await other_rep.patch(f"/api/v1/organizations/{org['id']}", json={"city": "Варна"}),
        await other_rep.delete(f"/api/v1/organizations/{org['id']}"),
    ):
        assert response.status_code == 403
        assert response.json()["code"] == "permission.denied"
    # Reading is open to everyone (assumption A1).
    assert (await other_rep.get(f"/api/v1/organizations/{org['id']}")).status_code == 200


async def test_FR_AUTH_05_AC2_viewer_cannot_change_organizations(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    viewer, _ = await test_app.signed_in(RoleCode.VIEWER)
    assert (await viewer.post("/api/v1/organizations", json=ACME)).status_code == 403
    assert (
        await viewer.patch(f"/api/v1/organizations/{org['id']}", json={"city": "Русе"})
    ).status_code == 403


async def test_manager_edits_any_organization_and_changes_owner(test_app: TestApp) -> None:
    rep, rep_user = await test_app.signed_in()
    org = await create_org(rep)
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    new_owner = await test_app.create_user(full_name="New Owner")
    response = await manager.patch(
        f"/api/v1/organizations/{org['id']}", json={"owner_id": str(new_owner.id)}
    )
    assert response.status_code == 200
    assert response.json()["owner"] == {"id": str(new_owner.id), "full_name": "New Owner"}
    [entry] = await test_app.audit("organization.owner_changed")
    assert entry.before is not None
    assert entry.before["owner_id"] == str(rep_user.id)
    # The former owner (a rep) can no longer edit it.
    assert (
        await rep.patch(f"/api/v1/organizations/{org['id']}", json={"city": "Бургас"})
    ).status_code == 403


async def test_rep_cannot_give_an_organization_to_someone_else(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    colleague = await test_app.create_user()
    create = await rep.post("/api/v1/organizations", json={**ACME, "owner_id": str(colleague.id)})
    assert create.status_code == 403
    org = await create_org(rep)
    change = await rep.patch(
        f"/api/v1/organizations/{org['id']}", json={"owner_id": str(colleague.id)}
    )
    assert change.status_code == 403


async def test_owner_must_be_an_active_person(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    inactive = await test_app.create_user(is_active=False)
    service_user = await test_app.create_user(RoleCode.INTEGRATION, user_type="service")
    for owner in (inactive.id, service_user.id, uuid4()):
        response = await admin.post("/api/v1/organizations", json={**ACME, "owner_id": str(owner)})
        assert response.status_code == 422
        assert response.json()["errors"] == [{"field": "owner_id", "code": "owner.invalid"}]


async def test_FR_PARTY_01_archive_and_restore(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    assert (await rep.delete(f"/api/v1/organizations/{org['id']}")).status_code == 204
    assert (await rep.get("/api/v1/organizations")).json()["total"] == 0
    with_archived = await rep.get("/api/v1/organizations", params={"include_archived": "true"})
    assert with_archived.json()["items"][0]["archived_at"] is not None
    edit = await rep.patch(f"/api/v1/organizations/{org['id']}", json={"city": "Варна"})
    assert edit.status_code == 409
    assert edit.json()["code"] == "resource.archived"

    assert (await rep.post(f"/api/v1/organizations/{org['id']}/restore")).status_code == 403
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    restored = await manager.post(f"/api/v1/organizations/{org['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    actions = [e.action for e in await test_app.audit() if e.entity_type == "organization"]
    assert actions == ["organization.created", "organization.archived", "organization.restored"]


# --- List, filter, sort, search (FR-PARTY-04) ---------------------------------------------


async def test_FR_PARTY_04_search_by_name_number_and_across_scripts(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    await create_org(rep, name="Глобал Телеком ЕАД", registration_number="000000000", city="Варна")
    await create_org(rep, name="Sofia Logistics OOD", registration_number=None, city="Sofia")

    async def names(q: str) -> list[str]:
        items = (await rep.get("/api/v1/organizations", params={"q": q})).json()["items"]
        return [o["name"] for o in items]

    assert await names("глобал") == ["Глобал Телеком ЕАД"]
    assert await names("global telekom") == ["Глобал Телеком ЕАД"]
    assert await names("софия") == ["Sofia Logistics OOD"]
    assert await names("000000") == ["Глобал Телеком ЕАД"]
    assert await names("varna") == ["Глобал Телеком ЕАД"]
    assert await names("100%") == []


async def test_FR_PARTY_04_filters_sorting_and_paging(test_app: TestApp) -> None:
    rep, rep_user = await test_app.signed_in()
    other, _ = await test_app.signed_in()
    telecom = await industry_id(rep)
    await create_org(rep, name="Beta", registration_number=None, city="Varna", industry_id=telecom)
    await create_org(rep, name="Alpha", registration_number=None, city="Sofia", size_band="1-9")
    await create_org(other, name="Gamma", registration_number=None, city="sofia")

    async def names(**params: Any) -> list[str]:
        response = await rep.get("/api/v1/organizations", params=params)
        assert response.status_code == 200, response.text
        return [o["name"] for o in response.json()["items"]]

    assert await names() == ["Alpha", "Beta", "Gamma"]
    assert await names(sort="-name") == ["Gamma", "Beta", "Alpha"]
    assert await names(owner_id="me") == ["Alpha", "Beta"]
    assert await names(owner_id=str(rep_user.id), city="SOFIA") == ["Alpha"]
    assert await names(industry_id=telecom) == ["Beta"]
    assert await names(size_band="1-9") == ["Alpha"]
    assert await names(city=["Varna", "Sofia"]) == ["Alpha", "Beta", "Gamma"]
    page = (await rep.get("/api/v1/organizations", params={"page": 2, "page_size": 2})).json()
    assert (page["total"], page["page"], [o["name"] for o in page["items"]]) == (3, 2, ["Gamma"])


async def test_unknown_sort_or_filter_is_400(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    sort = await rep.get("/api/v1/organizations", params={"sort": "password"})
    assert sort.status_code == 400
    assert sort.json()["errors"] == [{"field": "sort", "code": "validation.unknown_sort"}]
    unknown = await rep.get("/api/v1/organizations", params={"colour": "red"})
    assert unknown.status_code == 400
    assert unknown.json()["errors"] == [{"field": "colour", "code": "validation.unknown_filter"}]
    big = await rep.get("/api/v1/organizations", params={"page_size": 101})
    assert big.status_code == 400
    bad_owner = await rep.get("/api/v1/organizations", params={"owner_id": "nobody"})
    assert bad_owner.status_code == 400
