"""GDPR tools for contacts (FR-ADM-04; NFR-05; API spec 8; ADR 0027)."""

import json
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select

from app.core.principal import RoleCode
from app.modules.assistant.models import ChatConversation, ChatMessage
from app.modules.integration.models import OutboxEvent
from tests.api.test_opportunities import create_opp
from tests.api.test_organizations import create_org
from tests.helpers import TestApp

EMAIL = "maria.petrova@example.test"


async def person(client: httpx.AsyncClient) -> dict[str, Any]:
    org = await create_org(client, name="Данни ЕООД")
    response = await client.post(
        "/api/v1/contacts",
        json={
            "first_name": "Мария",
            "last_name": "Петрова",
            "email": EMAIL,
            "phone": "+359 2 000 0000",
            "job_title": "CFO",
            "preferred_locale": "bg",
            "notes": "Prefers calls after 16:00",
            "organization_id": org["id"],
        },
    )
    assert response.status_code == 201, response.text
    contact: dict[str, Any] = response.json()
    contact["org"] = org
    return contact


async def footprint(
    test_app: TestApp, client: httpx.AsyncClient, contact: dict[str, Any]
) -> dict[str, str]:
    """Records in other modules that hold or mention the contact."""
    linked = await client.post(
        "/api/v1/leads",
        json={
            "title": "Cloud backup",
            "company_name": "Данни ЕООД",
            "contact_name": "Мария Петрова",
            "email": EMAIL,
            "phone": "+359 2 000 0000",
            "contact_id": contact["id"],
            "organization_id": contact["org"]["id"],
        },
    )
    assert linked.status_code == 201, linked.text
    same_email = await client.post(
        "/api/v1/leads",
        json={"title": "SIP trunk", "company_name": "Друга АД", "email": EMAIL.upper()},
    )
    assert same_email.status_code == 201, same_email.text
    opp = await create_opp(
        client, contact["org"], name="Backup deal", primary_contact_id=contact["id"]
    )
    note = await client.post(
        "/api/v1/activities",
        json={
            "type": "call",
            "subject": "Intro call",
            "body": "Budget OK",
            "contact_id": contact["id"],
        },
    )
    mention = await client.post(
        "/api/v1/activities",
        json={
            "type": "note",
            "subject": "Board meeting",
            "body": "Мария Петрова asked for a discount",
            "opportunity_id": opp["id"],
        },
    )
    assert note.status_code == 201
    assert mention.status_code == 201
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    ref = await admin.put(
        f"/api/v1/contacts/{contact['id']}/external-references/erp",
        json={"external_id": "P-77"},
    )
    assert ref.status_code == 200, ref.text
    async with test_app.sessions() as session:
        users = (await client.get("/api/v1/me")).json()
        chat = ChatConversation(user_id=UUID(users["id"]), title="Prep")
        session.add(chat)
        await session.flush()
        session.add(
            ChatMessage(
                conversation_id=chat.id,
                role="assistant",
                content=f"Draft for {EMAIL}: thank you for the meeting.",
                status="complete",
                created_at=test_app.clock.now(),
            )
        )
        await session.commit()
    return {
        "linked_lead": linked.json()["id"],
        "email_lead": same_email.json()["id"],
        "opportunity": opp["id"],
        "note": note.json()["id"],
        "mention": mention.json()["id"],
    }


async def test_FR_ADM_04_export_lists_everything_held_about_the_contact(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    contact = await person(rep)
    ids = await footprint(test_app, rep, contact)
    admin, admin_user = await test_app.signed_in(RoleCode.ADMIN)

    response = await admin.get(f"/api/v1/contacts/{contact['id']}/personal-data")
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == (
        f'attachment; filename="contact-{contact["id"]}-personal-data.json"'
    )
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["contact"]["email"] == EMAIL
    assert data["contact"]["notes"] == "Prefers calls after 16:00"
    assert sorted(lead["id"] for lead in data["leads"]) == sorted(
        [ids["linked_lead"], ids["email_lead"]]
    )
    assert [o["id"] for o in data["opportunities_as_primary_contact"]] == [ids["opportunity"]]
    assert [a["id"] for a in data["activities"]] == [ids["note"]]
    assert [a["id"] for a in data["activities_mentioning_the_contact"]] == [ids["mention"]]
    assert data["ids_in_other_systems"] == [{"system": "erp", "external_id": "P-77", "url": None}]
    [chat] = data["assistant_chats_mentioning_the_contact"]
    assert EMAIL in chat["excerpt"]
    assert data["audit_log"]["entries"] >= 1

    [entry] = await test_app.audit("contact.personal_data_exported")
    assert (entry.actor_id, str(entry.entity_id)) == (admin_user.id, contact["id"])
    assert (await admin.get(f"/api/v1/contacts/{uuid4()}/personal-data")).status_code == 404
    assert (await rep.get(f"/api/v1/contacts/{contact['id']}/personal-data")).status_code == 403


async def test_FR_ADM_04_anonymize_replaces_personal_fields_and_keeps_history(
    test_app: TestApp,
) -> None:
    rep, _ = await test_app.signed_in()
    contact = await person(rep)
    ids = await footprint(test_app, rep, contact)
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    url = f"/api/v1/contacts/{contact['id']}/anonymize"

    for body in ({}, {"confirm": "yes"}, {"confirm": "anonymize"}):
        refused = await admin.post(url, json=body)
        assert refused.status_code == 422, body

    done = await admin.post(url, json={"confirm": "ANONYMIZE"})
    assert done.status_code == 200, done.text
    out = done.json()
    assert out["first_name"] == "Anonymized"
    assert out["last_name"] == f"#{UUID(contact['id']).hex[-6:]}"
    for field in ("email", "phone", "job_title", "notes", "preferred_locale"):
        assert out[field] is None, field
    assert out["anonymized_at"] is not None
    assert out["organization"]["id"] == contact["org"]["id"]

    # Linked and same-email leads lose their person fields; the commercial records stay.
    for lead_id in (ids["linked_lead"], ids["email_lead"]):
        lead = (await admin.get(f"/api/v1/leads/{lead_id}")).json()
        assert (lead["contact_name"], lead["email"], lead["phone"]) == (None, None, None)
        assert lead["title"] in {"Cloud backup", "SIP trunk"}
    opp = (await admin.get(f"/api/v1/opportunities/{ids['opportunity']}")).json()
    assert opp["primary_contact"]["id"] == contact["id"]
    note = (await admin.get(f"/api/v1/activities/{ids['note']}")).json()
    assert note["body"] == "Budget OK"

    # Search no longer finds the person.
    found = (await admin.get("/api/v1/contacts", params={"q": "Петрова"})).json()
    assert found["total"] == 0
    assert (await admin.get("/api/v1/leads", params={"q": EMAIL})).json()["total"] == 0

    # The audit entry and the webhook event carry the result only, never the old values.
    [entry] = await test_app.audit("contact.anonymized")
    assert entry.before is None
    assert EMAIL not in json.dumps(entry.after, ensure_ascii=False)
    assert "Петрова" not in json.dumps(entry.after, ensure_ascii=False)
    reasons = [e.details for e in await test_app.audit("lead.updated") if e.details]
    assert reasons == [{"reason": "contact_anonymized"}] * 2
    async with test_app.sessions() as session:
        events = (
            (
                await session.execute(
                    select(OutboxEvent).where(OutboxEvent.event_type == "contact.anonymized")
                )
            )
            .scalars()
            .all()
        )
    assert len(events) == 1
    assert EMAIL not in json.dumps(events[0].changes, ensure_ascii=False)

    # Irreversible: no second anonymization and no edits that would add data back.
    again = await admin.post(url, json={"confirm": "ANONYMIZE"})
    assert again.status_code == 409
    assert again.json()["code"] == "contact.anonymized"
    edit = await admin.patch(f"/api/v1/contacts/{contact['id']}", json={"email": EMAIL})
    assert edit.status_code == 409
    assert edit.json()["code"] == "contact.anonymized"


async def test_FR_ADM_04_export_after_anonymization_holds_only_free_text_mentions(
    test_app: TestApp,
) -> None:
    rep, _ = await test_app.signed_in()
    contact = await person(rep)
    await footprint(test_app, rep, contact)
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    await admin.post(f"/api/v1/contacts/{contact['id']}/anonymize", json={"confirm": "ANONYMIZE"})
    data = (await admin.get(f"/api/v1/contacts/{contact['id']}/personal-data")).json()
    structured = {
        key: value
        for key, value in data.items()
        if key
        not in {"activities_mentioning_the_contact", "assistant_chats_mentioning_the_contact"}
    }
    text = json.dumps(structured, ensure_ascii=False)
    for personal in (EMAIL, "Петрова", "+359 2 000 0000", "Prefers calls"):
        assert personal not in text
    assert data["contact"]["anonymized_at"] is not None


async def test_FR_ADM_04_only_admins(test_app: TestApp) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    contact = await person(manager)
    for method, path, body in [
        ("GET", f"/api/v1/contacts/{contact['id']}/personal-data", None),
        ("POST", f"/api/v1/contacts/{contact['id']}/anonymize", {"confirm": "ANONYMIZE"}),
    ]:
        response = await manager.request(method, path, json=body)
        assert response.status_code == 403
