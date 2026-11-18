"""FR-INT-10: the request collection handed to integrators matches the API."""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from app.core.config import Environment, Settings
from app.main import create_app

COLLECTION = (
    Path(__file__).parents[3] / "docs" / "integration" / "light-crm.postman_collection.json"
)


def _requests(items: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for item in items:
        if "item" in item:
            yield from _requests(item["item"])
        else:
            yield item["request"]


def test_FR_INT_10_collection_requests_match_routes() -> None:
    collection = json.loads(COLLECTION.read_text())
    assert collection["info"]["schema"].endswith("/v2.1.0/collection.json")
    assert collection["auth"]["type"] == "bearer"
    app = create_app(Settings(env=Environment.DEVELOPMENT))
    # Routes as published in the OpenAPI document (what integrators see).
    routes = [
        (method.upper(), re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$"))
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    ]
    routes.append(("GET", re.compile(r"^/api/v1/openapi\.json$")))
    requests = list(_requests(collection["item"]))
    assert len(requests) >= 15
    for request in requests:
        path = "/" + "/".join(request["url"]["path"])
        assert any(
            method == request["method"] and pattern.match(path) for method, pattern in routes
        ), (request["method"], path)
