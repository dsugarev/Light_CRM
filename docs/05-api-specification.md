# 05 — API Specification (Release 1)

Status: Draft v0.12 (updated after Phase 8a, 2026-11-18) · Read together with `01-requirements.md` (requirement IDs) and `02-architecture.md` section 5 (conventions).

This document lists every endpoint the backend must provide in Release 1. The same API serves two kinds of caller: the CRM's own web frontend (users, cookie sessions) and **integrated applications** (Conclusion, ERP and Billing in R1; service accounts with API keys, section 19). It is the reference for implementation, for the authorization matrix test, for the integrating teams, and for review. The FastAPI-generated OpenAPI document remains the machine-readable contract and must match this catalog. An endpoint that is not listed here is not built without first adding it here.

**Machine-readable contract.** A snapshot of the generated OpenAPI 3.1 document is committed at [`api/openapi.json`](api/openapi.json) and checked by CI to match the code. Each operation carries `x-access-level` (the access level wording of this document) and, for integration-accessible operations from Phase 6, `x-required-scope`. The live document is `GET /api/v1/openapi.json`; interactive docs at `/api/docs` outside production.

### Implementation status

| Section | Phase | Status |
|---|---|---|
| 1 Conventions: problem details, request IDs, CSRF, access levels | 0–1 | Built |
| 1.3 Lists: paging, sorting, filters, `q`, `include_archived`, sync mode | 2 | Built (shared machinery, ADR 0017); users and audit-log lists keep their Phase 1 parameters (the users list gained an optional `sort`, UX-08) |
| 2 System and health | 0–1 | Built |
| 3 Authentication and sessions | 1, 8 | Built; two-factor sign-in (FR-AUTH-07) since Phase 8a |
| 4 Current user | 1, 4, 6 | Built; `/me/tasks` since Phase 4b; integration callers (`system`, `scopes`) since Phase 6a |
| 5 Users and roles | 1 | Built |
| 6.1 Application settings | 1, 4 | Built with session timeouts (Phase 1) and the stale-opportunity threshold (Phase 4); further settings added by their phases |
| 6.2 Reference lists | 2–4 | Built; `industries`, `lead-sources`, `disqualification-reasons`, `loss-reasons` registered; `external-systems` since Phase 6a (seeded `conclusion`, `erp`, `billing`) |
| 6.3 Pipelines and stages | 4 | Built (Phase 4a) |
| 7 Organizations | 2–5 | Built; `/export` since Phase 5a; `/leads` and the open-lead count added in Phase 3; `/opportunities`, open-opportunity figures and the archive guard in Phase 4a; `/timeline` in Phase 4b |
| 8 Contacts | 2, 4, 5, 8 | Built; `/timeline` since Phase 4b; `/export` since Phase 5a; GDPR `personal-data` and `anonymize` since Phase 8a |
| 9 Leads | 3–5 | Built; `conversion-preview`, `convert` and `/timeline` since Phase 4b; `/export` since Phase 5a |
| 10 Opportunities and pipeline board | 4, 5 | Built; `/export` since Phase 5a |
| 11 Activities and tasks | 4, 5 | Built (Phase 4b); `/export` since Phase 5a |
| 12 Search | 2–4, 6 | Built for organizations, contacts, leads and opportunities; integration clients get only the types they may read (Phase 6a) |
| 13–14 Reports, exports | 5 | Built (Phase 5a) |
| 15 Data import | 5 | Built (Phase 5b) |
| 16 Audit log | 1, 5 | Built; `/audit-log/export` since Phase 5a |
| 17 AI assistant | 7 | Built: all nine endpoints, the eight read-only tools, streaming, limits and token accounting (Phase 7a); the chat drawer (Phase 7b); off by default (`AI_ENABLED=false`) |
| 18 Rate limits | 1, 6 | Built for sign-in, password endpoints, per user and per integration client (Phase 6a); others with their features |
| 19 Integration API | 6 | Built: API keys (19.2), scopes (19.3), external references and filters (19.4), idempotency (19.5) in Phase 6a; webhooks with the outbox, signing, retries, suspension and the delivery log (19.6, 19.7), the integration guide and collection (19.10) in Phase 6b; the initial profiles as a CLI command (19.9) |

`backend/tests/api/catalog_pending.py` lists every endpoint not yet built; the route catalog test fails if this document and the code disagree.

## 1. General conventions

### 1.1 Base path and format

- Versioned business API: `/api/v1`. Health endpoints: `/api/health/*` (unversioned).
- JSON request and response bodies, UTF-8, `snake_case` field names.
- IDs are UUID strings. Timestamps are ISO 8601 in UTC (`2026-11-17T09:30:00Z`). Dates without time are `YYYY-MM-DD`. Money is a decimal string (`"125000.00"`) with a separate `currency` field, so no precision is lost in JavaScript.
- Breaking changes require `/api/v2`. Adding endpoints, optional request fields or response fields is non-breaking and stays in `v1`; clients must ignore unknown response fields.

### 1.2 Authentication and request headers

Two authentication methods exist, each for one kind of caller. A request carrying both a session cookie and an `Authorization` header is rejected with `400`.

| Caller | Method | Notes |
|---|---|---|
| Web frontend (people) | Session cookie set by `POST /auth/login` (architecture section 7) | CSRF protection applies |
| Integrated applications | `Authorization: Bearer <api_key>` (section 19) | No cookies; CSRF headers not required; scopes apply |

- Every cookie-authenticated mutating request (`POST`, `PUT`, `PATCH`, `DELETE`) must send `X-Requested-With: XMLHttpRequest`; the server also validates `Origin`. Missing or wrong values return `403` with code `auth.csrf_failed`. This applies to every mutating request without an `Authorization` header, including sign-in. Trusted origins: `PUBLIC_URL` plus `CSRF_TRUSTED_ORIGINS` (e.g. the Vite dev server).
- The session cookie is named `session` (`HttpOnly; Secure; SameSite=Strict; Path=/api`, `Max-Age` = remaining absolute lifetime). An unknown, expired or revoked session is treated as anonymous: protected endpoints return `401 auth.session_expired`.
- Integration `POST` requests that create records should send an `Idempotency-Key` header (section 19.5).
- Optional `X-Request-ID` from the client is echoed back; otherwise the server generates one. Every response carries `X-Request-ID`.
- `Accept-Language` is not used for API messages; the backend returns error codes and the frontend translates them.

### 1.3 Lists: pagination, sorting, filtering, search

| Parameter | Meaning | Example |
|---|---|---|
| `page` | 1-based page number, default 1 | `page=2` |
| `page_size` | Default 25, maximum 100 | `page_size=50` |
| `sort` | Comma-separated fields; `-` prefix for descending | `sort=-amount,name` |
| `q` | Free-text search (full-text plus trigram, Cyrillic-aware) | `q=софия` |
| `<field>` | Exact filter; repeat for "any of" | `status=new&status=contacted` |
| `<field>_from`, `<field>_to` | Inclusive range filter for dates and amounts | `expected_close_date_from=2026-12-01` |
| `owner_id=me` | Shortcut for the signed-in user | `owner_id=me` |
| `include_archived` | Include archived records, default `false` | `include_archived=true` |
| `updated_since` | Only records created or changed at or after this timestamp; switches the list to sync mode (below) | `updated_since=2026-11-17T00:00:00Z` |
| `cursor` | Continuation token from `next_cursor`, sync mode only | `cursor=eyJ1IjoiMjAy...` |
| `external_system`, `external_id` | Records linked to an ID in another system (section 19.4) | `external_system=erp&external_id=C-10023` |

List response envelope:

```json
{ "items": [ ... ], "total": 137, "page": 2, "page_size": 25 }
```

**Sync mode.** When `updated_since` is given, the list is ordered by `(updated_at, id)` ascending, `sort` and `page` are ignored, archived and anonymized records are included (so consumers can mirror removals), and the envelope is `{ "items": [...], "next_cursor": "..." | null }`. Clients keep calling with `cursor` until `next_cursor` is `null`, then store the largest `updated_at` seen for the next run. Ordering is stable, so no record is skipped or repeated when data changes during paging. Page size in sync mode defaults to 100 and may be raised to 500. Sync mode is available on organizations, contacts, leads, opportunities and activities.

Each list endpoint documents which fields are sortable and filterable in its OpenAPI description; unknown sort or filter fields return `400` with code `validation.failed`.

Details (as built, ADR 0017):

- Error field codes: `validation.unknown_filter` (field = the parameter name), `validation.unknown_sort`, `validation.less_than_equal` (`page_size` over 100, or over 500 in sync mode), `validation.invalid_cursor` (altered cursor or one from another list), `validation.cursor_requires_updated_since`.
- `sort` accepts several fields; ties are always broken by `id`, so paging is stable. Name sorting uses the folded name, so Cyrillic and Latin sort together.
- `q` matches every whitespace-separated term, each as typed or transliterated (official Bulgarian system), anywhere in the indexed fields; "sofia" finds «София» and «глобал» finds "Global".
- `owner_id` filters accept user IDs and `me`, and may be repeated.
- The sync cursor is opaque: a signed token bound to one list. Rows changed within the last few seconds (`SYNC_SAFETY_LAG_SECONDS`, default 5) are returned on a later call, so no committed change is skipped. A record changed while a client pages is returned again in its new version; consumers keep the newest `updated_at` per `id`.

### 1.4 Create, update, archive

- `POST` on a collection creates and returns `201` with the full record and a `Location` header.
- `PATCH` updates only the fields sent. Leads and opportunities require the current `version` in the body; a mismatch returns `409` with code `conflict.version_mismatch` and the current record in `current`.
- `DELETE` on a business record **archives** it (sets `archived_at`) and returns `204`. `POST /{id}/restore` reverses it. Hard deletion is not exposed, except anonymization for GDPR.
- Lifecycle changes that carry business rules are explicit actions (`POST /leads/{id}/qualify`, `POST /opportunities/{id}/close`) rather than free `PATCH` of a status field. `PATCH` rejects `status`, `stage_id` and `owner_id` changes with code `validation.use_action_endpoint`.

### 1.5 Embedded summaries

Responses embed short summaries of related records so the UI does not need extra calls, for example `"owner": { "id": "...", "full_name": "Ivan Petrov" }` and `"organization": { "id": "...", "name": "Acme EOOD" }`. Requests reference related records by ID only (`owner_id`, `organization_id`).

Organizations, contacts, leads and opportunities also embed their links to other systems:

```json
"external_references": [
  { "system": "erp", "external_id": "C-10023", "url": null, "updated_at": "2026-11-17T12:00:00Z" },
  { "system": "billing", "external_id": "BA-778812", "url": null, "updated_at": "2026-11-17T12:05:00Z" }
]
```

### 1.6 Errors

Errors use RFC 9457 problem details with content type `application/problem+json`:

```json
{
  "type": "https://crm.internal/errors/validation.failed",
  "title": "Validation failed",
  "status": 422,
  "code": "validation.failed",
  "detail": "One or more fields are invalid.",
  "request_id": "0b9c...",
  "errors": [
    { "field": "expected_close_date", "code": "validation.date_in_past" }
  ]
}
```

| HTTP status | Used for |
|---|---|
| 200 / 201 / 202 / 204 | Success: read or action, created, accepted, no content |
| 400 | Malformed request, unknown filter or sort field |
| 401 | Not signed in or session expired |
| 403 | Signed in but not permitted, or CSRF check failed |
| 404 | Record does not exist (also used instead of 403 for records a user may not know about, none in R1 because all users may read all records) |
| 405 | HTTP method not supported on this path |
| 409 | Version conflict, duplicate, or invalid state transition |
| 413 | Upload too large |
| 415 | Unsupported upload type |
| 422 | Field validation failed |
| 423 | Account locked |
| 429 | Rate limit or AI budget exceeded; includes `Retry-After` |
| 500 | Unexpected server error; the body never contains internal details |
| 503 | Dependency unavailable (database not ready, LLM provider down) |

Error codes (stable, used by the frontend for translation; add new codes here when introduced):

| Code | Status | Meaning |
|---|---|---|
| `auth.invalid_credentials` | 401 | Email or password wrong (generic on purpose) |
| `auth.session_expired` | 401 | Session missing, expired or revoked |
| `auth.account_locked` | 423 | Too many failed attempts; `locked_until` included |
| `auth.account_inactive` | 401 | User deactivated (returned as invalid credentials at sign-in) |
| `auth.token_invalid` | 400 | Set or reset password token invalid, used or expired |
| `auth.password_policy` | 422 | Password fails the policy; `errors` lists rules failed (`password.too_short`, `password.too_long`, `password.too_common`) |
| `auth.csrf_failed` | 403 | Missing header or bad origin |
| `auth.mfa_required` | 401 | Password accepted, TOTP code needed (only if MFA enabled); sets the pending-MFA cookie |
| `auth.mfa_code_invalid` | 401 / 422 | Wrong, expired or reused code (401 at `login/mfa`; 422 with field `code` at `mfa/confirm`) |
| `auth.mfa_setup_required` | 403 | An Admin must set up two-factor sign-in first (setting `mfa_required_for_admins`) |
| `auth.mfa_enforced` | 403 | Two-factor sign-in is required for Admins and cannot be turned off |
| `auth.mfa_already_enabled` | 409 | `mfa/setup` or `mfa/confirm` while already on |
| `auth.mfa_not_enabled` | 409 | `mfa/disable` while off, or `mfa/confirm` without `mfa/setup` |
| `contact.anonymized` | 409 | The contact was anonymized and cannot be changed or anonymized again |
| `permission.denied` | 403 | Role or ownership does not allow the action |
| `permission.last_admin` | 409 | The change would leave no active Admin (demote or deactivate the last one) |
| `resource.not_found` | 404 | No such record (also returned for unknown paths) |
| `resource.archived` | 409 | The record is archived; restore it before changing it |
| `request.method_not_allowed` | 405 | HTTP method not supported on this path |
| `server.internal_error` | 500 | Unexpected error; details are only in the server log, under the `request_id` |
| `validation.failed` | 422 | Field-level errors in `errors` (field codes below). Also used with `400` for a malformed body (field `body`, code `validation.json_invalid`) and unknown sort or filter fields |
| `validation.use_action_endpoint` | 422 | Field must be changed through an action endpoint |
| `conflict.version_mismatch` | 409 | Record changed since it was loaded |
| `conflict.duplicate` | 409 | Matches an existing record; `matches` lists them |
| `lead.invalid_transition` | 409 | Status change not allowed from the current status |
| `lead.bant_incomplete` | 409 | Cannot qualify while a BANT item is unknown |
| `lead.not_convertible` | 409 | Lead is not Qualified or is already converted |
| `activity.not_a_task` | 409 | Complete or reopen called on an activity that is not a task |
| `lead.read_only` | 409 | Lead is converted or disqualified; only reopen (disqualified, Manager+) is possible |
| `opportunity.closed` | 409 | Change attempted on a closed opportunity |
| `opportunity.loss_reason_required` | 422 | Lost outcome without a loss reason |
| `opportunity.not_closed` | 409 | Reopen attempted on an opportunity that is not closed |
| `organization.has_open_opportunities` | 409 | Archive attempted while the organization has open opportunities |
| `stage.in_use` | 409 | Stage cannot be removed while in use |
| `stage.required` | 409 | The change would leave the pipeline without an active stage of a type (open, won or lost) |
| `reference.in_use` | 409 | Reference value cannot be removed while in use |
| `import.invalid_file` | 415 | Not a readable XLSX or CSV |
| `import.too_large` | 413 | File exceeds 10 MB |
| `import.invalid_state` | 409 | Import step called out of order |
| `import.has_errors` | 409 | Commit in strict mode with invalid rows |
| `export.too_many_rows` | 422 | Export exceeds the row cap; narrow the filters |
| `rate_limit.exceeded` | 429 | Too many requests |
| `assistant.disabled` | 503 | `AI_ENABLED` is false |
| `assistant.budget_exceeded` | 429 | Daily token budget used up |
| `assistant.provider_unavailable` | 503 | LLM provider error or timeout (in the stream, as an `error` event) |
| `auth.api_key_invalid` | 401 | API key missing, unknown, revoked or expired |
| `auth.client_inactive` | 401 | Integration client deactivated |
| `auth.ip_not_allowed` | 403 | Caller IP outside the client's allowlist |
| `auth.mixed_credentials` | 400 | Both cookie and `Authorization` header sent |
| `api_key.limit` | 409 | The client already has two active keys; revoke one first. `max` included |
| `permission.scope_missing` | 403 | Integration client lacks the scope; `required_scope` included |
| `permission.not_for_integrations` | 403 | Endpoint is not available to integration clients |
| `idempotency.key_reused` | 422 | Same `Idempotency-Key` sent with a different request body |
| `idempotency.in_progress` | 409 | First request with this key is still being processed |
| `external_reference.conflict` | 409 | That external ID is already linked to another record |
| `external_reference.system_mismatch` | 403 | Integration tried to write another system's reference |
| `owner.required` | 422 | Integration-created record has no `owner_id` and the client has no default owner |
| `webhook.url_not_allowed` | 422 | Webhook URL not HTTPS or host not in the allowlist |

**Field error codes** (in `errors[].code`, translated by the frontend): Pydantic validation types as `validation.<type>` (for example `validation.missing`, `validation.string_too_short`, `validation.extra_forbidden`, `validation.int_parsing`, `validation.literal_error`, `validation.value_error`), `validation.json_invalid` (body is not JSON, status 400), `validation.exceeds_absolute` (settings), `password.too_short`, `password.too_long`, `password.too_common`, `password.current_incorrect`, `user.email_taken`, `user.inactive`, `owner.invalid`, `organization.not_found`, `organization.archived`, `organization.registration_checksum` (warning only), `reference.invalid`, `reference.code_taken`, `reference.order_incomplete`, `contact.not_found`, `contact.organization_mismatch`, `lead.bant_unknown`, `stage.not_open` (stage must be an active open stage), `stage.order_incomplete`, `export.unknown_column` (field `columns`, status 400), import mapping and row codes `import.unknown_column`, `import.unknown_field`, `import.field_mapped_twice` (field `mapping.<column>`), `import.required_field` (field `field.<key>`), `import.duplicate_in_file` (field `row`), `organization.ambiguous`, `validation.period` (field `from`, status 400: `from` after `to`), `activity.link_required` (field `links`), `activity.due_required`, `activity.task_only`, `assignee.invalid`, `lead.not_found`, `lead.archived`, `opportunity.not_found`, `opportunity.archived`, `validation.use_action_endpoint`, list errors from section 1.3 (`validation.unknown_filter`, `validation.unknown_sort`, `validation.invalid_cursor`, `validation.cursor_requires_updated_since`, `validation.uuid_parsing`), API keys `api_key.expiry_past` and `api_key.expiry_too_long` (field `expires_at`), `validation.missing` on `external_system` (status 400) when `external_id` or `has_external_reference` is sent without it, `validation.string_too_long` on `Idempotency-Key` (status 422). Field names are the request body or query field names.

### 1.7 Access levels used in the tables

| Level | Who |
|---|---|
| Public | No session required |
| Signed-in | Any active user: Admin, Sales Manager, Sales Rep, Viewer |
| Signed-in (own only) | Any active user, for their own data only; another user's returns `404 resource.not_found` (assistant conversations) |
| Contributor | Admin, Sales Manager, Sales Rep |
| Owner+ | Admin, Sales Manager, or the Sales Rep who owns the record |
| Owner+ (owner = activity owner; assignee may update a task) | Admin, Sales Manager, the Sales Rep who owns the activity, or the assignee of a task |
| Owner+ or assignee | Admin, Sales Manager, the Sales Rep who owns the task, or its assignee |
| Manager+ | Admin, Sales Manager |
| Admin | Admin only |
| Integration: `scope` | An integration client holding that scope (section 19.3) |
| Signed-in; Integration: read scope of `{resource}` | Any active user; an integration client holding the read scope of the record type in the path (`organizations:read` for `/organizations/...`) |
| Signed-in; Integration: read scope of the resolved type | Any active user; an integration client holding any record read scope, and the read scope of the record type the reference resolves to (otherwise `403 permission.scope_missing`) |
| Admin; Integration: `external-references:write` and `{system}` equals the client's system | Admin; an integration client with that scope, for references of its own system only (otherwise `403 external_reference.system_mismatch`) |

Every endpoint below maps to exactly one access level for people. Whether an integration client may call it, and with which scope, is defined only in section 19.3; endpoints not listed there return `403 permission.not_for_integrations` to integration clients; so do the Public endpoints (sign-in, password set and reset) when called with an API key. The authorization matrix test (test strategy section 3) is generated from these tables and section 19.3.

## 2. System and health

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/health/live` | Process is running; no dependencies checked | Public | NFR-08 |
| GET | `/api/health/ready` | Database reachable and migrations at head | Public | NFR-08 |
| GET | `/api/v1/system/info` | App version, build, supported locales, feature flags (`ai_enabled`, `mfa_available`) for the frontend | Signed-in | — |
| GET | `/api/v1/openapi.json` | OpenAPI document (includes the bearer security scheme and the scope required by each operation) | Signed-in or any integration client; Public when `ENV` is not `production` | FR-INT-10 |
| GET | `/api/docs` | Interactive API documentation | Only when `ENV` is not `production` | — |

Health responses contain status only, never version numbers, hostnames or configuration.

## 3. Authentication and sessions

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| POST | `/api/v1/auth/login` | Sign in with email and password; sets the session cookie | Public | FR-AUTH-01 |
| POST | `/api/v1/auth/login/mfa` | Complete sign-in with a TOTP code (or a recovery code) when MFA is enabled; needs the pending-MFA cookie set by `login` | Public | FR-AUTH-07 (S) |
| POST | `/api/v1/auth/logout` | End the current session and clear the cookie | Signed-in | FR-AUTH-04 |
| POST | `/api/v1/auth/password/set` | Set a password using a one-time token (new user or reset) | Public | FR-AUTH-02, 03 |
| GET | `/api/v1/auth/password/token/{token}` | Check a token is valid before showing the form; returns email only | Public | FR-AUTH-02 |
| POST | `/api/v1/auth/password/forgot` | Request a reset email; always returns `202` whether or not the email exists | Public | FR-AUTH-02 |
| POST | `/api/v1/auth/password/change` | Change own password (current + new); revokes other sessions | Signed-in | FR-AUTH-04 |
| POST | `/api/v1/auth/mfa/setup` | Start TOTP enrolment; returns secret and provisioning URI | Signed-in | FR-AUTH-07 (S) |
| POST | `/api/v1/auth/mfa/confirm` | Confirm enrolment with a code; returns recovery codes once | Signed-in | FR-AUTH-07 (S) |
| POST | `/api/v1/auth/mfa/disable` | Disable own MFA (requires password); not allowed where enforced | Signed-in | FR-AUTH-07 (S) |

Rules:

- Auth endpoints are rate limited per IP (section 18); the account itself is locked after 5 consecutive failed passwords for 15 minutes (`LOGIN_MAX_FAILED_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`). While locked, sign-in returns `423 auth.account_locked` with `locked_until`, even with the right password. Unknown emails, wrong passwords, deactivated users and service users all return the same `401 auth.invalid_credentials`. Every attempt is audited (`auth.login_succeeded`, `auth.login_failed` with a reason, `auth.account_locked`).
- **One-time links** have the form `{PUBLIC_URL}/set-password#token=<token>`. The token travels in the URL fragment, which browsers do not send to servers; the SPA reads it and calls `GET /auth/password/token/{token}` (response `{ "email", "purpose": "set" | "reset" }`) and `POST /auth/password/set` (`{ "token", "password" }` → `204`). Links for new users last 72 hours, reset links 2 hours (`PASSWORD_SET_TOKEN_HOURS`, `PASSWORD_RESET_TOKEN_HOURS`); a token works once and a new link voids older unused ones. Setting a password clears any lockout and ends all of the user's sessions. Invalid, used or expired tokens return `400 auth.token_invalid`.
- `forgot` (`{ "email" }`) always returns `202`. It sends a reset email only when SMTP is configured and the email belongs to an active local user; without SMTP it does nothing, and the Admin reset flow in section 5 is the fallback.
- `password/change` (`{ "current_password", "new_password" }` → `204`): a wrong current password returns `422 validation.failed` with field `current_password` / code `password.current_incorrect`; all other sessions of the user end, the current one stays.
- Password policy failures return `422 auth.password_policy` with field codes `password.too_short` (< 12), `password.too_long` (> 128), `password.too_common` (in the bundled common-password list, case-insensitive).
- `logout` returns `204` and clears the cookie.
- **Two-factor sign-in (FR-AUTH-07, as built in Phase 8a).** With MFA on, a correct password returns `401 auth.mfa_required` and sets `mfa_pending` (HMAC-signed, 5 minutes, `HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth/login`); no session exists yet. `POST /auth/login/mfa` (`{ "code" }`, a 6-digit TOTP code or a recovery code `xxxxx-xxxxx`) then answers like `login`. A missing, forged or expired pending cookie returns `401 auth.session_expired`; a wrong or reused code `401 auth.mfa_code_invalid` and counts towards the lockout. Codes are valid one 30-second step either side of now, each once.
- `mfa/setup` → `{ "secret", "provisioning_uri" }` (otpauth URI for a QR code; a new call replaces the pending secret). `mfa/confirm` (`{ "code" }`) → `{ "recovery_codes": [10 codes] }`, shown once. `mfa/disable` (`{ "password" }`) → `204`; a wrong password is `422` with field `password` / `password.current_incorrect`. Audit actions: `user.mfa_enabled`, `user.mfa_disabled`, `user.mfa_recovery_code_used`, `user.mfa_reset` (CLI); `auth.login_succeeded` details include `mfa`.
- **Enforcement.** When the setting `mfa_required_for_admins` is on, an Admin without MFA can call only `GET /me`, `GET /system/info`, `POST /auth/logout`, `/auth/mfa/setup` and `/auth/mfa/confirm`; everything else returns `403 auth.mfa_setup_required`. `GET /me` adds `mfa_enabled` and `mfa_setup_required`. Operators reset a lost device with `python -m app.cli reset-mfa --email …`.

Login request and response:

```json
// POST /api/v1/auth/login
{ "email": "ivan.petrov@example.bg", "password": "••••••••••••" }

// 200 OK  (Set-Cookie: session=...; HttpOnly; Secure; SameSite=Strict; Path=/api)
{ "user": { "id": "...", "full_name": "Ivan Petrov", "role": "sales_rep", "locale": "bg" } }
```

## 4. Current user

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/me` | Profile, role, locale, and a `permissions` list the UI uses for its `can()` helper. For an integration client: `principal_type: "integration"`, client name, system code and granted scopes (useful as a connection test) | Signed-in or any integration client | FR-AUTH-05, FR-INT-03 |
| PATCH | `/api/v1/me` | Update own `full_name`, `locale` | Signed-in | FR-I18N-01 |
| GET | `/api/v1/me/sessions` | Own active sessions (created, last seen, user agent, current flag) | Signed-in | FR-AUTH-04 |
| DELETE | `/api/v1/me/sessions/{session_id}` | Revoke one of own sessions | Signed-in | FR-AUTH-04 |
| GET | `/api/v1/me/tasks` | Own open tasks, overdue first; filter `include_done` | Signed-in | FR-ACT-02 |

```json
// GET /api/v1/me  (user)
{ "principal_type": "user", "id": "...", "email": "ivan.petrov@example.bg", "full_name": "Ivan Petrov",
  "role": "sales_rep", "locale": "bg",
  "permissions": ["data.export", "records.create", "records.edit_own", "records.read"],
  "system": null, "scopes": [],
  "session": { "idle_timeout_minutes": 480, "expires_at": "2026-11-25T09:00:00Z" } }

// GET /api/v1/me  (integration client, Phase 6a)
{ "principal_type": "integration", "id": "<service user id>", "email": "erp-3f9c1a2b7d4e@integration.invalid",
  "full_name": "ERP (integration)", "role": "integration", "locale": "en", "permissions": [],
  "system": "erp", "scopes": ["external-references:write", "organizations:read"] }
```

Permission codes (derived from the role; the UI uses them only to hide controls): `records.read`, `records.create`, `records.edit_own`, `records.edit_any`, `records.reassign`, `records.restore`, `data.export`, `data.import`, `users.manage`, `settings.manage`, `audit.read`. `PATCH /me` accepts only `full_name` and `locale` (`en` | `bg`); other fields return `422`. `GET /me/sessions` returns `[{ "id", "created_at", "last_seen_at", "expires_at", "ip", "user_agent", "current" }]`; revoking a session that is not the caller's returns `404`.

`session` (added after Release 1 for the idle-timeout warning, FN-05; additive): for a signed-in user, the current setting `idle_timeout_minutes` and the session's absolute `expires_at`; `null` for integration clients. Any request (including `GET /me` itself) counts as activity; the server records it at most once a minute, so a client should count the idle time from one minute before its own last request.

## 5. Users and roles (administration)

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/users/lookup` | Active human users as `{id, full_name, email}` for owner and assignee pickers; supports `q` and `email`. Service users of integration clients are never listed | Signed-in | FR-LEAD-06 |
| GET | `/api/v1/users` | Full user list with role, status, last sign-in, lock state | Admin | FR-ADM-01 |
| POST | `/api/v1/users` | Create a user; returns the user and a one-time set-password link | Admin | FR-AUTH-02, FR-ADM-01 |
| GET | `/api/v1/users/{user_id}` | User detail | Admin | FR-ADM-01 |
| PATCH | `/api/v1/users/{user_id}` | Change name, email, role, locale | Admin | FR-ADM-01 |
| POST | `/api/v1/users/{user_id}/deactivate` | Deactivate and revoke all sessions; records stay | Admin | FR-ADM-01 |
| POST | `/api/v1/users/{user_id}/activate` | Reactivate | Admin | FR-ADM-01 |
| POST | `/api/v1/users/{user_id}/password-reset` | Issue a reset link (returned to the Admin, emailed if SMTP is set) | Admin | FR-ADM-01 |
| POST | `/api/v1/users/{user_id}/unlock` | Clear a lockout | Admin | FR-AUTH-01 |
| DELETE | `/api/v1/users/{user_id}/sessions` | Revoke all of a user's sessions | Admin | FR-AUTH-04 |
| GET | `/api/v1/roles` | Roles with their permission lists (read-only in R1) | Admin | FR-AUTH-05 |

An Admin cannot deactivate themselves (`403 permission.denied`) or remove the last active Admin, by deactivation or role change (`409 permission.last_admin`).

Payloads:

```json
// POST /api/v1/users   (role: admin | sales_manager | sales_rep | viewer; locale defaults to "en")
{ "email": "maria.ivanova@example.bg", "full_name": "Maria Ivanova", "role": "sales_rep", "locale": "bg" }

// 201 Created, Location: /api/v1/users/{id}
{ "user": { "id": "...", "email": "maria.ivanova@example.bg", "full_name": "Maria Ivanova",
            "role": "sales_rep", "locale": "bg", "user_type": "human", "is_active": true,
            "is_locked": false, "locked_until": null, "last_login_at": null,
            "created_at": "...", "updated_at": "..." },
  "set_password": { "url": "https://crm.internal/set-password#token=...",
                    "expires_at": "2026-11-20T09:00:00Z", "emailed": false } }
```

- Emails are unique case-insensitively and stored in lower case; a duplicate returns `409 conflict.duplicate` with field `email` / code `user.email_taken` and `matches`.
- `GET /users` filters: `q` (name or email), `role`, `is_active`, `page`, `page_size`; ordered by name unless `sort` is given: one of `name`, `email`, `role`, `last_login_at`, with a leading `-` for descending (users who never signed in come last either way; ties by name). Any other `sort` value returns `422`. Service users are never listed.
- `POST /users/{id}/password-reset` returns `{ "url", "expires_at", "emailed" }` (a set link if the user never had a password); for a deactivated user it returns `422` with field `user_id` / code `user.inactive`.
- `PATCH /users/{id}` with a changed role is audited as `user.role_changed`, other changes as `user.updated`, both with before and after values.
- `GET /roles` returns `[{ "code", "name", "permissions": [...] }]` for the four human roles.

## 6. Settings and reference data

### 6.1 Application settings

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/settings` | Configurable values: session timeouts, stale-opportunity days, AI rate limit and daily budget, MFA enforcement for Admins | Admin | FR-AUTH-04, FR-OPP-06, FR-AI-08 |
| PATCH | `/api/v1/settings` | Update settings; audited | Admin | same |

Settings present so far (later phases add theirs; unknown fields return `422`):

| Field | Default | Range | Phase |
|---|---|---|---|
| `session_idle_timeout_minutes` | 480 (8 h) | 15–1440, not above the absolute timeout | 1 |
| `session_absolute_timeout_minutes` | 10080 (7 days) | 60–43200 | 1 |
| `stale_opportunity_days` | 14 | 1–365 | 4 |
| `mfa_required_for_admins` | false | boolean | 8 |

Changes take effect within 30 seconds on every backend process and are audited as `settings.updated` with before and after values.

Secrets (API keys, SMTP passwords) are never readable or writable through the API; they come from the environment only.

### 6.2 Reference lists

One uniform set of endpoints serves every configurable list. `{list}` is one of `lead-sources`, `disqualification-reasons`, `loss-reasons`, `industries`, `external-systems`. The `external-systems` list is seeded with `conclusion`, `erp` and `billing`; its `code` is the value used in `external_system` filters, external references and integration clients. Each item has `id`, `code`, `name_en`, `name_bg`, `position`, `is_active`.

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/reference/{list}` | List values; `include_inactive=true` for administration | Signed-in | FR-ADM-02 |
| POST | `/api/v1/reference/{list}` | Add a value | Admin | FR-ADM-02 |
| PATCH | `/api/v1/reference/{list}/{item_id}` | Rename, activate, deactivate | Admin | FR-ADM-02 |
| PUT | `/api/v1/reference/{list}/order` | Reorder; body is the full ordered list of IDs | Admin | FR-ADM-02 |
| DELETE | `/api/v1/reference/{list}/{item_id}` | Delete only if never used; otherwise `409 reference.in_use` (deactivate instead) | Admin | FR-ADM-02 |

New lists in later releases are added by extending the allowed `{list}` values, not by new endpoint shapes.

As built: `lead-sources` (seeded: campaign, inbound, referral, event, cold_outreach, partner, other) and `disqualification-reasons` (seeded: no_budget, no_need, no_decision_maker, bad_timing, chose_competitor, unreachable, duplicate, outside_target, other), both in English and Bulgarian, since Phase 3. `industries` is available (seeded with 14 values in English and Bulgarian: telecommunications, IT and software, finance and banking, public sector, healthcare, manufacturing, retail and wholesale, energy and utilities, transport and logistics, construction and real estate, education, hospitality and tourism, media, other). `loss-reasons` is seeded with price, chose_competitor, no_budget, no_decision (no decision or project stopped), timing, solution_fit, other, in English and Bulgarian, since Phase 4. Other names return `404`.

- `POST` body `{ "code", "name_en", "name_bg", "is_active" }`; `code` is `^[a-z0-9_]{1,50}$` and unique in the list (`409 conflict.duplicate`, field `code` / `reference.code_taken`); the value goes to the end of the order. Returns `201` with `Location`.
- `PATCH` body `{ "name_en"?, "name_bg"?, "is_active"? }`; the code is permanent.
- `PUT /order` body: a JSON array of every item ID exactly once (`422`, field `body` / `reference.order_incomplete` otherwise); returns the reordered list.
- `GET` returns active values ordered by `position` (all with `include_inactive=true`). Records referencing an inactive value keep it; new references must use active values (`422`, field e.g. `industry_id` / `reference.invalid`).
- Changes are audited as `reference.created|updated|reordered|deleted` with entity type `industry` (etc.) and `details.list`.

### 6.3 Pipelines and stages

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/pipelines` | Pipelines (one in R1) with their stages in order | Signed-in | FR-OPP-02 |
| GET | `/api/v1/pipelines/{pipeline_id}` | One pipeline with stages | Signed-in | FR-OPP-02 |
| POST | `/api/v1/pipelines/{pipeline_id}/stages` | Add a stage: name (en/bg), default probability, type | Admin | FR-OPP-02 |
| PATCH | `/api/v1/pipelines/{pipeline_id}/stages/{stage_id}` | Rename, change probability, activate or deactivate | Admin | FR-OPP-02 |
| PUT | `/api/v1/pipelines/{pipeline_id}/stages/order` | Reorder stages | Admin | FR-OPP-02 |
| DELETE | `/api/v1/pipelines/{pipeline_id}/stages/{stage_id}` | Delete an unused stage; `409 stage.in_use` otherwise | Admin | FR-OPP-02 AC1 |

Creating additional pipelines is out of scope for R1; the paths are already pipeline-scoped so it can be added without change.

Rules (as built, Phase 4a):

- Seeded default pipeline "Sales pipeline" with six stages (English / Bulgarian, default probability, type): Prospecting / Проучване 10 open; Qualification / Квалификация 25 open; Solution & Proposal / Решение и оферта 50 open; Negotiation / Преговори 75 open; Closed Won / Спечелена 100 won; Closed Lost / Загубена 0 lost.
- Stage resource: `{ id, name_en, name_bg, position, default_probability, stage_type, is_active }`; `stage_type` is `open | won | lost`. Every write returns the whole pipeline.
- `POST …/stages` body `{ name_en, name_bg, default_probability (0–100), stage_type }`, added at the end; returns `201`. `PATCH` body `{ name_en?, name_bg?, default_probability?, is_active? }`; the type is permanent. `PUT …/order` body: every stage ID of the pipeline once (`422`, field `body` / `stage.order_incomplete` otherwise).
- A stage referenced by an opportunity or its stage history cannot be deleted (`409 stage.in_use`); deactivate it instead. Deactivating or deleting the last active stage of a type returns `409 stage.required` with `stage_type`. Inactive stages keep their opportunities; new opportunities, moves and reopens use active stages only.
- Changing a stage's default probability does not change existing opportunities.
- Audited as `pipeline_stage.created|updated|reordered|deleted`.
- `GET` endpoints are open to integration clients with `reference:read`.

## 7. Organizations

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/organizations` | List and search. Filters: `owner_id`, `industry_id`, `city`, `country`, `size_band`. Sort: `name`, `created_at`, `updated_at` | Signed-in | FR-PARTY-04 |
| POST | `/api/v1/organizations` | Create. Returns `409 conflict.duplicate` with `matches` unless `"confirm_duplicate": true` is sent | Contributor | FR-PARTY-01 |
| GET | `/api/v1/organizations/duplicate-check` | Check `name` and/or `registration_number` before saving; returns possible matches | Signed-in | FR-PARTY-01 AC1 |
| GET | `/api/v1/organizations/{org_id}` | Detail with counts of contacts, open leads, open opportunities and open pipeline value | Signed-in | FR-PARTY-03 |
| PATCH | `/api/v1/organizations/{org_id}` | Update fields, including `owner_id` (owner change requires Manager+) | Owner+ | FR-PARTY-01 |
| DELETE | `/api/v1/organizations/{org_id}` | Archive; blocked with `409` while it has open opportunities | Owner+ | FR-PARTY-01 |
| POST | `/api/v1/organizations/{org_id}/restore` | Restore from archive | Manager+ | FR-PARTY-01 |
| GET | `/api/v1/organizations/{org_id}/contacts` | Contacts of this organization (list conventions apply) | Signed-in | FR-PARTY-03 |
| GET | `/api/v1/organizations/{org_id}/leads` | Leads linked to this organization | Signed-in | FR-PARTY-03 |
| GET | `/api/v1/organizations/{org_id}/opportunities` | Opportunities of this organization | Signed-in | FR-PARTY-03 |
| GET | `/api/v1/organizations/{org_id}/timeline` | Merged timeline for the organization and its contacts, leads and opportunities | Signed-in | FR-ACT-03 |
| GET | `/api/v1/organizations/export` | Export the filtered list (section 14) | Signed-in | FR-REP-02 |

Organization resource (response; `GET /{id}` adds `counts`):

```json
{ "id": "...", "name": "Акме ЕООД", "registration_number": "123456786", "vat_number": "BG123456786",
  "industry": { "id": "...", "code": "telecommunications", "name_en": "Telecommunications", "name_bg": "Телекомуникации" },
  "size_band": "10-49", "website": "https://acme.example",
  "address_line": "бул. Витоша 1", "postal_code": "1000", "city": "София", "country": "BG",
  "owner": { "id": "...", "full_name": "Ivan Petrov" }, "notes": null,
  "created_at": "...", "updated_at": "...", "created_by": { "id": "...", "full_name": "Ivan Petrov" },
  "archived_at": null,
  "warnings": [ { "field": "registration_number", "code": "organization.registration_checksum" } ],
  "counts": { "contacts": 2, "open_leads": 0, "open_opportunities": 0, "open_pipeline_value": "0.00", "currency": "EUR" } }
```

Rules (as built):

- Fields: `name` (required, ≤ 200), `registration_number` (EIK/UIC, 9 or 13 digits, spaces ignored), `vat_number` (`BG` + 9–10 digits, stored upper case without spaces), `industry_id` (active industry), `size_band` (`1-9`, `10-49`, `50-249`, `250+`), `website` (`http(s)://…`), `address_line`, `postal_code`, `city`, `country` (ISO 3166-1 alpha-2, default `BG`), `owner_id`, `notes` (≤ 5000). Unknown fields return `422`. In `PATCH`, a field sent as `null` is cleared; fields not sent are unchanged.
- A wrong EIK check digit does not block saving; the response lists it in `warnings`.
- **Duplicates** (FR-PARTY-01 AC1): create, and a `PATCH` that changes `name` or `registration_number`, return `409 conflict.duplicate` with `matches` when another organization (archived ones included) has the same registration number or the same name key. The key ignores script (Cyrillic/Latin), case, punctuation and the legal form, so «Акме ЕООД» and "ACME e.o.o.d." match. Send `"confirm_duplicate": true` to save anyway. `duplicate-check` (`name`, `registration_number` query parameters) additionally returns similar names. Each match: `{ id, name, registration_number, city, archived, reason }` with `reason` `registration_number | name | similar_name`.
- **Ownership**: the owner defaults to the creator. Sales Reps may only own their own records: setting someone else as owner, on create or update, needs Manager+ (`403 permission.denied`). The owner must be an active person (`422`, field `owner_id` / `owner.invalid`). Owner changes are audited as `organization.owner_changed`.
- Archived records cannot be changed (`409 resource.archived`) until restored. Archiving is refused while the organization has open opportunities (`409 organization.has_open_opportunities`, Phase 4).
- Audit actions: `organization.created`, `organization.updated`, `organization.owner_changed`, `organization.archived`, `organization.restored`, with before and after values.
- List filters: `owner_id` (repeatable, `me`), `industry_id`, `city` (case-insensitive), `country`, `size_band` (all repeatable); `q` searches name (both scripts), registration and VAT numbers, city and website.

## 8. Contacts

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/contacts` | List and search. Filters: `organization_id`, `owner_id`. Sort: `last_name`, `created_at` | Signed-in | FR-PARTY-04 |
| POST | `/api/v1/contacts` | Create; duplicate check on email | Contributor | FR-PARTY-02 |
| GET | `/api/v1/contacts/{contact_id}` | Detail | Signed-in | FR-PARTY-02 |
| PATCH | `/api/v1/contacts/{contact_id}` | Update | Owner+ | FR-PARTY-02 |
| DELETE | `/api/v1/contacts/{contact_id}` | Archive | Owner+ | FR-PARTY-02 |
| POST | `/api/v1/contacts/{contact_id}/restore` | Restore | Manager+ | FR-PARTY-02 |
| GET | `/api/v1/contacts/{contact_id}/timeline` | Activities and events for the contact | Signed-in | FR-ACT-03 |
| GET | `/api/v1/contacts/{contact_id}/personal-data` | GDPR export of all personal data held about the contact (JSON download); audited | Admin | FR-ADM-04 |
| POST | `/api/v1/contacts/{contact_id}/anonymize` | Irreversibly anonymize; body must contain `"confirm": "ANONYMIZE"`; audited | Admin | FR-ADM-04 |
| GET | `/api/v1/contacts/export` | Export the filtered list | Signed-in | FR-REP-02 |

Ownership of a contact follows its organization; a contact without an organization is owned by its creator.

Contact resource (response):

```json
{ "id": "...", "first_name": "Мария", "last_name": "Иванова", "full_name": "Мария Иванова",
  "job_title": "CTO", "email": "m.ivanova@acme.example", "phone": "+359 2 000 0000", "preferred_locale": "bg",
  "organization": { "id": "...", "name": "Акме ЕООД" }, "owner": { "id": "...", "full_name": "Ivan Petrov" },
  "notes": null, "created_at": "...", "updated_at": "...", "created_by": { "id": "...", "full_name": "..." },
  "archived_at": null, "anonymized_at": null }
```

**GDPR (FR-ADM-04, as built in Phase 8a; ADR 0027).** `personal-data` returns a JSON attachment (`Content-Disposition: attachment; filename="contact-<id>-personal-data.json"`, `Cache-Control: no-store`) with `generated_at`, `contact` (the contact resource) and sections from the other modules: `leads` (linked, or with the same email), `opportunities_as_primary_contact`, `activities` (linked), `activities_mentioning_the_contact` and `assistant_chats_mentioning_the_contact` (free text that mentions the name or email, for manual review), `ids_in_other_systems`, and `audit_log` (number of entries, kept). Audited as `contact.personal_data_exported`. `anonymize` (`{ "confirm": "ANONYMIZE" }`, anything else `422`) sets the names to `Anonymized` / `#<last 6 hex digits of the ID>`, clears email, phone, job title, preferred language and notes, sets `anonymized_at`, and clears contact name, email and phone on leads linked to the contact or with its email (each audited as `lead.updated` with `details.reason = "contact_anonymized"`); it returns the contact. Organization, opportunities and activities stay. The audit entry `contact.anonymized` holds only the result; earlier audit entries are kept unchanged. Changing or anonymizing an anonymized contact returns `409 contact.anonymized`. Both endpoints are Admin only (`gdpr.manage` in `/me` permissions).

Rules (as built): `first_name` and `last_name` required (≤ 100); `email` stored in lower case; `preferred_locale` `en | bg`; `organization_id` must exist and not be archived (`422`, field `organization_id` / `organization.not_found` or `organization.archived`). A contact whose email already exists returns `409 conflict.duplicate` with `matches` (`reason: "email"`) unless `confirm_duplicate`. `owner` is derived (organization owner, else creator), and Owner+ edit rights follow it. Archived contacts cannot be changed (`409 resource.archived`). List filters: `organization_id`, `owner_id` (`me`); `q` searches names (both scripts), email, phone and job title. Audit actions: `contact.created`, `contact.updated`, `contact.archived`, `contact.restored`.

## 9. Leads

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/leads` | List and search. Filters: `status`, `owner_id`, `source_id`, `created_at_from/to`, `fits_target_profile`. Sort: `created_at`, `estimated_value`, `qualification_score`, `company_name` | Signed-in | FR-LEAD-05 |
| POST | `/api/v1/leads` | Capture a lead; status starts as `new`; owner defaults to the caller | Contributor | FR-LEAD-01 |
| GET | `/api/v1/leads/{lead_id}` | Detail including BANT, score, links to organization, contact and converted opportunity | Signed-in | FR-LEAD-01, 03 |
| PATCH | `/api/v1/leads/{lead_id}` | Update fields and BANT items; requires `version`; rejected on converted or disqualified leads | Owner+ | FR-LEAD-01, 03 |
| DELETE | `/api/v1/leads/{lead_id}` | Archive | Owner+ | — |
| POST | `/api/v1/leads/{lead_id}/restore` | Restore | Manager+ | — |
| POST | `/api/v1/leads/{lead_id}/assign` | Change owner. Body `{ "owner_id", "version" }`. A Sales Rep may only assign to themselves | Contributor (rules in service) | FR-LEAD-06 |
| POST | `/api/v1/leads/{lead_id}/mark-contacted` | `new` → `contacted` | Owner+ | FR-LEAD-02 |
| POST | `/api/v1/leads/{lead_id}/qualify` | → `qualified`; `409 lead.bant_incomplete` if any BANT item is unknown | Owner+ | FR-LEAD-02, 03 AC1 |
| POST | `/api/v1/leads/{lead_id}/disqualify` | → `disqualified`. Body `{ "reason_id", "note", "version" }` | Owner+ | FR-LEAD-02 AC1 |
| POST | `/api/v1/leads/{lead_id}/reopen` | `disqualified` → `contacted` | Manager+ | FR-LEAD-02 AC2 |
| GET | `/api/v1/leads/{lead_id}/conversion-preview` | Suggested organization and contact matches (duplicate check) to show before converting | Owner+ | FR-LEAD-04 |
| POST | `/api/v1/leads/{lead_id}/convert` | Convert in one transaction (see below) | Owner+ | FR-LEAD-04 |
| GET | `/api/v1/leads/{lead_id}/timeline` | Activities and system events for the lead | Signed-in | FR-ACT-03 |
| GET | `/api/v1/leads/export` | Export the filtered list | Signed-in | FR-REP-02 |

Allowed status transitions (anything else returns `409 lead.invalid_transition`):

```
new ──> contacted ──> qualified ──> converted
 │          │             │
 └──────────┴─────────────┴──> disqualified ──(reopen, Manager+)──> contacted
```

Lead resource (response):

```json
{
  "id": "0193...",
  "title": "Fibre connectivity for 3 branches",
  "company_name": "Acme EOOD",
  "contact_name": "Maria Ivanova",
  "email": "m.ivanova@acme.example",
  "phone": "+359 2 000 0000",
  "source": { "id": "...", "code": "inbound", "name": "Inbound inquiry" },
  "status": "contacted",
  "description": "...",
  "estimated_value": "48000.00",
  "currency": "EUR",
  "owner": { "id": "...", "full_name": "Ivan Petrov" },
  "qualification": {
    "budget":    { "status": "yes",     "note": "Approved for 2027" },
    "authority": { "status": "partial", "note": "IT director, CFO signs" },
    "need":      { "status": "yes",     "note": "" },
    "timeline":  { "status": "unknown", "note": "" },
    "fits_target_profile": true,
    "score": 63
  },
  "organization": null,
  "contact": null,
  "converted_opportunity": null,
  "disqualification": null,
  "created_at": "2026-11-17T09:30:00Z",
  "updated_at": "2026-11-17T10:02:11Z",
  "created_by": { "id": "...", "full_name": "Ivan Petrov" },
  "archived_at": null,
  "version": 4
}
```

Conversion request and response:

```json
// POST /api/v1/leads/{lead_id}/convert
{
  "version": 7,
  "organization": { "existing_id": null, "new": { "name": "Acme EOOD", "registration_number": "123456789" } },
  "contact": { "existing_id": null, "new": { "first_name": "Maria", "last_name": "Ivanova", "email": "m.ivanova@acme.example" } },
  "opportunity": {
    "name": "Acme – branch connectivity",
    "amount": "48000.00",
    "expected_close_date": "2027-02-28",
    "stage_id": "...",
    "owner_id": "..."
  }
}

// 201 Created
{ "lead": { ...status "converted"... }, "organization": { ... }, "contact": { ... }, "opportunity": { ... } }
```

Exactly one of `existing_id` and `new` is set for organization; `contact` may be `null`. Any failure rolls back the whole conversion.

Rules (as built in Phase 3; conversion in Phase 4b, see below):

- **Capture** (`POST`): `title` and `company_name` are required (≤ 200); optional `contact_name`, `email` (stored lower case), `phone`, `source_id` (active lead source), `description` (≤ 5000), `estimated_value` (decimal string or number, ≥ 0, 2 decimals; returned as a string with `currency: "EUR"`), `organization_id` and `contact_id` (links to existing, non-archived records; a contact of another organization returns `422`, field `contact_id` / `contact.organization_mismatch`), `owner_id` (a Sales Rep may only name themselves), and an optional `qualification` object. Status starts as `new`.
- **BANT** (`qualification`): `budget`, `authority`, `need`, `timeline`, each `{ "status": "unknown" | "no" | "partial" | "yes", "note" }`, plus `fits_target_profile`. In requests every part is optional and only the parts sent change. **Score** = yes 25 + partial 12.5 per item, no/unknown 0, rounded half up (0–100; the example above, yes/partial/yes/unknown, is 63). The fit flag does not change the score. The score is stored, so lists sort by it.
- **`PATCH`** requires `version`. A stale version returns `409 conflict.version_mismatch` with the current lead in `current`; a change that alters nothing keeps the version. `status` and `owner_id` are refused with `422 validation.use_action_endpoint`. Converted or disqualified leads return `409 lead.read_only`; archived ones `409 resource.archived`.
- **Actions** take `{ "version" }` (plus the fields below) and return the lead with an incremented version: `mark-contacted` (new → contacted), `qualify` (contacted → qualified; `409 lead.bant_incomplete` with one `errors` entry per unknown item, field `qualification.<item>` / `lead.bant_unknown`), `disqualify` (`{ reason_id, note?, version }` from new, contacted or qualified; `reason_id` must be an active disqualification reason), `reopen` (Manager+, disqualified → contacted; clears the disqualification). Any other change returns `409 lead.invalid_transition` with `status` and `action`.
- **Assign** (`{ owner_id, version }`): a Sales Rep may only take a lead for themselves, including one owned by another rep (owner decision, Phase 3); Managers+ assign to any active person (`422` `owner.invalid` otherwise). Converted or disqualified leads cannot be reassigned.
- **List filters**: `status` (repeatable), `owner_id` (repeatable, `me`), `source_id`, `created_at_from` / `created_at_to`, `fits_target_profile`; default sort `-created_at`; `q` searches title, company, contact name, email and phone in both scripts.
- `disqualification` in the response is `{ reason, note, disqualified_at }` when the lead is disqualified, else `null`; `converted_opportunity` is `{ id, name }` once converted.
- Audit actions: `lead.created`, `lead.updated`, `lead.status_changed`, `lead.owner_changed`, `lead.converted`, `lead.archived`, `lead.restored`, with before and after values.

Conversion rules (as built, Phase 4b; FR-LEAD-04):

- `POST /convert` needs the lead's `version` and Owner+; only a `qualified`, non-archived lead converts (`409 lead.not_convertible` with `status` otherwise, also for an already converted lead).
- `organization`: exactly one of `existing_id` (an existing, non-archived organization; `422`, field `organization.existing_id`) and `new` (the organization create body of section 7, including `confirm_duplicate`; duplicates return `409 conflict.duplicate` with `matches`). Sending both or neither returns `422`, field `organization`.
- `contact`: `null`, or exactly one of `existing_id` (must belong to the chosen organization or to none: `contact.organization_mismatch`) and `new` (the contact create body of section 8; it always belongs to the chosen organization; email duplicates as in section 8).
- `opportunity`: `name` (required), `amount`, `expected_close_date`, `stage_id` (an active open stage; default the first), `owner_id` (same rules as section 10; default the caller). The opportunity's `source_lead` is the lead and its primary contact the chosen contact.
- Everything happens in one transaction: any error leaves no organization, contact or opportunity and the lead unchanged (AC2). The lead becomes `converted` with `converted_opportunity`, `converted_at`, and links to the organization and contact.
- Response `201`: `{ lead, organization, contact, opportunity }` (full resources). Audited as `organization.created`, `contact.created`, `opportunity.created` (when new) and `lead.converted`.
- `GET /conversion-preview` (Owner+): `{ organization: { linked, matches, suggested: { name } }, contact: { linked, matches, suggested: { first_name, last_name, email, phone } | null }, opportunity: { name, amount, stage } }`. Organization matches use the duplicate check of section 7 on the company name (across scripts); contact matches are contacts with the lead's email; `suggested` values come from the lead (the contact name is split at the last space).
- `GET /organizations/{org_id}/leads` lists the leads linked to the organization (list conventions apply); the organization's `counts.open_leads` counts its open (new, contacted, qualified), non-archived leads.

## 10. Opportunities and pipeline board

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/opportunities` | List and search. Filters: `stage_id`, `stage_type` (`open`/`won`/`lost`), `owner_id`, `organization_id`, `expected_close_date_from/to`, `amount_from/to`, `is_stale`. Sort: `amount`, `expected_close_date`, `updated_at`, `name` | Signed-in | FR-OPP-04 |
| POST | `/api/v1/opportunities` | Create directly (without a lead); stage defaults to the first open stage, probability to the stage default | Contributor | FR-OPP-01 |
| GET | `/api/v1/opportunities/{opp_id}` | Detail with organization, primary contact, stage, source lead, `is_stale` | Signed-in | FR-OPP-01 |
| PATCH | `/api/v1/opportunities/{opp_id}` | Update fields (amount, close date, probability override, next step, contact, competitor…); requires `version`; `409 opportunity.closed` if closed | Owner+ | FR-OPP-01 |
| DELETE | `/api/v1/opportunities/{opp_id}` | Archive | Owner+ | — |
| POST | `/api/v1/opportunities/{opp_id}/restore` | Restore | Manager+ | — |
| POST | `/api/v1/opportunities/{opp_id}/assign` | Change owner; same rules as leads | Contributor (rules in service) | FR-LEAD-06 |
| POST | `/api/v1/opportunities/{opp_id}/move` | Change stage within open stages. Body `{ "stage_id", "version" }`. Probability resets to the stage default unless it was overridden. Won and lost go through `/close` | Owner+ | FR-OPP-02, 03 |
| POST | `/api/v1/opportunities/{opp_id}/close` | Close. Body `{ "outcome": "won" \| "lost", "loss_reason_id", "competitor", "actual_close_date", "version" }` | Owner+ | FR-OPP-05 |
| POST | `/api/v1/opportunities/{opp_id}/reopen` | Reopen into a chosen open stage | Manager+ | FR-OPP-05 |
| GET | `/api/v1/opportunities/{opp_id}/stage-history` | Stage changes with user, time, from and to | Signed-in | FR-OPP-02 AC2 |
| GET | `/api/v1/opportunities/{opp_id}/timeline` | Activities, stage changes and events, including those from the source lead | Signed-in | FR-ACT-03, FR-LEAD-04 AC3 |
| GET | `/api/v1/opportunities/board` | Kanban data: one column per active open stage with `count`, `total_amount`, `weighted_amount` and cards. Filters: `pipeline_id`, `owner_id`, `expected_close_date_from/to`. Up to 500 cards; `truncated: true` if more | Signed-in | FR-OPP-03 |
| GET | `/api/v1/opportunities/export` | Export the filtered list | Signed-in | FR-REP-02 |

Board response shape:

```json
{
  "pipeline_id": "...",
  "currency": "EUR",
  "columns": [
    {
      "stage": { "id": "...", "name_en": "Qualification", "name_bg": "Квалификация", "stage_type": "open", "position": 2, "default_probability": 25 },
      "count": 14, "total_amount": "612000.00", "weighted_amount": "153000.00",
      "cards": [
        { "id": "...", "name": "Acme – branch connectivity", "organization": { "id": "...", "name": "Acme EOOD" },
          "amount": "48000.00", "expected_close_date": "2027-02-28",
          "owner": { "id": "...", "full_name": "Ivan Petrov" }, "is_stale": false, "can_edit": true, "version": 3 }
      ]
    }
  ],
  "truncated": false
}
```

`can_edit` lets the UI disable dragging (FR-OPP-03 AC2); the server still enforces it on `move`.

Opportunity resource (response):

```json
{ "id": "...", "name": "Acme – branch connectivity",
  "organization": { "id": "...", "name": "Acme EOOD" }, "primary_contact": { "id": "...", "name": "Мария Иванова" },
  "owner": { "id": "...", "full_name": "Ivan Petrov" }, "pipeline_id": "...",
  "stage": { "id": "...", "name_en": "Negotiation", "name_bg": "Преговори", "stage_type": "open", "position": 4, "default_probability": 75 },
  "amount": "48000.00", "currency": "EUR", "probability": 75, "probability_overridden": false, "weighted_amount": "36000.00",
  "expected_close_date": "2027-02-28", "actual_close_date": null, "next_step": "Send the offer", "description": null,
  "source_lead": { "id": "...", "name": "Fibre for 3 branches" }, "loss_reason": null, "competitor": null,
  "is_stale": false, "last_activity_at": null,
  "created_at": "...", "updated_at": "...", "created_by": { ... }, "archived_at": null, "version": 3 }
```

Rules (as built, Phase 4a):

- **Create**: `name` (≤ 200) and `organization_id` (existing, not archived) required; optional `primary_contact_id` (must belong to the organization or to none: `contact.organization_mismatch`), `amount` (`numeric(14,2)`, ≥ 0, decimal string), `expected_close_date`, `probability` (0–100), `next_step`, `description`, `competitor`, `stage_id` (an active open stage, else `stage.not_open`), `owner_id` (same rules as leads). Without `stage_id` the first active open stage is used; without `probability` the stage default applies (`probability_overridden: false`). The creation is the first stage-history entry.
- **PATCH** requires `version`; `stage_id`, `owner_id` and `organization_id` return `422 validation.use_action_endpoint`; a closed opportunity returns `409 opportunity.closed`, an archived one `409 resource.archived`. `probability: null` returns to the stage default.
- **Move** accepts active open stages only (`422`, field `stage_id` / `stage.not_open`); moving to the current stage changes nothing.
- **Close** moves to the first active stage of type `won` or `lost`, sets the probability to that stage's default (100 / 0) and `actual_close_date` (default: today in Europe/Sofia). `lost` without `loss_reason_id` returns `422 opportunity.loss_reason_required`; an inactive or unknown reason returns `422`, field `loss_reason_id` / `reference.invalid`. `competitor` is optional for both outcomes.
- **Reopen** (Manager+) into an active open stage; clears `actual_close_date` and the loss reason; `409 opportunity.not_closed` if the opportunity is open.
- Every stage change (create, move, close, reopen) writes a stage-history row `{ id, from_stage, to_stage, changed_by, changed_at }`.
- **Stale** (FR-OPP-06): an open opportunity is stale when it had no activity (`last_activity_at`, else creation) for `stale_opportunity_days` (setting, default 14) or its expected close date has passed. Closed opportunities are never stale.
- **Board**: active open stages of the default pipeline (or `pipeline_id`), excluding archived opportunities, cards ordered by expected close date; `count`, `total_amount` and `weighted_amount` (Σ amount × probability / 100) cover every matching opportunity even when cards are truncated. `owner_id` accepts `me`.
- List filters: `stage_id`, `stage_type`, `owner_id` (`me`), `organization_id` (all repeatable), `expected_close_date_from/to`, `amount_from/to`, `is_stale`; `q` searches name, organization name and competitor in both scripts. Sync mode as in 1.3.
- Organization figures: `open_opportunities` and `open_pipeline_value` (Σ amount of open, non-archived opportunities) in `GET /organizations/{id}`; archiving an organization with open opportunities returns `409 organization.has_open_opportunities`.
- Audit actions: `opportunity.created`, `updated`, `stage_changed`, `closed_won`, `closed_lost`, `reopened`, `owner_changed`, `archived`, `restored`.

## 11. Activities and tasks

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/activities` | List. Filters: `type`, `lead_id`, `opportunity_id`, `organization_id`, `contact_id`, `owner_id`, `assignee_id`, `is_done`, `due_at_from/to`, `occurred_at_from/to` | Signed-in | FR-ACT-01 |
| POST | `/api/v1/activities` | Log a note, call, meeting, email or task linked to at least one of lead, opportunity, organization or contact | Contributor | FR-ACT-01, 02 |
| GET | `/api/v1/activities/{activity_id}` | Detail | Signed-in | FR-ACT-01 |
| PATCH | `/api/v1/activities/{activity_id}` | Update | Owner+ (owner = activity owner; assignee may update a task) | FR-ACT-01 |
| DELETE | `/api/v1/activities/{activity_id}` | Archive | Owner+ | FR-ACT-01 |
| POST | `/api/v1/activities/{activity_id}/complete` | Mark a task done | Owner+ or assignee | FR-ACT-02 |
| POST | `/api/v1/activities/{activity_id}/reopen` | Mark a task not done | Owner+ or assignee | FR-ACT-02 |
| GET | `/api/v1/activities/export` | Export the filtered list (section 14) | Signed-in | FR-REP-02 |

Timeline items (returned by every `/timeline` endpoint) share one shape so the UI renders them uniformly:

```json
{ "items": [
  { "id": "...", "kind": "activity", "occurred_at": "...", "actor": { ... }, "activity": { ... } },
  { "id": "...", "kind": "event", "occurred_at": "...", "actor": { ... },
    "event": { "type": "stage_changed", "entity_type": "opportunity", "entity_id": "...",
               "data": { "from_stage": { "name_en": "Qualification", "name_bg": "Квалификация", ... },
                         "to_stage": { "name_en": "Solution & Proposal", "name_bg": "Решение и оферта", ... } } } }
], "total": 42, "page": 1, "page_size": 25 }
```

Event types in R1: `created`, `updated`, `owner_changed`, `status_changed`, `stage_changed`, `converted`, `closed_won`, `closed_lost`, `reopened`, `archived`, `restored`. Later modules add their own types.

Rules (as built, Phase 4b):

- **Activity resource**: `{ id, type, subject, body, occurred_at, due_at, done_at, is_done, is_overdue, owner, assignee, links: { lead, opportunity, organization, contact } (each { id, name } or null), created_at, updated_at, created_by, archived_at, version }`.
- **Create** (Contributor): `type` (`note | call | meeting | email | task`), `subject` (≤ 200) required; `body` (≤ 10000); `occurred_at` (default now); at least one of `lead_id`, `opportunity_id`, `organization_id`, `contact_id` (`422`, field `links` / `activity.link_required`), each existing and not archived (`lead.not_found`, `opportunity.archived`, …); `owner_id` as for other records. **Tasks** need `due_at` (`activity.due_required`); `assignee_id` defaults to the owner and must be an active Admin, Sales Manager or Sales Rep (`assignee.invalid`, owner decision). Other types refuse `due_at` and `assignee_id` (`activity.task_only`).
- **PATCH** requires `version`; changes `subject`, `body`, `occurred_at`, and for tasks `due_at` and `assignee_id`. `type`, `owner_id` and `done` return `422 validation.use_action_endpoint`. Allowed for Owner+ and, on a task, its assignee.
- **Complete / reopen** (`{ version }`): tasks only (`409 activity.not_a_task`); Owner+ or the assignee. **Archive** (Owner+) hides the activity from lists (unless `include_archived`) and timelines.
- **Opportunity freshness** (FR-OPP-06): logging a non-task activity on an opportunity, or completing a task on it, moves `last_activity_at` forward to the activity time (never into the future, never backwards).
- **List**: filters as in the table (`owner_id` and `assignee_id` accept `me`; `is_done` applies to tasks), `q` searches the subject, sort `occurred_at` (default, descending), `due_at`, `created_at`, `updated_at`; sync mode as in 1.3.
- **`GET /me/tasks`**: the caller's tasks as assignee, open only unless `include_done=true`, sorted by due date so overdue tasks come first.
- **Timelines** (`page`, `page_size` ≤ 100; newest first): the lead's own items; the opportunity's plus those of its source lead (FR-LEAD-04 AC3); the contact's own; the organization's plus those of its contacts, leads and opportunities. Each item has `id`, `kind`, `occurred_at`, `actor` and either `activity` or `event`. Event `data` uses the record's values: `status_changed` `{ from_status, to_status }`; `stage_changed`, `closed_won`, `reopened` `{ from_stage, to_stage }` and `closed_lost` also `loss_reason` (stage and reason objects with `name_en`/`name_bg`); `owner_changed` `{ from_owner, to_owner }` (`{ id, full_name }`); `converted` `{ opportunity: { id, name } }`; `updated` `{ fields }`. Events are recorded from the same domain events as the audit log, in the same transaction (ADR 0020).
- Audit actions: `activity.created`, `activity.updated`, `activity.completed`, `activity.reopened`, `activity.archived`.

## 12. Search

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/search` | Global quick search across organizations, contacts, leads and opportunities. `q` required (min 2 chars), `types` optional, up to 5 results per type | Signed-in | FR-PARTY-04 |

Response: `{ "items": [ { "type": "organization" | "contact" | "lead" | "opportunity", "id", "label", "detail" } ] }` grouped by type, archived records excluded. `detail` is the city for organizations, the organization name (else email) for contacts, the company name for leads and the organization name for opportunities. `types` may repeat (`organization`, `contact`, `lead`, `opportunity`). For an integration client the types are narrowed to those it holds the read scope for (`organizations:read`, `contacts:read`, `leads:read`, `opportunities:read`); a client with none of them gets an empty result.

## 13. Reports and dashboard

All report endpoints accept `owner_id` (`me`, a user ID, or omitted for all) and, where relevant, `from` and `to` dates. Amounts are in EUR.

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/reports/dashboard` | Everything the dashboard shows in one call: pipeline by stage, 6-month forecast, conversion rate, win rate, my open tasks count | Signed-in | FR-REP-01 |
| GET | `/api/v1/reports/pipeline-by-stage` | Count, total and weighted amount per open stage | Signed-in | FR-REP-01 |
| GET | `/api/v1/reports/forecast` | Weighted forecast by expected close month. `months` (default 6, max 12) | Signed-in | FR-REP-01 AC1 |
| GET | `/api/v1/reports/lead-conversion` | Leads created, qualified, converted, disqualified and conversion rate in the period; group by `source` or `owner` | Signed-in | FR-REP-01 |
| GET | `/api/v1/reports/win-loss` | Won and lost counts and amounts, win rate; group by `loss_reason`, `owner` or `month` | Signed-in | FR-REP-01, FR-REP-03 |
| GET | `/api/v1/reports/{report}/export` | XLSX or CSV export of any report above | Signed-in | FR-REP-02 |

Forecast definition (tested against independently computed values): for each month, the sum of `amount × probability / 100` over open, non-archived opportunities whose `expected_close_date` falls in that month.

Rules (as built, Phase 5a):

- **Scope**: `owner_id` is `me`, a user ID or omitted (everyone); `from`/`to` are calendar dates, default the current calendar year in Europe/Sofia; `from` after `to` returns `400`, field `from` / `validation.period`. Archived records are excluded everywhere. `/pipeline-by-stage` and `/forecast` ignore the period (they describe the open pipeline now; the forecast starts with the current month).
- **`/pipeline-by-stage`**: `{ currency, stages: [{ stage, count, total_amount, weighted_amount }], count, total_amount, weighted_amount }` for the active open stages of the default pipeline (plus inactive open stages that still hold opportunities).
- **`/forecast`** (`months` 1–12, default 6): `{ currency, months: [{ month: "YYYY-MM", count, total_amount, weighted_amount }], weighted_amount }`, one entry per month, zeros included. Opportunities without an amount are counted but add nothing.
- **`/lead-conversion`** (`group_by` `source` | `owner`): leads **created** in the period and their current status: `totals: { created, qualified (qualified or converted), converted, disqualified, conversion_rate }` with `conversion_rate = converted / created` (0–1, `null` when no leads), and `groups` with the same figures plus `group: { key, name_en, name_bg }` (`key` `none` for leads without a source).
- **`/win-loss`** (`group_by` `loss_reason` | `owner` | `month`): opportunities **closed** (won or lost) with `actual_close_date` in the period: `totals: { won_count, won_amount, lost_count, lost_amount, win_rate }` with `win_rate = won / (won + lost)` (`null` when nothing closed). Grouped by loss reason, won deals fall under `key: "none"`; by month, `key` is `YYYY-MM`.
- **`/dashboard`**: `{ from_date, to_date, pipeline, forecast (6 months), lead_conversion (totals), win_loss (totals), my_tasks: { open, overdue } }`; `my_tasks` always counts the caller's own open tasks.
- **`/{report}/export`**: `report` is `pipeline-by-stage`, `forecast`, `lead-conversion` or `win-loss` (`dashboard` is not exportable; other names `422`); the report's parameters plus `format`, `columns`, `locale` (section 14). Rows follow the report; grouped reports and the pipeline end with a total row. Audited as `report.exported`.

## 14. Exports

Every list endpoint has an `/export` sibling (`/organizations/export`, `/contacts/export`, `/leads/export`, `/opportunities/export`, `/activities/export`) that accepts the same filters and sort as the list, plus:

| Parameter | Meaning |
|---|---|
| `format` | `xlsx` (default) or `csv` (UTF-8 with BOM so Excel shows Cyrillic correctly) |
| `columns` | Optional comma-separated list of columns; default is the list view's columns |
| `locale` | `en` or `bg` for column headers and reference value names; default the user's locale |

Responses are file downloads with `Content-Disposition: attachment`. Exports are synchronous, capped at 50,000 rows (`422 export.too_many_rows` above the cap), audited, and protected against spreadsheet formula injection (architecture section 7).

Rules (as built, Phase 5a):

- Endpoints: `/organizations/export`, `/contacts/export`, `/leads/export`, `/opportunities/export`, `/activities/export` (Signed-in) and `/audit-log/export` (Admin), each with the list's filters, `q`, `include_archived` and `sort`; paging parameters are ignored. Not available to integration clients.
- File name `<list>-<YYYY-MM-DD>.<format>` (Sofia date). XLSX has one sheet with a header row; numbers, amounts and dates stay typed (timestamps in Europe/Sofia local time); CSV is UTF-8 with BOM, comma-separated, CRLF line ends, timestamps as `YYYY-MM-DD HH:MM:SS` Sofia time.
- `columns` takes column keys in the wanted order; an unknown key returns `400`, field `columns` / `export.unknown_column`. Column keys: organizations `name, registration_number, vat_number, industry, size_band, website, address_line, postal_code, city, country, owner, created_at, archived_at, id`; contacts `first_name, last_name, job_title, email, phone, organization, owner, created_at, archived_at, id`; leads `title, company_name, contact_name, email, phone, source, status, score, fits_target_profile, estimated_value, organization, owner, created_at, converted_at, archived_at, id`; opportunities `name, organization, primary_contact, stage, amount, probability, weighted_amount, expected_close_date, actual_close_date, owner, next_step, loss_reason, competitor, is_stale, source_lead, created_at, archived_at, id`; activities `type, subject, occurred_at, due_at, is_done, owner, assignee, lead, opportunity, organization, contact, body, id`; audit log `occurred_at, actor, actor_type, action, entity_type, entity_id, ip, id`.
- `locale` (default: the user's language) sets the headers, reference names (stage, source, industry, loss reason), statuses, activity types and Yes/No values.
- Text starting with `=`, `+`, `-`, `@`, tab or carriage return is prefixed with `'` (numbers stay numbers).
- Audited as `<entity>.exported` (`organization`, `contact`, `lead`, `opportunity`, `activity`, `audit_log`, `report`) with `details: { format, rows, columns, filters }`; a refused export (over the cap) is not audited.

## 15. Data import

Import is a step-by-step flow over an import batch resource. Allowed `entity_type`: `organizations`, `contacts`, `leads`, `opportunities`.

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/imports/templates/{entity_type}` | Download the XLSX template with headers and an instructions sheet; `locale` parameter | Manager+ | FR-IMP-01 |
| POST | `/api/v1/imports` | Upload a file (`multipart/form-data`: `file`, `entity_type`). Returns the batch with detected columns and a suggested mapping. Status `uploaded` | Manager+ | FR-IMP-01 |
| GET | `/api/v1/imports` | List batches with status and counts | Manager+ | FR-IMP-01 |
| GET | `/api/v1/imports/{batch_id}` | Batch detail | Manager+ | FR-IMP-01 |
| PUT | `/api/v1/imports/{batch_id}/mapping` | Set column-to-field mapping and duplicate handling (`skip` or `update`) | Manager+ | FR-IMP-01 AC1, AC3 |
| POST | `/api/v1/imports/{batch_id}/validate` | Validate all rows. Status `validated`; returns counts of valid, invalid and duplicate rows | Manager+ | FR-IMP-01 AC1 |
| GET | `/api/v1/imports/{batch_id}/rows` | Paginated preview; filter `outcome` (`valid`, `invalid`, `duplicate`); each row lists field errors | Manager+ | FR-IMP-01 AC1 |
| POST | `/api/v1/imports/{batch_id}/commit` | Write records. Body `{ "mode": "strict" \| "skip_invalid" }`; strict fails with `409 import.has_errors` if any row is invalid. Status `committed` | Manager+ | FR-IMP-01 AC2 |
| POST | `/api/v1/imports/{batch_id}/rollback` | Archive every record created by the batch and revert updates it made; blocked for records changed since import (reported per record). Status `rolled_back` | Admin | FR-IMP-01 AC4 |
| DELETE | `/api/v1/imports/{batch_id}` | Discard a batch that was not committed, including its uploaded data | Manager+ | FR-IMP-01 |

Batch states: `uploaded → mapped → validated → committed → rolled_back`; steps out of order return `409 import.invalid_state`. Uploaded file contents are stored only until commit or discard, and at most 7 days.

Rules (as built, Phase 5b):

- **Files**: `.xlsx` (first sheet) or `.csv`, at most 10 MB (`413 import.too_large` with `max_bytes`) and 20,000 data rows (`413 import.too_large` with `max_rows`); anything else or unreadable returns `415 import.invalid_file`. Row 1 holds the headers; blank lines are ignored; XLSX formulas are not evaluated (their stored value is read). CSV encoding (UTF-8 with or without BOM, else Windows-1251) and delimiter (comma, semicolon or tab) are detected. Row numbers in the preview are the file's line numbers (data starts at 2).
- **Fields** (column headers of the templates, in English and Bulgarian; `*` required):
  - organizations: `name*`, `registration_number`, `vat_number`, `industry` (code or name of an active industry), `size_band`, `website`, `address_line`, `postal_code`, `city`, `country`, `owner` (email), `notes`;
  - contacts: `first_name*`, `last_name*`, `job_title`, `email`, `phone`, `organization` (EIK or exact name of an existing organization, either script), `notes`;
  - leads: `title*`, `company_name*`, `contact_name`, `email`, `phone`, `source` (code or name), `estimated_value`, `description`, `owner`, `organization`;
  - opportunities: `name*`, `organization*`, `stage` (English or Bulgarian name of an active open stage; empty: the first), `amount`, `probability`, `expected_close_date` (`YYYY-MM-DD` or `DD.MM.YYYY`), `next_step`, `competitor`, `description`, `owner`.
  Amounts accept a decimal comma and spaces. `owner` is an active user's email (`owner.invalid` otherwise; empty: the importer).
- **Upload** (`multipart/form-data`): returns `201` with the batch and `Location`. Batch resource: `{ id, entity_type, file_name, status, columns, mapping, duplicate_mode, fields: [{ key, name_en, name_bg, required }], counts: { rows, valid, invalid, duplicate, created, updated, skipped }, created_by, created_at, committed_at, rolled_back_at, expires_at }`. On upload `mapping` holds the suggestion: a column whose header equals a field key or its English or Bulgarian header (case-insensitive) is mapped, each field at most once.
- **Mapping** (`PUT …/mapping`, from `uploaded`, `mapped` or `validated`): `{ mapping: { "<column>": "<field>" | null }, duplicates: "skip" | "update" }`; unknown columns or fields, a field chosen twice, or a required field without a column return `422` with one error per problem. Setting the mapping clears earlier validation results.
- **Validation**: each row is checked with the same schemas and lookups as creating the record directly, plus duplicates by the FR-PARTY-01 rules (organizations: registration number or name in either script; contacts: email) against existing records (`duplicate`, with `match`) and against earlier rows of the same file (`invalid`, `import.duplicate_in_file`). Leads and opportunities have no duplicate rule. Row resource: `{ row_number, outcome, values (by field key), errors: [{ field, code }], match: { id, name } | null, action, record_id, rollback_result }`.
- **Commit** (`{ mode }`, from `validated`): `strict` refuses while any row is invalid (`409 import.has_errors` with `invalid`); `skip_invalid` skips them. Duplicates are skipped, or with `duplicates: "update"` the existing organization or contact gets the file's non-empty values (organizations: not the name, registration number or owner; contacts: not the name or email). Everything is one transaction: a row that fails at commit time (for example a list value retired since validation) returns `409 import.has_errors` with `row_number` and nothing is written. Created records carry `import_batch_id`; each creation and update is audited as usual. The uploaded values are deleted at commit.
- **Rollback** (Admin, from `committed`): created records are archived, updated ones get their previous values back; a record changed since the import (its `updated_at` differs from the value recorded at commit) is kept (`changed_since_import`), as is one that cannot be archived (`blocked:<code>`, e.g. an organization with open opportunities). Response `{ batch, archived, reverted, kept: [rows] }`.
- **Discard** (`DELETE`, before commit) deletes the batch and its rows; uncommitted batches are deleted by the worker after 7 days.
- Audited as `import.uploaded`, `import.mapped`, `import.validated`, `import.committed`, `import.rolled_back`, `import.discarded` (entity type `import_batch`). Not available to integration clients.

## 16. Audit log

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/audit-log` | Browse entries. Filters: `actor_id`, `entity_type`, `entity_id`, `action`, `occurred_at_from/to`. Sort: `-occurred_at` only | Admin | FR-ADM-03 |
| GET | `/api/v1/audit-log/{entry_id}` | One entry with full before and after values | Admin | FR-ADM-03 |
| GET | `/api/v1/audit-log/export` | Export the filtered log | Admin | FR-ADM-03 |

There are no write endpoints for the audit log, and the application's database role cannot update or delete entries. Values of secret fields (password hashes, tokens, MFA secrets) are never stored in audit entries.

```json
// GET /api/v1/audit-log/{entry_id}
{ "id": "...", "occurred_at": "2026-11-17T09:05:00Z",
  "actor": { "type": "user", "id": "...", "name": "Ada Admin" },     // type: user | integration | anonymous | system
  "action": "user.role_changed", "entity_type": "user", "entity_id": "...",
  "ip": "10.0.0.5", "request_id": "0b9c...",
  "before": { "role": "sales_rep", ... }, "after": { "role": "sales_manager", ... },
  "details": null }
```

The list returns the same fields without `before`, `after`, `details` and `request_id`, newest first; `action` may be repeated. The actor's name is stored as it was at the time of the action. Actions recorded in R1 so far: `auth.login_succeeded`, `auth.login_failed`, `auth.account_locked`, `auth.logout`, `auth.password_set`, `auth.password_changed`, `auth.password_reset_requested`, `user.created`, `user.updated`, `user.role_changed`, `user.deactivated`, `user.activated`, `user.password_reset_issued`, `user.unlocked`, `user.sessions_revoked`, `session.revoked`, `settings.updated`.

## 17. AI assistant

All assistant endpoints return `503 assistant.disabled` when `AI_ENABLED` is false, except `status`. `GET /system/info` reports the same switch as `features.ai_enabled`. Integration clients never reach these endpoints (`403 permission.not_for_integrations`).

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/assistant/status` | Whether the assistant is enabled, and the caller's remaining daily token budget | Signed-in | FR-AI-07, 08 |
| GET | `/api/v1/assistant/conversations` | Own conversations, newest first | Signed-in | FR-AI-01 |
| POST | `/api/v1/assistant/conversations` | Start a conversation, optionally with record context `{ "context": { "entity_type": "opportunity", "entity_id": "..." } }` | Signed-in | FR-AI-01, 03 |
| GET | `/api/v1/assistant/conversations/{conversation_id}` | Conversation with its messages (tool messages summarized, not raw) | Signed-in (own only) | FR-AI-01 |
| PATCH | `/api/v1/assistant/conversations/{conversation_id}` | Rename | Signed-in (own only) | FR-AI-01 |
| DELETE | `/api/v1/assistant/conversations/{conversation_id}` | Delete permanently with its messages | Signed-in (own only) | FR-AI-01 |
| POST | `/api/v1/assistant/conversations/{conversation_id}/messages` | Send a message; the response is a Server-Sent Events stream (below). Body `{ "content": "...", "context": {...optional} }`, max 4,000 characters | Signed-in (own only) | FR-AI-01, 02, 06 |
| POST | `/api/v1/assistant/conversations/{conversation_id}/messages/{message_id}/stop` | Stop a running generation | Signed-in (own only) | FR-AI-01 |
| POST | `/api/v1/assistant/messages/{message_id}/save-as-note` | Save an assistant draft as a note activity on a record. Body `{ "entity_type", "entity_id", "content" }` (content may be edited by the user). Normal activity permissions apply | Contributor | FR-AI-04 |

Another user's conversation returns `404`, not `403`.

**Payloads (as built, Phase 7a).**

- `status` → `{ "enabled", "daily_token_budget", "used_today", "remaining_budget" }`. The budget is per user per day; the day starts at midnight Europe/Sofia.
- Conversation → `{ "id", "title", "context": { "entity_type", "entity_id" } | null, "created_at", "updated_at" }`. `context.entity_type` is `lead`, `opportunity` or `organization`; a missing record is `422` with field `context.entity_id` and code `<type>.not_found`. Without a title, the first question (up to 80 characters) becomes the title. The list is paginated with the common envelope (`page`, `page_size`; `sort` is `updated_at`, default `-updated_at`).
- Conversation detail adds `messages`: `{ "id", "role": "user" | "assistant", "content", "status": "streaming" | "complete" | "stopped" | "failed", "error_code", "tools_used": ["search_opportunities", ...], "record_refs": [{ "entity_type", "entity_id", "label" }], "prompt_tokens", "completion_tokens", "created_at" }`. Tool arguments and results are never returned; tool results are not stored at all (ADR 0026).
- `PATCH` body `{ "title" }` (1–200 characters); no `version`: a conversation has a single owner.
- `stop` → `204`. It flags a running answer; the stream ends at its next check (within about a second) with `message_end` and `"status": "stopped"`, keeping the text written so far. Stopping an answer that already ended changes nothing.
- `save-as-note` → `201` with the created activity (section 11). The note's subject is the draft's first line without Markdown markers, its body the content. `entity_type` is `lead`, `opportunity`, `organization` or `contact`; the record checks of `POST /activities` apply (`422` with field `<type>_id` and code `<type>.not_found` or `<type>.archived`). Only the caller's own assistant messages can be saved (`404` otherwise). This is the only way a draft reaches the CRM, and it is an explicit user action (FR-AI-05).
- Conversation create, rename and delete write audit entries (`chat_conversation.created`, `.renamed`, `.deleted`) without titles or content.

**Before the stream starts**, `POST .../messages` answers with an ordinary problem response when: the assistant is off (`503 assistant.disabled`), the conversation is not the caller's (`404`), the body is invalid (`422`), the caller sent more than 20 messages in the current 10-minute window (`429 rate_limit.exceeded` with `Retry-After`), or the caller's daily token budget is used up (`429 assistant.budget_exceeded`). Once the stream has started, the status is `200` and failures arrive as `error` events.

Stream format (`Content-Type: text/event-stream`):

| Event | Data | Meaning |
|---|---|---|
| `message_start` | `{ "message_id", "conversation_id" }` | Assistant message created |
| `tool_call` | `{ "tool": "search_opportunities", "status": "running" \| "done" }` | Progress indicator; no arguments or results are sent to the browser |
| `delta` | `{ "text": "..." }` | Next piece of the answer (Markdown) |
| `record_ref` | `{ "entity_type", "entity_id", "label" }` | A record cited in the answer, for linking |
| `message_end` | `{ "prompt_tokens", "completion_tokens", "remaining_budget", "status": "complete" \| "stopped" }` | Answer complete and stored |
| `error` | `{ "code" }` | `assistant.provider_unavailable`, or `server.internal_error` for an unexpected failure; the stream then closes. (`assistant.budget_exceeded` and `rate_limit.exceeded` are returned before the stream starts, above.) |

The internal tools the model may call (`search_leads`, `search_opportunities`, `search_organizations`, `get_record`, `list_activities`, `pipeline_summary`, `forecast_summary`, `my_tasks`) are **not** HTTP endpoints. They call the same service functions as the endpoints above with the caller's permissions (architecture section 8.3).

**Tools (as built).** Each has a strict JSON schema (unknown arguments refused), returns at most 25 rows, leaves out archived records, and gives every record its `type`, `id` and in-app `url` (for example `/opportunities/<id>`) so answers can link to it. Contact email addresses and phone numbers are never included.

| Tool | Arguments | Returns |
|---|---|---|
| `search_leads` | `query`, `status[]`, `owner` (`me` \| `anyone`), `limit` | Leads: title, company, contact name, status, source, estimated value, owner, qualification score |
| `search_opportunities` | `query`, `stage_type` (`open` \| `won` \| `lost`), `owner`, `organization_id`, `close_from`, `close_to`, `is_stale`, `sort`, `limit` | Opportunities: name, organization, owner, stage, amount, probability, weighted amount, expected close date, next step, staleness |
| `search_organizations` | `query`, `owner`, `limit` | Organizations: name, industry, size, city, country, owner |
| `get_record` | `entity_type` (`lead` \| `opportunity` \| `organization` \| `contact`), `id` | One record with its detail fields (descriptions, BANT notes, counts, links) |
| `list_activities` | `lead_id`, `opportunity_id`, `organization_id`, `contact_id`, `types[]`, `limit` | Activities, newest first: type, subject, body (shortened), dates, owner, linked records |
| `pipeline_summary` | `owner` | Open pipeline per stage: count, total and weighted value (section 13) |
| `forecast_summary` | `owner`, `months` (1–12) | Weighted forecast by expected close month (section 13) |
| `my_tasks` | `include_done`, `limit` | The caller's own tasks, overdue first |

A tool call with invalid arguments, an unknown tool name or a missing record gives the model a short error (`invalid_arguments`, `unknown_tool`, the error code), never data. The model may use at most 5 rounds of tools per answer; then it must answer without tools.

## 18. Rate limits

Defaults, configurable through settings or environment; exceeded limits return `429 rate_limit.exceeded` with `Retry-After` (seconds). Counters are fixed windows stored in PostgreSQL. Environment variables: `RATE_LIMIT_LOGIN_PER_MINUTE`, `RATE_LIMIT_PASSWORD_PER_15_MINUTES` (covers `GET /auth/password/token/{token}` and every `POST /auth/password/*`), `RATE_LIMIT_USER_PER_MINUTE`.

| Scope | Limit |
|---|---|
| `POST /auth/login`, `/auth/login/mfa` | 10 per minute per IP; account lockout after 5 failures (FR-AUTH-01) |
| `POST /auth/password/*` | 5 per 15 minutes per IP |
| Assistant messages | 20 per 10 minutes per user (`RATE_LIMIT_ASSISTANT_PER_10_MINUTES`), plus the daily token budget (`AI_DAILY_TOKEN_BUDGET`, default 200,000 tokens per user) |
| Exports | 10 per minute per user |
| Imports (upload) | 10 per hour per user |
| All other authenticated endpoints | 600 per minute per user |
| Each integration client, all endpoints | 300 per minute by default (owner decision, Phase 6), set per client with `rate_limit_per_minute` (1–100,000); counted per client, not per service user |

## 19. Integration API (Conclusion, ERP, Billing)

### 19.1 Principles

- Integrated applications use **the same `/api/v1` endpoints, payloads and business rules** as the web frontend. There is no separate integration API to keep in sync.
- Each application is an **integration client**: a registered, non-human principal backed by a service user (`app_user.user_type = 'service'`) that cannot sign in interactively, cannot own records and is shown as the actor in audit logs and timelines (for example "ERP (integration)").
- Access is **least privilege**: an integration client can call only the endpoints its scopes allow (19.3). Write scopes are granted only after the data flow for that system is agreed (19.9).
- Communication is server to server over HTTPS on the company network. There is no CORS for integrations.
- The CRM pushes changes through **webhooks** (19.6); integrations can also pull changes with **sync mode** lists (section 1.3). Both may be used together; webhooks for timeliness, a periodic sync as the safety net.

### 19.2 Authentication with API keys

- Key format: `crm_<env>_<key_id>_<secret>`, for example `crm_prod_k7Q2…_…`, with at least 256 bits of randomness in the secret. Only a SHA-256 hash of the secret is stored; the full key is shown once, at creation.
- Sent as `Authorization: Bearer <api_key>`. Keys in query strings are rejected.
- Each key has an expiry (default 12 months, maximum 24) and records `last_used_at` and `last_used_ip`. A client may have two active keys at once so keys can be rotated without downtime. Revocation takes effect on the next request.
- Optional per-client IP allowlist (CIDR list); requests from other addresses return `403 auth.ip_not_allowed`.
- Keys never appear in logs, audit entries, error messages or API responses after creation.

As built (Phase 6a, ADR 0024):

- `<env>` is `prod`, `test` or `dev` (from `ENV`); `<key_id>` is 16 hex characters and is what the server looks up; `<secret>` is 43 URL-safe characters (256 bits). The non-secret prefix `crm_<env>_<key_id>` is shown in the key list.
- A third active key returns `409 api_key.limit`. `expires_at` is optional (default 12 months); a past date returns `422 api_key.expiry_past`, more than 24 months `422 api_key.expiry_too_long`.
- A malformed, unknown, revoked or expired key returns `401 auth.api_key_invalid`; a deactivated client `401 auth.client_inactive`. `last_used_at` and `last_used_ip` are written at most once a minute per key.
- An `Authorization` header with a session cookie returns `400 auth.mixed_credentials`; an `Authorization` scheme other than `Bearer` is `401 auth.api_key_invalid`.

### 19.3 Scopes and the endpoints they open

| Scope | Endpoints allowed |
|---|---|
| `organizations:read` | `GET /organizations`, `/organizations/{id}`, `/organizations/{id}/contacts`, `/organizations/{id}/opportunities`, `/organizations/{id}/timeline`, `/organizations/duplicate-check`, `/search` (organization results only) |
| `organizations:write` | `POST /organizations`, `PATCH /organizations/{id}` (not `owner_id`) |
| `contacts:read` | `GET /contacts`, `/contacts/{id}`, `/contacts/{id}/timeline` |
| `contacts:write` | `POST /contacts`, `PATCH /contacts/{id}` |
| `leads:read` | `GET /leads`, `/leads/{id}`, `/leads/{id}/timeline` |
| `leads:write` | `POST /leads`, `PATCH /leads/{id}`, `POST /leads/{id}/mark-contacted`, `/qualify`, `/disqualify` |
| `opportunities:read` | `GET /opportunities`, `/opportunities/{id}`, `/opportunities/{id}/stage-history`, `/opportunities/{id}/timeline` |
| `opportunities:write` | `POST /opportunities`, `PATCH /opportunities/{id}`, `POST /opportunities/{id}/move`, `/close` |
| `activities:read` | `GET /activities`, `/activities/{id}` |
| `activities:write` | `POST /activities`, `PATCH /activities/{id}` (only activities the client created) |
| `reference:read` | `GET /reference/{list}`, `/pipelines`, `/pipelines/{id}`, `GET /users/lookup` |
| `reports:read` | `GET /reports/*` (not the export variants) |
| `external-references:write` | `PUT` and `DELETE` on external references for **the client's own system only** (19.4) |

Every client may call `GET /me` and `GET /openapi.json` without a scope. Reading external references needs only the read scope of the record type.

Never available to integration clients, whatever their scopes: authentication and password endpoints, `/me/sessions`, `/me/tasks`, user administration, settings, writes to reference data and pipelines, archive and restore, assign, lead convert and reopen, opportunity reopen, imports, exports, the audit log, GDPR endpoints, the AI assistant, and integration administration (19.7).

As built (Phase 6a): the scope is declared on each route (`x-required-scope` in the OpenAPI document) and checked in the same policy function as roles, before any role or ownership rule. Within a write scope the role rules still apply: an integration acts with the `integration` role, which may create records and edit them, but may not change an organization's owner, archive, restore, assign or convert (`403 permission.denied` or `permission.not_for_integrations`). `PATCH /activities/{id}` is allowed only for activities the client created.

Records created by an integration must have a human owner: the request's `owner_id` (for example found with `GET /users/lookup?email=`) or, if omitted, the client's configured `default_owner_id`; otherwise `422 owner.required`.

### 19.4 External references (cross-system IDs)

Links a CRM record to its identifier in another system: an ERP customer number, a Billing account ID, a Conclusion record ID. One reference per record per system; an external ID is unique per system and record type.

`{resource}` is one of `organizations`, `contacts`, `leads`, `opportunities`; `{system}` is a code from the `external-systems` list.

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/external-references` | Resolve an external ID. Required: `system`, `external_id`; optional `entity_type`. Returns `{ entity_type, entity_id, ... }` or `404` | Signed-in; Integration: read scope of the resolved type | FR-INT-04 |
| GET | `/api/v1/{resource}/{id}/external-references` | All references of one record | Signed-in; Integration: read scope of `{resource}` | FR-INT-04 |
| PUT | `/api/v1/{resource}/{id}/external-references/{system}` | Create or replace the reference. Body `{ "external_id": "C-10023", "url": "https://erp.internal/customers/C-10023" }` (url optional, HTTPS only, shown as a link in the UI) | Admin; Integration: `external-references:write` and `{system}` equals the client's system | FR-INT-04 |
| DELETE | `/api/v1/{resource}/{id}/external-references/{system}` | Remove the reference | Admin; Integration: as for `PUT` | FR-INT-04 |

Lists accept `external_system` and `external_id` filters, and `external_system` with `has_external_reference=false` to find records not yet linked (for example won opportunities ERP has not picked up). Setting or removing a reference is audited and emits `external_reference.updated`.

As built (Phase 6a):

- `PUT` returns `200` with the reference; `DELETE` returns `204`; both `404` when the record or reference does not exist, `422 reference.invalid` (field `system`) for an unknown or inactive system.
- An external ID already linked to another record of the same type in the same system returns `409 external_reference.conflict`.
- The list filters work on `GET /organizations`, `/contacts`, `/leads`, `/opportunities` and their `/export` variants. `external_id` and `has_external_reference` need `external_system` (`400 validation.failed`, field `external_system`, code `validation.missing`).
- The web UI shows the references on the organization, contact, lead and opportunity pages, as a link when a `url` is stored; Admins add and remove them there.

```json
// PUT /api/v1/organizations/{id}/external-references/erp  →  200
{ "entity_type": "organization", "entity_id": "0193...", "external_id": "C-10023",
  "url": "https://erp.internal/customers/C-10023",
  "system": { "id": "...", "code": "erp", "name_en": "ERP", "name_bg": "ERP" },
  "updated_at": "2026-11-17T09:30:00Z", "updated_by": { "id": "...", "full_name": "ERP (integration)" } }
```

### 19.5 Idempotency

- Integration `POST` requests that create records (and the lead and opportunity action endpoints) accept an `Idempotency-Key` header (1–255 characters, typically a UUID or the source system's own record ID).
- The first response for a key is stored for 24 hours per client. A retry with the same key and the same body returns the stored response with header `Idempotent-Replayed: true`. The same key with a different body returns `422 idempotency.key_reused`; a retry while the first is still running returns `409 idempotency.in_progress`.
- Clients should still check for an existing external reference before creating a record.

As built (Phase 6a): every `POST` by an integration client that carries `Idempotency-Key` is covered (the header is ignored for web sessions). Records are kept per client; the request fingerprint is the method, path and body. A `5xx` response is not stored, so a retry runs again. A replay returns the stored status, body, `Content-Type` and `Location`. A key longer than 255 characters (or empty) returns `422 validation.failed` with field `Idempotency-Key`. Expired records are removed by the worker.

### 19.6 Webhooks (CRM → integrated applications)

**Delivery model.** Every relevant change writes an event to an **outbox table in the same database transaction** as the change, so no event is lost and no event is sent for a change that was rolled back. A background worker delivers events to subscribed endpoints. Delivery is at least once; consumers must deduplicate on `id` and use `data.version` or `occurred_at` to ignore out-of-date events, because ordering is guaranteed only per record, not globally.

**Event types (R1):** `organization.created`, `organization.updated`, `organization.archived`, `contact.created`, `contact.updated`, `contact.archived`, `contact.anonymized`, `lead.created`, `lead.updated`, `lead.status_changed`, `lead.converted`, `opportunity.created`, `opportunity.updated`, `opportunity.stage_changed`, `opportunity.closed_won`, `opportunity.closed_lost`, `opportunity.reopened`, `external_reference.updated`, and `ping` (test).

A subscription receives only events whose record type the client may read (for example `opportunity.*` requires `opportunities:read`). Events caused by a client's own API calls are delivered to it as well, flagged by `actor`, so it can ignore its own changes.

**Request sent to the subscriber:**

```
POST https://erp.internal/hooks/crm
Content-Type: application/json
X-CRM-Event-Id: evt_0193f1c2...
X-CRM-Event-Type: opportunity.closed_won
X-CRM-Delivery-Attempt: 1
X-CRM-Signature: t=1763380000,v1=5f2b...e9
```

```json
{
  "id": "evt_0193f1c2...",
  "type": "opportunity.closed_won",
  "api_version": "v1",
  "occurred_at": "2026-11-17T14:03:12Z",
  "actor": { "type": "user", "id": "...", "name": "Ivan Petrov" },
  "data": {
    "entity_type": "opportunity",
    "entity_id": "0193...",
    "version": 9,
    "changes": ["stage_id", "actual_close_date"],
    "object": { "...": "the full resource exactly as GET /api/v1/opportunities/{id} returns it" }
  }
}
```

Contact events for an anonymized contact carry the anonymized object. The `object` snapshot is taken when the event is delivered, never containing fields the client's scopes do not cover.

**Signature.** `v1` is the hex HMAC-SHA256 of `"{t}.{raw_body}"` with the subscription's secret. Receivers must recompute it with a constant-time comparison and reject timestamps older than 5 minutes. Secrets can be rotated; for 24 hours after rotation both old and new signatures are sent (`v1=old,v1=new`).

**Retries.** A delivery succeeds on any `2xx` within 10 seconds. Otherwise it is retried with exponential backoff and jitter (about 1 min, 5 min, 30 min, 2 h, 6 h, then every 6 h) for up to 72 hours, then marked `failed` and shown to Admins. Redirects are not followed. A subscription failing continuously for 72 hours is suspended automatically and Admins are alerted.

**URL rules.** HTTPS only (HTTP allowed only when `ENV` is not `production`), host must match the `WEBHOOK_ALLOWED_HOSTS` allowlist, no credentials in the URL. This prevents the CRM being used to reach arbitrary internal addresses.

As built (Phase 6b, ADR 0025):

- **Outbox.** The integration module subscribes to the domain event bus and writes an `outbox_event` row in the business transaction for each mapped action. Actions without an event type of their own (`<record>.archived` for leads and opportunities, `.restored`, `.owner_changed`) are sent as `<record>.updated`; audit-only actions (sign-in, exports, imports' own events, user administration) are not sent. `contact.anonymized` is accepted in subscriptions and sent once GDPR anonymization exists (Phase 8). `changes` lists the fields whose values differ between before and after (empty for creations). `actor` is `{ "type": "user" | "integration" | "system", "id", "name" }`, plus `client_id` for integrations.
- **Fan-out.** The worker (every `WORKER_POLL_INTERVAL_SECONDS`, default 5) turns new events into one delivery per active, non-suspended subscription whose `event_types` match (`*`, `<record>.*` or the exact type) and whose client may read the record type (AC4); it then attempts what is due, four at a time. Deliveries for a deactivated client wait and are sent once it is active again.
- **Object and version.** `data.object` is built when the delivery is attempted, through the same service functions as `GET` (so retries carry current data); `null` if the record no longer exists. `data.version` is the record's `version` for leads and opportunities and `null` for organizations and contacts, which have none. For `external_reference.updated`, `data.system` is the system code and `object` is the reference (`null` after removal).
- **Request.** Body is compact UTF-8 JSON; headers as above plus `User-Agent: LightCRM-Webhooks/1`. The host is resolved, and the delivery is refused (`address_not_allowed`) if any address is loopback, link-local, unspecified, multicast, reserved or a cloud metadata address; otherwise the connection goes to the vetted address (no second lookup) while TLS still verifies the certificate for the URL's host. Private ranges (on-premises systems) are allowed. The URL is re-checked against the allowlist at each attempt. 10 seconds in total; redirects are failures; at most 4 KB of the response is read and 1,000 characters stored.
- **Ordering.** A delivery waits while an earlier one (by event time, then event ID) for the same record and subscription is pending or retrying.
- **Retry and suspension.** Delays after attempts 1–5 are 1 min, 5 min, 30 min, 2 h, 6 h (±10 % jitter), then every 6 h; after 72 hours from the first attempt the delivery is `failed`. A subscription whose deliveries have failed without a success for 72 hours is suspended (`suspended_at`); `PATCH ... {"is_active": true}` resumes it. Test events (`ping`) are attempted once, whatever the client, subscription or suspension state, and never count towards suspension or the failing figure.
- **Error names** recorded for attempts without an HTTP status: `timeout`, `connection_failed`, `dns_failed`, `address_not_allowed`, `url_not_allowed`, `secret_unreadable` (the encryption key changed).
- **Housekeeping.** Events older than 30 days are deleted with their deliveries and attempts.

### 19.7 Integration administration (Admin)

| Method | Path | Purpose | Access | Req. |
|---|---|---|---|---|
| GET | `/api/v1/integration-clients` | List clients with system, scopes, status, last used, request and error counts for the last 24 hours, failing deliveries | Admin | FR-INT-01, 08 |
| POST | `/api/v1/integration-clients` | Register a client: `name`, `system` (from `external-systems`), `scopes`, `default_owner_id`, `ip_allowlist`, `technical_contact`, `rate_limit_per_minute`. Creates the service user | Admin | FR-INT-01 |
| GET | `/api/v1/integration-clients/{client_id}` | Detail | Admin | FR-INT-01 |
| PATCH | `/api/v1/integration-clients/{client_id}` | Change scopes, owner default, allowlist, contact, rate limit | Admin | FR-INT-01, 03 |
| POST | `/api/v1/integration-clients/{client_id}/deactivate` | Block all access and pause its webhooks | Admin | FR-INT-01 |
| POST | `/api/v1/integration-clients/{client_id}/activate` | Re-enable | Admin | FR-INT-01 |
| GET | `/api/v1/integration-clients/{client_id}/api-keys` | Keys with prefix, created, expiry, last used (never the secret) | Admin | FR-INT-02 |
| POST | `/api/v1/integration-clients/{client_id}/api-keys` | Create a key; body `{ "label", "expires_at" }`; the full key is in this response only | Admin | FR-INT-02 |
| DELETE | `/api/v1/integration-clients/{client_id}/api-keys/{key_id}` | Revoke a key immediately | Admin | FR-INT-02 |
| GET | `/api/v1/integration-clients/{client_id}/webhook-subscriptions` | Subscriptions of a client | Admin | FR-INT-07 |
| POST | `/api/v1/integration-clients/{client_id}/webhook-subscriptions` | Create: `url`, `event_types` (list, wildcards like `opportunity.*` allowed), `is_active`. Returns the signing secret once | Admin | FR-INT-07 |
| PATCH | `/api/v1/webhook-subscriptions/{subscription_id}` | Change URL, event types, active flag | Admin | FR-INT-07 |
| DELETE | `/api/v1/webhook-subscriptions/{subscription_id}` | Remove | Admin | FR-INT-07 |
| POST | `/api/v1/webhook-subscriptions/{subscription_id}/rotate-secret` | New secret, returned once; old one valid for 24 hours | Admin | FR-INT-07 |
| POST | `/api/v1/webhook-subscriptions/{subscription_id}/test` | Queue a `ping` event (`202` with the delivery); the worker sends it once, and the receiver's status code and timing appear in the delivery (no outbound call inside a request) | Admin | FR-INT-07 |
| GET | `/api/v1/webhook-deliveries` | Delivery log. Filters: `subscription_id`, `client_id`, `event_type`, `status` (`pending`, `succeeded`, `retrying`, `failed`), `created_at_from/to` | Admin | FR-INT-07, 08 |
| GET | `/api/v1/webhook-deliveries/{delivery_id}` | Attempts with status codes, timings and truncated response bodies | Admin | FR-INT-07 |
| POST | `/api/v1/webhook-deliveries/{delivery_id}/redeliver` | Queue the event again | Admin | FR-INT-07 |

Delivery log entries are kept 30 days. Creating, changing, deactivating clients, keys and subscriptions is audited.

As built (Phase 6a for clients and keys, Phase 6b for webhooks): `GET /integration-clients` returns a plain array (a few clients, no paging). `POST /integration-clients` creates the client **inactive** unless `is_active: true` is sent, because clients are switched on only after the owner confirms the data flow (19.9); the web UI always creates inactive clients. `ip_allowlist` takes up to 50 CIDR ranges; `rate_limit_per_minute` defaults to 300. The service user is named `<name> (integration)` and never appears in user lists or owner pickers. Audit actions: `integration_client.created`, `.updated`, `.activated`, `.deactivated`, `api_key.created`, `api_key.revoked` (never with the key).

```json
// POST /api/v1/integration-clients  →  201
// body: { "name": "ERP", "system": "erp", "scopes": ["organizations:read", "external-references:write"],
//         "default_owner_id": "0193...", "ip_allowlist": ["10.1.2.0/24"], "technical_contact": "erp-team@example.bg" }
{ "id": "0193...", "name": "ERP", "system": { "id": "...", "code": "erp", "name_en": "ERP", "name_bg": "ERP" },
  "scopes": ["external-references:write", "organizations:read"], "default_owner": { "id": "0193...", "full_name": "Ivan Petrov" },
  "ip_allowlist": ["10.1.2.0/24"], "technical_contact": "erp-team@example.bg", "rate_limit_per_minute": 300,
  "is_active": false, "last_used_at": null, "usage": { "requests_24h": 0, "errors_24h": 0 }, "active_keys": 0,
  "created_at": "...", "updated_at": "..." }

// POST /api/v1/integration-clients/{client_id}/api-keys  →  201   body: { "label": "Production" }
{ "id": "0193...", "label": "Production", "prefix": "crm_prod_3f9c1a2b7d4e5f60",
  "key": "crm_prod_3f9c1a2b7d4e5f60_<43 characters, shown only here>",
  "created_at": "...", "expires_at": "2027-11-17T09:30:00Z", "revoked_at": null,
  "last_used_at": null, "last_used_ip": null, "created_by": { "id": "...", "full_name": "Ada Admin" } }
```

`usage` counts the client's requests and error responses (status 400 and above) over the last 24 hours, from hourly counters kept in PostgreSQL for 30 days. `webhooks` gives `subscriptions`, `failing_deliveries` (now retrying, or failed in the last 24 hours, test events excluded) and `suspended_subscriptions`; the web UI shows a banner in the admin area and a badge on the Integrations link while either of the last two is above zero (FR-INT-08).

Webhook administration (Phase 6b):

- Subscriptions: `url` (≤ 500 characters, URL rules of 19.6, else `422 webhook.url_not_allowed` with field `url`), `event_types` (1–40 of the types of 19.6, `<record>.*` or `*`; others `422` with `validation.value_error` on `event_types.<n>`; duplicates removed), `is_active` (default `true`). The secret (`whsec_` + 43 characters) is returned by `POST` and `rotate-secret` only, stored encrypted with `APP_ENCRYPTION_KEY`. `previous_secret_valid_until` is set for 24 hours after a rotation. `DELETE` removes the subscription with its deliveries.
- `POST .../test` returns `202` with the queued `ping` delivery; its attempt appears in `GET /webhook-deliveries/{id}` within one worker poll.
- `GET /webhook-deliveries` is paginated (`page`, `page_size` ≤ 100), newest first; `status` must be one of the four statuses (`422` otherwise). `POST .../redeliver` returns `202` with a new delivery of the same event to the same subscription; the receiver sees the same event `id`.
- Audit actions: `webhook_subscription.created`, `.updated`, `.deleted`, `.secret_rotated`, `.test_sent`, `webhook_delivery.redelivered` (never with a secret). Automatic suspension is logged by the worker (`webhook_subscription_suspended`).

```json
// POST /api/v1/integration-clients/{client_id}/webhook-subscriptions  →  201
// body: { "url": "https://erp.internal/hooks/crm", "event_types": ["opportunity.closed_won", "organization.*"] }
{ "id": "0193...", "client_id": "0193...", "url": "https://erp.internal/hooks/crm",
  "event_types": ["opportunity.closed_won", "organization.*"], "is_active": true,
  "suspended_at": null, "failing_since": null, "previous_secret_valid_until": null,
  "deliveries_24h": { "succeeded": 0, "pending": 0, "retrying": 0, "failed": 0 },
  "created_at": "...", "updated_at": "...", "secret": "whsec_<43 characters, shown only here>" }

// GET /api/v1/webhook-deliveries/{delivery_id}
{ "id": "0193...", "subscription_id": "0193...", "client_id": "0193...", "event_id": "evt_0193f1c2...",
  "event_type": "opportunity.closed_won", "entity_type": "opportunity", "entity_id": "0193...",
  "occurred_at": "...", "status": "retrying", "attempt_count": 1, "next_attempt_at": "...",
  "last_status_code": 503, "last_error": null, "delivered_at": null, "created_at": "...",
  "url": "https://erp.internal/hooks/crm",
  "attempts": [ { "number": 1, "attempted_at": "...", "duration_ms": 87, "status_code": 503,
                  "error": null, "response_excerpt": "Service Unavailable" } ] }
```

### 19.8 Versioning and change policy for integrators

- Integrators build against `/api/v1` and the published OpenAPI document. Non-breaking additions (new endpoints, new optional request fields, new response fields, new event types, new values in reference lists) may appear at any release; clients must ignore unknown fields and event types.
- Breaking changes go to `/api/v2`; `v1` then stays available for at least 6 months, with deprecation announced through the `Deprecation` and `Sunset` response headers and release notes.
- Each release's notes list API changes in a dedicated section.

### 19.9 Initial integration profiles

**Owner answer (2026-11-18, ADR 0028):** for now each of the three systems gets every integration scope; endpoints closed to integration clients stay closed (19.3). The purposes and webhook events below remain working assumptions until the teams describe their flows; narrow the scopes then (an Admin action).

| Client | Assumed purpose | Scopes first assumed (now: all) | Initial webhook events |
|---|---|---|---|
| ERP (`erp`) | Create the customer in ERP when a deal is won; write the ERP customer number back to the organization | `organizations:read`, `contacts:read`, `opportunities:read`, `reference:read`, `external-references:write` | `opportunity.closed_won`, `organization.updated`, `contact.updated` |
| Billing (`billing`) | Set up the billing account and services for a won deal; write the billing account ID back to the organization and opportunity | `organizations:read`, `contacts:read`, `opportunities:read`, `reference:read`, `external-references:write` | `opportunity.closed_won`, `organization.updated` |
| Conclusion (`conclusion`) | Purpose to be confirmed | `organizations:read`, `opportunities:read`, `reference:read`, `external-references:write` | None until the purpose is confirmed |

`python -m app.cli create-integration-client [--system erp|billing|conclusion|all]` creates these clients with every integration scope, inactive and without keys; it skips a system that already has a client (an Admin edits the scopes of an existing one). Writes need a default owner on the client (19.3).

Typical ERP flow under these assumptions: receive `opportunity.closed_won` → read the organization and contacts → create the customer in ERP → `PUT /organizations/{id}/external-references/erp` with the customer number. Nightly, call `GET /opportunities?stage_type=won&external_system=erp&has_external_reference=false` and a sync-mode `GET /organizations?updated_since=...` to catch anything missed.

### 19.10 Integration guide deliverable

Delivered in Phase 6b: [`integration-guide.md`](integration-guide.md), the Postman v2.1 collection [`integration/light-crm.postman_collection.json`](integration/light-crm.postman_collection.json) (checked against the routes by a test) and the reference receiver `deploy/examples/webhook_receiver.py`. Only the Python verification sample is executed by the test suite (owner decision); the C# and Java samples are marked untested.

Original scope: Phase 6 produces `docs/integration-guide.md` for the Conclusion, ERP and Billing teams: how to obtain a key, authentication, scopes, sync mode, external references, idempotency, webhook verification with code samples (Python, C#, Java), error codes, rate limits, the versioning policy, and a ready-to-import Postman or Bruno collection in `docs/integration/`.

## 20. Future extensions (not in R1)

These are recorded so R1 does not block them; do not build them now.

- **OAuth 2.0 client credentials** as an alternative to API keys, if an integrated application or company policy requires it; the integration client model already fits it (ADR 0028).
- **Mutual TLS** for integration traffic, at the proxy on a separate host name or port, in addition to the API key (ADR 0028).
- **Further integrated applications** (for example a website contact form creating leads) are added as new integration clients and `external-systems` values, with no code change.
- **TM Forum facade**: a separate `/tmf-api/...` adapter exposing TMF699 Sales Management and TMF632 Party Management shapes, mapped onto the R1 services.
- **R2–R4 resources**: `/product-offerings`, `/product-offering-qualifications`, `/solution-configurations`, `/site-surveys`, `/quotes`, `/proposals`, `/agreements`, `/partners`, each nested or linked by `opportunity_id` and `organization_id` in the same style as this document, with matching scopes and webhook events.
- **Assistant actions**: `POST /assistant/messages/{id}/actions/{action_id}/confirm` for user-approved changes proposed by the assistant (R1.1).
