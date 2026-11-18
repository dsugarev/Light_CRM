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
    # The caller's own data only (assistant conversations); others' return 404.
    SIGNED_IN_OWN = "Signed-in (own only)"
    SIGNED_IN_OR_ANY_CLIENT = "Signed-in or any integration client"
    CONTRIBUTOR = "Contributor"
    # Contributors may call it; the service applies finer rules (e.g. assign, FR-LEAD-06).
    CONTRIBUTOR_RULES_IN_SERVICE = "Contributor (rules in service)"
    OWNER_PLUS = "Owner+"
    # Activities (API spec 11): the record rule involves the task assignee.
    OWNER_PLUS_OR_TASK_ASSIGNEE = "Owner+ (owner = activity owner; assignee may update a task)"
    OWNER_PLUS_OR_ASSIGNEE = "Owner+ or assignee"
    # External references (API spec 19.4): people by role, integrations by the scope of
    # the record type or of their own system, checked by the service where it depends
    # on the record.
    SIGNED_IN_OR_TYPE_SCOPE = "Signed-in; Integration: read scope of the resolved type"
    SIGNED_IN_OR_RESOURCE_SCOPE = "Signed-in; Integration: read scope of {resource}"
    ADMIN_OR_OWN_SYSTEM = (
        "Admin; Integration: external-references:write and {system} equals the client's system"
    )
    ADMIN_OR_OWN_SYSTEM_DELETE = "Admin; Integration: as for PUT"
    MANAGER_PLUS = "Manager+"
    ADMIN = "Admin"


def access(level: AccessLevel, scope: str | None = None) -> dict[str, Any]:
    """Route `openapi_extra` that records the access level in the OpenAPI document."""
    extra: dict[str, Any] = {ACCESS_EXTENSION: level.value}
    if scope is not None:
        extra[SCOPE_EXTENSION] = scope
    return extra
