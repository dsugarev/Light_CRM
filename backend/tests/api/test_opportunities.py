"""Opportunities, pipeline board and stages (FR-OPP-01..06, FR-ADM-02; API spec 6.3, 10).

Fictional data only.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import update

from app.core import runtime_settings
from app.core.principal import RoleCode
from app.modules.sales.models import Opportunity
from tests.helpers import TestApp


async def create_org(client: httpx.AsyncClient, name: str = "Акме ЕООД") -> dict[str, Any]:
    response = await client.post(
        "/api/v1/organizations", json={"name": name, "confirm_duplicate": True}
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def create_opp(
    client: httpx.AsyncClient, org: dict[str, Any] | None = None, **fields: Any
) -> dict[str, Any]:
    org = org or await create_org(client)
    response = await client.post(
        "/api/v1/opportunities",
        json={"name": "Fibre for 3 branches", "organization_id": org["id"], **fields},
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def stages(client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    """Stages of the default pipeline keyed by English name."""
    [pipeline] = (await client.get("/api/v1/pipelines")).json()
    return {s["name_en"]: s for s in pipeline["stages"]}


async def pipeline_id(client: httpx.AsyncClient) -> str:
    [pipeline] = (await client.get("/api/v1/pipelines")).json()
    return str(pipeline["id"])


async def loss_reason(client: httpx.AsyncClient, code: str = "price") -> str:
    items: list[dict[str, str]] = (await client.get("/api/v1/reference/loss-reasons")).json()
    return next(i["id"] for i in items if i["code"] == code)


async def act(
    client: httpx.AsyncClient, opp: dict[str, Any], action: str, **body: Any
) -> httpx.Response:
    return await client.post(
        f"/api/v1/opportunities/{opp['id']}/{action}", json={"version": opp["version"], **body}
    )


# --- FR-OPP-02 / FR-ADM-02 pipeline and stages ----------------------------------------------


async def test_FR_OPP_02_default_pipeline_is_seeded_in_both_languages(test_app: TestApp) -> None:
    viewer, _ = await test_app.signed_in(RoleCode.VIEWER)
    [pipeline] = (await viewer.get("/api/v1/pipelines")).json()
    assert pipeline["is_default"] is True
    assert [
        (s["name_en"], s["name_bg"], s["default_probability"], s["stage_type"])
        for s in pipeline["stages"]
    ] == [
        ("Prospecting", "Проучване", 10, "open"),
        ("Qualification", "Квалификация", 25, "open"),
        ("Solution & Proposal", "Решение и оферта", 50, "open"),
        ("Negotiation", "Преговори", 75, "open"),
        ("Closed Won", "Спечелена", 100, "won"),
        ("Closed Lost", "Загубена", 0, "lost"),
    ]
    one = (await viewer.get(f"/api/v1/pipelines/{pipeline['id']}")).json()
    assert one == pipeline
    assert (await viewer.get(f"/api/v1/pipelines/{uuid4()}")).status_code == 404


async def test_FR_ADM_02_admin_adds_renames_reorders_and_deletes_a_stage(
    test_app: TestApp,
) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    pid = await pipeline_id(admin)
    response = await admin.post(
        f"/api/v1/pipelines/{pid}/stages",
        json={
            "name_en": "Pilot",
            "name_bg": "Пилот",
            "default_probability": 60,
            "stage_type": "open",
        },
    )
    assert response.status_code == 201, response.text
    added = next(s for s in response.json()["stages"] if s["name_en"] == "Pilot")
    assert added["position"] == 7
    assert added["is_active"] is True

    response = await admin.patch(
        f"/api/v1/pipelines/{pid}/stages/{added['id']}",
        json={"name_en": "Pilot project", "default_probability": 65},
    )
    renamed = next(s for s in response.json()["stages"] if s["id"] == added["id"])
    assert (renamed["name_en"], renamed["default_probability"]) == ("Pilot project", 65)

    ids = [s["id"] for s in response.json()["stages"]]
    order = [*ids[:3], added["id"], *[i for i in ids[3:] if i != added["id"]]]
    response = await admin.put(f"/api/v1/pipelines/{pid}/stages/order", json=order)
    assert response.status_code == 200, response.text
    assert [s["id"] for s in response.json()["stages"]] == order
    incomplete = await admin.put(f"/api/v1/pipelines/{pid}/stages/order", json=order[:-1])
    assert incomplete.status_code == 422
    assert incomplete.json()["errors"] == [{"field": "body", "code": "stage.order_incomplete"}]

    deleted = await admin.delete(f"/api/v1/pipelines/{pid}/stages/{added['id']}")
    assert deleted.status_code == 204
    assert "Pilot project" not in await stages(admin)
    actions = {e.action for e in await test_app.audit() if e.action.startswith("pipeline_stage.")}
    assert actions == {
        "pipeline_stage.created",
        "pipeline_stage.updated",
        "pipeline_stage.reordered",
        "pipeline_stage.deleted",
    }


async def test_FR_OPP_02_AC1_stage_in_use_cannot_be_deleted_only_deactivated(
    test_app: TestApp,
) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    pid = await pipeline_id(admin)
    await create_opp(admin)
    prospecting = (await stages(admin))["Prospecting"]
    response = await admin.delete(f"/api/v1/pipelines/{pid}/stages/{prospecting['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "stage.in_use"
    response = await admin.patch(
        f"/api/v1/pipelines/{pid}/stages/{prospecting['id']}", json={"is_active": False}
    )
    assert response.status_code == 200
    # New opportunities now start in the next active open stage.
    assert (await create_opp(admin))["stage"]["name_en"] == "Qualification"


async def test_each_stage_type_keeps_one_active_stage(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    pid = await pipeline_id(admin)
    won = (await stages(admin))["Closed Won"]
    response = await admin.patch(
        f"/api/v1/pipelines/{pid}/stages/{won['id']}", json={"is_active": False}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "stage.required"
    response = await admin.delete(f"/api/v1/pipelines/{pid}/stages/{won['id']}")
    assert response.json()["code"] == "stage.required"


async def test_stage_validation(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    pid = await pipeline_id(admin)
    response = await admin.post(
        f"/api/v1/pipelines/{pid}/stages",
        json={"name_en": "X", "name_bg": "Х", "default_probability": 101, "stage_type": "maybe"},
    )
    assert response.status_code == 422
    assert {e["field"] for e in response.json()["errors"]} == {
        "default_probability",
        "stage_type",
    }
    unknown = await admin.patch(f"/api/v1/pipelines/{pid}/stages/{uuid4()}", json={})
    assert unknown.status_code == 404


# --- FR-OPP-01 create, read, update ---------------------------------------------------------


async def test_FR_OPP_01_create_defaults_to_first_open_stage_and_its_probability(
    test_app: TestApp,
) -> None:
    rep, user = await test_app.signed_in(full_name="Rep One")
    opp = await create_opp(rep, amount="48000.00", expected_close_date="2027-02-28")
    assert opp["stage"]["name_en"] == "Prospecting"
    assert opp["probability"] == 10
    assert opp["probability_overridden"] is False
    assert opp["weighted_amount"] == "4800.00"
    assert opp["amount"] == "48000.00"
    assert opp["currency"] == "EUR"
    assert opp["owner"] == {"id": str(user.id), "full_name": "Rep One"}
    assert opp["organization"]["name"] == "Акме ЕООД"
    assert opp["version"] == 1
    assert opp["is_stale"] is False
    assert opp["source_lead"] is None
    [entry] = await test_app.audit("opportunity.created")
    assert entry.after is not None
    assert entry.after["amount"] == "48000.00"
    history = (await rep.get(f"/api/v1/opportunities/{opp['id']}/stage-history")).json()
    assert [(h["from_stage"], h["to_stage"]["name_en"]) for h in history] == [(None, "Prospecting")]
    assert history[0]["changed_by"]["full_name"] == "Rep One"


async def test_FR_OPP_01_stage_contact_and_probability_override_on_create(
    test_app: TestApp,
) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    contact = (
        await rep.post(
            "/api/v1/contacts",
            json={"first_name": "Мария", "last_name": "Иванова", "organization_id": org["id"]},
        )
    ).json()
    negotiation = (await stages(rep))["Negotiation"]
    opp = await create_opp(
        rep, org, stage_id=negotiation["id"], probability=90, primary_contact_id=contact["id"]
    )
    assert opp["stage"]["id"] == negotiation["id"]
    assert (opp["probability"], opp["probability_overridden"]) == (90, True)
    assert opp["primary_contact"] == {"id": contact["id"], "name": "Мария Иванова"}


async def test_FR_OPP_01_links_are_validated(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    other = await create_org(rep, "Бета АД")
    stranger = (
        await rep.post(
            "/api/v1/contacts",
            json={"first_name": "Иван", "last_name": "Петров", "organization_id": other["id"]},
        )
    ).json()
    won = (await stages(rep))["Closed Won"]
    cases = [
        ({"organization_id": str(uuid4())}, "organization_id", "organization.not_found"),
        (
            {"primary_contact_id": stranger["id"]},
            "primary_contact_id",
            "contact.organization_mismatch",
        ),
        ({"primary_contact_id": str(uuid4())}, "primary_contact_id", "contact.not_found"),
        ({"stage_id": won["id"]}, "stage_id", "stage.not_open"),
        ({"amount": "-1"}, "amount", None),
        ({"probability": 101}, "probability", None),
    ]
    for fields, field, code in cases:
        response = await rep.post(
            "/api/v1/opportunities",
            json={"name": "X", "organization_id": org["id"], **fields},
        )
        assert response.status_code == 422, (fields, response.text)
        [error] = response.json()["errors"]
        assert error["field"] == field
        if code:
            assert error["code"] == code
    await rep.delete(f"/api/v1/organizations/{other['id']}")
    response = await rep.post(
        "/api/v1/opportunities", json={"name": "X", "organization_id": other["id"]}
    )
    assert response.json()["errors"] == [
        {"field": "organization_id", "code": "organization.archived"}
    ]


async def test_FR_OPP_01_update_with_version_and_probability_reset(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    opp = await create_opp(rep, amount="1000.00")
    response = await rep.patch(
        f"/api/v1/opportunities/{opp['id']}",
        json={"version": 1, "probability": 40, "next_step": "Send the offer"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["probability"], body["probability_overridden"], body["version"]) == (40, True, 2)
    assert body["weighted_amount"] == "400.00"
    stale = await rep.patch(f"/api/v1/opportunities/{opp['id']}", json={"version": 1, "name": "Y"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "conflict.version_mismatch"
    assert stale.json()["current"]["version"] == 2
    reset = await rep.patch(
        f"/api/v1/opportunities/{opp['id']}", json={"version": 2, "probability": None}
    )
    assert (reset.json()["probability"], reset.json()["probability_overridden"]) == (10, False)
    [entry, *_] = await test_app.audit("opportunity.updated")
    assert entry.before is not None
    assert entry.after is not None
    assert (entry.before["probability"], entry.after["probability"]) == (10, 40)


async def test_patch_refuses_action_only_fields(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    opp = await create_opp(rep)
    for field in ("stage_id", "owner_id", "organization_id"):
        response = await rep.patch(
            f"/api/v1/opportunities/{opp['id']}", json={"version": 1, field: str(uuid4())}
        )
        assert response.status_code == 422
        assert response.json()["errors"] == [
            {"field": field, "code": "validation.use_action_endpoint"}
        ]


async def test_FR_AUTH_05_rep_cannot_change_another_reps_opportunity(test_app: TestApp) -> None:
    owner, _ = await test_app.signed_in()
    other, _ = await test_app.signed_in()
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    opp = await create_opp(owner)
    qualification = (await stages(owner))["Qualification"]
    assert (
        await other.patch(f"/api/v1/opportunities/{opp['id']}", json={"version": 1, "name": "Mine"})
    ).status_code == 403
    assert (await act(other, opp, "move", stage_id=qualification["id"])).status_code == 403
    assert (await act(other, opp, "close", outcome="won")).status_code == 403
    assert (await other.delete(f"/api/v1/opportunities/{opp['id']}")).status_code == 403
    assert (await act(manager, opp, "move", stage_id=qualification["id"])).status_code == 200


# --- FR-OPP-02 / 03 move ---------------------------------------------------------------------


async def test_FR_OPP_02_AC2_move_records_history_and_resets_probability(
    test_app: TestApp,
) -> None:
    rep, _ = await test_app.signed_in()
    by_name = await stages(rep)
    opp = await create_opp(rep, amount="2000.00")
    moved = (await act(rep, opp, "move", stage_id=by_name["Solution & Proposal"]["id"])).json()
    assert (moved["stage"]["name_en"], moved["probability"], moved["version"]) == (
        "Solution & Proposal",
        50,
        2,
    )
    # An overridden probability survives later moves.
    moved = (
        await rep.patch(
            f"/api/v1/opportunities/{opp['id']}", json={"version": 2, "probability": 33}
        )
    ).json()
    moved = (await act(rep, moved, "move", stage_id=by_name["Negotiation"]["id"])).json()
    assert moved["probability"] == 33
    history = (await rep.get(f"/api/v1/opportunities/{opp['id']}/stage-history")).json()
    assert [
        (h["from_stage"] and h["from_stage"]["name_en"], h["to_stage"]["name_en"]) for h in history
    ] == [
        (None, "Prospecting"),
        ("Prospecting", "Solution & Proposal"),
        ("Solution & Proposal", "Negotiation"),
    ]
    assert len(await test_app.audit("opportunity.stage_changed")) == 2
    assert (await rep.get(f"/api/v1/opportunities/{uuid4()}/stage-history")).status_code == 404


async def test_move_only_between_open_stages(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    by_name = await stages(rep)
    opp = await create_opp(rep)
    for name in ("Closed Won", "Closed Lost"):
        response = await act(rep, opp, "move", stage_id=by_name[name]["id"])
        assert response.status_code == 422
        assert response.json()["errors"] == [{"field": "stage_id", "code": "stage.not_open"}]
    same = await act(rep, opp, "move", stage_id=by_name["Prospecting"]["id"])
    assert same.json()["version"] == 1


# --- FR-OPP-05 close and reopen ---------------------------------------------------------------


async def test_FR_OPP_05_close_won_with_actual_close_date(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    opp = await create_opp(rep, amount="1000.00")
    response = await act(rep, opp, "close", outcome="won")
    assert response.status_code == 200, response.text
    won = response.json()
    assert won["stage"]["stage_type"] == "won"
    assert won["probability"] == 100
    assert won["actual_close_date"] == "2026-11-17"  # business date in Sofia
    assert won["loss_reason"] is None
    assert len(await test_app.audit("opportunity.closed_won")) == 1


async def test_FR_OPP_05_lost_requires_a_loss_reason(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    opp = await create_opp(rep)
    response = await act(rep, opp, "close", outcome="lost")
    assert response.status_code == 422
    assert response.json()["code"] == "opportunity.loss_reason_required"
    response = await act(rep, opp, "close", outcome="lost", loss_reason_id=str(uuid4()))
    assert response.json()["errors"] == [{"field": "loss_reason_id", "code": "reference.invalid"}]
    reason = await loss_reason(rep, "chose_competitor")
    response = await act(
        rep,
        opp,
        "close",
        outcome="lost",
        loss_reason_id=reason,
        competitor="Друг оператор",
        actual_close_date="2026-11-10",
    )
    lost = response.json()
    assert lost["stage"]["stage_type"] == "lost"
    assert (lost["probability"], lost["actual_close_date"]) == (0, "2026-11-10")
    assert lost["loss_reason"]["code"] == "chose_competitor"
    assert lost["competitor"] == "Друг оператор"
    assert len(await test_app.audit("opportunity.closed_lost")) == 1


async def test_FR_OPP_05_closed_is_read_only_until_a_manager_reopens(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    by_name = await stages(rep)
    opp = await create_opp(rep)
    closed = (await act(rep, opp, "close", outcome="won")).json()
    for response in (
        await rep.patch(f"/api/v1/opportunities/{opp['id']}", json={"version": 2, "name": "Y"}),
        await act(rep, closed, "move", stage_id=by_name["Negotiation"]["id"]),
        await act(rep, closed, "close", outcome="won"),
    ):
        assert response.status_code == 409
        assert response.json()["code"] == "opportunity.closed"
    assert (
        await act(rep, closed, "reopen", stage_id=by_name["Negotiation"]["id"])
    ).status_code == 403
    response = await act(manager, closed, "reopen", stage_id=by_name["Negotiation"]["id"])
    assert response.status_code == 200, response.text
    reopened = response.json()
    assert reopened["stage"]["name_en"] == "Negotiation"
    assert (reopened["probability"], reopened["actual_close_date"]) == (75, None)
    again = await act(manager, reopened, "reopen", stage_id=by_name["Negotiation"]["id"])
    assert again.json()["code"] == "opportunity.not_closed"
    history = (await rep.get(f"/api/v1/opportunities/{opp['id']}/stage-history")).json()
    assert [h["to_stage"]["name_en"] for h in history] == [
        "Prospecting",
        "Closed Won",
        "Negotiation",
    ]
    assert len(await test_app.audit("opportunity.reopened")) == 1


# --- Assign, archive, restore -----------------------------------------------------------------


async def test_FR_LEAD_06_opportunity_assignment_rules(test_app: TestApp) -> None:
    rep, rep_user = await test_app.signed_in()
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    colleague = await test_app.create_user()
    opp = await create_opp(rep)
    refused = await act(rep, opp, "assign", owner_id=str(colleague.id))
    assert refused.status_code == 403
    response = await act(manager, opp, "assign", owner_id=str(colleague.id))
    assert response.status_code == 200
    assert response.json()["owner"]["id"] == str(colleague.id)
    [entry] = await test_app.audit("opportunity.owner_changed")
    assert entry.before is not None
    assert entry.before["owner_id"] == str(rep_user.id)
    inactive = await test_app.create_user(is_active=False)
    response = await act(manager, response.json(), "assign", owner_id=str(inactive.id))
    assert response.json()["errors"] == [{"field": "owner_id", "code": "owner.invalid"}]


async def test_archive_and_restore(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    opp = await create_opp(rep)
    assert (await rep.delete(f"/api/v1/opportunities/{opp['id']}")).status_code == 204
    listed = (await rep.get("/api/v1/opportunities")).json()
    assert listed["total"] == 0
    archived = (await rep.get("/api/v1/opportunities?include_archived=true")).json()
    assert archived["total"] == 1
    response = await rep.patch(
        f"/api/v1/opportunities/{opp['id']}", json={"version": 2, "name": "Y"}
    )
    assert response.json()["code"] == "resource.archived"
    restored = await manager.post(f"/api/v1/opportunities/{opp['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    assert [e.action for e in await test_app.audit() if e.entity_type == "opportunity"][-2:] == [
        "opportunity.archived",
        "opportunity.restored",
    ]


# --- FR-OPP-04 list, FR-OPP-06 stale ------------------------------------------------------


async def test_FR_OPP_04_list_filters_sort_and_search(test_app: TestApp) -> None:
    rep, rep_user = await test_app.signed_in()
    other, _ = await test_app.signed_in()
    by_name = await stages(rep)
    org = await create_org(rep, "Гама ООД")
    small = await create_opp(rep, org, name="Small fibre", amount="100.00")
    big = await create_opp(rep, name="Big data centre", amount="90000.00")
    theirs = await create_opp(other, name="Their deal", amount="500.00")
    await act(rep, big, "move", stage_id=by_name["Negotiation"]["id"])
    await act(other, theirs, "close", outcome="won")

    async def names(query: str) -> list[str]:
        response = await rep.get(f"/api/v1/opportunities?{query}")
        assert response.status_code == 200, response.text
        return [o["name"] for o in response.json()["items"]]

    assert await names("sort=amount") == ["Small fibre", "Their deal", "Big data centre"]
    assert await names("owner_id=me&sort=name") == ["Big data centre", "Small fibre"]
    assert await names("stage_type=won") == ["Their deal"]
    assert await names(f"stage_id={by_name['Negotiation']['id']}") == ["Big data centre"]
    assert await names(f"organization_id={org['id']}") == ["Small fibre"]
    assert await names("amount_from=200&amount_to=1000") == ["Their deal"]
    assert await names("q=гама") == ["Small fibre"]  # organization name, Cyrillic
    assert await names("q=gama") == ["Small fibre"]  # and transliterated
    assert await names("is_stale=true") == []
    unknown = await rep.get("/api/v1/opportunities?colour=red")
    assert unknown.status_code == 400
    assert str(rep_user.id) in {
        o["owner"]["id"] for o in (await rep.get("/api/v1/opportunities")).json()["items"]
    }
    assert small["id"]


async def test_FR_OPP_06_stale_when_idle_or_past_expected_close(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    overdue = await create_opp(rep, name="Overdue", expected_close_date="2026-11-16")
    idle = await create_opp(rep, name="Idle")
    fresh = await create_opp(rep, name="Fresh", expected_close_date="2026-12-31")
    async with test_app.sessions() as session:
        await session.execute(
            update(Opportunity)
            .where(Opportunity.id.in_([UUID(idle["id"]), UUID(fresh["id"])]))
            .values(created_at=test_app.clock.now() - timedelta(days=10))
        )
        await session.commit()
    stale = (await rep.get("/api/v1/opportunities?is_stale=true&sort=name")).json()
    assert [o["name"] for o in stale["items"]] == ["Overdue"]
    assert (await rep.get(f"/api/v1/opportunities/{overdue['id']}")).json()["is_stale"] is True

    # Lower the threshold to 7 days: idle ones become stale too (setting is Admin-only).
    await admin.patch("/api/v1/settings", json={"stale_opportunity_days": 7})
    runtime_settings.invalidate_cache()
    stale = (await rep.get("/api/v1/opportunities?is_stale=true&sort=name")).json()
    assert [o["name"] for o in stale["items"]] == ["Fresh", "Idle", "Overdue"]
    not_stale = (await rep.get("/api/v1/opportunities?is_stale=false")).json()
    assert not_stale["total"] == 0

    # Closed opportunities are never stale.
    closed = (await act(rep, overdue, "close", outcome="won")).json()
    assert closed["is_stale"] is False


# --- FR-OPP-03 board ---------------------------------------------------------------------------


async def test_FR_OPP_03_board_columns_totals_and_can_edit(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    other, _ = await test_app.signed_in()
    viewer, _ = await test_app.signed_in(RoleCode.VIEWER)
    by_name = await stages(rep)
    a = await create_opp(rep, name="A", amount="1000.00", expected_close_date="2027-01-31")
    await create_opp(rep, name="B", amount="3000.00", expected_close_date="2027-01-15")
    await create_opp(rep, name="No amount")
    c = await create_opp(other, name="C", amount="10000.00")
    await act(other, c, "move", stage_id=by_name["Negotiation"]["id"])
    won = await create_opp(rep, name="Won", amount="99999.00")
    await act(rep, won, "close", outcome="won")
    archived = await create_opp(rep, name="Archived", amount="5.00")
    await rep.delete(f"/api/v1/opportunities/{archived['id']}")

    response = await rep.get("/api/v1/opportunities/board")
    assert response.status_code == 200, response.text
    board = response.json()
    assert board["currency"] == "EUR"
    assert board["truncated"] is False
    assert [col["stage"]["name_en"] for col in board["columns"]] == [
        "Prospecting",
        "Qualification",
        "Solution & Proposal",
        "Negotiation",
    ]
    prospecting, qualification, _, negotiation = board["columns"]
    assert (prospecting["count"], prospecting["total_amount"], prospecting["weighted_amount"]) == (
        3,
        "4000.00",
        "400.00",
    )
    assert [card["name"] for card in prospecting["cards"]] == ["B", "A", "No amount"]
    assert all(card["can_edit"] for card in prospecting["cards"])
    assert (qualification["count"], qualification["total_amount"]) == (0, "0.00")
    assert (negotiation["count"], negotiation["weighted_amount"]) == (1, "7500.00")
    assert negotiation["cards"][0]["can_edit"] is False
    assert a["id"] in {card["id"] for card in prospecting["cards"]}

    mine = (await rep.get("/api/v1/opportunities/board?owner_id=me")).json()
    assert [col["count"] for col in mine["columns"]] == [3, 0, 0, 0]
    window = (
        await rep.get(
            "/api/v1/opportunities/board?expected_close_date_from=2027-01-20"
            "&expected_close_date_to=2027-02-28"
        )
    ).json()
    assert [card["name"] for card in window["columns"][0]["cards"]] == ["A"]
    seen = (await viewer.get("/api/v1/opportunities/board")).json()
    assert not any(card["can_edit"] for col in seen["columns"] for card in col["cards"])


# --- Contributions to party, search and reference data -------------------------------------


async def test_FR_PARTY_03_organization_counts_and_opportunities(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    first = await create_opp(rep, org, amount="1500.50")
    await create_opp(rep, org, amount="500.00")
    lost = await create_opp(rep, org, amount="999.00")
    await act(rep, lost, "close", outcome="lost", loss_reason_id=await loss_reason(rep))
    counts = (await rep.get(f"/api/v1/organizations/{org['id']}")).json()["counts"]
    assert (counts["open_opportunities"], counts["open_pipeline_value"]) == (2, "2000.50")
    listed = (await rep.get(f"/api/v1/organizations/{org['id']}/opportunities")).json()
    assert listed["total"] == 3
    assert first["id"] in {o["id"] for o in listed["items"]}


async def test_organization_archive_blocked_while_open_opportunities(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    opp = await create_opp(rep, org)
    response = await rep.delete(f"/api/v1/organizations/{org['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "organization.has_open_opportunities"
    await act(rep, opp, "close", outcome="won")
    assert (await rep.delete(f"/api/v1/organizations/{org['id']}")).status_code == 204


async def test_FR_PARTY_04_search_finds_opportunities(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep, "Делта ЕООД")
    opp = await create_opp(rep, org, name="Облачна телефония")
    response = await rep.get("/api/v1/search?q=oblachna&types=opportunity")
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {
            "type": "opportunity",
            "id": opp["id"],
            "label": "Облачна телефония",
            "detail": "Делта ЕООД",
        }
    ]


async def test_FR_ADM_02_loss_reasons_are_seeded_and_protected_when_used(
    test_app: TestApp,
) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    items = (await admin.get("/api/v1/reference/loss-reasons")).json()
    assert [i["code"] for i in items] == [
        "price",
        "chose_competitor",
        "no_budget",
        "no_decision",
        "timing",
        "solution_fit",
        "other",
    ]
    assert items[0]["name_bg"] == "Цена"
    opp = await create_opp(admin)
    await act(admin, opp, "close", outcome="lost", loss_reason_id=items[0]["id"])
    response = await admin.delete(f"/api/v1/reference/loss-reasons/{items[0]['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "reference.in_use"
    assert (
        await admin.delete(f"/api/v1/reference/loss-reasons/{items[-1]['id']}")
    ).status_code == 204


async def test_FR_INT_05_opportunities_support_sync_mode(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    org = await create_org(rep)
    ids = [(await create_opp(rep, org, name=f"Sync {i}"))["id"] for i in range(3)]
    await rep.delete(f"/api/v1/opportunities/{ids[0]}")
    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"updated_since": "2000-01-01T00:00:00Z", "page_size": 2}
        if cursor:
            params["cursor"] = cursor
        body = (await rep.get("/api/v1/opportunities", params=params)).json()
        assert set(body) == {"items", "next_cursor"}
        seen += [o["id"] for o in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == sorted(ids)  # archived row included
