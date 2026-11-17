# 04 — Test Strategy

Status: Draft v0.1

The tests actually performed in each phase, with results, are recorded in [`Test_strategy.md`](Test_strategy.md).

## 1. Principles

- Tests are written **with** the code in the same change, not afterwards. For business rules (state machines, permissions, forecast math), write the test first.
- Every acceptance criterion in `01-requirements.md` maps to at least one automated test. Test names carry the requirement ID, for example `test_FR_LEAD_03_AC1_cannot_qualify_with_unknown_bant`.
- Prefer tests at the lowest level that gives real confidence; keep end-to-end tests few and valuable.
- Tests are deterministic: no live network, no real LLM, no dependence on the current date (inject a clock), no shared state between tests.
- A failing test is fixed or the code is fixed. Tests are never weakened, skipped or deleted to get a green build without owner agreement.

## 2. Test levels

| Level | Scope | Tools | Runs |
|---|---|---|---|
| Backend unit | Services and pure logic: lead state machine, BANT score, forecast calculation, permission rules, duplicate normalization, import validation | pytest | Every commit |
| Backend API | Each endpoint through HTTP against a real PostgreSQL: happy path, validation errors, 401/403/404/409, pagination, filtering, audit side effects | pytest, httpx, real PostgreSQL (never SQLite) | Every commit |
| Migration | Upgrade from empty to head; downgrade one step and re-upgrade; upgrade a database populated at the previous release tag without data loss | pytest, Alembic | Every commit touching migrations, and before release |
| Frontend unit/component | Forms and validation, tables with URL state, board interactions, permission-based rendering, assistant drawer states | Vitest, Testing Library, MSW | Every commit |
| Contract | Generated TypeScript types match the backend OpenAPI document | openapi-typescript diff check | Every commit |
| End-to-end | Critical journeys through the composed stack in a real browser | Playwright (Chromium and Firefox) | Every merge to main |
| Non-functional | Performance, security, accessibility checks (section 5) | seed script, pytest, axe, audits | Before release, and nightly where cheap |

## 3. Required cross-cutting suites

**Authorization matrix.** One parametrized test enumerates every registered API route and asserts the expected result for each role, for an anonymous caller, and for integration clients holding each single scope, no scopes and all scopes. Routes outside the scope table must return `403 permission.not_for_integrations` to every integration client. A new route without an entry in the matrix fails the suite. The expected results come from the access levels in `05-api-specification.md`, and a further check fails if a registered route is missing from that catalog or a catalog entry has no route. Object-level rules (owner versus non-owner) have explicit cases for leads, opportunities and activities.

**Audit.** Each mutating endpoint test asserts that an audit entry with correct actor, action and before/after values was written, and that the application database role cannot update or delete audit rows.

**Localization.** A check fails when a translation key exists in one language and not the other, or when a component contains hard-coded user-facing text. At least one end-to-end journey runs in Bulgarian, including Cyrillic input, search and export.

**Module boundaries.** import-linter contracts fail the build on a forbidden import, including any `litellm` import outside `app/llm/`.

## 4. End-to-end journeys (Playwright)

1. Admin creates a user; the user sets a password and signs in; lockout after repeated failures.
2. Rep captures a lead, completes BANT, qualifies it and converts it to an opportunity with a new organization and contact.
3. Rep moves an opportunity across the board, logs an activity, closes it as lost with a reason; a manager reopens it.
4. Rep attempts to edit another rep's opportunity and is refused; Viewer sees no edit controls.
5. Manager imports a leads file with invalid rows, reviews the preview, commits, then an Admin rolls the batch back.
6. Manager views the dashboard and exports a filtered opportunity list; figures match the seeded data.
7. User asks the assistant a pipeline question (fake LLM) and receives a streamed answer with record links; with the provider failing, the CRM still works.
8. Journey 2 repeated with the UI in Bulgarian.

## 5. Non-functional testing

- **Performance:** a seed script loads the NFR-01 volumes; a pytest check measures p95 for list, search and dashboard endpoints against the 500 ms target and inspects query counts to catch N+1 queries.
- **Security:** tests assert cookie flags, security headers, CSRF rejection, lockout, rate limits, upload type and size limits, and export formula-injection protection. `pip-audit` and `pnpm audit` run in CI. An OWASP ASVS Level 1 checklist is completed in Phase 8.
- **Accessibility:** axe checks run inside Playwright on every main page; a manual keyboard-only pass covers the board and the forms.
- **Backup and restore:** a restore drill into a fresh environment is performed and documented before go-live.

## 6. Testing the integration API

Integrations have no browser, so their journeys are API-level tests against the composed stack, using only an API key, exactly as Conclusion, ERP or Billing would.

- **Authentication:** valid, unknown, revoked and expired keys; key in query string refused; cookie plus bearer refused; IP allowlist; deactivated client; key rotation with two active keys; the key never appears in logs (asserted by capturing log output).
- **Scopes:** covered by the authorization matrix, plus owner rules for integration-created records (`owner.required`, default owner).
- **Sync mode:** records created, updated, archived and anonymized while a client pages through `updated_since` are neither skipped nor repeated; cursor tokens cannot be tampered with to read other data.
- **External references:** uniqueness, own-system-only writes, lookup by external ID, `has_external_reference` filters, events emitted.
- **Idempotency:** replay returns the same response with `Idempotent-Replayed`; different body with the same key fails; concurrent duplicates create one record.
- **Outbox and webhooks:** an event row is written in the same transaction as the change and none is written for a rolled-back change; deliveries are signed correctly (verified by the reference receiver script); retries follow the schedule with an injected clock; non-2xx, timeouts and redirects are treated as failures; suspension after 72 hours; redeliver; scope filtering of events; disallowed hosts and private-address resolution blocked.
- **Rate limits** per client return `429` with `Retry-After`.
- **Contract:** the OpenAPI document declares the bearer scheme and a scope on every integration-accessible operation; a test fails if any operation in the scope table lacks it.
- **Integration journeys (API end-to-end):**
  1. ERP flow: rep closes an opportunity as won in the UI → ERP test client receives `opportunity.closed_won` → reads the organization and contacts → writes its customer number → the reference shows on the organization page.
  2. Billing flow: nightly-style sync of won opportunities without a `billing` reference → writes a billing account ID → the next sync returns none.
  3. Conclusion client with its read-only profile is refused every write endpoint.
  4. Receiver down for a period → deliveries retry and succeed once it is back, with no events lost or duplicated by ID.

## 7. Testing the AI assistant

- **Unit and API tests use a fake LLM client** injected in place of `app/llm/client.py`. The fake returns scripted tool calls and answers, so the tool loop, streaming, limits, persistence and error handling are tested deterministically. CI never calls the real model.
- **Tool tests:** each tool is tested like an API endpoint, including that it returns only what the calling user may see and respects row limits.
- **Safety tests:** a record containing injected instructions ("ignore previous instructions and…") is returned by a tool, and the test asserts no data change is possible and no unexpected tool is available; the round limit, timeout and token budget each have a test.
- **Live evaluation set (manual, on demand):** about 20 questions in English and Bulgarian over seeded data, each with the expected tool calls and facts that must appear in the answer. Run before release and whenever the prompt, tools or model change; results are recorded in `docs/assistant-eval.md`.

## 8. Test data

- Factories (for example factory-boy) create entities with sensible defaults; tests state only what matters to them.
- Each API test runs in a transaction that is rolled back, or against a per-test schema.
- No production or real customer data in tests, fixtures or seeds. Seed data uses clearly fictional companies and people, in both Latin and Cyrillic.

## 9. Coverage and quality gates

- Backend: at least 85% line coverage on `service.py` and `permissions.py` files, 75% overall. Coverage is a floor, not a goal; missing acceptance-criteria tests fail review regardless of the percentage.
- Frontend: all forms, the board and permission-dependent rendering have component tests.
- Merge is blocked unless lint, type checks, all suites, the contract check, the i18n check and the dependency audit pass.

## 10. User acceptance

Before go-live the owner and two Commercial users walk through a checklist derived from the end-to-end journeys using a copy of real Excel data imported into a staging instance. In parallel, the Conclusion, ERP and Billing teams run their integration flows against the same staging instance with their own API keys. Sign-off of the user checklist and confirmation from each integrating team are the release criteria for `v1.0.0`.
