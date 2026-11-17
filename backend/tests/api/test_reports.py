"""Reports and dashboard (FR-REP-01, FR-REP-03; API spec 13). Fictional data only.

The test clock stands at 2026-11-17, so the 6-month forecast covers 2026-11 .. 2027-04.
"""

import csv
import io
from decimal import Decimal
from typing import Any

import httpx

from app.core.principal import RoleCode
from tests.api.test_leads import BANT_COMPLETE
from tests.api.test_leads import act as lead_act
from tests.api.test_opportunities import act, create_opp, create_org, loss_reason, stages
from tests.helpers import TestApp


async def report(client: httpx.AsyncClient, path: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/reports/{path}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def test_FR_REP_01_AC1_forecast_matches_an_independent_calculation(
    test_app: TestApp,
) -> None:
    rep, _ = await test_app.signed_in()
    other, _ = await test_app.signed_in()
    by_name = await stages(rep)
    org = await create_org(rep)
    # (owner, amount, expected close, stage, probability override, archived/closed)
    deals = [
        (rep, "10000.00", "2026-11-30", "Prospecting", None, None),
        (rep, "3333.33", "2026-11-03", "Negotiation", 33, None),  # earlier this month counts
        (other, "20000.00", "2026-12-15", "Qualification", None, None),
        (rep, "999.99", "2027-04-30", "Solution & Proposal", 7, None),
        (rep, "5000.00", "2027-05-01", "Prospecting", None, None),  # outside the window
        (rep, "8000.00", "2026-10-31", "Prospecting", None, None),  # before the window
        (rep, "7000.00", "2026-12-01", "Prospecting", None, "archived"),
        (rep, "6000.00", "2026-12-02", "Prospecting", None, "won"),
        (rep, None, "2027-01-10", "Negotiation", None, None),  # no amount: count only
    ]
    for owner, amount, close, stage, probability, state in deals:
        fields: dict[str, Any] = {"expected_close_date": close, "stage_id": by_name[stage]["id"]}
        if amount:
            fields["amount"] = amount
        if probability is not None:
            fields["probability"] = probability
        opp = await create_opp(owner, org, **fields)
        if state == "archived":
            await owner.delete(f"/api/v1/opportunities/{opp['id']}")
        elif state == "won":
            await act(owner, opp, "close", outcome="won")

    # Independent calculation from the table above (stage defaults 10/25/50/75).
    defaults = {
        "Prospecting": 10,
        "Qualification": 25,
        "Solution & Proposal": 50,
        "Negotiation": 75,
    }
    expected: dict[str, Decimal] = {}
    for _, amount, close, stage, probability, state in deals:
        month = close[:7]
        if state or not amount or not "2026-11" <= month <= "2027-04":
            continue
        share = Decimal(probability if probability is not None else defaults[stage]) / 100
        expected[month] = expected.get(month, Decimal(0)) + Decimal(amount) * share
    body = await report(rep, "forecast")
    got = {m["month"]: Decimal(m["weighted_amount"]) for m in body["months"]}
    assert [m["month"] for m in body["months"]] == [
        "2026-11", "2026-12", "2027-01", "2027-02", "2027-03", "2027-04",
    ]  # fmt: skip
    for month, value in got.items():
        assert value == expected.get(month, Decimal(0)).quantize(Decimal("0.01")), month
    assert got["2026-11"] == Decimal("2100.00")  # 1000.00 + 3333.33 × 33 % = 2099.9989
    assert next(m for m in body["months"] if m["month"] == "2027-01")["count"] == 1
    mine = await report(rep, "forecast?owner_id=me&months=2")
    assert [m["weighted_amount"] for m in mine["months"]] == ["2100.00", "0.00"]


async def test_FR_REP_01_pipeline_by_stage(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    by_name = await stages(rep)
    await create_opp(rep, amount="1000.00")
    await create_opp(rep, amount="3000.00", stage_id=by_name["Negotiation"]["id"])
    won = await create_opp(rep, amount="50000.00")
    await act(rep, won, "close", outcome="won")
    body = await report(rep, "pipeline-by-stage")
    figures = {s["stage"]["name_en"]: (s["count"], s["total_amount"], s["weighted_amount"])
               for s in body["stages"]}  # fmt: skip
    assert figures == {
        "Prospecting": (1, "1000.00", "100.00"),
        "Qualification": (0, "0.00", "0.00"),
        "Solution & Proposal": (0, "0.00", "0.00"),
        "Negotiation": (1, "3000.00", "2250.00"),
    }
    assert (body["count"], body["total_amount"], body["weighted_amount"]) == (
        2,
        "4000.00",
        "2350.00",
    )


async def _lead(client: httpx.AsyncClient, *, to: str, source: str | None = None) -> None:
    fields: dict[str, Any] = {"title": f"Lead {to}", "company_name": "Делта"}
    if source:
        items = (await client.get("/api/v1/reference/lead-sources")).json()
        fields["source_id"] = next(i["id"] for i in items if i["code"] == source)
    lead = (await client.post("/api/v1/leads", json=fields)).json()
    if to == "new":
        return
    if to == "disqualified":
        reasons = (await client.get("/api/v1/reference/disqualification-reasons")).json()
        await lead_act(client, lead, "disqualify", reason_id=reasons[0]["id"])
        return
    lead = (await lead_act(client, lead, "mark-contacted")).json()
    lead = (
        await client.patch(
            f"/api/v1/leads/{lead['id']}",
            json={"version": lead["version"], "qualification": BANT_COMPLETE},
        )
    ).json()
    lead = (await lead_act(client, lead, "qualify")).json()
    if to == "converted":
        response = await client.post(
            f"/api/v1/leads/{lead['id']}/convert",
            json={
                "version": lead["version"],
                "organization": {"new": {"name": "Конв ЕООД", "confirm_duplicate": True}},
                "opportunity": {"name": "From lead"},
            },
        )
        assert response.status_code == 201, response.text


async def test_FR_REP_01_lead_conversion_rate_and_groups(test_app: TestApp) -> None:
    rep, rep_user = await test_app.signed_in(full_name="Rep One")
    other, _ = await test_app.signed_in(full_name="Rep Two")
    await _lead(rep, to="converted", source="inbound")
    await _lead(rep, to="qualified", source="inbound")
    await _lead(rep, to="disqualified", source="event")
    await _lead(rep, to="new")
    await _lead(other, to="converted")
    body = await report(rep, "lead-conversion?group_by=owner")
    assert body["totals"] == {
        "created": 5, "qualified": 3, "converted": 2, "disqualified": 1, "conversion_rate": 0.4,
    }  # fmt: skip
    assert (body["from_date"], body["to_date"]) == ("2026-01-01", "2026-12-31")
    groups = {g["group"]["name_en"]: (g["created"], g["conversion_rate"]) for g in body["groups"]}
    assert groups == {"Rep One": (4, 0.25), "Rep Two": (1, 1.0)}
    by_source = await report(rep, f"lead-conversion?group_by=source&owner_id={rep_user.id}")
    sources = {g["group"]["key"] if g["group"]["name_en"] is None else g["group"]["name_en"]:
               g["created"] for g in by_source["groups"]}  # fmt: skip
    assert sources == {"Inbound inquiry": 2, "Event": 1, "none": 1}
    last_year = await report(rep, "lead-conversion?from=2025-01-01&to=2025-12-31")
    assert last_year["totals"]["created"] == 0
    assert last_year["totals"]["conversion_rate"] is None


async def test_FR_REP_03_win_loss_by_reason_owner_and_month(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in(full_name="Rep One")
    price = await loss_reason(rep, "price")
    timing = await loss_reason(rep, "timing")
    closes = [
        ("won", None, "1000.00", "2026-03-10"),
        ("won", None, "2000.00", "2026-11-01"),
        ("lost", price, "500.00", "2026-11-02"),
        ("lost", price, "700.00", "2026-03-15"),
        ("lost", timing, "300.00", "2026-11-05"),
        ("won", None, "9999.00", "2025-12-31"),  # previous year: outside the default period
    ]
    for outcome, reason, amount, day in closes:
        opp = await create_opp(rep, amount=amount)
        await act(rep, opp, "close", outcome=outcome, loss_reason_id=reason, actual_close_date=day)
    body = await report(rep, "win-loss?group_by=loss_reason")
    assert body["totals"] == {
        "won_count": 2, "won_amount": "3000.00", "lost_count": 3, "lost_amount": "1500.00",
        "win_rate": 0.4,
    }  # fmt: skip
    reasons = {g["group"]["name_en"] or "none": (g["won_count"], g["lost_count"])
               for g in body["groups"]}  # fmt: skip
    assert reasons == {"Price": (0, 2), "Timing": (0, 1), "none": (2, 0)}
    months = await report(rep, "win-loss?group_by=month")
    assert [(g["group"]["key"], g["win_rate"]) for g in months["groups"]] == [
        ("2026-03", 0.5),
        ("2026-11", round(1 / 3, 4)),
    ]
    november = await report(rep, "win-loss?from=2026-11-01&to=2026-11-30")
    assert (november["totals"]["won_count"], november["totals"]["lost_count"]) == (1, 2)


async def test_FR_REP_01_dashboard_in_one_call(test_app: TestApp) -> None:
    rep, user = await test_app.signed_in()
    viewer, _ = await test_app.signed_in(RoleCode.VIEWER)
    org = await create_org(rep)
    await create_opp(rep, org, amount="1000.00", expected_close_date="2026-12-10")
    won = await create_opp(rep, org, amount="500.00")
    await act(rep, won, "close", outcome="won")
    for due in ("2026-11-10T09:00:00Z", "2026-12-10T09:00:00Z"):
        await rep.post(
            "/api/v1/activities",
            json={"type": "task", "subject": "T", "organization_id": org["id"], "due_at": due},
        )
    body = await report(rep, "dashboard?owner_id=me")
    assert body["pipeline"]["total_amount"] == "1000.00"
    assert body["forecast"]["months"][1] == {
        "month": "2026-12", "count": 1, "total_amount": "1000.00", "weighted_amount": "100.00",
    }  # fmt: skip
    assert body["win_loss"]["won_count"] == 1
    assert body["lead_conversion"]["created"] == 0
    assert body["my_tasks"] == {"open": 2, "overdue": 1}
    seen = await report(viewer, "dashboard")
    assert seen["pipeline"]["count"] == 1
    assert seen["my_tasks"] == {"open": 0, "overdue": 0}
    assert str(user.id)  # owner filter by ID works too
    assert (await report(rep, f"dashboard?owner_id={user.id}"))["pipeline"]["count"] == 1


async def test_report_parameters_are_validated(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    for path, field in (
        ("forecast?months=13", "months"),
        ("win-loss?from=2026-12-01&to=2026-01-01", "from"),
        ("dashboard?owner_id=someone", "owner_id"),
        ("lead-conversion?group_by=month", "group_by"),
    ):
        response = await rep.get(f"/api/v1/reports/{path}")
        assert response.status_code in (400, 422), path
        assert field in {e["field"] for e in response.json()["errors"]}, path
    assert (await rep.get("/api/v1/reports/dashboard/export")).status_code in (404, 422)


async def test_FR_REP_02_report_export_with_total_row(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    await create_opp(rep, amount="1000.00")
    response = await rep.get("/api/v1/reports/pipeline-by-stage/export?format=csv&locale=bg")
    assert response.status_code == 200, response.text
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == ["Етап", "Възможности", "Общо (EUR)", "Претеглено (EUR)"]
    assert rows[1] == ["Проучване", "1", "1000.00", "100.00"]
    assert rows[-1] == ["Общо", "1", "1000.00", "100.00"]
    assert len(await test_app.audit("report.exported")) == 1
    bad = await rep.get("/api/v1/reports/forecast/export?group_by=owner")
    assert bad.status_code == 400


async def test_FR_REP_02_forecast_conversion_and_win_loss_exports(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in(full_name="Rep One")
    await create_opp(rep, amount="2000.00", expected_close_date="2026-12-01")
    lost = await create_opp(rep, amount="300.00")
    await act(rep, lost, "close", outcome="lost", loss_reason_id=await loss_reason(rep))
    await _lead(rep, to="new")

    async def rows(path: str) -> list[list[str]]:
        response = await rep.get(f"/api/v1/reports/{path}")
        assert response.status_code == 200, response.text
        return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))

    forecast = await rows("forecast/export?format=csv&months=2")
    assert forecast == [
        ["Month", "Opportunities", "Total (EUR)", "Weighted (EUR)"],
        ["2026-11", "0", "0.00", "0.00"],
        ["2026-12", "1", "2000.00", "200.00"],
    ]
    conversion = await rows(
        "lead-conversion/export?format=csv&group_by=owner&columns=group,created"
    )
    assert conversion == [["Group", "Created"], ["Rep One", "1"], ["Total", "1"]]
    closed = await rows("win-loss/export?format=csv&locale=bg&group_by=loss_reason")
    assert closed[1][:4] == ["Цена", "0", "0.00", "1"]
    assert closed[-1][0] == "Общо"
