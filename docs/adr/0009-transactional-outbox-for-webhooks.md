# ADR 0009: Transactional outbox in PostgreSQL for webhooks

Status: Accepted · Date: 2026-11-17 · Phase 0

## Context
Webhooks must be sent for committed changes only and must not be lost while a receiver is down (FR-INT-07 AC1). Requests must never call external systems.

## Decision
Business modules publish domain events in-process; the integration module writes `outbox_event` rows in the same transaction. The worker (`python -m app.worker`) delivers them with HMAC-SHA256 signatures, retries with backoff for up to 72 hours, to allowlisted HTTPS hosts only (checked again after DNS resolution). Built in Phase 6; the worker loop exists from Phase 0.

## Consequences
At-least-once delivery; consumers deduplicate by event ID. No broker to operate.
