# ADR 0020: Timeline events recorded from domain events

Status: Accepted · Date: 2026-11-17 · Phase 4b

## Context
FR-ACT-03 asks for a reverse-chronological timeline on every record that merges activities with system events (created, owner changed, stage changed, converted, …); FR-LEAD-04 AC3 asks that a lead's history stays visible from the opportunity it became; the organization timeline merges its contacts, leads and opportunities. The audit log (ADR 0014) already receives a domain event for every change, but it is an administrative, append-only record with Admin-only access, its own retention and before/after snapshots of whole records. The owner accepted a separate `timeline_event` table on 2026-11-17 (recommendation 5).

## Decision
- The `activity` module subscribes `record_event` to the in-process event bus next to the audit subscriber. For actions `<entity>.<verb>` where the entity is a lead, opportunity, organization or contact and the verb is one of the R1 event types, it adds a `timeline_event` row (`entity_type`, `entity_id`, `event_type`, `occurred_at`, `actor_id`, `data`) in the same session, so the event commits or rolls back with the change.
- `data` stores only identifiers and raw values taken from the event's before/after views (`from_stage_id`, `to_owner_id`, `from_status`, `loss_reason_id`, `opportunity_id`, changed `fields`). Names are resolved when the timeline is read, through the owning modules' public functions, so renamed stages, users and loss reasons show their current names in both languages.
- A timeline is a scope of record IDs (leads, opportunities, organizations, contacts). One `UNION ALL` query over activities and timeline events orders by time and pages in the database; the opportunity scope adds its source lead, the organization scope adds its contacts, leads and opportunities (IDs obtained from party and sales).
- Activities are not copied into `timeline_event`; they are read from `activity`. Activity changes themselves (`activity.*`) do not create timeline events: the activity is the entry.
- Existing records created before Phase 4b have no timeline events; R1 is not in production, so no backfill is done.

## Consequences
- Business modules stay unaware of timelines; a new module adds timeline entries by publishing domain events with the conventional action names.
- The audit log and timelines can evolve independently (retention, GDPR anonymisation in Phase 8 must cover `timeline_event.data` and `actor_id` as well as the audit log).
- Reading a timeline costs one paged union query plus batched name lookups; the `(entity_type, entity_id, occurred_at)` index and the activity link indexes serve it.
