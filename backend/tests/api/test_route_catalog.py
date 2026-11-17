"""Registered routes match the endpoint catalog (test strategy section 3).

- Every registered route is listed in docs/05-api-specification.md.
- Every API route declares an access level equal to the one in the catalog.
- Every catalog entry has a route, unless it is listed as pending.

Phase 1 extends this into the full route x role authorization matrix.
"""

from pathlib import Path

import pytest
from starlette.routing import Route

from app.core.access import ACCESS_EXTENSION
from app.core.config import Environment, Settings
from app.main import create_app
from tests.api.catalog_pending import PENDING
from tests.api.spec_catalog import load_catalog

APP_DIR = Path(__file__).resolve().parents[2] / "app"
_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

_app = create_app(Settings(env=Environment.DEVELOPMENT))

# API routes, read from the public OpenAPI document: "METHOD path" -> access level.
API_ROUTES: dict[str, str | None] = {
    f"{method.upper()} {path}": operation.get(ACCESS_EXTENSION)
    for path, operations in _app.openapi()["paths"].items()
    for method, operation in operations.items()
    if method in _HTTP_METHODS
}
# Routes FastAPI adds itself (OpenAPI document, docs UI) are plain Starlette routes.
FRAMEWORK_ROUTES = {
    f"{method} {route.path}"
    for route in _app.routes
    if isinstance(route, Route)
    for method in (route.methods or set()) - {"HEAD"}
}
REGISTERED = set(API_ROUTES) | FRAMEWORK_ROUTES
CATALOG = {entry.key: entry for entry in load_catalog()}


def test_catalog_is_parsed() -> None:
    # Guards against the parser silently matching nothing after a doc edit.
    assert len(CATALOG) > 100


@pytest.mark.parametrize("key", sorted(REGISTERED))
def test_every_route_is_in_the_catalog(key: str) -> None:
    assert key in CATALOG, f"{key} is not in docs/05-api-specification.md; add it there first"
    assert key not in PENDING, f"{key} is built; remove it from tests/api/catalog_pending.py"


@pytest.mark.parametrize("key", sorted(API_ROUTES))
def test_every_api_route_declares_the_catalog_access_level(key: str) -> None:
    declared = API_ROUTES[key]
    expected = CATALOG[key].access
    assert declared == expected, f"{key}: declared {declared!r}, spec says {expected!r}"


@pytest.mark.parametrize("key", sorted(CATALOG))
def test_every_catalog_entry_is_built_or_pending(key: str) -> None:
    assert key in REGISTERED or key in PENDING, f"{key} has no route and is not pending"


def test_pending_list_only_names_catalog_entries() -> None:
    assert set(PENDING) <= set(CATALOG)


def test_no_route_is_hidden_from_the_openapi_document() -> None:
    # Hidden routes would escape this test and the authorization matrix.
    offenders = [
        str(path.relative_to(APP_DIR))
        for path in APP_DIR.rglob("*.py")
        if "include_in_schema=False" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
