"""Sync mode for integrations (FR-INT-05; API spec section 1.3).

Integration clients arrive in Phase 6; the list machinery is built now and every
list endpoint reuses it, so its guarantees are tested here through users' calls.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text

from app.core.config import Settings
from app.main import create_app
from tests.helpers import TestApp, app_client

SINCE = "2000-01-01T00:00:00Z"


async def page(client: httpx.AsyncClient, path: str, **params: Any) -> dict[str, Any]:
    response = await client.get(path, params={"updated_since": SINCE, **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def drain(client: httpx.AsyncClient, path: str, page_size: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"page_size": page_size}
        if cursor:
            params["cursor"] = cursor
        body = await page(client, path, **params)
        items += body["items"]
        cursor = body["next_cursor"]
        if cursor is None:
            return items


async def test_FR_INT_05_sync_envelope_order_and_archived_rows(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    ids = []
    for i in range(5):
        created = await rep.post("/api/v1/organizations", json={"name": f"Sync Org {i}"})
        ids.append(created.json()["id"])
    await rep.delete(f"/api/v1/organizations/{ids[0]}")

    body = await page(rep, "/api/v1/organizations", page_size=2)
    assert set(body) == {"items", "next_cursor"}
    items = await drain(rep, "/api/v1/organizations", 2)
    assert sorted(i["id"] for i in items) == sorted(ids)  # archived row included
    keys = [(i["updated_at"], i["id"]) for i in items]
    assert keys == sorted(keys)


async def test_FR_INT_05_AC2_no_skips_or_repeats_while_data_changes(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    created = [
        (await rep.post("/api/v1/organizations", json={"name": f"Org {i}"})).json()["id"]
        for i in range(6)
    ]
    first = await page(rep, "/api/v1/organizations", page_size=3)
    seen = [i["id"] for i in first["items"]]
    # Meanwhile: one already-seen record changes and a new one appears.
    await rep.patch(f"/api/v1/organizations/{seen[0]}", json={"city": "Changed"})
    new = (await rep.post("/api/v1/organizations", json={"name": "Late"})).json()["id"]
    cursor = first["next_cursor"]
    while cursor:
        body = await page(rep, "/api/v1/organizations", page_size=3, cursor=cursor)
        seen += [i["id"] for i in body["items"]]
        cursor = body["next_cursor"]
    # Every record is delivered; the changed one again in its new version, after the rest.
    assert set(seen) == {*created, new}
    assert seen.count(seen[0]) == 2
    assert len(seen) == len(set(seen)) + 1


async def test_FR_INT_05_updated_since_filters_and_contacts_work_too(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    await rep.post("/api/v1/contacts", json={"first_name": "A", "last_name": "B"})
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    later = await rep.get("/api/v1/contacts", params={"updated_since": future})
    assert later.json() == {"items": [], "next_cursor": None}
    assert len((await page(rep, "/api/v1/contacts"))["items"]) == 1


async def test_cursors_cannot_be_tampered_with_or_reused_elsewhere(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    for i in range(3):
        await rep.post("/api/v1/organizations", json={"name": f"Org {i}"})
    cursor = (await page(rep, "/api/v1/organizations", page_size=1))["next_cursor"]
    payload, signature = cursor.split(".")
    tampered = f"{payload[:-2]}AA.{signature}"
    for bad, path in (
        (tampered, "/api/v1/organizations"),
        ("garbage", "/api/v1/organizations"),
        (cursor, "/api/v1/contacts"),  # valid signature, other list
    ):
        response = await rep.get(path, params={"updated_since": SINCE, "cursor": bad})
        assert response.status_code == 400
        assert response.json()["errors"] == [
            {"field": "cursor", "code": "validation.invalid_cursor"}
        ]
    without_since = await rep.get("/api/v1/organizations", params={"cursor": cursor})
    assert without_since.status_code == 400


async def test_sync_page_size_limits(test_app: TestApp) -> None:
    rep, _ = await test_app.signed_in()
    assert (
        await rep.get("/api/v1/organizations", params={"updated_since": SINCE, "page_size": 500})
    ).status_code == 200
    assert (
        await rep.get("/api/v1/organizations", params={"updated_since": SINCE, "page_size": 501})
    ).status_code == 400


async def test_rows_inside_the_safety_lag_are_held_back(
    test_app: TestApp, settings: Settings
) -> None:
    rep, user = await test_app.signed_in()
    await rep.post("/api/v1/organizations", json={"name": "Just written"})
    lagging = create_app(
        settings.model_copy(update={"sync_safety_lag_seconds": 3600}), clock=test_app.clock
    )
    async with app_client(lagging) as client:
        client.headers["X-Requested-With"] = "XMLHttpRequest"
        await test_app.login(client, user.email)
        body = await page(client, "/api/v1/organizations")
    assert body["items"] == []


@pytest.mark.parametrize("path", ["/api/v1/organizations", "/api/v1/contacts"])
async def test_sync_mode_needs_an_index_on_updated_at_and_id(test_app: TestApp, path: str) -> None:
    table = path.rsplit("/", 1)[1].rstrip("s")
    async with test_app.sessions() as session:
        indexes = (
            (
                await session.execute(
                    text("SELECT indexdef FROM pg_indexes WHERE tablename = :t"), {"t": table}
                )
            )
            .scalars()
            .all()
        )
    assert any("(updated_at, id)" in definition for definition in indexes)
