"""The caller of a request: a human user or an integration client.

Services receive a `Principal`, never a cookie or an API key (architecture
section 3). Integration clients (Phase 6) are principals of type INTEGRATION
backed by a service user; they reuse the same services and policy.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID


class PrincipalType(StrEnum):
    USER = "user"
    INTEGRATION = "integration"


class RoleCode(StrEnum):
    ADMIN = "admin"
    SALES_MANAGER = "sales_manager"
    SALES_REP = "sales_rep"
    VIEWER = "viewer"
    INTEGRATION = "integration"


@dataclass(frozen=True, slots=True)
class Principal:
    type: PrincipalType
    user_id: UUID
    role: RoleCode
    display_name: str
    scopes: frozenset[str] = field(default_factory=frozenset)
    # The session the request was authenticated with (users only).
    session_id: UUID | None = None

    @property
    def is_integration(self) -> bool:
        return self.type is PrincipalType.INTEGRATION
