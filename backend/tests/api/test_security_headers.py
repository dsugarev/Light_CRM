"""Security pass (NFR-04, OWASP ASVS Level 1; docs/security/asvs-l1.md).

Headers set by Caddy (HSTS, CSP, nosniff, ...) are checked through the proxy by the
Playwright security journey; these tests cover what the backend itself sends.
"""

from app.core.principal import RoleCode
from tests.helpers import TestApp


async def test_ASVS_8_2_1_api_responses_are_not_cached(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in(RoleCode.ADMIN)
    for path in ("/api/v1/me", "/api/v1/organizations", "/api/v1/settings"):
        response = await client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "no-store", path
    anonymous = await test_app.client().get("/api/v1/me")
    assert anonymous.status_code == 401
    assert anonymous.headers["cache-control"] == "no-store"


async def test_ASVS_8_2_1_routes_may_set_their_own_cache_policy(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in(RoleCode.ADMIN)
    org = await client.post("/api/v1/organizations", json={"name": "Кеш ООД"})
    contact = await client.post(
        "/api/v1/contacts",
        json={"first_name": "A", "last_name": "B", "organization_id": org.json()["id"]},
    )
    export = await client.get(f"/api/v1/contacts/{contact.json()['id']}/personal-data")
    assert export.headers["cache-control"] == "no-store"
    assert export.headers["content-disposition"].startswith("attachment;")


async def test_ASVS_4_2_2_state_changing_requests_need_the_csrf_header(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in()
    bare = test_app.client(csrf=False, cookies=client.cookies)
    response = await bare.post("/api/v1/organizations", json={"name": "Forged"})
    assert response.status_code == 403
    assert response.json()["code"] == "auth.csrf_failed"
    cross_site = await client.post(
        "/api/v1/organizations",
        json={"name": "Forged"},
        headers={"Origin": "https://evil.example.test"},
    )
    assert cross_site.status_code == 403


async def test_ASVS_7_4_1_errors_carry_a_code_and_request_id_only(test_app: TestApp) -> None:
    client, _ = await test_app.signed_in()
    response = await client.get("/api/v1/organizations/not-a-uuid")
    body = response.json()
    assert response.status_code == 422
    assert set(body) <= {"type", "title", "status", "code", "request_id", "detail", "errors"}
    assert "Traceback" not in response.text
