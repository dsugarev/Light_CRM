# 02 — Architecture and Technical Specification

Status: Draft v0.1 · Read together with `01-requirements.md`.

## 1. Architecture summary

A **modular monolith** with a strict split between a single-page frontend and a JSON API backend, backed by one PostgreSQL database, deployed on-premises with Docker Compose. The same API serves the web frontend and the integrated applications (Conclusion, ERP, Billing). A background worker, built from the backend image, delivers webhooks from a transactional outbox.

```
Browser ──────────HTTPS (cookie)──┐
Conclusion / ERP / Billing ─HTTPS (Bearer API key)─┐
                                   v               v
                         Reverse proxy (Caddy)
                           ├── /        -> frontend (static SPA)
                           └── /api/*   -> backend  (FastAPI) ──> PostgreSQL <── worker
                                              └──HTTPS──> OpenRouter -> Cerebras (LLM)
worker ──HTTPS (signed webhooks)──> Conclusion / ERP / Billing endpoints
```

Why this shape: 20 users and three integrated systems do not justify microservices, a message broker or caches. A modular monolith keeps operations trivial while module boundaries keep the R2–R4 expansion clean. Serving the frontend and API under one origin through the proxy removes CORS and makes cookie security simple. PostgreSQL doubles as the outbox and job store (`SELECT … FOR UPDATE SKIP LOCKED`), which is reliable at this volume and avoids another moving part.

## 2. Technology stack

Use the current stable (LTS where one exists) version of each item at implementation time and pin exact versions in lockfiles.

| Layer | Choice | Reason |
|---|---|---|
| Frontend language | TypeScript, strict mode | Type safety shared with the API contract |
| Frontend framework | React with Vite | Mainstream, fast builds, plain SPA (no server rendering needed for an internal tool) |
| Routing | React Router | Standard; supports URL-held filter state |
| Server state | TanStack Query | Caching, invalidation and optimistic updates for the board |
| UI components | shadcn/ui on Tailwind CSS | Accessible primitives, owned in-repo, easy to restyle |
| Forms and validation | React Hook Form + Zod | Typed validation matching backend rules |
| Drag and drop | dnd-kit | Accessible, keyboard-capable Kanban |
| Charts | Recharts | Sufficient for dashboard charts |
| i18n | i18next + react-i18next | English and Bulgarian, namespace per feature |
| Backend language | Python | LiteLLM is a Python library; mature web and data ecosystem |
| Backend framework | FastAPI with Pydantic v2 | Async, generates OpenAPI automatically, strong validation |
| ORM and migrations | SQLAlchemy 2.x (async) + Alembic | Explicit, reviewable, additive migrations |
| Database | PostgreSQL | Relational integrity, JSONB for audit payloads, full-text search with Cyrillic support |
| Password hashing | argon2-cffi (Argon2id) | Current recommended algorithm |
| LLM client | LiteLLM → OpenRouter → Cerebras | Mandated; see section 8 |
| Excel handling | openpyxl | Import and export of XLSX |
| Background worker | Same backend image, `python -m app.worker`; PostgreSQL outbox polled with `SKIP LOCKED` | Webhook delivery and housekeeping without a broker |
| Outbound HTTP | httpx (async) | Webhook delivery with strict timeouts, no redirects |
| Reverse proxy | Caddy | Simple TLS configuration, static file serving |
| Packaging | Docker, Docker Compose | Mandated by on-prem deployment |
| Backend tooling | uv, Ruff, mypy (strict), pytest | Fast, reproducible, typed |
| Frontend tooling | pnpm, ESLint, Prettier, Vitest, Testing Library, MSW | Standard |
| End-to-end tests | Playwright | Cross-browser journeys |

Deliberately **not** used in R1: Redis, message brokers, Kubernetes, a separate search engine, a vector database, an API gateway product. Sessions, rate-limit counters, idempotency records and the webhook outbox live in PostgreSQL. Add these only when a requirement demands them.

## 3. Repository layout

Frontend and backend are fully separate projects. Neither imports code from the other; the only shared artifact is the OpenAPI contract.

```
/
├── CLAUDE.md
├── README.md
├── docker-compose.yml            # production-like stack
├── docker-compose.dev.yml        # dev overrides (hot reload, exposed ports)
├── .env.example
├── docs/                         # these specifications, ADRs in docs/adr/,
│                                 # integration guide and request collection in docs/integration/
├── deploy/                       # Caddyfile, backup and restore scripts
├── backend/
│   ├── pyproject.toml, uv.lock, Dockerfile
│   ├── alembic/                  # migrations
│   ├── app/
│   │   ├── main.py               # app factory, router registration
│   │   ├── worker.py             # background worker entry point (outbox, cleanup jobs)
│   │   ├── core/                 # config, db session, security, principal, errors, logging,
│   │   │                         # pagination (page + cursor), idempotency, rate limiting, events
│   │   ├── modules/
│   │   │   ├── identity/         # users, roles, sessions, auth providers
│   │   │   ├── party/            # organizations, contacts
│   │   │   ├── sales/            # leads, opportunities, pipeline stages
│   │   │   ├── activity/         # activities, tasks, timeline
│   │   │   ├── reporting/        # dashboard queries, export
│   │   │   ├── dataimport/       # XLSX/CSV import
│   │   │   ├── audit/            # audit log
│   │   │   ├── integration/      # integration clients, API keys, scopes, external references,
│   │   │   │                     # webhook subscriptions, outbox, deliveries
│   │   │   └── assistant/        # chat, tools, conversations
│   │   └── llm/                  # the ONLY place that calls LiteLLM
│   └── tests/                    # unit/, api/, migrations/
└── frontend/
    ├── package.json, pnpm-lock.yaml, Dockerfile
    ├── src/
    │   ├── app/                  # router, providers, layout
    │   ├── api/                  # generated types + typed client
    │   ├── features/             # auth, party, leads, opportunities, activities,
    │   │                         # dashboard, import, assistant, admin
    │   ├── components/           # shared UI
    │   ├── i18n/                 # en/*.json, bg/*.json
    │   └── lib/
    └── e2e/                      # Playwright tests
```

Each backend module has the same internal structure: `router.py` (HTTP only), `schemas.py` (Pydantic request/response), `service.py` (business rules, transactions), `repository.py` (queries), `models.py` (SQLAlchemy), `permissions.py`.

### Module boundary rules

- Routers call services. Services call repositories. Routers never touch the database.
- A module may call another module **only through its service's public functions**, never its repositories or models. Enforce this with an import-linter contract in CI.
- Dependencies point one way: `sales → party → identity`; `activity`, `reporting`, `assistant`, `integration` may depend on `sales` and `party`; nothing depends on `assistant` or `integration`. Business modules never call `integration`; they publish domain events, and `integration` turns them into outbox rows in the same transaction. Future modules (`catalog`, `qualification`, `quote`, `agreement`) depend on `sales` and `party`, never the reverse.
- **Principals:** request handling works with a `Principal` (human user or integration client) defined in `core`, never directly with a cookie or API key. Services receive the principal and check permissions through one policy function that combines role, ownership and scopes. This is built in Phase 1 even though integration clients arrive in Phase 6, so no service needs rework.
- Cross-module reactions (for example writing the audit log or a timeline event) go through a small in-process domain event dispatcher in `core`, so new modules can subscribe without editing existing ones.

## 4. Data model

### 4.1 Conventions (apply to every table, now and in future releases)

- Primary keys are UUID (v7 where available), named `id`.
- Every business table has `created_at`, `updated_at`, `created_by`, `updated_by`, and `archived_at` (soft delete). Timestamps are `timestamptz` in UTC.
- Money is `numeric(14,2)` with a `currency` column (`char(3)`, default `EUR`), so multi-currency is a later additive change.
- Configurable lists (stages, sources, reasons, industries) are **lookup tables**, not database enums, so values can be changed without a migration.
- Table names are singular snake_case, prefixed by nothing; foreign keys are `<table>_id` with explicit `ON DELETE` behavior (default `RESTRICT`).
- Optimistic concurrency via an integer `version` column on leads and opportunities; a stale update returns HTTP 409.
- Text search uses PostgreSQL full-text with the `simple` configuration plus `pg_trgm` for partial matches, which works for both Latin and Cyrillic.

### 4.2 Migration policy — the extensibility guarantee

- All schema change goes through Alembic; no manual DDL, no `create_all` outside tests.
- Migrations are **additive**: new tables, new nullable columns or columns with defaults, new indexes. Renames and removals use expand → migrate → contract across separate releases, and a "contract" step needs an ADR.
- A released migration file is never edited; fixes are new migrations.
- Every migration has a working downgrade and is covered by the migration test (see test strategy).
- Reference data that the application needs to run (default stages, roles, reasons) is inserted by data migrations, idempotently.

### 4.3 R1 entities

| Module | Table | Key columns and notes |
|---|---|---|
| identity | `app_user` | user_type (`human` / `service`), email (unique, case-insensitive), full_name, password_hash (nullable), role_id, locale, is_active, auth_provider (`local`), external_subject, failed_login_count, locked_until, mfa_secret. Service users have no password and cannot sign in or own records |
| identity | `role` | code (`admin`, `sales_manager`, `sales_rep`, `viewer`, `integration`), name |
| identity | `user_session` | token_hash, user_id, created_at, last_seen_at, expires_at, ip, user_agent |
| identity | `password_token` | token_hash, user_id, purpose (set / reset), expires_at, used_at |
| party | `organization` | name, name_normalized, registration_number, vat_number, industry_id, size_band, website, address fields, owner_id |
| party | `contact` | first_name, last_name, job_title, email, phone, preferred_locale, organization_id (nullable), anonymized_at |
| sales | `lead` | title, company_name, contact_name, email, phone, source_id, status, description, estimated_value, owner_id, bant_budget, bant_authority, bant_need, bant_timeline (+ note for each), fits_target_profile, disqualification_reason_id, organization_id, contact_id, converted_opportunity_id, import_batch_id, version |
| sales | `pipeline` | name, is_default (one row in R1) |
| sales | `pipeline_stage` | pipeline_id, name, position, default_probability, stage_type (open / won / lost), is_active |
| sales | `opportunity` | name, organization_id, primary_contact_id, owner_id, pipeline_id, stage_id, amount, currency, probability, expected_close_date, actual_close_date, next_step, description, source_lead_id, loss_reason_id, competitor, import_batch_id, version |
| sales | `opportunity_stage_history` | opportunity_id, from_stage_id, to_stage_id, changed_by, changed_at |
| sales | `lead_source`, `disqualification_reason`, `loss_reason`, `industry` | code, name_en, name_bg, is_active, position |
| integration | `external_system` | code (`conclusion`, `erp`, `billing`), name_en, name_bg, is_active, position (lookup list) |
| integration | `integration_client` | name, external_system_id, service_user_id (→ `app_user`), scopes (text array), default_owner_id, ip_allowlist (cidr array), technical_contact, rate_limit_per_minute, is_active |
| integration | `api_key` | client_id, key_id (public part, unique), secret_hash, label, expires_at, revoked_at, last_used_at, last_used_ip |
| integration | `external_reference` | entity_type, entity_id, external_system_id, external_id, url. Unique (external_system_id, entity_type, external_id) and (entity_type, entity_id, external_system_id) |
| integration | `idempotency_record` | client_id, key, request_hash, status, response_status, response_body (JSONB), expires_at. Unique (client_id, key) |
| integration | `outbox_event` | event_type, entity_type, entity_id, actor (JSONB), changes (JSONB), details (JSONB), occurred_at, dispatched_at. Written in the business transaction; the worker sets dispatched_at when it fans the event out (ADR 0025) |
| integration | `webhook_subscription` | client_id, url, event_types (text array), secret (encrypted), previous_secret (encrypted, with expiry), is_active, failing_since, suspended_at |
| integration | `webhook_delivery` | event_id, subscription_id, status, attempt_count, next_attempt_at, first_attempt_at, last_status_code, last_error, last_response_excerpt, delivered_at. Index on (status, next_attempt_at) |
| integration | `webhook_attempt` | delivery_id, number, attempted_at, duration_ms, status_code, error, response_excerpt (the delivery log, ADR 0025) |
| activity | `activity` | type (note / call / meeting / email / task), subject, body, occurred_at, due_at, done_at, owner_id, assignee_id, and nullable links: lead_id, opportunity_id, organization_id, contact_id (at least one required by a check constraint) |
| audit | `audit_log` | occurred_at, actor_id, action, entity_type, entity_id, before (JSONB), after (JSONB), ip, request_id. Append-only: the application database role has INSERT and SELECT only on this table |
| dataimport | `import_batch` | entity_type, file_name, status, row counts, created_by, rolled_back_at |
| assistant | `chat_conversation` | user_id, title, context_entity_type, context_entity_id |
| assistant | `chat_message` | conversation_id, role (user / assistant / tool), content, tool_calls (JSONB), prompt_tokens, completion_tokens |

### 4.4 How later releases attach (do not build now; do not block)

- R2: `product_offering`, `product_offering_qualification` (→ `opportunity_id`, `organization_id`), `solution_configuration`, `site_survey`.
- R3: `quote` and `quote_item` (→ `opportunity_id`), `proposal`, `agreement` (→ `organization_id`, `quote_id`).
- R4: `sales_channel`, `partner` as a role on `organization`; reporting views.

R1 must therefore keep `opportunity` and `organization` as stable anchors, and must not put product, price or contract fields onto them as shortcuts. Likewise, identifiers from other systems go into `external_reference`, never into new columns such as `erp_customer_number` on business tables.

### 4.5 Integration data rules

- `updated_at` is set by the database on every change (trigger), including archive, anonymize and external-reference changes, so sync mode is reliable. Every syncable table has an index on `(updated_at, id)`.
- Webhook payloads carry the record's `version` (leads and opportunities) taken from the record when the event is delivered, letting consumers discard stale events; it is not stored in the outbox (ADR 0025).
- Webhook secrets are encrypted at rest with a key from the environment (`APP_ENCRYPTION_KEY`), because they must be readable to sign deliveries; API key secrets are only hashed.
- Housekeeping jobs in the worker: purge expired idempotency records (24 h), outbox events with their deliveries and attempts older than 30 days, usage counters older than 30 days, and expired sessions.

## 5. API conventions

The full endpoint catalog, access levels, error codes, payload examples and streaming format are in `05-api-specification.md`. The points below are the summary.

- Base path `/api/v1`. JSON only. Resource-oriented, plural nouns: `/leads`, `/opportunities`, `/organizations`, `/contacts`, `/activities`, `/pipeline-stages`, `/users`.
- State changes that are not simple updates are explicit sub-resources: `POST /leads/{id}/convert`, `POST /leads/{id}/disqualify`, `POST /opportunities/{id}/move`, `POST /opportunities/{id}/close`.
- Lists: `?page=1&page_size=25&sort=-created_at&q=...` plus field filters. Response envelope: `{ "items": [...], "total": n, "page": n, "page_size": n }`. Maximum page size 100.
- Errors follow RFC 9457 problem details, with a stable machine-readable `code` and field-level `errors` for validation failures. The frontend maps `code` to translated messages; the backend does not return translated text.
- Updates use `PATCH` with the record `version`; a mismatch returns 409.
- FastAPI's generated OpenAPI document is the contract. `frontend/src/api/schema.d.ts` is generated from it with `openapi-typescript`; CI fails if the generated file is out of date. Hand-written API types in the frontend are not allowed.
- Integrated applications call the same endpoints with `Authorization: Bearer <api_key>`; the scope each operation requires is declared once, next to the route, and published in the OpenAPI document as a security requirement. Lists support cursor-based sync mode (`updated_since`), creates accept `Idempotency-Key`, and changes are pushed as signed webhooks. Details: `05-api-specification.md` section 19.
- Naming is kept close to TM Forum Open APIs (TMF699 `salesLead`, `salesOpportunity`; TMF632 `organization`, `individual`) so a conformant facade could be added later, but the R1 API is pragmatic REST, not a TMF implementation.

## 6. Frontend architecture

- Feature folders own their pages, components, hooks and translations. Shared UI lives in `components/`.
- All server data goes through TanStack Query hooks wrapping the typed client. No `fetch` calls in components.
- List filters, sorting and pagination live in the URL query string.
- The Kanban board uses optimistic updates and rolls back with a toast on a 403 or 409.
- Route-level code splitting; an error boundary per route; a global handler turns 401 into a redirect to sign-in.
- The assistant drawer is mounted in the app layout and consumes a Server-Sent Events stream.
- Role checks in the UI use one `can(action, record)` helper that mirrors the backend permission rules; it is a convenience only.

## 7. Security design

| Area | Design |
|---|---|
| Transport | HTTPS only at the proxy; HSTS; HTTP redirects to HTTPS. Backend and database ports are not published outside the Compose network. |
| Sessions | Random 256-bit opaque token; only its SHA-256 hash is stored. Cookie flags: `HttpOnly`, `Secure`, `SameSite=Strict`, path `/api`. No tokens in localStorage. |
| CSRF | `SameSite=Strict` plus a required custom header (`X-Requested-With`) on all mutating requests, checked server-side, plus `Origin` validation. |
| Passwords | Argon2id with current OWASP parameters; policy per FR-AUTH-03; constant-time comparison; generic sign-in errors. |
| Brute force | Per-account lockout (FR-AUTH-01) and per-IP rate limiting on auth endpoints. |
| Authorization | Deny by default. A permission dependency on every route; object-level checks in services (owner or elevated role). An automated test walks every route × role (see test strategy). |
| Input | Pydantic validation at the boundary; SQLAlchemy parameterized queries only; no string-built SQL. |
| Output | React escaping by default; `dangerouslySetInnerHTML` is forbidden; assistant output is rendered as sanitized Markdown with no raw HTML. |
| Headers | Content-Security-Policy (self only, no inline script), `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`. |
| File upload | Import accepts only `.xlsx` and `.csv`, maximum 10 MB, parsed in memory, never executed or stored on a served path; formulas are ignored. Exports prefix cells starting with `= + - @` to prevent spreadsheet formula injection. |
| Secrets | From environment variables or Docker secrets only; `.env` is git-ignored; `.env.example` holds placeholders. The application refuses to start with default secrets when `ENV=production`. |
| Database | Separate roles for migration (DDL) and application (DML); audit table is append-only for the application role. |
| Dependencies | Lockfiles committed; `pip-audit` and `pnpm audit` in CI; containers run as non-root with read-only root filesystems where practical. |
| Logging | No passwords, tokens, cookies or chat bodies in logs. Security events go to the audit log. |
| Integration authentication | Bearer API keys `crm_<env>_<key_id>_<secret>`; lookup by `key_id`, constant-time comparison of the SHA-256 hash of the secret; expiry, revocation, optional IP allowlist per client; cookie and bearer on the same request rejected. CSRF checks apply only to cookie-authenticated requests. |
| Integration authorization | Scopes checked by the same policy function as roles; endpoints absent from the scope table are denied to integrations by default; integration principals cannot reach admin, import, export, audit, GDPR or assistant routes. |
| Webhooks | HMAC-SHA256 signatures with timestamp; HTTPS only; host allowlist (`WEBHOOK_ALLOWED_HOSTS`) checked at subscription time and again at delivery after DNS resolution, to prevent SSRF; no redirects; 10-second timeout; response bodies truncated before storage. |
| SSO readiness | `AuthProvider` interface with a `LocalPasswordProvider` implementation; an `OidcProvider` can be added and users matched on `external_subject`. |

## 8. AI assistant design

### 8.1 LLM access — mandatory rule

**When writing code that calls an LLM, use your Cerebras skill to use LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b` model with Cerebras as the inference provider.** The skill is the authority on the exact call; the sketch below shows the intended shape, and where the two differ, follow the skill.

```python
# backend/app/llm/client.py — the only module allowed to import litellm
from litellm import acompletion

async def chat(messages, tools=None, stream=True):
    return await acompletion(
        model=settings.LLM_MODEL,            # "openrouter/openai/gpt-oss-120b"
        messages=messages,
        tools=tools,
        stream=stream,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        extra_body={"provider": {"order": ["cerebras"], "allow_fallbacks": False}},
    )
```

Configuration comes from environment variables: `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_PROVIDER`, `LLM_TIMEOUT_SECONDS`, `AI_ENABLED`, `AI_DAILY_TOKEN_BUDGET`. Nothing else in the codebase imports `litellm`; an import-linter rule enforces this, which also makes the model swappable and the tests mockable.

### 8.2 Flow

1. The frontend posts the user message to `POST /api/v1/assistant/conversations/{id}/messages` and reads a Server-Sent Events stream.
2. The backend builds the prompt: system instructions, the user's name, role and locale, today's date, optional record context, and recent conversation history trimmed to a token limit.
3. The model may request tools. The backend executes each tool **through the same service layer and permission checks as the REST API**, as the signed-in user, and returns compact JSON results.
4. The loop ends on a final answer or after 5 tool rounds. The answer is streamed, then stored with token counts.

### 8.3 Tools in R1 (all read-only)

`search_leads`, `search_opportunities`, `search_organizations`, `get_record` (by type and ID), `list_activities`, `pipeline_summary`, `forecast_summary`, `my_tasks`. Each has a strict JSON schema, bounded result sizes (maximum 25 rows), and returns record IDs so the answer can link to records.

The model never receives database access, never writes SQL, and has no tool that changes data.

### 8.4 Guardrails

- **Prompt injection:** CRM text (notes, descriptions, imported data) is untrusted. It is passed only inside tool results, the system prompt instructs the model to treat tool content as data, and because no write tools exist, injected text cannot change anything.
- **Data minimization:** tool results contain only the fields needed; no password hashes, sessions, audit data or other users' chat history are ever reachable by tools.
- **Limits:** per-user rate limit, daily token budget, request timeout, maximum tool rounds, maximum message length.
- **Failure:** provider errors and timeouts become a translated, friendly chat error; nothing else in the application depends on the LLM.
- **Privacy:** chat content is stored in the database for the user's history but never written to application logs. `AI_ENABLED=false` removes the drawer and disables the endpoints.
- **Honesty:** the system prompt instructs the model to answer only from tool results and to say when data is missing.

## 9. Deployment and operations

- Compose services: `proxy` (Caddy, serves the built SPA and proxies `/api`), `backend` (Uvicorn workers), `worker` (same image, `python -m app.worker`, delivers webhooks and runs housekeeping), `db` (PostgreSQL with a named volume), `backup` (scheduled `pg_dump` to a mounted backup path, 30-day retention).
- Network: the proxy is reachable from user workstations and from the Conclusion, ERP and Billing servers; the worker needs outbound HTTPS to the webhook hosts in `WEBHOOK_ALLOWED_HOSTS`. Both are documented for the network team in the operations guide.
- Migrations run as a one-shot `migrate` service before `backend` starts.
- Health endpoints: `/api/health/live` and `/api/health/ready` (checks the database); Compose healthchecks use them.
- Configuration is by environment variables only (twelve-factor); `.env.example` documents each one.
- First run: a CLI command `python -m app.cli create-admin` creates the initial Admin; there is no default account.
- `deploy/` contains a documented restore script and an upgrade procedure (pull images → backup → migrate → restart).
- CI (pipeline definition included in the repo): lint, type check, unit and API tests, frontend tests, contract-drift check, i18n key check, dependency audit, image build, then Playwright against the composed stack.

## 10. Architecture decision records

Record each significant decision as a short ADR in `docs/adr/NNNN-title.md` (context, decision, consequences). Seed ADRs to write during Phase 0: modular monolith; FastAPI and React stack; cookie sessions over JWT; PostgreSQL for sessions and rate limits; additive-only migrations; read-only AI assistant; LLM routing via LiteLLM, OpenRouter and Cerebras; one API for frontend and integrations with scoped API keys; transactional outbox in PostgreSQL for webhooks; external references table for cross-system IDs.
