"""The single permission policy: role, ownership and integration scopes.

Route-level checks (`check_access`) run in the permission dependency for every
request; object-level checks (`check_owner`) run in services once the record is
loaded. Integration principals are deny-by-default: a route is open to them only
when it declares a scope (API spec section 19.3) and the client holds it.
"""

from enum import StrEnum
from http import HTTPStatus
from uuid import UUID

from app.core.access import AccessLevel
from app.core.errors import AppError, ErrorCode
from app.core.principal import Principal, RoleCode

HUMAN_ROLES = frozenset(
    {RoleCode.ADMIN, RoleCode.SALES_MANAGER, RoleCode.SALES_REP, RoleCode.VIEWER}
)
CONTRIBUTOR_ROLES = frozenset({RoleCode.ADMIN, RoleCode.SALES_MANAGER, RoleCode.SALES_REP})
MANAGER_ROLES = frozenset({RoleCode.ADMIN, RoleCode.SALES_MANAGER})

# Roles allowed past the route-level check for each level. Owner+ admits every
# contributor; the service then checks ownership for Sales Reps.
_ROLES_BY_LEVEL: dict[AccessLevel, frozenset[RoleCode]] = {
    AccessLevel.SIGNED_IN: HUMAN_ROLES,
    AccessLevel.SIGNED_IN_OWN: HUMAN_ROLES,
    AccessLevel.SIGNED_IN_OR_ANY_CLIENT: HUMAN_ROLES,
    AccessLevel.CONTRIBUTOR: CONTRIBUTOR_ROLES,
    AccessLevel.CONTRIBUTOR_RULES_IN_SERVICE: CONTRIBUTOR_ROLES,
    AccessLevel.OWNER_PLUS: CONTRIBUTOR_ROLES,
    AccessLevel.OWNER_PLUS_OR_TASK_ASSIGNEE: CONTRIBUTOR_ROLES,
    AccessLevel.OWNER_PLUS_OR_ASSIGNEE: CONTRIBUTOR_ROLES,
    AccessLevel.MANAGER_PLUS: MANAGER_ROLES,
    AccessLevel.ADMIN: frozenset({RoleCode.ADMIN}),
    AccessLevel.SIGNED_IN_OR_TYPE_SCOPE: HUMAN_ROLES,
    AccessLevel.SIGNED_IN_OR_RESOURCE_SCOPE: HUMAN_ROLES,
    AccessLevel.ADMIN_OR_OWN_SYSTEM: frozenset({RoleCode.ADMIN}),
    AccessLevel.ADMIN_OR_OWN_SYSTEM_DELETE: frozenset({RoleCode.ADMIN}),
}


class Permission(StrEnum):
    """Capabilities exposed to the UI through GET /me (`can()` helper)."""

    RECORDS_READ = "records.read"
    RECORDS_CREATE = "records.create"
    RECORDS_EDIT_OWN = "records.edit_own"
    RECORDS_EDIT_ANY = "records.edit_any"
    RECORDS_REASSIGN = "records.reassign"
    RECORDS_RESTORE = "records.restore"
    DATA_EXPORT = "data.export"
    DATA_IMPORT = "data.import"
    USERS_MANAGE = "users.manage"
    SETTINGS_MANAGE = "settings.manage"
    AUDIT_READ = "audit.read"


ROLE_PERMISSIONS: dict[RoleCode, frozenset[Permission]] = {
    RoleCode.ADMIN: frozenset(Permission),
    RoleCode.SALES_MANAGER: frozenset(
        {
            Permission.RECORDS_READ,
            Permission.RECORDS_CREATE,
            Permission.RECORDS_EDIT_OWN,
            Permission.RECORDS_EDIT_ANY,
            Permission.RECORDS_REASSIGN,
            Permission.RECORDS_RESTORE,
            Permission.DATA_EXPORT,
            Permission.DATA_IMPORT,
        }
    ),
    RoleCode.SALES_REP: frozenset(
        {
            Permission.RECORDS_READ,
            Permission.RECORDS_CREATE,
            Permission.RECORDS_EDIT_OWN,
            Permission.DATA_EXPORT,
        }
    ),
    RoleCode.VIEWER: frozenset({Permission.RECORDS_READ}),
    RoleCode.INTEGRATION: frozenset(),
}


def permissions_for(role: RoleCode) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]


def check_access(principal: Principal | None, level: AccessLevel, scope: str | None = None) -> None:
    """Route-level check. Raises AppError (401/403) when the caller may not proceed."""
    if level is AccessLevel.PUBLIC:
        # Public routes are for people (sign-in, password links); an API key is refused
        # there too (API spec 19.3: deny by default).
        if principal is not None and principal.is_integration:
            raise AppError(ErrorCode.PERMISSION_NOT_FOR_INTEGRATIONS, HTTPStatus.FORBIDDEN)
        return
    if principal is None:
        raise AppError(ErrorCode.AUTH_SESSION_EXPIRED, HTTPStatus.UNAUTHORIZED)
    if principal.is_integration:
        _check_integration(principal, level, scope)
        return
    if principal.role not in _ROLES_BY_LEVEL[level]:
        raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)


def _check_integration(principal: Principal, level: AccessLevel, scope: str | None) -> None:
    if level is AccessLevel.SIGNED_IN_OR_ANY_CLIENT:
        return
    if scope is None:
        raise AppError(ErrorCode.PERMISSION_NOT_FOR_INTEGRATIONS, HTTPStatus.FORBIDDEN)
    # "a|b": any of the scopes (the service narrows it down, e.g. external references).
    if not principal.scopes & set(scope.split("|")):
        raise AppError(
            ErrorCode.PERMISSION_SCOPE_MISSING,
            HTTPStatus.FORBIDDEN,
            extra={"required_scope": scope},
        )


def has_scope(principal: Principal, scope: str) -> bool:
    """Object-level scope check for integrations (people pass; their role was checked)."""
    return not principal.is_integration or scope in principal.scopes


def require_scope(principal: Principal, scope: str) -> None:
    if not has_scope(principal, scope):
        raise AppError(
            ErrorCode.PERMISSION_SCOPE_MISSING,
            HTTPStatus.FORBIDDEN,
            extra={"required_scope": scope},
        )


def record_owner(principal: Principal, requested: UUID | None) -> UUID:
    """Owner of a record being created (API spec 19.3): the requested one, else the caller;
    an integration falls back to its client's default owner, or `422 owner.required`."""
    if requested is not None:
        return requested
    if not principal.is_integration:
        return principal.user_id
    if principal.default_owner_id is None:
        raise AppError(ErrorCode.OWNER_REQUIRED, HTTPStatus.UNPROCESSABLE_CONTENT)
    return principal.default_owner_id


def can_edit_owned(principal: Principal, owner_id: UUID | None) -> bool:
    """Owner+ object rule: Admins and Sales Managers edit anything, Sales Reps their own."""
    if principal.is_integration:
        # Integration writes are governed by scopes at the route level (19.3).
        return True
    if principal.role in MANAGER_ROLES:
        return True
    return principal.role is RoleCode.SALES_REP and owner_id == principal.user_id


def check_owner(principal: Principal, owner_id: UUID | None) -> None:
    if not can_edit_owned(principal, owner_id):
        raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)
