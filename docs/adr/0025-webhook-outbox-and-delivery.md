# ADR 0025: Webhooks through a PostgreSQL outbox, delivered by the worker with a pinned, allowlisted connection

Status: Accepted · Date: 2026-11-18 · Phase 6b

## Context
FR-INT-07 requires events recorded in the same transaction as the change (AC1), signed deliveries with unique event IDs (AC2), retries for 72 hours with a visible history and redelivery (AC3), events only for readable record types (AC4), and HTTPS URLs on allowlisted hosts (AC5). CLAUDE.md adds: business modules only publish domain events; only the worker makes outbound calls; webhook secrets are encrypted at rest. Owner decisions (Phase 6): `cryptography` for encryption with `APP_ENCRYPTION_KEY`; `httpx` as a runtime dependency; `WEBHOOK_ALLOWED_HOSTS` with exact hosts or `*.suffix`, resolved and pinned, loopback, link-local and metadata always refused; a banner and badge for failing deliveries rather than email.

## Decision
- **Outbox subscriber.** `integration.webhooks.record_event` is subscribed to the event bus beside the audit log and timelines and adds an `outbox_event` row in the caller's session, so it commits or rolls back with the change. Business modules are unchanged. Domain actions map to the event types of API spec 19.6; actions without their own type become `<record>.updated`; everything else is ignored.
- **Fan-out in the worker, not the request.** The worker selects undispatched events with `FOR UPDATE SKIP LOCKED`, creates one `webhook_delivery` per matching subscription whose client may read the record type, and sets `dispatched_at` (a column added to the architecture's outbox table). The request path stays a single insert, and scope changes apply to events not yet dispatched.
- **Claim with a lease, send outside the transaction.** Due deliveries are locked with `SKIP LOCKED` and leased (`next_attempt_at` moved 5 minutes ahead) in a short transaction; the HTTP call happens with no transaction open; the result is written in a second transaction with a `webhook_attempt` row (a table added for the delivery log). A crashed worker's claims become due again when the lease ends.
- **Payload built at delivery time.** `data.object` comes from the owning modules' `get` service functions, as `GET` returns it, so retries never send stale data and nothing large is stored in the outbox. The record's `version` is read from that object; the architecture's `entity_version` column is therefore not stored.
- **Per-record ordering in the claim query.** A delivery is not claimed while an earlier delivery (event time, then UUIDv7 event ID) for the same record and subscription is open.
- **Network guard.** `integration.netguard` checks the URL (scheme, no credentials, allowlisted host) at subscription time and at every attempt, resolves the host, refuses the attempt if any address is loopback, link-local, unspecified, multicast, reserved or a metadata address, and connects to the vetted address through a custom httpcore network backend, so a second DNS answer cannot redirect the request while TLS still verifies the URL's host name. Private ranges stay allowed for on-premises systems. Tests replace the `Network` policy to reach a receiver on 127.0.0.1; the default policy is tested separately.
- **Signing and secrets.** `t=<unix>,v1=<hex>` HMAC-SHA256 over `"<t>.<body>"`; after rotation the previous secret also signs for 24 hours (`v1=old,v1=new`). Secrets are Fernet-encrypted with a key derived by HKDF from `APP_ENCRYPTION_KEY` (`app.core.crypto`); production refuses the placeholder value.
- **Test events are queued.** `POST .../test` queues a `ping` delivery and returns `202`; the result appears in the delivery log after one worker poll. The draft said the endpoint returns the receiver's status, which would make the request call the external system (forbidden). Pings bypass client and subscription state, are attempted once, and do not count towards suspension or alerts.
- **Reference receiver.** `deploy/examples/webhook_receiver.py` (standard library only) is both the sample for integrators and the endpoint the exit test delivers to.

## Consequences
- No broker or extra service: the outbox and delivery state live in PostgreSQL, matching the architecture's scale assumptions.
- Delivery latency is one worker poll (5 seconds by default), within NFR-13's 30 seconds.
- A changed `APP_ENCRYPTION_KEY` makes existing secrets unreadable (`secret_unreadable` attempts); Admins must rotate each subscription's secret. The key belongs with the database backups.
- The `httpx` transport's private connection pool is replaced to install the pinned backend; an `httpx` upgrade must keep the netguard tests green.
- Events older than 30 days are deleted with their history; a client switched off for longer loses those deliveries and catches up with sync mode.
