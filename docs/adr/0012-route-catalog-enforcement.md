# ADR 0012: Enforcing the endpoint catalog and access levels

Status: Accepted · Date: 2026-11-17 · Phase 0

## Context
CLAUDE.md requires that only endpoints in `docs/05-api-specification.md` are built, with the documented access levels, and that every endpoint is in the authorization matrix.

## Decision
- Each route declares its access level once: `openapi_extra=access(AccessLevel.X)` (`app/core/access.py`); the value is the exact wording of the spec table and appears in the OpenAPI document as `x-access-level`.
- `tests/api/test_route_catalog.py` parses the spec tables and fails when a route is not in the catalog, when its declared level differs from the spec, or when a catalog entry has neither a route nor an entry in `tests/api/catalog_pending.py`. Each phase removes the entries it builds from the pending list.
- Routes are read from the public OpenAPI document (FastAPI 0.163 keeps included routers in private structures); `include_in_schema=False` is therefore forbidden in `app/` and checked by a test.
- Phase 1 extends this into the full route × role (× scope) authorization matrix, with the permission dependency that enforces the declared level.

## Consequences
The spec, the code and the tests cannot drift silently; changing an endpoint starts with editing the spec.
