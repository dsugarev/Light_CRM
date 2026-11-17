"""Access levels declared on every route (docs/05-api-specification.md section 1.7).

Each route states its level once, with `openapi_extra=access(...)`. The route
catalog test compares the declared level with the API specification. Phase 1
adds the permission dependency that enforces the levels; until then only
Public routes exist.
"""

from enum import StrEnum
from typing import Any

ACCESS_EXTENSION = "x-access-level"


class AccessLevel(StrEnum):
    """Values are the exact wording used in the specification tables."""

    PUBLIC = "Public"
    SIGNED_IN = "Signed-in"
    CONTRIBUTOR = "Contributor"
    OWNER_PLUS = "Owner+"
    MANAGER_PLUS = "Manager+"
    ADMIN = "Admin"


def access(level: AccessLevel) -> dict[str, Any]:
    """Route `openapi_extra` that records the access level in the OpenAPI document."""
    return {ACCESS_EXTENSION: level.value}
