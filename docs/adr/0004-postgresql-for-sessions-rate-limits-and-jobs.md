# ADR 0004: PostgreSQL for sessions, rate limits, idempotency and jobs

Status: Accepted · Date: 2026-11-17 · Phase 0

## Context
Sessions, rate-limit counters, idempotency records and the webhook outbox need shared state. Redis or a message broker would add operational weight to an on-prem install for 20 users.

## Decision
Keep all of it in PostgreSQL. The worker polls with `SELECT … FOR UPDATE SKIP LOCKED`. Housekeeping jobs purge expired rows. No Redis, broker, cache or search engine in R1.

## Consequences
- One stateful component to back up and restore.
- Throughput is bounded by PostgreSQL, ample for the NFRs; revisit only if a requirement demands it.
