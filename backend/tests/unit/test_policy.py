"""The single permission policy: roles, ownership and integration scopes (FR-AUTH-05)."""

from uuid import uuid4

import pytest

from app.core.access import AccessLevel
from app.core.errors import AppError
from app.core.policy import Permission, can_edit_owned, check_access, check_owner, permissions_for
from app.core.principal import Principal, PrincipalType, RoleCode

ROLE_ACCESS = {
    # level: roles allowed past the route check
    AccessLevel.SIGNED_IN: {"admin", "sales_manager", "sales_rep", "viewer"},
    AccessLevel.SIGNED_IN_OR_ANY_CLIENT: {"admin", "sales_manager", "sales_rep", "viewer"},
    AccessLevel.CONTRIBUTOR: {"admin", "sales_manager", "sales_rep"},
    AccessLevel.CONTRIBUTOR_RULES_IN_SERVICE: {"admin", "sales_manager", "sales_rep"},
    AccessLevel.OWNER_PLUS: {"admin", "sales_manager", "sales_rep"},
    AccessLevel.MANAGER_PLUS: {"admin", "sales_manager"},
    AccessLevel.ADMIN: {"admin"},
}
HUMAN_ROLES = [RoleCode.ADMIN, RoleCode.SALES_MANAGER, RoleCode.SALES_REP, RoleCode.VIEWER]


def user(role: RoleCode) -> Principal:
    return Principal(type=PrincipalType.USER, user_id=uuid4(), role=role, display_name="Test")


def client(*scopes: str) -> Principal:
    return Principal(
        type=PrincipalType.INTEGRATION,
        user_id=uuid4(),
        role=RoleCode.INTEGRATION,
        display_name="ERP (integration)",
        scopes=frozenset(scopes),
    )


@pytest.mark.parametrize("level", list(ROLE_ACCESS))
@pytest.mark.parametrize("role", HUMAN_ROLES)
def test_FR_AUTH_05_role_matrix(level: AccessLevel, role: RoleCode) -> None:
    if role.value in ROLE_ACCESS[level]:
        check_access(user(role), level)
    else:
        with pytest.raises(AppError) as error:
            check_access(user(role), level)
        assert error.value.status == 403
        assert error.value.code == "permission.denied"


@pytest.mark.parametrize("level", list(AccessLevel))
def test_public_is_open_to_everyone(level: AccessLevel) -> None:
    check_access(None, AccessLevel.PUBLIC)


@pytest.mark.parametrize("level", [lv for lv in AccessLevel if lv is not AccessLevel.PUBLIC])
def test_FR_AUTH_05_anonymous_callers_get_401(level: AccessLevel) -> None:
    with pytest.raises(AppError) as error:
        check_access(None, level)
    assert error.value.status == 401
    assert error.value.code == "auth.session_expired"


def test_FR_INT_03_integrations_are_denied_routes_without_a_scope() -> None:
    with pytest.raises(AppError) as error:
        check_access(client("organizations:read"), AccessLevel.SIGNED_IN)
    assert error.value.code == "permission.not_for_integrations"


def test_FR_INT_03_AC1_missing_scope_names_the_required_scope() -> None:
    with pytest.raises(AppError) as error:
        check_access(client("contacts:read"), AccessLevel.SIGNED_IN, scope="organizations:read")
    assert error.value.status == 403
    assert error.value.code == "permission.scope_missing"
    assert error.value.extra == {"required_scope": "organizations:read"}


def test_FR_INT_03_scope_opens_the_route() -> None:
    check_access(client("organizations:read"), AccessLevel.SIGNED_IN, scope="organizations:read")


def test_any_client_may_call_me_without_a_scope() -> None:
    check_access(client(), AccessLevel.SIGNED_IN_OR_ANY_CLIENT)


def test_FR_AUTH_05_AC1_rep_cannot_edit_another_reps_record() -> None:
    rep = user(RoleCode.SALES_REP)
    assert can_edit_owned(rep, rep.user_id)
    assert not can_edit_owned(rep, uuid4())
    with pytest.raises(AppError) as error:
        check_owner(rep, uuid4())
    assert error.value.status == 403


@pytest.mark.parametrize("role", [RoleCode.ADMIN, RoleCode.SALES_MANAGER])
def test_managers_edit_any_record(role: RoleCode) -> None:
    check_owner(user(role), uuid4())


def test_FR_AUTH_05_AC2_viewer_edits_nothing() -> None:
    viewer = user(RoleCode.VIEWER)
    assert not can_edit_owned(viewer, viewer.user_id)


def test_permissions_follow_the_role_matrix() -> None:
    assert permissions_for(RoleCode.ADMIN) == frozenset(Permission)
    assert Permission.USERS_MANAGE not in permissions_for(RoleCode.SALES_MANAGER)
    assert Permission.RECORDS_REASSIGN in permissions_for(RoleCode.SALES_MANAGER)
    assert permissions_for(RoleCode.SALES_REP) >= {
        Permission.RECORDS_CREATE,
        Permission.RECORDS_EDIT_OWN,
    }
    assert permissions_for(RoleCode.VIEWER) == {Permission.RECORDS_READ}
    assert permissions_for(RoleCode.INTEGRATION) == frozenset()
