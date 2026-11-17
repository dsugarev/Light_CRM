# ADR 0017: Shared list machinery and sync mode with signed cursors

Status: Accepted · Date: 2026-11-17 · Phase 2

## Context
Every list endpoint needs the same paging, sorting, filtering and search behaviour (API spec 1.3), and integrations need reliable incremental sync (FR-INT-05) without skipping or repeating records while data changes.

## Decision
- `app/core/listing.py`: a `list_query(...)` dependency parses `page`, `page_size`, `sort`, `q`, `include_archived`, `updated_since`, `cursor`; module-specific filters are declared on the route (so they appear in OpenAPI) and listed for validation. Unknown parameters, unknown sort fields, page sizes over 100 (500 in sync mode) and bad cursors return `400 validation.failed` with a field code.
- Page mode returns `{items, total, page, page_size}`; ties are broken by `id` so paging is stable.
- Sync mode (`updated_since`) orders by `(updated_at, id)`, includes archived rows, and returns `{items, next_cursor}`. The cursor is `base64url(JSON{resource, updated_at, id})` plus an HMAC-SHA256 signature (truncated to 128 bits) with `APP_SECRET_KEY`; a cursor from another list or altered in any way is refused.
- Rows newer than `SYNC_SAFETY_LAG_SECONDS` (default 5) are held back, so a transaction that commits after a client has paged past its `updated_at` timestamp is not skipped. `updated_at` is set by the database trigger in every change, and each syncable table has an index on `(updated_at, id)`.
- A record changed during paging is delivered again in its new version later in the same run; consumers deduplicate by `id` and keep the newest `updated_at`.

## Consequences
- `APP_SECRET_KEY` is a new required secret (refused at its placeholder in production; start scripts generate it). Rotating it invalidates outstanding cursors, so clients restart from their last stored `updated_since`.
- A transaction longer than the safety lag could still be skipped; transactions in this application are short, and the lag is configurable.
