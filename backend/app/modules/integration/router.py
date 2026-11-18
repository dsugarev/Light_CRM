"""HTTP layer only: parse requests, call the service, shape responses."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock
from app.core.db import DbSession
from app.modules.integration import service
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
)

clients_router = APIRouter(prefix="/integration-clients", tags=["integration"])
references_router = APIRouter(tags=["external references"])


async def context(request: Request, session: DbSession) -> service.Context:
    clock: Clock = request.app.state.clock
    return service.Context(
        session=session,
        events=request.app.state.event_bus,
        settings=request.app.state.settings,
        now=clock.now(),
    )


Ctx = Annotated[service.Context, Depends(context)]

# --- Clients and keys (API spec 19.7) --------------------------------------------------------


@clients_router.get(
    "",
    summary="Clients with system, scopes, status, last use and 24-hour counts",
    **endpoint(AccessLevel.ADMIN),
)
async def list_clients(ctx: Ctx) -> list[IntegrationClientOut]:
    return await service.list_clients(ctx)


@clients_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Register a client and its service user",
    **endpoint(AccessLevel.ADMIN),
)
async def create_client(
    body: IntegrationClientCreate, ctx: Ctx, principal: CurrentPrincipal, response: Response
) -> IntegrationClientOut:
    created = await service.create_client(ctx, principal, body)
    response.headers["Location"] = f"/api/v1/integration-clients/{created.id}"
    return created


@clients_router.get("/{client_id}", summary="Detail", **endpoint(AccessLevel.ADMIN))
async def get_client(client_id: UUID, ctx: Ctx) -> IntegrationClientOut:
    return await service.get_client(ctx, client_id)


@clients_router.patch(
    "/{client_id}",
    summary="Change scopes, owner default, allowlist, contact, rate limit",
    **endpoint(AccessLevel.ADMIN),
)
async def update_client(
    client_id: UUID, body: IntegrationClientUpdate, ctx: Ctx, principal: CurrentPrincipal
) -> IntegrationClientOut:
    return await service.update_client(ctx, principal, client_id, body)


@clients_router.post(
    "/{client_id}/deactivate",
    summary="Block all access and pause its webhooks",
    **endpoint(AccessLevel.ADMIN),
)
async def deactivate_client(
    client_id: UUID, ctx: Ctx, principal: CurrentPrincipal
) -> IntegrationClientOut:
    return await service.set_active(ctx, principal, client_id, active=False)


@clients_router.post("/{client_id}/activate", summary="Re-enable", **endpoint(AccessLevel.ADMIN))
async def activate_client(
    client_id: UUID, ctx: Ctx, principal: CurrentPrincipal
) -> IntegrationClientOut:
    return await service.set_active(ctx, principal, client_id, active=True)


@clients_router.get(
    "/{client_id}/api-keys",
    summary="Keys with prefix, created, expiry, last used (never the secret)",
    **endpoint(AccessLevel.ADMIN),
)
async def list_keys(client_id: UUID, ctx: Ctx) -> list[ApiKeyOut]:
    return await service.list_keys(ctx, client_id)


@clients_router.post(
    "/{client_id}/api-keys",
    status_code=status.HTTP_201_CREATED,
    summary="Create a key; the full key is in this response only",
    **endpoint(AccessLevel.ADMIN),
)
async def create_key(
    client_id: UUID, body: ApiKeyCreate, ctx: Ctx, principal: CurrentPrincipal
) -> ApiKeyCreated:
    return await service.create_key(ctx, principal, client_id, body)


@clients_router.delete(
    "/{client_id}/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a key immediately",
    **endpoint(AccessLevel.ADMIN),
)
async def revoke_key(client_id: UUID, key_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> None:
    await service.revoke_key(ctx, principal, client_id, key_id)


# --- External references (API spec 19.4) -------------------------------------------------------

_ANY_READ = "organizations:read|contacts:read|leads:read|opportunities:read"


@references_router.get(
    "/external-references",
    summary="Resolve an external ID to the CRM record",
    **endpoint(AccessLevel.SIGNED_IN_OR_TYPE_SCOPE, scope=_ANY_READ),
)
async def resolve_reference(
    ctx: Ctx,
    principal: CurrentPrincipal,
    system: Annotated[str, Query(max_length=50)],
    external_id: Annotated[str, Query(min_length=1, max_length=200)],
    entity_type: EntityType | None = None,
) -> ExternalReferenceOut:
    return await service.resolve_reference(ctx, principal, system, external_id, entity_type)


@references_router.get(
    "/{resource}/{id}/external-references",
    summary="All references of one record",
    **endpoint(AccessLevel.SIGNED_IN_OR_RESOURCE_SCOPE, scope="{resource}:read"),
)
async def record_references(resource: Resource, id: UUID, ctx: Ctx) -> list[ExternalReferenceOut]:
    return await service.record_references(ctx, resource, id)


@references_router.put(
    "/{resource}/{id}/external-references/{system}",
    summary="Create or replace the reference in a system",
    **endpoint(AccessLevel.ADMIN_OR_OWN_SYSTEM, scope="external-references:write"),
)
async def put_reference(
    resource: Resource,
    id: UUID,
    system: str,
    body: ExternalReferencePut,
    ctx: Ctx,
    principal: CurrentPrincipal,
) -> ExternalReferenceOut:
    return await service.put_reference(ctx, principal, resource, id, system, body)


@references_router.delete(
    "/{resource}/{id}/external-references/{system}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the reference",
    **endpoint(AccessLevel.ADMIN_OR_OWN_SYSTEM_DELETE, scope="external-references:write"),
)
async def delete_reference(
    resource: Resource,
    id: UUID,
    system: str,
    ctx: Ctx,
    principal: CurrentPrincipal,
) -> None:
    await service.delete_reference(ctx, principal, resource, id, system)


routers = [clients_router, references_router]
