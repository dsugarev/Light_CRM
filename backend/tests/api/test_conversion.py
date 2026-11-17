"""Lead conversion (FR-LEAD-04; API spec 9). Fictional data only."""

from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import func, select

from app.modules.party.models import Contact, Organization
from app.modules.sales.models import Opportunity
from tests.api.test_leads import BANT_COMPLETE, act, create_lead
from tests.api.test_opportunities import stages
from tests.helpers import TestApp


async def qualified_lead(client: httpx.AsyncClient, **fields: Any) -> dict[str, Any]:
    lead = await create_lead(
        client,
        contact_name="Мария Иванова",
        email="maria@acme.example",
        estimated_value="48000",
        qualification=BANT_COMPLETE,
        **fields,
    )
    lead = (await act(client, lead, "mark-contacted")).json()
    response = await act(client, lead, "qualify")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def convert_body(lead: dict[str, Any], **parts: Any) -> dict[str, Any]:
    return {
        "version": lead["version"],
        "organization": {"new": {"name": "Акме ЕООД", "registration_number": "121212126"}},
        "contact": {"new": {"first_name": "Мария", "last_name": "Иванова",
                            "email": "maria@acme.example"}},
        "opportunity": {"name": "Acme – branch connectivity", "amount": "48000.00",
                        "expected_close_date": "2027-02-28"},
        **parts,
    }  # fmt: skip


async def counts(test_app: TestApp) -> tuple[int, int, int]:
    async with test_app.sessions() as session:
        return (
            (await session.execute(select(func.count()).select_from(Organization))).scalar_one(),
            (await session.execute(select(func.count()).select_from(Contact))).scalar_one(),
            (await session.execute(select(func.count()).select_from(Opportunity))).scalar_one(),
        )


async def test_FR_LEAD_04_AC1_convert_creates_and_links_everything(test_app: TestApp) -> None:
    rep, user = await test_app.signed_in()
    lead = await qualified_lead(rep)
    response = await rep.post(f"/api/v1/leads/{lead['id']}/convert", json=convert_body(lead))
    assert response.status_code == 201, response.text
    result = response.json()
    opp, org, contact = result["opportunity"], result["organization"], result["contact"]
    assert result["lead"]["status"] == "converted"
    assert result["lead"]["converted_opportunity"] == {"id": opp["id"], "name": opp["name"]}
    assert result["lead"]["converted_at"] == "2026-11-17T09:00:00Z"
    assert result["lead"]["organization"] == {"id": org["id"], "name": "Акме ЕООД"}
    assert opp["source_lead"] == {"id": lead["id"], "name": lead["title"]}
    assert opp["organization"]["id"] == org["id"]
    assert opp["primary_contact"]["id"] == contact["id"]
    assert (opp["stage"]["name_en"], opp["probability"], opp["owner"]["id"]) == (
        "Prospecting",
        10,
        str(user.id),
    )
    assert contact["organization"]["id"] == org["id"]
    actions = [e.action for e in await test_app.audit()]
    for action in (
        "organization.created",
        "contact.created",
        "opportunity.created",
        "lead.converted",
    ):
        assert action in actions
    # A converted lead is read-only and cannot be converted again.
    converted = result["lead"]
    refused = await rep.patch(
        f"/api/v1/leads/{lead['id']}", json={"version": converted["version"], "title": "X"}
    )
    assert refused.json()["code"] == "lead.read_only"
    again = await rep.post(f"/api/v1/leads/{lead['id']}/convert", json=convert_body(converted))
    assert (again.status_code, again.json()["code"]) == (409, "lead.not_convertible")


async def test_FR_LEAD_04_convert_with_existing_records(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = (await rep.post("/api/v1/organizations", json={"name": "Бета АД"})).json()
    contact = (
        await rep.post(
            "/api/v1/contacts",
            json={"first_name": "Иван", "last_name": "Петров", "organization_id": org["id"]},
        )
    ).json()
    negotiation = (await stages(rep))["Negotiation"]
    lead = await qualified_lead(rep)
    body = convert_body(
        lead,
        organization={"existing_id": org["id"]},
        contact={"existing_id": contact["id"]},
        opportunity={"name": "Deal", "stage_id": negotiation["id"]},
    )
    response = await rep.post(f"/api/v1/leads/{lead['id']}/convert", json=body)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["organization"]["id"] == org["id"]
    assert result["contact"]["id"] == contact["id"]
    assert result["opportunity"]["stage"]["id"] == negotiation["id"]
    assert await counts(test_app) == (1, 1, 1)


async def test_FR_LEAD_04_without_a_contact(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    lead = await qualified_lead(rep)
    response = await rep.post(
        f"/api/v1/leads/{lead['id']}/convert", json=convert_body(lead, contact=None)
    )
    assert response.status_code == 201, response.text
    assert response.json()["contact"] is None
    assert response.json()["opportunity"]["primary_contact"] is None


async def test_FR_LEAD_04_AC2_nothing_is_created_when_a_step_fails(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    won = (await stages(rep))["Closed Won"]
    lead = await qualified_lead(rep)
    # The opportunity step fails after the organization and contact were prepared.
    body = convert_body(lead, opportunity={"name": "Deal", "stage_id": won["id"]})
    response = await rep.post(f"/api/v1/leads/{lead['id']}/convert", json=body)
    assert response.status_code == 422
    assert response.json()["errors"] == [{"field": "stage_id", "code": "stage.not_open"}]
    assert await counts(test_app) == (0, 0, 0)
    assert (await rep.get(f"/api/v1/leads/{lead['id']}")).json()["status"] == "qualified"
    assert await test_app.audit("organization.created") == []

    # A duplicate organization is refused unless confirmed; again nothing is kept.
    await rep.post("/api/v1/organizations", json={"name": "ACME e.o.o.d."})
    response = await rep.post(f"/api/v1/leads/{lead['id']}/convert", json=convert_body(lead))
    assert (response.status_code, response.json()["code"]) == (409, "conflict.duplicate")
    assert await counts(test_app) == (1, 0, 0)
    confirmed = convert_body(
        lead,
        organization={"new": {"name": "Акме ЕООД", "confirm_duplicate": True}},
    )
    response = await rep.post(f"/api/v1/leads/{lead['id']}/convert", json=confirmed)
    assert response.status_code == 201, response.text


async def test_FR_LEAD_04_validation_and_state_rules(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    other, _ = await test_app.signed_in()
    other_org = (await rep.post("/api/v1/organizations", json={"name": "Гама ООД"})).json()
    stranger = (
        await rep.post(
            "/api/v1/contacts",
            json={"first_name": "Петя", "last_name": "Колева", "organization_id": other_org["id"]},
        )
    ).json()
    lead = await qualified_lead(rep)
    path = f"/api/v1/leads/{lead['id']}/convert"

    both = convert_body(lead, organization={"existing_id": other_org["id"], "new": {"name": "X"}})
    response = await rep.post(path, json=both)
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "organization"

    response = await rep.post(
        path, json=convert_body(lead, organization={"existing_id": str(uuid4())})
    )
    assert response.json()["errors"] == [
        {"field": "organization.existing_id", "code": "organization.not_found"}
    ]
    org = (await rep.post("/api/v1/organizations", json={"name": "Делта АД"})).json()
    mismatch = convert_body(
        lead, organization={"existing_id": org["id"]}, contact={"existing_id": stranger["id"]}
    )
    response = await rep.post(path, json=mismatch)
    assert response.json()["errors"] == [
        {"field": "contact.existing_id", "code": "contact.organization_mismatch"}
    ]
    assert (await other.post(path, json=convert_body(lead))).status_code == 403
    stale = await rep.post(path, json={**convert_body(lead), "version": lead["version"] - 1})
    assert stale.json()["code"] == "conflict.version_mismatch"

    fresh = await create_lead(rep)
    response = await rep.post(f"/api/v1/leads/{fresh['id']}/convert", json=convert_body(fresh))
    assert (response.status_code, response.json()["code"]) == (409, "lead.not_convertible")
    assert response.json()["status"] == "new"


async def test_FR_LEAD_04_conversion_preview_suggests_matches(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    other, _ = await test_app.signed_in()
    org = (await rep.post("/api/v1/organizations", json={"name": "ACME EOOD"})).json()
    contact = (
        await rep.post(
            "/api/v1/contacts",
            json={"first_name": "Maria", "last_name": "Ivanova", "email": "maria@acme.example"},
        )
    ).json()
    lead = await qualified_lead(rep)
    response = await rep.get(f"/api/v1/leads/{lead['id']}/conversion-preview")
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["organization"]["suggested"] == {"name": "Акме ЕООД"}
    assert [m["id"] for m in preview["organization"]["matches"]] == [org["id"]]  # across scripts
    assert [m["id"] for m in preview["contact"]["matches"]] == [contact["id"]]
    assert preview["contact"]["suggested"] == {
        "first_name": "Мария",
        "last_name": "Иванова",
        "email": "maria@acme.example",
        "phone": None,
    }
    assert preview["opportunity"]["name"] == lead["title"]
    assert preview["opportunity"]["amount"] == "48000.00"
    assert preview["opportunity"]["stage"]["name_en"] == "Prospecting"
    refused = await other.get(f"/api/v1/leads/{lead['id']}/conversion-preview")
    assert refused.status_code == 403


async def test_FR_LEAD_04_AC3_lead_activities_appear_on_the_opportunity_timeline(
    test_app: TestApp,
) -> None:
    rep, _ = await test_app.signed_in()
    lead = await qualified_lead(rep)
    await rep.post(
        "/api/v1/activities",
        json={"type": "call", "subject": "First call with Maria", "lead_id": lead["id"]},
    )
    result = (await rep.post(f"/api/v1/leads/{lead['id']}/convert", json=convert_body(lead))).json()
    items = (await rep.get(f"/api/v1/opportunities/{result['opportunity']['id']}/timeline")).json()
    subjects = [i["activity"]["subject"] for i in items["items"] if i["kind"] == "activity"]
    assert subjects == ["First call with Maria"]
    events = [
        (i["event"]["entity_type"], i["event"]["type"])
        for i in items["items"]
        if i["kind"] == "event"
    ]
    assert ("lead", "converted") in events
    assert ("opportunity", "created") in events
    converted = next(
        i for i in items["items"] if i["kind"] == "event" and i["event"]["type"] == "converted"
    )
    assert converted["event"]["data"]["opportunity"]["id"] == result["opportunity"]["id"]
