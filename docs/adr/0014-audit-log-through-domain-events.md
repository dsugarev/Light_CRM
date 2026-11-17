# ADR 0014: Audit log through in-process domain events

Status: Accepted · Date: 2026-11-17 · Phase 1

## Context
FR-ADM-03 requires every create/update/delete, sign-ins, failed sign-ins, exports, imports and role changes to be audited, with entries that cannot be edited or deleted. Phase 6 needs the same change stream for the webhook outbox.

## Decision
- Services publish a `DomainEvent` (action, entity, actor, before, after, details) on `app/core/events.EventBus` in the same database session as the change. The audit module subscribes in `app.main.create_event_bus()`; Phase 6 adds the outbox subscriber.
- `audit_log` stores the actor's ID, type and display name at the time of the action, so it reads correctly without joining identity tables. Columns `actor_type`, `actor_label` and `details` extend the architecture's column list.
- Append-only: migration 0002 revokes UPDATE, DELETE and TRUNCATE on `audit_log` from `crm_app`; a test proves the application role cannot change entries.
- Secrets never enter entries: services pass a whitelisted view of users, and the audit handler additionally strips keys such as `password_hash`, `token`, `secret`.
- Failed sign-ins and lockouts are committed before the error response, so they are recorded even though the request fails.

## Consequences
A service that forgets to publish an event leaves no audit trail; API tests assert the expected audit entries for every mutating endpoint.
