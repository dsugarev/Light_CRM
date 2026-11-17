"""Access levels declared on every route (docs/05-api-specification.md section 1.7).

Each route states its level once with `**endpoint(AccessLevel.X, scope=...)`
(app/core/auth.py). The level is published in the OpenAPI document as
`x-access-level` (and the integration scope as `x-required-scope`), enforced by
the permission dependency, and compared with the specification by the route
catalog and authorization matrix tests.
"""

from enum import StrEnum
from typing import Any

ACCESS_EXTENSION = "x-access-level"
SCOPE_EXTENSION = "x-required-scope"


class AccessLevel(StrEnum):
    """Values are the exact wording used in the specification tables."""

    PUBLIC = "Public"
    SIGNED_IN = "Signed-in"
    SIGNED_IN_OR_ANY_CLIENT = "Signed-in or any integration client"
    CONTRIBUTOR = "Contributor"
    OWNER_PLUS = "Owner+"
    MANAGER_PLUS = "Manager+"
    ADMIN = "Admin"


def access(level: AccessLevel, scope: str | None = None) -> dict[str, Any]:
    """Route `openapi_extra` that records the access level in the OpenAPI document."""
    extra: dict[str, Any] = {ACCESS_EXTENSION: level.value}
    if scope is not None:
        extra[SCOPE_EXTENSION] = scope
    return extra
