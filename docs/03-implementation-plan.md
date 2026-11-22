# 03 — Implementation Plan

Status: Draft v0.1 · Requirement IDs refer to `01-requirements.md`.

## How to work through this plan

- Build **one phase at a time, in order**. Each phase ends in a working, tested, runnable system.
- At the start of a phase: re-read the relevant requirement and architecture sections, then propose a short task breakdown and wait for approval before coding.
- At the end of a phase: run the full quality gate, update `README.md` and any affected docs, write ADRs for decisions made, summarize what was built and what was deferred, and **stop for owner review**. Do not start the next phase unprompted.
- If a requirement is ambiguous or seems wrong, ask. Do not guess silently and do not expand scope.
- Keep commits small and described in Conventional Commits style, one logical change each.

## Definition of done (every phase)

1. Acceptance criteria of the phase's requirements pass as automated tests, with test names referencing requirement IDs.
2. `docker compose up` from a clean checkout yields a working system.
3. Lint, type checks and all test suites are green; no skipped tests without a linked reason.
4. New endpoints have permission checks and appear in the route × role authorization test.
5. New UI text exists in both English and Bulgarian.
6. Schema changes are Alembic migrations that are additive and pass the migration tests.
7. Create, update and delete paths write audit entries.
8. The OpenAPI-generated frontend types are regenerated and committed.
9. Endpoints built in the phase match `05-api-specification.md` (paths, access levels, error codes); any deviation is reflected in that document in the same change.

## Phase 0 — Foundation

Goal: an empty but production-shaped skeleton.

- Repository layout exactly as in the architecture document; `frontend/` and `backend/` as independent projects.
- Backend: app factory, settings, async database session, error handling (problem details), structured logging with request IDs, health endpoints, Alembic initialized, pytest with a PostgreSQL test database.
- Frontend: Vite + React + TypeScript strict, router, layout shell, TanStack Query, Tailwind and shadcn/ui, i18next with `en` and `bg`, typed API client generated from OpenAPI.
- Compose files, Dockerfiles, Caddyfile, `.env.example`.
- CI pipeline with every gate from architecture section 9; import-linter contracts for module boundaries and the `litellm` import rule.
- Seed ADRs.

Exit: the sign-in page placeholder loads over HTTPS locally in both languages; `/api/health/ready` is green; CI is green.

## Phase 1 — Identity, access and audit

Requirements: FR-AUTH-01 to 06, FR-ADM-01, FR-ADM-03, FR-I18N-01 to 03.

- Users (with `user_type`), roles, sessions, password tokens; `AuthProvider` interface with the local provider.
- The `Principal` abstraction and a single permission policy that already accepts scopes, so integration clients in Phase 6 plug in without changing services (architecture section 3).
- Sign-in, sign-out, set and reset password, lockout, rate limiting, CSRF protection, security headers.
- Permission framework and the route × role authorization test.
- Audit module with the domain event dispatcher; audit log viewer for Admin.
- Admin user management screens; `create-admin` CLI; profile page with language switch.

Exit: an Admin can create a Sales Rep, who can set a password and sign in; every action appears in the audit log.

## Phase 2 — Organizations and contacts

Requirements: FR-PARTY-01 to 04, FR-ADM-02 (industries).

- Party module: CRUD, archive, duplicate detection, search with Cyrillic support.
- Shared list infrastructure supporting both page and cursor (sync mode, `updated_since`) pagination, the database `updated_at` trigger and `(updated_at, id)` indexes. Every later list endpoint reuses it.
- Domain events published for every change (created, updated, archived…), consumed by audit now and by the outbox in Phase 6.
- List and detail pages; organization 360 page with empty placeholders for leads, opportunities and timeline.
- Reusable frontend building blocks established here and reused later: data table with URL state, form patterns, confirmation dialogs, toasts, empty and error states.

## Phase 3 — Leads

Requirements: FR-LEAD-01 to 06, FR-ADM-02 (sources, disqualification reasons).

- Lead CRUD, lifecycle state machine implemented in the service layer, BANT qualification and score, assignment.
- Lead list and detail pages.
- Conversion is built in Phase 4, once opportunities exist.

## Phase 4 — Opportunities, pipeline and activities

Requirements: FR-OPP-01 to 06, FR-LEAD-04, FR-ACT-01 to 03, FR-ADM-02 (stages, loss reasons).

- Pipeline and stage configuration with seeded defaults; opportunity CRUD, move, close, reopen, stage history, optimistic concurrency.
- Kanban board with drag and drop and a keyboard alternative; list view; stale indicator.
- Lead conversion as a single transaction.
- Activities, tasks, "My tasks", and the merged timeline on every record page.

Exit: the full journey lead → qualify → convert → progress → close won works end to end and is covered by a Playwright test.

## Phase 5 — Dashboard, export and import

Requirements: FR-REP-01 to 03, FR-IMP-01.

- Reporting queries and dashboard charts; forecast figures verified against independently computed values.
- XLSX and CSV export from every list, with formula-injection protection and audit.
- Import wizard: upload, column mapping, validation preview, commit, batch rollback; downloadable templates.
- Seed script producing the NFR-01 data volumes, and a performance check against the 500 ms target.

## Phase 6 — Integration API (Conclusion, ERP, Billing)

Requirements: FR-INT-01 to 12, NFR-13 to 15. Design: `05-api-specification.md` section 19, architecture sections 4.5 and 7.

- Integration module: `external_system` list seeded with `conclusion`, `erp`, `billing`; integration clients with service users; API keys; bearer authentication; scope enforcement through the Phase 1 policy, with the scope table from API spec 19.3 declared next to each route.
- External references: endpoints, list filters, embedding in resources, display on record pages in the UI.
- Idempotency for integration creates and actions.
- Transactional outbox fed by the domain events; `worker` service with webhook delivery, signing, retries, suspension and housekeeping; host allowlist.
- Admin API and screens for clients, keys, subscriptions, delivery log, test event and redeliver; per-client usage counters and the failing-delivery alert.
- Per-client rate limiting.
- The three initial clients created by a seed/CLI command (`python -m app.cli create-integration-client`) with the read-only profiles from API spec 19.9, disabled until keys are issued.
- `docs/integration-guide.md` and a request collection in `docs/integration/`, plus a small reference consumer script (`deploy/examples/webhook_receiver.py`) that verifies signatures, used in tests and handed to the integrating teams.

Exit: a test client using only an API key can sync organizations with `updated_since`, receives a signed `opportunity.closed_won` webhook, writes back an ERP external reference, and is refused every endpoint outside its scopes.

## Phase 7 — AI assistant

Requirements: FR-AI-01 to 08. Design: architecture section 8.

- `app/llm/client.py` built with the Cerebras skill (LiteLLM → OpenRouter → `openrouter/openai/gpt-oss-120b`, Cerebras provider).
- Assistant module: conversations, messages, tool registry, tool loop, SSE streaming, limits and budgets, token accounting.
- Read-only tools implemented on top of existing services.
- Chat drawer: streaming, record context, history, copy, "save as note", Markdown rendering without raw HTML.
- Tests use a fake LLM client; a small scripted evaluation set (English and Bulgarian questions with expected tool calls and facts) is runnable on demand against the live model.
- `AI_ENABLED` defaults to `false` until the owner confirms the data-flow question in requirements section 8.

## Phase 8 — Hardening and release

Requirements: FR-ADM-04, FR-AUTH-07 (if time allows), all NFRs.

- GDPR export and anonymization.
- Security pass against the OWASP ASVS Level 1 checklist; dependency audit clean; headers and cookie flags verified by tests.
- Accessibility pass (automated axe checks plus keyboard walkthrough).
- Backup service, restore drill executed and documented.
- Integration readiness: keys issued to the Conclusion, ERP and Billing teams in a staging environment, each team runs its flow end to end, and network rules for API and webhook traffic are in place.
- Operations guide (install, upgrade, backup, restore, create admin, configuration reference) and a short user guide in English and Bulgarian.
- User acceptance checklist handed to the owner; version tagged `v1.0.0`.

## Phase 9 — Assistant actions with confirmation (R1.1)

Requirements: FR-AI-09 (supersedes FR-AI-05); ADR 0030. Owner approval 2026-11-22: all main user actions, with the recommended exclusions.

| # | Task |
|---|---|
| 9.1 | ADR 0030; FR-AI-09; CLAUDE.md rule; API spec 17.1 (actions, endpoints, event, error code) |
| 9.2 | Additive migration: `assistant_action` (proposal, target, version, request, status, result, expiry) |
| 9.3 | Action registry (`assistant/actions.py`): argument schemas, permission pre-checks, the service call, bilingual card text; proposal tools offered by role |
| 9.4 | Confirm and cancel endpoints; conflicts and expiry; audit `details.via = "assistant"`; authorization matrix |
| 9.5 | Frontend: confirmation card (Confirm / Cancel, destructive style, result link, one-time link for a new user), en and bg, accessible |
| 9.6 | Tests per action (permission, payload, conflict), injection, expiry, Viewer; live evaluation cases |
| 9.7 | Manuals, user guides, ASVS, accessibility, Plan.md, Test_strategy.md, release notes |

Exit: "Create a task due tomorrow: Call Mr Z" produces a card; Confirm creates the task, which appears in My tasks and in the audit log with `via: assistant`; full gate and live evaluation pass.

## After R1 — roadmap (do not build yet)

| Release | Adds | Attaches to |
|---|---|---|
| R1.1 | Assistant-proposed actions with user confirmation (Phase 9, above); SSO via OpenID Connect; email notifications; write scopes for integrations once flows are agreed; OAuth 2.0 client credentials if required | `assistant`, `identity`, `integration` |
| R2 | Product catalog, product offering qualification, solution configuration, site surveys | new modules → `opportunity`, `organization` |
| R3 | Quotes, proposals, agreements and contracts | new modules → `opportunity`, `organization`, R2 catalog |
| R4 | Channel and partner management, sales portal, advanced reporting | new modules → `party`, `sales` |

Rule for all future releases: new modules, new tables, additive migrations, no rewrite of R1 modules.

## Risks

| Risk | Mitigation |
|---|---|
| LLM data flow not approved for on-prem context | Assistant is isolated, off by default and removable by one setting |
| Excel data is messier than the templates assume | Get sample files early (open question 2); validation preview and batch rollback |
| Scope creep into quoting and catalog | Out-of-scope list in requirements; extension points documented, not built |
| Schema shortcuts that block R2–R4 | Migration policy, anchors kept clean, ADR required for exceptions |
| Model tool-calling quality in Bulgarian | Evaluation set in both languages; narrow, well-described tools |
| Integration data flows for Conclusion, ERP and Billing not yet defined | Start read-only with write-back of own IDs; generic API so confirmed flows need configuration, not code; open question 7 tracked with each system's owner |
| Integrating teams adopt the API late or misuse it | Early staging access, integration guide with samples, idempotency, stable `v1` contract, per-client monitoring |
| Integration traffic slows the UI | Per-client rate limits, sync-mode page caps, indexes on `(updated_at, id)` |
