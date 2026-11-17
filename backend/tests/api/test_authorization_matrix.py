"""Route x role authorization matrix (test strategy section 3, FR-AUTH-05).

Every registered API route is called by an anonymous caller and by each human
role. The expected outcome comes from the access level in
docs/05-api-specification.md, not from the code. A route whose level is not in
EXPECTED fails, so every new route must be accounted for here.

Integration principals (scopes) are covered by tests/unit/test_policy.py until
API keys exist (Phase 6), when they join this matrix.
"""

import re
from uuid import uuid4

import httpx
import pytest

from app.core.access import ACCESS_EXTENSION
from app.core.config import Environment, Settings
from app.core.principal import RoleCode
from app.main import create_app
from tests.api.spec_catalog import load_catalog
from tests.helpers import TestApp

CALLERS = ["anonymous", "admin", "sales_manager", "sales_rep", "viewer"]
HUMANS = {"admin", "sales_manager", "sales_rep", "viewer"}

# Callers allowed past the permission check, per access level wording in the spec.
EXPECTED: dict[str, set[str]] = {
    "Public": set(CALLERS),
    "Signed-in": HUMANS,
    "Signed-in or any integration client": HUMANS,
    "Contributor": {"admin", "sales_manager", "sales_rep"},
    "Contributor (rules in service)": {"admin", "sales_manager", "sales_rep"},
    "Owner+": {"admin", "sales_manager", "sales_rep"},  # ownership checked per record
    "Manager+": {"admin", "sales_manager"},
    "Admin": {"admin"},
}

_SPEC = {entry.key: entry.access for entry in load_catalog()}
_ROUTES = sorted(
    f"{method.upper()} {path}"
    for path, operations in create_app(Settings(env=Environment.DEVELOPMENT))
    .openapi()["paths"]
    .items()
    for method, operation in operations.items()
    if ACCESS_EXTENSION in operation and path.startswith("/api/v1/")
)


def _request_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid4()), path)


@pytest.mark.parametrize("route", _ROUTES)
async def test_FR_AUTH_05_route_role_matrix(test_app: TestApp, route: str) -> None:
    level = _SPEC[route]
    assert level in EXPECTED, f"{route}: access level {level!r} has no matrix entry"
    method, path = route.split(" ", 1)

    clients: dict[str, httpx.AsyncClient] = {"anonymous": test_app.client()}
    for role in HUMANS:
        user = await test_app.create_user(RoleCode(role))
        clients[role] = await test_app.session_client(user)

    for caller in CALLERS:
        body: dict[str, object] | None = {} if method in {"POST", "PUT", "PATCH"} else None
        response = await clients[caller].request(method, _request_path(path), json=body)
        if caller in EXPECTED[level]:
            assert response.status_code not in {401, 403}, (
                f"{caller} should pass {route} ({level}), got {response.status_code}: "
                f"{response.text}"
            )
        elif caller == "anonymous":
            assert response.status_code == 401, f"anonymous on {route}: {response.status_code}"
            assert response.json()["code"] == "auth.session_expired"
        else:
            assert response.status_code == 403, f"{caller} on {route}: {response.status_code}"
            assert response.json()["code"] == "permission.denied"


def test_matrix_covers_every_api_route() -> None:
    assert len(_ROUTES) >= 26
    assert all(route in _SPEC for route in _ROUTES)
