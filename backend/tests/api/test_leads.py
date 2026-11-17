"""Leads (FR-LEAD-01..03, 05, 06; API spec section 9). Fictional data only."""

from typing import Any
from uuid import uuid4

import httpx

from app.core.principal import RoleCode
from tests.helpers import TestApp

BANT_COMPLETE = {
    "budget": {"status": "yes", "note": "Approved for 2027"},
    "authority": {"status": "partial", "note": "IT director, CFO signs"},
    "need": {"status": "yes"},
    "timeline": {"status": "no"},
}


async def create_lead(client: httpx.AsyncClient, **fields: Any) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/leads",
        json={"title": "Fibre for 3 branches", "company_name": "Акме ЕООД", **fields},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def act(
    client: httpx.AsyncClient, lead: dict[str, Any], action: str, **body: Any
) -> httpx.Response:
    return await client.post(
        f"/api/v1/leads/{lead['id']}/{action}", json={"version": lead["version"], **body}
    )


async def reference_id(client: httpx.AsyncClient, list_name: str, code: str) -> str:
    items: list[dict[str, str]] = (await client.get(f"/api/v1/reference/{list_name}")).json()
    return next(i["id"] for i in items if i["code"] == code)


# --- FR-LEAD-01 capture ---------------------------------------------------------------------


async def test_FR_LEAD_01_company_name_alone_is_enough(test_app: TestApp) -> None:
    rep, user = await test_app.signed_in(full_name="Rep One")
    lead = await create_lead(rep)
    assert lead["status"] == "new"
    assert lead["owner"] == {"id": str(user.id), "full_name": "Rep One"}
    assert lead["version"] == 1
    assert lead["currency"] == "EUR"
    assert lead["qualification"] == {
        "budget": {"status": "unknown", "note": ""},
        "authority": {"status": "unknown", "note": ""},
        "need": {"status": "unknown", "note": ""},
        "timeline": {"status": "unknown", "note": ""},
        "fits_target_profile": False,
        "score": 0,
    }
    [entry] = await test_app.audit("lead.created")
    assert entry.after is not None
    assert entry.after["status"] == "new"


async def test_FR_LEAD_01_all_fields_bant_score_and_links(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = (await rep.post("/api/v1/organizations", json={"name": "Акме ЕООД"})).json()
    contact = (
        await rep.post(
            "/api/v1/contacts",
            json={"first_name": "Мария", "last_name": "Иванова", "organization_id": org["id"]},
        )
    ).json()
    inbound = await reference_id(rep, "lead-sources", "inbound")
    lead = await create_lead(
        rep,
        contact_name="Мария Иванова",
        email="M.Ivanova@Acme.Example",
        phone="+359 2 000 0000",
        source_id=inbound,
        description="Needs fibre",
        estimated_value="48000.5",
        organization_id=org["id"],
        contact_id=contact["id"],
        qualification={
            "budget": {"status": "yes", "note": "Approved"},
            "authority": {"status": "partial"},
            "need": {"status": "yes"},
            "fits_target_profile": True,
        },
    )
    assert lead["email"] == "m.ivanova@acme.example"
    assert lead["estimated_value"] == "48000.50"
    assert lead["source"]["code"] == "inbound"
    assert lead["source"]["name_bg"] == "Входящо запитване"
    assert lead["organization"] == {"id": org["id"], "name": "Акме ЕООД"}
    assert lead["contact"] == {"id": contact["id"], "name": "Мария Иванова"}
    assert lead["qualification"]["score"] == 63
    assert lead["qualification"]["budget"] == {"status": "yes", "note": "Approved"}
    assert lead["qualification"]["fits_target_profile"] is True


async def test_lead_validation(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    response = await rep.post(
        "/api/v1/leads",
        json={
            "title": "",
            "email": "nope",
            "estimated_value": "-1",
            "qualification": {"budget": {"status": "maybe"}},
            "status": "qualified",
        },
    )
    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["errors"]}
    assert {
        "title",
        "company_name",
        "email",
        "estimated_value",
        "qualification.budget.status",
        "status",
    } <= fields


async def test_lead_links_and_lists_are_validated(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org_a = (await rep.post("/api/v1/organizations", json={"name": "A Org"})).json()
    org_b = (await rep.post("/api/v1/organizations", json={"name": "B Org"})).json()
    contact_b = (
        await rep.post(
            "/api/v1/contacts",
            json={"first_name": "B", "last_name": "B", "organization_id": org_b["id"]},
        )
    ).json()
    cases = [
        ({"organization_id": str(uuid4())}, "organization_id", "organization.not_found"),
        ({"contact_id": str(uuid4())}, "contact_id", "contact.not_found"),
        (
            {"organization_id": org_a["id"], "contact_id": contact_b["id"]},
            "contact_id",
            "contact.organization_mismatch",
        ),
        ({"source_id": str(uuid4())}, "source_id", "reference.invalid"),
    ]
    for extra, field, code in cases:
        response = await rep.post(
            "/api/v1/leads", json={"title": "T", "company_name": "C", **extra}
        )
        assert response.status_code == 422, extra
        assert response.json()["errors"] == [{"field": field, "code": code}]


# --- FR-LEAD-02, 03 lifecycle -----------------------------------------------------------------


async def test_FR_LEAD_02_happy_path_new_contacted_qualified(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    lead = await create_lead(rep)
    contacted = await act(rep, lead, "mark-contacted")
    assert contacted.status_code == 200
    lead = contacted.json()
    assert (lead["status"], lead["version"]) == ("contacted", 2)

    lead = (
        await rep.patch(
            f"/api/v1/leads/{lead['id']}", json={"version": 2, "qualification": BANT_COMPLETE}
        )
    ).json()
    assert lead["qualification"]["score"] == 63
    qualified = await act(rep, lead, "qualify")
    assert qualified.status_code == 200
    assert qualified.json()["status"] == "qualified"
    statuses = [(e.before or {}).get("status") for e in await test_app.audit("lead.status_changed")]
    assert statuses == ["new", "contacted"]


async def test_FR_LEAD_03_AC1_cannot_qualify_with_unknown_bant(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    lead = (await act(rep, await create_lead(rep), "mark-contacted")).json()
    lead = (
        await rep.patch(
            f"/api/v1/leads/{lead['id']}",
            json={
                "version": lead["version"],
                "qualification": {"budget": {"status": "yes"}, "need": {"status": "no"}},
            },
        )
    ).json()
    response = await act(rep, lead, "qualify")
    assert response.status_code == 409
    assert response.json()["code"] == "lead.bant_incomplete"
    assert response.json()["errors"] == [
        {"field": "qualification.authority", "code": "lead.bant_unknown"},
        {"field": "qualification.timeline", "code": "lead.bant_unknown"},
    ]


async def test_FR_LEAD_02_invalid_transitions_are_409(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    lead = await create_lead(rep, qualification=BANT_COMPLETE)
    response = await act(rep, lead, "qualify")  # new -> qualified is not allowed
    assert response.status_code == 409
    assert response.json() | {"code": "lead.invalid_transition", "status": "new"} == response.json()
    contacted = (await act(rep, lead, "mark-contacted")).json()
    again = await act(rep, contacted, "mark-contacted")
    assert again.json()["code"] == "lead.invalid_transition"


async def test_FR_LEAD_02_AC1_disqualify_needs_a_reason_and_makes_the_lead_read_only(
    test_app: TestApp,
) -> None:
    rep, _ = await test_app.signed_in()
    lead = await create_lead(rep)
    no_reason = await act(rep, lead, "disqualify")
    assert no_reason.status_code == 422
    assert no_reason.json()["errors"] == [{"field": "reason_id", "code": "validation.missing"}]
    bad_reason = await act(rep, lead, "disqualify", reason_id=str(uuid4()))
    assert bad_reason.json()["errors"] == [{"field": "reason_id", "code": "reference.invalid"}]

    reason = await reference_id(rep, "disqualification-reasons", "no_budget")
    response = await act(rep, lead, "disqualify", reason_id=reason, note="Frozen budget")
    assert response.status_code == 200
    lead = response.json()
    assert lead["status"] == "disqualified"
    assert lead["disqualification"]["reason"]["code"] == "no_budget"
    assert lead["disqualification"]["note"] == "Frozen budget"
    assert lead["disqualification"]["disqualified_at"] is not None

    edit = await rep.patch(
        f"/api/v1/leads/{lead['id']}", json={"version": lead["version"], "title": "X"}
    )
    assert edit.status_code == 409
    assert edit.json()["code"] == "lead.read_only"


async def test_FR_LEAD_02_AC2_only_managers_reopen(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    lead = await create_lead(rep)
    reason = await reference_id(rep, "disqualification-reasons", "bad_timing")
    lead = (await act(rep, lead, "disqualify", reason_id=reason)).json()
    assert (await act(rep, lead, "reopen")).status_code == 403
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    reopened = await act(manager, lead, "reopen")
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "contacted"
    assert reopened.json()["disqualification"] is None
    # The rep can work it again.
    edit = await rep.patch(
        f"/api/v1/leads/{lead['id']}", json={"version": reopened.json()["version"], "title": "Back"}
    )
    assert edit.status_code == 200


# --- Optimistic concurrency and PATCH rules ------------------------------------------------------


async def test_stale_version_returns_409_with_the_current_lead(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    lead = await create_lead(rep)
    await rep.patch(f"/api/v1/leads/{lead['id']}", json={"version": 1, "title": "First"})
    stale = await rep.patch(f"/api/v1/leads/{lead['id']}", json={"version": 1, "title": "Second"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "conflict.version_mismatch"
    assert stale.json()["current"]["title"] == "First"
    assert stale.json()["current"]["version"] == 2
    stale_action = await act(rep, lead, "mark-contacted")
    assert stale_action.json()["code"] == "conflict.version_mismatch"


async def test_patch_refuses_status_and_owner(test_app: TestApp) -> None:
    rep, user = await test_app.signed_in()
    lead = await create_lead(rep)
    for field, value in (("status", "qualified"), ("owner_id", str(user.id))):
        response = await rep.patch(f"/api/v1/leads/{lead['id']}", json={"version": 1, field: value})
        assert response.status_code == 422
        assert response.json()["code"] == "validation.use_action_endpoint"
        assert response.json()["errors"] == [
            {"field": field, "code": "validation.use_action_endpoint"}
        ]


async def test_patch_needs_a_version(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    lead = await create_lead(rep)
    response = await rep.patch(f"/api/v1/leads/{lead['id']}", json={"title": "No version"})
    assert response.status_code == 422
    assert response.json()["errors"] == [{"field": "version", "code": "validation.missing"}]


async def test_unchanged_patch_keeps_the_version(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    lead = await create_lead(rep)
    response = await rep.patch(
        f"/api/v1/leads/{lead['id']}", json={"version": 1, "title": lead["title"]}
    )
    assert response.json()["version"] == 1
    assert await test_app.audit("lead.updated") == []


# --- Ownership and FR-LEAD-06 assignment ------------------------------------------------------


async def test_FR_AUTH_05_AC1_rep_cannot_change_another_reps_lead(test_app: TestApp) -> None:
    owner, _ = await test_app.signed_in()
    lead = await create_lead(owner)
    other, _ = await test_app.signed_in()
    for response in (
        await other.patch(f"/api/v1/leads/{lead['id']}", json={"version": 1, "title": "Mine now"}),
        await act(other, lead, "mark-contacted"),
        await other.delete(f"/api/v1/leads/{lead['id']}"),
    ):
        assert response.status_code == 403
    assert (await other.get(f"/api/v1/leads/{lead['id']}")).status_code == 200


async def test_FR_LEAD_06_rep_takes_over_a_lead_but_cannot_give_it_away(test_app: TestApp) -> None:
    owner, owner_user = await test_app.signed_in()
    lead = await create_lead(owner)
    taker, taker_user = await test_app.signed_in()
    given = await taker.post(
        f"/api/v1/leads/{lead['id']}/assign", json={"owner_id": str(owner_user.id), "version": 1}
    )
    assert given.status_code == 403
    taken = await taker.post(
        f"/api/v1/leads/{lead['id']}/assign", json={"owner_id": str(taker_user.id), "version": 1}
    )
    assert taken.status_code == 200
    assert taken.json()["owner"]["id"] == str(taker_user.id)
    [entry] = await test_app.audit("lead.owner_changed")
    assert entry.before is not None
    assert entry.after is not None
    assert (entry.before["owner_id"], entry.after["owner_id"]) == (
        str(owner_user.id),
        str(taker_user.id),
    )


async def test_FR_LEAD_06_manager_assigns_to_anyone_active(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    lead = await create_lead(rep)
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    colleague = await test_app.create_user()
    inactive = await test_app.create_user(is_active=False)
    bad = await manager.post(
        f"/api/v1/leads/{lead['id']}/assign", json={"owner_id": str(inactive.id), "version": 1}
    )
    assert bad.status_code == 422
    assert bad.json()["errors"] == [{"field": "owner_id", "code": "owner.invalid"}]
    good = await manager.post(
        f"/api/v1/leads/{lead['id']}/assign", json={"owner_id": str(colleague.id), "version": 1}
    )
    assert good.json()["owner"]["id"] == str(colleague.id)


async def test_viewer_cannot_capture_or_assign(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    lead = await create_lead(rep)
    viewer, viewer_user = await test_app.signed_in(RoleCode.VIEWER)
    assert (
        await viewer.post("/api/v1/leads", json={"title": "T", "company_name": "C"})
    ).status_code == 403
    assign = await viewer.post(
        f"/api/v1/leads/{lead['id']}/assign", json={"owner_id": str(viewer_user.id), "version": 1}
    )
    assert assign.status_code == 403


async def test_archive_and_restore(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    lead = await create_lead(rep)
    assert (await rep.delete(f"/api/v1/leads/{lead['id']}")).status_code == 204
    assert (await rep.get("/api/v1/leads")).json()["total"] == 0
    archived = (await rep.get(f"/api/v1/leads/{lead['id']}")).json()
    assert (await act(rep, archived, "mark-contacted")).json()["code"] == "resource.archived"
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    restored = await manager.post(f"/api/v1/leads/{lead['id']}/restore")
    assert restored.json()["archived_at"] is None


# --- FR-LEAD-05 list, search, organisation leads ----------------------------------------------


async def test_FR_LEAD_05_filters_sort_and_search(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    other, _ = await test_app.signed_in()
    event = await reference_id(rep, "lead-sources", "event")
    a = await create_lead(
        rep, title="Alpha", company_name="Глобал Телеком", estimated_value="1000", source_id=event
    )
    await create_lead(
        rep,
        title="Beta",
        company_name="Beta OOD",
        estimated_value="5000",
        qualification=BANT_COMPLETE,
    )
    await create_lead(
        other, title="Gamma", company_name="Gamma AD", qualification={"fits_target_profile": True}
    )
    await act(rep, a, "mark-contacted")

    async def titles(**params: Any) -> list[str]:
        response = await rep.get("/api/v1/leads", params=params)
        assert response.status_code == 200, response.text
        return [lead["title"] for lead in response.json()["items"]]

    assert await titles() == ["Gamma", "Beta", "Alpha"]  # newest first
    assert await titles(sort="-estimated_value") == ["Beta", "Alpha", "Gamma"]
    assert await titles(sort="-qualification_score") == ["Beta", "Alpha", "Gamma"]
    assert await titles(sort="company_name") == ["Beta", "Gamma", "Alpha"]
    assert await titles(status="contacted") == ["Alpha"]
    assert await titles(status=["new", "contacted"], owner_id="me") == ["Beta", "Alpha"]
    assert await titles(source_id=event) == ["Alpha"]
    assert await titles(fits_target_profile="true") == ["Gamma"]
    assert await titles(q="global telekom") == ["Alpha"]
    assert (
        await titles(created_at_from="2000-01-01T00:00:00Z", created_at_to="2001-01-01T00:00:00Z")
        == []
    )
    assert (await rep.get("/api/v1/leads", params={"sort": "owner"})).status_code == 400

    hits = (await rep.get("/api/v1/search", params={"q": "gamma", "types": "lead"})).json()["items"]
    assert hits == [{"type": "lead", "id": hits[0]["id"], "label": "Gamma", "detail": "Gamma AD"}]


async def test_FR_PARTY_03_organization_shows_its_open_leads(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = (await rep.post("/api/v1/organizations", json={"name": "Lead Org"})).json()
    await create_lead(rep, organization_id=org["id"])
    lost = await create_lead(rep, organization_id=org["id"], title="Lost")
    reason = await reference_id(rep, "disqualification-reasons", "no_need")
    await act(rep, lost, "disqualify", reason_id=reason)
    await create_lead(rep, title="Unlinked")

    detail = (await rep.get(f"/api/v1/organizations/{org['id']}")).json()
    assert detail["counts"]["open_leads"] == 1
    leads = (await rep.get(f"/api/v1/organizations/{org['id']}/leads")).json()
    assert sorted(lead["title"] for lead in leads["items"]) == ["Fibre for 3 branches", "Lost"]


# --- FR-ADM-02 lead lists ------------------------------------------------------------------------


async def test_FR_ADM_02_lead_lists_are_seeded_and_protected_when_used(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    sources = (await admin.get("/api/v1/reference/lead-sources")).json()
    reasons = (await admin.get("/api/v1/reference/disqualification-reasons")).json()
    assert [s["code"] for s in sources] == [
        "campaign",
        "inbound",
        "referral",
        "event",
        "cold_outreach",
        "partner",
        "other",
    ]
    assert len(reasons) == 9
    referral = next(s for s in sources if s["code"] == "referral")
    await create_lead(admin, source_id=referral["id"])
    in_use = await admin.delete(f"/api/v1/reference/lead-sources/{referral['id']}")
    assert in_use.json()["code"] == "reference.in_use"
