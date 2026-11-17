# ADR 0015: Runtime settings and rate limits as core infrastructure

Status: Accepted · Date: 2026-11-17 · Phase 1

## Context
Session timeouts must be configurable by an Admin (FR-AUTH-04, API spec 6.1), and later phases add their own settings (stale-opportunity days, AI budgets). Rate limits must live in PostgreSQL (ADR 0004).

## Decision
- `app_setting` is a single-row table (`id = 1`) owned by `app/core/runtime_settings.py`, with `GET/PATCH /api/v1/settings` (Admin, audited). Each later setting is a new column with a default (additive migration). Values are cached for 30 seconds per process because every authenticated request reads the timeouts.
- `rate_limit_bucket` (key, window start, hits) is owned by `app/core/ratelimit.py`: fixed windows, counted in a separate short transaction so they count even when the request fails, and purged hourly by the worker. Limits come from the environment (API spec section 18 defaults).
- Both tables are core infrastructure rather than a business module; Alembic's `env.py` registers them alongside module models.

## Consequences
Changing a timeout takes effect within 30 seconds on every backend process. Rate limits apply per client IP, so a shared IP (CI, NAT) may need higher limits, which are configurable.
