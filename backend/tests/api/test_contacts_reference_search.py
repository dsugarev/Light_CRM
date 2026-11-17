"""Contacts (FR-PARTY-02), reference lists (FR-ADM-02), global search (FR-PARTY-04)."""

from typing import Any
from uuid import uuid4

import httpx

from app.core.principal import RoleCode
from tests.helpers import TestApp


async def org(client: httpx.AsyncClient, name: str = "Акме ЕООД") -> dict[str, Any]:
    response = await client.post("/api/v1/organizations", json={"name": name})
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def contact(client: httpx.AsyncClient, **fields: Any) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/contacts", json={"first_name": "Мария", "last_name": "Иванова", **fields}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


# --- Contacts ---------------------------------------------------------------------------


async def test_FR_PARTY_02_create_contact_linked_to_organization(test_app: TestApp) -> None:
    rep, user = await test_app.signed_in(full_name="Rep One")
    acme = await org(rep)
    body = await contact(
        rep,
        job_title="CTO",
        email="M.Ivanova@Example.TEST",
        phone="+359 2 000 0000",
        preferred_locale="bg",
        organization_id=acme["id"],
    )
    assert body["full_name"] == "Мария Иванова"
    assert body["email"] == "m.ivanova@example.test"
    assert body["organization"] == {"id": acme["id"], "name": "Акме ЕООД"}
    assert body["owner"] == {"id": str(user.id), "full_name": "Rep One"}
    assert await test_app.audit("contact.created")


async def test_FR_PARTY_02_contact_without_organization_is_owned_by_creator(
    test_app: TestApp,
) -> None:
    rep, user = await test_app.signed_in()
    body = await contact(rep)
    assert body["organization"] is None
    assert body["owner"]["id"] == str(user.id)


async def test_contact_validation(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    response = await rep.post(
        "/api/v1/contacts",
        json={"first_name": "", "email": "nope", "preferred_locale": "de", "organization_id": "x"},
    )
    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["errors"]}
    assert fields == {"first_name", "last_name", "email", "preferred_locale", "organization_id"}
    missing_org = await rep.post(
        "/api/v1/contacts",
        json={"first_name": "A", "last_name": "B", "organization_id": str(uuid4())},
    )
    assert missing_org.json()["errors"] == [
        {"field": "organization_id", "code": "organization.not_found"}
    ]


async def test_contact_cannot_join_an_archived_organization(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    acme = await org(rep)
    await rep.delete(f"/api/v1/organizations/{acme['id']}")
    response = await rep.post(
        "/api/v1/contacts",
        json={"first_name": "A", "last_name": "B", "organization_id": acme["id"]},
    )
    assert response.json()["errors"] == [
        {"field": "organization_id", "code": "organization.archived"}
    ]


async def test_duplicate_email_needs_confirmation(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    first = await contact(rep, email="maria@example.test")
    response = await rep.post(
        "/api/v1/contacts",
        json={"first_name": "Maria", "last_name": "Ivanova", "email": "MARIA@example.test"},
    )
    assert response.status_code == 409
    assert (
        response.json()["matches"][0] | {"id": first["id"], "reason": "email"}
        == response.json()["matches"][0]
    )
    confirmed = await rep.post(
        "/api/v1/contacts",
        json={
            "first_name": "Maria",
            "last_name": "Ivanova",
            "email": "maria@example.test",
            "confirm_duplicate": True,
        },
    )
    assert confirmed.status_code == 201


async def test_contact_ownership_follows_the_organization(test_app: TestApp) -> None:
    owner, owner_user = await test_app.signed_in()
    acme = await org(owner)
    other_rep, _ = await test_app.signed_in()
    # Another rep may add a contact to the organisation; it then belongs to the org's owner.
    added = await contact(other_rep, organization_id=acme["id"])
    assert added["owner"]["id"] == str(owner_user.id)
    assert (
        await other_rep.patch(f"/api/v1/contacts/{added['id']}", json={"job_title": "CEO"})
    ).status_code == 403
    updated = await owner.patch(f"/api/v1/contacts/{added['id']}", json={"job_title": "CEO"})
    assert updated.status_code == 200
    [entry] = await test_app.audit("contact.updated")
    assert entry.before is not None
    assert entry.after is not None
    assert (entry.before["job_title"], entry.after["job_title"]) == (None, "CEO")


async def test_FR_PARTY_02_archive_restore_and_owner_filter(test_app: TestApp) -> None:
    rep, rep_user = await test_app.signed_in()
    mine = await contact(rep, last_name="Аз")
    other, _ = await test_app.signed_in()
    await contact(other, last_name="Друг")

    owned = await rep.get("/api/v1/contacts", params={"owner_id": "me"})
    assert [c["last_name"] for c in owned.json()["items"]] == ["Аз"]
    everyone = await rep.get("/api/v1/contacts", params={"sort": "-last_name"})
    assert [c["last_name"] for c in everyone.json()["items"]] == ["Друг", "Аз"]

    assert (await rep.delete(f"/api/v1/contacts/{mine['id']}")).status_code == 204
    assert (await rep.get("/api/v1/contacts", params={"owner_id": str(rep_user.id)})).json()[
        "total"
    ] == 0
    edit = await rep.patch(f"/api/v1/contacts/{mine['id']}", json={"phone": "1"})
    assert edit.json()["code"] == "resource.archived"
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    restored = await manager.post(f"/api/v1/contacts/{mine['id']}/restore")
    assert restored.json()["archived_at"] is None
    assert [e.action for e in await test_app.audit() if e.entity_type == "contact"][-2:] == [
        "contact.archived",
        "contact.restored",
    ]


async def test_contact_search_in_both_scripts(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    await contact(rep, email="maria@example.test", job_title="Финансов директор")
    for q in ("мария", "maria ivanova", "финансов", "example.test"):
        found = await rep.get("/api/v1/contacts", params={"q": q})
        assert found.json()["total"] == 1, q


# --- Reference lists (FR-ADM-02) --------------------------------------------------------


async def test_FR_ADM_02_industries_are_seeded_in_both_languages(test_app: TestApp) -> None:
    viewer, _ = await test_app.signed_in(RoleCode.VIEWER)
    items = (await viewer.get("/api/v1/reference/industries")).json()
    assert len(items) == 14
    assert items[0] | {"code": "telecommunications", "name_bg": "Телекомуникации"} == items[0]
    assert [i["position"] for i in items] == list(range(1, 15))
    assert (await viewer.get("/api/v1/reference/unknown-list")).status_code == 404


async def test_FR_ADM_02_admin_manages_a_list(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    created = await admin.post(
        "/api/v1/reference/industries",
        json={"code": "agriculture", "name_en": "Agriculture", "name_bg": "Земеделие"},
    )
    assert created.status_code == 201
    item = created.json()
    assert item["position"] == 15
    duplicate = await admin.post(
        "/api/v1/reference/industries", json={"code": "agriculture", "name_en": "X", "name_bg": "Х"}
    )
    assert duplicate.status_code == 409
    bad_code = await admin.post(
        "/api/v1/reference/industries", json={"code": "Bad Code", "name_en": "X", "name_bg": "Х"}
    )
    assert bad_code.status_code == 422

    renamed = await admin.patch(
        f"/api/v1/reference/industries/{item['id']}",
        json={"name_en": "Agriculture and food", "is_active": False},
    )
    assert renamed.json()["is_active"] is False
    active = (await admin.get("/api/v1/reference/industries")).json()
    assert item["id"] not in {i["id"] for i in active}
    everything = (
        await admin.get("/api/v1/reference/industries", params={"include_inactive": "true"})
    ).json()
    assert item["id"] in {i["id"] for i in everything}

    order = [i["id"] for i in reversed(everything)]
    reordered = await admin.put("/api/v1/reference/industries/order", json=order)
    assert [i["id"] for i in reordered.json()] == order
    incomplete = await admin.put("/api/v1/reference/industries/order", json=order[:3])
    assert incomplete.status_code == 422

    assert (await admin.delete(f"/api/v1/reference/industries/{item['id']}")).status_code == 204
    actions = [e.action for e in await test_app.audit() if e.action.startswith("reference.")]
    assert actions == [
        "reference.created",
        "reference.updated",
        "reference.reordered",
        "reference.deleted",
    ]


async def test_FR_ADM_02_value_in_use_cannot_be_deleted(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    items = (await admin.get("/api/v1/reference/industries")).json()
    telecom = next(i for i in items if i["code"] == "telecommunications")
    await admin.post(
        "/api/v1/organizations", json={"name": "Телеком", "industry_id": telecom["id"]}
    )
    response = await admin.delete(f"/api/v1/reference/industries/{telecom['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "reference.in_use"


# --- Global search (API spec section 12) -------------------------------------------------


async def test_FR_PARTY_04_global_search_across_types(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    acme = await org(rep, "София Софтуер АД")
    await contact(rep, first_name="Софи", last_name="Петрова", organization_id=acme["id"])
    for i in range(6):
        await org(rep, f"Sofia Company {i}")

    result = (await rep.get("/api/v1/search", params={"q": "sofi"})).json()["items"]
    by_type = {t: [h for h in result if h["type"] == t] for t in ("organization", "contact")}
    assert len(by_type["organization"]) == 5  # capped per type
    assert by_type["contact"] == [
        {
            "type": "contact",
            "id": by_type["contact"][0]["id"],
            "label": "Софи Петрова",
            "detail": "София Софтуер АД",
        }
    ]
    only_contacts = (
        await rep.get("/api/v1/search", params={"q": "sofi", "types": "contact"})
    ).json()
    assert {h["type"] for h in only_contacts["items"]} == {"contact"}
    assert (await rep.get("/api/v1/search", params={"q": "s"})).status_code == 422
