"""Activities, tasks and timelines (FR-ACT-01..03, FR-OPP-06; API spec 11). Fictional data only."""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import update

from app.core.principal import RoleCode
from app.modules.sales.models import Opportunity
from tests.api.test_opportunities import act, create_opp, create_org, loss_reason, stages
from tests.helpers import TestApp

DUE = "2026-11-20T10:00:00Z"


async def log(client: httpx.AsyncClient, **fields: Any) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/activities", json={"type": "call", "subject": "Discovery call", **fields}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def timeline(client: httpx.AsyncClient, path: str) -> list[dict[str, Any]]:
    response = await client.get(f"{path}/timeline")
    assert response.status_code == 200, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def kinds(items: list[dict[str, Any]]) -> list[str]:
    return [
        f"activity:{i['activity']['subject']}" if i["kind"] == "activity" else
        f"event:{i['event']['entity_type']}.{i['event']['type']}"
        for i in items
    ]  # fmt: skip


# --- FR-ACT-01 log activities -------------------------------------------------------------------


async def test_FR_ACT_01_log_a_call_against_an_opportunity(test_app: TestApp) -> None:
    rep, user = await test_app.signed_in(full_name="Rep One")
    org = await create_org(rep)
    opp = await create_opp(rep, org, name="Branch connectivity")
    call = await log(rep, opportunity_id=opp["id"], body="Talked about 3 sites")
    assert call["owner"] == {"id": str(user.id), "full_name": "Rep One"}
    assert call["occurred_at"] == "2026-11-17T09:00:00Z"  # now (frozen test clock)
    assert call["links"]["opportunity"] == {"id": opp["id"], "name": "Branch connectivity"}
    assert (call["is_done"], call["assignee"], call["due_at"]) == (False, None, None)
    [entry] = await test_app.audit("activity.created")
    assert entry.after is not None
    assert entry.after["subject"] == "Discovery call"
    fresh = (await rep.get(f"/api/v1/opportunities/{opp['id']}")).json()
    assert fresh["last_activity_at"] == "2026-11-17T09:00:00Z"


async def test_FR_ACT_01_links_are_required_and_validated(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    cases = [
        ({}, "links", "activity.link_required"),
        ({"lead_id": str(uuid4())}, "lead_id", "lead.not_found"),
        ({"opportunity_id": str(uuid4())}, "opportunity_id", "opportunity.not_found"),
        ({"organization_id": str(uuid4())}, "organization_id", "organization.not_found"),
        ({"contact_id": str(uuid4())}, "contact_id", "contact.not_found"),
        ({"organization_id": org["id"], "due_at": DUE}, "due_at", "activity.task_only"),
        ({"organization_id": org["id"], "type": "visit"}, "type", None),
    ]
    for fields, field, code in cases:
        response = await rep.post(
            "/api/v1/activities", json={"type": "note", "subject": "X", **fields}
        )
        assert response.status_code == 422, (fields, response.text)
        [error] = response.json()["errors"]
        assert error["field"] == field
        if code:
            assert error["code"] == code
    await rep.delete(f"/api/v1/organizations/{org['id']}")
    response = await rep.post(
        "/api/v1/activities",
        json={"type": "note", "subject": "X", "organization_id": org["id"]},
    )
    assert response.json()["errors"] == [
        {"field": "organization_id", "code": "organization.archived"}
    ]


async def test_FR_ACT_01_update_with_version_and_ownership(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    other, _ = await test_app.signed_in()
    org = await create_org(rep)
    note = await log(rep, type="note", organization_id=org["id"])
    path = f"/api/v1/activities/{note['id']}"
    refused = await other.patch(path, json={"version": 1, "subject": "Mine"})
    assert refused.status_code == 403
    response = await rep.patch(path, json={"version": 1, "subject": "Notes from the visit"})
    assert (response.json()["subject"], response.json()["version"]) == ("Notes from the visit", 2)
    stale = await rep.patch(path, json={"version": 1, "subject": "Again"})
    assert stale.status_code == 409
    assert stale.json()["current"]["version"] == 2
    for field, value in (("type", "task"), ("owner_id", str(uuid4())), ("done", True)):
        response = await rep.patch(path, json={"version": 2, field: value})
        assert response.json()["errors"] == [
            {"field": field, "code": "validation.use_action_endpoint"}
        ]
    assert len(await test_app.audit("activity.updated")) == 1


async def test_archived_activities_leave_lists_and_timelines(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    note = await log(rep, type="note", subject="Old note", organization_id=org["id"])
    assert (await rep.delete(f"/api/v1/activities/{note['id']}")).status_code == 204
    assert (await rep.get("/api/v1/activities")).json()["total"] == 0
    assert (await rep.get("/api/v1/activities?include_archived=true")).json()["total"] == 1
    assert "activity:Old note" not in kinds(
        await timeline(rep, f"/api/v1/organizations/{org['id']}")
    )
    response = await rep.patch(
        f"/api/v1/activities/{note['id']}", json={"version": 2, "subject": "X"}
    )
    assert response.json()["code"] == "resource.archived"


async def test_activity_list_filters(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    other, _ = await test_app.signed_in()
    org = await create_org(rep)
    opp = await create_opp(rep, org)
    await log(rep, subject="Call A", opportunity_id=opp["id"])
    await log(rep, type="meeting", subject="Meeting B", organization_id=org["id"])
    await log(other, type="task", subject="Task C", organization_id=org["id"], due_at=DUE)

    async def subjects(query: str) -> list[str]:
        response = await rep.get(f"/api/v1/activities?sort=occurred_at,created_at&{query}")
        assert response.status_code == 200, response.text
        return sorted(a["subject"] for a in response.json()["items"])

    assert await subjects("type=meeting") == ["Meeting B"]
    assert await subjects(f"opportunity_id={opp['id']}") == ["Call A"]
    assert await subjects("owner_id=me") == ["Call A", "Meeting B"]
    assert await subjects("is_done=false") == ["Task C"]
    assert await subjects("q=meeting") == ["Meeting B"]
    assert (await rep.get("/api/v1/activities?colour=red")).status_code == 400


# --- FR-ACT-02 tasks ------------------------------------------------------------------------------


async def test_FR_ACT_02_task_needs_due_date_and_an_assignee(test_app: TestApp) -> None:
    rep, user = await test_app.signed_in()
    viewer = await test_app.create_user(RoleCode.VIEWER)
    org = await create_org(rep)
    response = await rep.post(
        "/api/v1/activities",
        json={"type": "task", "subject": "Send offer", "organization_id": org["id"]},
    )
    assert response.json()["errors"] == [{"field": "due_at", "code": "activity.due_required"}]
    response = await rep.post(
        "/api/v1/activities",
        json={
            "type": "task",
            "subject": "Send offer",
            "organization_id": org["id"],
            "due_at": DUE,
            "assignee_id": str(viewer.id),
        },
    )
    assert response.json()["errors"] == [{"field": "assignee_id", "code": "assignee.invalid"}]
    task = await log(rep, type="task", subject="Send offer", organization_id=org["id"], due_at=DUE)
    assert task["assignee"]["id"] == str(user.id)
    assert (task["is_done"], task["is_overdue"]) == (False, False)


async def test_FR_ACT_02_assignee_or_owner_completes_and_reopens(test_app: TestApp) -> None:
    owner, _ = await test_app.signed_in()
    assignee, assignee_user = await test_app.signed_in()
    stranger, _ = await test_app.signed_in()
    org = await create_org(owner)
    task = await log(
        owner,
        type="task",
        subject="Prepare offer",
        organization_id=org["id"],
        due_at=DUE,
        assignee_id=str(assignee_user.id),
    )
    path = f"/api/v1/activities/{task['id']}"
    assert (await stranger.post(f"{path}/complete", json={"version": 1})).status_code == 403
    done = await assignee.post(f"{path}/complete", json={"version": 1})
    assert done.status_code == 200, done.text
    assert (done.json()["is_done"], done.json()["done_at"]) == (True, "2026-11-17T09:00:00Z")
    # The assignee may also edit the task (API spec 11).
    edited = await assignee.patch(path, json={"version": 2, "subject": "Prepare final offer"})
    assert edited.status_code == 200
    reopened = await owner.post(f"{path}/reopen", json={"version": 3})
    assert reopened.json()["is_done"] is False
    actions = [e.action for e in await test_app.audit() if e.entity_type == "activity"]
    assert actions == [
        "activity.created",
        "activity.completed",
        "activity.updated",
        "activity.reopened",
    ]
    note = await log(owner, type="note", organization_id=org["id"])
    response = await owner.post(f"/api/v1/activities/{note['id']}/complete", json={"version": 1})
    assert (response.status_code, response.json()["code"]) == (409, "activity.not_a_task")


async def test_FR_ACT_02_my_tasks_open_and_overdue_first(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    other, _ = await test_app.signed_in()
    org = await create_org(rep)
    for subject, due in (
        ("Later", "2026-12-01T09:00:00Z"),
        ("Overdue", "2026-11-10T09:00:00Z"),
        ("Soon", "2026-11-18T09:00:00Z"),
    ):
        await log(rep, type="task", subject=subject, organization_id=org["id"], due_at=due)
    done = await log(rep, type="task", subject="Done", organization_id=org["id"], due_at=DUE)
    await rep.post(f"/api/v1/activities/{done['id']}/complete", json={"version": 1})
    await log(other, type="task", subject="Not mine", organization_id=org["id"], due_at=DUE)
    await log(rep, type="call", subject="A call", organization_id=org["id"])

    tasks = (await rep.get("/api/v1/me/tasks")).json()
    assert [t["subject"] for t in tasks["items"]] == ["Overdue", "Soon", "Later"]
    assert [t["is_overdue"] for t in tasks["items"]] == [True, False, False]
    everything = (await rep.get("/api/v1/me/tasks?include_done=true")).json()
    assert {t["subject"] for t in everything["items"]} == {"Overdue", "Soon", "Later", "Done"}


# --- FR-OPP-06 activity keeps an opportunity fresh --------------------------------------------


async def test_FR_OPP_06_logged_activity_clears_the_idle_flag(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    opp = await create_opp(rep, expected_close_date="2027-03-31")
    async with test_app.sessions() as session:
        await session.execute(
            update(Opportunity)
            .where(Opportunity.id == UUID(opp["id"]))
            .values(created_at=test_app.clock.now() - timedelta(days=30))
        )
        await session.commit()
    assert (await rep.get(f"/api/v1/opportunities/{opp['id']}")).json()["is_stale"] is True
    # An old call does not count as recent activity...
    await log(rep, opportunity_id=opp["id"], occurred_at="2026-10-01T09:00:00Z")
    assert (await rep.get(f"/api/v1/opportunities/{opp['id']}")).json()["is_stale"] is True
    # ...a call today does.
    await log(rep, opportunity_id=opp["id"])
    assert (await rep.get(f"/api/v1/opportunities/{opp['id']}")).json()["is_stale"] is False
    stale_list = (await rep.get("/api/v1/opportunities?is_stale=true")).json()
    assert stale_list["total"] == 0


# --- FR-ACT-03 timelines --------------------------------------------------------------------------


async def test_FR_ACT_03_opportunity_timeline_merges_activities_and_events(
    test_app: TestApp,
) -> None:
    rep, user = await test_app.signed_in(full_name="Rep One")
    manager, manager_user = await test_app.signed_in(
        RoleCode.SALES_MANAGER, full_name="Mia Manager"
    )
    by_name = await stages(rep)
    opp = await create_opp(rep)
    test_app.clock.advance(timedelta(minutes=1))
    moved = (await act(rep, opp, "move", stage_id=by_name["Negotiation"]["id"])).json()
    test_app.clock.advance(timedelta(minutes=1))
    await log(rep, subject="Negotiation call", opportunity_id=opp["id"])
    test_app.clock.advance(timedelta(minutes=1))
    assigned = (await act(manager, moved, "assign", owner_id=str(manager_user.id))).json()
    test_app.clock.advance(timedelta(minutes=1))
    await act(manager, assigned, "close", outcome="lost", loss_reason_id=await loss_reason(rep))

    items = await timeline(rep, f"/api/v1/opportunities/{opp['id']}")
    assert kinds(items) == [
        "event:opportunity.closed_lost",
        "event:opportunity.owner_changed",
        "activity:Negotiation call",
        "event:opportunity.stage_changed",
        "event:opportunity.created",
    ]
    lost, owner_changed, call, stage_changed, created = items
    assert stage_changed["event"]["data"]["from_stage"]["name_en"] == "Prospecting"
    assert stage_changed["event"]["data"]["to_stage"]["name_bg"] == "Преговори"
    assert stage_changed["actor"] == {"id": str(user.id), "full_name": "Rep One"}
    assert owner_changed["event"]["data"]["to_owner"]["full_name"] == "Mia Manager"
    assert lost["event"]["data"]["loss_reason"]["code"] == "price"
    assert call["actor"]["full_name"] == "Rep One"
    assert created["event"]["entity_id"] == opp["id"]
    assert (await rep.get(f"/api/v1/opportunities/{uuid4()}/timeline")).status_code == 404


async def test_FR_ACT_03_organization_timeline_includes_its_records(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    other_org = await create_org(rep, "Друга ЕООД")
    contact = (
        await rep.post(
            "/api/v1/contacts",
            json={"first_name": "Мария", "last_name": "Иванова", "organization_id": org["id"]},
        )
    ).json()
    lead = (
        await rep.post(
            "/api/v1/leads",
            json={"title": "Fibre", "company_name": "Акме", "organization_id": org["id"]},
        )
    ).json()
    test_app.clock.advance(timedelta(minutes=1))
    await log(rep, subject="Call Maria", contact_id=contact["id"])
    await log(rep, subject="Lead call", lead_id=lead["id"])
    await log(rep, subject="Elsewhere", organization_id=other_org["id"])
    test_app.clock.advance(timedelta(minutes=1))
    await create_opp(rep, org, name="Deal")

    items = await timeline(rep, f"/api/v1/organizations/{org['id']}")
    found = kinds(items)
    assert found[0] == "event:opportunity.created"
    assert {"activity:Call Maria", "activity:Lead call", "event:contact.created",
            "event:lead.created", "event:organization.created"} <= set(found)  # fmt: skip
    assert "activity:Elsewhere" not in found
    contact_items = kinds(await timeline(rep, f"/api/v1/contacts/{contact['id']}"))
    assert contact_items == ["activity:Call Maria", "event:contact.created"]
    lead_items = kinds(await timeline(rep, f"/api/v1/leads/{lead['id']}"))
    assert lead_items == ["activity:Lead call", "event:lead.created"]
    page = (await rep.get(f"/api/v1/organizations/{org['id']}/timeline?page_size=2")).json()
    assert (len(page["items"]), page["total"]) == (2, len(found))


async def test_FR_ACT_02_task_edit_rules(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    colleague = await test_app.create_user()
    org = await create_org(rep)
    task = await log(rep, type="task", subject="Offer", organization_id=org["id"], due_at=DUE)
    note = await log(rep, type="note", organization_id=org["id"])
    task_path, note_path = f"/api/v1/activities/{task['id']}", f"/api/v1/activities/{note['id']}"
    for body, field, code in (
        ({"due_at": None}, "due_at", "activity.due_required"),
        ({"assignee_id": None}, "assignee_id", "validation.missing"),
        ({"subject": None}, "subject", "validation.missing"),
    ):
        response = await rep.patch(task_path, json={"version": 1, **body})
        assert response.json()["errors"] == [{"field": field, "code": code}], body
    response = await rep.patch(note_path, json={"version": 1, "due_at": DUE})
    assert response.json()["errors"] == [{"field": "due_at", "code": "activity.task_only"}]
    moved = await rep.patch(
        task_path,
        json={"version": 1, "assignee_id": str(colleague.id), "due_at": "2026-11-25T09:00:00Z"},
    )
    assert moved.json()["assignee"]["id"] == str(colleague.id)
    assert moved.json()["due_at"] == "2026-11-25T09:00:00Z"


async def test_activity_date_filters_and_sync_mode(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    await log(rep, subject="October", organization_id=org["id"], occurred_at="2026-10-01T09:00:00Z")
    await log(rep, subject="November", organization_id=org["id"])
    await log(rep, type="task", subject="Due soon", organization_id=org["id"], due_at=DUE)

    async def subjects(query: str) -> list[str]:
        response = await rep.get(f"/api/v1/activities?{query}")
        assert response.status_code == 200, response.text
        return sorted(a["subject"] for a in response.json()["items"])

    assert await subjects("occurred_at_to=2026-10-31T00:00:00Z") == ["October"]
    assert await subjects("occurred_at_from=2026-11-01T00:00:00Z&type=call") == ["November"]
    assert await subjects("due_at_from=2026-11-19T00:00:00Z&due_at_to=2026-11-21T00:00:00Z") == [
        "Due soon"
    ]
    body = (
        await rep.get("/api/v1/activities", params={"updated_since": "2000-01-01T00:00:00Z"})
    ).json()
    assert set(body) == {"items", "next_cursor"}
    assert len(body["items"]) == 3
    assert (await rep.get(f"/api/v1/activities/{uuid4()}")).status_code == 404
