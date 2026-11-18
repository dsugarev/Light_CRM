"""Integration clients, API keys, external references and usage (FR-INT-01..04, 08, 09).

Public API of the module. Integrated applications call the same `/api/v1` endpoints
as the web frontend; this module turns their bearer API keys into `Principal`s
(API spec 19.2) and owns the cross-system identifiers (19.4).
"""

import hashlib
import hmac
import ipaddress
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import Environment, Settings
from app.core.errors import AppError, ErrorCode, FieldError
from app.core.events import DomainEvent, EventBus
from app.core.logging import client_ip_var
from app.core.policy import require_scope
from app.core.principal import Principal, PrincipalType, RoleCode
from app.core.reference import ReferenceList
from app.modules.identity import service as identity
from app.modules.integration import repository
from app.modules.integration.models import (
    ApiKey,
    ExternalReference,
    ExternalSystem,
    IntegrationClient,
)
from app.modules.integration.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    EntityType,
    ExternalReferenceOut,
    ExternalReferencePut,
    IntegrationClientCreate,
    IntegrationClientOut,
    IntegrationClientUpdate,
    Resource,
    SystemSummary,
    UsageFigures,
    WebhookFigures,
)
from app.modules.party import service as party
from app.modules.sales import service as sales
from app.modules.sales.schemas import UserSummary

KEY_PATTERN = re.compile(r"^crm_([a-z]+)_([0-9a-f]{16})_([A-Za-z0-9_-]{43})$")
KEY_DEFAULT_LIFETIME = timedelta(days=365)
KEY_MAX_LIFETIME = timedelta(days=730)
MAX_ACTIVE_KEYS = 2
_TOUCH_INTERVAL = timedelta(minutes=1)
ENTITY_OF: Mapping[str, EntityType] = {
    "organizations": "organization",
    "contacts": "contact",
    "leads": "lead",
    "opportunities": "opportunity",
}
RESOURCE_OF: Mapping[str, str] = {entity: resource for resource, entity in ENTITY_OF.items()}

# API spec 19.9: working assumptions until the data flows are confirmed (read-only plus
# writing back each system's own IDs). Created inactive, without keys.
PROFILES: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "erp": ("ERP", ("organizations:read", "contacts:read", "opportunities:read",
                    "reference:read", "external-references:write")),
    "billing": ("Billing", ("organizations:read", "contacts:read", "opportunities:read",
                            "reference:read", "external-references:write")),
    "conclusion": ("Conclusion", ("organizations:read", "opportunities:read", "reference:read",
                                  "external-references:write")),
}  # fmt: skip


@dataclass(frozen=True, slots=True)
class Context:
    session: AsyncSession
    events: EventBus
    settings: Settings
    now: datetime


def _not_found() -> AppError:
    return AppError(ErrorCode.RESOURCE_NOT_FOUND, HTTPStatus.NOT_FOUND)


def _invalid(field: str, code: str) -> AppError:
    return AppError(
        ErrorCode.VALIDATION_FAILED,
        HTTPStatus.UNPROCESSABLE_CONTENT,
        errors=[FieldError(field, code)],
    )


async def _publish(
    ctx: Context,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    principal: Principal,
    *,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> None:
    await ctx.events.publish(
        ctx.session,
        DomainEvent(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=principal,
            occurred_at=ctx.now,
            before=before,
            after=after,
            details=details or {},
        ),
    )


def _system(system: ExternalSystem) -> SystemSummary:
    return SystemSummary(
        id=system.id, code=system.code, name_en=system.name_en, name_bg=system.name_bg
    )


# --- API keys and bearer authentication (API spec 19.2) ------------------------------------------


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _env_label(settings: Settings) -> str:
    return {Environment.PRODUCTION: "prod", Environment.TEST: "test"}.get(settings.env, "dev")


def _prefix(settings: Settings, key: ApiKey) -> str:
    return f"crm_{_env_label(settings)}_{key.key_id}"


def _invalid_key() -> AppError:
    return AppError(ErrorCode.AUTH_API_KEY_INVALID, HTTPStatus.UNAUTHORIZED)


def _ip_allowed(allowlist: Sequence[str], address: str | None) -> bool:
    if not allowlist:
        return True
    if address is None:
        return False
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in ipaddress.ip_network(cidr, strict=False) for cidr in allowlist)


async def authenticate_bearer(request: Request, session: AsyncSession) -> Principal:
    """Resolve `Authorization: Bearer crm_…` to the client's principal (FR-INT-02, 03).

    Refused with 401 when the key is malformed, unknown, revoked or expired or the client
    is deactivated, and with 403 when the caller's address is outside the allowlist.
    """
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    match = KEY_PATTERN.match(token.strip()) if scheme.lower() == "bearer" else None
    if match is None:
        raise _invalid_key()
    now: datetime = request.app.state.clock.now()
    key = await repository.get_key_by_key_id(session, match[2])
    if (
        key is None
        or key.revoked_at is not None
        or key.expires_at <= now
        or not hmac.compare_digest(key.secret_hash, hash_secret(match[3]))
    ):
        raise _invalid_key()
    client = await repository.get_client(session, key.client_id)
    if client is None or not client.is_active:
        raise AppError(ErrorCode.AUTH_CLIENT_INACTIVE, HTTPStatus.UNAUTHORIZED)
    address = client_ip_var.get()
    if not _ip_allowed(client.ip_allowlist, address):
        raise AppError(ErrorCode.AUTH_IP_NOT_ALLOWED, HTTPStatus.FORBIDDEN)
    if key.last_used_at is None or now - key.last_used_at >= _TOUCH_INTERVAL:
        key.last_used_at, key.last_used_ip = now, address
        await session.commit()
    return Principal(
        type=PrincipalType.INTEGRATION,
        user_id=client.service_user_id,
        role=RoleCode.INTEGRATION,
        display_name=f"{client.name} (integration)",
        scopes=frozenset(client.scopes),
        client_id=client.id,
        system=client.system.code,
        default_owner_id=client.default_owner_id,
        rate_limit_per_minute=client.rate_limit_per_minute,
    )


# --- Clients (API spec 19.7) ---------------------------------------------------------------------


async def _clients_out(
    ctx: Context, clients: list[IntegrationClient]
) -> list[IntegrationClientOut]:
    since = ctx.now - timedelta(hours=24)
    usage = await repository.usage_since(ctx.session, [c.id for c in clients], since)
    webhooks = await repository.webhook_figures(ctx.session, [c.id for c in clients], since)
    owners = await identity.user_names(
        ctx.session, {c.default_owner_id for c in clients if c.default_owner_id}
    )
    out = []
    for client in clients:
        keys = await repository.keys_of(ctx.session, client.id)
        used = [k.last_used_at for k in keys if k.last_used_at]
        requests, errors = usage.get(client.id, (0, 0))
        subscriptions, failing, suspended = webhooks.get(client.id, (0, 0, 0))
        out.append(
            IntegrationClientOut(
                id=client.id,
                name=client.name,
                system=_system(client.system),
                scopes=client.scopes,  # type: ignore[arg-type]
                default_owner=UserSummary(
                    id=client.default_owner_id, full_name=owners.get(client.default_owner_id, "")
                )
                if client.default_owner_id
                else None,
                ip_allowlist=client.ip_allowlist,
                technical_contact=client.technical_contact,
                rate_limit_per_minute=client.rate_limit_per_minute,
                is_active=client.is_active,
                last_used_at=max(used) if used else None,
                usage=UsageFigures(requests_24h=requests, errors_24h=errors),
                active_keys=sum(1 for k in keys if k.revoked_at is None and k.expires_at > ctx.now),
                webhooks=WebhookFigures(
                    subscriptions=subscriptions,
                    failing_deliveries=failing,
                    suspended_subscriptions=suspended,
                ),
                created_at=client.created_at,
                updated_at=client.updated_at,
            )
        )
    return out


def _view(client: IntegrationClient) -> dict[str, Any]:
    return {
        "name": client.name,
        "scopes": sorted(client.scopes),
        "default_owner_id": str(client.default_owner_id) if client.default_owner_id else None,
        "ip_allowlist": list(client.ip_allowlist),
        "technical_contact": client.technical_contact,
        "rate_limit_per_minute": client.rate_limit_per_minute,
        "is_active": client.is_active,
    }


async def _load(ctx: Context, client_id: UUID) -> IntegrationClient:
    client = await repository.get_client(ctx.session, client_id, for_update=True)
    if client is None:
        raise _not_found()
    return client


async def _fresh(ctx: Context, client_id: UUID) -> IntegrationClientOut:
    ctx.session.expire_all()
    client = await repository.get_client(ctx.session, client_id)
    assert client is not None  # noqa: S101 - exists
    return (await _clients_out(ctx, [client]))[0]


async def _check_owner(ctx: Context, owner_id: UUID | None) -> None:
    if owner_id is not None and not await identity.is_assignable_owner(ctx.session, owner_id):
        raise _invalid("default_owner_id", "owner.invalid")


async def list_clients(ctx: Context) -> list[IntegrationClientOut]:
    return await _clients_out(ctx, await repository.list_clients(ctx.session))


async def get_client(ctx: Context, client_id: UUID) -> IntegrationClientOut:
    client = await repository.get_client(ctx.session, client_id)
    if client is None:
        raise _not_found()
    return (await _clients_out(ctx, [client]))[0]


async def create_client(
    ctx: Context, principal: Principal | None, data: IntegrationClientCreate
) -> IntegrationClientOut:
    """FR-INT-01: register a client and its service user."""
    system = await repository.get_system_by_code(ctx.session, data.system)
    if system is None or not system.is_active:
        raise _invalid("system", "reference.invalid")
    await _check_owner(ctx, data.default_owner_id)
    client = IntegrationClient(
        name=data.name,
        external_system_id=system.id,
        service_user_id=await identity.create_service_user(ctx.session, data.name, system.code),
        scopes=sorted(set(data.scopes)),
        default_owner_id=data.default_owner_id,
        ip_allowlist=list(data.ip_allowlist),
        technical_contact=data.technical_contact,
        rate_limit_per_minute=data.rate_limit_per_minute,
        is_active=data.is_active,
        created_by=principal.user_id if principal else None,
        updated_by=principal.user_id if principal else None,
    )
    ctx.session.add(client)
    await ctx.session.flush()
    await identity.update_service_user(ctx.session, client.service_user_id, active=data.is_active)
    if principal is not None:
        await _publish(
            ctx, "integration_client.created", "integration_client", client.id, principal,
            after={**_view(client), "system": system.code},
        )  # fmt: skip
    await ctx.session.commit()
    return await _fresh(ctx, client.id)


async def update_client(
    ctx: Context, principal: Principal, client_id: UUID, data: IntegrationClientUpdate
) -> IntegrationClientOut:
    client = await _load(ctx, client_id)
    changes = data.model_dump(exclude_unset=True)
    if "default_owner_id" in changes:
        await _check_owner(ctx, changes["default_owner_id"])
    for field in ("name", "scopes", "ip_allowlist", "rate_limit_per_minute"):
        if field in changes and changes[field] is None:
            raise _invalid(field, "validation.missing")
    before = _view(client)
    if "scopes" in changes:
        changes["scopes"] = sorted(set(changes["scopes"]))
    for key, value in changes.items():
        setattr(client, key, value)
    if "name" in changes:
        await identity.update_service_user(ctx.session, client.service_user_id, name=client.name)
    after = _view(client)
    if after != before:
        client.updated_by = principal.user_id
        await _publish(
            ctx, "integration_client.updated", "integration_client", client.id, principal,
            before=before, after=after,
        )  # fmt: skip
    await ctx.session.commit()
    return await _fresh(ctx, client.id)


async def set_active(
    ctx: Context, principal: Principal, client_id: UUID, active: bool
) -> IntegrationClientOut:
    """FR-INT-01 AC1: a deactivated client is refused with 401 (webhooks pause in 6b)."""
    client = await _load(ctx, client_id)
    if client.is_active != active:
        client.is_active = active
        client.updated_by = principal.user_id
        await identity.update_service_user(ctx.session, client.service_user_id, active=active)
        action = "activated" if active else "deactivated"
        await _publish(
            ctx, f"integration_client.{action}", "integration_client", client.id, principal
        )
    await ctx.session.commit()
    return await _fresh(ctx, client.id)


# --- Keys -------------------------------------------------------------------------------------


async def _keys_out(ctx: Context, keys: list[ApiKey]) -> list[ApiKeyOut]:
    names = await identity.user_names(ctx.session, {k.created_by for k in keys if k.created_by})
    return [
        ApiKeyOut(
            id=k.id,
            prefix=_prefix(ctx.settings, k),
            label=k.label,
            created_at=k.created_at,
            expires_at=k.expires_at,
            revoked_at=k.revoked_at,
            last_used_at=k.last_used_at,
            last_used_ip=k.last_used_ip,
            created_by=UserSummary(id=k.created_by, full_name=names.get(k.created_by, ""))
            if k.created_by
            else None,
        )
        for k in keys
    ]


async def list_keys(ctx: Context, client_id: UUID) -> list[ApiKeyOut]:
    if await repository.get_client(ctx.session, client_id) is None:
        raise _not_found()
    return await _keys_out(ctx, await repository.keys_of(ctx.session, client_id))


async def create_key(
    ctx: Context, principal: Principal, client_id: UUID, data: ApiKeyCreate
) -> ApiKeyCreated:
    """FR-INT-02: the full key is returned once; only the hash of its secret is stored."""
    client = await _load(ctx, client_id)
    expires_at = data.expires_at or ctx.now + KEY_DEFAULT_LIFETIME
    if expires_at <= ctx.now:
        raise _invalid("expires_at", "api_key.expiry_past")
    if expires_at > ctx.now + KEY_MAX_LIFETIME:
        raise _invalid("expires_at", "api_key.expiry_too_long")
    keys = await repository.keys_of(ctx.session, client.id)
    if sum(1 for k in keys if k.revoked_at is None and k.expires_at > ctx.now) >= MAX_ACTIVE_KEYS:
        raise AppError(ErrorCode.API_KEY_LIMIT, HTTPStatus.CONFLICT, extra={"max": MAX_ACTIVE_KEYS})
    secret = secrets.token_urlsafe(32)  # 256 bits, 43 characters
    key = ApiKey(
        client_id=client.id,
        key_id=secrets.token_hex(8),
        secret_hash=hash_secret(secret),
        label=data.label,
        expires_at=expires_at,
        created_by=principal.user_id,
    )
    ctx.session.add(key)
    await ctx.session.flush()
    # The audit entry names the key, never its secret (FR-INT-02 AC3).
    await _publish(
        ctx, "api_key.created", "integration_client", client.id, principal,
        details={"key_id": key.key_id, "label": key.label, "expires_at": expires_at.isoformat()},
    )  # fmt: skip
    await ctx.session.commit()
    await ctx.session.refresh(key)
    [out] = await _keys_out(ctx, [key])
    return ApiKeyCreated(**out.model_dump(), key=f"{_prefix(ctx.settings, key)}_{secret}")


async def revoke_key(ctx: Context, principal: Principal, client_id: UUID, key_id: UUID) -> None:
    key = await repository.get_key(ctx.session, client_id, key_id)
    if key is None:
        raise _not_found()
    if key.revoked_at is None:
        key.revoked_at = ctx.now
        await _publish(
            ctx, "api_key.revoked", "integration_client", client_id, principal,
            details={"key_id": key.key_id, "label": key.label},
        )  # fmt: skip
    await ctx.session.commit()


# --- External references (API spec 19.4) ---------------------------------------------------------


async def _record_exists(session: AsyncSession, entity_type: str, entity_id: UUID) -> bool:
    if entity_type == "organization":
        return await party.organization_summary(session, entity_id) is not None
    if entity_type == "contact":
        return await party.contact_link(session, entity_id, include_archived=True) is not None
    if entity_type == "lead":
        return await sales.links.lead_exists(session, entity_id)
    exists, _ = await sales.links.opportunity_source(session, entity_id)
    return exists


async def _references_out(
    ctx: Context, references: list[ExternalReference]
) -> list[ExternalReferenceOut]:
    names = await identity.user_names(
        ctx.session, {r.updated_by for r in references if r.updated_by}
    )
    return [
        ExternalReferenceOut(
            entity_type=r.entity_type,  # type: ignore[arg-type]
            entity_id=r.entity_id,
            system=_system(r.system),
            external_id=r.external_id,
            url=r.url,
            updated_at=r.updated_at,
            updated_by=UserSummary(id=r.updated_by, full_name=names.get(r.updated_by, ""))
            if r.updated_by
            else None,
        )
        for r in references
    ]


async def resolve_reference(
    ctx: Context,
    principal: Principal,
    system: str,
    external_id: str,
    entity_type: EntityType | None,
) -> ExternalReferenceOut:
    """FR-INT-04 AC3: find a record by its ID in another system."""
    found_system = await repository.get_system_by_code(ctx.session, system)
    if found_system is None:
        raise _not_found()
    found = await repository.find_reference(ctx.session, found_system.id, external_id, entity_type)
    readable = [
        r for r in found if not principal.is_integration
        or f"{RESOURCE_OF[r.entity_type]}:read" in principal.scopes
    ]  # fmt: skip
    if not readable:
        if found:  # the client may not read that record type
            require_scope(principal, f"{RESOURCE_OF[found[0].entity_type]}:read")
        raise _not_found()
    return (await _references_out(ctx, readable[:1]))[0]


async def record_references(
    ctx: Context, resource: Resource, entity_id: UUID
) -> list[ExternalReferenceOut]:
    entity_type = ENTITY_OF[resource]
    if not await _record_exists(ctx.session, entity_type, entity_id):
        raise _not_found()
    return await _references_out(
        ctx, await repository.references_of(ctx.session, entity_type, entity_id)
    )


async def _system_for_write(ctx: Context, principal: Principal, system: str) -> ExternalSystem:
    """FR-INT-04 AC2: a client writes only its own system's references; Admins any."""
    if principal.is_integration and principal.system != system:
        raise AppError(ErrorCode.EXTERNAL_REFERENCE_SYSTEM_MISMATCH, HTTPStatus.FORBIDDEN)
    found = await repository.get_system_by_code(ctx.session, system)
    if found is None:
        raise _not_found()
    return found


async def put_reference(
    ctx: Context,
    principal: Principal,
    resource: Resource,
    entity_id: UUID,
    system: str,
    data: ExternalReferencePut,
) -> ExternalReferenceOut:
    """Create or replace the record's reference in `system` (FR-INT-04 AC1, AC2)."""
    entity_type = ENTITY_OF[resource]
    found_system = await _system_for_write(ctx, principal, system)
    if not found_system.is_active:
        raise _invalid("system", "reference.invalid")
    if not await _record_exists(ctx.session, entity_type, entity_id):
        raise _not_found()
    taken = [
        r
        for r in await repository.find_reference(
            ctx.session, found_system.id, data.external_id, entity_type
        )
        if r.entity_id != entity_id
    ]
    if taken:
        raise AppError(
            ErrorCode.EXTERNAL_REFERENCE_CONFLICT,
            HTTPStatus.CONFLICT,
            extra={"entity_type": entity_type, "entity_id": str(taken[0].entity_id)},
        )
    reference = await repository.get_reference(ctx.session, entity_type, entity_id, found_system.id)
    before = {"external_id": reference.external_id, "url": reference.url} if reference else None
    if reference is None:
        reference = ExternalReference(
            entity_type=entity_type,
            entity_id=entity_id,
            external_system_id=found_system.id,
            created_by=principal.user_id,
        )
        ctx.session.add(reference)
    reference.external_id, reference.url = data.external_id, data.url
    reference.updated_by = principal.user_id
    after = {"external_id": data.external_id, "url": data.url}
    if after != before:
        await _publish(
            ctx, "external_reference.updated", entity_type, entity_id, principal,
            before=before, after=after, details={"system": system},
        )  # fmt: skip
    system_id = found_system.id  # attributes expire below
    await ctx.session.commit()
    ctx.session.expire_all()
    current = await repository.get_reference(ctx.session, entity_type, entity_id, system_id)
    assert current is not None  # noqa: S101 - just written
    return (await _references_out(ctx, [current]))[0]


async def delete_reference(
    ctx: Context, principal: Principal, resource: Resource, entity_id: UUID, system: str
) -> None:
    entity_type = ENTITY_OF[resource]
    found_system = await _system_for_write(ctx, principal, system)
    reference = await repository.get_reference(ctx.session, entity_type, entity_id, found_system.id)
    if reference is None:
        raise _not_found()
    before = {"external_id": reference.external_id, "url": reference.url}
    await ctx.session.delete(reference)
    await _publish(
        ctx, "external_reference.updated", entity_type, entity_id, principal,
        before=before, after=None, details={"system": system, "removed": True},
    )  # fmt: skip
    await ctx.session.commit()


def external_filter(
    entity_type: str,
    id_column: ColumnElement[UUID],
    system: str,
    external_id: str | None,
    has_reference: bool | None,
) -> ColumnElement[bool]:
    """List filter registered with party and sales (ADR 0018 pattern)."""
    return repository.reference_condition(
        entity_type, id_column, system, external_id, has_reference
    )


# --- Usage and housekeeping --------------------------------------------------------------------


async def record_usage(engine: AsyncEngine, client_id: UUID, now: datetime, status: int) -> None:
    """FR-INT-08: count the request (and an error for 4xx/5xx) in the client's hour."""
    hour = now.replace(minute=0, second=0, microsecond=0)
    await repository.record_usage(engine, client_id, hour, status >= HTTPStatus.BAD_REQUEST)


async def purge_expired(session: AsyncSession, now: datetime) -> dict[str, int]:
    """Housekeeping (worker): idempotency records after 24 h, usage after 30 days."""
    removed = {
        "idempotency_records": await repository.purge_idempotency(session, now),
        "usage_hours": await repository.purge_usage(session, now - timedelta(days=30)),
    }
    await session.commit()
    return removed


async def _system_usage(session: AsyncSession, item_id: UUID) -> int:
    return await repository.count_with_system(session, item_id)


REFERENCE_LISTS = (
    ReferenceList("external-systems", "external_system", ExternalSystem, _system_usage),
)
