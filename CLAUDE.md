# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this project is

A light B2B CRM for a telecom Commercial team (about 20 internal users, on-premises). Release 1 delivers Lead and Opportunity Management with an AI assistant, and an integration API consumed by three other company applications: Conclusion, ERP and Billing. Later releases add product qualification, quoting and contracts by **extending** this codebase and schema, never rewriting them.

## Read before you work

| Document | Use it for |
|---|---|
| `docs/01-requirements.md` | What to build: requirements with IDs and acceptance criteria, scope, open questions |
| `docs/02-architecture.md` | How to build it: stack, layout, data model, API, security, AI design |
| `docs/03-implementation-plan.md` | Order of work, phase exits, definition of done |
| `docs/04-test-strategy.md` | What tests are required and how |
| `docs/05-api-specification.md` | Every REST endpoint: path, purpose, access level, requirement IDs, error codes, payload shapes; section 19 is the integration API (scopes, external references, sync, idempotency, webhooks) |
| `docs/adr/` | Decisions already made; add one for each new significant decision |
| `docs/Plan.md` | Implementation log: what each phase built, with code excerpts, deviations and open items. Update it with every implemented task |

These documents are the source of truth. If code and documents disagree, raise it; do not silently pick one.

## Working agreement

1. Work **one phase at a time**, in the order of the implementation plan. Propose a task breakdown at the start of a phase and wait for approval. Stop for review at the end of each phase.
2. Ask when a requirement is ambiguous. Do not invent requirements and do not build anything listed as out of scope or as a future release.
3. Write tests alongside code; name tests with requirement IDs. Never weaken, skip or delete a test to get a green run.
4. Before saying a task is done, run the full quality gate below and report the real results, including failures.
5. Small commits in Conventional Commits style. Never commit secrets or `.env`.

## Hard rules

- **Strict separation:** `frontend/` and `backend/` are independent projects. No shared code and no cross-imports. The only shared artifact is the OpenAPI contract; frontend API types are generated, never hand-written.
- **Layering (backend):** router → service → repository. Business rules and permission checks live in services. Modules talk to each other only through service functions. Dependency direction is in architecture section 3.
- **Database:** all schema change through Alembic. Migrations are additive only; never edit a released migration; no destructive change without an ADR and owner approval. Follow the table conventions in architecture section 4.1. Lookup tables, not database enums, for configurable lists.
- **API catalog:** build only endpoints listed in `docs/05-api-specification.md`, with the paths, access levels and error codes given there. To add or change an endpoint, update that document first in the same change.
- **Security:** every endpoint has a permission check and an entry in the authorization matrix test. Server-side checks are the authority. No tokens in localStorage, no string-built SQL, no `dangerouslySetInnerHTML`, no secrets in code or logs.
- **One API, two kinds of caller:** the web frontend (cookie session) and integrated applications (bearer API key) use the same `/api/v1` endpoints and services. Never create integration-only copies of business logic. Code works with a `Principal`, and permissions combine role, ownership and scopes in one policy function.
- **Integrations are deny-by-default:** an endpoint is open to integration clients only if it is in the scope table in `docs/05-api-specification.md` 19.3, with its scope declared on the route. Integration clients never reach admin, import, export, audit, GDPR or assistant endpoints.
- **API keys** are shown once, stored only as hashes, and never logged. Webhook secrets are encrypted at rest.
- **Cross-system IDs** (ERP customer number, Billing account ID, Conclusion IDs) go in the `external_reference` table, never as new columns on business tables.
- **Webhooks only through the outbox:** business modules publish domain events; the integration module writes outbox rows in the same transaction; only the worker makes outbound HTTP calls, to allowlisted HTTPS hosts. Never call an external system from inside a request.
- **API stability:** changes to `/api/v1` are additive only. A change that could break Conclusion, ERP or Billing (renaming or removing a field, changing a type or meaning, tightening validation) needs owner approval and a new API version.
- **Audit:** every create, update and delete writes an audit entry, whether made by a user or an integration client.
- **i18n:** no hard-coded user-facing strings; every key exists in both `en` and `bg`. The backend returns error codes, not translated text.
- **LLM calls:** when writing code to make calls to LLMs, use your Cerebras skill to use LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b` model with Cerebras as the inference provider. All LLM calls go through `backend/app/llm/client.py`; no other file imports `litellm`. Tests never call the live model.
- **AI assistant is read-only in R1:** do not add any tool that creates, changes or deletes data. Tools run with the signed-in user's permissions through the service layer.
- **Dependencies:** do not add a library, service or infrastructure component that is not in the architecture document without proposing it first. Pin exact versions.
- **No real customer data** in code, tests, fixtures, seeds or prompts.

## Commands

Established in Phase 0; keep this section current.

```bash
# Production-like stack (Caddy on https://localhost; only ports 80/443 published).
# First run creates .env from .env.example with generated passwords.
scripts/start-mac.sh        scripts/stop-mac.sh
scripts/start-linux.sh      scripts/stop-linux.sh
scripts/start-windows.ps1   scripts/stop-windows.ps1

# Development stack: backend with hot reload on http://localhost:8000 (/api/docs),
# PostgreSQL on localhost:5432 with a crm_test database (ADR 0011)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Backend (from backend/)
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run python -m app.worker                                   # webhook delivery and housekeeping
uv run python -m app.cli export-openapi --output openapi.json # OpenAPI document for the frontend
uv run python -m app.cli create-admin                         # Phase 1
uv run python -m app.cli create-integration-client            # Phase 6
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest                 # needs PostgreSQL: TEST_DATABASE_URL / TEST_APP_DATABASE_URL

# Frontend (from frontend/)
pnpm install
pnpm dev                      # http://localhost:5173, proxies /api to :8000
pnpm lint && pnpm typecheck
pnpm test
pnpm check:i18n
pnpm generate:api [file|url]  # regenerate src/api/schema.d.ts from the backend OpenAPI document
pnpm e2e                      # Playwright against https://localhost (E2E_BASE_URL to override)
```

Adding an endpoint: add it to `docs/05-api-specification.md`, declare `openapi_extra=access(AccessLevel.X)` on the route, remove it from `backend/tests/api/catalog_pending.py`, regenerate the frontend types (ADR 0012).

## Quality gate (run before declaring work complete)

Backend: ruff, mypy, import-linter, pytest (unit, API, migration). Frontend: lint, typecheck, Vitest, API types up to date, i18n key check. For user-facing changes: the relevant Playwright journeys. For API changes: the authorization matrix (including integration scopes), the integration API tests, and a check that the change is additive for `/api/v1`. Then check the phase's definition of done in `docs/03-implementation-plan.md`.

## Conventions in brief

- Python: type hints everywhere, async I/O, Pydantic schemas at boundaries, no business logic in routers.
- TypeScript: strict mode, no `any`, feature folders, server data only through TanStack Query hooks, list state in the URL.
- API: `/api/v1`, plural resources, RFC 9457 problem details, paginated envelope, `PATCH` with `version` for optimistic concurrency.
- Naming follows TM Forum ODA vocabulary: lead, opportunity, organization, contact (individual), party.
- Timestamps in UTC in storage, Europe/Sofia in the UI. Money as `numeric(14,2)` plus currency, EUR.
