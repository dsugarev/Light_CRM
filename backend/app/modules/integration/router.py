"""HTTP layer only: parse requests, call the service, shape responses."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.access import AccessLevel
from app.core.auth import CurrentPrincipal, endpoint
from app.core.clock import Clock
from app.core.db import DbSession
from app.modules.integration import service, webhooks
from app.modules.integration.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    DeliveryStatus,
    EntityType,
    ExternalReferenceOut,
    ExternalReferencePut,
    IntegrationClientCreate,
    IntegrationClientOut,
    IntegrationClientUpdate,
    Resource,
    WebhookDeliveryDetail,
    WebhookDeliveryOut,
    WebhookDeliveryPage,
    WebhookSecret,
    WebhookSubscriptionCreate,
    WebhookSubscriptionCreated,
    WebhookSubscriptionOut,
    WebhookSubscriptionUpdate,
)

clients_router = APIRouter(prefix="/integration-clients", tags=["integration"])
references_router = APIRouter(tags=["external references"])
subscriptions_router = APIRouter(prefix="/webhook-subscriptions", tags=["webhooks"])
deliveries_router = APIRouter(prefix="/webhook-deliveries", tags=["webhooks"])


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


# --- Webhooks (API spec 19.6, 19.7) ------------------------------------------------------------


@clients_router.get(
    "/{client_id}/webhook-subscriptions",
    summary="Subscriptions of a client, with 24-hour delivery counts",
    **endpoint(AccessLevel.ADMIN),
)
async def list_subscriptions(client_id: UUID, ctx: Ctx) -> list[WebhookSubscriptionOut]:
    return await webhooks.list_subscriptions(ctx, client_id)


@clients_router.post(
    "/{client_id}/webhook-subscriptions",
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe an HTTPS endpoint; the signing secret is in this response only",
    **endpoint(AccessLevel.ADMIN),
)
async def create_subscription(
    client_id: UUID, body: WebhookSubscriptionCreate, ctx: Ctx, principal: CurrentPrincipal
) -> WebhookSubscriptionCreated:
    return await webhooks.create_subscription(ctx, principal, client_id, body)


@subscriptions_router.patch(
    "/{subscription_id}",
    summary="Change URL, event types or the active flag",
    **endpoint(AccessLevel.ADMIN),
)
async def update_subscription(
    subscription_id: UUID, body: WebhookSubscriptionUpdate, ctx: Ctx, principal: CurrentPrincipal
) -> WebhookSubscriptionOut:
    return await webhooks.update_subscription(ctx, principal, subscription_id, body)


@subscriptions_router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a subscription and its delivery log",
    **endpoint(AccessLevel.ADMIN),
)
async def delete_subscription(subscription_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> None:
    await webhooks.delete_subscription(ctx, principal, subscription_id)


@subscriptions_router.post(
    "/{subscription_id}/rotate-secret",
    summary="New signing secret, returned once; the old one signs too for 24 hours",
    **endpoint(AccessLevel.ADMIN),
)
async def rotate_secret(
    subscription_id: UUID, ctx: Ctx, principal: CurrentPrincipal
) -> WebhookSecret:
    return await webhooks.rotate_secret(ctx, principal, subscription_id)


@subscriptions_router.post(
    "/{subscription_id}/test",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a ping event; the worker sends it once and records the result",
    **endpoint(AccessLevel.ADMIN),
)
async def send_test(
    subscription_id: UUID, ctx: Ctx, principal: CurrentPrincipal
) -> WebhookDeliveryOut:
    return await webhooks.send_test(ctx, principal, subscription_id)


@deliveries_router.get(
    "",
    summary="Delivery log, newest first",
    **endpoint(AccessLevel.ADMIN),
)
async def list_deliveries(
    ctx: Ctx,
    subscription_id: UUID | None = None,
    client_id: UUID | None = None,
    event_type: Annotated[str | None, Query(max_length=60)] = None,
    status: DeliveryStatus | None = None,
    created_at_from: datetime | None = None,
    created_at_to: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> WebhookDeliveryPage:
    filters = webhooks.DeliveryFilters(
        subscription_id=subscription_id,
        client_id=client_id,
        event_type=event_type,
        status=status,
        created_from=created_at_from,
        created_to=created_at_to,
    )
    return await webhooks.list_deliveries(ctx, filters, page, page_size)


@deliveries_router.get(
    "/{delivery_id}",
    summary="A delivery with its attempts",
    **endpoint(AccessLevel.ADMIN),
)
async def get_delivery(delivery_id: UUID, ctx: Ctx) -> WebhookDeliveryDetail:
    return await webhooks.get_delivery(ctx, delivery_id)


@deliveries_router.post(
    "/{delivery_id}/redeliver",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue the event again for the same subscription",
    **endpoint(AccessLevel.ADMIN),
)
async def redeliver(delivery_id: UUID, ctx: Ctx, principal: CurrentPrincipal) -> WebhookDeliveryOut:
    return await webhooks.redeliver(ctx, principal, delivery_id)


routers = [clients_router, references_router, subscriptions_router, deliveries_router]
