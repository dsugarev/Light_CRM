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

## 2. Requirement coverage (Phases 0–6)

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
| FR-LEAD-01 capture | `test_FR_LEAD_01_company_name_alone_is_enough`, `..._all_fields_bant_score_and_links`, validation and link checks; Vitest "saves with only a title and company name"; E2E leads journey | API, component, E2E |
| FR-LEAD-02 lifecycle (AC1 reason, AC2 read-only/reopen) | `tests/unit/test_lead_lifecycle.py` (full transition matrix); `test_FR_LEAD_02_*` (happy path, invalid transitions, disqualify with reason, read-only, reopen by managers); Vitest disqualify and reopen; E2E leads journey | Unit, API, component, E2E |
| FR-LEAD-03 BANT (AC1 qualify needs BANT, AC2 score) | `test_FR_LEAD_03_AC2_score` (7 vectors incl. the spec example 63), `test_FR_LEAD_03_AC1_cannot_qualify_with_unknown_bant`; Vitest live score and disabled Qualify; E2E score 63 | Unit, API, component, E2E |
| FR-LEAD-05 lead list | `test_FR_LEAD_05_filters_sort_and_search`; Vitest lead list with URL filters | API, component |
| FR-LEAD-06 assignment | `test_FR_LEAD_06_rep_takes_over_a_lead_but_cannot_give_it_away`, `..._manager_assigns_to_anyone_active`; Vitest "take over" | API, component |
| FR-OPP-01 create and edit opportunities | `test_FR_OPP_01_create_defaults_to_first_open_stage_and_its_probability`, `..._stage_contact_and_probability_override_on_create`, `..._links_are_validated`, `..._update_with_version_and_probability_reset`; Vitest create tests; E2E opportunities journey | API, component, E2E |
| FR-OPP-02 stages (AC1 in-use stage, AC2 history) | `test_FR_OPP_02_default_pipeline_is_seeded_in_both_languages`, `test_FR_OPP_02_AC1_stage_in_use_cannot_be_deleted_only_deactivated`, `test_FR_OPP_02_AC2_move_records_history_and_resets_probability`, `test_each_stage_type_keeps_one_active_stage`; Vitest move and stage admin; E2E | API, component, E2E |
| FR-OPP-03 board (AC1 totals, AC2 no drag without rights) | `test_FR_OPP_03_board_columns_totals_and_can_edit`; Vitest board tests (totals, move list, Won/Lost, `AC2`, Bulgarian); E2E mouse drag and move list | API, component, E2E |
| FR-OPP-04 list | `test_FR_OPP_04_list_filters_sort_and_search`; Vitest list with URL filters | API, component |
| FR-OPP-05 close won/lost, reopen | `test_FR_OPP_05_close_won_with_actual_close_date`, `..._lost_requires_a_loss_reason`, `..._closed_is_read_only_until_a_manager_reopens`; Vitest close and reopen; E2E lost from the board, Admin reopen, won | API, component, E2E |
| FR-OPP-06 stale flag and setting | `test_FR_OPP_06_stale_when_idle_or_past_expected_close`, `test_FR_OPP_06_logged_activity_clears_the_idle_flag`; settings validation tests; Vitest "FR-OPP-06 saves the stale-opportunity threshold" | API, component |
| FR-LEAD-04 conversion (AC1 links, AC2 all or nothing, AC3 lead history on the opportunity) | `test_FR_LEAD_04_AC1_convert_creates_and_links_everything`, `..._convert_with_existing_records`, `..._without_a_contact`, `test_FR_LEAD_04_AC2_nothing_is_created_when_a_step_fails`, `..._validation_and_state_rules`, `..._conversion_preview_suggests_matches`, `test_FR_LEAD_04_AC3_lead_activities_appear_on_the_opportunity_timeline`; Vitest conversion tests; E2E full journey | API, component, E2E |
| FR-ACT-01 log activities | `test_FR_ACT_01_log_a_call_against_an_opportunity`, `..._links_are_required_and_validated`, `..._update_with_version_and_ownership`, archive, filters, sync; Vitest "FR-ACT-01 logs a call"; E2E journey | API, component, E2E |
| FR-ACT-02 tasks and My tasks | `test_FR_ACT_02_task_needs_due_date_and_an_assignee`, `..._assignee_or_owner_completes_and_reopens`, `..._my_tasks_open_and_overdue_first`, `..._task_edit_rules`; Vitest task and My tasks tests; E2E journey | API, component, E2E |
| FR-REP-01 dashboard (AC1 forecast) | `test_FR_REP_01_AC1_forecast_matches_an_independent_calculation`, `test_FR_REP_01_pipeline_by_stage`, `..._lead_conversion_rate_and_groups`, `..._dashboard_in_one_call`, `test_report_parameters_are_validated`; Vitest dashboard (en, bg); E2E reports journey | API, component, E2E |
| FR-REP-02 exports | `tests/api/test_exports.py` (XLSX with filters and audit, CSV in Bulgarian with chosen columns, user's language, opportunities and activities, contacts and audit log, row cap, formula prefixes), `test_FR_REP_02_report_export_with_total_row`, `..._forecast_conversion_and_win_loss_exports`; Vitest export download and too-large message; E2E CSV download | API, component, E2E |
| FR-REP-03 win/loss | `test_FR_REP_03_win_loss_by_reason_owner_and_month`; Vitest win/loss page; E2E | API, component, E2E |
| FR-IMP-01 import (AC1 preview, AC2 all or nothing, AC3 duplicates, AC4 tag and rollback) | `tests/api/test_imports.py` (templates, CSV encoding/delimiter, mapping rules, file checks, `AC1_AC3` preview with reasons, `AC2` strict refusal and late failure, `AC2_AC3_AC4` commit with updates and rollback, `AC4` changed records kept, contacts, leads, opportunities, discard and expiry); `tests/unit/test_import_parsing.py`; Vitest import wizard; E2E import journey | Unit, API, component, E2E |
| NFR-01 performance at volume | `backend/scripts/perf_check.py` against the seeded stack (section 10); `test_NFR_01_seed_creates_fictional_volumes`, `test_NFR_01_seed_demo_is_refused_in_production` | Manual run, API, unit |
| FR-INT-01 integration clients (AC1 deactivation refuses, AC2 client is the actor) | `test_FR_INT_01_admin_registers_a_client_backed_by_a_service_user`, `_AC1_deactivated_client_is_refused`, `_AC2_client_is_the_actor_of_its_changes`, `_admin_updates_a_client`, `_cli_creates_the_initial_profiles_inactive`; Vitest integrations pages; E2E integrations journey | API, component, E2E |
| FR-INT-02 API keys (AC1 shown once, AC2 rotation and expiry, AC3 revocation) | `test_FR_INT_02_key_is_shown_once_and_only_its_hash_is_stored`, `_AC2_rotation_limit_expiry_and_revocation`, `_malformed_and_mixed_credentials`, `_ip_allowlist`, `_last_use_is_recorded`; Vitest key shown once, revoke, limit; E2E | API, component, E2E |
| FR-INT-03 scopes (AC1–AC4) | `test_FR_INT_03_AC1_AC2_scopes_and_refused_areas`, `_AC3_no_archive_assign_convert_or_owner_change`, `_AC4_created_records_need_a_human_owner`, `_search_is_limited_to_readable_types`, `_activities_patch_only_own`; `test_FR_INT_03_integration_scope_matrix` (every route, all scopes vs. none); policy unit tests; E2E scoped access | Unit, API, matrix, E2E |
| FR-INT-04 external references | `test_FR_INT_04_client_writes_its_own_system_and_finds_records`, `_reference_rules`; Vitest references on record pages; E2E | API, component, E2E |
| FR-INT-05 sync mode with a key | `test_FR_INT_05_sync_with_an_api_key` | API |
| FR-INT-06 idempotency | `test_FR_INT_06_idempotent_creation`, `_idempotency_edge_cases` | API |
| FR-INT-08 usage counters (webhook figures in 6b) | `test_FR_INT_08_usage_counters` | API |
| FR-INT-09 per-client rate limit | `test_FR_INT_09_rate_limit_per_client` | API |
| FR-INT-07 webhooks (AC1 outbox in the transaction, AC2 signed with event ID, AC3 retries for 72 h and redelivery, AC4 readable record types only, AC5 HTTPS and allowlisted hosts) | `tests/api/test_webhooks.py` (`AC1` rollback and mapped events, `AC2` signed delivery to the reference receiver with the current record, `AC3` backoff, failure after 72 h, suspension, redirects, `AC4` scope filtering, `AC5` allowlist at subscription and delivery, loopback refused after resolution, address rules, rotation with two signatures, ordering per record, inactive client); `tests/api/test_phase6_exit.py`; Vitest subscriptions; E2E webhook journey | Unit, API, component, E2E |
| FR-INT-08 failing deliveries and alert | `test_FR_INT_07_AC3_retries_with_backoff_then_fails_after_72_hours` (client figures), ping excluded; Vitest badge and banner | API, component |
| FR-INT-10 documentation | `test_FR_INT_10_integration_guide_python_sample_verifies_crm_signatures`, `test_FR_INT_10_reference_receiver_verifies_signatures`, `test_FR_INT_10_collection_requests_match_routes` | API, unit |
| FR-INT-12 admin screens (subscriptions, delivery log, test event, redeliver) | `test_FR_INT_12_*`; Vitest delivery log and detail; E2E webhook journey | API, component, E2E |
| NFR-13 first attempt within a poll | `test_NFR_13_worker_job_dispatches_and_attempts_on_each_poll` | API |
| Phase 6 exit | `test_phase_6_exit_erp_round_trip` | API |
| FR-ACT-03 timelines | `test_FR_ACT_03_opportunity_timeline_merges_activities_and_events`, `..._organization_timeline_includes_its_records`; Vitest timeline rendering and freshness; E2E journey (converted and stage-change entries) | API, component, E2E |
| FR-ADM-02 stages and loss reasons | `test_FR_ADM_02_admin_adds_renames_reorders_and_deletes_a_stage`, `test_FR_ADM_02_loss_reasons_are_seeded_and_protected_when_used` | API, component |
| Optimistic concurrency (architecture 4.1) | `test_stale_version_returns_409_with_the_current_lead`, `test_patch_needs_a_version`, `test_unchanged_patch_keeps_the_version`; Vitest "shows the latest version after a conflict" | API, component |
| FR-INT-10 OpenAPI document | `test_FR_INT_10_openapi_document_is_public_outside_production`, `..._requires_sign_in_in_production`, `test_FR_INT_10_export_openapi_writes_document` | Unit, API |
| NFR-04 security (secrets, CSRF, headers, DB roles) | `tests/unit/test_config.py`; CSRF tests in `test_auth.py`; `test_NFR_04_application_role_cannot_run_ddl`; E2E "security headers", "CSRF header" | Unit, API, migration, E2E |
| NFR-08 health, JSON logs, request IDs | `tests/api/test_health.py`; `tests/unit/test_logging.py`; `tests/unit/test_errors.py`; Vitest API status; E2E readiness through proxy | Unit, API, component, E2E |
| NFR-12 additive migrations | `tests/migrations/test_migrations.py` | Migration |

Not yet covered because not yet built: IMP, AI, INT (except policy scopes and the sync machinery), FR-ADM-04 GDPR, FR-AUTH-07 MFA (Phase 8).

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

## 6. Phase 3 — Leads

### Strategy

- **State machine and score as pure functions**, tested exhaustively: every action × every status against the spec's transition table, and score vectors including the spec's own example (63).
- **Every rule through HTTP on PostgreSQL**: capture with minimal and full data, links to existing records, BANT and score, each transition (allowed and refused), qualify with unknown BANT (field-level errors), disqualify reasons, read-only states, reopen by managers only, version conflicts (PATCH and actions) returning the current lead, `use_action_endpoint`, assignment rules (take over versus give away, inactive owner), viewer refusals, archive/restore, filters/sort/search, organisation leads and counts, lead lists seeded and protected when used.
- **Extension points** (ADR 0018) tested through behaviour: leads in global search, `open_leads` on the organisation 360.
- **Authorization matrix** grows automatically by 12 routes, including the new access wording "Contributor (rules in service)".
- **Frontend**: list URL filters, capture payload (decimal comma → dot), BANT live score, Qualify disabled, disqualify reason required, reopen visibility by role, conflict handling, take over, list administration switching.
- **E2E** in both languages with a freshly created Sales Rep (created with the test language), a second Rep for the ownership refusal, and the Admin reopening.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Transition matrix (5 actions × 5 statuses), terminal states, score vectors, unknown items | 34 | `backend/tests/unit/test_lead_lifecycle.py` |
| Leads API (capture, links, lifecycle, BANT, concurrency, PATCH rules, ownership, assignment, archive, lists, organisation leads, seeded lists) | 21 | `backend/tests/api/test_leads.py` |
| Authorization matrix: 12 new routes | +12 | `backend/tests/api/test_authorization_matrix.py` |
| Route catalog: new routes and access levels | +24 | `backend/tests/api/test_route_catalog.py` |
| Policy: new access level | +6 | `backend/tests/unit/test_policy.py` |
| Lead list, capture, BANT, Qualify, disqualify, reopen, conflict, take over, lists admin | 10 | `frontend/src/features/leads/leads.test.tsx` |
| Leads journey (en, bg) | 1 × 2 languages × 2 browsers | `frontend/e2e/leads.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-17 | Developer Mac, scratch PostgreSQL 18.7 | Migration 0004 up/down/up; seeded lists inspected | OK (7 sources, 9 reasons) |
| 2026-11-17 | Developer Mac | ruff, mypy, import-linter, pytest, pip-audit | 614 passed, 96% coverage (lead service 96%); clean |
| 2026-11-17 | Developer Mac (heavily loaded by other applications, load average 8–15) | ESLint, Prettier, tsc, Vitest, i18n (458 keys), pnpm audit, contract, OpenAPI snapshot | 69 passed with a 60 s per-test timeout for the local run (default 5 s exceeded under load); clean |
| 2026-11-17 | Docker Desktop, rebuilt stack | Playwright Chromium, full suite (14 tests) | Run 1: 5 timeouts in older tests at the 30 s limit under load; runs 2 and 3 (two workers): 14/14 |
| 2026-11-17 | GitHub Actions, PR #5 run 44116111752 | All four jobs | Green; Vitest with default timeouts; Playwright on Chromium and Firefox |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| API tests | Money serializer turned `estimated_value` into text inside the service, breaking audit formatting (500) | Serializer applies to JSON output only |
| Vitest | Organization 360 test lacked the new leads request; a check ran before the leads loaded | Mock added; test waits for the section |
| Vitest (under load) | `findBy` waits of 1 s caused flaky failures on a busy machine | Testing Library wait raised to 3 s for all tests |
| E2E | New users default to English, so the Bulgarian journey switched language after sign-in | Test users are created with the journey's language |
| E2E | "Qualify" also matched "Disqualify" | Exact button names |

### Gaps and deferred

- Lead conversion (FR-LEAD-04), conversion preview and lead timeline: Phase 4.
- Lead export: Phase 5.
- The local frontend and E2E runs were affected by machine load; CI is the reference run for timing.

## 7. Phase 4a — Pipelines, opportunities and the board

### Strategy

- **Every opportunity rule through HTTP on PostgreSQL**: defaults on create (first open stage, its probability, history entry, audit), link validation (organisation, contact of another organisation, closed stage), probability override and reset, version conflicts returning the current opportunity, `use_action_endpoint`, owner and Manager+ rules, move only between open stages, close won/lost with the loss-reason rule and Sofia business date, read-only closed opportunities, reopen by managers only, assignment, archive/restore.
- **Stage administration** with the two protective rules (`stage.in_use`, `stage.required`) and the seeded pipeline checked value by value in both languages.
- **Board totals** with mixed owners, a won and an archived opportunity, cards without an amount, the owner filter (`me`), the date window and a viewer (`can_edit` false everywhere).
- **Stale rule**: overdue close date, idle time (created_at moved back in the database because the test clock is frozen), the threshold setting lowered to 7 days, closed never stale; the `is_stale` filter and the response flag agree.
- **Extension points**: organisation counts and archive guard, opportunity search across scripts, loss-reasons list protected when used, sync mode on the new list.
- **Authorization matrix** grows by 19 routes automatically; the route catalog checks paths and access levels against spec v0.5.
- **Frontend**: list URL filters and stale badge, create (organisation required, payload with decimal comma and null probability), move with the version, lost needs a reason, closed read-only with reopen for Admin only, conflict handling, board totals and the move list, Lost opening the reason form while Won closes, `can_edit` false hides drag and list, Bulgarian stage names, stage admin errors, stale setting validation.
- **E2E** in both languages with a fresh Sales Rep: create from an organisation, board totals, a **real mouse drag** with dnd-kit, the move list, lost from the board with a reason, then the Admin reopens into Negotiation and closes as won.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Pipelines and stages (seed, add/rename/reorder/delete, in use, required types, validation) | 5 | `backend/tests/api/test_opportunities.py` |
| Opportunities (create, links, update, concurrency, action-only fields, ownership, move, close, reopen, assign, archive, list, stale, board, organisation figures and archive guard, search, loss reasons, sync) | 21 | `backend/tests/api/test_opportunities.py` |
| Settings: new field in defaults/audit, range validation | +2 (and 1 updated) | `backend/tests/api/test_me_settings_audit.py` |
| Authorization matrix: 19 new routes | +19 | `backend/tests/api/test_authorization_matrix.py` |
| Route catalog: new routes and access levels | +38 | `backend/tests/api/test_route_catalog.py` |
| Opportunity list, create, detail, board, stage admin | 12 | `frontend/src/features/opportunities/opportunities.test.tsx` |
| Stale setting; organisation 360 opportunities section | 1 new, 3 updated | `frontend/src/features/admin/admin.test.tsx`, `organizations/organizations.test.tsx` |
| Opportunities journey (en, bg) | 1 × 2 languages × 2 browsers | `frontend/e2e/opportunities.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-17 | Developer Mac, scratch PostgreSQL 18.7 | Migration 0005 up/down/up; `alembic check` | OK, no drift; 6 stages and 7 loss reasons seeded |
| 2026-11-17 | Developer Mac | ruff, mypy, import-linter, pytest, pip-audit | 699 passed, 96% coverage (opportunities 96%, pipelines 99%); clean |
| 2026-11-17 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n (594 keys), pnpm audit, OpenAPI snapshot and generated types | 82 passed with default timeouts; clean |
| 2026-11-17 | Docker Desktop, rebuilt stack | Playwright Chromium, full suite (16 tests, two workers) | 16/16 |
| 2026-11-17 | GitHub Actions, PR #6 run 44124492826 | All four jobs | Green; Playwright on Chromium and Firefox |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| mypy | Open-opportunity figures query lacked an explicit `FROM` for the join and could return `NULL` | `select_from(Opportunity)`; `NULL` total treated as 0 |
| API tests | Settings defaults changed by the new field (expected) | Defaults, audit and range tests extended |
| Vitest | Stage selects rendered before the pipeline loaded, so they were briefly empty | Move and reopen controls appear once the stages are known |
| Code review of the first E2E draft | A drag step was wrapped in a fallback that would have hidden a broken drag | Rewritten: the drag must succeed; the move list is tested as its own step |

### Gaps and deferred

- Activities, tasks, timelines and lead conversion (FR-ACT-01..03, FR-LEAD-04) and the full lead → won journey: done in Phase 4b (section 8).
- Opportunity export: Phase 5. Integration-client calls with scopes: Phase 6 (scopes already declared on the routes).
- Firefox runs in CI only (it cannot start on the developer Mac).

## 8. Phase 4b — Activities, timelines and lead conversion

### Strategy

- **Activities through HTTP on PostgreSQL**: logging with defaults (owner, time now), every link rule (required, unknown, archived), task-only fields, versioned edits with ownership and action-only fields, archive (gone from lists and timelines), list filters including dates and sync mode.
- **Tasks**: due date and assignee rules (a Viewer cannot be assigned), completion and reopening by the assignee or the owner but not by a stranger, assignee edits, `activity.not_a_task`, My tasks ordering (overdue first) and `include_done`.
- **Opportunity freshness**: an old call keeps an idle opportunity stale; a call today clears the flag in the response and in the `is_stale` filter.
- **Timelines**: exact order and content of an opportunity timeline across move, activity, reassignment and close-lost (stage names in both languages, owner names, loss reason); the organization timeline merges its contact, lead and opportunity, excludes another organization's activity, and pages; contact and lead timelines; 404 for unknown records.
- **Conversion**: new records, existing records, no contact; AC2 checked by counting rows after a failure in the last step and after a duplicate refusal, then success with `confirm_duplicate`; exactly-one validation, unknown organization, contact of another organization, ownership, stale version, unqualified and already-converted leads; the preview's matches across scripts and suggested values; AC3 through the opportunity timeline.
- **Authorization matrix** grows by 14 routes, including the two new access wordings; the policy unit test covers them.
- **Frontend**: timeline rendering of activities and events, logging a call (payload with the record link), task due-date validation, My tasks with the overdue badge and completion, Convert button and converted link on the lead, the conversion screen (match chosen by default, prefilled contact, payload) and the duplicate confirmation flow, and a regression test that a change reloads the timeline.
- **E2E**: the Phase 4 exit journey in English and Bulgarian with a fresh Sales Rep: capture → contacted → BANT 100 → qualify → convert (new organization and contact) → the lead's history on the opportunity timeline → a task in My tasks → move to Negotiation (on the timeline) → close as won.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Activities, tasks, freshness, timelines | 13 | `backend/tests/api/test_activities.py` |
| Lead conversion and preview | 7 | `backend/tests/api/test_conversion.py` |
| Authorization matrix: 14 new routes | +14 | `backend/tests/api/test_authorization_matrix.py` |
| Route catalog: new routes and access wordings | +28 | `backend/tests/api/test_route_catalog.py` |
| Policy: two new access levels | +12 | `backend/tests/unit/test_policy.py` |
| Timeline, activity form, task, My tasks, freshness | 5 | `frontend/src/features/activities/activities.test.tsx` |
| Convert button, converted link, conversion screen, duplicates | 4 | `frontend/src/features/leads/leads.test.tsx` |
| Lead → won journey (en, bg) | 1 × 2 languages × 2 browsers | `frontend/e2e/journey.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-17 | Developer Mac, scratch PostgreSQL 18.7 | Migration 0006 up/down/up; `alembic check` | OK, no drift |
| 2026-11-17 | Developer Mac | ruff, mypy, import-linter, pytest, pip-audit | 773 passed, 96% coverage (activity service 96%); clean |
| 2026-11-17 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n (679 keys), pnpm audit, OpenAPI snapshot and generated types | 91 passed; clean |
| 2026-11-17 | Docker Desktop, rebuilt stack | Playwright Chromium, full suite (18 tests, two workers) | First run: the new journey failed twice (see defects); after the fixes and a rebuild 18/18 in two consecutive runs |
| 2026-11-17 | GitHub Actions, PR #7 run 44130293284 | All four jobs | Green; Playwright on Chromium and Firefox |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| API tests | `Result.tuples()` is deprecated in SQLAlchemy 2.1 (warnings are errors in tests): 500 on activity and timeline reads | Rows unpacked directly |
| API tests | Conversion read the opportunity's ID after the commit had expired it (500, `MissingGreenlet`) | IDs captured before the commit |
| E2E journey | A stage change did not appear on the opportunity timeline until the 30 s cache expired | Every successful mutation marks timelines stale; Vitest regression test (verified to fail without the fix) |
| E2E journey (test defect) | BANT choices were made before the "contacted" response re-rendered the card, losing them | The journey waits for the new status first, as the leads journey does |

### Gaps and deferred

- Activity export and reports: Phase 5. Integration clients with `activities:*` scopes ("only activities the client created" for PATCH): Phase 6.
- GDPR anonymisation must also cover `timeline_event` (Phase 8, noted in ADR 0020).
- Firefox runs in CI only.

## 9. Phase 5a — Reports, dashboard and exports

### Strategy

- **Forecast against an independent calculation** (FR-REP-01 AC1): nine opportunities across months, owners, probability overrides, an archived one, a won one, one without an amount and two outside the six-month window; the test computes the expected monthly sums itself from its own table and compares every month, plus the owner filter.
- **Every report figure through HTTP on PostgreSQL**: pipeline per stage with a won deal excluded; lead conversion with leads driven through every status (including a real conversion), grouped by owner and source, and an empty period (`null` rate); win/loss by loss reason, owner-free month grouping and a period window, with a deal from the previous year excluded; the dashboard for `me`, an owner ID and a viewer (whose own task counts are zero); parameter validation.
- **Exports**: open each produced XLSX with openpyxl and each CSV with the csv module; check headers in both languages, typed numbers, the list filters (`q`, columns), the user's default language, formula neutralization (a hostile organization name), the BOM, the audit entry's details, the row cap (patched to 1, not audited), the audit-log export and report exports with total rows.
- **Authorization matrix** grows by 12 routes (exports and reports for every role, the audit-log export for Admins only).
- **Frontend**: dashboard KPIs, accessible chart tables and the owner filter in the URL (en, bg); win/loss table with groups, total and regrouping; export download with the list's filters and without paging; the too-large message.
- **E2E** in both languages with a fresh Sales Rep: the dashboard for "Mine", a real CSV download (file name, BOM, translated header, the rep's rows) and the win/loss total.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Exports (lists, audit log, cap, formula prefixes) | 7 | `backend/tests/api/test_exports.py` |
| Reports, dashboard, report exports, validation | 8 | `backend/tests/api/test_reports.py` |
| Authorization matrix: 12 new routes | +12 | `backend/tests/api/test_authorization_matrix.py` |
| Route catalog: new routes | +25 | `backend/tests/api/test_route_catalog.py` |
| Dashboard (en, bg), win/loss page, export download and error | 5 | `frontend/src/features/reports/reports.test.tsx` |
| Reports journey (en, bg) | 1 × 2 languages × 2 browsers | `frontend/e2e/reports.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-17 | Developer Mac, scratch PostgreSQL 18.7 | ruff, mypy, import-linter, pytest, pip-audit | 825 passed, 97% coverage; clean |
| 2026-11-17 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n (719 keys), pnpm audit, OpenAPI snapshot and generated types | 96 passed; clean |
| 2026-11-17 | Docker Desktop, rebuilt stack | Playwright Chromium, full suite (20 tests, two workers) | First run: the new journey's last assertion failed (test defect, see below); after the fix 20/20 in two consecutive runs |
| 2026-11-17 | GitHub Actions, PR #9 run 44159185613 (after ADR 0022) | All four jobs | Green; Playwright on Chromium and Firefox |
| 2026-11-17 | GitHub Actions, PR #9 run 44158425076 | All four jobs | Backend and contract green; frontend failed in `pnpm audit --audit-level high` on a newly published dev-only advisory (GHSA-fc5q-39xc-vjpf, no fix); E2E skipped. Owner decision: ignore this advisory only (ADR 0022) |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| API test (independent forecast) | Months were grouped with `date_trunc` on a date column, which returns a timestamp in the session time zone: every month's figures shifted to the previous month | Group by `to_char(date, 'YYYY-MM')` (ADR 0021) |
| API test (test defect) | Expected 2099.99 where the sum 2099.9989 correctly rounds to 2100.00 | Expectation corrected and explained in the test |
| API test (test defect) | Conversions in a loop created organizations with the same name (duplicate refusal) | The test confirms the duplicate |
| E2E (test defect) | Compared a table row's raw text, which has no spaces between cells | Asserts the row's accessible name |

### Gaps and deferred

- Import (FR-IMP-01), seed data and the NFR-01 performance check: Phase 5b.
- Very large exports (near 50,000 rows) are covered by the cap test and batching, not timed; the 5b seed provides the volumes for a timing run.

## 10. Phase 5b — Import, seed data and performance

### Strategy

- **Each acceptance criterion through HTTP on PostgreSQL**: AC1 with a mixed file (valid, wrong EIK, unknown industry, repeated row, invalid size band, duplicate across scripts) and the preview's exact field/code pairs and match; AC2 twice — strict refusal while rows are invalid, and a row that becomes invalid between validation and commit (a list value retired) so the whole commit writes nothing; AC3 with skip and update of a duplicate organization and contact duplicates by email; AC4 with batch tags in the database, Admin-only rollback that archives and reverts, and a record edited after the import kept as `changed_since_import`.
- **Per record type**: contacts linked by transliterated organization name, leads with source names, owner emails and decimal commas, opportunities with organization by spaced EIK, Bulgarian stage names, `DD.MM.YYYY` dates and the stage default probability; all records tagged.
- **Parsing as unit tests**: UTF-8 with BOM and quoted commas, Windows-1251 with semicolons, XLSX numbers/dates/repeated headers/blank rows, formulas not evaluated, unreadable files; mapping suggestions by key and both languages.
- **Limits and lifecycle**: 415/413 for bad, large and too-long files (limits patched small), states out of order, discard, the 7-day purge, mapping rule errors.
- **Seed**: the generator against the test database (volumes, board and lists work) and refusal in production.
- **Authorization matrix** grows by 10 routes (Manager+ and Admin-only rollback).
- **Frontend**: upload (multipart sent, batch opened), mapping payload and validation, preview with translated reasons, commit modes, discard, rollback visible only to Admins, nav hidden from Sales Reps, and the preview filter after commit (regression).
- **E2E** in both languages as the Admin: a semicolon CSV with a repeated row, the counts and reason, import skipping invalid rows (2 organizations found by API), rollback (0 found).
- **Performance** (NFR-01): seeded volumes and a timed run of 15 requests × 40 on the composed stack, plus timings of a 20,000-row export and a 5,000-row import.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Import API (templates, upload, mapping, files, AC1–AC4, record types, discard, expiry, seed) | 14 | `backend/tests/api/test_imports.py` |
| Parsing and mapping suggestions | 8 | `backend/tests/unit/test_import_parsing.py` |
| Seed refused in production | 1 | `backend/tests/unit/test_cli.py` |
| Authorization matrix: 10 new routes | +10 | `backend/tests/api/test_authorization_matrix.py` |
| Route catalog: new routes | +20 | `backend/tests/api/test_route_catalog.py` |
| Import wizard | 6 | `frontend/src/features/imports/imports.test.tsx` |
| Import journey (en, bg) | 1 × 2 languages × 2 browsers | `frontend/e2e/imports.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-17 | Developer Mac, scratch PostgreSQL 18.7 | Migration 0007 up/down/up; `alembic check` | OK, no drift |
| 2026-11-17 | Developer Mac | ruff, mypy, import-linter, pytest, pip-audit | 878 passed, 96% coverage; clean |
| 2026-11-17 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n (814 keys), `pnpm audit` (high, one approved ignore) and `--prod`, OpenAPI snapshot and generated types | 101 passed; clean |
| 2026-11-17 | Docker Desktop, rebuilt stack | Playwright Chromium, full suite (22 tests) | First run: the import journey failed (UX defect, see below); a second attempt was invalid because rebuilding only the proxy restarted the backend with default sign-in limits; after restarting the whole stack 22/22 in two consecutive runs |
| 2026-11-17 | Docker Desktop, composed stack with seeded NFR-01 volumes | `scripts/perf_check.py` (15 requests × 40, after warm-up) | All p95 under 500 ms (below) |
| 2026-11-17 | Same | Bulk timings | Export 20,000 leads: 2.3 s XLSX, 1.1 s CSV; import 5,000 organizations: upload 0.3 s, validation 2.4 s, commit 6.9 s |
| 2026-11-17 | GitHub Actions, PR #10 run 44164230647 | All four jobs | Green; Playwright on Chromium and Firefox |

NFR-01 measurement (milliseconds):

| Endpoint | p50 ms | p95 ms | max ms |
|---|---|---|---|
| `/api/v1/organizations` | 5 | 11 | 15 |
| `/api/v1/organizations?q=alfa%20mrezhi&sort=name` | 5 | 6 | 6 |
| `/api/v1/organizations?city=Варна&sort=-created_at&page=20` | 10 | 15 | 15 |
| `/api/v1/contacts?q=иванова` | 10 | 34 | 34 |
| `/api/v1/leads` | 21 | 23 | 24 |
| `/api/v1/leads?q=fibre&status=new&sort=-estimated_value` | 7 | 11 | 12 |
| `/api/v1/leads?page=400` | 55 | 64 | 83 |
| `/api/v1/opportunities` | 10 | 13 | 13 |
| `/api/v1/opportunities?q=cloud&stage_type=open&sort=amount` | 8 | 16 | 18 |
| `/api/v1/opportunities?is_stale=true` | 8 | 9 | 10 |
| `/api/v1/opportunities/board` | 34 | 92 | 108 |
| `/api/v1/activities` | 5 | 7 | 8 |
| `/api/v1/search?q=vega` | 15 | 17 | 18 |
| `/api/v1/search?q=Сириус` | 21 | 28 | 56 |
| `/api/v1/reports/dashboard` | 17 | 20 | 22 |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| E2E import journey | After commit and rollback the preview kept the "invalid rows" filter from the checking step and hid the imported rows and their rollback results | The preview remounts per batch status; Vitest regression test |
| API tests (test defects) | Test data used a wrong Bulgarian industry name; one expectation missed that "abc" is also an invalid amount | Test data and expectation corrected |
| Vitest (tooling) | jsdom `File` objects cannot be read back from a multipart body by MSW | The component test checks the multipart request is sent; the API and E2E tests cover the real upload |
| Performance check (tooling) | The compose file did not pass `RATE_LIMIT_USER_PER_MINUTE`, so 600 requests per minute would throttle the check | Variable passed through (default unchanged) |

### Gaps and deferred

- Imports through integration clients and asynchronous large imports are out of R1 scope.
- The performance figures come from one developer machine; the on-premises server should be measured again before go-live (Phase 8 hardening).

## 11. Phase 6a — Integration clients, API keys, scopes, external references, idempotency

### Strategy

- **Real keys through HTTP on PostgreSQL**: `TestApp.integration_client(scopes, …)` registers a client through the service, issues a key and returns an httpx client that sends only `Authorization: Bearer` (no cookies), so every integration test exercises the real authenticator, policy, middleware and services.
- **Authentication edges**: malformed, unknown, revoked and expired keys, a deactivated client, an address outside the allowlist, cookie plus key, a third active key, expiry in the past and beyond 24 months; the key never appears in responses after creation, in the audit log or in the database (only its hash).
- **Authorization matrix for integration callers**: for every route, a client holding **all** scopes and a client with **none** must get exactly the outcome the spec's access level and section 19.3 give, with path parameters filled for scope templates (`{resource}`, `{system}`). This is what found Public routes open to keys.
- **Scope rules inside services**: owner required on create (`owner.required`, default owner used), no owner change, archive, assign or convert, activities editable only by their creator, search narrowed to readable types, reference resolution needing the resolved type's scope, writing only the client's own system.
- **Idempotency**: replay with `Idempotent-Replayed` (status, body, `Location`, content type), a different body, a request still in progress, a `5xx` not stored, key length, keys per client, 24 h expiry via the worker purge.
- **Usage and rate limit**: hourly counters with errors over 24 h and after a clock jump; a client limited to 2/min gets `429` on the third call while another client is unaffected.
- **Migration 0008** in the up/down/up suite; model/schema drift check.
- **Frontend**: client list, new client sent inactive with chosen scopes, settings with the allowlist split into lines and server field errors, activation, key shown once with copy field, revoke after confirmation, two-key limit message, navigation only for Admins; references shown as links, hidden for non-Admins when empty, Admin add and remove.
- **E2E** in both languages: an Admin creates and activates a client, creates a key (shown once, gone after reload), adds an ERP ID with a link to a new organization; a separate cookie-less request context with the key resolves the ID, reads the organization, is refused leads (`permission.scope_missing`), and gets `401` after the key is revoked in the UI.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Integration API (clients, keys, scopes, references, sync, idempotency, usage, rate limit, CLI) | 22 | `backend/tests/api/test_integration.py` |
| Integration scope matrix (all scopes vs. none, every route) | +126 (one per route) | `backend/tests/api/test_authorization_matrix.py` |
| Authorization matrix and route catalog: 13 new routes and access levels | +13 matrix, +26 catalog | `backend/tests/api/test_authorization_matrix.py`, `test_route_catalog.py` |
| Policy: new access levels, scope alternatives, `has_scope`, `record_owner` | +24 | `backend/tests/unit/test_policy.py` |
| Integration screens and references | 12 | `frontend/src/features/integrations/integrations.test.tsx` |
| Integrations journey (en, bg) | 1 × 2 languages × 2 browsers | `frontend/e2e/integrations.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-17 | Developer Mac, scratch PostgreSQL 18.7 | Migration 0008 up/down/up; `alembic check` | OK, no drift |
| 2026-11-17 | Developer Mac | ruff, mypy, import-linter, pytest, pip-audit | 1089 passed, 96% coverage; clean |
| 2026-11-17 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n (891 keys), `pnpm audit` (high, one approved ignore) and `--prod`, OpenAPI snapshot and generated types | 114 passed; clean. `pnpm audit` also reports a moderate dev-only advisory (minimatch via typescript-eslint, GHSA-g3hv-75wg-m249), below the CI threshold |
| 2026-11-17 | Docker Desktop, rebuilt stack | Playwright, integrations journey (Chromium) | 2/2 (en, bg) on the first run |
| 2026-11-17 | Same | Playwright, full suite | Chromium 24/24. The unfiltered run reported 28 passed (the 24 Chromium tests and 4 Firefox tests) and the other Firefox tests failed with `browserType.launch` (an environment problem on this machine; an earlier version of this record wrongly said Chromium 28/28). Firefox is covered by CI |
| 2026-11-17 | GitHub Actions, PR #12 run 44172903654 | All four jobs | Green; Playwright on Chromium and Firefox |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| Integration scope matrix | Public routes (sign-in, password set and reset) accepted requests carrying an API key | The policy refuses integration principals on Public routes (`permission.not_for_integrations`) |
| Migration/model tests | `ExternalSystem` had no primary key mapping | Uses the shared id and timestamp mixins like the other reference lists |
| API tests | `PUT` on a reference raised `MissingGreenlet` after the session was expired following commit | The system ID is read before the commit |
| API tests | An idempotent replay of an error lost `application/problem+json` | The replay keeps `Content-Type` (and sets `Content-Length`) |
| Review while documenting | `POST /integration-clients` created clients active by default, against the "inactive until confirmed" decision | Default `is_active: false`; tests create active clients explicitly |
| API tests (test defects) | Field names are `scopes.0` / `ip_allowlist.0`; the admin's session expired after a 25-hour clock jump in the usage test | Expectations corrected; a fresh session after the jump |

### Gaps and deferred

- Webhooks, the delivery log, alerts and the exit test with a real receiver: Phase 6b.
- Firefox could not launch on the developer Mac during this phase's local E2E run (browser launch error, all Firefox tests); Firefox runs in CI.
- The C# and Java samples of the integration guide (6b) are not executed; only the Python sample is tested (owner decision).
- The moderate minimatch advisory (dev-only, below the CI threshold) is left until typescript-eslint updates it; no ignore entry is needed.

## 12. Phase 6b — Webhooks, delivery log, integration guide

### Strategy

- **Real deliveries over HTTP.** The reference receiver (`deploy/examples/webhook_receiver.py`) runs in a thread on 127.0.0.1 and verifies every signature with its own code; tests pass a `Network` that allows loopback, while the default policy is tested to refuse it after DNS resolution. Delivered payloads are compared with what `GET` returns. A fixed-status endpoint (500, 302) and a closed port cover failures.
- **Transactions.** Events published and rolled back leave no outbox row; committed ones do, with `changes` and `actor`. A won opportunity writes `organization.created`, `opportunity.created` and `opportunity.closed_won`; audit-only actions write nothing.
- **Time.** Retries are driven by passing explicit times to the worker functions: first retry after 54–66 s, nothing sent before it is due, `failed` after 72 hours, suspension of a subscription failing for 72 hours, and resumption lifting it. Receivers check signatures against the real clock, so successful deliveries use the real time.
- **Rules.** Scope filtering per client (AC4), event-type patterns, URL allowlist at subscription and at delivery (allowlist narrowed between), address classes (loopback, link-local, metadata, IPv4-mapped, multicast, unspecified; private allowed), rotation (both secrets for 24 h, then one), test events (sent for an inactive client, one attempt, not counted), per-record ordering, deliveries waiting while a client is inactive, redelivery deduplicated by the receiver, log filters and paging, purge after 30 days.
- **Exit test** (implementation plan): an ERP client with the 19.9 profile and only its API key receives the signed `opportunity.closed_won`, reads the organization, writes the ERP reference, finds it by filter, syncs with `updated_since`, and gets `403` on leads, activities, writes, users, audit, export, imports, integration admin, deliveries and reports.
- **Documentation checks.** The integration guide's Python sample is extracted and run against the CRM's signer; every Postman request must match a route in the OpenAPI document.
- **Authorization matrix** grows by 9 routes (Admin; closed to integration clients with all or no scopes).
- **Frontend**: subscribe with the secret shown once, URL rule error, list with 24-hour counts, rotate (new secret shown), test event leading to the delivery, resume a suspended subscription, delivery log filters in the URL, detail with attempts, redeliver, badge and banner.
- **E2E** in both languages against the composed stack with `WEBHOOK_ALLOWED_HOSTS=hooks.example.test`: the Admin creates a client and a subscription (secret shown once), sends a test event, and sees the **real worker's** attempt fail with "host name not found", then finds it in the delivery log.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Webhooks: outbox, mapping, subscriptions, fan-out, delivery, retries, suspension, rotation, test events, ordering, log, redeliver, purge, network guard, receiver, guide sample, worker job | 42 | `backend/tests/api/test_webhooks.py` |
| Phase 6 exit | 1 | `backend/tests/api/test_phase6_exit.py` |
| Postman collection matches the routes | 1 | `backend/tests/unit/test_integration_docs.py` |
| Settings: encryption key refused as placeholder, host list parsing | +2 | `backend/tests/unit/test_config.py` |
| Authorization matrix and integration scope matrix: 9 new routes | +18 | `backend/tests/api/test_authorization_matrix.py` |
| Route catalog: new routes | +18 | `backend/tests/api/test_route_catalog.py` |
| Webhook screens, delivery log, alert | +8 | `frontend/src/features/integrations/integrations.test.tsx` |
| Webhook journey (en, bg) | 1 × 2 languages × 2 browsers | `frontend/e2e/integrations.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-18 | Developer Mac, scratch PostgreSQL 18.7 | Migration 0009 up/down/up; `alembic check` | OK, no drift |
| 2026-11-18 | Developer Mac | ruff, mypy, import-linter, pytest, pip-audit | 1171 passed, 96% coverage; clean |
| 2026-11-18 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n (959 keys), `pnpm audit` (high) and `--prod`, OpenAPI snapshot and generated types | 122 passed; clean |
| 2026-11-18 | Docker Desktop, stack rebuilt with migration 0009, `APP_ENCRYPTION_KEY` and `WEBHOOK_ALLOWED_HOSTS` | Playwright Chromium, integrations spec, then full suite | 4/4, then 26/26 |
| 2026-11-18 | GitHub Actions, PR #13 run 44209396859 | All four jobs | Green; Playwright on Chromium and Firefox |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| Ordering test | Two events for one record at the same instant (same transaction) were both claimed: the tie-break compared delivery creation times, which are equal after one fan-out | Ties broken by the UUIDv7 event ID |
| Matrix (deprecation as error) | `Result.tuples()` is deprecated in SQLAlchemy 2.1 | Rows unpacked directly |
| Ruff auto-fix review | An unsafe fix turned a comprehension into `dict(result)`, which fails at runtime | Explicit comprehension over `.all()` |
| E2E design review | A failed test ping counted as a failing delivery, raising the admin alert for a deliberate check | Test events excluded from the failing figure (API test added) |
| Collection test (test defect) | FastAPI 0.163 nests included routers, so `app.routes` did not list API routes | The test reads paths from the OpenAPI document |
| Recount for this record | The Phase 6a record said Chromium 28/28; the unfiltered run counted 4 Firefox tests | Corrected to 24/24 in section 11, the 6a log and PR #12 |

### Gaps and deferred

- A slow receiver (10-second timeout) is not exercised end to end, to keep the suite fast; the timeout path is shared with connection errors in `send`.
- HTTPS delivery with certificate verification against the pinned address is covered by the design (httpcore keeps the URL host for TLS) but not by a test with a local certificate authority.
- `contact.anonymized` can be subscribed to but is only produced once GDPR anonymization exists (Phase 8).
- The C# and Java samples are not executed (owner decision).

## 13. Phase 7a — AI assistant backend

### Strategy

- **A scripted model, never the provider.** API tests replace `app.state.llm` with `ScriptedLLM`, which plays queued steps (text deltas, tool calls with usage, or an exception) one per model call and records the messages and tool definitions it was sent. Assertions look at both sides: the SSE events the browser receives and the prompt the model received (system instructions, history, the record in view, tool results).
- **Tools tested through the loop.** Each tool runs for real against PostgreSQL through the owning services; tests check what the model was given: only non-archived records, the caller's own records for `owner: "me"`, compact fields with in-app URLs, no contact email or phone, report figures matching the reports, the caller's own tasks. Invalid arguments, unknown tools and missing records come back as errors.
- **Safety** (test strategy 7): a record whose description holds injected instructions is read by a tool; the scripted model then asks for `delete_opportunity` and `update_opportunity`, which do not exist; the record's version and archive state stay unchanged and the audit log gains only the conversation. The set of tools is asserted to be exactly the eight read-only ones, each schema closed to unknown fields. The 5-round limit, the provider timeout, the daily budget (including the next Sofia day and per-user separation) and the message rate limit each have a test.
- **Privacy:** chat text never appears in log records captured during a message; audit entries for conversations carry no content; unexpected errors reach the browser as a code only; the API key never appears in the settings' representation; LiteLLM must not load `.env` files on import.
- **The real client offline.** A scripted OpenAI-compatible server (`app.llm.fake_server`, also used by the E2E stack) serves the real LiteLLM client a tool call, then a streamed answer, then a 503. LiteLLM's own `mock_response` drives the real streaming path to check routing (model, Cerebras only, no fallbacks, timeout, key); hand-built LiteLLM stream chunks check that tool-call fragments are assembled with usage; provider errors and a slow provider become `LLMUnavailableError` without details.
- **Authorization:** the matrix covers the 9 routes with the new level "Signed-in (own only)" (all people pass the route check; another user's conversation is `404`, tested separately for every own-only route) and `save-as-note` as Contributor; integration clients are refused all of them.
- **Live evaluation** (manual): `scripts/assistant_eval.py` with 20 cases in English and Bulgarian (`docs/assistant-eval.md`). Not part of CI.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Assistant API: switch, status, conversations, ownership, validation, streaming with tools and links, tools as the user, compact results, reports/tasks/activities tools, tool errors, round limit, record context, read-only and injection, language and history, history trimming, provider failure, unexpected failure, budget, rate limit, stop (stream and endpoint), save as note, viewers, logging, integration clients, no writes on read | 29 | `backend/tests/api/test_assistant.py` |
| LLM client: routing, streaming, tool-call assembly, errors, timeout, no `.env` loading, logging off, factory, settings checks, demo model, the real client with tools against the scripted provider server | 10 | `backend/tests/unit/test_llm_client.py` |
| Authorization matrix and integration scope matrix: 9 new routes | +18 | `backend/tests/api/test_authorization_matrix.py` |
| Route catalog: new routes | +18 | `backend/tests/api/test_route_catalog.py` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-18 | Developer Mac, PostgreSQL 18 | Migration 0010 up/down/up; `alembic check` | OK, no drift |
| 2026-11-18 | Developer Mac | ruff, mypy, import-linter, pytest, pip-audit | 1247 passed, 95.7% coverage (assistant service 95%, tools 89%, LLM client 85%); clean. After the MCP fix: 1248 passed, 95.6% |
| 2026-11-18 | Developer Mac | `assistant_eval.py --fake` (harness dry run against a disposable database) | Seeding, streaming and report work; demo answers not scored |
| 2026-11-18 | Developer Mac | `assistant_eval.py` against the live model | Not run: OpenRouter `402 Insufficient credits` |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| Real client against the scripted provider server | Every model call with tools failed: LiteLLM 1.108 imports its MCP gateway, which needs the optional `mcp` package (the first live smoke call had failed the same way) | `_skip_mcp_handler=True`; the test keeps running the real client with tools |
| Same test (warnings as errors) | A pydantic deprecation raised from LiteLLM's code ended the stream | Filtered in the test configuration for `litellm` modules only |
| Settings test | Importing LiteLLM loaded the repository's `.env` into the process (its default `DEV` mode), so an unset key looked set and `ENV` became `production` | `LITELLM_MODE=PRODUCTION` before the import (client and test configuration); guard test |
| Client test (warnings as errors) | A pydantic `ReadOnly` notice from LiteLLM's own types was raised inside the call and reported as a provider failure | Filtered in the test configuration (harmless at runtime) |
| import-linter | The assistant reached `litellm` through `app.llm.client` | Types split into `app.llm.types`; the client loaded on demand by `app.llm.factory`; the contract forbids direct imports |
| Budget test (test defect) | Moving the clock a day expired the test session | The test signs in again |
| Evaluation dry run | Emptying the database with `TRUNCATE … CASCADE` also removed the settings row and seeded lists | The script rebuilds the database through the migrations |

### Gaps and deferred

- The live model has not been evaluated yet (no OpenRouter credits).
- A browser disconnecting mid-answer is handled (the partial answer is kept as stopped) but not tested: the test client reads whole responses.
- The streamed response through Caddy is checked by the 7b Playwright journey.

## 14. Phase 7b — AI assistant chat drawer

### Strategy

- **The stream as the browser sees it.** Vitest tests serve `POST .../messages` from MSW in the Server-Sent Events format of API spec 17. A held stream sends the first events, waits, then sends the rest, so a test can check the answer in progress (tool progress, the Stop button) before it ends.
- **Untrusted Markdown.** An answer containing an external link, an `<img>` tag and raw HTML is rendered: only the in-app record link becomes a link, no image or raw element reaches the DOM, and tables and emphasis render.
- **Behaviour tests per requirement:**
  - the launcher is hidden while the assistant is off;
  - the drawer works in both languages;
  - record context is offered on an opportunity page and sent with the new conversation;
  - a follow-up in an existing conversation shows each message once while it streams;
  - history: open, rename, delete;
  - Stop posts the stop request;
  - provider failure and a used-up budget show translated errors;
  - Copy writes the draft to the clipboard;
  - "Save as note" posts the edited draft to the chosen record;
  - viewers get no "Save as note".
- **E2E (journey 7) in both languages** against the production-like stack plus `docker-compose.e2e.yml`. The real LiteLLM client calls the scripted provider server, streaming through Caddy. The journey:
  - asks a pipeline question and checks the table;
  - opens an opportunity, sees it offered as context, and gets a list with record links;
  - saves the answer as a note and finds it on the timeline;
  - sends `#fail` and sees the provider error;
  - opens the Leads list, which still works.
- **Backend:**
  - a stopped answer's tokens are estimated, and a failed call is not charged (assertions added to the stop and provider-failure tests);
  - the log formatter leaves out LiteLLM's record marker.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Assistant drawer: switch, Bulgarian, streaming with tool progress, Markdown and links, stop, provider failure, budget, follow-up without duplicates, record context, history, copy and save as note, viewers, SSE parsing | 12 | `frontend/src/features/assistant/assistant.test.tsx` |
| Assistant journey (en, bg) | 1 × 2 languages × 2 browsers | `frontend/e2e/assistant.spec.ts` |
| LiteLLM's log marker left out | +1 | `backend/tests/unit/test_logging.py` |
| Stopped answers estimated, failed calls not charged | assertions in 2 existing tests | `backend/tests/api/test_assistant.py` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-18 | GitHub Actions, PR #15 (7a) run 44241332019 | All four jobs | Green (an earlier run, 44240438088, was cancelled by the MCP fix push after three jobs passed) |
| 2026-11-18 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n (1,012 keys), build, `pnpm audit --prod` | 134 passed; clean |
| 2026-11-18 | Developer Mac | ruff, mypy, import-linter, pytest | 1249 passed, 95.6% coverage; clean |
| 2026-11-18 | Docker Desktop, stack rebuilt with `docker-compose.e2e.yml` and raised per-IP limits (as in CI) | Playwright Chromium, assistant spec, then full suite | 2/2, then 28/28 |
| 2026-11-18 | GitHub Actions, PR #16 run 44244163565 | All four jobs | Green; Playwright on Chromium and Firefox |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| Vitest (duplicate table) | During streaming the conversation also returns the stored question and unfinished answer, which were shown twice beside the live turn | Stored messages are cut at the question while a turn is live; regression test for a follow-up |
| E2E (usage rows) | An answer cut off by navigation recorded 0 tokens: the provider's usage arrives only at the end | Stopped answers are estimated; failed calls stay uncharged |
| E2E (Bulgarian navigation) | The assistant said „лийд“ while the application says „потенциален клиент“ | Bulgarian strings and the evaluation question aligned |
| E2E (logs) | LiteLLM's redaction filter stamped `litellm_redacted` on every JSON log line; the scripted server printed tracebacks for clients that stopped reading | Marker left out by the formatter; broken pipes ignored |
| E2E (test defect) | The pipeline figures assertion assumed an empty database; the local stack holds the demo volumes | The test checks the stage rows, not the totals |

### Gaps and deferred

- Firefox does not launch on the developer Mac; CI runs the journeys on Chromium and Firefox.
- The live model is still not evaluated (no OpenRouter credits).
- Screen-reader behaviour of the streaming log (`role="log"`, `aria-busy`) was not checked with an actual screen reader.

## 15. Phase 8a — GDPR tools, two-factor sign-in, security pass

### Strategy

- **Two-factor sign-in with real codes.** API tests compute TOTP codes with `pyotp` at the frozen test clock, so time decides validity. Covered:
  - the pending cookie's attributes;
  - no session before the code;
  - a code works once;
  - a recovery code works once;
  - wrong codes lock the account;
  - a forged or expired pending token is refused;
  - turning it off needs the password;
  - enforcement for Admins (only the allowed routes, other roles unaffected);
  - the CLI reset;
  - secrets encrypted and never in the audit log.

  The Playwright journey computes codes in Node (RFC 6238 with `node:crypto`), turns it on from the profile, then signs in again with a recovery code.
- **GDPR across modules.** One fixture gives a contact a footprint in every module:
  - a linked lead and a same-email lead;
  - an opportunity with the contact as primary contact;
  - a linked activity, and an activity that mentions the contact;
  - an ERP ID;
  - an assistant chat message.

  The export must list each item. Anonymization must clear the person fields and keep the commercial records. Search must no longer find the person. The audit entry and the outbox event must hold no old values. Re-anonymizing and editing must be refused, and after anonymization the export's structured sections must hold no personal data.
- **Security pass.** The ASVS L1 checklist was reviewed requirement by requirement. What the browser receives through Caddy is checked by Playwright:
  - security headers on the app and the API;
  - no `Server` header;
  - `Cache-Control: no-store` on the API;
  - the session cookie's flags;
  - no CSP violation on ten main pages.

  Backend tests cover anti-caching, CSRF and error bodies.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Two-factor sign-in: enrol, two-step sign-in, pending cookie, replay, recovery codes, lockout, disable, enforcement, CLI reset, flag, malformed codes | 13 | `backend/tests/api/test_mfa.py` |
| GDPR: export, anonymization, export after anonymization, Admin only | 4 | `backend/tests/api/test_gdpr.py` |
| Security: anti-caching, routes' own cache policy, CSRF, error bodies | 4 | `backend/tests/api/test_security_headers.py` |
| Concurrent duplicate user creation | 1 | `backend/tests/api/test_users.py` |
| Settings and system info expectations updated for the new setting and flag | (2 updated) | `backend/tests/api/test_me_settings_audit.py` |
| Authorization matrix and integration scope matrix: 6 new routes | +12 | `backend/tests/api/test_authorization_matrix.py` |
| Route catalog: new routes | +12 | `backend/tests/api/test_route_catalog.py` |
| Sign-in code step, profile setup and disable, forced setup, Admin setting | 6 | `frontend/src/features/profile/mfa.test.tsx` |
| GDPR panel: download, typed confirmation, other roles | 3 | `frontend/src/features/contacts/gdpr.test.tsx` |
| Privacy journeys (two-factor sign-in, anonymization) | 2 × 2 languages × 2 browsers | `frontend/e2e/privacy.spec.ts` |
| Security checks through Caddy | 2 × 2 browsers | `frontend/e2e/security.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-18 | Developer Mac, PostgreSQL 18 | Migration 0011 up/down/up; `alembic check` | OK, no drift |
| 2026-11-18 | Developer Mac | ruff, mypy, import-linter, pytest, pip-audit | 1295 passed, 95.5% coverage; clean |
| 2026-11-18 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n (1,064 keys), build, `pnpm audit` | 143 passed; clean |
| 2026-11-18 | Docker Desktop, stack rebuilt (migration 0011, new Caddyfile; proxy restarted) | Playwright Chromium: privacy and security specs, then the full suite | 4/6 then 6/6 after the fixes below; full suite 34/34 |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| Security journey (CSP violations) | The toast library injects its stylesheet inline; the CSP blocked it on every page, so toasts were unstyled behind Caddy since Phase 1 | The two style blocks allowed by hash; the journey fails if a library upgrade changes them |
| ASVS review (8.2.1) | API responses had no anti-caching header | `Cache-Control: no-store` on `/api` unless the route sets one; tests |
| Privacy journey (500) | Two users created with the same email at the same moment: the loser hit the unique index and got 500 | Mapped to `409 conflict.duplicate`; concurrent API test |
| Privacy journey (test defect) | The en and bg journeys generated the same email in the same millisecond | The language is part of the generated address |
| MFA enforcement test | The allowed-routes check compared route templates, which FastAPI 0.163 stores without the router prefix | Compares the request path (the allowed routes have no parameters) |
| Local stack | A changed Caddyfile is bind-mounted but not reloaded | Proxy restarted; noted for the operations guide |
| CI security journey on Firefox (run 44258388795) | Zod 4 probes `new Function` once per page; the CSP blocks it and Firefox reports a violation (Chromium does not) | `z.config({ jitless: true })` loaded first; Vitest check |

### Gaps and deferred

- ASVS open items (strength meter, show-password toggle, notices after credential changes, privacy notice) wait for the owner.
- Firefox does not launch on the developer Mac; CI runs both browsers.
- The CLI reset is tested through its service function, not by running the command.

## 16. Phase 8b — Accessibility, restore drill, readiness, guides

### Strategy

- **Accessibility, automated.** axe-core in Playwright runs the WCAG 2.0 and 2.1 A and AA rules on 23 main pages, the sign-in page, a record page and the assistant drawer. All violations are collected before the test fails, with the element and axe's explanation, so one run shows every problem.
- **Keyboard, automated.** The walkthroughs use only Tab, Enter, Escape and typing:
  - sign-in;
  - the skip link;
  - creating an organization;
  - moving an opportunity without dragging;
  - a dialog and the assistant drawer, both closing with Escape and returning focus.
- **Restore drill**, performed and timed: a fresh second stack, `scripts/restore.sh` with that morning's backup, row counts compared, then a sign-in and data read on the restored stack (operations guide 5.3).
- **Scripts tried end to end:** `staging.sh` (`init`, `up`, `seed`) and `restore.sh` (`--yes`). Both stacks were removed afterwards.
- **Documentation checked against the product:** UI labels taken from the translation files, requirement IDs checked against the requirements document, operator commands run as written.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| axe WCAG 2.1 A/AA: sign-in page; main pages, a record page and the assistant drawer | 2 × 2 browsers | `frontend/e2e/accessibility.spec.ts` |
| Keyboard walkthroughs | 3 × 2 browsers | `frontend/e2e/keyboard.spec.ts` |
| Privacy journey waits for sign-out before signing in again (test robustness) | (1 updated) | `frontend/e2e/privacy.spec.ts` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-18 | GitHub Actions, PR #17 (8a): run 44258388795, then 44259936104 after the Zod fix | All four jobs | First run: the Firefox security check failed on Zod's eval probe; second run green |
| 2026-11-18 | Docker Desktop, rebuilt stack with `docker-compose.e2e.yml` | Accessibility spec | First run: 3 rules failed (charts, destructive buttons); after the fixes: 2/2 |
| 2026-11-18 | Same | Keyboard spec | 3/3 |
| 2026-11-18 | Same | Full Chromium suite | First run 36/39 (privacy race, broken focus check, one journey timing); after the fixes 39/39 twice |
| 2026-11-18 | Docker Desktop, second stack `light-crm-drill` | Restore drill | 41 s; counts of 9 tables and the migration version identical; restored sign-in works |
| 2026-11-18 | Developer Mac | ESLint, Prettier, tsc, Vitest, i18n (1,065 keys), build, `pnpm audit` | 144 passed; clean |
| 2026-11-18 | OpenRouter | Live assistant evaluation | Not run: `402 Insufficient credits` |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| axe (`aria-hidden-focus`) | Dashboard charts hidden from assistive technology but focusable (Recharts 3 accessibility layer) | `accessibilityLayer={false}`; the figures are in screen-reader tables |
| axe (`color-contrast`) | Destructive buttons below 4.5:1 | Text 20 % darker in the light theme |
| Keyboard review (WCAG 2.4.1) | No way to skip the navigation | "Skip to main content" link; `main` focusable |
| Keyboard walkthrough | Closing the assistant drawer with Escape lost focus | Focus returns to the Assistant button |
| Restore drill | The backup service could not run after a branch switch (single-file bind mount points at the replaced file) | Upgrade procedure restarts `proxy` and `backup` |
| Operations review | No mount for IT's TLS certificate although `CRM_TLS=/certs/…` was documented | `CRM_CERTS_DIR` mounted read-only |
| Full suite (test defect) | A lint change made the keyboard focus check pass a string to `evaluate`, so it never matched | A typed function again |
| Full suite (test defect) | The privacy journey signed in again before sign-out finished | Waits for the sign-in URL |

### Gaps and deferred

- The manual accessibility checks (screen reader, 200 % zoom, dark-theme focus) are listed in `docs/accessibility.md` for a person to do.
- The restore drill was done on the developer Mac; repeat it on the production server.
- One run of the lead-to-won journey timed out waiting for a timeline entry under parallel load; it did not recur in two further full runs. Watch it in CI.
- The live assistant evaluation waits for OpenRouter credits; the teams' staging runs wait for open questions 7 and 8.

## 17. Live assistant evaluation (after Phase 8)

### Strategy
- The 20-case set of `docs/assistant-eval.md` runs against the real model through the real API and service path, on a disposable database with fictional data. It is run on demand only, never in CI.
- The case checks were reviewed after each run, so that failures blamed on the model really are the model's. Three checker problems (typography, language judged on record names, an injection case that could not tell quoting from obeying) were fixed in the checker, and the assistant was not tuned to them.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| The question's language decides the answer language and the tool results' language; detection with mixed scripts | 2 | `backend/tests/api/test_assistant.py` |
| Prompt assertions updated for the language rule | (1 updated) | same |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-18 10:15 | Developer Mac → OpenRouter (Cerebras) | Live evaluation, run 1 | 10/20 |
| 2026-11-18 10:20 | Same | Run 2, after the language and owner fixes | 18/20 (checker problems only) |
| 2026-11-18 10:22 | Same | Run 3, after the checker fixes | **20/20**; median 1.3 s per answer |
| 2026-11-18 | Developer Mac | ruff, mypy, import-linter, pytest | 1297 passed, 95.6% coverage; clean |
| 2026-11-18 | Docker Desktop, rebuilt stack with `docker-compose.e2e.yml` | Full Chromium suite with the contrast and keyboard fixes | First run: 9 sign-in timeouts right after the rebuild (backend busy); rerun 39/39 |
| 2026-11-18 | GitHub Actions, PR #19 run 44268290688 | All four jobs | Green; Playwright on Chromium and Firefox, including the accessibility and keyboard journeys |

### Defects found by testing and fixed

| Found by | Defect | Fix |
|---|---|---|
| Live run 1 | Bulgarian questions answered in English and vice versa (FR-AI-06): the model followed the interface language or the record names | The backend decides the language per question; tool results follow it; API tests |
| Live run 1 | "The open pipeline" answered for the user's own deals only | Prompt: "me" only when the user asks about their own records |
| Live runs 1–2 (checker defects) | Typographic hyphens and apostrophes; record names counted as language; the injection case could not tell quoting from obeying | Normalization; names ignored; the injection case requires the real figure |
| Live run 1 | Migration and LiteLLM INFO lines mixed into the report | Logs to stderr; LiteLLM below WARNING silenced |
| CI on `main` after #18 (merged while its end-to-end job was failing) | axe: the red "Locked" badge below 4.5:1 (local data had no locked user); Firefox keyboard journey: Tab does not wrap from the page end to the header | Light `--destructive` darkened to red 700 (buttons, badges, alerts); the axe check creates a locked user first; the keyboard journey reloads before tabbing to the header |

### Gaps and deferred
- One Bulgarian answer took 18 s (provider latency); the timeout is 60 s.
- The model is non-deterministic: rerun the set before release and after any prompt, tool or model change, and record each run.

## 18. Owner answers to the open questions

### Strategy
- Each answer that changes behaviour gets a test:
  - the sample import files go through the real import API in order, with the template headers matched automatically and every row valid;
  - the format document is checked against the import field definitions;
  - security notices: one per change, in the user's language, none without SMTP and none for a first password;
  - the CLI creates the profiles with every integration scope.
- The Phase 6 exit test keeps the original narrow ERP scopes, so it still proves that scopes are enforced now that the profiles hold every scope.

### Test cases added (summary)

| Area | Cases | Files |
|---|---|---|
| Sample import files: headers, format document, import of all four | 3 | `backend/tests/api/test_import_samples.py` |
| Security notices: language, reset and two-factor changes, none without SMTP or for a first password | 3 | `backend/tests/api/test_security_notices.py` |
| CLI profiles with every scope | (1 updated) | `backend/tests/api/test_integration.py` |
| Phase 6 exit with explicit narrow scopes | (1 updated) | `backend/tests/api/test_phase6_exit.py` |

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-18 | Developer Mac | pytest (full) | First run: 1 failure (the CLI profile test expected the old scopes; updated with the decision); then the affected suites pass |
| 2026-11-18 | Developer Mac | ruff, mypy, import-linter, pytest | 1303 passed, 95.6% coverage; clean |

### Defects found
| Found by | Defect | Fix |
|---|---|---|
| Review of the operations guide | The first backup-copy example used `rsync --delete-after`, which would delete the other machine's copies when the server prunes after 10 days | `--delete` removed and warned against |

## 19. UI polish after Release 1 (UX-01..14, FN-01..08)

### Strategy
- Every backlog item adds tests named after its ID (`UX-06 shows caps lock warning`) next to the change: component tests (Vitest, MSW), and Playwright where the item is about a journey or the real browser.
- **Guards instead of reviews:** for conventions that should stay true, a test scans the sources or the running app:
  - no color literals or palette classes (UX-01);
  - no `<h1>` outside `PageHeader`/`AuthCard` (UX-03);
  - no hand-written loading or empty text (UX-04);
  - no bare `Label` in features (UX-11);
  - lint rules against `window.confirm`/`alert`/`prompt` and direct toasts (UX-05).
- **Looking at it:** for every visible change, screenshots in English and Bulgarian at 1440 and 768 px were reviewed (not committed), with axe on each new state: drawer, menus, sheets, dialogs, error and empty states.
- **Layout and accessibility in the browser:**
  - `e2e/layout.spec.ts` (Bulgarian, 768 px: no sideways scrolling, no cut selects);
  - axe on every route (`accessibility.spec.ts`);
  - focus-indicator contrast measured in Chromium (`keyboard.spec.ts`).
- **Visual baselines (UX-14):** `e2e/visual.spec.ts` in its own project (`pnpm e2e:visual`). List responses are emptied and dates and figures masked, so the 152 screenshots are deterministic on a growing database. They are macOS baselines, so not run in CI (proposal C-10).
- **Each item's gate:** lint, prettier, typecheck, Vitest, i18n, Playwright Chromium (2 workers on this machine), the visual suite once it existed, and the backend gate (ruff, mypy, import-linter, pytest).

### Test cases added (summary)

| Item | Cases | Files |
|---|---|---|
| UX-01, UX-12 | 3 (+1 E2E focus contrast) | `src/app/designTokens.test.ts`, `e2e/keyboard.spec.ts` |
| UX-02 | 5 (+2 E2E) | `src/app/appShell.test.tsx`, `e2e/shell.spec.ts` |
| UX-03 | 4 | `src/components/PageHeader.test.tsx` |
| UX-04 | 7 | `src/components/states.test.tsx` |
| UX-05 | 5 | `src/lib/notify.test.tsx` |
| UX-06 | 7 | `src/features/auth/signInPage.test.tsx` |
| UX-07 | 10 | `src/features/auth/passwordRules.test.tsx` |
| UX-08 | 11 (+1 backend) | `src/features/admin/usersTable.test.tsx`, `backend/tests/api/test_users.py` |
| UX-09 | 4 | `src/features/admin/userSheets.test.tsx` |
| UX-10, FN-07 | 11 | `src/features/admin/auditViewer.test.tsx` |
| UX-11 | 8 | `src/components/formConventions.test.tsx` |
| UX-12 | 2 E2E (all remaining routes, signed-out pages) | `e2e/accessibility.spec.ts` |
| UX-13 | 5 (+1 E2E) | `src/lib/format.test.ts`, `e2e/layout.spec.ts` |
| UX-14 | 4 E2E (152 screenshots) | `e2e/visual.spec.ts` |
| FN-01, FN-02 | 4 + 7 | `src/features/profile/profile.test.tsx`, `src/lib/userAgent.test.ts` |
| FN-03 | 5 | `src/features/admin/userActions.test.tsx` |
| FN-04 | 4 (+1 E2E) | `src/features/auth/sessionExpiry.test.tsx`, `e2e/session.spec.ts` |
| FN-06 | 1 | `src/app/app.test.tsx` |
| FN-08 | 4 | `src/features/admin/lastAdmin.test.tsx` |
| FN-05 | 6 (+1 backend, +1 E2E with two tabs) | `src/features/auth/idleWarning.test.tsx`, `backend/tests/api/test_me_settings_audit.py`, `e2e/idle.spec.ts` |
| Assistant note form fix | 1 | `src/features/assistant/assistant.test.tsx` |

Tests updated for changed behaviour, never weakened:
- sign-out and language through the account menu (UX-02);
- menu clicks scoped to the main navigation because breadcrumbs repeat names (UX-03);
- confirmation before signing out a session or unlocking (UX-05, FN-03);
- the identity journey fills the new-user sheet and presses Done (UX-09);
- the keyboard board walkthrough runs as a fresh rep, because the admin's board outgrew 200 tab stops (UX-12);
- session fixtures use realistic user-agent strings (FN-02).

### Runs performed

| Date | Where | What | Result |
|---|---|---|---|
| 2026-11-18 | Developer Mac (8 GB) | Full gate per item, 21 items | Final: Vitest 251/251, Playwright Chromium 46/46, visual 4/4 twice in a row, pytest 1304 passed (95.5%) |
| 2026-11-18 | Developer Mac under memory pressure (swap 9–13 GB) | Playwright, UX-03..06 | Timeouts that moved between specs (backend requests of 3–42 s); UX-05 and UX-06 were parked until the host was freed, then passed 41/41 unchanged |
| 2026-11-18 | Developer Mac, Spotlight or Teams busy | Playwright, default workers | Load 16–78 caused timeouts; runs use 2 workers since |

### Defects found
| Found by | Defect | Fix |
|---|---|---|
| Intermittent assistant E2E (C-08) | The reload after an answer remounted the message and dropped an opened "save as note" form | Live and stored messages in one keyed list; regression test |
| UX-13 sweep | Stages and lists put `display: flex` on `<td>`; actions drew above the row | Inner wrapping container |
| UX-10 screenshots | A missing field and `null` were shown as a change | Treated as equal |
| UX-12 measurement | Focus ring about 1.5:1 on links | Token darkened to 3:1 or more |
| UX-05 test | A toast raised after a language switch used the old language | Errors translated when shown |
| UX-14 second run | Win/loss totals were not masked | Masked; verified after a full E2E run |

## 20. CRM UI improvements loop

Per-iteration detail is in `docs/loop_result.md`. Same strategy as section 19: tests with each change, the full gate, screenshots where visible.

| Iteration | Cases | Files |
|---|---|---|
| 1 Page titles, contact links | 13 (+1 E2E) | `src/components/pageTitlesAndLinks.test.tsx`, `e2e/shell.spec.ts` |
| 2 Recently viewed | 7 | `src/features/recent/recentlyViewed.test.tsx` |
| 3 Empty lists with a next step | 4 (2 updated) | `src/components/listEmptyState.test.tsx` |

| Date | What | Result |
|---|---|---|
| 2026-11-22 | Iteration 3 gate | Vitest 281/281; Playwright 48/48; visual 4/4 twice (16 list baselines updated); pytest first run 1 failure (housekeeping test vs real clock, fixed), then 1305 passed |
| 2026-11-22 | End-to-end on `6d42f62` | Chromium 47/48 with CI's sign-in limits (1 known sign-in timing flake in `party.spec.ts`, then 9/9 alone); axe, layout and keyboard specs passed; visual 4/4 with no baseline change. First attempt hit the local production rate limit (30 failures, not a defect). Firefox did not launch in the session sandbox |
| 2026-11-22 | End-to-end after the page-transition fix | Defect: the page fade let axe measure muted text at 4.35:1 mid-animation (`shell.spec.ts`, ~1 in 3); fixed with a movement-only transition. `expectSignedIn` waits 15 s. Full Chromium suite 48/48 (two workers), affected specs 18/18, visual 4/4, Vitest 312/312. Two runs under a load average of ~24 timed out (not counted) |
| 2026-11-18 | Iteration 2 gate | Vitest 277/277; Playwright 48/48; visual 4/4 twice (two home baselines updated); pytest 1305 passed |
| 2026-11-18 | Iteration 1 gate | Vitest 270/270; Playwright 45/48 under load (3 timeouts in untouched specs, which passed alone 10/10); visual 4/4; pytest 1305 passed |

Defects found by the loop: `SearchInput` kept its text after the URL search was cleared (fixed, iteration 3); the housekeeping test placed a "still valid" session relative to the fixed test date while the worker uses the real clock, so it failed from 2026-11-20 (fixed).

## 21. CRM UI loop 2 (colour, responsive layout, motion)

Per-iteration detail is in `docs/loop_result.md` ("Loop 2"). Strategy: as section 20, plus measured contrast for every colour token a status uses (computed from `index.css` in a unit test, so a token change cannot silently drop below 4.5:1).

| Iteration | Cases | Files |
|---|---|---|
| 1 Semantic status colours | 8 | `src/app/statusColors.test.tsx` |
| 2 Touch tablets, narrow screens | 15 | `src/components/responsive.test.tsx` |
| 3 Interface dynamics | 6 | `src/components/motion.test.tsx` |

| Date | What | Result |
|---|---|---|
| 2026-11-22 | Iteration 1 gate | Lint, typecheck, Vitest 291/291, i18n 1208 keys. Playwright and visual not run: no E2E admin credentials available in the session (see `docs/loop_result.md`) |
| 2026-11-22 | Iteration 2 gate | Lint, typecheck, Vitest 306/306, i18n 1208 keys, production build. Chromium measurement on the sign-in page (no account needed): 32 px controls with a mouse, 44 px with touch emulation at 768 and 360 px, no horizontal overflow. Playwright journeys and visual not run (no credentials) |
| 2026-11-22 | Iteration 3 gate | Lint, typecheck, Vitest 312/312, i18n 1208 keys, production build. Chromium: transitions 0.15 s normally, ~0 with reduced motion. Playwright journeys, axe and visual not run (no credentials) |

Defects found: the page fade-in lowered text contrast while it ran, caught by axe in `shell.spec.ts` (fixed: movement-only transition); the "Show password" button stayed 40 px next to a 44 px field on touch (found in the touch screenshot, fixed in iteration 2); the old success green measured 2.5:1 on white, below the text threshold, which is why it was darkened before using it for badge text.

## 22. CRM UI loop 3 (warm colours, interactivity)

Per-iteration detail is in `docs/loop_result.md` ("Loop 3"). Strategy: as section 21. Every theme token the interface draws text, focus or chart marks with is measured in a unit test. A palette change therefore cannot silently drop below 4.5:1 (text) or 3:1 (focus ring, chart marks). The warm look is pinned by token checks: neutrals tinted warm, a terracotta brand, warning away from the brand hue.

| Iteration | Cases | Files |
|---|---|---|
| 1 Warm colour scheme | 32 + 4 | `src/app/warmTheme.test.ts`, `src/app/warmShell.test.tsx` (helper `src/test/themeContrast.ts`) |

| Date | What | Result |
|---|---|---|
| 2026-11-22 | Iteration 1 gate | Lint, typecheck, Vitest 348/348, i18n 1208 keys |
| 2026-11-22 | Iteration 1 Chromium E2E (E2E stack, CI's sign-in limits) | First full run 47/48: UX-13 layout failed (see defects). After the fix: layout, accessibility, shell and keyboard 12/12. Firefox can't start in the sandbox; CI runs it |
| 2026-11-22 | Iteration 1 visual (UX-14) | All baselines changed, as intended. Updated with `--update-snapshots`; rerun 4/4 |

Defects found: uppercase, letter-spaced table headers with wider padding made four Bulgarian tables scroll sideways at 768 px by 11–37 px (leads, win/loss, deliveries, stages). Fixed by removing the uppercase and keeping `px-2`.

## Appendix — test case inventory

<!-- inventory:start -->
_Generated by `python3 scripts/test_inventory.py`; do not edit by hand._

### Backend (pytest: unit, API, authorization matrix, migrations) — 1305 test cases

**`backend/tests/api/test_activities.py`** (13)

| Test | Requirement | Cases |
|---|---|---|
| Log a call against an opportunity | FR-ACT-01 | 1 |
| Links are required and validated | FR-ACT-01 | 1 |
| Update with version and ownership | FR-ACT-01 | 1 |
| Archived activities leave lists and timelines | — | 1 |
| Activity list filters | — | 1 |
| Task needs due date and an assignee | FR-ACT-02 | 1 |
| Assignee or owner completes and reopens | FR-ACT-02 | 1 |
| My tasks open and overdue first | FR-ACT-02 | 1 |
| Logged activity clears the idle flag | FR-OPP-06 | 1 |
| Opportunity timeline merges activities and events | FR-ACT-03 | 1 |
| Organization timeline includes its records | FR-ACT-03 | 1 |
| Task edit rules | FR-ACT-02 | 1 |
| Activity date filters and sync mode | — | 1 |

**`backend/tests/api/test_assistant.py`** (31)

| Test | Requirement | Cases |
|---|---|---|
| Switched off every endpoint but status is 503 | FR-AI-07 | 1 |
| Default settings keep the assistant off | FR-AI-07 | 1 |
| Feature flag follows the switch | FR-AI-07 | 1 |
| Status reports the daily budget | FR-AI-08 | 1 |
| Conversations are saved renamed and deleted | FR-AI-01 | 1 |
| Another users conversation is not found | FR-AI-01 | 1 |
| Message length and context are validated | FR-AI-01 | 1 |
| Answer streams with tool progress and record links | FR-AI-02 | 1 |
| Tools run as the user and skip archived records | FR-AI-02 AC1 | 1 |
| Tools return compact records without contact details | FR-AI-02 | 1 |
| Reports tasks and activities tools | FR-AI-02 | 1 |
| Bad tool calls come back to the model as errors | FR-AI-02 AC3 | 1 |
| Tool loop stops after five rounds | — | 1 |
| Record in view reaches the model as a tool result | FR-AI-03 | 1 |
| Only read only tools exist | FR-AI-05 | 1 |
| Injected instructions cannot change data | FR-AI-05 | 1 |
| Prompt asks for the users language and keeps history | FR-AI-06 | 1 |
| History is trimmed to the token limit | — | 1 |
| Provider failure is a chat error and the crm keeps working | FR-AI-07 | 1 |
| Unexpected failure is reported without details | FR-AI-07 | 1 |
| Daily token budget | FR-AI-08 | 1 |
| Message rate limit | FR-AI-08 | 1 |
| Stop ends the answer and keeps what was written | FR-AI-01 | 1 |
| Stop endpoint flags a running answer | FR-AI-01 | 1 |
| Draft is saved as a note only on request | FR-AI-04 | 1 |
| Viewers cannot save notes | FR-AI-04 | 1 |
| Chat content is never logged | — | 1 |
| Integration clients never reach the assistant | — | 1 |
| Opportunity table untouched by reads | — | 1 |
| The question decides the language not the profile | FR-AI-06 | 1 |
| Reply language detection | FR-AI-06 | 1 |

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

**`backend/tests/api/test_authorization_matrix.py`** (301)

| Test | Requirement | Cases |
|---|---|---|
| Route role matrix | FR-AUTH-05 | 150 |
| Matrix covers every api route | — | 1 |
| Integration scope matrix | FR-INT-03 | 150 |

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

**`backend/tests/api/test_conversion.py`** (7)

| Test | Requirement | Cases |
|---|---|---|
| Convert creates and links everything | FR-LEAD-04 AC1 | 1 |
| Convert with existing records | FR-LEAD-04 | 1 |
| Without a contact | FR-LEAD-04 | 1 |
| Nothing is created when a step fails | FR-LEAD-04 AC2 | 1 |
| Validation and state rules | FR-LEAD-04 | 1 |
| Conversion preview suggests matches | FR-LEAD-04 | 1 |
| Lead activities appear on the opportunity timeline | FR-LEAD-04 AC3 | 1 |

**`backend/tests/api/test_exports.py`** (7)

| Test | Requirement | Cases |
|---|---|---|
| Organizations xlsx with filters and audit | FR-REP-02 | 1 |
| Leads csv in bulgarian with chosen columns | FR-REP-02 | 1 |
| Export defaults to the users language | FR-REP-02 | 1 |
| Opportunities and activities | FR-REP-02 | 1 |
| Contacts and audit log | FR-REP-02 | 1 |
| Row cap | FR-REP-02 | 1 |
| Neutralize formula prefixes | — | 1 |

**`backend/tests/api/test_gdpr.py`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Export lists everything held about the contact | FR-ADM-04 | 1 |
| Anonymize replaces personal fields and keeps history | FR-ADM-04 | 1 |
| Export after anonymization holds only free text mentions | FR-ADM-04 | 1 |
| Only admins | FR-ADM-04 | 1 |

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

**`backend/tests/api/test_import_samples.py`** (3)

| Test | Requirement | Cases |
|---|---|---|
| Every sample column is a template header | — | 1 |
| The format document lists every field in both languages | — | 1 |
| Samples import without errors | FR-IMP-01 | 1 |

**`backend/tests/api/test_imports.py`** (14)

| Test | Requirement | Cases |
|---|---|---|
| Templates in both languages | FR-IMP-01 | 1 |
| Csv upload detects encoding delimiter and mapping | FR-IMP-01 AC1 | 1 |
| Mapping rules | FR-IMP-01 | 1 |
| File checks | FR-IMP-01 | 1 |
| Ac3 validation preview with reasons | FR-IMP-01 AC1 | 1 |
| Strict commit writes nothing while rows are invalid | FR-IMP-01 AC2 | 1 |
| Ac3 ac4 commit update duplicates and roll back | FR-IMP-01 AC2 | 1 |
| Rollback keeps records changed since import | FR-IMP-01 AC4 | 1 |
| Commit is all or nothing when a row fails late | FR-IMP-01 AC2 | 1 |
| Contacts link organizations and skip duplicates | FR-IMP-01 | 1 |
| Leads with sources and owners | FR-IMP-01 | 1 |
| Opportunities with lookups | FR-IMP-01 | 1 |
| Discard and expiry | — | 1 |
| Seed creates fictional volumes | NFR-01 | 1 |

**`backend/tests/api/test_integration.py`** (22)

| Test | Requirement | Cases |
|---|---|---|
| Admin registers a client backed by a service user | FR-INT-01 | 1 |
| Deactivated client is refused | FR-INT-01 AC1 | 1 |
| Client is the actor of its changes | FR-INT-01 AC2 | 1 |
| Key is shown once and only its hash is stored | FR-INT-02 | 1 |
| Rotation limit expiry and revocation | FR-INT-02 AC2 | 1 |
| Malformed and mixed credentials | FR-INT-02 | 1 |
| Ip allowlist | FR-INT-02 | 1 |
| Last use is recorded | FR-INT-02 | 1 |
| Ac2 scopes and refused areas | FR-INT-03 AC1 | 1 |
| No archive assign convert or owner change | FR-INT-03 AC3 | 1 |
| Created records need a human owner | FR-INT-03 AC4 | 1 |
| Search is limited to readable types | FR-INT-03 | 1 |
| Activities patch only own | FR-INT-03 | 1 |
| Client writes its own system and finds records | FR-INT-04 | 1 |
| Reference rules | FR-INT-04 | 1 |
| Sync with an api key | FR-INT-05 | 1 |
| Idempotent creation | FR-INT-06 | 1 |
| Usage counters | FR-INT-08 | 1 |
| Rate limit per client | FR-INT-09 | 1 |
| Admin updates a client | FR-INT-01 | 1 |
| Cli creates the initial profiles inactive | FR-INT-01 | 1 |
| Idempotency edge cases | FR-INT-06 | 1 |

**`backend/tests/api/test_leads.py`** (21)

| Test | Requirement | Cases |
|---|---|---|
| Company name alone is enough | FR-LEAD-01 | 1 |
| All fields bant score and links | FR-LEAD-01 | 1 |
| Lead validation | — | 1 |
| Lead links and lists are validated | — | 1 |
| Happy path new contacted qualified | FR-LEAD-02 | 1 |
| Cannot qualify with unknown bant | FR-LEAD-03 AC1 | 1 |
| Invalid transitions are 409 | FR-LEAD-02 | 1 |
| Disqualify needs a reason and makes the lead read only | FR-LEAD-02 AC1 | 1 |
| Only managers reopen | FR-LEAD-02 AC2 | 1 |
| Stale version returns 409 with the current lead | — | 1 |
| Patch refuses status and owner | — | 1 |
| Patch needs a version | — | 1 |
| Unchanged patch keeps the version | — | 1 |
| Rep cannot change another reps lead | FR-AUTH-05 AC1 | 1 |
| Rep takes over a lead but cannot give it away | FR-LEAD-06 | 1 |
| Manager assigns to anyone active | FR-LEAD-06 | 1 |
| Viewer cannot capture or assign | — | 1 |
| Archive and restore | — | 1 |
| Filters sort and search | FR-LEAD-05 | 1 |
| Organization shows its open leads | FR-PARTY-03 | 1 |
| Lead lists are seeded and protected when used | FR-ADM-02 | 1 |

**`backend/tests/api/test_me_settings_audit.py`** (17)

| Test | Requirement | Cases |
|---|---|---|
| Me lists permissions for the ui | FR-AUTH-05 | 1 |
| Fn 05 me gives the session timeouts | — | 1 |
| Language preference is saved on the profile | FR-I18N-01 | 1 |
| Me rejects unknown fields and locales | — | 1 |
| List and revoke own sessions | FR-AUTH-04 | 1 |
| Revoking another users session is not found | — | 1 |
| System info for signed in users | — | 1 |
| Settings defaults and update | FR-AUTH-04 | 1 |
| Settings validation | — | 6 |
| Admin browses and filters the audit log | FR-ADM-03 | 1 |
| Audit entries never contain secrets | — | 1 |
| Application role cannot change audit entries | FR-ADM-03 | 1 |

**`backend/tests/api/test_mfa.py`** (13)

| Test | Requirement | Cases |
|---|---|---|
| Enrol with a code and get recovery codes | FR-AUTH-07 | 1 |
| Sign in needs the code after the password | FR-AUTH-07 | 1 |
| Pending cookie is scoped and short lived | FR-AUTH-07 | 1 |
| A code works once | FR-AUTH-07 | 1 |
| Recovery code works once | FR-AUTH-07 | 1 |
| Wrong codes lock the account | FR-AUTH-01 | 1 |
| Disable needs the password | FR-AUTH-07 | 1 |
| Enforced for admins | FR-AUTH-07 | 1 |
| Reset mfa from the cli | — | 1 |
| System info reports mfa available | — | 1 |
| Malformed codes are refused | — | 3 |

**`backend/tests/api/test_operations.py`** (5)

| Test | Requirement | Cases |
|---|---|---|
| Create admin prints a one time link | — | 1 |
| Create admin with password from stdin | — | 1 |
| Create admin rejects weak password and duplicates | — | 1 |
| Housekeeping removes expired sessions | — | 1 |
| Every limits how often a job runs | — | 1 |

**`backend/tests/api/test_opportunities.py`** (26)

| Test | Requirement | Cases |
|---|---|---|
| Default pipeline is seeded in both languages | FR-OPP-02 | 1 |
| Admin adds renames reorders and deletes a stage | FR-ADM-02 | 1 |
| Stage in use cannot be deleted only deactivated | FR-OPP-02 AC1 | 1 |
| Each stage type keeps one active stage | — | 1 |
| Stage validation | — | 1 |
| Create defaults to first open stage and its probability | FR-OPP-01 | 1 |
| Stage contact and probability override on create | FR-OPP-01 | 1 |
| Links are validated | FR-OPP-01 | 1 |
| Update with version and probability reset | FR-OPP-01 | 1 |
| Patch refuses action only fields | — | 1 |
| Rep cannot change another reps opportunity | FR-AUTH-05 | 1 |
| Move records history and resets probability | FR-OPP-02 AC2 | 1 |
| Move only between open stages | — | 1 |
| Close won with actual close date | FR-OPP-05 | 1 |
| Lost requires a loss reason | FR-OPP-05 | 1 |
| Closed is read only until a manager reopens | FR-OPP-05 | 1 |
| Opportunity assignment rules | FR-LEAD-06 | 1 |
| Archive and restore | — | 1 |
| List filters sort and search | FR-OPP-04 | 1 |
| Stale when idle or past expected close | FR-OPP-06 | 1 |
| Board columns totals and can edit | FR-OPP-03 | 1 |
| Organization counts and opportunities | FR-PARTY-03 | 1 |
| Organization archive blocked while open opportunities | — | 1 |
| Search finds opportunities | FR-PARTY-04 | 1 |
| Loss reasons are seeded and protected when used | FR-ADM-02 | 1 |
| Opportunities support sync mode | FR-INT-05 | 1 |

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

**`backend/tests/api/test_phase6_exit.py`** (1)

| Test | Requirement | Cases |
|---|---|---|
| Phase 6 exit erp round trip | — | 1 |

**`backend/tests/api/test_reports.py`** (8)

| Test | Requirement | Cases |
|---|---|---|
| Forecast matches an independent calculation | FR-REP-01 AC1 | 1 |
| Pipeline by stage | FR-REP-01 | 1 |
| Lead conversion rate and groups | FR-REP-01 | 1 |
| Win loss by reason owner and month | FR-REP-03 | 1 |
| Dashboard in one call | FR-REP-01 | 1 |
| Report parameters are validated | — | 1 |
| Report export with total row | FR-REP-02 | 1 |
| Forecast conversion and win loss exports | FR-REP-02 | 1 |

**`backend/tests/api/test_route_catalog.py`** (463)

| Test | Requirement | Cases |
|---|---|---|
| Catalog is parsed | — | 1 |
| Every route is in the catalog | — | 154 |
| Every api route declares the catalog access level | — | 152 |
| Every catalog entry is built or pending | — | 154 |
| Pending list only names catalog entries | — | 1 |
| No route is hidden from the openapi document | — | 1 |

**`backend/tests/api/test_security_headers.py`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Asvs 8 2 1 api responses are not cached | — | 1 |
| Asvs 8 2 1 routes may set their own cache policy | — | 1 |
| Asvs 4 2 2 state changing requests need the csrf header | — | 1 |
| Asvs 7 4 1 errors carry a code and request id only | — | 1 |

**`backend/tests/api/test_security_notices.py`** (3)

| Test | Requirement | Cases |
|---|---|---|
| Password change is notified in the users language | — | 1 |
| Reset and two factor changes are notified | — | 1 |
| No notices without smtp or for a first password | — | 1 |

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

**`backend/tests/api/test_users.py`** (18)

| Test | Requirement | Cases |
|---|---|---|
| Admin creates user with one time link | FR-ADM-01 | 1 |
| Link is emailed when smtp is configured | FR-AUTH-02 | 1 |
| Duplicate email is rejected case insensitively | — | 1 |
| Create user validates fields | — | 1 |
| List filter and detail | — | 1 |
| Ux 08 list sorts by column | FR-ADM-01 | 1 |
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
| Simultaneous creation with one email is a conflict | FR-ADM-01 | 1 |

**`backend/tests/api/test_webhooks.py`** (42)

| Test | Requirement | Cases |
|---|---|---|
| Events commit or roll back with the change | FR-INT-07 AC1 | 1 |
| Business changes write mapped events | FR-INT-07 AC1 | 1 |
| Domain actions map to event types | FR-INT-07 | 1 |
| Subscription secret shown once and encrypted | FR-INT-07 | 1 |
| Url must be on the allowlist | FR-INT-07 AC5 | 5 |
| Subscription validation update and delete | FR-INT-07 | 1 |
| Only events the client may read | FR-INT-07 AC4 | 1 |
| Signed delivery with the current record | FR-INT-07 AC2 | 1 |
| Wrong signature is refused by the receiver | FR-INT-07 | 1 |
| Retries with backoff then fails after 72 hours | FR-INT-07 AC3 | 1 |
| Backoff schedule | FR-INT-07 AC3 | 1 |
| Redirects are not followed | FR-INT-07 | 1 |
| Loopback is refused after resolution | FR-INT-07 AC5 | 1 |
| Url rechecked at delivery | FR-INT-07 | 1 |
| Rotation signs with both secrets for 24 hours | FR-INT-07 | 1 |
| Test event is sent once even for an inactive client | FR-INT-12 | 1 |
| Deliveries wait while the client is inactive | FR-INT-01 | 1 |
| Events for one record are delivered in order | FR-INT-07 | 1 |
| Delivery log filters and redeliver | FR-INT-12 | 1 |
| Old events are purged | FR-INT-07 | 1 |
| Host and url rules | FR-INT-07 AC5 | 1 |
| Address rules | FR-INT-07 AC5 | 12 |
| Reference receiver verifies signatures | FR-INT-10 | 1 |
| Worker job dispatches and attempts on each poll | NFR-13 | 1 |
| Integration guide python sample verifies crm signatures | FR-INT-10 | 1 |
| Reference changes are sent with the reference | FR-INT-04 | 1 |
| Connection failures are recorded | FR-INT-07 | 1 |

**`backend/tests/migrations/test_migrations.py`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Every migration upgrades and downgrades | NFR-12 | 1 |
| Models match migrations | NFR-12 | 1 |
| Pg trgm is installed | — | 1 |
| Application role cannot run ddl | NFR-04 | 1 |

**`backend/tests/unit/test_cli.py`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Export openapi writes document | FR-INT-10 | 1 |
| Export openapi defaults to stdout | — | 1 |
| Command is required | — | 1 |
| Seed demo is refused in production | NFR-01 | 1 |

**`backend/tests/unit/test_config.py`** (9)

| Test | Requirement | Cases |
|---|---|---|
| Production refuses default database secret | NFR-04 | 1 |
| Production refuses default migration secret | NFR-04 | 1 |
| Production starts with real secrets | NFR-04 | 1 |
| Production refuses default encryption key | NFR-04 | 1 |
| Webhook hosts are parsed from a list | FR-INT-07 | 1 |
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

**`backend/tests/unit/test_import_parsing.py`** (8)

| Test | Requirement | Cases |
|---|---|---|
| Csv utf8 with bom and commas | FR-IMP-01 | 1 |
| Csv windows 1251 and semicolons | FR-IMP-01 | 1 |
| Xlsx values are text and formulas are not run | FR-IMP-01 | 1 |
| Unreadable files | FR-IMP-01 | 4 |
| Mapping suggestion by key and both languages | FR-IMP-01 | 1 |

**`backend/tests/unit/test_integration_docs.py`** (1)

| Test | Requirement | Cases |
|---|---|---|
| Collection requests match routes | FR-INT-10 | 1 |

**`backend/tests/unit/test_lead_lifecycle.py`** (34)

| Test | Requirement | Cases |
|---|---|---|
| Transition matrix | FR-LEAD-02 | 25 |
| Converted and disqualified are terminal except reopen | FR-LEAD-02 AC2 | 1 |
| Score | FR-LEAD-03 AC2 | 7 |
| Unknown items are listed | FR-LEAD-03 AC1 | 1 |

**`backend/tests/unit/test_llm_client.py`** (10)

| Test | Requirement | Cases |
|---|---|---|
| Routes to the configured model through cerebras only | — | 1 |
| Tool call fragments are assembled | — | 1 |
| Provider errors become unavailable without details | FR-AI-07 | 1 |
| Slow provider times out | FR-AI-07 | 1 |
| Importing litellm does not load dotenv files | — | 1 |
| Message logging is off | — | 1 |
| Factory picks the model from settings | — | 1 |
| Settings refuse an assistant without a model | FR-AI-07 | 1 |
| Demo model answers from the tool result in the users language | — | 1 |
| Real client against the scripted provider server | — | 1 |

**`backend/tests/unit/test_logging.py`** (5)

| Test | Requirement | Cases |
|---|---|---|
| Log line is json with request id | NFR-08 | 1 |
| Log line without request context has no request id | NFR-08 | 1 |
| Litellm redaction marker is not logged | NFR-08 | 1 |
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

**`backend/tests/unit/test_policy.py`** (90)

| Test | Requirement | Cases |
|---|---|---|
| Role matrix | FR-AUTH-05 | 52 |
| Public is open to everyone | — | 15 |
| Anonymous callers get 401 | FR-AUTH-05 | 14 |
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

### Frontend (Vitest + Testing Library + MSW) — 282 test cases

**`frontend/src/app/app.test.tsx`** (16)

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
| FN-06 language preference › FN-06 signing in on another device applies the language saved on the profile | — | 1 |

**`frontend/src/app/appShell.test.tsx`** (5)

| Test | Requirement | Cases |
|---|---|---|
| UX-02 app shell › UX-02 groups the navigation by area and highlights the active route | — | 1 |
| UX-02 app shell › UX-02 shows only the routes a sales rep may open | — | 1 |
| UX-02 app shell › UX-02 collapses the sidebar and remembers it for the session | — | 1 |
| UX-02 app shell › UX-02 opens the navigation drawer and closes it after navigating, in Bulgarian too | — | 1 |
| UX-02 app shell › UX-02 user menu links to the profile and offers language and sign out | — | 1 |

**`frontend/src/app/designTokens.test.ts`** (3)

| Test | Requirement | Cases |
|---|---|---|
| UX-01 design tokens › scans the source files | — | 1 |
| UX-01 design tokens › UX-01 has no hex, rgb, hsl or oklch color literals outside the theme file | — | 1 |
| UX-01 design tokens › UX-01 uses theme color utilities, not Tailwind palette colors | — | 1 |

**`frontend/src/app/statusColors.test.tsx`** (5)

| Test | Requirement | Cases |
|---|---|---|
| NFR-10 status color contrast (loop 2) › NFR-10 %s text keeps 4.5:1 on white and on its 10% badge tint | NFR-10 | 1 |
| NFR-10 status color contrast (loop 2) › NFR-10 the contrast helper agrees with a known pair (black on white is 21:1) | NFR-10 | 1 |
| UX-01 status badges use semantic colors (loop 2) › FR-LEAD-05 lead statuses: new blue, qualified green, disqualified red, others neutral | FR-LEAD-05 | 1 |
| UX-01 status badges use semantic colors (loop 2) › FR-OPP-06 stages: open blue, won green, lost red; stale amber | FR-OPP-06 | 1 |
| UX-01 status badges use semantic colors (loop 2) › FR-IMP-01 imports: steps in progress blue, imported green, rolled back neutral | FR-IMP-01 | 1 |

**`frontend/src/app/warmShell.test.tsx`** (4)

| Test | Requirement | Cases |
|---|---|---|
| UX-02 warm app shell (loop 3) › UX-02 the sidebar sits on the warm sidebar surface | — | 1 |
| UX-02 warm app shell (loop 3) › UX-02 the active page is a peach tint with a terracotta edge; others warm on hover | — | 1 |
| UX-02 warm app shell (loop 3) › UX-01 the header shows a decorative brand mark next to the app name | — | 1 |
| UX-02 warm app shell (loop 3) › UX-01 primary buttons darken on hover instead of fading (white text keeps contrast) | — | 1 |

**`frontend/src/app/warmTheme.test.ts`** (8)

| Test | Requirement | Cases |
|---|---|---|
| UX-01 warm theme (loop 3) › UX-01 neutral token --%s is tinted warm, not pure grey | — | 1 |
| UX-01 warm theme (loop 3) › UX-01 the brand is a warm terracotta and primary follows it | — | 1 |
| UX-01 warm theme (loop 3) › UX-01 warning is kept apart from the brand hue, so it does not read as a brand accent | — | 1 |
| NFR-10 warm theme contrast (loop 3) › NFR-10 text in --%s on --%s keeps 4.5:1 | NFR-10 | 1 |
| NFR-10 warm theme contrast (loop 3) › NFR-10 muted text on a table header (muted at 70% over the card) keeps 4.5:1 | NFR-10 | 1 |
| NFR-10 warm theme contrast (loop 3) › NFR-10 accent text on a 60% accent hover keeps 4.5:1 | NFR-10 | 1 |
| NFR-10 warm theme contrast (loop 3) › NFR-10 the focus ring keeps 3:1 against --%s (WCAG 1.4.11) | NFR-10 | 1 |
| NFR-10 warm theme contrast (loop 3) › NFR-10 dashboard series --%s keeps 3:1 against the card (WCAG 1.4.11) | NFR-10 | 1 |

**`frontend/src/components/PageHeader.test.tsx`** (4)

| Test | Requirement | Cases |
|---|---|---|
| UX-03 page header › UX-03 no page renders its own h1 | — | 1 |
| UX-03 page header › UX-03 record pages show breadcrumbs back to their list | — | 1 |
| UX-03 page header › UX-03 edit pages lead back through the record, in Bulgarian too | — | 1 |
| UX-03 page header › UX-03 list pages have no breadcrumbs but keep their actions | — | 1 |

**`frontend/src/components/formConventions.test.tsx`** (8)

| Test | Requirement | Cases |
|---|---|---|
| UX-11 form conventions › UX-11 marks a required field without changing its label | — | 1 |
| UX-11 form conventions › UX-11 leaves optional fields unmarked | — | 1 |
| UX-11 form conventions › UX-11 no feature builds its own labels | — | 1 |
| UX-11 unsaved changes › UX-11 marks required fields on a record form | — | 1 |
| UX-11 unsaved changes › UX-11 warns before leaving a form with changes, and can stay | — | 1 |
| UX-11 unsaved changes › UX-11 leaves without saving when asked to | — | 1 |
| UX-11 unsaved changes › UX-11 an untouched form does not ask | — | 1 |
| UX-11 unsaved changes › UX-11 also asks the browser before closing the tab | — | 1 |

**`frontend/src/components/listEmptyState.test.tsx`** (4)

| Test | Requirement | Cases |
|---|---|---|
| empty lists say what to do next › offers to create the first record | — | 1 |
| empty lists say what to do next › offers no create action to a user who may not create | — | 1 |
| empty lists say what to do next › clears search and filters but keeps the sort | — | 1 |
| empty lists say what to do next › says so in Bulgarian too | — | 1 |

**`frontend/src/components/motion.test.tsx`** (6)

| Test | Requirement | Cases |
|---|---|---|
| UX-04 busy lists (loop 2) › UX-04 a busy table is marked aria-busy, dims its rows and shows the progress bar | — | 1 |
| UX-04 busy lists (loop 2) › UX-04 an idle table has no busy state | — | 1 |
| UX-04 busy lists (loop 2) › FR-LEAD-05 the lead list shows it is updating while the next page loads | FR-LEAD-05 | 1 |
| UX-04 page transitions (loop 2) › UX-04 a new page enters when the address changes, not when only the search changes | — | 1 |
| WCAG 2.3.3 reduced motion (loop 2) › WCAG 2.3.3 the theme stops animations and transitions when the user asks for less motion | — | 1 |
| WCAG 2.3.3 reduced motion (loop 2) › UX-04 the busy bar appears only after a short delay, so quick answers do not flicker | — | 1 |

**`frontend/src/components/pageTitlesAndLinks.test.tsx`** (9)

| Test | Requirement | Cases |
|---|---|---|
| page titles (WCAG 2.4.2) › names the page in the browser tab | — | 1 |
| page titles (WCAG 2.4.2) › uses the record name on a record page | — | 1 |
| page titles (WCAG 2.4.2) › titles signed-out and error pages, in Bulgarian too | — | 1 |
| contact details as links › calls the number without spaces or punctuation | — | 1 |
| contact details as links › writes an email | — | 1 |
| contact details as links › opens a website in a new tab without giving it access to this one | — | 1 |
| contact details as links › only links http(s) addresses: %s | — | 1 |
| contact details as links › shows any other address as plain text | — | 1 |
| contact details as links › shows nothing when there is no value | — | 1 |

**`frontend/src/components/responsive.test.tsx`** (8)

| Test | Requirement | Cases |
|---|---|---|
| NFR-11 touch targets (loop 2) › NFR-11 a %s button grows on a coarse pointer | NFR-11 | 1 |
| NFR-11 touch targets (loop 2) › NFR-11 text inputs grow to 44 px on a coarse pointer | NFR-11 | 1 |
| NFR-11 narrow screens (loop 2) › NFR-11 the search box never needs more than the screen width | NFR-11 | 1 |
| NFR-11 narrow screens (loop 2) › NFR-11 pagination wraps instead of overflowing | NFR-11 | 1 |
| NFR-11 narrow screens (loop 2) › NFR-11 a sideways-scrolling table shows a scroll hint | NFR-11 | 1 |
| NFR-11 narrow screens (loop 2) › NFR-11 record details stack label over value below the sm breakpoint | NFR-11 | 1 |
| NFR-11 record detail lists (loop 2) › NFR-11 no page hard-codes a two-column detail list | NFR-11 | 1 |
| NFR-11 record detail lists (loop 2) › NFR-11 the record pages use the shared detail list | NFR-11 | 1 |

**`frontend/src/components/states.test.tsx`** (5)

| Test | Requirement | Cases |
|---|---|---|
| UX-04 loading, empty and error states › UX-04 no page writes its own loading or empty text | — | 1 |
| UX-04 loading, empty and error states › UX-04 %s skeleton is announced once, without visible text | — | 1 |
| UX-04 loading, empty and error states › UX-04 an empty list shows the empty state | — | 1 |
| UX-04 loading, empty and error states › UX-04 a failed list shows the request ID and retries | — | 1 |
| UX-04 loading, empty and error states › UX-04 the route error boundary offers a retry and the request ID, in Bulgarian too | — | 1 |

**`frontend/src/lib/format.test.ts`** (3)

| Test | Requirement | Cases |
|---|---|---|
| FR-I18N-03 locale formatting in Europe/Sofia time › shows UTC timestamps in Sofia time | FR-I18N-03 | 1 |
| FR-I18N-03 locale formatting in Europe/Sofia time › formats numbers and EUR amounts per language | FR-I18N-03 | 1 |
| UX-13 compact money for chart axes › UX-13 %d in %s is %s | — | 1 |

**`frontend/src/lib/locale.test.ts`** (4)

| Test | Requirement | Cases |
|---|---|---|
| FR-I18N-01 locale detection › uses a stored choice first | FR-I18N-01 | 1 |
| FR-I18N-01 locale detection › follows the browser language when nothing is stored | FR-I18N-01 | 1 |
| FR-I18N-01 locale detection › ignores unsupported stored values | FR-I18N-01 | 1 |
| FR-I18N-01 locale detection › remembers the chosen language | FR-I18N-01 | 1 |

**`frontend/src/lib/notify.test.tsx`** (5)

| Test | Requirement | Cases |
|---|---|---|
| UX-05 feedback › UX-05 maps a backend error code to its translated message | — | 1 |
| UX-05 feedback › UX-05 falls back to a generic message for unknown codes and network failures | — | 1 |
| UX-05 feedback › UX-05 maps the code in Bulgarian too | — | 1 |
| UX-05 feedback › UX-05 shows success messages | — | 1 |
| UX-05 feedback › UX-05 says when the language could not be kept on the profile | — | 1 |

**`frontend/src/lib/userAgent.test.ts`** (2)

| Test | Requirement | Cases |
|---|---|---|
| FN-02 device names › FN-02 %s | — | 1 |
| FN-02 device names › FN-02 no user agent | — | 1 |

**`frontend/src/lib/zodConfig.test.ts`** (1)

| Test | Requirement | Cases |
|---|---|---|
| ASVS 5.2.4 Zod never probes eval, which the CSP forbids | — | 1 |

**`frontend/src/features/activities/activities.test.tsx`** (5)

| Test | Requirement | Cases |
|---|---|---|
| FR-ACT-03 timeline › merges activities with system events, including the source lead | FR-ACT-03 | 1 |
| FR-ACT-03 timeline › FR-ACT-01 logs a call against the record | FR-ACT-03, FR-ACT-01 | 1 |
| FR-ACT-03 timeline › FR-ACT-02 a task needs a due date | FR-ACT-03, FR-ACT-02 | 1 |
| FR-ACT-03 timeline freshness › reloads the timeline after a change to the record | FR-ACT-03 | 1 |
| FR-ACT-02 my tasks › shows overdue tasks and marks them done | FR-ACT-02 | 1 |

**`frontend/src/features/admin/admin.test.tsx`** (9)

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
| FR-AUTH-04 settings › FR-OPP-06 saves the stale-opportunity threshold | FR-AUTH-04, FR-OPP-06 | 1 |

**`frontend/src/features/admin/auditViewer.test.tsx`** (9)

| Test | Requirement | Cases |
|---|---|---|
| UX-10 audit log viewer › UX-10 filters by user and record type | — | 1 |
| UX-10 audit log viewer › UX-10 the %s preset sets the date range | — | 1 |
| UX-10 audit log viewer › UX-10 opens an entry in a drawer with changes side by side | — | 1 |
| UX-10 audit log viewer › UX-10 opens the drawer from a shared link, in Bulgarian too | — | 1 |
| UX-10 diff › UX-10 shows a created record with nothing before | — | 1 |
| UX-10 diff › UX-10 shows nested values as formatted JSON | — | 1 |
| UX-10 diff › UX-10 falls back to formatted JSON when the values are not field maps | — | 1 |
| UX-10 diff of a created record › UX-10 does not flag fields that stay empty | — | 1 |
| FN-07 audit log export › FN-07 exports the log with the current filters and without paging | — | 1 |

**`frontend/src/features/admin/lastAdmin.test.tsx`** (4)

| Test | Requirement | Cases |
|---|---|---|
| FN-08 last-admin protection › FN-08 the last active Admin cannot be demoted, and the sheet says why | — | 1 |
| FN-08 last-admin protection › FN-08 with two active Admins the role can change | — | 1 |
| FN-08 last-admin protection › FN-08 deactivating the last Admin is disabled on their page, with the reason | — | 1 |
| FN-08 last-admin protection › FN-08 the server refusal is still explained if the count was out of date | — | 1 |

**`frontend/src/features/admin/userActions.test.tsx`** (4)

| Test | Requirement | Cases |
|---|---|---|
| FN-03 admin user actions in the row menu › FN-03 offers the actions that fit each user | — | 1 |
| FN-03 admin user actions in the row menu › FN-03 %s asks first and tells the result | — | 1 |
| FN-03 admin user actions in the row menu › FN-03 cancelling does nothing | — | 1 |
| FN-03 admin user actions in the row menu › FN-03 shows a reset link once and forgets it, in Bulgarian too | — | 1 |

**`frontend/src/features/admin/userSheets.test.tsx`** (4)

| Test | Requirement | Cases |
|---|---|---|
| UX-09 create and edit user › UX-09 creates a user in a sheet and shows the link once | — | 1 |
| UX-09 create and edit user › UX-09 closing with Escape also forgets the link | — | 1 |
| UX-09 create and edit user › UX-09 edits a user from the row menu | — | 1 |
| UX-09 create and edit user › UX-09 edits from the user page, in Bulgarian too | — | 1 |

**`frontend/src/features/admin/usersTable.test.tsx`** (7)

| Test | Requirement | Cases |
|---|---|---|
| UX-08 users table › UX-08 sorts by a column and keeps the sort in the URL | — | 1 |
| UX-08 users table › UX-08 reads search, filters and sort from a shared URL | — | 1 |
| UX-08 users table › UX-08 falls back to name for a sort the API does not accept | — | 1 |
| UX-08 users table › UX-08 shows last sign-in relative with the exact time on hover | — | 1 |
| UX-08 users table › UX-08 shows status badges | — | 1 |
| UX-08 users table › UX-08 row action menu opens the user or unlocks a locked one | — | 1 |
| UX-08 relative time › UX-08 %s in %s is \"%s\" | — | 1 |

**`frontend/src/features/auth/idleWarning.test.tsx`** (6)

| Test | Requirement | Cases |
|---|---|---|
| FN-05 idle-timeout warning › FN-05 the schedule counts from a minute before the last request and respects the absolute expiry | — | 1 |
| FN-05 idle-timeout warning › FN-05 warns five minutes before the timeout and stays signed in | — | 1 |
| FN-05 idle-timeout warning › FN-05 activity in another tab closes the warning | — | 1 |
| FN-05 idle-timeout warning › FN-05 without an answer the session ends and sign-in says why | — | 1 |
| FN-05 idle-timeout warning › FN-05 signing out from the warning tells the other tabs | — | 1 |
| FN-05 idle-timeout warning › FN-05 a sign-out in another tab signs this tab out too, in Bulgarian | — | 1 |

**`frontend/src/features/auth/passwordRules.test.tsx`** (6)

| Test | Requirement | Cases |
|---|---|---|
| UX-07 password checklist › UX-07 length rule for %# | — | 1 |
| UX-07 password checklist › UX-07 the common-password rule says it is checked on save | — | 1 |
| UX-07 password checklist › UX-07 match rule for %s / %s | — | 1 |
| UX-07 set password page › UX-07 updates the checklist while typing | — | 1 |
| UX-07 set password page › UX-07 explains an expired link and what to do next | — | 1 |
| UX-07 set password page › UX-07 explains an incomplete link, in Bulgarian too | — | 1 |

**`frontend/src/features/auth/sessionExpiry.test.tsx`** (6)

| Test | Requirement | Cases |
|---|---|---|
| FN-04 session expiry › FN-04 a lost session goes to sign-in, says so, and comes back after signing in | — | 1 |
| FN-04 session expiry › FN-04 says so too when the profile reload is the first request after the session ended | — | 1 |
| FN-04 session expiry › FN-04 says so when several requests fail together as the session ends | — | 1 |
| FN-04 session expiry › FN-04 a first visit is sent to sign-in without the expiry message | — | 1 |
| FN-04 session expiry › FN-04 unsaved changes do not hold back the move to sign-in | — | 1 |
| FN-04 session expiry › FN-04 the sign-in target keeps the page and only flags a lost session | — | 1 |

**`frontend/src/features/auth/setPassword.test.tsx`** (6)

| Test | Requirement | Cases |
|---|---|---|
| FR-AUTH-02 set password from a one-time link › checks the token from the URL fragment and sets the password | FR-AUTH-02 | 1 |
| FR-AUTH-02 set password from a one-time link › explains an invalid or used link | FR-AUTH-02 | 1 |
| FR-AUTH-02 set password from a one-time link › shows the policy error returned by the server | FR-AUTH-02 | 1 |
| forgot password › always confirms without revealing whether the account exists | — | 1 |
| safeNext | — | 1 |
| set password errors › reports rate limiting instead of calling the link invalid | — | 1 |

**`frontend/src/features/auth/signInPage.test.tsx`** (7)

| Test | Requirement | Cases |
|---|---|---|
| UX-06 sign-in page › UX-06 uses the autocomplete hints password managers expect | — | 1 |
| UX-06 sign-in page › UX-06 shows and hides the password | — | 1 |
| UX-06 sign-in page › UX-06 shows caps lock warning | — | 1 |
| UX-06 sign-in page › UX-06 disables the button with a spinner while signing in | — | 1 |
| UX-06 sign-in page › UX-06 says how long a lockout lasts and focuses the message | — | 1 |
| UX-06 sign-in page › UX-06 moves focus to the first field with an error | — | 1 |
| UX-06 sign-in page › UX-06 shows the lockout time in Bulgarian too | — | 1 |

**`frontend/src/features/imports/imports.test.tsx`** (6)

| Test | Requirement | Cases |
|---|---|---|
| FR-IMP-01 import wizard › uploads a file and opens the batch | FR-IMP-01 | 1 |
| FR-IMP-01 import wizard › FR-IMP-01 AC1 maps columns, then saves and checks the rows | FR-IMP-01, FR-IMP-01 AC1 | 1 |
| FR-IMP-01 import wizard › FR-IMP-01 AC1 AC2 shows invalid rows with reasons and imports without them | FR-IMP-01, FR-IMP-01 AC1 | 1 |
| FR-IMP-01 import wizard › FR-IMP-01 AC4 only an Admin can roll back | FR-IMP-01, FR-IMP-01 AC4 | 1 |
| FR-IMP-01 import wizard › shows all rows once imported (the checking filter does not carry over) | FR-IMP-01 | 1 |
| FR-IMP-01 import wizard › is hidden from Sales Reps | FR-IMP-01 | 1 |

**`frontend/src/features/integrations/integrations.test.tsx`** (20)

| Test | Requirement | Cases |
|---|---|---|
| FR-INT-01 integration clients › lists clients and creates a new one inactive | FR-INT-01 | 1 |
| FR-INT-01 integration clients › keeps non-Admins out and hides the navigation link | FR-INT-01 | 1 |
| FR-INT-01 integration clients › shows the navigation link to Admins | FR-INT-01 | 1 |
| FR-INT-01 client settings › saves settings with the allowlist split into lines | FR-INT-01 | 1 |
| FR-INT-01 client settings › shows field errors from the server | FR-INT-01 | 1 |
| FR-INT-01 client settings › activates an inactive client | FR-INT-01 | 1 |
| FR-INT-02 API keys › AC1 shows a new key once, then only its prefix | FR-INT-02 | 1 |
| FR-INT-02 API keys › AC3 revokes a key after confirmation | FR-INT-02 | 1 |
| FR-INT-02 API keys › explains the two-key limit | FR-INT-02 | 1 |
| FR-INT-04 IDs in other systems on record pages › AC4 shows a stored ID as a link to the other system | FR-INT-04 | 1 |
| FR-INT-04 IDs in other systems on record pages › is hidden from non-Admins when there is nothing to show | FR-INT-04 | 1 |
| FR-INT-04 IDs in other systems on record pages › lets an Admin add and remove an ID | FR-INT-04 | 1 |
| FR-INT-07 webhook subscriptions › subscribes an endpoint and shows the signing secret once | FR-INT-07 | 1 |
| FR-INT-07 webhook subscriptions › AC5 shows the URL rule when the host is not allowed | FR-INT-07 | 1 |
| FR-INT-07 webhook subscriptions › lists a subscription, rotates its secret and queues a test event | FR-INT-07 | 1 |
| FR-INT-07 webhook subscriptions › resumes a suspended subscription | FR-INT-07 | 1 |
| FR-INT-12 delivery log › filters by status in the URL and opens a delivery with its attempts | FR-INT-12 | 1 |
| FR-INT-12 delivery log › AC3 redelivers a delivery | FR-INT-12 | 1 |
| FR-INT-08 failing-delivery alert › shows a badge on the navigation and a banner in the admin area | FR-INT-08 | 1 |
| FR-INT-08 failing-delivery alert › is not shown without problems | FR-INT-08 | 1 |

**`frontend/src/features/assistant/assistant.test.tsx`** (13)

| Test | Requirement | Cases |
|---|---|---|
| FR-AI-07 switch › shows no assistant while it is switched off | FR-AI-07 | 1 |
| FR-AI-07 switch › opens the drawer from the header, in Bulgarian too | FR-AI-07 | 1 |
| FR-AI-01, 02 streamed answers › streams an answer with tool progress, Markdown, record links and no raw HTML | FR-AI-01 | 1 |
| FR-AI-01, 02 streamed answers › stops a running answer | FR-AI-01 | 1 |
| FR-AI-01, 02 streamed answers › FR-AI-07 shows a provider failure as a chat error | FR-AI-01, FR-AI-07 | 1 |
| FR-AI-01, 02 streamed answers › FR-AI-08 shows a used-up budget | FR-AI-01, FR-AI-08 | 1 |
| FR-AI-01 follow-up questions › shows each message once while a follow-up streams | FR-AI-01 | 1 |
| FR-AI-03 record context › offers the opportunity in view and sends it with the new conversation | FR-AI-03 | 1 |
| FR-AI-01 history › lists, opens, renames and deletes conversations | FR-AI-01 | 1 |
| FR-AI-04 drafts › copies a draft and saves an edited draft as a note on a cited record | FR-AI-04 | 1 |
| FR-AI-04 drafts › offers no note saving to viewers | FR-AI-04 | 1 |
| Server-Sent Events parsing › keeps an unfinished block for the next chunk | — | 1 |
| FR-AI-04 save as note right after an answer › keeps an opened note form when the stored conversation replaces the live answer | FR-AI-04 | 1 |

**`frontend/src/features/leads/leads.test.tsx`** (14)

| Test | Requirement | Cases |
|---|---|---|
| FR-LEAD-05 lead list › shows status, score and value, with filters in the URL | FR-LEAD-05 | 1 |
| FR-LEAD-01 capture › saves with only a title and company name | FR-LEAD-01 | 1 |
| FR-LEAD-01 capture › validates the amount on the client | FR-LEAD-01 | 1 |
| FR-LEAD-02, 03 lead detail › FR-LEAD-03 shows BANT, recomputes the score live and saves with the version | FR-LEAD-02, FR-LEAD-03 | 1 |
| FR-LEAD-02, 03 lead detail › FR-LEAD-03 AC1 disables Qualify while a BANT item is unknown | FR-LEAD-02, FR-LEAD-03 AC1 | 1 |
| FR-LEAD-02, 03 lead detail › FR-LEAD-02 AC1 disqualifying needs a reason | FR-LEAD-02, FR-LEAD-02 AC1 | 1 |
| FR-LEAD-02, 03 lead detail › FR-LEAD-02 AC2 shows Reopen to managers only | FR-LEAD-02, FR-LEAD-02 AC2 | 1 |
| FR-LEAD-02, 03 lead detail › shows the latest version after a conflict | FR-LEAD-02 | 1 |
| FR-LEAD-02, 03 lead detail › FR-LEAD-06 lets a rep take over another rep's lead | FR-LEAD-02, FR-LEAD-06 | 1 |
| FR-ADM-02 lead lists administration › switches between the three lists | FR-ADM-02 | 1 |
| FR-LEAD-04 conversion › offers Convert on a qualified lead | FR-LEAD-04 | 1 |
| FR-LEAD-04 conversion › shows the opportunity a converted lead became | FR-LEAD-04 | 1 |
| FR-LEAD-04 conversion › suggests the matching organization and converts in one request | FR-LEAD-04 | 1 |
| FR-LEAD-04 conversion › asks before creating a duplicate organization | FR-LEAD-04 | 1 |

**`frontend/src/features/opportunities/opportunities.test.tsx`** (12)

| Test | Requirement | Cases |
|---|---|---|
| FR-OPP-04 opportunity list › shows stage, amounts and the stale flag, with filters in the URL | FR-OPP-04 | 1 |
| FR-OPP-01 create › requires an organization | FR-OPP-01 | 1 |
| FR-OPP-01 create › creates for a preset organization; empty probability follows the stage | FR-OPP-01 | 1 |
| FR-OPP-02, 05 opportunity detail › FR-OPP-02 moves to another open stage with the version and shows history | FR-OPP-02 | 1 |
| FR-OPP-02, 05 opportunity detail › FR-OPP-05 closing as lost needs a loss reason | FR-OPP-02, FR-OPP-05 | 1 |
| FR-OPP-02, 05 opportunity detail › FR-OPP-05 a closed opportunity is read-only; only a manager sees Reopen | FR-OPP-02, FR-OPP-05 | 1 |
| FR-OPP-02, 05 opportunity detail › shows the server version after a conflict | FR-OPP-02 | 1 |
| FR-OPP-03 pipeline board › shows open stages with totals and moves a card with the keyboard alternative | FR-OPP-03 | 1 |
| FR-OPP-03 pipeline board › dropping on Lost asks for a loss reason; won closes directly | FR-OPP-03 | 1 |
| FR-OPP-03 pipeline board › FR-OPP-03 AC2 cards the user may not edit cannot be moved | FR-OPP-03, FR-OPP-03 AC2 | 1 |
| FR-OPP-03 pipeline board › FR-I18N-01 shows Bulgarian stage names | FR-OPP-03, FR-I18N-01 | 1 |
| FR-OPP-02 / FR-ADM-02 stage administration › deactivates a stage and explains why a used stage cannot be deleted | FR-OPP-02, FR-ADM-02 | 1 |

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

**`frontend/src/features/contacts/gdpr.test.tsx`** (3)

| Test | Requirement | Cases |
|---|---|---|
| FR-ADM-04 GDPR tools › downloads the personal data as a JSON file | FR-ADM-04 | 1 |
| FR-ADM-04 GDPR tools › anonymizes only after the word is typed | FR-ADM-04 | 1 |
| FR-ADM-04 GDPR tools › is not offered to other roles | FR-ADM-04 | 1 |

**`frontend/src/features/profile/mfa.test.tsx`** (6)

| Test | Requirement | Cases |
|---|---|---|
| FR-AUTH-07 sign-in with a code › asks for the code after the password and signs in with it | FR-AUTH-07 | 1 |
| FR-AUTH-07 sign-in with a code › shows a wrong code and goes back to the password when the step expired | FR-AUTH-07 | 1 |
| FR-AUTH-07 profile › sets up with a QR code and a key, then shows the recovery codes once | FR-AUTH-07 | 1 |
| FR-AUTH-07 profile › turns off with the password and shows an enforcement refusal | FR-AUTH-07 | 1 |
| FR-AUTH-07 profile › sends an Admin who must set it up to the profile, with only the setup card | FR-AUTH-07 | 1 |
| FR-AUTH-07 Admin setting › requires two-factor sign-in for Admins | FR-AUTH-07 | 1 |

**`frontend/src/features/profile/profile.test.tsx`** (7)

| Test | Requirement | Cases |
|---|---|---|
| profile › FR-AUTH-04 lists sessions and signs out another one | FR-AUTH-04 | 1 |
| profile › FR-AUTH-03 checks the new password before calling the API | FR-AUTH-03 | 1 |
| profile › shows the server error for a wrong current password | — | 1 |
| FN-01 change password › FN-01 shows the password rules live while typing | — | 1 |
| FN-01 change password › FN-01 changes the password and says the other sessions were signed out | — | 1 |
| FN-02 my sessions › FN-02 lists device, start and last activity, with only the others revocable | — | 1 |
| FN-02 my sessions › FN-02 names the browser in Bulgarian too | — | 1 |

**`frontend/src/features/recent/recentlyViewed.test.tsx`** (7)

| Test | Requirement | Cases |
|---|---|---|
| recently viewed records › shows nothing until a record is opened | — | 1 |
| recently viewed records › lists opened records on the home page, newest first, without duplicates | — | 1 |
| recently viewed records › keeps only the latest records | — | 1 |
| recently viewed records › keeps each user’s records apart | — | 1 |
| recently viewed records › forgets a record that no longer exists | — | 1 |
| recently viewed records › clears the list on sign-out, so a shared computer shows nothing | — | 1 |
| recently viewed records › labels record types in Bulgarian | — | 1 |

**`frontend/src/features/reports/reports.test.tsx`** (5)

| Test | Requirement | Cases |
|---|---|---|
| FR-REP-01 dashboard › shows pipeline, forecast, rates and my tasks; the owner filter is in the URL | FR-REP-01 | 1 |
| FR-REP-01 dashboard › FR-I18N-01 in Bulgarian | FR-REP-01, FR-I18N-01 | 1 |
| FR-REP-03 win/loss report › groups by loss reason with a total row and regroups by month | FR-REP-03 | 1 |
| FR-REP-02 export › downloads the list with its filters and without paging | FR-REP-02 | 1 |
| FR-REP-02 export › explains when the export is too large | FR-REP-02 | 1 |

### End-to-end (Playwright, composed stack) — 100 test cases

**`frontend/e2e/accessibility.spec.ts`** (8)

| Test | Requirement | Cases |
|---|---|---|
| NFR-10 sign-in page (chromium) | NFR-10 | 1 |
| NFR-10 main pages, a record page and the assistant drawer (chromium) | NFR-10 | 1 |
| UX-12 record, edit, detail and drawer pages (chromium) | — | 1 |
| UX-12 signed-out pages: forgot password and set password (chromium) | — | 1 |
| NFR-10 sign-in page (firefox) | NFR-10 | 1 |
| NFR-10 main pages, a record page and the assistant drawer (firefox) | NFR-10 | 1 |
| UX-12 record, edit, detail and drawer pages (firefox) | — | 1 |
| UX-12 signed-out pages: forgot password and set password (firefox) | — | 1 |

**`frontend/e2e/assistant.spec.ts`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Assistant in en › FR-AI-01..04, 07 streamed answers with links, a saved draft, a provider failure (chromium) | FR-AI-01 | 1 |
| Assistant in bg › FR-AI-01..04, 07 streamed answers with links, a saved draft, a provider failure (chromium) | FR-AI-01 | 1 |
| Assistant in en › FR-AI-01..04, 07 streamed answers with links, a saved draft, a provider failure (firefox) | FR-AI-01 | 1 |
| Assistant in bg › FR-AI-01..04, 07 streamed answers with links, a saved draft, a provider failure (firefox) | FR-AI-01 | 1 |

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

**`frontend/e2e/idle.spec.ts`** (2)

| Test | Requirement | Cases |
|---|---|---|
| FN-05 the idle warning appears in every tab and staying signed in closes it everywhere (chromium) | — | 1 |
| FN-05 the idle warning appears in every tab and staying signed in closes it everywhere (firefox) | — | 1 |

**`frontend/e2e/imports.spec.ts`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Import in en › FR-IMP-01 upload, preview with reasons, import valid rows, roll back (chromium) | FR-IMP-01 | 1 |
| Import in bg › FR-IMP-01 upload, preview with reasons, import valid rows, roll back (chromium) | FR-IMP-01 | 1 |
| Import in en › FR-IMP-01 upload, preview with reasons, import valid rows, roll back (firefox) | FR-IMP-01 | 1 |
| Import in bg › FR-IMP-01 upload, preview with reasons, import valid rows, roll back (firefox) | FR-IMP-01 | 1 |

**`frontend/e2e/integrations.spec.ts`** (8)

| Test | Requirement | Cases |
|---|---|---|
| Integrations in en › FR-INT-01..04 client, key shown once, scoped access, external ID, revocation (chromium) | FR-INT-01 | 1 |
| Integrations in en › FR-INT-07, 12 subscription with secret shown once, test event through the worker, delivery log (chromium) | FR-INT-07 | 1 |
| Integrations in bg › FR-INT-01..04 client, key shown once, scoped access, external ID, revocation (chromium) | FR-INT-01 | 1 |
| Integrations in bg › FR-INT-07, 12 subscription with secret shown once, test event through the worker, delivery log (chromium) | FR-INT-07 | 1 |
| Integrations in en › FR-INT-01..04 client, key shown once, scoped access, external ID, revocation (firefox) | FR-INT-01 | 1 |
| Integrations in en › FR-INT-07, 12 subscription with secret shown once, test event through the worker, delivery log (firefox) | FR-INT-07 | 1 |
| Integrations in bg › FR-INT-01..04 client, key shown once, scoped access, external ID, revocation (firefox) | FR-INT-01 | 1 |
| Integrations in bg › FR-INT-07, 12 subscription with secret shown once, test event through the worker, delivery log (firefox) | FR-INT-07 | 1 |

**`frontend/e2e/journey.spec.ts`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Lead to won in en › FR-LEAD-01..04, FR-OPP-01..05, FR-ACT-01..03 lead → qualify → convert → progress → won (chromium) | FR-LEAD-01, FR-OPP-01, FR-ACT-01 | 1 |
| Lead to won in bg › FR-LEAD-01..04, FR-OPP-01..05, FR-ACT-01..03 lead → qualify → convert → progress → won (chromium) | FR-LEAD-01, FR-OPP-01, FR-ACT-01 | 1 |
| Lead to won in en › FR-LEAD-01..04, FR-OPP-01..05, FR-ACT-01..03 lead → qualify → convert → progress → won (firefox) | FR-LEAD-01, FR-OPP-01, FR-ACT-01 | 1 |
| Lead to won in bg › FR-LEAD-01..04, FR-OPP-01..05, FR-ACT-01..03 lead → qualify → convert → progress → won (firefox) | FR-LEAD-01, FR-OPP-01, FR-ACT-01 | 1 |

**`frontend/e2e/keyboard.spec.ts`** (8)

| Test | Requirement | Cases |
|---|---|---|
| NFR-10 sign in, skip the navigation, create an organization by keyboard (chromium) | NFR-10 | 1 |
| NFR-10 move an opportunity to another stage without dragging (chromium) | NFR-10 | 1 |
| NFR-10 dialogs and the assistant drawer close with Escape and return focus (chromium) | NFR-10 | 1 |
| UX-12 focus indicators have 3:1 contrast with the page (chromium) | — | 1 |
| NFR-10 sign in, skip the navigation, create an organization by keyboard (firefox) | NFR-10 | 1 |
| NFR-10 move an opportunity to another stage without dragging (firefox) | NFR-10 | 1 |
| NFR-10 dialogs and the assistant drawer close with Escape and return focus (firefox) | NFR-10 | 1 |
| UX-12 focus indicators have 3:1 contrast with the page (firefox) | — | 1 |

**`frontend/e2e/layout.spec.ts`** (2)

| Test | Requirement | Cases |
|---|---|---|
| UX-13 Bulgarian at 768 px: no sideways scrolling or cut filter labels (chromium) | — | 1 |
| UX-13 Bulgarian at 768 px: no sideways scrolling or cut filter labels (firefox) | — | 1 |

**`frontend/e2e/leads.spec.ts`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Leads in en › FR-LEAD-01..03 capture, contact, qualify with BANT; disqualify and reopen (chromium) | FR-LEAD-01 | 1 |
| Leads in bg › FR-LEAD-01..03 capture, contact, qualify with BANT; disqualify and reopen (chromium) | FR-LEAD-01 | 1 |
| Leads in en › FR-LEAD-01..03 capture, contact, qualify with BANT; disqualify and reopen (firefox) | FR-LEAD-01 | 1 |
| Leads in bg › FR-LEAD-01..03 capture, contact, qualify with BANT; disqualify and reopen (firefox) | FR-LEAD-01 | 1 |

**`frontend/e2e/opportunities.spec.ts`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Opportunities in en › FR-OPP-01..05 create, move on the board, close lost and won, manager reopens (chromium) | FR-OPP-01 | 1 |
| Opportunities in bg › FR-OPP-01..05 create, move on the board, close lost and won, manager reopens (chromium) | FR-OPP-01 | 1 |
| Opportunities in en › FR-OPP-01..05 create, move on the board, close lost and won, manager reopens (firefox) | FR-OPP-01 | 1 |
| Opportunities in bg › FR-OPP-01..05 create, move on the board, close lost and won, manager reopens (firefox) | FR-OPP-01 | 1 |

**`frontend/e2e/party.spec.ts`** (6)

| Test | Requirement | Cases |
|---|---|---|
| Organizations and contacts in en › FR-PARTY-01..04 create, detect duplicate, add contact, search across scripts, archive (chromium) | FR-PARTY-01 | 1 |
| Organizations and contacts in bg › FR-PARTY-01..04 create, detect duplicate, add contact, search across scripts, archive (chromium) | FR-PARTY-01 | 1 |
| Ownership › FR-AUTH-05 AC1 a sales rep cannot edit an organization owned by someone else (chromium) | FR-AUTH-05 AC1 | 1 |
| Organizations and contacts in en › FR-PARTY-01..04 create, detect duplicate, add contact, search across scripts, archive (firefox) | FR-PARTY-01 | 1 |
| Organizations and contacts in bg › FR-PARTY-01..04 create, detect duplicate, add contact, search across scripts, archive (firefox) | FR-PARTY-01 | 1 |
| Ownership › FR-AUTH-05 AC1 a sales rep cannot edit an organization owned by someone else (firefox) | FR-AUTH-05 AC1 | 1 |

**`frontend/e2e/privacy.spec.ts`** (8)

| Test | Requirement | Cases |
|---|---|---|
| Privacy and sign-in in en › FR-AUTH-07 a rep turns on two-factor sign-in and signs in with a recovery code (chromium) | FR-AUTH-07 | 1 |
| Privacy and sign-in in en › FR-ADM-04 an Admin anonymizes a contact (chromium) | FR-ADM-04 | 1 |
| Privacy and sign-in in bg › FR-AUTH-07 a rep turns on two-factor sign-in and signs in with a recovery code (chromium) | FR-AUTH-07 | 1 |
| Privacy and sign-in in bg › FR-ADM-04 an Admin anonymizes a contact (chromium) | FR-ADM-04 | 1 |
| Privacy and sign-in in en › FR-AUTH-07 a rep turns on two-factor sign-in and signs in with a recovery code (firefox) | FR-AUTH-07 | 1 |
| Privacy and sign-in in en › FR-ADM-04 an Admin anonymizes a contact (firefox) | FR-ADM-04 | 1 |
| Privacy and sign-in in bg › FR-AUTH-07 a rep turns on two-factor sign-in and signs in with a recovery code (firefox) | FR-AUTH-07 | 1 |
| Privacy and sign-in in bg › FR-ADM-04 an Admin anonymizes a contact (firefox) | FR-ADM-04 | 1 |

**`frontend/e2e/reports.spec.ts`** (4)

| Test | Requirement | Cases |
|---|---|---|
| Reports in en › FR-REP-01..03 dashboard for my opportunities, list export, win/loss (chromium) | FR-REP-01 | 1 |
| Reports in bg › FR-REP-01..03 dashboard for my opportunities, list export, win/loss (chromium) | FR-REP-01 | 1 |
| Reports in en › FR-REP-01..03 dashboard for my opportunities, list export, win/loss (firefox) | FR-REP-01 | 1 |
| Reports in bg › FR-REP-01..03 dashboard for my opportunities, list export, win/loss (firefox) | FR-REP-01 | 1 |

**`frontend/e2e/security.spec.ts`** (4)

| Test | Requirement | Cases |
|---|---|---|
| ASVS 14.4 security headers on the app and the API, no server banner (chromium) | — | 1 |
| ASVS 3.4 session cookie flags and no CSP violations on the main pages (chromium) | — | 1 |
| ASVS 14.4 security headers on the app and the API, no server banner (firefox) | — | 1 |
| ASVS 3.4 session cookie flags and no CSP violations on the main pages (firefox) | — | 1 |

**`frontend/e2e/session.spec.ts`** (2)

| Test | Requirement | Cases |
|---|---|---|
| FN-04 an ended session returns to the same page after signing in again (chromium) | — | 1 |
| FN-04 an ended session returns to the same page after signing in again (firefox) | — | 1 |

**`frontend/e2e/shell.spec.ts`** (6)

| Test | Requirement | Cases |
|---|---|---|
| UX-02 sidebar collapses at 1440 px and stays collapsed for the session (chromium) | — | 1 |
| UX-02 navigation drawer and user menu at 768 px by keyboard (chromium) | — | 1 |
| the browser tab names the page (WCAG 2.4.2) (chromium) | — | 1 |
| UX-02 sidebar collapses at 1440 px and stays collapsed for the session (firefox) | — | 1 |
| UX-02 navigation drawer and user menu at 768 px by keyboard (firefox) | — | 1 |
| the browser tab names the page (WCAG 2.4.2) (firefox) | — | 1 |

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

**`frontend/e2e/visual.spec.ts`** (4)

| Test | Requirement | Cases |
|---|---|---|
| visual en › UX-14 signed-out pages in en (visual) | — | 1 |
| visual en › UX-14 pages in en (visual) | — | 1 |
| visual bg › UX-14 signed-out pages in bg (visual) | — | 1 |
| visual bg › UX-14 pages in bg (visual) | — | 1 |

<!-- inventory:end -->
