# ADR 0013: Principal resolution and the single permission policy

Status: Accepted · Date: 2026-11-17 · Phase 1

## Context
Every endpoint needs a permission check (CLAUDE.md), integration clients must reuse the same endpoints and rules (ADR 0008), and `core` must not depend on business modules (ADR 0001).

## Decision
- `app/core/principal.py` defines `Principal` (type user/integration, user ID, role, display name, scopes, session ID).
- `app/core/auth.py` resolves the principal through an injected `Authenticator` (`app.state.authenticator`, wired in `app.main` to `identity.service.authenticate_request`). Core never imports identity.
- Each route declares its access once: `@router.get(..., **endpoint(AccessLevel.X, scope="…"))`. That both publishes `x-access-level` (and `x-required-scope`) in OpenAPI and adds the dependency that enforces it through `app/core/policy.check_access`.
- `check_access` combines role and integration scope at route level. Object rules (Owner+) are checked in services with `check_owner`/`can_edit_owned` once the record is loaded. Integration principals are deny-by-default: a route without a scope returns `permission.not_for_integrations`.
- Permission codes for the UI (`records.edit_own`, `users.manage`, …) are derived from the role in `ROLE_PERMISSIONS` and returned by `GET /me`.
- The authorization matrix test derives expectations from the access levels in the API specification, not from the code.

## Consequences
- Adding a route without `endpoint(...)` fails the route catalog test (no `x-access-level`).
- Phase 6 adds bearer-key resolution inside the authenticator and new principals of type INTEGRATION; services stay unchanged.
