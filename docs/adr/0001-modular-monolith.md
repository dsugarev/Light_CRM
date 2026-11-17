# ADR 0001: Modular monolith

Status: Accepted · Date: 2026-11-17 · Phase 0

## Context
About 20 internal users and three integrated applications (Conclusion, ERP, Billing). The product must grow through R2–R4 (catalog, quoting, contracts) without rewrites. Operations are on-premises with a small team.

## Decision
One backend deployable (FastAPI) split into modules under `backend/app/modules/` (identity, party, sales, activity, reporting, dataimport, audit, integration, assistant), a separate SPA, one PostgreSQL database, and a worker built from the backend image. Module boundaries are enforced with import-linter (`backend/pyproject.toml`):
- entry points > modules > llm > core;
- module direction: `assistant | integration` > `dataimport | reporting | audit` > `activity` > `sales` > `party` > `identity`;
- inside a module: router > service > repository > models; routers never import repositories, models or SQLAlchemy;
- a module's router, repository and models are private: other modules use its service only.

## Consequences
- Simple deployment and transactions across modules; no network calls between modules.
- Boundaries hold only through CI; the contracts fail the build on a forbidden import.
- Cross-module reporting must go through service functions, which may need purpose-built aggregate functions in `sales`/`party` services.
- New R2–R4 modules slot in above `sales`/`party`; adding them means adding a layer entry and a "private internals" contract.
