# ADR 0011: Local HTTPS through Caddy; development ports only in the dev override

Status: Accepted · Date: 2026-11-17 · Phase 0

## Context
CLAUDE.md said the backend is available at `http://localhost:8000`; the architecture says only the proxy is published and the Phase 0 exit requires HTTPS locally. Decision confirmed by the owner on 2026-11-17.

## Decision
- `docker-compose.yml` (production-like, used by `scripts/start-*`): only Caddy publishes ports 80/443; the app is at `https://localhost` with Caddy's internal CA (`CRM_TLS=internal`), or IT's certificate in production (`CRM_TLS="/certs/crm.crt /certs/crm.key"`). `ENV=production`, so the OpenAPI document and `/api/docs` are not published until Phase 1 adds authentication.
- `docker-compose.dev.yml` adds `ENV=development`, the backend on `http://localhost:8000` (hot reload, `/api/docs`), PostgreSQL on `localhost:5432` with a `crm_test` database. The SPA dev server runs on the host (`pnpm dev`, port 5173, proxying `/api`).
- Browsers warn about Caddy's local CA unless it is trusted; Playwright ignores certificate errors for this origin only.

## Consequences
The same proxy configuration (headers, CSP, routing) is exercised locally, in CI and in production. The interactive docs page loads assets from a CDN, so it is used directly on port 8000 in development rather than through Caddy's CSP.
