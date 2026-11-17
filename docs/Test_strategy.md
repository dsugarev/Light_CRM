# Test strategy and test record

This document records, phase by phase, **how** each phase was tested and **which test cases were actually performed**, with results. The rules every test follows (levels, naming, coverage floors, required suites) are in [`04-test-strategy.md`](04-test-strategy.md); this file is the evidence that they were applied.

- Section 1 summarises the test levels and tools as implemented.
- Section 2 maps requirements to the tests that cover them.
- Sections 3 onwards: one section per phase (strategy, test cases added, runs performed, manual checks, gaps).
- The appendix is the complete, generated inventory of test cases (`python3 scripts/test_inventory.py`).

Test names carry requirement IDs (`test_FR_AUTH_01_AC3_lockout_after_5_failures_for_15_minutes`, `"FR-AUTH-02 ..."`), so the inventory and this matrix can be traced to `01-requirements.md`.

## 1. Test levels as implemented

| Level | Where | Tool | Data / environment | Runs |
|---|---|---|---|---|
| Backend unit | `backend/tests/unit/` | pytest, pytest-asyncio | No database (pure logic: policy, passwords, config, logging, errors, worker, CLI) | Every commit (CI `backend` job) |
| Backend API | `backend/tests/api/` | pytest, httpx ASGI transport | Real PostgreSQL 18 (`crm_test`), app connects as the DML role `crm_app`; tables truncated before each test; frozen clock; recording mailer | Every commit |
| Authorization matrix | `backend/tests/api/test_authorization_matrix.py` | pytest | Every API route × anonymous/admin/sales_manager/sales_rep/viewer; expectations from the API spec | Every commit |
| Route catalog | `backend/tests/api/test_route_catalog.py` | pytest | Registered routes vs. `05-api-specification.md` (paths, access levels, pending list) | Every commit |
| Migrations | `backend/tests/migrations/` | pytest + Alembic | Each revision up/down/up, models vs. schema drift, role privileges | Every commit |
| Module boundaries | `backend/pyproject.toml` | import-linter (14 contracts) | Static | Every commit |
| Frontend unit/component | `frontend/src/**/*.test.ts(x)` | Vitest, Testing Library, MSW | jsdom; API mocked with MSW; fictional fixtures | Every commit (CI `frontend` job) |
| Contract | CI `contract` job | openapi-typescript | Backend OpenAPI export vs. committed `frontend/src/api/schema.d.ts` and `docs/api/openapi.json` | Every commit |
| i18n | `frontend/scripts/check-i18n.mjs`, ESLint `i18next/no-literal-string` | Node, ESLint | Key parity en/bg; no hard-coded UI text | Every commit |
| End-to-end | `frontend/e2e/` | Playwright (Chromium, Firefox) | Composed Docker stack over HTTPS; Admins created with `create-admin --password-stdin` | Every commit (CI `e2e` job) and locally on demand |
| Dependency audit | CI | pip-audit (hashed lock export), `pnpm audit --audit-level high` | Lockfiles | Every commit |

## 2. Requirement coverage (Phases 0–2)

| Requirement | Covered by (examples; see appendix for all) | Levels |
|---|---|---|
| FR-AUTH-01 AC1 sign-in, HttpOnly cookie | `test_FR_AUTH_01_AC1_sign_in_sets_secure_httponly_cookie`; Vitest "FR-AUTH-01 AC1 signs in and returns to the requested page"; E2E journey 1 (cookie flags) | API, component, E2E |
| FR-AUTH-01 AC2 generic error | `test_FR_AUTH_01_AC2_errors_do_not_reveal_whether_email_exists`; Vitest "AC2 shows a generic message" | API, component |
| FR-AUTH-01 AC3 lockout 5 × / 15 min, audited | `test_FR_AUTH_01_AC3_lockout_after_5_failures_for_15_minutes`; `test_FR_AUTH_01_admin_unlocks_an_account`; Vitest "AC3 shows when a locked account opens again"; E2E journey 1 step 3 | API, component, E2E |
| FR-AUTH-02 no self-registration, one-time expiring link | `test_FR_AUTH_02_new_user_sets_password_with_one_time_link`, `..._link_expires`, `..._link_is_emailed_when_smtp_is_configured`; Vitest set-password tests; E2E journey 1 | API, component, E2E |
| FR-AUTH-03 12+ chars, common list, Argon2id | `tests/unit/test_passwords.py`; `test_FR_AUTH_03_set_password_enforces_policy`; Vitest "FR-AUTH-03 checks the new password" | Unit, API, component |
| FR-AUTH-04 idle/absolute timeouts, sign-out, revocation on password change | `test_FR_AUTH_04_idle_timeout_8_hours`, `..._absolute_timeout_7_days`, `..._timeouts_are_configurable`, `..._sign_out_invalidates_the_session_on_the_server`, `..._password_change_revokes_other_sessions`, `..._list_and_revoke_own_sessions` | API, component |
| FR-AUTH-05 RBAC on the server (AC1 rep vs. other rep's record, AC2 viewer mutations) | Authorization matrix (all routes × roles); `tests/unit/test_policy.py` (`AC1`, `AC2`); Vitest "hides admin navigation from non-admins" | Unit, API, component |
| FR-AUTH-06 SSO-ready | `test_FR_AUTH_06_user_record_is_sso_ready`, `..._unknown_auth_provider_cannot_use_passwords` | API |
| FR-ADM-01 user management | `tests/api/test_users.py` (create, list/filter, update, deactivate/activate, reset link, unlock, revoke sessions, last-admin rules) ; Vitest admin tests; E2E journey 1 | API, component, E2E |
| FR-ADM-03 audit log, append-only | `test_FR_ADM_03_admin_browses_and_filters_the_audit_log`, `..._role_change_is_audited_with_before_and_after`, `..._application_role_cannot_change_audit_entries`, `test_audit_entries_never_contain_secrets`; Vitest audit tests; E2E journey 1 step 4 | API, component, E2E |
| FR-I18N-01 en/bg, per-user preference, browser default | `test_FR_I18N_01_language_preference_is_saved_on_the_profile`; Vitest locale and language tests; E2E smoke and journey 1 in Bulgarian | API, component, E2E |
| FR-I18N-02 no hard-coded strings, key parity | `pnpm check:i18n`; ESLint `i18next/no-literal-string` (probe verified) | Static |
| FR-I18N-03 UTC stored, Europe/Sofia displayed, locale formats | Vitest `lib/format.test.ts`; "AC3 ... in Sofia time" | Component |
| FR-PARTY-01 organizations, AC1 duplicate warning | `tests/api/test_organizations.py` (create, validation, EIK warning, `AC1` name across scripts, registration number, duplicate-check with similar names, rename into duplicate, update audit, archive/restore); `tests/unit/test_text.py`, `test_eik.py`; Vitest "AC1 warns about possible duplicates", "offers Create anyway"; E2E party journey (Latin name flagged against Cyrillic one) | Unit, API, component, E2E |
| FR-PARTY-02 contacts | `tests/api/test_contacts_reference_search.py` (create, ownership via organization, email duplicates, archive/restore, search); Vitest contact tests; E2E party journey | API, component, E2E |
| FR-PARTY-03 organization 360 | `test_FR_PARTY_03_detail_with_counts`; Vitest "shows details, counts, contacts and empty later-phase sections"; E2E party journey | API, component, E2E |
| FR-PARTY-04 search and filter | `test_FR_PARTY_04_search_by_name_number_and_across_scripts`, `..._filters_sorting_and_paging`, `..._global_search_across_types`; Vitest list, search tests; E2E header search by transliteration | API, component, E2E |
| FR-ADM-02 reference lists (industries) | `test_FR_ADM_02_*` (seeded en/bg, add/rename/deactivate/reorder/delete, in-use refused); Vitest reference admin | API, component |
| FR-I18N-04 Cyrillic search and import | `tests/unit/test_text.py` (transliteration, name key, search text); API search tests in both scripts; E2E party journey | Unit, API, E2E |
| FR-INT-05 sync mode (machinery; integration clients in Phase 6) | `tests/api/test_sync_mode.py` (envelope, order, archived rows, `AC2` no skips/repeats during changes, tampered and foreign cursors, page-size limits, safety lag, `(updated_at, id)` indexes) | API |
| FR-INT-03 scopes (policy only until Phase 6) | `test_FR_INT_03_*` in `tests/unit/test_policy.py` | Unit |
| FR-INT-10 OpenAPI document | `test_FR_INT_10_openapi_document_is_public_outside_production`, `..._requires_sign_in_in_production`, `test_FR_INT_10_export_openapi_writes_document` | Unit, API |
| NFR-04 security (secrets, CSRF, headers, DB roles) | `tests/unit/test_config.py`; CSRF tests in `test_auth.py`; `test_NFR_04_application_role_cannot_run_ddl`; E2E "security headers", "CSRF header" | Unit, API, migration, E2E |
| NFR-08 health, JSON logs, request IDs | `tests/api/test_health.py`; `tests/unit/test_logging.py`; `tests/unit/test_errors.py`; Vitest API status; E2E readiness through proxy | Unit, API, component, E2E |
| NFR-12 additive migrations | `tests/migrations/test_migrations.py` | Migration |

Not yet covered because not yet built: LEAD, OPP, ACT, REP, IMP, AI, INT (except policy scopes and the sync machinery), FR-ADM-04 GDPR, FR-AUTH-07 MFA (Phase 8).

## 3. Phase 0 — Foundation

### Strategy

Prove the skeleton is production-shaped and the gates work, before any business feature: every gate from architecture section 9 runs in CI; tests use a real PostgreSQL from the start; the route catalog ties the code to the API spec; module boundaries are enforced statically.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Settings refuse default secrets in production | 6 | `backend/tests/unit/test_config.py` |
| JSON logging with request ID | 4 | `backend/tests/unit/test_logging.py` |
| RFC 9457 problems, request ID echo, generic 500 | 9 | `backend/tests/unit/test_errors.py` |
| Worker loop, CLI `export-openapi` | 5 | `backend/tests/unit/test_worker.py`, `test_cli.py` |
| Health live/ready (ok, migrations behind, DB unreachable, status only), OpenAPI/docs exposure | 7 | `backend/tests/api/test_health.py` |
| Route catalog vs. API spec | 191 (parametrised) | `backend/tests/api/test_route_catalog.py` |
| Migrations up/down/drift, `pg_trgm`, DML role cannot run DDL | 4 | `backend/tests/migrations/test_migrations.py` |
| App shell, language, API status, locale detection | 11 | `frontend/src/app/app.test.tsx`, `frontend/src/lib/locale.test.ts` |
| Smoke over HTTPS in en/bg, security headers, readiness through proxy | 5 × 2 browsers | `frontend/e2e/smoke.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-17 | Developer Mac, scratch PostgreSQL 18.7 | ruff, mypy, import-linter, pytest, pip-audit | 197 passed, 93% coverage; clean |
| 2026-11-17 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n, pnpm audit, contract | 11 passed; clean (1 moderate dev-only advisory) |
| 2026-11-17 | Developer Mac, local Caddy + Uvicorn | Playwright Chromium | 5/5 passed |
| 2026-11-17 | Docker Desktop, `scripts/start-mac.sh` | Stack up, Playwright Chromium, manual backup, dev override | 5/5 passed; backup dump written; dev backend ready |
| 2026-11-17 | GitHub Actions, PR #1 run 44084724475 | All four jobs | Green; Playwright 10/10 (Chromium + Firefox) |

### Manual / exploratory checks

- import-linter: injected a `litellm` import in core, a router importing SQLAlchemy and a cross-module repository import; the three contracts reported BROKEN; probes removed.
- ESLint: a probe component with hard-coded text, a hard-coded `aria-label`, `dangerouslySetInnerHTML` and raw `fetch`; all four reported.
- `init-roles.sh` run twice against the same server (idempotent).

### Gaps

- Firefox cannot start on the developer Mac ("Could not find profile folder"); Firefox runs in CI only.

## 4. Phase 1 — Identity, access and audit

### Strategy

- **Security rules first, at the lowest level:** the permission policy (roles, ownership, integration scopes) and the password policy are unit-tested exhaustively.
- **Every endpoint through HTTP against PostgreSQL**, as the application role, with a frozen clock to test lockout windows and session timeouts deterministically, and a recording mailer to test the SMTP and no-SMTP paths.
- **Authorization matrix generated from the spec**, not from the code, so a weakened permission fails twice (matrix and route catalog). Verified by deliberately weakening `GET /users`.
- **Audit side effects asserted** for each mutating action (actor, action, before/after), plus a database-level test that the application role cannot UPDATE or DELETE audit rows, and a test that no secret appears in any entry.
- **Frontend:** component tests with MSW for every screen's main path and error mapping; one Playwright journey per language through the real stack (exit criterion of the phase).

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Policy: role matrix, anonymous 401, integration `not_for_integrations` / `scope_missing`, ownership, permissions | 46 | `backend/tests/unit/test_policy.py` |
| Password policy and Argon2id hashing | 7 | `backend/tests/unit/test_passwords.py` |
| Sign-in, lockout, sessions, timeouts, links, forgot password, CSRF, mixed credentials, rate limits | 27 | `backend/tests/api/test_auth.py` |
| User administration and last-admin rules | 16 | `backend/tests/api/test_users.py` |
| `/me`, sessions, system info, settings, audit log, append-only, no secrets | 14 | `backend/tests/api/test_me_settings_audit.py` |
| Route × role authorization matrix (26 routes × 5 callers) | 27 | `backend/tests/api/test_authorization_matrix.py` |
| `create-admin` CLI (link, stdin, errors), housekeeping, `every()` | 5 | `backend/tests/api/test_operations.py` |
| OpenAPI behind sign-in in production (replaces the Phase 0 "404 in production" case) | 1 | `backend/tests/api/test_health.py` |
| Sign-in, guards, language on profile, sign-out, 401 redirect | 15 | `frontend/src/app/app.test.tsx` |
| Users list/filter/create/link/deactivate/reset, audit list/detail, settings validation | 8 | `frontend/src/features/admin/admin.test.tsx` |
| Profile sessions and password change | 3 | `frontend/src/features/profile/profile.test.tsx` |
| Set/forgot password, rate-limit message, open-redirect guard | 11 | `frontend/src/features/auth/setPassword.test.tsx` |
| Sofia time, number and EUR formatting | 2 | `frontend/src/lib/format.test.ts` |
| Journey 1 (en, bg), CSRF rejection, anonymous 401 | 4 × 2 browsers | `frontend/e2e/identity.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-17 | Developer Mac, scratch PostgreSQL 18.7 | ruff, mypy, import-linter, pytest, pip-audit | 391 passed, 95.3% coverage (identity service 96%, policy 97%); clean |
| 2026-11-17 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n (207 keys), pnpm audit, contract | 43 passed; clean (same moderate dev-only advisory) |
| 2026-11-17 | Docker Desktop, rebuilt stack, Admins via `create-admin --password-stdin` | Playwright Chromium | First runs found 3 defects (below); after fixes 9/9 passed in three consecutive runs |
| 2026-11-17 | GitHub Actions, PR #2 run 44093849594 | All four jobs | Green; Playwright journey 1 passed on Chromium and Firefox |
| 2026-11-17 | GitHub Actions, `main` after merge, run 44094038484 | All four jobs | Green |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| API tests | Reading `updated_at` after commit failed in async code (value set by a DB trigger) | Services refresh the row after commit |
| API tests | Test helper dropped custom headers | Headers merged |
| E2E | "New user" link rendered with `role="button"` (wrong semantics for screen readers) | Real `<Link>` styled as a button |
| E2E | Test filled the list page's search box while navigating (partial label match) | Wait for the form heading; exact label matching |
| E2E | Set-password page called every failure "invalid link", hiding rate limiting | Page shows the actual error code; component test added |

### Manual / exploratory checks

- Authorization matrix weakened on purpose (`GET /users` as Signed-in): matrix and route catalog both failed; reverted.
- Migration 0002 applied, downgraded and re-applied by hand; seeded roles, the settings row and `crm_app` grants on `audit_log` (INSERT, SELECT only) inspected in psql.
- Request log checked: `/api/v1/auth/password/token/***` masks one-time tokens.
- Production-mode stack restarted with default rate limits for owner testing (login 10/min, password 5/15 min per IP).

### Gaps and deferred

- Integration principals are tested through the policy only; they join the HTTP matrix in Phase 6 with API keys.
- MFA (FR-AUTH-07) is deferred to Phase 8.
- Firefox still runs in CI only.
- Performance, accessibility (axe) and the OWASP ASVS checklist are scheduled for Phases 5 and 8 (test strategy section 5).

## 5. Phase 2 — Organizations and contacts

### Strategy

- **Normalisation as pure functions first:** transliteration, the duplicate name key and the EIK checksum are unit-tested with hand-computed vectors, independently of the database.
- **Behaviour through HTTP on PostgreSQL** for every endpoint: duplicates (both scripts, registration number, similar names, confirmation), ownership (organization owner, derived contact owner, owner change by Manager+ only), archive/restore and edits refused on archived records, audit before/after values, list filters, sorting and paging, search in Cyrillic and Latin.
- **Sync mode tested as a contract** for Phase 6 integrations: ordering, archived rows, a record changed and a record created while paging, tampered and foreign cursors, page-size limits, the safety lag, and the presence of `(updated_at, id)` indexes.
- **Authorization matrix** extended automatically by the 20 new routes (expectations from the spec); explicit owner-versus-non-owner API cases for organizations and contacts.
- **Frontend:** component tests for list URL state, aria-sort, live duplicate warning and the 409 "create anyway" flow, EIK warning toast, owner picker visibility, 360 page, ownership-based hiding of edit/archive, organization picker, reference administration and global search.
- **E2E:** one journey per language through the real stack plus an ownership check with a freshly created Sales Rep.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Transliteration, name key, search text, LIKE escaping | 17 | `backend/tests/unit/test_text.py` |
| EIK/UIC checksum (9 and 13 digits, second weights) | 9 | `backend/tests/unit/test_eik.py` |
| Organizations: create/validate, EIK warning, industries, 360 counts, duplicates (4 cases), update/audit, ownership (4 cases), archive/restore, search, filters/sort/paging, 400s | 19 | `backend/tests/api/test_organizations.py` |
| Contacts (7), reference lists (3), global search (1) | 12 | `backend/tests/api/test_contacts_reference_search.py` |
| Sync mode | 8 | `backend/tests/api/test_sync_mode.py` |
| Authorization matrix: 20 new routes | +20 | `backend/tests/api/test_authorization_matrix.py` |
| Route catalog: new routes and access levels | +40 | `backend/tests/api/test_route_catalog.py` |
| Production refuses default `APP_SECRET_KEY` | 1 | `backend/tests/unit/test_config.py` |
| Organization list, create (duplicates, validation, owner picker), 360, archive | 8 | `frontend/src/features/organizations/organizations.test.tsx` |
| Contacts, reference administration, global search | 7 | `frontend/src/features/contacts/contacts.test.tsx` |
| Organizations and contacts journey (en, bg), ownership | 3 × 2 browsers | `frontend/e2e/party.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-17 | Developer Mac, scratch PostgreSQL 18.7 | Migration 0003 up/down/up; seeded industries inspected | OK (14 industries, en/bg) |
| 2026-11-17 | Developer Mac | ruff, mypy, import-linter, pytest, pip-audit | 517 passed, 95.7% coverage (party service 93%, listing 98%, reference 98%); clean |
| 2026-11-17 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n (357 keys), pnpm audit, contract, OpenAPI snapshot | 59 passed; clean (same moderate dev-only advisory) |
| 2026-11-17 | Docker Desktop, `scripts/start-mac.sh` (also appended `APP_SECRET_KEY` to the existing `.env`) | Playwright Chromium, full suite | First run: 1 failure (test data collision, below); after the fix 12/12 in three consecutive runs |
| 2026-11-17 | GitHub Actions, PR #4 run 44102245986 | All four jobs | Green; Playwright journeys passed on Chromium and Firefox |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| Design review while writing tests | The transliterated name key did not match "Acme" with «Акме» (c vs к) | Phonetic alignment of Latin spellings in the duplicate key (ADR 0016) |
| import-linter | "Internals are private" contracts counted indirect chains (party → identity service → identity models) | Contracts check direct imports only (`allow_indirect_imports`) |
| mypy | SQLAlchemy 2.1 types `select(Model)` as `Select[Model]` | Annotations updated |
| Vitest | Changing sort or filters replaced the table with a loading indicator | Lists keep the previous rows while loading (`keepPreviousData`) |
| Vitest | Test fixtures: admin lacked permissions; Bulgarian test user had an English profile | Fixtures corrected |
| E2E | English and Bulgarian journeys generated the same company name in parallel; the app correctly flagged a duplicate | Unique token includes the language |

### Manual / exploratory checks

- Normalisation examples checked by hand: «Акме ЕООД», "ACME e.o.o.d.", "Acme EOOD" → `akme`; «Филипс»/"Philips" → `filips`; «София» → `sofia`.
- `scripts/start-mac.sh` on an existing installation added the missing `APP_SECRET_KEY` and the stack started in production mode.

### Gaps and deferred

- Organization archive is not yet blocked by open opportunities (added with opportunities in Phase 4).
- Organization `leads`, `opportunities`, `timeline` sub-resources and exports: Phases 3–5.
- Performance against the NFR-01 volumes (10,000 organizations): Phase 5 seed and measurement.
- Integration clients calling sync mode with API keys: Phase 6 (machinery tested now through users).

## Appendix — test case inventory

<!-- inventory:start -->
_Generated by `python3 scripts/test_inventory.py`; do not edit by hand._

### Backend (pytest: unit, API, authorization matrix, migrations) — 517 test cases

**`backend/tests/api/test_auth.py`** (27)

| Test | Requirement | Cases |
|---|---|---|
| Sign in sets secure httponly cookie | FR-AUTH-01 AC1 | 1 |
| Errors do not reveal whether email exists | FR-AUTH-01 AC2 | 1 |
| Lockout after 5 failures for 15 minutes | FR-AUTH-01 AC3 | 1 |
| Failures reset after a successful sign in | — | 1 |
| Inactive and service users cannot sign in | — | 1 |
| Unknown auth provider cannot use passwords | FR-AUTH-06 | 1 |
| User record is sso ready | FR-AUTH-06 | 1 |
| Sign out invalidates the session on the server | FR-AUTH-04 | 1 |
| Idle timeout 8 hours | FR-AUTH-04 | 1 |
| Absolute timeout 7 days | FR-AUTH-04 | 1 |
| Timeouts are configurable | FR-AUTH-04 | 1 |
| Deactivated user session stops working | — | 1 |
| Password change revokes other sessions | FR-AUTH-04 | 1 |
| Password change checks current password and policy | — | 1 |
| New user sets password with one time link | FR-AUTH-02 | 1 |
| Link expires | FR-AUTH-02 | 1 |
| Set password enforces policy | FR-AUTH-03 | 1 |
| Only token hashes are stored | — | 1 |
| Forgot password always 202 and silent without smtp | — | 1 |
| Forgot password emails a reset link when smtp is configured | — | 1 |
| Setting a password unlocks and ends all sessions | — | 1 |
| Csrf header is required on mutating requests | — | 1 |
| Csrf rejects foreign origin | — | 1 |
| Cookie and authorization header together are rejected | — | 1 |
| Bearer keys are not accepted before phase 6 | — | 1 |
| Login is rate limited per ip | — | 1 |
| Rate limit response has retry after | — | 1 |

**`backend/tests/api/test_authorization_matrix.py`** (47)

| Test | Requirement | Cases |
|---|---|---|
| Route role matrix | FR-AUTH-05 | 46 |
| Matrix covers every api route | — | 1 |

**`backend/tests/api/test_contacts_reference_search.py`** (12)

| Test | Requirement | Cases |
|---|---|---|
| Create contact linked to organization | FR-PARTY-02 | 1 |
| Contact without organization is owned by creator | FR-PARTY-02 | 1 |
| Contact validation | — | 1 |
| Contact cannot join an archived organization | — | 1 |
| Duplicate email needs confirmation | — | 1 |
| Contact ownership follows the organization | — | 1 |
| Archive restore and owner filter | FR-PARTY-02 | 1 |
| Contact search in both scripts | — | 1 |
| Industries are seeded in both languages | FR-ADM-02 | 1 |
| Admin manages a list | FR-ADM-02 | 1 |
| Value in use cannot be deleted | FR-ADM-02 | 1 |
| Global search across types | FR-PARTY-04 | 1 |

**`backend/tests/api/test_health.py`** (7)

| Test | Requirement | Cases |
|---|---|---|
| Live is ok without dependencies | NFR-08 | 1 |
| Ready is ok when database is at head | NFR-08 | 1 |
| Ready is 503 when migrations are behind | NFR-08 | 1 |
| Ready is 503 when database is unreachable | NFR-08 | 1 |
| Health reveals status only | NFR-08 | 1 |
| Openapi document is public outside production | FR-INT-10 | 1 |
| Openapi requires sign in in production | FR-INT-10 | 1 |

**`backend/tests/api/test_me_settings_audit.py`** (14)

| Test | Requirement | Cases |
|---|---|---|
| Me lists permissions for the ui | FR-AUTH-05 | 1 |
| Language preference is saved on the profile | FR-I18N-01 | 1 |
| Me rejects unknown fields and locales | — | 1 |
| List and revoke own sessions | FR-AUTH-04 | 1 |
| Revoking another users session is not found | — | 1 |
| System info for signed in users | — | 1 |
| Settings defaults and update | FR-AUTH-04 | 1 |
| Settings validation | — | 4 |
| Admin browses and filters the audit log | FR-ADM-03 | 1 |
| Audit entries never contain secrets | — | 1 |
| Application role cannot change audit entries | FR-ADM-03 | 1 |

**`backend/tests/api/test_operations.py`** (5)

| Test | Requirement | Cases |
|---|---|---|
| Create admin prints a one time link | — | 1 |
| Create admin with password from stdin | — | 1 |
| Create admin rejects weak password and duplicates | — | 1 |
| Housekeeping removes expired sessions | — | 1 |
| Every limits how often a job runs | — | 1 |

**`backend/tests/api/test_organizations.py`** (19)

| Test | Requirement | Cases |
|---|---|---|
| Create with all fields | FR-PARTY-01 | 1 |
| Validation | FR-PARTY-01 | 1 |
| Wrong eik checksum is a warning | FR-PARTY-01 | 1 |
| Inactive or unknown industry is rejected | — | 1 |
| Detail with counts | FR-PARTY-03 | 1 |
| Duplicate name across scripts is flagged | FR-PARTY-01 AC1 | 1 |
| Duplicate registration number is flagged | FR-PARTY-01 AC1 | 1 |
| Duplicate check endpoint includes similar names | FR-PARTY-01 AC1 | 1 |
| Renaming into a duplicate needs confirmation | — | 1 |
| Update is audited with before and after | FR-PARTY-01 | 1 |
| Rep cannot edit another reps organization | FR-AUTH-05 AC1 | 1 |
| Viewer cannot change organizations | FR-AUTH-05 AC2 | 1 |
| Manager edits any organization and changes owner | — | 1 |
| Rep cannot give an organization to someone else | — | 1 |
| Owner must be an active person | — | 1 |
| Archive and restore | FR-PARTY-01 | 1 |
| Search by name number and across scripts | FR-PARTY-04 | 1 |
| Filters sorting and paging | FR-PARTY-04 | 1 |
| Unknown sort or filter is 400 | — | 1 |

**`backend/tests/api/test_route_catalog.py`** (254)

| Test | Requirement | Cases |
|---|---|---|
| Catalog is parsed | — | 1 |
| Every route is in the catalog | — | 50 |
| Every api route declares the catalog access level | — | 48 |
| Every catalog entry is built or pending | — | 153 |
| Pending list only names catalog entries | — | 1 |
| No route is hidden from the openapi document | — | 1 |

**`backend/tests/api/test_sync_mode.py`** (8)

| Test | Requirement | Cases |
|---|---|---|
| Sync envelope order and archived rows | FR-INT-05 | 1 |
| No skips or repeats while data changes | FR-INT-05 AC2 | 1 |
| Updated since filters and contacts work too | FR-INT-05 | 1 |
| Cursors cannot be tampered with or reused elsewhere | — | 1 |
| Sync page size limits | — | 1 |
| Rows inside the safety lag are held back | — | 1 |
| Sync mode needs an index on updated at and id | — | 2 |

**`backend/tests/api/test_users.py`** (16)

| Test | Requirement | Cases |
|---|---|---|
| Admin creates user with one time link | FR-ADM-01 | 1 |
| Link is emailed when smtp is configured | FR-AUTH-02 | 1 |
| Duplicate email is rejected case insensitively | — | 1 |
| Create user validates fields | — | 1 |
| List filter and detail | — | 1 |
| Lookup lists active humans for every signed in user | — | 1 |
| Role change is audited with before and after | FR-ADM-03 | 1 |
| Update rejects taken email | — | 1 |
| Last admin cannot be demoted or deactivated | — | 1 |
| Admin cannot deactivate themselves | — | 1 |
| Deactivation ends sessions and keeps the user | FR-ADM-01 | 1 |
| Admin issues password reset link | — | 1 |
| Password reset for inactive user is refused | — | 1 |
| Admin unlocks an account | FR-AUTH-01 | 1 |
| Admin revokes all sessions of a user | — | 1 |
| Roles list permissions | — | 1 |

**`backend/tests/migrations/test_migrations.py`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Every migration upgrades and downgrades | NFR-12 | 1 |
| Models match migrations | NFR-12 | 1 |
| Pg trgm is installed | — | 1 |
| Application role cannot run ddl | NFR-04 | 1 |

**`backend/tests/unit/test_cli.py`** (3)

| Test | Requirement | Cases |
|---|---|---|
| Export openapi writes document | FR-INT-10 | 1 |
| Export openapi defaults to stdout | — | 1 |
| Command is required | — | 1 |

**`backend/tests/unit/test_config.py`** (7)

| Test | Requirement | Cases |
|---|---|---|
| Production refuses default database secret | NFR-04 | 1 |
| Production refuses default migration secret | NFR-04 | 1 |
| Production starts with real secrets | NFR-04 | 1 |
| Production refuses default secret key | NFR-04 | 1 |
| Development allows placeholder secrets | — | 1 |
| Settings are read from environment | — | 1 |
| Migration url falls back to database url | — | 1 |

**`backend/tests/unit/test_eik.py`** (9)

| Test | Requirement | Cases |
|---|---|---|
| Valid codes | — | 3 |
| Invalid codes | — | 5 |
| Second weights are used when the first sum gives 10 | — | 1 |

**`backend/tests/unit/test_errors.py`** (9)

| Test | Requirement | Cases |
|---|---|---|
| Validation errors are problem details with field codes | — | 1 |
| Malformed json is 400 | — | 1 |
| Unknown route is resource not found | — | 1 |
| Wrong method is method not allowed | — | 1 |
| App error carries detail errors extra and headers | — | 1 |
| Unhandled error is generic 500 with request id | NFR-08 | 1 |
| Client request id is echoed | — | 1 |
| Unsafe client request id is replaced | — | 1 |
| Request id is generated when absent | — | 1 |

**`backend/tests/unit/test_logging.py`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Log line is json with request id | NFR-08 | 1 |
| Log line without request context has no request id | NFR-08 | 1 |
| Exceptions are included | NFR-08 | 1 |
| Configure logging installs json handler | NFR-08 | 1 |

**`backend/tests/unit/test_passwords.py`** (7)

| Test | Requirement | Cases |
|---|---|---|
| Minimum length is 12 | FR-AUTH-03 | 1 |
| Common passwords are rejected case insensitively | FR-AUTH-03 | 1 |
| Overlong passwords are rejected | — | 1 |
| Acceptable passwords | FR-AUTH-03 | 2 |
| Stored only as argon2id hash | FR-AUTH-03 | 1 |
| Garbage hash never verifies | — | 1 |

**`backend/tests/unit/test_policy.py`** (46)

| Test | Requirement | Cases |
|---|---|---|
| Role matrix | FR-AUTH-05 | 24 |
| Public is open to everyone | — | 7 |
| Anonymous callers get 401 | FR-AUTH-05 | 6 |
| Integrations are denied routes without a scope | FR-INT-03 | 1 |
| Missing scope names the required scope | FR-INT-03 AC1 | 1 |
| Scope opens the route | FR-INT-03 | 1 |
| Any client may call me without a scope | — | 1 |
| Rep cannot edit another reps record | FR-AUTH-05 AC1 | 1 |
| Managers edit any record | — | 2 |
| Viewer edits nothing | FR-AUTH-05 AC2 | 1 |
| Permissions follow the role matrix | — | 1 |

**`backend/tests/unit/test_text.py`** (17)

| Test | Requirement | Cases |
|---|---|---|
| Bulgarian transliteration | FR-I18N-04 | 5 |
| Fold strips accents and case | — | 1 |
| Name key ignores script case punctuation and legal form | FR-PARTY-01 AC1 | 6 |
| Name key keeps names made only of a legal form | — | 1 |
| Different companies keep different keys | — | 1 |
| Search text holds original and folded forms | FR-I18N-04 | 1 |
| Search terms offer both forms | — | 1 |
| Like wildcards are escaped | — | 1 |

**`backend/tests/unit/test_worker.py`** (2)

| Test | Requirement | Cases |
|---|---|---|
| Failing job does not stop other jobs | — | 1 |
| Worker runs jobs until stopped | — | 1 |

### Frontend (Vitest + Testing Library + MSW) — 54 test cases

**`frontend/src/app/app.test.tsx`** (15)

| Test | Requirement | Cases |
|---|---|---|
| app shell and sign-in › FR-AUTH-01 sends anonymous visitors to sign-in and remembers where they were going | FR-AUTH-01 | 1 |
| app shell and sign-in › FR-AUTH-01 AC1 signs in and returns to the requested page | FR-AUTH-01 AC1 | 1 |
| app shell and sign-in › FR-AUTH-01 AC2 shows a generic message for wrong credentials | FR-AUTH-01 AC2 | 1 |
| app shell and sign-in › FR-AUTH-01 AC3 shows when a locked account opens again, in Sofia time | FR-AUTH-01 AC3 | 1 |
| app shell and sign-in › validates required fields before calling the API | — | 1 |
| app shell and sign-in › FR-I18N-01 shows the sign-in page in Bulgarian | FR-I18N-01 | 1 |
| app shell and sign-in › FR-I18N-01 switches language before sign-in and remembers it locally | FR-I18N-01 | 1 |
| app shell and sign-in › FR-I18N-01 saves the language on the profile when signed in | FR-I18N-01 | 1 |
| app shell and sign-in › FR-I18N-01 follows the language stored on the profile | FR-I18N-01 | 1 |
| app shell and sign-in › FR-AUTH-05 hides admin navigation from non-admins and keeps them out of admin pages | FR-AUTH-05 | 1 |
| app shell and sign-in › shows admin navigation to admins | — | 1 |
| app shell and sign-in › FR-AUTH-04 signs out and returns to sign-in | FR-AUTH-04 | 1 |
| app shell and sign-in › shows a translated not-found message for unknown pages | — | 1 |
| app shell and sign-in › NFR-08 shows the API as online or unavailable | NFR-08 | 1 |
| app shell and sign-in › NFR-08 shows the API as unavailable when the readiness check fails | NFR-08 | 1 |

**`frontend/src/lib/format.test.ts`** (2)

| Test | Requirement | Cases |
|---|---|---|
| FR-I18N-03 locale formatting in Europe/Sofia time › shows UTC timestamps in Sofia time | FR-I18N-03 | 1 |
| FR-I18N-03 locale formatting in Europe/Sofia time › formats numbers and EUR amounts per language | FR-I18N-03 | 1 |

**`frontend/src/lib/locale.test.ts`** (4)

| Test | Requirement | Cases |
|---|---|---|
| FR-I18N-01 locale detection › uses a stored choice first | FR-I18N-01 | 1 |
| FR-I18N-01 locale detection › follows the browser language when nothing is stored | FR-I18N-01 | 1 |
| FR-I18N-01 locale detection › ignores unsupported stored values | FR-I18N-01 | 1 |
| FR-I18N-01 locale detection › remembers the chosen language | FR-I18N-01 | 1 |

**`frontend/src/features/admin/admin.test.tsx`** (8)

| Test | Requirement | Cases |
|---|---|---|
| FR-ADM-01 user administration › lists users with translated roles and keeps filters in the URL | FR-ADM-01 | 1 |
| FR-ADM-01 user administration › FR-AUTH-02 creates a user and shows the one-time link to hand over | FR-ADM-01, FR-AUTH-02 | 1 |
| FR-ADM-01 user administration › validates the form and shows server field errors | FR-ADM-01 | 1 |
| FR-ADM-01 user administration › deactivates a user after confirmation and explains the last-admin rule | FR-ADM-01 | 1 |
| FR-ADM-01 user administration › creates a password reset link for a user | FR-ADM-01 | 1 |
| FR-ADM-03 audit log › shows translated actions and filters by action | FR-ADM-03 | 1 |
| FR-ADM-03 audit log › shows before and after values as text | FR-ADM-03 | 1 |
| FR-AUTH-04 settings › validates timeouts before saving | FR-AUTH-04 | 1 |

**`frontend/src/features/auth/setPassword.test.tsx`** (6)

| Test | Requirement | Cases |
|---|---|---|
| FR-AUTH-02 set password from a one-time link › checks the token from the URL fragment and sets the password | FR-AUTH-02 | 1 |
| FR-AUTH-02 set password from a one-time link › explains an invalid or used link | FR-AUTH-02 | 1 |
| FR-AUTH-02 set password from a one-time link › shows the policy error returned by the server | FR-AUTH-02 | 1 |
| forgot password › always confirms without revealing whether the account exists | — | 1 |
| safeNext | — | 1 |
| set password errors › reports rate limiting instead of calling the link invalid | — | 1 |

**`frontend/src/features/profile/profile.test.tsx`** (3)

| Test | Requirement | Cases |
|---|---|---|
| profile › FR-AUTH-04 lists sessions and signs out another one | FR-AUTH-04 | 1 |
| profile › FR-AUTH-03 checks the new password before calling the API | FR-AUTH-03 | 1 |
| profile › shows the server error for a wrong current password | — | 1 |

**`frontend/src/features/contacts/contacts.test.tsx`** (7)

| Test | Requirement | Cases |
|---|---|---|
| FR-PARTY-02 contacts › lists contacts with their organization | FR-PARTY-02 | 1 |
| FR-PARTY-02 contacts › creates a contact for the organization it was started from | FR-PARTY-02 | 1 |
| FR-PARTY-02 contacts › picks an organization by searching | FR-PARTY-02 | 1 |
| FR-PARTY-02 contacts › shows email duplicates after a 409 | FR-PARTY-02 | 1 |
| FR-PARTY-02 contacts › shows a contact with links and the ownership note | FR-PARTY-02 | 1 |
| FR-ADM-02 reference list administration › adds a value and explains why a used value cannot be deleted | FR-ADM-02 | 1 |
| FR-PARTY-04 global search › searches from the header and shows grouped results | FR-PARTY-04 | 1 |

**`frontend/src/features/organizations/organizations.test.tsx`** (9)

| Test | Requirement | Cases |
|---|---|---|
| FR-PARTY-04 organization list › shows organizations with translated industry and keeps sort and filters in the URL | FR-PARTY-04 | 1 |
| FR-PARTY-04 organization list › searches after typing pauses | FR-PARTY-04 | 1 |
| FR-PARTY-01 create organization › AC1 warns about possible duplicates before saving, with a link | FR-PARTY-01 | 1 |
| FR-PARTY-01 create organization › AC1 offers \"Create anyway\" after a 409 and resends with confirm_duplicate | FR-PARTY-01 | 1 |
| FR-PARTY-01 create organization › validates EIK, VAT, website and country on the client | FR-PARTY-01 | 1 |
| FR-PARTY-01 create organization › shows the owner picker only to users who may reassign | FR-PARTY-01 | 1 |
| FR-PARTY-03 organization 360 › shows details, counts, contacts and empty later-phase sections | FR-PARTY-03 | 1 |
| FR-PARTY-03 organization 360 › FR-AUTH-05 hides edit and archive from a rep who does not own it | FR-PARTY-03, FR-AUTH-05 | 1 |
| FR-PARTY-03 organization 360 › archives after confirmation | FR-PARTY-03 | 1 |

### End-to-end (Playwright, composed stack) — 24 test cases

**`frontend/e2e/identity.spec.ts`** (8)

| Test | Requirement | Cases |
|---|---|---|
| Journey 1 in en › FR-AUTH-02 admin creates a rep who sets a password, signs in and gets locked out (chromium) | FR-AUTH-02 | 1 |
| Journey 1 in bg › FR-AUTH-02 admin creates a rep who sets a password, signs in and gets locked out (chromium) | FR-AUTH-02 | 1 |
| NFR-04 mutating requests without the CSRF header are rejected (chromium) | NFR-04 | 1 |
| FR-AUTH-01 anonymous API calls get 401 (chromium) | FR-AUTH-01 | 1 |
| Journey 1 in en › FR-AUTH-02 admin creates a rep who sets a password, signs in and gets locked out (firefox) | FR-AUTH-02 | 1 |
| Journey 1 in bg › FR-AUTH-02 admin creates a rep who sets a password, signs in and gets locked out (firefox) | FR-AUTH-02 | 1 |
| NFR-04 mutating requests without the CSRF header are rejected (firefox) | NFR-04 | 1 |
| FR-AUTH-01 anonymous API calls get 401 (firefox) | FR-AUTH-01 | 1 |

**`frontend/e2e/party.spec.ts`** (6)

| Test | Requirement | Cases |
|---|---|---|
| Organizations and contacts in en › FR-PARTY-01..04 create, detect duplicate, add contact, search across scripts, archive (chromium) | FR-PARTY-01 | 1 |
| Organizations and contacts in bg › FR-PARTY-01..04 create, detect duplicate, add contact, search across scripts, archive (chromium) | FR-PARTY-01 | 1 |
| Ownership › FR-AUTH-05 AC1 a sales rep cannot edit an organization owned by someone else (chromium) | FR-AUTH-05 AC1 | 1 |
| Organizations and contacts in en › FR-PARTY-01..04 create, detect duplicate, add contact, search across scripts, archive (firefox) | FR-PARTY-01 | 1 |
| Organizations and contacts in bg › FR-PARTY-01..04 create, detect duplicate, add contact, search across scripts, archive (firefox) | FR-PARTY-01 | 1 |
| Ownership › FR-AUTH-05 AC1 a sales rep cannot edit an organization owned by someone else (firefox) | FR-AUTH-05 AC1 | 1 |

**`frontend/e2e/smoke.spec.ts`** (10)

| Test | Requirement | Cases |
|---|---|---|
| English browser › FR-I18N-01 sign-in placeholder loads over HTTPS (chromium) | FR-I18N-01 | 1 |
| Bulgarian browser › FR-I18N-01 sign-in placeholder follows the browser language (chromium) | FR-I18N-01 | 1 |
| Bulgarian browser › FR-I18N-01 language can be switched to English (chromium) | FR-I18N-01 | 1 |
| NFR-04 security headers are set by the proxy (chromium) | NFR-04 | 1 |
| NFR-08 API readiness is reachable through the proxy (chromium) | NFR-08 | 1 |
| English browser › FR-I18N-01 sign-in placeholder loads over HTTPS (firefox) | FR-I18N-01 | 1 |
| Bulgarian browser › FR-I18N-01 sign-in placeholder follows the browser language (firefox) | FR-I18N-01 | 1 |
| Bulgarian browser › FR-I18N-01 language can be switched to English (firefox) | FR-I18N-01 | 1 |
| NFR-04 security headers are set by the proxy (firefox) | NFR-04 | 1 |
| NFR-08 API readiness is reachable through the proxy (firefox) | NFR-08 | 1 |

<!-- inventory:end -->
