# Implementation log

What has been built, phase by phase, with the key code. The specifications in `docs/01`–`05` say what to build; this file records what exists, how it works, how it was verified, and what was deferred or decided along the way. The test cases performed in each phase are recorded in [`Test_strategy.md`](Test_strategy.md); the API documentation is [`05-api-specification.md`](05-api-specification.md) plus the OpenAPI snapshot in [`api/`](api/README.md).

| Phase | Status | Branch |
|---|---|---|
| 0 — Foundation | Done, merged (PR #1) | `phase-0-foundation` |
| 1 — Identity, access and audit | Done, merged (PR #2), CI green | `phase-1-identity` |
| 2 — Organizations and contacts | Done, merged (PR #4) | `phase-2-party` |
| 3 — Leads | Done, merged (PR #5) | `phase-3-leads` |
| 4a — Pipelines, opportunities and board | Done, merged (PR #6) | `phase-4a-opportunities` |
| 4b — Activities, timelines and lead conversion | Done, reviewed in PR #7; reaches `main` with PR #8 | `phase-4b-activities` |
| 5a — Reports, dashboard and exports | Built; PR #9 (stacked on #8), CI green | `phase-5a-reports` |
| 5b — Import, seed data and performance | Built; PR #10 (stacked on #9), CI green; awaiting owner review of Phase 5 | `phase-5b-import` |

---

## Phase 0 — Foundation

Goal (implementation plan): an empty but production-shaped skeleton. Exit: the sign-in page placeholder loads over HTTPS locally in both languages; `/api/health/ready` is green; CI is green.

### Tasks

| # | Task | Result |
|---|---|---|
| 0.1 | Remove Prelegal code, repo layout, `.gitignore`, README | Done |
| 0.2 | Backend skeleton: app factory, settings, DB session, problem details, JSON logs + request IDs, health, OpenAPI, module packages, worker, CLI | Done (the `Principal` type moved to Phase 1, where architecture §3 places it) |
| 0.3 | Alembic (async) with baseline migration, DDL/DML roles, pytest on real PostgreSQL, migration tests | Done |
| 0.4 | ruff, mypy strict, import-linter contracts, route-catalog test | Done |
| 0.5 | Frontend: Vite, React, TS strict, router, layout, TanStack Query, Tailwind + shadcn/ui, i18next en/bg, sign-in placeholder, generated typed client | Done |
| 0.6 | ESLint/Prettier, Vitest + MSW, i18n parity script, contract-drift check, Playwright smoke | Done |
| 0.7 | Dockerfiles, Compose (prod-like + dev), Caddyfile, `.env.example`, backups, start/stop scripts | Done; verified under Docker Desktop (see Verification) |
| 0.8 | GitHub Actions CI with all gates | Done; green on PR #1 |
| 0.9 | Seed ADRs | Done: `docs/adr/0001`–`0012` |
| 0.10 | Quality gate, docs, this log | Done; see "Verification" |

### Repository layout

```
backend/
  app/
    main.py            app factory, router registration
    worker.py          background worker loop (jobs registered from Phase 6)
    cli.py             operator commands (export-openapi; create-admin in Phase 1)
    core/              config, db, errors, logging, middleware, access, health, migrations
    modules/<9>/       identity, party, sales, activity, reporting, dataimport, audit,
                       integration, assistant — each with router/schemas/service/
                       repository/models/permissions (empty placeholders)
    llm/client.py      the only place allowed to import litellm (Phase 7)
  alembic/             env.py (async), versions/0001_baseline.py
  tests/               unit/, api/, migrations/
  Dockerfile           one image for API, worker and migrations
frontend/
  src/app/             router, layout, error boundary, query client
  src/api/             generated schema.d.ts + typed client
  src/features/        auth (sign-in placeholder), system (API status, language switch)
  src/components/ui/   shadcn/ui primitives (button, input, label)
  src/i18n/            en/*.json, bg/*.json, typed keys
  e2e/                 Playwright smoke tests
  Dockerfile           builds the SPA into the Caddy image
deploy/                caddy/Caddyfile, postgres/init-roles.sh, backup/backup.sh
scripts/               start/stop for macOS, Linux, Windows
.github/workflows/     ci.yml
```

### Backend

**Versions** (exact pins in `backend/pyproject.toml` / `uv.lock`): Python 3.14.8, FastAPI 0.163.1, Pydantic 2.14.3, pydantic-settings 2.16.3, SQLAlchemy 2.1.9, asyncpg 0.32.0, Alembic 1.20.1, Uvicorn 0.54.0; dev: pytest 9.2, pytest-asyncio 1.5, pytest-cov 7.1, httpx 0.28.1, ruff 0.17.5, mypy 2.4.1, import-linter 2.16, pip-audit 2.10.1.

#### Settings refuse default secrets in production (`app/core/config.py`)

Configuration comes only from environment variables (or a local `.env`). Placeholder secrets contain `change-me`; with `ENV=production` the app will not start with them.

```python
@model_validator(mode="after")
def _refuse_default_secrets_in_production(self) -> Self:
    if not self.is_production:
        return self
    secrets = {
        "DATABASE_URL": str(self.database_url),
        "MIGRATION_DATABASE_URL": str(self.migration_database_url or ""),
    }
    insecure = sorted(name for name, value in secrets.items() if INSECURE_PLACEHOLDER in value)
    if insecure:
        raise ValueError(
            "Refusing to start with default secrets in production: " + ", ".join(insecure)
        )
    return self
```

#### Problem details (`app/core/errors.py`)

Every error is RFC 9457 `application/problem+json` with a stable `code` and the `request_id`. Services raise `AppError(code, status, detail=..., errors=[FieldError(...)], extra=...)`. Validation errors map Pydantic error types to field codes (`validation.missing`, `validation.int_parsing`, …); a body that is not JSON is `400` with field `body`, code `validation.json_invalid`.

```python
def problem_body(code: ErrorCode, status: int, *, detail=None, errors=(), extra=None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": PROBLEM_TYPE_BASE + code.value,      # https://crm.internal/errors/<code>
        "title": HTTPStatus(status).phrase,
        "status": status,
        "code": code.value,
        "request_id": request_id_var.get(),
    }
    ...
```

New codes added to the API spec table in the same change: `request.method_not_allowed` (405) and `server.internal_error` (500); `resource.not_found` is also returned for unknown paths.

#### Request ID, request log, last-resort 500 (`app/core/middleware.py`)

A pure ASGI middleware sets the request ID (client `X-Request-ID` is echoed if it matches `[A-Za-z0-9._-]{1,128}`, otherwise a new one is generated), adds it to every response, logs method/path/status/duration (no headers, query strings or bodies), and turns unhandled exceptions into a generic 500 problem inside the request context so it still carries the ID.

```python
try:
    await self.app(scope, receive, send_wrapper)
except Exception:
    logger.exception("unhandled_error")
    if response_started:
        raise
    response = problem_response(ErrorCode.SERVER_INTERNAL_ERROR, HTTPStatus.INTERNAL_SERVER_ERROR)
    await response(scope, receive, send_wrapper)
```

Logs are one JSON object per line (`app/core/logging.py`): `timestamp`, `level`, `logger`, `message`, `request_id`, plus `extra=` fields. Uvicorn's access log is disabled because it would include query strings.

#### Health (`app/core/health.py`)

```python
@router.get("/ready", response_model=HealthStatus, openapi_extra=access(AccessLevel.PUBLIC), ...)
async def ready(request: Request, response: Response) -> HealthStatus:
    ...
    try:
        async with asyncio.timeout(settings.health_check_timeout_seconds):
            is_ready = await _database_ready(engine)   # SELECT 1 + alembic_version == script heads
    except Exception:
        logger.warning("readiness_check_failed", exc_info=True)
        is_ready = False
    if not is_ready:
        response.status_code = 503
        return HealthStatus(status="unavailable")
    return HealthStatus(status="ok")
```

`/api/health/live` checks nothing. Both return only `{"status": ...}`.

#### OpenAPI and docs (`app/main.py`)

`/api/v1/openapi.json` and `/api/docs` are published only when `ENV` is not `production`. In production they stay off until Phase 1 can restrict the document to signed-in users and integration clients (API spec §2).

#### Access levels and the route catalog (ADR 0012)

Each route declares its access level with the spec's wording:

```python
@router.get("/live", ..., openapi_extra=access(AccessLevel.PUBLIC))   # -> "x-access-level": "Public"
```

`tests/api/test_route_catalog.py` parses every `| METHOD | `/path` | … | Access | … |` row in `docs/05-api-specification.md` (153 endpoints) and checks:
- every registered route is in the catalog and its declared level equals the spec;
- every catalog entry is either built or listed in `tests/api/catalog_pending.py` (149 pending; each phase removes what it builds);
- no route uses `include_in_schema=False` (routes are read from the OpenAPI document, because FastAPI 0.163 nests included routers in private structures).

#### Module boundaries (`backend/pyproject.toml`, ADR 0001)

14 import-linter contracts, including:

```toml
[[tool.importlinter.contracts]]
name = "Module dependency direction (nothing depends on assistant or integration)"
type = "layers"
containers = ["app.modules"]
layers = [
    "assistant | integration",
    "dataimport | reporting | audit",
    "activity",
    "sales",
    "party",
    "identity",
]

[[tool.importlinter.contracts]]
name = "Routers never touch the database"
type = "forbidden"
source_modules = ["app.modules.*.router"]
forbidden_modules = ["app.modules.*.repository", "app.modules.*.models", "sqlalchemy"]

[[tool.importlinter.contracts]]
name = "Only app.llm may import litellm"
type = "forbidden"
source_modules = ["app.main", "app.worker", "app.cli", "app.core", "app.modules"]
forbidden_modules = ["litellm"]
```

Plus "inside a module: router > service > repository > models", "entry points > modules > llm > core", and one "internals are private" contract per module (other modules may not import its router, repository or models). Verified by injecting violations: the litellm, router-to-DB and cross-module-repository contracts all reported BROKEN, then the probes were removed.

#### Database roles and migrations (ADR 0005)

`deploy/postgres/init-roles.sh` (idempotent; run by the Postgres container on first start and by CI) creates `crm_migrator` (owns the database and schema, runs Alembic) and `crm_app` (DML only via default privileges):

```sql
ALTER SCHEMA public OWNER TO crm_migrator;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO crm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE crm_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO crm_app;
```

Baseline migration `0001` only enables `pg_trgm` (needed for Cyrillic-aware partial-match search from Phase 2). Alembic uses `MIGRATION_DATABASE_URL`; the app uses `DATABASE_URL`. SQLAlchemy `Base` has a naming convention so constraint names are deterministic.

Migration tests (`tests/migrations/test_migrations.py`):

```python
def test_NFR_12_every_migration_upgrades_and_downgrades(migrated_database: str) -> None:
    config = alembic_config(migrated_database)
    command.downgrade(config, "base")
    for revision in _revisions_base_to_head(migrated_database):
        command.upgrade(config, revision)
        command.downgrade(config, "-1")
        command.upgrade(config, revision)
    command.upgrade(config, "head")
```

plus "models match migrations" (Alembic `compare_metadata` must be empty), `pg_trgm` installed, and "the application role cannot run DDL" (`permission denied`).

#### Worker and CLI

`python -m app.worker` runs registered jobs every `WORKER_POLL_INTERVAL_SECONDS` until SIGTERM/SIGINT; one failing job is logged and does not stop the others. No jobs exist yet (outbox delivery and housekeeping arrive in Phase 6).

`python -m app.cli export-openapi [--output FILE]` writes the OpenAPI document; the frontend generates its types from it.

#### Tests

Tests run against a real PostgreSQL database (`TEST_DATABASE_URL` for migrations as `crm_migrator`, `TEST_APP_DATABASE_URL` for the app as `crm_app`; database `crm_test`). Test names carry requirement IDs where one applies (`test_NFR_08_ready_is_503_when_migrations_are_behind`). 197 tests: config, logging, problem details and request IDs, worker, CLI, health (ok / migrations behind / database unreachable / status-only body), OpenAPI published in dev and hidden in production, route catalog, migrations.

### Frontend

**Versions** (exact pins in `frontend/package.json`): React 19.3.1, Vite 8.3.8, TypeScript 6.0.3, React Router 8.5.1, TanStack Query 5.107.1, i18next 27.1.3 / react-i18next 18.0.2, openapi-fetch 0.17.0, openapi-typescript 7.13.0, Tailwind CSS 4.3.5, shadcn/ui (Base UI 1.9.0, `cn` 0.5.2), ESLint 10.15, typescript-eslint 8.72.2, eslint-plugin-i18next 6.1.5, Prettier 3.10.1, Vitest 5.1.0, Testing Library, MSW 3.0.6, Playwright 1.65.1. Runtime images use Node 26.13.1 LTS.

#### Typed API client (`src/api/client.ts`)

```ts
export const api = createClient<paths>({
  baseUrl: globalThis.location.origin,
  credentials: 'same-origin',
  headers: { 'X-Requested-With': 'XMLHttpRequest' },
  // Resolve fetch per call so test doubles (MSW) installed later are used.
  fetch: (request) => globalThis.fetch(request),
})
```

`paths` comes from `src/api/schema.d.ts`, generated by `pnpm generate:api [file|url]` (`scripts/generate-api.mjs`, default source `http://localhost:8000/api/v1/openapi.json`). Components never call `fetch`; they use TanStack Query hooks such as:

```ts
export function useApiHealth() {
  return useQuery({
    queryKey: ['system', 'health', 'ready'],
    queryFn: async ({ signal }): Promise<ApiHealth> => {
      try {
        const { data } = await api.GET('/api/health/ready', { signal })
        return data?.status === 'ok' ? 'ok' : 'unavailable'
      } catch {
        return 'unavailable'
      }
    },
    refetchInterval: 30_000,
    retry: false,
  })
}
```

#### i18n (`src/i18n/`)

One JSON file per namespace and language (`common`, `auth`). Keys are typed, so `t('missing.key')` does not compile:

```ts
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: typeof defaultNS
    resources: (typeof resources)['en']
  }
}
```

The language comes from a stored choice, else the browser language (`bg*` → Bulgarian, otherwise English) (`src/lib/locale.ts`). Until Phase 1 stores it on the user profile, the choice lives in `localStorage` (`crm.locale`), a preference, not a token. `pnpm check:i18n` fails when a key exists in one language only.

#### Lint rules for the hard rules (`eslint.config.js`)

```js
'no-restricted-syntax': ['error', {
  selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
  message: 'dangerouslySetInnerHTML is forbidden (architecture section 7).',
}],
'no-restricted-globals': ['error', {
  name: 'fetch',
  message: 'Use the typed client in src/api through a TanStack Query hook.',
}],
// in src/**/*.tsx:
'i18next/no-literal-string': ['error', {
  mode: 'jsx-only',
  'jsx-attributes': { include: ['alt', 'aria-label', 'aria-description', 'title', 'placeholder', 'label'] },
}],
```

Plus `typescript-eslint` strict and stylistic type-checked presets (no `any`), React Hooks rules and Prettier. Verified with a probe component: all four violations were reported.

#### Pages

- `/` redirects to `/sign-in` until authentication exists.
- `/sign-in`: email/password form, disabled, with a translated "not available yet" note.
- Layout: app name, language switch ("English" / "Български", `aria-pressed`), footer with the API readiness status; sets `<html lang>` and the document title.
- Unknown paths: translated not-found message; any route error: translated generic message (no error details).

#### Tests

Vitest + Testing Library + MSW (11 tests): redirect, disabled form, Bulgarian rendering, language switch remembered, not-found, API online/unavailable, locale detection. Playwright smoke (`e2e/smoke.spec.ts`, Chromium and Firefox): sign-in over HTTPS with HSTS in English, Bulgarian from the browser locale, language switch, proxy security headers, readiness through the proxy.

### Deployment

#### Compose (`docker-compose.yml`, ADR 0011)

Services: `db` (PostgreSQL 18.7, roles from the init script), `migrate` (one-shot `alembic upgrade head`), `backend` (Uvicorn, read-only root FS), `worker`, `proxy` (Caddy with the built SPA), `backup` (nightly `pg_dump`, 30-day retention, `TZ=Europe/Sofia`). Only `proxy` publishes ports (80, 443). Database URLs are composed from `CRM_APP_PASSWORD` / `CRM_MIGRATOR_PASSWORD` in `.env`.

`docker-compose.dev.yml`: `ENV=development`, backend on `:8000` with `--reload` and `/api/docs`, PostgreSQL on `:5432`, extra `crm_test` database.

#### Caddy (`deploy/caddy/Caddyfile`)

```caddy
{$CRM_SITE_ADDRESS:localhost} {
	tls {$CRM_TLS:internal}
	header {
		Strict-Transport-Security "max-age=31536000; includeSubDomains"
		X-Content-Type-Options "nosniff"
		Referrer-Policy "strict-origin-when-cross-origin"
		Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
		...
	}
	handle /api/* { reverse_proxy backend:8000 }
	handle { root * /srv/www; try_files {path} /index.html; file_server }
}
```

#### Start scripts

`scripts/start-{mac,linux}.sh` (shared `_start-unix.sh`) and `start-windows.ps1`: on first run create `.env` from `.env.example` with three random 48-hex-character database passwords (`chmod 600`), `docker compose up --build --detach`, then wait up to 3 minutes for `https://<host>/api/health/ready`. Stop scripts run `docker compose down` (volumes and backups kept).

### CI (`.github/workflows/ci.yml`)

| Job | Steps |
|---|---|
| backend | PostgreSQL 18.7 service, `init-roles.sh`, `uv sync --frozen`, ruff check + format, mypy, lint-imports, pytest (coverage ≥ 75%), pip-audit on the hashed lock export |
| frontend | `pnpm install --frozen-lockfile`, lint (ESLint + Prettier), typecheck, Vitest, i18n parity, `pnpm audit --audit-level high` |
| contract | export OpenAPI from the backend → `pnpm generate:api` → `git diff --exit-code src/api/schema.d.ts` |
| e2e | `.env` with random passwords, `docker compose up --build`, wait for readiness, Playwright (Chromium, Firefox), logs and report uploaded on failure |

Actions are pinned by commit SHA (checkout v7.0.1, setup-node v7.1.0, pnpm/action-setup v6.1.1, setup-uv v10.3.3, upload-artifact v7.0.2).

### Verification (2026-11-17, on the developer Mac)

Docker was not installed, so the stack was checked locally with equivalent pieces: PostgreSQL 18.7 (conda-forge, session scratch folder, not a project dependency) with `init-roles.sh` applied twice, `alembic upgrade head`, Uvicorn with `ENV=production`, the built SPA, and Caddy 2.11.9 with the project Caddyfile (`caddy validate`: valid; local copy on port 8443 pointing at 127.0.0.1).

| Gate | Result |
|---|---|
| ruff check / format | pass / 97 files formatted |
| mypy (strict) | no issues in 97 files |
| import-linter | 14 kept, 0 broken |
| pytest | 197 passed; coverage 93.1% |
| pip-audit | no known vulnerabilities |
| ESLint + Prettier | pass |
| tsc | pass |
| Vitest | 11 passed |
| i18n parity | pass (16 keys, en/bg) |
| pnpm audit (high) | pass. One **moderate** advisory: `minimatch` < 11.0.1 (GHSA-g3hv-75wg-m249), only through dev tooling (typescript-eslint, shadcn CLI) |
| Contract drift | generated types up to date |
| Playwright, Chromium | 5 passed against `https://localhost:8443` |
| Playwright, Firefox | 2 passed (HTTP-only tests); 3 browser tests **could not run**: Firefox 159 fails to start on this Mac ("Could not find profile folder"), also outside the sandbox. A local machine issue, not a test failure; CI on Ubuntu runs them |
| Proxy headers | HSTS, CSP, nosniff, Referrer-Policy, Permissions-Policy present; `X-Request-ID` passes through |
| Production mode | `/api/v1/openapi.json` returns 404 |
| `scripts/start-mac.sh` (Docker Desktop 29.9, Compose 5.7) | stack up first time: db healthy, migrate exited 0, backend healthy (runs as uid 10001), worker started, proxy on 80/443; database owned by `crm_migrator` with `pg_trgm` |
| Playwright vs. composed stack | Chromium 5 passed; Firefox same local launch issue as above |
| Backup | `backup.sh --now` wrote a custom-format dump; scheduler waits for 02:00 Europe/Sofia |
| Dev override | backend on `http://localhost:8000`, ready `ok`, OpenAPI published (200) |
| GitHub Actions (PR #1, run 44084724475) | all four jobs green: backend 39 s, frontend 28 s, contract 29 s, e2e 2 min 3 s; Playwright 10/10 including Firefox |

### Phase 0 definition of done

| # | Item | State |
|---|---|---|
| 1 | Acceptance criteria as tests named with requirement IDs | Done for the Phase 0 scope (NFR-04, NFR-08, NFR-12, FR-I18N-01, FR-INT-10) |
| 2 | `docker compose up` from a clean checkout works | Done (`scripts/start-mac.sh`) |
| 3 | Lint, types, all suites green | Done locally and in CI |
| 4 | New endpoints have permission checks and are in the authorization test | Health endpoints are Public and checked by the route-catalog test; the role matrix starts in Phase 1 |
| 5 | UI text in English and Bulgarian | Done; Bulgarian wording should be reviewed by a native speaker |
| 6 | Additive migrations passing migration tests | Done |
| 7 | Audit entries on create/update/delete | N/A (no business data yet; audit module is Phase 1) |
| 8 | Frontend types regenerated and committed | Done |
| 9 | Endpoints match the API spec | Done; spec updated with two new error codes |

### Decisions and deviations

- **Node 26 LTS** in Docker and CI instead of the Node 24 discussed at planning: 26 became the active LTS in October 2026 (24 is in maintenance); local development works on 24+.
- **TypeScript 6.0** rather than 7.0: typescript-eslint supports TypeScript < 6.1 (ADR 0002).
- **shadcn/ui** now builds on Base UI with the `cn` package and the self-hosted Geist font; `lucide-react`, `clsx` and `tailwind-merge` were not kept because nothing needs them yet.
- The **`Principal`** type is left to Phase 1, where the architecture places it, rather than added as an unused stub.
- **Route catalog** checks use the OpenAPI document (ADR 0012).
- The **interactive docs** (`/api/docs`) load Swagger UI from a CDN, which the proxy's CSP blocks; use them on `http://localhost:8000/api/docs` with the dev stack.
- **CRM name**: the UI shows "Light CRM" as a placeholder product name.

### Open items

1. Owner review and merge of PR #1 (https://github.com/dsugarev/Light_CRM/pull/1).
2. Bulgarian UI texts accepted for now by the owner (2026-11-17); revisit if needed.

Repository history: the GitHub repository starts from a clean root (the specifications commit). The Prelegal history is kept only locally, on branches `prelegal-archive` and `phase-0-foundation-prelegal-based`.

Carried to later phases (spec observations, not blocking):
- **Phase 2:** `contact` has no `owner_id`, but the API filters contacts by owner (ownership follows the organization); `organization` lacks `notes` and spells out no address columns.
- **Phase 3:** `lead.estimated_value` has no `currency` column, but the API returns `currency`.
- **Phase 5:** the requirements limit Sales Rep exports to their own data and Viewers make no changes, while the API spec opens every export to any signed-in user.
- **Phase 7:** the Cerebras skill uses `reasoning_effort="low"` and no `allow_fallbacks`; the architecture sketch differs. The skill wins (ADR 0007).

---

## Phase 1 — Identity, access and audit

Requirements: FR-AUTH-01 to 06, FR-ADM-01, FR-ADM-03, FR-I18N-01 to 03. Exit: an Admin creates a Sales Rep, who sets a password and signs in; every action appears in the audit log.

Owner decisions at the start (2026-11-17): build `/settings` now (session timeouts only); optional SMTP sender with the standard library; bundle the SecLists common-password list; add `argon2-cffi`, `factory-boy`, `react-hook-form`, `zod`, `@hookform/resolvers`; a simple paginated user table until Phase 2.

### Tasks

| # | Task | Result |
|---|---|---|
| 1.1 | Schema: `role`, `app_user`, `user_session`, `password_token`, `audit_log`, `app_setting`, `rate_limit_bucket`; `updated_at` trigger; seeds; append-only audit grants | Done: migration `0002` |
| 1.2 | Principal, single policy, `endpoint()` declaration + enforcement, Argon2id, password policy, `AuthProvider`, CSRF, rate limits, injectable clock | Done (ADR 0013, 0015) |
| 1.3 | Audit module and domain event bus | Done (ADR 0014) |
| 1.4 | Identity service and endpoints (§3, §4, §5), settings (§6.1), system info (§2), audit log (§16) | Done: 26 endpoints |
| 1.5 | Route × role authorization matrix | Done |
| 1.6 | `create-admin` CLI | Done (link, or `--password-stdin`) |
| 1.7 | Frontend foundation: forms, current user, 401 handling, `can()`, error codes, Sofia time formatting | Done |
| 1.8 | Sign-in, set/forgot password, profile, users admin, audit log viewer, settings; en + bg | Done |
| 1.9 | Playwright journey 1 (en + bg), cookie flags, CSRF | Done |
| 1.10 | Gate, ADRs, docs, PR | Done; see Verification |

### Endpoints built (26)

`GET /system/info`; `POST /auth/login`, `/auth/logout`, `/auth/password/set`, `/auth/password/forgot`, `/auth/password/change`, `GET /auth/password/token/{token}`; `GET|PATCH /me`, `GET /me/sessions`, `DELETE /me/sessions/{session_id}`; all of §5 (`/users/lookup`, `/users`, `/users/{id}` and its `deactivate`, `activate`, `password-reset`, `unlock`, `sessions`, `/roles`); `GET|PATCH /settings`; `GET /audit-log`, `/audit-log/{entry_id}`. Plus: the OpenAPI document in production is served to signed-in callers only.

Not built yet (still in `tests/api/catalog_pending.py`): MFA endpoints (FR-AUTH-07, Phase 8), `/me/tasks` (Phase 4), `/audit-log/export` (Phase 5, with the export machinery).

### Backend

#### Declaring and enforcing access (`app/core/auth.py`, `app/core/policy.py`)

```python
@users_router.get("", summary="Full user list ...", **endpoint(AccessLevel.ADMIN))
async def list_users(ctx: Ctx, q: ... = None, ...) -> UserPage:
    ...

def endpoint(level: AccessLevel, *, scope: str | None = None) -> dict[str, Any]:
    """Keyword arguments for a route decorator: declared level + its enforcement."""
    return {
        "openapi_extra": access(level, scope),                       # x-access-level in OpenAPI
        "dependencies": [Depends(_requirement(level, scope))],       # check_access + per-user rate limit
    }

def check_access(principal: Principal | None, level: AccessLevel, scope: str | None = None) -> None:
    if level is AccessLevel.PUBLIC:
        return
    if principal is None:
        raise AppError(ErrorCode.AUTH_SESSION_EXPIRED, HTTPStatus.UNAUTHORIZED)
    if principal.is_integration:
        _check_integration(principal, level, scope)   # not_for_integrations / scope_missing
        return
    if principal.role not in _ROLES_BY_LEVEL[level]:
        raise AppError(ErrorCode.PERMISSION_DENIED, HTTPStatus.FORBIDDEN)
```

Core never imports identity: `app.main` wires `app.state.authenticator = identity_service.authenticate_request`.

#### Sessions (`identity/service.py`)

Opaque 256-bit token in the `session` cookie (`HttpOnly; Secure; SameSite=Strict; Path=/api`), only its SHA-256 stored. On each request:

```python
expired = (
    now >= user_session.expires_at                       # absolute timeout (default 7 days)
    or now - user_session.last_seen_at > idle_limit      # idle timeout (default 8 hours)
    or not user.is_active
    or not user.is_human
)
if expired:
    await repository.delete_session(session, user_session.id)
    ...
if now - user_session.last_seen_at >= _TOUCH_INTERVAL:  # write last_seen at most once a minute
    user_session.last_seen_at = now
```

Sign-out deletes the row; a password change deletes all the user's other sessions; set/reset password and deactivation delete all of them.

#### Sign-in and lockout (FR-AUTH-01)

```python
if not await provider.verify_credentials(user, password):
    user.failed_login_count += 1
    await _publish(ctx, "auth.login_failed", ..., details={"email": user.email, "reason": "bad_password"})
    if user.failed_login_count >= ctx.settings.login_max_failed_attempts:          # 5
        user.locked_until = ctx.now + timedelta(minutes=ctx.settings.login_lockout_minutes)  # 15
        user.failed_login_count = 0
        await _publish(ctx, "auth.account_locked", ...)
    await ctx.session.commit()      # audit survives the failed request
    raise AppError(ErrorCode.AUTH_INVALID_CREDENTIALS, HTTPStatus.UNAUTHORIZED)
```

Unknown emails run a dummy Argon2 verification so timing does not reveal them; inactive and service users get the same generic error. A locked account answers `423 auth.account_locked` with `locked_until`.

#### Passwords (FR-AUTH-03)

Argon2id with OWASP parameters (`m=19 MiB, t=2, p=1`), hashed in a thread. Policy: 12–128 characters and not in the bundled 10,000 common passwords (case-insensitive) → `422 auth.password_policy` with field codes `password.too_short | too_long | too_common`.

One-time links (`/set-password#token=…`; the token travels in the URL fragment, which browsers never send to servers, and the request log masks `/auth/password/token/***`). Set links last 72 hours, reset links 2 hours (`PASSWORD_SET_TOKEN_HOURS`, `PASSWORD_RESET_TOKEN_HOURS`). A new link voids older unused ones.

#### CSRF, credentials, rate limits

```python
async def csrf_protect(request: Request) -> None:      # dependency on the whole /api/v1 router
    if request.method in _SAFE_METHODS or "authorization" in request.headers:
        return
    if request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE:
        raise AppError(ErrorCode.AUTH_CSRF_FAILED, HTTPStatus.FORBIDDEN)
    origin = request.headers.get("origin")
    if origin is not None and origin.rstrip("/") not in settings.trusted_origins:
        raise AppError(ErrorCode.AUTH_CSRF_FAILED, HTTPStatus.FORBIDDEN)
```

Cookie + `Authorization` together → `400 auth.mixed_credentials`; a bearer key alone → `401 auth.api_key_invalid` until Phase 6. Rate limits (PostgreSQL fixed windows, `Retry-After` on 429): sign-in 10/min per IP, password endpoints 5 per 15 min per IP, 600/min per user.

#### Audit (ADR 0014)

```python
async def record(session: AsyncSession, event: DomainEvent) -> None:   # subscribed in app.main
    actor = event.actor
    repository.add(session, AuditLog(
        occurred_at=event.occurred_at,
        actor_id=actor.user_id if actor else None,
        actor_type=actor.type.value if actor else "anonymous",
        actor_label=actor.display_name if actor else None,
        action=event.action, entity_type=event.entity_type, entity_id=event.entity_id,
        before=_payload(event.before), after=_payload(event.after),   # secret keys stripped
        details=_payload(event.details) or None,
        ip=client_ip_var.get(), request_id=request_id_var.get(),
    ))
```

```sql
-- migration 0002
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM crm_app;
GRANT SELECT, INSERT ON audit_log TO crm_app;
```

Actions recorded: `auth.login_succeeded|login_failed|account_locked|logout|password_set|password_changed|password_reset_requested`, `user.created|updated|role_changed|deactivated|activated|password_reset_issued|unlocked|sessions_revoked`, `session.revoked`, `settings.updated`.

#### User administration rules

- Email unique case-insensitively (`409 conflict.duplicate`, field `user.email_taken`).
- An Admin cannot deactivate themselves (`403 permission.denied`) or leave no active Admin by demotion or deactivation (`409 permission.last_admin`, added to the spec).
- `users/lookup` lists active human users only; service users never appear.

#### Operations

```bash
docker compose exec backend python -m app.cli create-admin --email admin@company.bg --full-name "First Admin"
# Created admin admin@company.bg (…).
# Set the password here (valid until 2026-11-20 09:00 UTC):
# https://crm.company.bg/set-password#token=…
echo "$PASSWORD" | docker compose exec -T backend python -m app.cli create-admin ... --password-stdin   # automation
```

The worker purges expired sessions, stale password tokens and old rate-limit windows hourly.

#### Tests

391 backend tests, 95% coverage (identity service 96%, policy 97%). Highlights:
- `tests/api/test_authorization_matrix.py`: every API route × anonymous/admin/manager/rep/viewer, expectations from the spec's access levels; verified to fail when a route's level is weakened.
- `tests/api/test_auth.py`: cookie flags, generic errors, lockout and release after 15 minutes, idle (8 h) and absolute (7 d) timeouts with a frozen clock, configurable timeouts, sign-out invalidation, password change revoking other sessions, one-time and expiring links, SMTP on/off, CSRF, mixed credentials, rate limits with `Retry-After`.
- `tests/api/test_users.py`, `test_me_settings_audit.py`: admin rules, audit before/after values, no secrets in the log, application role cannot UPDATE/DELETE `audit_log`.
- `tests/unit/test_policy.py`: role matrix and integration scopes (`not_for_integrations`, `scope_missing` with `required_scope`).

### Frontend

- `api.call()` unwraps openapi-fetch results and throws `ApiError(status, code, errors)`; a 401 anywhere clears the current user and redirects to `/sign-in?next=…` (only same-site paths are accepted).

```ts
export async function call<T>(request: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await request
  if (!response.ok) {
    const problem = (error && typeof error === 'object' ? error : {}) as Problem
    throw new ApiError(response.status, problem)
  }
  return data as T
}
```

- Server codes are translated: `errors.json` is nested by code (`auth.invalid_credentials` → `errors:auth.invalid_credentials`); field errors from 422 problems are put on the form fields (`applyServerErrors`).
- `useMe()` (GET /me) drives `RequireAuth`, `RequirePermission` and `useCan()`; the UI follows the profile language and the language switch saves it on the profile (FR-I18N-01).
- Dates are shown in Europe/Sofia (`Intl.DateTimeFormat(..., { timeZone: 'Europe/Sofia' })`), numbers and EUR per locale (FR-I18N-03).
- Screens: sign-in, set password, forgot password, profile (details, language, password, sessions), users (list with URL filters, create with one-time link panel, detail with edit, deactivate/activate, unlock, reset link, end sessions), audit log (filters, entry detail with before/after as escaped text), settings.
- 207 translation keys in English and Bulgarian; 43 Vitest tests.

#### End-to-end (`frontend/e2e/identity.spec.ts`)

Journey 1 in English and in Bulgarian: the Admin creates a Sales Rep → the rep opens the one-time link in a separate browser session, sets a password, signs in (cookie flags checked) → five wrong passwords lock the account → the audit log shows "User created" and "Account locked". The E2E Admins are created with `create-admin --password-stdin`; CI does this and raises the per-IP limits because all browsers share one IP.

### Verification (2026-11-17)

| Gate | Result |
|---|---|
| ruff, format, mypy (strict), import-linter (14 contracts) | clean |
| pytest (scratch PostgreSQL 18.7) | 391 passed, 95.3% coverage |
| pip-audit | no known vulnerabilities |
| ESLint, Prettier, tsc, i18n parity (207 keys) | clean |
| Vitest | 43 passed |
| pnpm audit (high) | pass; the moderate `minimatch` advisory (dev tooling) remains |
| Contract drift | types up to date |
| Docker stack | rebuilt; migration 0002 applied; two admins created with the CLI |
| Playwright on Chromium vs. the stack | 9/9, three consecutive runs |
| Playwright on Firefox | runs in CI (local Firefox still cannot start on this Mac) |
| GitHub Actions | PR #2 (run 44093849594) and `main` after merge (run 44094038484): all four jobs green; Playwright journey 1 passed on Chromium and Firefox |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests named with requirement IDs | Done for FR-AUTH-01..06, FR-ADM-01, FR-ADM-03, FR-I18N-01..03 |
| 2 | `docker compose up` works | Done |
| 3 | Lint, types, suites green | Done locally and in CI |
| 4 | Permission checks + authorization matrix | Done for all 26 routes |
| 5 | UI text in en and bg | Done |
| 6 | Additive migrations passing migration tests | Done (0002, up/down/drift) |
| 7 | Audit entries for create/update/delete | Done, asserted per endpoint |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec updated with `permission.last_admin` and password field codes |

### Decisions and deviations

- **Tables beyond the architecture list:** `app_setting` (single row) and `rate_limit_bucket` live in core (ADR 0015); `audit_log` adds `actor_type`, `actor_label`, `details` (ADR 0014).
- **`/settings` holds only session timeouts** for now; stale-opportunity days, AI limits and MFA enforcement are added by their phases as new columns.
- **Link lifetimes:** set-password 72 hours, reset 2 hours (configurable). Please confirm these suit the team.
- **Forgot password without SMTP** does nothing (still `202`), so the Admin reset flow is the fallback, as the spec says.
- **Common-password list:** only 10 of the 10,000 entries are 12+ characters, so with the 12-character minimum the list adds little protection. A longer list (e.g. 100k) could be swapped in later.
- **Email validation** uses a simple shape check instead of `email-validator`, which was not on the approved dependency list.
- **Integration principals** are covered by policy unit tests; they join the HTTP matrix in Phase 6 when API keys exist.
- **Accessibility fix** found by the E2E run: buttons used as links (`role="button"` on navigation) were replaced by real links styled as buttons.
- **Frontend typing:** i18next's context separator set to `|` because error-code keys contain underscores.

### Open items

1. ~~Owner review of PR for Phase 1~~ — merged 2026-11-17 (PR #2).
2. ~~Confirm the password link lifetimes (72 h / 2 h)~~ — confirmed by the owner on 2026-11-17.
3. SMTP relay details when available (open question 4); set `SMTP_*` in `.env`.

### Documentation update after Phase 1 (2026-11-17)

On the owner's instruction, before Phase 2:

- `docs/05-api-specification.md` v0.2: implementation-status table; CSRF scope and cookie details; sign-in, lockout, one-time link format and lifetimes, forgot/change password rules; `/me` and permission codes; user payloads and rules; settings fields; audit entry shape and recorded actions; field error codes; rate-limit variables.
- `docs/api/openapi.json`: committed OpenAPI snapshot; CI's contract job now fails when it is stale. `docs/api/README.md` explains how to view the documentation.
- `docs/Test_strategy.md`: new test record (levels as implemented, requirement coverage, per-phase strategy, cases, runs, defects, gaps) with an inventory generated by `scripts/test_inventory.py`:

```python
def backend() -> "OrderedDict[str, OrderedDict[str, int]]":
    out = run(["uv", "run", "pytest", "--collect-only", "-q", "--no-cov", "-p", "no:cacheprovider"], ROOT / "backend")
    ...                      # parametrised cases collapsed, requirement IDs parsed from test names
```

- CLAUDE.md: documentation is part of done; new rows for `Test_strategy.md` and `docs/api/`.

---

## Phase 2 — Organizations and contacts

Requirements: FR-PARTY-01 to 04, FR-ADM-02 (industries). Owner decisions at the start (2026-11-17, "accept the recommendations"): industries owned by party (ADR 0016); organization fields `address_line`, `postal_code`, `city`, `country`, `notes` and a fixed size-band list; EIK/VAT format checks with a checksum **warning**; duplicate rule by registration number or a name key that ignores script, case, punctuation and legal form, plus similar-name suggestions; cross-script search; the proposed 14 industries; `sonner` for toasts; a new `APP_SECRET_KEY`.

### Tasks

| # | Task | Result |
|---|---|---|
| 2.1 | Schema: `industry` (seeded), `organization`, `contact`; trigram and `(updated_at, id)` indexes | Done: migration `0003` |
| 2.2 | Shared list machinery: paging, sorting, filters, `include_archived`, sync mode with signed cursors | Done (ADR 0017) |
| 2.3 | Party service: CRUD, archive/restore, ownership, owner changes, duplicates, audit events | Done |
| 2.4 | Generic reference lists wired for `industries` | Done |
| 2.5 | Global search | Done |
| 2.6 | Backend tests | Done (517 total) |
| 2.7 | Reusable frontend pieces: URL list state, data table, toasts, empty/error states | Done |
| 2.8 | Screens: organizations (list, form, 360), contacts, industries admin, search | Done, en + bg |
| 2.9 | E2E journeys | Done (en, bg, ownership) |
| 2.10 | Documentation, gate, PR | Done |

### Endpoints built (20)

`/reference/{list}` (GET, POST, PATCH, PUT order, DELETE); `/organizations` (GET, POST), `/organizations/duplicate-check`, `/organizations/{org_id}` (GET, PATCH, DELETE), `/organizations/{org_id}/restore`, `/organizations/{org_id}/contacts`; `/contacts` (GET, POST), `/contacts/{contact_id}` (GET, PATCH, DELETE), `/contacts/{contact_id}/restore`; `/search`. Routes that integrations will use already declare their scope (`organizations:read`, `contacts:write`, `reference:read`, …) for Phase 6.

### Backend

#### Text normalisation (`app/core/text.py`, ADR 0016)

```python
def normalize_company_name(name: str) -> str:
    """Duplicate key ... "Акме ЕООД", "ACME e.o.o.d." and "Acme EOOD" all become "akme"."""
    words = _NON_WORD.sub(" ", fold(name).replace(".", "")).split()   # fold = transliterate + casefold + strip accents
    kept = [w for w in words if w not in _LEGAL_FORMS] or words      # ЕООД/ООД/АД/EAD/Ltd/GmbH...
    key = " ".join(kept)
    for latin, replacement in _PHONETIC:                              # c/q->k, w->v, x->ks, ph->f, kh->h
        key = key.replace(latin, replacement)
    return key
```

Transliteration follows the official Streamlined System, including word-final «-ия» → "-ia" (`София` → `sofia`). Searchable text stores every field both as typed and folded; a query term matches either form (`ILIKE` on a trigram GIN index).

#### Duplicates (FR-PARTY-01 AC1)

```python
if not data.confirm_duplicate:
    matches = await _duplicates(ctx, data.name, data.registration_number, None, similar=False)
    if matches:
        raise _duplicate_error(matches)        # 409 conflict.duplicate, extra={"matches": [...]}
```

`repository.organization_duplicates` collects exact matches on registration number and name key and, for the duplicate-check endpoint, similar names via `pg_trgm` (`name_normalized % :key`, ordered by `similarity`). Contacts match on email.

#### Ownership

```python
def _contact_owner_id(contact: Contact) -> UUID:
    """Ownership follows the organisation; without one, the creator (API spec section 8)."""
    if contact.organization is not None:
        return contact.organization.owner_id
    return contact.created_by
```

Every change loads the record and calls `check_owner(principal, owner_id)` (Owner+). Changing an organization's owner, or creating one for somebody else, requires Manager+; owners must be active people (`identity.service.is_assignable_owner`). The owner filter for contacts is a SQL condition over the organization's owner or the creator.

#### List machinery and sync mode (`app/core/listing.py`, ADR 0017)

```python
OrganizationList = Annotated[ListQuery, Depends(list_query(
    "organizations", sortable=("name", "created_at", "updated_at"), default_sort="name",
    filters=("owner_id", "industry_id", "city", "country", "size_band"),
))]
...
statement = statement.where(
    updated_at >= query.updated_since,
    updated_at < func.now() - text("make_interval(secs => :lag)").bindparams(lag=safety_lag_seconds),
)
if query.cursor is not None:
    statement = statement.where(tuple_(updated_at, id_column) > tuple_(literal(cursor.updated_at), literal(cursor.id)))
```

Cursors are `base64url(JSON) + "." + HMAC-SHA256` (128-bit) with `APP_SECRET_KEY`, bound to the list name.

#### Reference lists (`app/core/reference.py`)

Each module registers `ReferenceList(name, entity_type, model, usage_counter)`; `app.main` puts them in `app.state.reference_lists`. Deletion checks the usage counter (`409 reference.in_use`); changes are audited as `reference.*`.

#### EIK checksum (`app/modules/party/eik.py`)

9-digit: weights 1–8 mod 11, else 3–10, 10 → 0; 13-digit: additionally digits 9–12 with (2,7,3,5), else (4,9,5,7). A mismatch is returned as `warnings: [{field: "registration_number", code: "organization.registration_checksum"}]`.

### Frontend

- **Reusable:** `useListParams` (sort, page, `q`, filters, archived in the URL), `DataTable` (sortable headers with `aria-sort`), `SearchInput` (debounced), `ErrorState`, `Textarea`, toasts via `sonner`, `useCanEditOwned` (UI mirror of Owner+), `useUserLookup`, `useReferenceList` + `referenceName(item, locale)`, `asPage()` for list envelopes. List queries keep the previous rows while the next page loads.
- **Organizations:** list (search, owner "mine", industry, archived), form with a **live duplicate warning** while typing and a "Create anyway" after a 409, EIK checksum warning as a toast and on the 360 page, owner picker only with `records.reassign`, 360 page with counts, contacts, empty leads/opportunities/timeline sections, archive (confirm) and restore.
- **Contacts:** list, form with a searchable organization picker (thousands of organizations), email duplicates, detail with derived owner.
- **Admin → Lists:** industries (add, reorder ↑/↓, activate/deactivate, delete with the in-use explanation).
- **Search:** header box → `/search?q=` results grouped by type.
- 357 translation keys in English and Bulgarian; 59 Vitest tests (15 new).

```tsx
// Live duplicate check while typing (FR-PARTY-01 AC1)
const duplicates = useQuery({
  queryKey: ['organizations', 'duplicate-check', probe],
  queryFn: () => call(api.GET('/api/v1/organizations/duplicate-check', { params: { query: {...} } })),
  enabled: changedIdentity && (probe.name.length >= 2 || /^\d{9}(\d{4})?$/.test(probe.registration)),
})
```

### Deployment

- `APP_SECRET_KEY` required by Compose (`:?`), placeholder in `.env.example`, refused at its default in production. The start scripts generate it for new installations and **append it to an existing `.env`** (verified on this machine). CI generates one.

### Verification (2026-11-17)

| Gate | Result |
|---|---|
| ruff, format, mypy (strict), import-linter (14) | clean |
| pytest (scratch PostgreSQL 18.7) | 517 passed, 95.7% coverage (party service 93%, listing 98%, reference 98%) |
| pip-audit | no known vulnerabilities |
| ESLint, Prettier, tsc, i18n (357 keys) | clean |
| Vitest | 59 passed |
| pnpm audit (high) | pass; moderate dev-only `minimatch` advisory remains |
| Contract drift, OpenAPI snapshot | up to date |
| Docker stack via `scripts/start-mac.sh` | migration 0003 applied; `APP_SECRET_KEY` appended to `.env` |
| Playwright Chromium vs. stack | 12/12 in three consecutive runs (after fixing a test-data collision) |
| GitHub Actions (PR #4, run 44102245986) | all four jobs green: backend 1 min 15 s, frontend 46 s, contract 36 s, e2e 2 min 7 s (Playwright on Chromium and Firefox) |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | Done for FR-PARTY-01..04, FR-ADM-02, FR-I18N-04, FR-INT-05 (machinery) |
| 2 | `docker compose up` works | Done (start script) |
| 3 | Lint, types, suites green | Done locally and in CI |
| 4 | Permission checks + matrix | Done for all 46 routes; owner/non-owner cases for organizations and contacts |
| 5 | UI text en + bg | Done |
| 6 | Additive migrations + tests | Done (0003) |
| 7 | Audit for create/update/delete | Done (organization.*, contact.*, reference.*) |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec v0.3 with payloads, rules, field codes, `resource.archived` |

### Decisions and deviations

- **Industries in party**, not sales (ADR 0016).
- **No full-text (`tsvector`) search**: trigram `ILIKE` over folded text covers partial, cross-script matching for names; FTS can be added if long-text search is needed (ADR 0016).
- **Name sorting** uses the folded name, so Cyrillic and Latin names interleave alphabetically by their Latin form.
- **Reference values** are returned with both names (`name_en`, `name_bg`) rather than one translated `name`; the UI picks the language (the backend returns data, not translations).
- **Editing archived records** is refused with a new code `resource.archived` (409), added to the spec.
- **Duplicate check on rename**: a `PATCH` that changes the name or registration number into a duplicate also needs `confirm_duplicate`.
- **Organization counts** for leads and opportunities are `0` until those modules exist; archiving is not yet blocked by open opportunities (Phase 4).

### Open items

1. ~~Owner review of the Phase 2 pull request~~ — merged 2026-11-17 (PR #4).

---

## Phase 3 — Leads

Requirements: FR-LEAD-01, 02, 03, 05, 06, FR-ADM-02 (lead sources, disqualification reasons). FR-LEAD-04 (conversion) is Phase 4. Owner decisions (2026-11-17, "accept the recommendations"): score yes 25 / partial 12.5 / no and unknown 0, rounded, fit flag shown separately; a Sales Rep may take over any lead for themselves (audited); optional links to an existing organization and contact; a `currency` column on leads; the proposed seeded lists.

### Tasks

| # | Task | Result |
|---|---|---|
| 3.1 | Schema: `lead`, `lead_source`, `disqualification_reason` (seeded), score column, version, indexes | Done: migration `0004` |
| 3.2 | Lead service: lifecycle, BANT and score, version checks, owner/assign rules, audit | Done |
| 3.3 | Lists, global search, organisation leads and counts | Done via extension points (ADR 0018) |
| 3.4 | Backend tests | Done (614 total) |
| 3.5 | Screens: list, form, lead page with BANT and actions, lists admin, 360 leads | Done, en + bg |
| 3.6 | E2E | Done (en, bg) |
| 3.7 | Documentation, gate, PR | Done |

### Endpoints built (12)

`GET|POST /leads`, `GET|PATCH|DELETE /leads/{lead_id}`, `POST /leads/{lead_id}/restore|assign|mark-contacted|qualify|disqualify|reopen`, `GET /organizations/{org_id}/leads`; plus `lead-sources` and `disqualification-reasons` under `/reference/{list}` and leads in `/search`.

### Backend

#### Lifecycle and score (`app/modules/sales/lifecycle.py`)

```python
TRANSITIONS: Mapping[str, tuple[frozenset[str], str]] = {
    "mark_contacted": (frozenset({"new"}), "contacted"),
    "qualify": (frozenset({"contacted"}), "qualified"),
    "disqualify": (OPEN_STATUSES, "disqualified"),
    "reopen": (frozenset({"disqualified"}), "contacted"),
    "convert": (frozenset({"qualified"}), "converted"),  # Phase 4
}
_POINTS = {"yes": 25.0, "partial": 12.5, "no": 0.0, "unknown": 0.0}

def qualification_score(statuses: Mapping[str, str]) -> int:
    total = sum(_POINTS[statuses[item]] for item in BANT_ITEMS)
    return int(total + 0.5)          # the spec example yes/partial/yes/unknown -> 63
```

#### Optimistic concurrency and action-only fields (`sales/service.py`)

```python
async def _check_version(ctx: Context, lead: Lead, version: int) -> None:
    if lead.version != version:
        current = (await _leads_out(ctx, [lead]))[0]
        raise AppError(ErrorCode.CONFLICT_VERSION_MISMATCH, HTTPStatus.CONFLICT,
                       extra={"current": current.model_dump(mode="json")})
...
for field in ("status", "owner_id"):
    if field in data.model_fields_set:
        raise AppError(ErrorCode.VALIDATION_USE_ACTION_ENDPOINT, HTTPStatus.UNPROCESSABLE_CONTENT,
                       errors=[FieldError(field, "validation.use_action_endpoint")])
```

The row is locked (`SELECT … FOR UPDATE`) before the version comparison; every effective change increments `version` and publishes an audit event (`lead.status_changed`, `lead.owner_changed`, …). Converted and disqualified leads answer `409 lead.read_only`.

#### Extension points (ADR 0018)

```python
# app/main.py
app.state.search_providers = {p.type: p for p in (*party_service.SEARCH_PROVIDERS, *sales_service.SEARCH_PROVIDERS)}
app.state.organization_stats = (sales_service.organization_lead_stats,)
app.state.reference_lists = {ref.name: ref for ref in (*party_service.REFERENCE_LISTS, *sales_service.REFERENCE_LISTS)}
```

Party never imports sales: `GET /organizations/{id}` merges `{"open_leads": …}` from the registered provider, and `GET /search` (moved to `app/core/search.py`) runs one provider per type.

#### Other details

- `estimated_value` is `numeric(14,2)` with `currency` (default EUR) and travels as a decimal string; the serializer applies to JSON only.
- Links to an existing organization/contact are validated through party's public functions (`check_organization_link`, `contact_link`); a contact of another organization is refused.
- `AccessLevel.CONTRIBUTOR_RULES_IN_SERVICE` matches the spec wording for `assign`.

### Frontend

- `features/leads`: list (status, owner, source, fit, archived filters in the URL; score and value columns), capture/edit form (decimal comma accepted), lead page with **BANT editor** (live score using the same rule), **status actions** shown only when allowed (Qualify disabled with a hint while BANT is incomplete), a **disqualify form** requiring a reason, **reopen** for Manager+, **take over** for reps and **assign** for Manager+, archive/restore.
- `useLeadMutation`: on `409 conflict.version_mismatch` it shows the server's `current` lead and explains; other errors become translated toasts.
- Organization 360: real leads table with "New lead" prefilled; `/admin/reference/:list` manages all three lists; lead hits in search.
- 458 translation keys; 69 Vitest tests (10 new). Testing Library waits up to 3 s (was 1 s).

```tsx
{editable && lead.status === 'contacted' ? (
  <Button type="button" disabled={qualify.isPending || unknownBant.length > 0}
          title={unknownBant.length > 0 ? t('bant.incomplete') : undefined}
          onClick={() => { qualify.mutate(undefined) }}>
    {t('actions.qualify')}
  </Button>
) : null}
```

### Verification (2026-11-17)

| Gate | Result |
|---|---|
| ruff, format, mypy (strict), import-linter (14) | clean |
| pytest (scratch PostgreSQL 18.7) | 614 passed, 96% coverage (lead service 96%) |
| pip-audit | no known vulnerabilities |
| ESLint, Prettier, tsc, i18n (458 keys) | clean |
| Vitest | 69 passed (local run with a 60 s timeout because the machine was heavily loaded) |
| pnpm audit (high) | pass; moderate dev-only advisory remains |
| Contract drift, OpenAPI snapshot | up to date |
| Playwright Chromium vs. rebuilt stack | 14/14 in two consecutive runs (a first run under load timed out in 5 older tests) |
| GitHub Actions (PR #5, run 44116111752) | all four jobs green, including Vitest with default timeouts and Playwright on Chromium and Firefox |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | Done for FR-LEAD-01, 02, 03, 05, 06, FR-ADM-02 |
| 2 | `docker compose up` works | Done |
| 3 | Lint, types, suites green | Done locally and in CI |
| 4 | Permission checks + matrix | Done for all 58 routes; owner/non-owner lead cases |
| 5 | UI text en + bg | Done |
| 6 | Additive migrations + tests | Done (0004) |
| 7 | Audit for create/update/delete | Done (`lead.*`) |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec v0.4 (rules, payloads, `lead.read_only`) |

### Decisions and deviations

- **Extension points** for search and organisation figures (ADR 0018); `/search` moved from party to core (same URL and response).
- **`lead.read_only`** (409) is a new code for changes to converted or disqualified leads.
- **Reopen** clears the stored disqualification reason and note; the history stays in the audit log.
- **Assign** refuses converted and disqualified leads; reps may take over other reps' leads (owner decision).
- **Lead response**: `source` carries `name_en`/`name_bg` like other reference values (Phase 2 decision).

### Open items

1. ~~Owner review of the Phase 3 pull request.~~ Merged (PR #5).

---

## Phase 4a — Pipelines, opportunities and the board

Requirements: FR-OPP-01..06, FR-ADM-02 (stages, loss reasons). Phase 4 is delivered in two pull requests (owner decision, 2026-11-17, "accept the recommendations"): **4a** pipelines, opportunities and the board; **4b** activities and tasks, timelines, lead conversion and the full journey. Owner review follows 4b. Accepted recommendations used here: the six default stages with Bulgarian names; the board shows open stages plus Won/Lost drop areas that call `/close` (Lost asks for a reason) while `/move` stays between open stages; the seven seeded loss reasons; stale = no activity for N days (setting `stale_opportunity_days`, default 14) or the expected close date passed; dnd-kit for drag and drop.

### Tasks

| # | Task | Result |
|---|---|---|
| 4a.1 | Schema: `pipeline`, `pipeline_stage` (seeded), `loss_reason` (seeded), `opportunity`, `opportunity_stage_history`, FK `lead.converted_opportunity_id`, setting `stale_opportunity_days` | Done: migration `0005` |
| 4a.2 | Sales service becomes a package: `common`, `leads`, `pipelines`, `opportunities` | Done |
| 4a.3 | Stage administration with `stage.in_use` / `stage.required` | Done |
| 4a.4 | Opportunity rules: create, update, move, close, reopen, assign, archive, history, stale, board totals | Done |
| 4a.5 | Contributions to party/core: organisation figures, archive guard, search, loss-reasons list | Done (ADR 0018 pattern) |
| 4a.6 | Backend tests | Done (699 total; 26 new API tests + matrix/catalog growth) |
| 4a.7 | Screens: list, form, detail, board (dnd-kit), stage admin, settings, organisation 360 | Done, en + bg |
| 4a.8 | E2E: create, drag, move list, close lost from the board, Admin reopens and closes won | Done (en, bg) |
| 4a.9 | Documentation (spec v0.5, ADR 0019, snapshot, this log, test record), gate, PR | Done |

### Endpoints built (19)

`GET /pipelines`, `GET /pipelines/{pipeline_id}`, `POST /pipelines/{pipeline_id}/stages`, `PATCH|DELETE /pipelines/{pipeline_id}/stages/{stage_id}`, `PUT /pipelines/{pipeline_id}/stages/order`; `GET|POST /opportunities`, `GET /opportunities/board`, `GET|PATCH|DELETE /opportunities/{opp_id}`, `POST /opportunities/{opp_id}/restore|assign|move|close|reopen`, `GET /opportunities/{opp_id}/stage-history`, `GET /organizations/{org_id}/opportunities`; plus `loss-reasons` under `/reference/{list}` and opportunities in `/search`. 77 routes in total, all in the authorization matrix.

### Backend

#### Service package (`app/modules/sales/service/`)

`service.py` became a package; the router and `app.main` import only `app.modules.sales.service` (the `__init__` re-exports the public API), so the layer contracts are unchanged.

```python
# app/modules/sales/service/__init__.py
REFERENCE_LISTS = (*_LEAD_REFERENCE_LISTS, *opportunities.REFERENCE_LISTS)
SEARCH_PROVIDERS = (*_LEAD_SEARCH_PROVIDERS, *opportunities.SEARCH_PROVIDERS)
ORGANIZATION_STATS = (organization_lead_stats, organization_opportunity_stats)
ORGANIZATION_ARCHIVE_GUARDS = (organization_archive_guard,)
```

`common.py` holds what leads and opportunities share: `Context`, `not_found`, `invalid`, `use_action_endpoint`, `version_conflict`, `check_owner_choice`, `publish`.

#### Stages (`service/pipelines.py`)

```python
def _ensure_type_remains(pipeline: Pipeline, leaving: PipelineStage) -> None:
    """Every pipeline keeps one active stage of each type (open, won, lost)."""
    others = [s for s in pipeline.stages
              if s.id != leaving.id and s.is_active and s.stage_type == leaving.stage_type]
    if leaving.is_active and not others:
        raise AppError(ErrorCode.STAGE_REQUIRED, HTTPStatus.CONFLICT,
                       extra={"stage_type": leaving.stage_type})

async def delete_stage(ctx, principal, pipeline_id, stage_id) -> None:
    ...
    if await repository.stage_usage(ctx.session, stage.id) > 0:   # opportunities + history
        raise AppError(ErrorCode.STAGE_IN_USE, HTTPStatus.CONFLICT)
```

#### Opportunity rules (`service/opportunities.py`)

```python
async def move(ctx, principal, opp_id, data: MoveRequest) -> OpportunityOut:
    opp = await _load(ctx, opp_id, data.version)          # row lock + version check
    check_owner(principal, opp.owner_id)                  # Owner+
    _ensure_open(opp)                                     # 409 resource.archived / opportunity.closed
    stage = _open_stage(await _pipeline_of(ctx, opp), data.stage_id)   # 422 stage.not_open
    ...
    if not opp.probability_overridden:
        opp.probability = stage.default_probability
    _record_stage(ctx, principal, opp, from_stage)        # FR-OPP-02 AC2
    return await _commit(ctx, principal, opp, "opportunity.stage_changed", before)

async def close(ctx, principal, opp_id, data: CloseRequest) -> OpportunityOut:
    if data.outcome == "lost":
        if data.loss_reason_id is None:
            raise AppError(ErrorCode.OPPORTUNITY_LOSS_REASON_REQUIRED, HTTPStatus.UNPROCESSABLE_CONTENT)
        ...
    stage = first_stage(await _pipeline_of(ctx, opp), data.outcome)
    opp.probability = stage.default_probability           # 100 or 0
    opp.actual_close_date = data.actual_close_date or today(ctx)   # business date in Sofia
```

#### Stale (FR-OPP-06) and board totals (`repository.py`)

```python
def stale_condition(stale_before: datetime, today: date) -> ColumnElement[bool]:
    return and_(
        PipelineStage.stage_type == "open",
        or_(func.coalesce(Opportunity.last_activity_at, Opportunity.created_at) < stale_before,
            Opportunity.expected_close_date < today),
    )

async def column_totals(session, statement) -> dict[UUID, tuple[int, Decimal, Decimal]]:
    sub = statement.order_by(None).subquery()
    weighted = func.coalesce(func.sum(sub.c.amount * sub.c.probability / 100), 0)
    rows = await session.execute(select(sub.c.stage_id, func.count(),
                                        func.coalesce(func.sum(sub.c.amount), 0), weighted)
                                 .group_by(sub.c.stage_id))
```

The same Python rule (`_is_stale`) fills `is_stale` on every response, with the threshold from the runtime settings (cached 30 s, ADR 0015). Board totals are computed over all matching rows, so they stay right when the cards are capped at 500 (`truncated: true`).

#### Organisation archive guard (party, ADR 0018 pattern)

```python
# party/service.py
OrganizationArchiveGuard = Callable[[AsyncSession, UUID], Awaitable[ErrorCode | None]]

async def archive_organization(ctx, principal, org_id) -> None:
    org = await _load_org_for_change(ctx, principal, org_id)
    if org.archived_at is None:
        for guard in ctx.organization_archive_guards:
            code = await guard(ctx.session, org.id)
            if code:
                raise AppError(code, HTTPStatus.CONFLICT)   # organization.has_open_opportunities
```

#### Migration 0005

Creates the five tables with `updated_at` triggers, adds the `lead → opportunity` foreign key announced in 0004 and the setting column, and seeds:

```sql
WITH p AS (INSERT INTO pipeline (id, name, is_default)
           VALUES (gen_random_uuid(), 'Sales pipeline', true) RETURNING id)
INSERT INTO pipeline_stage (id, pipeline_id, name_en, name_bg, position, default_probability, stage_type)
SELECT gen_random_uuid(), p.id, s.name_en, s.name_bg, s.position, s.probability, s.stage_type
FROM p, (VALUES ('Prospecting', 'Проучване', 1, 10, 'open'), ...,
                ('Closed Lost', 'Загубена', 6, 0, 'lost')) AS s (...);
```

Verified up → down → up on PostgreSQL 18.7 and with `alembic check` (no drift).

### Frontend

- `features/opportunities`: list (stage, status, owner, "needs attention", archived filters in the URL; amount, probability, weighted and expected-close columns), form (organisation picker on create, contacts of that organisation, decimal comma, empty probability = stage default), detail (stage move, close won/lost form, reopen for Manager+, take over / assign, archive/restore, stage history), organisation 360 section.
- **Board** (`BoardPage.tsx`) on `@dnd-kit/core` 6.3.1 + `@dnd-kit/utilities` 3.2.2: one droppable column per open stage with count, total and weighted total; Won and Lost drop areas; the pointer sensor (5 px activation) and the keyboard sensor with translated screen-reader announcements; a "Move to…" list on every editable card as a simple keyboard alternative. Cards the user may not edit (`can_edit: false`) have neither a drag handle nor the list (FR-OPP-03 AC2).

```tsx
const apply = (card: BoardCard, from: StageSummary, target: Target) => {
  if (target.kind === 'lost') { setLosing(card); return }          // ask for the loss reason
  if (target.kind === 'stage' && target.stageId === from.id) return
  change.mutate({ card, target })                                   // /move or /close (won)
}
```

- **Stage admin** (`/admin/stages`): rename in both languages, default probability, reorder, (de)activate, delete with the server's `stage.in_use` / `stage.required` explained; settings page gains the stale-days field; "Loss reasons" joins `/admin/reference/:list`.
- `AssignControl` moved to `features/auth` and is shared by leads and opportunities; `formatDay` formats calendar dates without a time-zone shift.
- 594 translation keys (en = bg); 82 Vitest tests (13 new).

### Verification (2026-11-17)

| Gate | Result |
|---|---|
| ruff, format, mypy (strict), import-linter (14) | clean |
| pytest (scratch PostgreSQL 18.7) | 699 passed, 96% coverage (opportunities 96%, pipelines 99%) |
| pip-audit | no known vulnerabilities |
| ESLint, Prettier, tsc, i18n (594 keys) | clean |
| Vitest | 82 passed (default timeouts) |
| pnpm audit (production) | no known vulnerabilities |
| Contract: OpenAPI snapshot regenerated, frontend types generated from it without diff | up to date |
| Playwright Chromium vs. rebuilt stack | 16/16 (two workers), including a real mouse drag on the board in both languages |
| GitHub Actions (PR #6, run 44124492826) | all four jobs green, including Playwright on Chromium and Firefox |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | Done for FR-OPP-01..06 (FR-OPP-06 activity part completes with 4b), FR-ADM-02 |
| 2 | `docker compose up` works | Done |
| 3 | Lint, types, suites green | Done locally |
| 4 | Permission checks + matrix | Done for all 77 routes; owner/non-owner and Manager+ reopen cases |
| 5 | UI text en + bg | Done |
| 6 | Additive migrations + tests | Done (0005) |
| 7 | Audit for create/update/delete | Done (`opportunity.*`, `pipeline_stage.*`) |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec v0.5 |

### Decisions and deviations

- **`move` stays between open stages**; won/lost only through `close` (owner decision; spec v0.5 changed the `move` row, which previously allowed a lost stage with a reason). ADR 0019.
- **Board stage summary** carries `name_en`, `name_bg` and `stage_type` instead of a single `name` (like reference values since Phase 2); the example in spec section 10 was updated before the endpoint was released.
- **New codes**: `opportunity.not_closed` (reopen of an open opportunity), `stage.required`, `organization.has_open_opportunities`; field codes `stage.not_open`, `stage.order_incomplete`.
- **`@dnd-kit/sortable` not used**: stage reordering uses up/down buttons like the reference lists, so only `@dnd-kit/core` and `@dnd-kit/utilities` are dependencies.
- The board's Won target closes immediately with today's date; the detail page's "Close as won" offers the date field.

### Open items

1. ~~Phase 4b~~: done, see below. Owner review of 4a + 4b.

---

## Phase 4b — Activities, timelines and lead conversion

Requirements: FR-ACT-01..03, FR-LEAD-04, the activity part of FR-OPP-06, and the Phase 4 exit: the Playwright journey lead → qualify → convert → progress → close won in English and Bulgarian (close lost and manager reopen are in the 4a journey). Accepted recommendations used here: a separate `timeline_event` table fed by domain events (ADR 0020); tasks can be assigned to any active user who can change records; the owner or the assignee completes and reopens; Owner+ archives.

### Tasks

| # | Task | Result |
|---|---|---|
| 4b.1 | Schema: `activity` (type check, at-least-one-link check, open-task index), `timeline_event` | Done: migration `0006` |
| 4b.2 | Activity service: create/update/archive, tasks (complete/reopen), `/me/tasks`, list filters and sync | Done |
| 4b.3 | Timelines: event subscriber, merged paged query, name resolution, four timeline endpoints | Done (ADR 0020) |
| 4b.4 | Opportunity freshness from activities (`last_activity_at`) | Done |
| 4b.5 | Lead conversion: preview and one-transaction convert (party create functions gain `commit=False`) | Done |
| 4b.6 | New access wordings for activities (spec 11) in the policy, matrix and catalog | Done |
| 4b.7 | Backend tests | Done (773 total; 20 new API tests + matrix/catalog growth) |
| 4b.8 | Screens: timeline with "Log activity" on lead, opportunity, organization and contact pages; My tasks; conversion screen; Convert button | Done, en + bg |
| 4b.9 | E2E: full journey in both languages | Done |
| 4b.10 | Documentation (spec v0.6, ADR 0020, snapshot, this log, test record), gate, PR | Done |

### Endpoints built (14)

`GET|POST /activities`, `GET|PATCH|DELETE /activities/{activity_id}`, `POST /activities/{activity_id}/complete|reopen`, `GET /me/tasks`, `GET /leads/{lead_id}/timeline`, `GET /opportunities/{opp_id}/timeline`, `GET /organizations/{org_id}/timeline`, `GET /contacts/{contact_id}/timeline`, `GET /leads/{lead_id}/conversion-preview`, `POST /leads/{lead_id}/convert`. 91 routes in the authorization matrix.

### Backend

#### Timeline events from domain events (`activity/service.py`, ADR 0020)

```python
# app/main.py
bus.subscribe(audit_service.record)
bus.subscribe(activity_service.record_event)  # record timelines (ADR 0020)

async def record_event(session: AsyncSession, event: DomainEvent) -> None:
    entity_type, _, verb = event.action.partition(".")
    if entity_type not in TIMELINE_ENTITIES or verb not in TIMELINE_EVENTS or ...:
        return
    session.add(TimelineEvent(entity_type=entity_type, entity_id=event.entity_id,
                              event_type=verb, occurred_at=event.occurred_at,
                              actor_id=event.actor.user_id if event.actor else None,
                              data=_event_data_from(verb, event)))   # IDs only; names on read
```

#### One paged query per timeline (`activity/repository.py`)

```python
activities = select(literal("activity").label("kind"), Activity.id.label("id"),
                    Activity.occurred_at.label("at")).where(Activity.archived_at.is_(None), or_(
    _in(Activity.lead_id, scope.leads), _in(Activity.opportunity_id, scope.opportunities),
    _in(Activity.organization_id, scope.organizations), _in(Activity.contact_id, scope.contacts)))
events = select(literal("event").label("kind"), TimelineEvent.id.label("id"),
                TimelineEvent.occurred_at.label("at")).where(or_(...per entity type...))
merged = union_all(activities, events).subquery()
rows = await session.execute(select(merged.c.kind, merged.c.id)
                             .order_by(merged.c.at.desc(), merged.c.id.desc())
                             .offset((page - 1) * page_size).limit(page_size))
```

The opportunity scope adds its source lead (FR-LEAD-04 AC3); the organization scope adds the IDs of its contacts (party) and leads and opportunities (`sales.links`).

#### Activity rules

```python
def _may_edit(principal: Principal, activity: Activity) -> bool:
    """Owner+, or the assignee of a task (API spec 11)."""
    if can_edit_owned(principal, activity.owner_id):
        return True
    return activity.type == "task" and activity.assignee_id == principal.user_id

async def _touch(ctx: Context, activity: Activity, at: datetime) -> None:
    """Logged activity keeps an opportunity fresh (FR-OPP-06)."""
    if activity.opportunity_id is not None:
        await sales.links.touch_opportunity(ctx.session, activity.opportunity_id, min(at, ctx.now))
```

`touch_opportunity` uses `greatest(coalesce(last_activity_at, at), at)`, so an older activity never makes an opportunity look staler.

#### Lead conversion in one transaction (`sales/service/leads.py`)

```python
async def convert(ctx, principal, lead_id, data: ConvertRequest) -> ConversionResult:
    lead = await _load(ctx, lead_id)                 # row lock
    check_owner(principal, lead.owner_id)
    await _check_version(ctx, lead, data.version)
    if lead.status != "qualified":
        raise AppError(ErrorCode.LEAD_NOT_CONVERTIBLE, HTTPStatus.CONFLICT, extra={"status": lead.status})
    organization = await _conversion_organization(ctx, principal, data.organization)   # party, commit=False
    contact = await _conversion_contact(ctx, principal, data.contact, organization.id)  # party, commit=False
    opportunity = await opportunities.create_opportunity(ctx, principal, OpportunityCreate(...),
                                                         source_lead_id=lead.id, commit=False)
    ...                                              # lead -> converted, links, version + 1
    await _publish(ctx, "lead.converted", lead, principal, before=before, after=after)
    await ctx.session.commit()                       # nothing is stored if any step raised (AC2)
```

`ConversionOrganization` / `ConversionContact` reuse party's create schemas with an "exactly one of `existing_id` and `new`" validator. `GET /conversion-preview` returns organization matches (duplicate check across scripts), contacts with the lead's email and suggested values.

#### Access wording

`AccessLevel.OWNER_PLUS_OR_TASK_ASSIGNEE` ("Owner+ (owner = activity owner; assignee may update a task)") and `AccessLevel.OWNER_PLUS_OR_ASSIGNEE` ("Owner+ or assignee") let the route catalog and matrix match the spec text; route-level roles are those of Contributor, and the service applies the record rule.

### Frontend

- `features/activities`: `RecordTimeline` (paged, newest first; activities with type, task checkbox, overdue badge and links to other records; events rendered per type with stage/owner/status names in the UI language and a link to the record they belong to), `ActivityForm` (type, subject, details, date/time or due date and assignee for tasks), `MyTasksPage` (`/tasks`, overdue first, show completed), `TaskCheckbox`.
- `features/leads/ConvertPage` (`/leads/:id/convert`): radio choices for the linked organization, duplicate-check matches or a new one (name prefilled), the same for the contact (or none), and the opportunity's name, amount, expected close date and stage. A `409 conflict.duplicate` lists the matches and offers "Create anyway". The lead page shows "Convert" for qualified leads and links a converted lead to its opportunity.
- Timelines appear on lead, opportunity, organization and contact pages; "My tasks" in the navigation.
- **Every successful mutation marks timelines stale** (query client mutation cache), found by the journey:

```ts
mutationCache: new MutationCache({
  onError: handle,
  // Any change can add an event to record timelines (FR-ACT-03); mark them stale.
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['timeline'] }),
}),
```

- 679 translation keys (en = bg); 91 Vitest tests (9 new); a default MSW handler returns empty timelines.

### Verification (2026-11-17)

| Gate | Result |
|---|---|
| ruff, format, mypy (strict), import-linter (14) | clean |
| Migration 0006 up → down → up; `alembic check` | OK, no drift |
| pytest (scratch PostgreSQL 18.7) | 773 passed, 96% coverage (activity service 96%) |
| pip-audit | no known vulnerabilities |
| ESLint, Prettier, tsc, i18n (679 keys) | clean |
| Vitest | 91 passed |
| pnpm audit (production) | no known vulnerabilities |
| OpenAPI snapshot and generated types | up to date |
| Playwright Chromium vs. rebuilt stack | 18/18 in two consecutive runs, including the full journey in both languages |
| GitHub Actions (PR #7, run 44130293284) | all four jobs green, including Playwright on Chromium and Firefox |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | Done for FR-ACT-01..03, FR-LEAD-04 AC1–AC3, FR-OPP-06 |
| 2 | `docker compose up` works | Done |
| 3 | Lint, types, suites green | Done locally and in CI (PR #7) |
| 4 | Permission checks + matrix | Done for all 91 routes; owner, assignee and stranger cases |
| 5 | UI text en + bg | Done |
| 6 | Additive migrations + tests | Done (0006) |
| 7 | Audit for create/update/delete | Done (`activity.*`, `lead.converted`) |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec v0.6 |
| Exit | Journey lead → qualify → convert → progress → won in en and bg (+ close lost and manager reopen) | Done (`journey.spec.ts`, `opportunities.spec.ts`) |

### Decisions and deviations

- **Timeline events** are their own table, recorded from domain events; names are resolved on read (ADR 0020). No backfill for records created before 4b (not in production).
- **Assignees** must be active Admins, Sales Managers or Sales Reps (a Viewer could not complete a task); new field code `assignee.invalid`.
- **Assignee edits**: the spec allows the assignee to update a task (PATCH), which is slightly wider than "owner or Manager+ edits" in the recommendation; the spec wording was followed. Archive stays Owner+.
- **Only non-task activities and completed tasks** make an opportunity fresh; creating a future task does not.
- **Conversion** reuses party's create functions with `commit=False`, so duplicate rules and audit events are identical to creating the records directly.
- **Timeline items carry an `id`** (the activity's or event's ID) for stable list keys; the spec example was updated.
- New codes: `activity.not_a_task` (409); field codes `activity.link_required`, `activity.due_required`, `activity.task_only`, `assignee.invalid`, `lead.not_found`, `lead.archived`, `opportunity.not_found`, `opportunity.archived`.

### Open items

1. ~~Owner review of Phase 4~~: approved. PR #7 was merged into the 4a branch after #6 had reached `main`, so PR #8 carries the same commits to `main`.

---

## Phase 5a — Reports, dashboard and exports

Requirements: FR-REP-01, FR-REP-02, FR-REP-03 and the audit-log export (FR-ADM-03). Phase 5 is delivered in two pull requests (owner approval, 2026-11-17): **5a** reports, dashboard and exports; **5b** import, seed data and the performance check, then owner review. Owner decisions used here: default period = the current calendar year; conversion rate = converted ÷ created in the period; win rate = won ÷ (won + lost) closed in the period.

### Tasks

| # | Task | Result |
|---|---|---|
| 5a.1 | Export machinery in core: columns, XLSX/CSV, cap, formula-injection guard, audit event | Done (`app/core/export.py`) |
| 5a.2 | Exports of organizations, contacts, leads, opportunities, activities and the audit log | Done |
| 5a.3 | Batched embedded summaries (organizations, contacts, lead titles) for large exports | Done |
| 5a.4 | Report queries in sales; reporting module with scope, dashboard, report exports | Done (ADR 0021) |
| 5a.5 | Backend tests, including the forecast against an independent calculation (FR-REP-01 AC1) | Done (825 total) |
| 5a.6 | Dashboard (Recharts), win/loss page, Export buttons on lists | Done, en + bg |
| 5a.7 | E2E: dashboard, CSV download, win/loss | Done (en, bg) |
| 5a.8 | Documentation (spec v0.7, ADR 0021, snapshot, this log, test record), gate, PR | Done |

### Endpoints built (12)

`GET /reports/dashboard`, `/reports/pipeline-by-stage`, `/reports/forecast`, `/reports/lead-conversion`, `/reports/win-loss`, `/reports/{report}/export`; `GET /organizations/export`, `/contacts/export`, `/leads/export`, `/opportunities/export`, `/activities/export` (added to spec section 11, where it was missing from the table), `/audit-log/export`. 103 routes in the authorization matrix.

### Backend

#### Export machinery (`app/core/export.py`)

```python
def neutralize(value: str) -> str:
    """Prefix text a spreadsheet would run as a formula with an apostrophe."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value   # = + - @ \t \r

async def build_export(session, statement, query, sort_columns, id_column, outs, row,
                       available, options, locale, *, name, day) -> tuple[ExportFile, int]:
    columns = select_columns(available, options.columns)          # 400 export.unknown_column
    total = (await session.execute(select(func.count()).select_from(
        statement.order_by(None).subquery()))).scalar_one()
    check_row_count(total)                                          # 422 export.too_many_rows
    records = list((await session.execute(statement.order_by(*order, id_column))).unique().scalars())
    for start in range(0, len(records), _CHUNK):                    # the module's own outputs
        rows.extend(row(item, locale) for item in await outs(records[start : start + _CHUNK]))
    content = render(columns, rows, options.format, locale, sheet=name)
```

Each module declares its columns with both headers and a row builder, e.g. leads:

```python
LEAD_EXPORT = (ExportColumn("title", "Title", "Заглавие"), ExportColumn("status", "Status", "Състояние"), ...)

def _lead_row(lead: LeadOut, locale: ExportLocale) -> dict[str, Any]:
    en, bg = LEAD_STATUS_NAMES[lead.status]
    return {**lead.model_dump(include={c.key for c in LEAD_EXPORT}),
            "source": reference_name(lead.source, locale), "status": bg if locale == "bg" else en, ...}
```

The export publishes `exported_event("lead", principal, now, rows=..., options=..., filters=...)` (audit) and commits. Export routes are declared before `/{id}` routes and accept the list's filters plus `format`, `columns`, `locale` (`EXPORT_PARAMS`).

#### Reports (`sales/service/reports.py`, `reporting/service.py`)

```python
async def forecast(session, owner_ids, today, months) -> ForecastReport:
    """FR-REP-01 AC1: per month from the current one, Σ amount × probability / 100 over open,
    non-archived opportunities expected to close in that month."""
    first = today.replace(day=1)
    found = {month: (count, total, weighted) for month, count, total, weighted in
             await repository.forecast_rows(session, owner_ids, first, _add_months(first, months))}
    ...

# repository: to_char, not date_trunc (date_trunc yields a timestamp in the session time zone)
month = func.to_char(Opportunity.expected_close_date, "YYYY-MM").label("month")
```

Lead conversion and win/loss use `count(*) FILTER (WHERE …)` per status or stage type, grouped by source/owner or loss reason/owner/month. The reporting module resolves the scope (`owner_id` `me`/ID, `from`/`to` defaulting to the Sofia calendar year), composes the dashboard (including the caller's open and overdue tasks from `activity`) and exports reports with a total row.

#### Batched summaries

`party.organization_summaries(session, ids)`, `party.contact_links(session, ids)` and `sales.repository.lead_titles(session, ids)` replace per-record lookups in lead, opportunity and activity outputs.

### Frontend

- `features/reports`: `Dashboard` on the home page (KPIs for open pipeline, conversion rate, win rate and my tasks; Recharts bar charts for pipeline by stage and the 6-month weighted forecast, each with a screen-reader table of the same figures; owner and year filters kept in the URL), `WinLossPage` (`/reports/win-loss`, group by loss reason, owner or month, total row, export), `ExportMenu` (Export XLSX / Export CSV) and `download()`:

```ts
export async function download(path: string, query: string): Promise<void> {
  const response = await globalThis.fetch(`${globalThis.location.origin}${path}?${query}`, {
    credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
  if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => ({})))
  ...  // Blob → object URL → <a download> with the server's file name
}
```

- Export buttons on the organization, contact, lead, opportunity and audit-log lists send the list's current filters and sort (paging dropped); errors such as `export.too_many_rows` become translated toasts.
- "Reports" in the navigation; `recharts` 3.10.1 pinned (a release older than two weeks; 3.11.0 was published the same day).
- 719 translation keys (en = bg); 96 Vitest tests (5 new).

### Verification (2026-11-17)

| Gate | Result |
|---|---|
| ruff, format, mypy (strict), import-linter (14) | clean |
| pytest (scratch PostgreSQL 18.7) | 825 passed, 97% coverage |
| pip-audit | no known vulnerabilities |
| ESLint, Prettier, tsc, i18n (719 keys) | clean |
| Vitest | 96 passed |
| pnpm audit (production) | no known vulnerabilities |
| OpenAPI snapshot and generated types | up to date |
| Playwright Chromium vs. rebuilt stack | 20/20 in two consecutive runs |
| GitHub Actions (PR #9) | run 44158425076 failed only in the frontend dependency audit (new dev-only advisory, ADR 0022); after the owner's decision run 44159185613: all four jobs green |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | Done for FR-REP-01 (AC1 independently computed), FR-REP-02, FR-REP-03 |
| 2 | `docker compose up` works | Done |
| 3 | Lint, types, suites green | Done locally and in CI (PR #12) |
| 4 | Permission checks + matrix | Done for all 103 routes; exports and reports for every role, audit export Admin only |
| 5 | UI text en + bg | Done (headers of exported files too) |
| 6 | Additive migrations + tests | No migration in 5a |
| 7 | Audit | Every export audited (`*.exported`) |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec v0.7 |

### Decisions and deviations

- **Reports are computed by the module that owns the data** (sales, activity); reporting composes them (ADR 0021).
- `/activities/export` was named in spec section 14 but missing from the section 11 table; the table row was added.
- The dashboard is not exportable (it is a composition); `/reports/{report}/export` accepts the four reports.
- New field codes `export.unknown_column` (400) and `validation.period` (400).
- `types-openpyxl` added as a dev dependency so mypy strict covers the export code.

### Open items

1. ~~Phase 5b~~: done, see below. Owner review of 5a + 5b.
2. Remove the ignored advisory GHSA-fc5q-39xc-vjpf from `frontend/pnpm-workspace.yaml` once picomatch ships a fix (ADR 0022). The first CI run of PR #9 (44158425076) failed on it in the frontend dependency audit; everything else was green.

---

## Phase 5b — Import, seed data and performance

Requirements: FR-IMP-01 (AC1–AC4) and the NFR-01 volume and performance check. Owner decisions used here (2026-11-17): `python-multipart` added; organizations found by EIK, then by name in either script, stages by English or Bulgarian name, owners by email; CSV encoding and delimiter detected; 10 MB and 20,000 rows per file; uploaded rows kept in the database for at most 7 days, with previous values for rollback; the performance check runs locally, not in CI.

### Tasks

| # | Task | Result |
|---|---|---|
| 5b.1 | Schema: `import_batch`, `import_row`, `import_batch_id` on organization, contact, lead, opportunity | Done: migration `0007` |
| 5b.2 | Parsing (XLSX/CSV, encoding, delimiter, limits), field definitions, templates (en/bg) | Done |
| 5b.3 | Import service: state machine, mapping, validation, commit, rollback, discard, expiry | Done (ADR 0023) |
| 5b.4 | Owning-module entry points for imports (create with batch tag, update/restore, lookups, stamps) | Done |
| 5b.5 | Backend tests | Done (878 total) |
| 5b.6 | Import wizard (list, upload, templates, mapping, preview, commit, discard, rollback) | Done, en + bg |
| 5b.7 | `seed-demo` command and `scripts/perf_check.py`; measured run | Done (results below) |
| 5b.8 | E2E: import journey | Done (en, bg) |
| 5b.9 | Documentation (spec v0.8, ADR 0023, snapshot, this log, test record, README, CLAUDE.md), gate, PR | Done |

### Endpoints built (10)

`GET /imports/templates/{entity_type}`, `POST|GET /imports`, `GET|DELETE /imports/{batch_id}`, `PUT /imports/{batch_id}/mapping`, `POST /imports/{batch_id}/validate`, `GET /imports/{batch_id}/rows`, `POST /imports/{batch_id}/commit`, `POST /imports/{batch_id}/rollback`. 113 routes in the authorization matrix; the route catalog has no pending entries left for Phases 0–5.

### Backend

#### Adapters call the owning modules (`dataimport/adapters.py`)

```python
class Opportunities(Adapter):
    record = "opportunity"
    schema = OpportunityCreate
    lookups: ClassVar[Mapping[str, str]] = {"organization": "organization_id", "stage": "stage_id",
                                             "owner": "owner_id"}
    decimals = frozenset({"amount"})
    dates = frozenset({"expected_close_date"})

    async def create(self, ctx, principal, payload, batch_id) -> UUID:
        opportunity = await sales.opportunities.create_opportunity(
            ctx.sales(), principal, payload, commit=False, import_batch_id=batch_id)
        return opportunity.id
```

`Adapter.prepare` turns the mapped text into the create schema: plain fields (decimal comma and `DD.MM.YYYY` normalized), looked-up fields (cached per batch), then `schema.model_validate`; Pydantic errors become `validation.<type>` on the import field names.

#### Commit in one transaction, rollback by stamp (`dataimport/service.py`)

```python
for row in rows:
    if row.outcome == "invalid" or (row.outcome == "duplicate" and batch.duplicate_mode != "update"):
        row.action = "skipped"; continue
    prepared = await adapter.prepare(ctx, lookups, _values(batch, row))
    if prepared.payload is None:                  # changed since validation -> nothing is written
        raise AppError(ErrorCode.IMPORT_HAS_ERRORS, HTTPStatus.CONFLICT, extra={"row_number": row.row_number, ...})
    if row.outcome == "duplicate" and row.match_id is not None:
        row.before = await adapter.update(ctx, principal, row.match_id, prepared.payload)
        ...
    else:
        row.record_id = await adapter.create(ctx, principal, prepared.payload, batch.id)
await ctx.session.flush()
stamps = await adapter.stamps(ctx.session, {r.record_id for r in rows if r.record_id})
...
# rollback: a record whose updated_at differs from its stamp was changed since -> kept
if current.get(row.record_id) != row.stamp:
    row.rollback_result = "changed_since_import"
```

#### Parsing (`dataimport/parsing.py`)

`openpyxl` in read-only mode with cached values (formulas are not evaluated); CSV decoded as UTF-8 (with or without BOM) or Windows-1251, delimiter sniffed among comma, semicolon and tab; repeated headers get the column number; blank lines are dropped; 10 MB and 20,000 rows.

#### Seed and performance check

`python -m app.cli seed-demo [--organizations N --contacts N --leads N --opportunities N --seed S]` bulk-inserts fictional records (owners: the active Admins, Sales Managers and Sales Reps), refuses `ENV=production` and writes no audit entries. `backend/scripts/perf_check.py` signs in, warms up and calls 15 list, search, board and dashboard requests 40 times each, printing p50/p95/max and failing when a p95 exceeds 500 ms. The compose file now passes `RATE_LIMIT_USER_PER_MINUTE` through (default 600) so the check can run without throttling.

### Performance (NFR-01), 2026-11-17

Docker Desktop on the developer Mac, composed production-like stack behind Caddy (HTTPS), after `docker compose exec -T -e ENV=test backend python -m app.cli seed-demo` (10,000 organizations, 10,000 contacts, 20,000 leads, 5,000 opportunities; seeded in 6.7 s) plus the existing test data; per-user rate limit raised for the run only.

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

All p95 values are far below the 500 ms target. Bulk operations on the same stack: export of 20,000 leads 2.3 s (XLSX, 1.1 MB) and 1.1 s (CSV); import of 5,000 organizations: upload 0.3 s, validation 2.4 s, commit 6.9 s.

### Frontend

- `features/imports`: `ImportsPage` (`/admin/imports`, Manager+: batch list, new upload with record type and file, template downloads in English and Bulgarian) and `ImportBatchPage` (counts; mapping table with a field per column and the duplicate choice for organizations and contacts; "Save and check"; preview filtered by outcome with each row's translated reasons and matches; "Import all" (disabled while rows are invalid) or "Import, skipping invalid rows"; discard; rollback for Admins with per-row results). Uploads go through `uploadImport()` (multipart via `fetch`).
- "Import" in the navigation for users with `data.import`.
- The preview remounts per batch status, so the checking filter (invalid rows) does not hide the imported rows (found by the journey).
- 814 translation keys (en = bg); 101 Vitest tests (6 new).

### Verification (2026-11-17)

| Gate | Result |
|---|---|
| ruff, format, mypy (strict), import-linter (14) | clean |
| Migration 0007 up → down → up; `alembic check` | OK, no drift |
| pytest (scratch PostgreSQL 18.7) | 878 passed, 96% coverage (import 95–97%) |
| pip-audit | no known vulnerabilities |
| ESLint, Prettier, tsc, i18n (814 keys) | clean |
| Vitest | 101 passed |
| `pnpm audit --audit-level high` | passes (one advisory ignored, ADR 0022); `--prod` clean |
| OpenAPI snapshot and generated types | up to date |
| Playwright Chromium vs. rebuilt stack | 22/22 in two consecutive runs |
| GitHub Actions (PR #10, run 44164230647) | all four jobs green, including Playwright on Chromium and Firefox |
| NFR-01 performance check | all p95 under 500 ms (table above) |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | Done for FR-IMP-01 AC1–AC4, NFR-01 |
| 2 | `docker compose up` works | Done |
| 3 | Lint, types, suites green | Done locally and in CI (PR #10) |
| 4 | Permission checks + matrix | Done for all 113 routes; rollback Admin only |
| 5 | UI text en + bg | Done (templates too) |
| 6 | Additive migrations + tests | Done (0007) |
| 7 | Audit | `import.*` events plus the usual audit of every created or updated record |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec v0.8 |
| Exit | Forecast verified independently; exports and import working; NFR-01 volumes and target | Done (5a forecast test; this phase's performance table) |

### Decisions and deviations

- `import_batch_id` is on organization and contact too (architecture lists lead and opportunity); AC4 requires every imported record to be tagged (ADR 0023).
- Duplicate rules apply to organizations (registration number or name key) and contacts (email); leads and opportunities have none, as FR-PARTY-01 defines duplicates for parties only.
- An update of a duplicate leaves its identifying fields alone (organizations: name, registration number, owner; contacts: name, email).
- The seed tool bypasses the services (bulk inserts, no audit) and is refused in production.
- The stack's per-user rate limit is now configurable through compose (`RATE_LIMIT_USER_PER_MINUTE`, default unchanged).

### Open items

1. Owner review of Phase 5 (PR #9 for 5a and the 5b PR stacked on it; PR #8 brings 4b to `main` first).
2. Remove the ignored advisory (ADR 0022) when picomatch ships a fix.


## Phase 6a — Integration clients, API keys, scopes, external references, idempotency

Requirements: FR-INT-01, 02, 03, 04, 05 (sync mode with a key), 06, 08 (usage counters), 09 (per-client rate limit), 12 (admin screens for clients and keys); NFR-13, NFR-14. Webhooks (FR-INT-07, 10, 11), the integration guide and the rest of FR-INT-08/12 are Phase 6b. Owner decisions used here (2026-11-17): build on the API spec 19.9 read-only profiles; clients inactive until the owner confirms each flow, write scopes only after that (requirements open questions 7 and 8 still open); per-client limit 300/min by default; key expiry 12 months by default, 24 at most; hourly usage counters in PostgreSQL.

### Tasks

| # | Task | Result |
|---|---|---|
| 6a.1 | Schema: `external_system` (seeded), `integration_client`, `api_key`, `external_reference`, `idempotency_record`, `integration_usage` | Done: migration `0008` |
| 6a.2 | Principal and policy: integration principal, scope templates and alternatives, `has_scope`/`require_scope`/`record_owner`, Public refused to keys | Done (ADR 0024) |
| 6a.3 | Bearer authentication: key format, hash, expiry, two active keys, revocation, IP allowlist, mixed credentials, per-client rate limit | Done |
| 6a.4 | Client and key administration API, service users, audit; `create-integration-client` CLI | Done |
| 6a.5 | External references: resolve, per record, put/delete with own-system rule; list filters on four lists and exports | Done |
| 6a.6 | Idempotency and usage counting middleware; worker housekeeping | Done |
| 6a.7 | Scope rules in modules: owner required, no owner change, own activities only, search narrowed | Done |
| 6a.8 | Backend tests: integration suite, matrix with integration callers, policy | Done |
| 6a.9 | Admin screens (clients, settings, keys) and references on four record pages, en + bg | Done |
| 6a.10 | Vitest and Playwright (en, bg) | Done |
| 6a.11 | Documentation (spec v0.9, ADR 0024, snapshot, this log, test record, README, CLAUDE.md), gate, PR | Done |

### Endpoints built (13)

`GET|POST /integration-clients`, `GET|PATCH /integration-clients/{client_id}`, `POST /integration-clients/{client_id}/activate|deactivate`, `GET|POST /integration-clients/{client_id}/api-keys`, `DELETE /integration-clients/{client_id}/api-keys/{key_id}`, `GET /external-references`, `GET /{resource}/{id}/external-references`, `PUT|DELETE /{resource}/{id}/external-references/{system}`. Existing list and export endpoints for organizations, contacts, leads and opportunities gained `external_system`, `external_id` and `has_external_reference`. Route catalog: only the webhook endpoints (Phase 6b), the assistant (Phase 7) and MFA/GDPR (Phase 8) remain pending.

### Backend

#### Bearer keys become principals (`integration/service.py`)

```python
KEY_PATTERN = re.compile(r"^crm_([a-z]+)_([0-9a-f]{16})_([A-Za-z0-9_-]{43})$")

async def authenticate_bearer(request: Request, session: AsyncSession) -> Principal:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    match = KEY_PATTERN.match(token.strip()) if scheme.lower() == "bearer" else None
    ...
    if (key is None or key.revoked_at is not None or key.expires_at <= now
            or not hmac.compare_digest(key.secret_hash, hash_secret(match[3]))):
        raise _invalid_key()                                   # 401 auth.api_key_invalid
    if client is None or not client.is_active:
        raise AppError(ErrorCode.AUTH_CLIENT_INACTIVE, HTTPStatus.UNAUTHORIZED)
    if not _ip_allowed(client.ip_allowlist, client_ip_var.get()):
        raise AppError(ErrorCode.AUTH_IP_NOT_ALLOWED, HTTPStatus.FORBIDDEN)
    return Principal(type=PrincipalType.INTEGRATION, user_id=client.service_user_id,
                     role=RoleCode.INTEGRATION, scopes=frozenset(client.scopes),
                     client_id=client.id, system=client.system.code,
                     default_owner_id=client.default_owner_id,
                     rate_limit_per_minute=client.rate_limit_per_minute, ...)
```

`core.auth.combined_authenticator(cookie, bearer)` picks the method; a request with both returns `400 auth.mixed_credentials`. The service user (`user_type = 'service'`, role `integration`, email `<system>-<hex>@integration.invalid`) is the actor in audit entries and timelines.

#### Scopes in the one policy (`core/policy.py`, `core/auth.py`)

```python
def _check_integration(principal, level, scope):
    if level is AccessLevel.SIGNED_IN_OR_ANY_CLIENT:      # GET /me
        return
    if scope is None:                         # not in API spec 19.3 -> closed, Public included
        raise AppError(ErrorCode.PERMISSION_NOT_FOR_INTEGRATIONS, HTTPStatus.FORBIDDEN)
    # "a|b": any of the scopes (the service narrows it down, e.g. external references).
    if not principal.scopes & set(scope.split("|")):
        raise AppError(ErrorCode.PERMISSION_SCOPE_MISSING, HTTPStatus.FORBIDDEN,
                       extra={"required_scope": scope})

# core/auth.py: a scope may name a path parameter, e.g. "{resource}:read" (API spec 19.4)
resolved = scope.format(**request.path_params) if scope and "{" in scope else scope
check_access(principal, level, resolved)
```

`record_owner(principal, requested)` returns the requested owner, the client's default owner, or raises `422 owner.required`; it is used in the four create services. Organization owner changes stay Manager+ (closed to integrations); `activities:write` edits only activities the client created; search returns only the types the client may read.

#### External references and list filters (`core/external.py`, `integration/repository.py`)

```python
# party / sales list services
statement = apply_external(statement, ctx.external_filter, "organization", Organization.id, filters.external)

# integration module, registered as app.state.external_filter (ADR 0018)
def reference_condition(entity_type, id_column, system_code, external_id, has_reference):
    linked = (select(ExternalReference.entity_id)
              .join(ExternalSystem, ExternalSystem.id == ExternalReference.external_system_id)
              .where(ExternalReference.entity_type == entity_type, ExternalSystem.code == system_code))
    if external_id is not None:
        linked = linked.where(ExternalReference.external_id == external_id)
    condition = id_column.in_(linked)
    return ~condition if has_reference is False else condition
```

`PUT` checks the record exists and the system is active, refuses an integration writing another system's reference (`403 external_reference.system_mismatch`) and an external ID already used by another record (`409 external_reference.conflict`), and publishes `external_reference.updated` (audit).

#### Idempotency and usage (`integration/middleware.py`)

A pure ASGI middleware in front of the request context middleware. For an integration `POST` with `Idempotency-Key` it claims a row (`client_id`, key) with the request hash; a stored response is replayed with `Idempotent-Replayed: true`, a different hash is `422 idempotency.key_reused`, an unfinished claim `409 idempotency.in_progress`, and a `5xx` deletes the claim so the retry runs. After every integration response it upserts the client's hourly `integration_usage` row (an error for status 400 and above). The worker purges idempotency records after 24 h and usage after 30 days.

#### CLI

`python -m app.cli create-integration-client [--system erp|billing|conclusion|all]` creates the 19.9 profiles inactive and without keys, skipping systems that already have a client.

### Frontend

- `features/integrations/`: `IntegrationsPage` (clients with system, status, active keys, last-24-hour requests and errors, last use; form for a new client, always inactive), `ClientPage` (settings: name, default owner, rate limit, contact, CIDR allowlist one per line, scopes; activate/deactivate; keys with prefix, expiry, last use and state, revoke with confirmation; a new key shown once in an alert with a copy field), `ScopePicker`, `ExternalReferences`.
- `ExternalReferences` sits on the organization, contact, lead and opportunity pages before the timeline: the record's IDs per system, linked when a URL is stored; Admins add (system, ID, https link) and remove. Hidden for others when there is nothing to show.
- Navigation "Integrations" for Admins; routes `/admin/integrations` and `/admin/integrations/:clientId` in the users-manage group. New `integrations` namespace and error translations (en, bg).

### Verification (2026-11-17)

| Check | Result |
|---|---|
| ruff, format, mypy (strict), import-linter (14) | clean |
| Migration 0008 up → down → up; `alembic check` | OK, no drift |
| pytest (scratch PostgreSQL 18.7) | 1089 passed, 96% coverage (integration module 90–93%) |
| pip-audit | no known vulnerabilities |
| ESLint, Prettier, tsc, i18n (891 keys) | clean |
| Vitest | 114 passed |
| `pnpm audit --audit-level high` | passes (one advisory ignored, ADR 0022; one new moderate dev-only minimatch advisory below the threshold); `--prod` clean |
| OpenAPI snapshot and generated types | up to date |
| Playwright Chromium vs. rebuilt stack | 24/24 (corrected: an earlier note said 28/28, which was the unfiltered run, 24 Chromium tests plus 4 Firefox tests; the other Firefox tests could not launch the browser locally; Firefox runs in CI) |
| GitHub Actions (PR #12, run 44172903654) | all four jobs green, including Playwright on Chromium and Firefox |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | Done for FR-INT-01 AC1–AC2, 02 AC1–AC3, 03 AC1–AC4, 04, 05, 06, 08, 09 |
| 2 | `docker compose up` works | Done (rebuilt with migration 0008) |
| 3 | Lint, types, suites green | Done locally; CI on the PR |
| 4 | Permission checks + matrix | Done for all 126 routes, for people and for integration clients with all and with no scopes |
| 5 | UI text en + bg | Done |
| 6 | Additive migrations + tests | Done (0008, round trip and `alembic check`) |
| 7 | Audit | `integration_client.*`, `api_key.*`, `external_reference.updated`; integration changes audited with the service user as actor |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec v0.9 |
| Exit | Phase 6 exit (a real receiver gets signed webhooks) | Phase 6b |

### Decisions and deviations

- `POST /integration-clients` defaults to `is_active: false` (the original draft had no default); the UI and CLI always create inactive clients, matching the owner's "inactive until confirmed" decision.
- The per-client limit default is 300/min (spec v0.8 said 1,200); owner decision.
- API key secrets are hashed with SHA-256, not Argon2: they are 256-bit random values, so a slow hash adds cost without security (ADR 0024).
- Search for an integration is narrowed to readable types rather than refused, so `organizations:read` alone keeps `/search` useful.
- Public endpoints (sign-in, password) refuse API keys (`permission.not_for_integrations`); the matrix found them reachable before this rule.

### Open items

1. Phase 6b: outbox, webhook delivery, subscriptions, delivery log, alerts, integration guide, Postman collection, receiver example, exit test.
2. Requirements open questions 7 and 8 (data flows and write scopes for ERP, Billing, Conclusion) remain with the owner; clients stay inactive until answered.
3. PR #11 (Phase 5 to `main`) is still open; this PR stacks on it.

## Phase 6b — Webhooks, delivery log, integration guide

Requirements: FR-INT-07 (AC1–AC5), FR-INT-08 (failing deliveries and the alert), FR-INT-10 (guide, samples, collection), FR-INT-12 (subscriptions, delivery log, test event, redeliver), NFR-13 (first attempt within 30 s), NFR-14 (events raised during an outage are delivered afterwards). Owner decisions used here (2026-11-17): `cryptography` 50.0.2 for secret encryption with `APP_ENCRYPTION_KEY`; `httpx` 0.28.1 moved to the runtime dependencies; `WEBHOOK_ALLOWED_HOSTS` with exact hosts or `*.suffix`, resolved and pinned, loopback, link-local and metadata always refused; banner and badge instead of email; a Postman collection; only the Python sample tested.

### Tasks

| # | Task | Result |
|---|---|---|
| 6b.1 | Dependencies and settings (`APP_ENCRYPTION_KEY`, `WEBHOOK_ALLOWED_HOSTS`) in settings, `.env.example`, compose, start scripts and CI | Done |
| 6b.2 | Schema: `outbox_event`, `webhook_subscription`, `webhook_delivery`, `webhook_attempt` | Done: migration `0009` |
| 6b.3 | Outbox subscriber on the event bus; event mapping | Done (ADR 0025) |
| 6b.4 | Worker: fan-out with scope filtering, claim with lease and per-record ordering, signed delivery, retries, suspension, purge | Done |
| 6b.5 | Network guard: URL rules, DNS check, pinned connection, no redirects, 10 s | Done |
| 6b.6 | Admin API: subscriptions (secret once, rotate, test), delivery log, redeliver; webhook figures on clients | Done (9 endpoints) |
| 6b.7 | Admin screens: subscriptions on the client page, delivery log and detail, failing-delivery banner and badge (en, bg) | Done |
| 6b.8 | Reference receiver, integration guide (Python, C#, Java samples), Postman collection | Done |
| 6b.9 | Tests: webhook suite, Phase 6 exit test, guide sample and collection checks, Vitest, Playwright | Done |
| 6b.10 | Documentation (spec v0.10, architecture tables, ADR 0025, snapshot, this log, test record, README, CLAUDE.md), gate, PR | Done |

### Endpoints built (9)

`GET|POST /integration-clients/{client_id}/webhook-subscriptions`, `PATCH|DELETE /webhook-subscriptions/{subscription_id}`, `POST /webhook-subscriptions/{subscription_id}/rotate-secret`, `POST /webhook-subscriptions/{subscription_id}/test`, `GET /webhook-deliveries`, `GET /webhook-deliveries/{delivery_id}`, `POST /webhook-deliveries/{delivery_id}/redeliver`. `IntegrationClientOut` gained `webhooks` (additive). The route catalog's pending list now holds only the assistant (Phase 7) and MFA/GDPR (Phase 8).

### Backend

#### The outbox is one more event-bus subscriber (`app/main.py`, `integration/webhooks.py`)

```python
bus.subscribe(audit_service.record)
bus.subscribe(activity_service.record_event)        # record timelines (ADR 0020)
bus.subscribe(integration_webhooks.record_event)    # webhook outbox (FR-INT-07 AC1)

async def record_event(session: AsyncSession, event: DomainEvent) -> None:
    event_type = event_type_for(event)             # 19.6 types; archived/restored/owner_changed -> <record>.updated
    if event_type is None or event.entity_id is None:
        return
    session.add(OutboxEvent(event_type=event_type, entity_type=event.entity_type,
                            entity_id=event.entity_id, actor=_actor(event.actor),
                            changes=_changes(event), details=..., occurred_at=event.occurred_at))
```

#### Fan-out and delivery in the worker (`app/worker.py`)

```python
async def deliver_webhooks(engine: AsyncEngine) -> None:
    sessions = create_session_factory(engine)
    async with sessions() as session:
        while await webhooks.dispatch(session, clock.now()):   # deliveries for matching, readable subscriptions
            pass
    await webhooks.deliver_due(sessions, get_settings(), clock.now())

JOBS = (deliver_webhooks, every(timedelta(hours=1), purge_expired))
```

`deliver_due` claims due deliveries (`FOR UPDATE SKIP LOCKED`, 5-minute lease) in a short transaction, builds each payload with the owning modules' `get` functions, signs it, sends it with no transaction open, and records the attempt:

```python
if outcome.succeeded:
    delivery.status, delivery.delivered_at, delivery.next_attempt_at = "succeeded", now, None
elif is_ping or now - delivery.first_attempt_at >= RETRY_WINDOW:      # 72 h
    delivery.status, delivery.next_attempt_at = "failed", None
else:
    delivery.status, delivery.next_attempt_at = "retrying", now + backoff(number)  # 1m, 5m, 30m, 2h, 6h ±10 %
```

The claim query skips a delivery while an earlier one for the same record and subscription is open (event time, then UUIDv7 event ID), and passes test events whatever the client or subscription state.

#### Signing and the network guard (`webhooks.sign`, `integration/netguard.py`)

```python
def sign(signing_secrets, timestamp, body) -> str:   # old secret first for 24 h after rotation
    message = f"{timestamp}.".encode() + body
    return ",".join([f"t={timestamp}", *(f"v1={hmac.new(s.encode(), message, sha256).hexdigest()}"
                                         for s in signing_secrets)])

addresses = await network.resolve(host, port)
if not addresses or not all(network.address_allowed(a) for a in addresses):
    return failed("address_not_allowed")       # loopback, link-local, metadata, multicast, reserved
async with pinned_client(addresses[0], TIMEOUT_SECONDS) as client, client.stream("POST", url, ...) as r:
    ...                                         # connects to the vetted address; TLS checks the URL host
```

`pinned_client` installs an httpcore network backend that connects every stream to the vetted address, with `follow_redirects=False`, no proxy environment and a 10-second limit around the whole attempt. Secrets are Fernet-encrypted with an HKDF-derived key (`app/core/crypto.py`).

#### Reference receiver (`deploy/examples/webhook_receiver.py`)

Standard library only: `verify_signature` (constant-time, 5-minute window, any `v1`), an HTTP(S) server that deduplicates on the event ID and answers 204, 401 or 400. The webhook tests and the exit test deliver to it over real HTTP.

### Frontend

- `features/integrations/Webhooks.tsx` on the client page: subscriptions with URL, event types, state (active, paused, suspended), 24-hour counts, previous-secret validity; subscribe form (URL, event-type checkboxes including "all events"); the secret shown once after creation or rotation; send test event (opens the delivery, which refreshes until attempted), pause/resume, rotate, remove.
- `DeliveriesPage.tsx`: the delivery log with client, status and event-type filters in the URL; delivery detail with every attempt (status or translated error, duration, response excerpt) and redeliver.
- `useWebhookHealth` and `WebhookAlert`: a badge on the Integrations link and a banner in the admin area while deliveries are failing or subscriptions are suspended; the client list shows failing counts.

### Verification (2026-11-18)

| Check | Result |
|---|---|
| ruff, format, mypy (strict), import-linter (14) | clean |
| Migration 0009 up → down → up; `alembic check` | OK, no drift |
| pytest (scratch PostgreSQL 18.7) | 1171 passed, 96% coverage (webhooks 91%, netguard 97%) |
| pip-audit (with `cryptography` 50.0.2, `httpx` 0.28.1) | no known vulnerabilities |
| ESLint, Prettier, tsc, i18n (959 keys) | clean |
| Vitest | 122 passed |
| `pnpm audit --audit-level high` | passes (ADR 0022 ignore); `--prod` clean |
| OpenAPI snapshot and generated types | up to date |
| Playwright Chromium vs. rebuilt stack (`WEBHOOK_ALLOWED_HOSTS=hooks.example.test`) | 26/26, including the webhook journey through the real worker in en and bg |
| GitHub Actions (PR #13, run 44209396859) | all four jobs green, including Playwright on Chromium and Firefox |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | Done for FR-INT-07 AC1–AC5, FR-INT-08, 10, 12, NFR-13 |
| 2 | `docker compose up` works | Done (rebuilt with migration 0009 and the new settings) |
| 3 | Lint, types, suites green | Done locally and in CI (PR #13) |
| 4 | Permission checks + matrix | Done for all 135 routes (all Admin; closed to integration clients) |
| 5 | UI text en + bg | Done |
| 6 | Additive migrations + tests | Done (0009) |
| 7 | Audit | `webhook_subscription.*`, `webhook_delivery.redelivered`; never secrets |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec v0.10 |
| Exit | API-key client syncs, receives a signed `opportunity.closed_won`, writes back an ERP reference, is refused outside its scopes | Done: `tests/api/test_phase6_exit.py` (plus the integration scope matrix for every route) |

### Decisions and deviations

- `POST /webhook-subscriptions/{id}/test` queues the ping and returns `202` instead of the receiver's status: a synchronous call would make the request reach an external system, which CLAUDE.md forbids. Spec updated in the same change.
- The outbox stores no `entity_version`; payloads take `version` from the record at delivery time. Added columns `dispatched_at`, `details`, `first_attempt_at`, `failing_since` and the `webhook_attempt` table; architecture section 4 updated (ADR 0025).
- Test events never count towards suspension or the failing figure, so checking an endpoint cannot raise an alert.
- Suspension is logged by the worker rather than audited: the audit log records changes made by users and integration clients, and the worker has no actor.
- The Bulgarian UI uses „уебхук" for webhook.

### Open items

1. Owner review of Phase 6 (PR #12 for 6a, the 6b PR stacked on it; PR #11 brings Phase 5 to `main` first).
2. Requirements open questions 7 and 8 (data flows and write scopes) remain; the ERP, Billing and Conclusion clients stay inactive until answered.
3. The network team needs the webhook hosts for `WEBHOOK_ALLOWED_HOSTS` and outbound HTTPS from the worker (operations guide, Phase 8).

## Phase 7a — AI assistant backend: model client, tools, streaming, limits

Requirements: FR-AI-01 (conversations, streaming, stop), FR-AI-02 (questions over CRM data through read-only tools; AC1 user's permissions, AC2 links, AC3 no invention), FR-AI-03 (record context), FR-AI-04 (save a draft as a note, explicit), FR-AI-05 (read-only), FR-AI-06 (reply in the user's language), FR-AI-07 (switch, provider failure), FR-AI-08 (rate limit, daily budget, usage per request). Owner decisions (2026-11-18): `litellm` pinned; `react-markdown` + `remark-gfm` for the drawer (7b); streaming without a library; an `assistant_usage` table; budget 200,000 tokens per user per day, history about 8,000 tokens, 60 s per model call; stop through a database flag; a scripted model for the E2E stack, refused in production. Phase 6 reached `main` through PR #14 (PRs #12 and #13 had merged into their stacked bases).

### Tasks

| # | Task | Result |
|---|---|---|
| 7a.1 | `litellm` 1.108.3; settings `AI_ENABLED` (default off), `OPENROUTER_API_KEY`, `LLM_MODEL`, `LLM_PROVIDER`, `LLM_TIMEOUT_SECONDS`, `LLM_FAKE`, `AI_DAILY_TOKEN_BUDGET`, `AI_HISTORY_TOKENS`, `RATE_LIMIT_ASSISTANT_PER_10_MINUTES` in settings, `.env.example` and compose | Done |
| 7a.2 | `app/llm`: protocol and types, LiteLLM client (OpenRouter, Cerebras only), factory, scripted demo model, scripted provider server for the E2E stack (`LLM_API_BASE`) | Done |
| 7a.3 | Schema: `chat_conversation`, `chat_message`, `assistant_usage` | Done: migration `0010` |
| 7a.4 | The eight read-only tools over the services | Done |
| 7a.5 | Tool loop, SSE streaming, record context, citations, stop, usage, history | Done (ADR 0026) |
| 7a.6 | Nine endpoints; access level "Signed-in (own only)"; `features.ai_enabled` in `/system/info` | Done |
| 7a.7 | Tests: assistant API suite with a scripted model, client unit tests, matrix | Done |
| 7a.8 | Live evaluation set and script | Done; the live run waits for OpenRouter credits |
| 7a.9 | Documentation (spec v0.11, architecture, ADR 0026, `assistant-eval.md`, snapshot, this log, test record, README, CLAUDE.md), gate, PR | Done |

### Endpoints built (9)

`GET /assistant/status`, `GET|POST /assistant/conversations`, `GET|PATCH|DELETE /assistant/conversations/{conversation_id}`, `POST /assistant/conversations/{conversation_id}/messages` (SSE), `POST /assistant/conversations/{conversation_id}/messages/{message_id}/stop`, `POST /assistant/messages/{message_id}/save-as-note`. The route catalog's pending list now holds only MFA and GDPR (Phase 8).

### Backend

#### The model behind a protocol (`app/llm/`)

```python
class LLM(Protocol):                                   # app/llm/types.py
    def stream(self, messages, tools) -> AsyncIterator[StreamItem]: ...   # TextDelta..., then Completed

# app/llm/client.py: the only module importing litellm
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")   # no price-list download
os.environ.setdefault("LITELLM_MODE", "PRODUCTION")             # no .env loading at import
import litellm

response = await litellm.acompletion(
    model=self._model,                                  # openrouter/openai/gpt-oss-120b
    messages=list(messages), tools=list(tools) if tools else None,
    stream=True, stream_options={"include_usage": True},
    timeout=self._timeout, api_key=self._api_key,
    extra_body={"provider": {"order": [self._provider], "allow_fallbacks": False}},
)
...
except Exception as error:                              # provider, network or timeout
    raise LLMUnavailableError(type(error).__name__) from None   # never the prompt or answer
```

`app/llm/factory.create_llm` returns `None` while `AI_ENABLED` is off, the scripted `DemoLLM` with `LLM_FAKE`, and imports the LiteLLM client only otherwise. The import-linter contract now allows reaching `litellm` through `app.llm` and still forbids a direct import anywhere else.

#### Tools over the services (`assistant/tools.py`)

```python
class SearchOpportunities(_Args):                       # extra="forbid": the JSON schema has additionalProperties false
    query: Query | None = None
    stage_type: Literal["open", "won", "lost"] | None = None
    owner: Owner = "anyone"                              # "me" = the caller's own
    close_from: date | None = None
    close_to: date | None = None
    ...
    limit: Limit = 10                                    # 1..25

async def run(ctx, name, raw_arguments) -> dict[str, Any]:
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": "unknown_tool", "available": list(TOOLS)}
    ...                                                  # invalid_arguments with field names
    check_access(ctx.principal, AccessLevel.SIGNED_IN)   # the same policy as the API
    return await tool.run(ctx, args)                     # e.g. sales.opportunities.list_opportunities(...)
```

Every record in a result carries `type`, `id` and `url` (`/opportunities/<id>`); contacts come without email or phone.

#### The loop and the stream (`assistant/service.py`)

```python
turn = await service.prepare_message(ctx, principal, conversation_id, body)   # 503/404/422/429 here
return StreamingResponse(service.stream_answer(ctx, principal, turn), media_type="text/event-stream")

while True:
    offer_tools = result.rounds < MAX_TOOL_ROUNDS                 # 5; then the model must answer
    async for item in llm.stream(prompt, schemas if offer_tools else None):
        if isinstance(item, TextDelta):
            yield _sse("delta", {"text": item.text})            # stop flag checked every 0.5 s
        ...
    if not calls or not offer_tools:
        return
    for call in calls:
        yield _sse("tool_call", {"tool": call.name, "status": "running"})
        output = await tools.run(tctx, call.name, call.arguments)
        prompt.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(output)})
        yield _sse("tool_call", {"tool": call.name, "status": "done"})
```

The record in view is inserted before the question as a `get_record` call and its result, so CRM text reaches the model only inside tool results. After the answer, records whose ID or name appears in it are sent as `record_ref` events. The answer, the tools called, the citations and tokens are saved in a fresh session together with an `assistant_usage` row, also when the provider fails or the browser disconnects.

### Verification (2026-11-18)

| Check | Result |
|---|---|
| ruff, format, mypy (strict), import-linter (14) | clean |
| Migration 0010 up → down → up; `alembic check` | OK, no drift |
| pytest (PostgreSQL 18) | 1248 passed, 95.6% coverage (assistant service 95%, tools 89%) |
| pip-audit with `litellm` 1.108.3 | no known vulnerabilities |
| OpenAPI snapshot and generated frontend types; `tsc` | up to date; clean |
| Live evaluation | not run: the OpenRouter account has no credits (`402`); harness checked with `--fake` |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | Done for FR-AI-01..08 (backend) |
| 2 | `docker compose up` works | Compose validated with the new settings; the stack is rebuilt for the 7b journeys |
| 3 | Lint, types, suites green | Done locally |
| 4 | Permission checks + matrix | Done for the 9 routes (new level "Signed-in (own only)"; closed to integration clients) |
| 5 | UI text en + bg | 7b (the backend returns codes only) |
| 6 | Additive migrations + tests | Done (0010) |
| 7 | Audit | `chat_conversation.created/renamed/deleted` without content; saved notes as `activity.created` |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec v0.11 |

### Decisions and deviations

- **Tool results are not stored** (architecture listed role `tool` rows): they would copy CRM data, including personal data later anonymized, into chat history. Messages keep the tools called with their arguments and the cited records; history sent to the model is questions and answers only (ADR 0026).
- **`assistant_usage`** (one row per answer) is new in the data model; the budget does not depend on chat history.
- **Rate limit and budget are refused before the stream starts** as `429` problem responses; only provider failures (and unexpected errors, `server.internal_error`) are `error` events. Spec section 17 updated.
- **`stop` returns `204`, `save-as-note` returns `201`**, and `message_end` carries `status` (`complete` or `stopped`): details the draft spec left open.
- **LiteLLM's MCP import with tools** was found by running the real client against the scripted provider server: every call with tools failed (`No module named 'mcp'`), including the first live smoke call. The client passes LiteLLM's `_skip_mcp_handler=True`; the test guards it.
- **`LLM_API_BASE` and `app.llm.fake_server`**: the end-to-end stack runs with `ENV=production`, where `LLM_FAKE` is refused, so it points the real client at a scripted OpenAI-compatible server instead (deviation from the approved "fake through a setting refused in production"; the in-process `LLM_FAKE` remains for development).
- **LiteLLM's import-time `.env` loading** was found while testing (it read the repository's `.env`, including `ENV=production`, into the test process). The client sets `LITELLM_MODE=PRODUCTION` first; a unit test guards it.
- **The Cerebras skill named in CLAUDE.md is not installed** in this environment; the call follows architecture 8.1 (owner informed).

### Open items

1. The live evaluation needs OpenRouter credits (the account returns `402`). Then run `scripts/assistant_eval.py` and record the result in `docs/assistant-eval.md`.
2. Requirements open question 1 (LLM data flow): `AI_ENABLED` stays `false` by default until the owner confirms.
3. 7b: the chat drawer, Vitest and the Playwright journey with the demo model.

## Phase 7b — AI assistant chat drawer, journeys, closing Phase 7

Requirements: FR-AI-01 (drawer on every page, streaming, history, rename, delete, stop), FR-AI-02 AC2 (links to cited records), FR-AI-03 (record in view offered), FR-AI-04 (copy, save as note on an explicit click), FR-AI-06 (UI in both languages; answers follow the question), FR-AI-07 (hidden when off; provider failure in the chat), FR-AI-08 (remaining budget, refusals). Owner decision used: `react-markdown` 10.1.0 + `remark-gfm` 4.0.1.

### Tasks

| # | Task | Result |
|---|---|---|
| 7b.1 | `react-markdown`, `remark-gfm` (pinned); architecture stack table | Done |
| 7b.2 | SSE client (`fetch` + parser) and TanStack Query hooks | Done |
| 7b.3 | Drawer: launcher in the header, chat with streaming, tool progress, stop, record context from the URL, history (open, rename, delete), copy, save as note, remaining budget, errors | Done |
| 7b.4 | Markdown rendering without raw HTML; only in-app record links | Done |
| 7b.5 | i18n namespace `assistant` (en, bg) and error texts | Done (1,012 keys) |
| 7b.6 | Vitest suite; E2E journey 7 in both languages against the composed stack with the scripted provider (`docker-compose.e2e.yml`, CI) | Done |
| 7b.7 | Backend refinements found by the journeys (below) | Done |
| 7b.8 | Documentation, gate, PR | Done |

### Frontend

#### Reading the stream (`features/assistant/stream.ts`)

```ts
const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
let buffer = ''
for (;;) {
  const { value, done } = await reader.read()
  if (done) break
  buffer += value
  const parsed = parseEvents(buffer)          // complete "event:/data:" blocks; the rest waits
  buffer = parsed.rest
  parsed.events.forEach(onEvent)              // message_start, tool_call, delta, record_ref, message_end, error
}
```

A refusal before the stream (`429` budget or rate limit, `422`) is an `ApiError` like any other call; everything else uses the generated client and TanStack Query.

#### The drawer (`AssistantLauncher`, `AssistantPanel`, `AssistantMessage`)

- The header button appears only when `GET /assistant/status` says `enabled`; the drawer is a right-hand `complementary` region (Escape closes it), not a modal, so the page stays usable.
- The record in view comes from the URL (`/leads/:id`, `/opportunities/:id`, `/organizations/:id`): "Ask about this opportunity" is offered and checked; it becomes the new conversation's context, or the message's context in an existing conversation.
- While an answer streams, the stored messages are shown only up to the question (the server already holds the question and the unfinished answer), then the conversation is refetched.
- Answers render through `react-markdown` with `remark-gfm` and `skipHtml`; images are dropped and only links matching `/(leads|opportunities|organizations|contacts)/<uuid>` become links, everything else stays text:

```tsx
a: ({ href, children }) =>
  href && isRecordLink(href) ? <Link to={href}>{children}</Link> : <span>{children}</span>,
img: () => null,
```

- Each finished answer has Copy and, for people who may create records, "Save as note": an editable form with the target record (the record in view or a cited one), posting `save-as-note`; the record's timeline refreshes.

### Backend refinements (found by the journeys)

- **Usage of a stopped answer.** An answer cut off by Stop or by the browser leaving never receives the provider's usage; its tokens were recorded as 0. The open model call is now estimated (prompt and text size, four characters per token) for stopped answers; failed calls are still not charged.
- **Log noise.** LiteLLM's secret-redaction filter stamps every log record with `litellm_redacted`; the JSON formatter now leaves it out.
- **Scripted provider.** `fake_server` ignores clients that stop reading; an empty `LLM_API_BASE` (compose default) means OpenRouter.
- **End-to-end stack.** `docker-compose.e2e.yml` adds the `fake-llm` service and points the backend at it (`AI_ENABLED=true`, `LLM_API_BASE`); CI's E2E job uses it through `COMPOSE_FILE`.

### Verification (2026-11-18)

| Check | Result |
|---|---|
| ESLint, Prettier, tsc, i18n (1,012 keys), production build | clean |
| Vitest | 134 passed (12 new) |
| `pnpm audit --prod` with `react-markdown`, `remark-gfm` | no known vulnerabilities |
| Backend: ruff, mypy, import-linter, pytest | 1249 passed, 95.6% coverage; clean |
| Playwright Chromium against the rebuilt stack with `docker-compose.e2e.yml` | 28/28, including the assistant journey in en and bg (real LiteLLM client, streaming through Caddy) |
| GitHub Actions (PR #15, run 44241332019; PR #16, run 44244163565) | all four jobs green, including Playwright on Chromium and Firefox |

### Definition of done (Phase 7)

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | FR-AI-01..08 in API tests, Vitest and the E2E journey |
| 2 | `docker compose up` works | Done; with and without `docker-compose.e2e.yml` |
| 3 | Lint, types, suites green | Done locally and in CI (PR #15, PR #16) |
| 4 | Permission checks + matrix | Done (7a) |
| 5 | UI text en + bg | Done |
| 6 | Additive migrations + tests | Done (0010) |
| 7 | Audit | Done (7a) |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec v0.11 |
| Exit | Assistant answers from CRM data through read-only tools with the user's permissions, streamed, with links; switchable; limited | Done with scripted models; the live evaluation waits for OpenRouter credits |

### Decisions and deviations

- **The E2E stack uses a scripted provider server, not `LLM_FAKE`.** The approved plan was a fake selected by a setting refused in production; the E2E stack runs with `ENV=production`, so it reaches `app.llm.fake_server` through `LLM_API_BASE` instead, which also exercises the real LiteLLM client and streaming through Caddy (ADR 0026). `LLM_FAKE` remains for development.
- **Bulgarian wording.** The assistant uses the application's term „потенциален клиент“ for lead (the first draft said „лийд“; the evaluation question was changed to match).
- **Context from the URL**, not from each record page: the drawer offers the record whose page is open, so record pages needed no changes.

### Open items

1. Owner review of Phase 7 (PR #15 for 7a; the 7b PR).
2. Fund the OpenRouter account, then run `scripts/assistant_eval.py` and record the results.
3. Requirements question 1 (LLM data flow) before `AI_ENABLED=true` in production; the backend then needs outbound HTTPS to `openrouter.ai`.

## Phase 8a — GDPR tools, two-factor sign-in, security pass

Requirements: FR-ADM-04 (GDPR export and anonymization), FR-AUTH-07 (optional TOTP, enforceable for Admins), NFR-04 (OWASP ASVS Level 1), NFR-05 (privacy). Owner decisions (2026-11-18): build two-factor sign-in with `pyotp` 2.9.0 and a QR code (`qrcode.react` 4.2.0); anonymize the contact and linked leads, keep the audit log, list free-text mentions for manual review; no staging server (Phase 8b uses a second stack).

### Tasks

| # | Task | Result |
|---|---|---|
| 8a.1 | Migration 0011: MFA columns on `app_user`, `mfa_required_for_admins` setting | Done |
| 8a.2 | TOTP helpers (replay protection, recovery codes, pending-sign-in token); `login` split into password and code steps; setup, confirm, disable; Admin enforcement; `reset-mfa` CLI | Done |
| 8a.3 | GDPR export and anonymization through provider and anonymizer extension points (party, sales, activity, integration, assistant, audit) | Done (ADR 0027) |
| 8a.4 | Frontend: sign-in code step, two-factor card on the profile (QR, key, recovery codes, disable), forced setup for Admins, Admin setting, GDPR panel on the contact page, anonymized state, audit labels (en, bg) | Done |
| 8a.5 | Security pass: ASVS L1 checklist, fixes, header and cookie checks through Caddy | Done (`docs/security/asvs-l1.md`) |
| 8a.6 | Tests: API (MFA, GDPR, security headers, user race), Vitest, Playwright (privacy, security) | Done |
| 8a.7 | Documentation (spec v0.12, architecture, ADR 0027, checklist, this log, test record, README, CLAUDE.md), gate, PR | Done |

### Endpoints built (6)

`POST /auth/login/mfa`, `POST /auth/mfa/setup`, `POST /auth/mfa/confirm`, `POST /auth/mfa/disable`, `GET /contacts/{contact_id}/personal-data`, `POST /contacts/{contact_id}/anonymize`. The route catalog's pending list is now empty: every endpoint in the specification is built. `/me` gained `mfa_enabled` and `mfa_setup_required`; settings gained `mfa_required_for_admins` (additive).

### Backend

#### Sign-in in two steps (`identity/service.py`, `identity/mfa.py`)

```python
if user.mfa_enabled_at is not None:
    # FR-AUTH-07: the password is right; the session waits for the code.
    await ctx.session.commit()
    return MfaChallenge(token=mfa.pending_token(ctx.settings.app_secret_key, user.id, ctx.now))
return await _start_session(ctx, user)

def verify_code(secret, code, now, last_counter) -> int | None:
    current = int(now.timestamp()) // STEP_SECONDS
    for counter in (current - 1, current, current + 1):
        if last_counter is not None and counter <= last_counter:
            continue                                       # a code works once
        if hmac.compare_digest(totp.generate_otp(counter), digits):
            return counter
```

The router turns the challenge into `401 auth.mfa_required` with the pending cookie (`Path=/api/v1/auth/login`, 5 minutes). Wrong codes go through the same `_failed_attempt` as wrong passwords, so they lock the account too. While `mfa_required_for_admins` is on, an Admin without MFA gets `mfa_setup_required` on the principal and the permission dependency allows only `/me`, `/system/info`, sign-out and enrolment.

#### GDPR through extension points (`party/service.py`, `app/main.py`)

```python
PersonalDataProvider = Callable[[AsyncSession, DataSubject], Awaitable[Mapping[str, Any]]]
ContactAnonymizer = Callable[[AnonymizeContext, DataSubject], Awaitable[None]]

app.state.personal_data_providers = (
    *sales_service.PERSONAL_DATA_PROVIDERS,     # leads (linked or same email), opportunities
    activity_service.personal_data,            # linked activities, and mentions for review
    integration_service.personal_data,         # IDs in other systems
    assistant_service.personal_data,           # chat mentions with an excerpt
    audit_service.personal_data,               # number of entries kept
)
app.state.contact_anonymizers = sales_service.CONTACT_ANONYMIZERS   # clears person fields on leads
```

`anonymize_contact` replaces the personal fields, runs the anonymizers, and publishes `contact.anonymized` with the result only; further edits return `409 contact.anonymized`.

#### Security pass fixes

- `RequestContextMiddleware` adds `Cache-Control: no-store` to every `/api` response that sets none (ASVS 8.2.1).
- The Caddyfile CSP allows the toast library's two injected style blocks by hash. Before, they were blocked and toasts were unstyled behind the proxy (ASVS 14.4.3; found by the new no-violations check).
- `create_user` maps the unique-index error of a concurrent duplicate to `409 conflict.duplicate` instead of `500` (found by the privacy journey).
- Zod runs `jitless`: its `new Function` probe was blocked by the CSP and reported by Firefox (found by the security journey in CI).

### Frontend

- Sign-in: after `auth.mfa_required`, a code step that accepts a TOTP or a recovery code; back to the password when the five minutes pass.
- Profile: a "Two-factor sign-in" card with the QR code (`qrcode.react`), the key to type, confirmation, recovery codes shown once with Copy, and turning off with the password. Admins who must enrol are redirected to the profile and see only this card.
- Settings: "Require two-factor sign-in for Admins".
- Contact page (`gdpr.manage`): export as a JSON download, anonymize after typing ANONYMIZE; anonymized contacts show the date and lose the Edit button.

### Verification (2026-11-18)

| Check | Result |
|---|---|
| ruff, format, mypy (strict), import-linter (14) | clean |
| Migration 0011 up → down → up; `alembic check` | OK, no drift |
| pytest | 1295 passed, 95.5% coverage (identity MFA 98%, GDPR providers 92–95%) |
| pip-audit with `pyotp` 2.9.0 | no known vulnerabilities |
| ESLint, Prettier, tsc, i18n (1,064 keys), build | clean |
| Vitest | 143 passed (9 new) |
| `pnpm audit --prod` with `qrcode.react` | no known vulnerabilities |
| OpenAPI snapshot and generated types | up to date |
| Playwright Chromium against the rebuilt stack | 34/34, including the privacy journeys (en, bg) and the security checks |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | FR-ADM-04, FR-AUTH-07; ASVS IDs on the security tests |
| 2 | `docker compose up` works | Done (rebuilt with migration 0011; the proxy must be restarted after a Caddyfile change) |
| 3 | Lint, types, suites green | Done locally |
| 4 | Permission checks + matrix | Done for the 6 routes (GDPR Admin; MFA Signed-in/Public; closed to integration clients) |
| 5 | UI text en + bg | Done |
| 6 | Additive migrations + tests | Done (0011) |
| 7 | Audit | `user.mfa_*`, `contact.personal_data_exported`, `contact.anonymized` (result only), `lead.updated` with a reason |
| 8 | Frontend types regenerated | Done |
| 9 | Endpoints match the spec | Done; spec v0.12 |

### Decisions and deviations

- `login/mfa` is "Public" in the spec table (the pending cookie is described in the purpose) instead of a new access level "Public (pending-MFA cookie)".
- A new permission `gdpr.manage` (Admins) drives the GDPR panel; the server check is the Admin access level.
- No API to reset another user's second factor: the `reset-mfa` CLI only, so a stolen Admin session cannot remove it.
- Accepted ASVS deviations and open items are listed in the checklist and ADR 0027.

### Open items

1. ASVS open items for the owner: password strength meter and show-password toggle (2.1.8, 2.1.12), email notices after credential changes once SMTP is confirmed (2.2.3, 2.5.5), the privacy notice (8.3.3).
2. Phase 8b: accessibility, restore drill, integration readiness kit, guides, acceptance checklist, live assistant evaluation (OpenRouter credits), `v1.0.0`.

## Phase 8b — Accessibility, restore drill, integration readiness, guides, release

Requirements: NFR-03 (recovery objectives), NFR-05 (documented data flows), NFR-06, NFR-07 (tested restore), NFR-10 (accessibility), NFR-11, NFR-14; the implementation plan's Phase 8 items. Owner decisions (2026-11-18): `@axe-core/playwright` 4.14.0 (dev); no staging server, a second stack on the same host instead.

### Tasks

| # | Task | Result |
|---|---|---|
| 8b.1 | axe checks on every main page in Playwright; fixes | Done: no violations (`docs/accessibility.md`) |
| 8b.2 | Keyboard walkthroughs, automated; skip link; focus return from the assistant drawer | Done |
| 8b.3 | `scripts/restore.sh` and the restore drill into a fresh second stack | Done: 41 s from an empty server, counts identical |
| 8b.4 | `scripts/staging.sh`: the second stack for the teams; certificate mount for IT's TLS certificate | Done |
| 8b.5 | Operations guide (install, configuration reference, network rules, upgrade, backup and restore, security tasks, data flows and retention, staging, troubleshooting) | Done (`docs/operations-guide.md`) |
| 8b.6 | User guide in English and Bulgarian | Done (`docs/user-guide.en.md`, `docs/user-guide.bg.md`) |
| 8b.7 | Integration readiness kit (staging, network rules, key handover, checklist per team) | Done (`docs/integration-readiness.md`); the teams' runs wait for open questions 7 and 8 |
| 8b.8 | User acceptance checklist and release notes | Done; `v1.0.0` is tagged on acceptance |
| 8b.9 | Live assistant evaluation | Not run: the OpenRouter account still returns `402 Insufficient credits` |

### Accessibility fixes

```tsx
{/* WCAG 2.4.1: keyboard users skip the navigation. Visible when focused. */}
<a href="#main" className="sr-only focus:not-sr-only …">{t('nav.skipToContent')}</a>
<main id="main" tabIndex={-1} …>

<BarChart data={stages} accessibilityLayer={false}>   // hidden chart, figures in a table: not focusable

// destructive buttons: red text 20 % darker on the light tint (contrast 4.5:1)
'bg-destructive/10 text-[color-mix(in_oklch,var(--destructive),black_20%)] … dark:text-destructive'
```

The assistant launcher takes focus back when the drawer closes.

### Restore (`scripts/restore.sh`)

```bash
"${compose[@]}" stop backend worker proxy backup
"${compose[@]}" exec -T db psql -U postgres -d postgres -c "DROP DATABASE IF EXISTS crm WITH (FORCE)"
"${compose[@]}" exec -T -e CRM_MIGRATOR_PASSWORD=… -e CRM_APP_PASSWORD=… db bash /docker-entrypoint-initdb.d/10-init-roles.sh
"${compose[@]}" exec -T db pg_restore --exit-on-error --no-owner -U crm_migrator -d crm < "$dump"
"${compose[@]}" up --detach --wait        # pending migrations run first
```

It asks for the word RESTORE, and works on any stack through `CRM_ENV_FILE` and `COMPOSE_PROJECT_NAME`. The drill: a fresh stack `light-crm-drill` on ports 8080/8443 with the main stack's `APP_SECRET_KEY` and `APP_ENCRYPTION_KEY`, restored from that morning's backup (3.4 MB). Row counts of nine tables and the migration version were identical, and a restored Admin signed in and read data. The whole drill took 41 s against a recovery time objective of 4 hours.

### Found during the operations work

- The `proxy` service did not mount a directory for IT's certificate, although `.env.example` described `CRM_TLS=/certs/…`: added `CRM_CERTS_DIR` (default `./certs`, read-only, git-ignored).
- Single-file bind mounts (`Caddyfile`, `backup.sh`) keep pointing at the old file after a `git checkout`: the backup service could not run an on-demand backup, and an earlier Caddyfile change needed a proxy restart. The upgrade procedure restarts `proxy` and `backup`.
- The user guides first said error messages show a request ID and that managers roll imports back; neither is true (request IDs are in the `X-Request-ID` header and the audit log; rollback is Admin only). Corrected.

### Verification (2026-11-18)

| Check | Result |
|---|---|
| Playwright Chromium, accessibility and keyboard specs | 5/5 |
| Playwright Chromium, full suite on the rebuilt stack | 39/39, twice |
| ESLint, Prettier, tsc, Vitest (144), i18n (1,065 keys), build, `pnpm audit` | clean |
| Restore drill | 41 s, counts identical (operations guide 5.3) |
| Staging stack (`init`, `up`, `seed`) | Started, seeded (10,000 organizations, the three clients), removed |

### Definition of done (Phase 8)

| # | Item | State |
|---|---|---|
| 1 | AC tests with requirement IDs | NFR-10 journeys; FR-ADM-04, FR-AUTH-07 (8a) |
| 2 | `docker compose up` works | Done; also as a second stack (drill, staging) |
| 3 | Lint, types, suites green | Done locally; CI on the PRs |
| 4 | Permission checks + matrix | No new endpoints in 8b |
| 5 | UI text en + bg | Done (skip link) |
| 6 | Additive migrations + tests | No migration in 8b |
| 7 | Audit | No new changes |
| 8 | Frontend types regenerated | No API change in 8b |
| 9 | Endpoints match the spec | Unchanged; all specified endpoints built |
| Exit | Security pass, accessibility pass, backup and restore drill, guides, acceptance checklist, `v1.0.0` | Done except: the teams' staging runs (open questions 7 and 8), the live assistant evaluation (credits), the owner's acceptance and the tag |

### Open items

1. Owner: the acceptance checklist, open questions 1 and 4–8, the ASVS open items, the manual accessibility checks, and the tag `v1.0.0` after acceptance.
2. OpenRouter credits, then the live evaluation.
3. The restore drill repeated on the production server.

## After Phase 8 — live assistant evaluation (2026-11-18)

The OpenRouter account was funded, so the live evaluation ran against `openrouter/openai/gpt-oss-120b` on Cerebras (`docs/assistant-eval.md`):

| Run | Result | What changed afterwards |
|---|---|---|
| 1 | 10/20 | Answers in the wrong language (6 cases); "the open pipeline" read as the user's own (2); checker problems (2). |
| 2 | 18/20 | Only checker problems were left: a typographic apostrophe, and an injection case that could not tell quoting from obeying. |
| 3 | **20/20** | Median 1.3 s per answer; 65,217 tokens for the 20 cases. |

#### The answer language is decided by the backend (`assistant/prompt.py`)

```python
def reply_language(text: str) -> str:
    words = [w.casefold() for w in _WORD.findall(text)]
    english = sum(w in _EN_WORDS for w in words)       # who, what, my, show, ...
    bulgarian = sum(w in _BG_WORDS for w in words)     # кой, какви, моите, покажи, ...
    if english != bulgarian:
        return "en" if english > bulgarian else "bg"
    ...                                                # otherwise the script of the letters

# system prompt
Language: the user's latest message is in {language}. Write your whole answer in
{language}, including table headings, whatever the language of the record names ...
```

The tool results (stage names, sources) use the same language. The prompt also says to use owner "me" only for "my / mine / I have". The evaluation script now sends logs to stderr, normalizes typography before matching, ignores record names when judging the language, and labels dry runs. LiteLLM's own INFO lines no longer reach the JSON logs.

The same PR fixes `main`, whose end-to-end job failed after #18: the red "Locked" badge was below 4.5:1 (the light `--destructive` is now red 700), and the Firefox keyboard journey now reloads before tabbing to the header. CI: PR #19 run 44268290688, all four jobs green.

Open items: the owner's acceptance (`docs/acceptance-checklist.md`), then the tag `v1.0.0`; open questions 1 and 4–8.

## Owner answers to the open questions (2026-11-18)

The owner answered requirements section 8 (recorded there, in the acceptance checklist and in ADR 0028).

| # | Answer | What changed |
|---|---|---|
| 1 | LLM data flow approved | Docs; switch on per deployment with `AI_ENABLED=true` and the key (code default stays off) |
| 2 | No tracker copies; suggest a format | `docs/import-format.md` (generated from the import fields, both languages) and four fictional sample CSVs in `docs/import-samples/`; a test imports them through the API (12 rows, all valid) |
| 3 | Default stages stay, editable | Nothing to build (Admin **Stages**, FR-ADM-02) |
| 4 | SMTP optional | Security notice emails after password change or reset and two-factor on, off or reset, only when SMTP is configured (ASVS 2.2.3, 2.5.5 now met) |
| 5 | Copies on another machine; 10 days locally | `BACKUP_RETENTION_DAYS` default 10 (compose, `.env.example`, `backup.sh`); the operations guide adds the nightly copy with a cron example |
| 6 | A1 now, option later | ADR 0028 describes how restricted visibility would be added; nothing built |
| 7 | All APIs and data for now; no addresses yet | The three profiles get every integration scope; closed endpoints stay closed; the Phase 6 exit test keeps the original narrow scopes to test the mechanism |
| 8 | API keys, with OAuth 2.0 or mutual TLS possible | ADR 0028 and API spec section 20 describe both; nothing built |

#### Security notices (`identity/service.py`, `identity/emails.py`)

```python
async def _notify(mailer: Mailer, user: User, kind: str, at: datetime) -> None:
    """Tell the user about a change to how they sign in, when SMTP is configured.
    Sent after the change is committed; a mail failure never undoes the change."""
    if mailer.enabled:
        await mailer.send(security_notice_email(to=user.email, name=user.full_name,
                                                locale=user.locale, kind=kind, at=at))
```

Called after `change_password`, a password set from a reset link (not from an invitation), `mfa_confirm`, `mfa_disabled` and the CLI `reset-mfa`.

## Release v1.0.0 (2026-11-18)

The owner accepted Release 1 and asked for the tag. `v1.0.0` is an annotated tag on `main` 026719d (the merge of #20; CI run 44277448331 green on all four jobs), published as the GitHub release `v1.0.0`. The local stack was rebuilt from that commit following the upgrade procedure (images rebuilt, `proxy` and `backup` restarted).

Open after the release (none blocking): the integrating teams' addresses and detailed flows (open question 7); the off-server backup copy and a restore drill on the production server; the ASVS open items 2.1.8, 2.1.12 and 8.3.3; the manual accessibility checks. Work beyond Release 1 (implementation plan, "After R1") needs the owner's go-ahead.

## UI polish after Release 1 (2026-11-18)

Run as a loop over `docs/loops/ui-polish-backlog.md` (prompt `docs/loops/PROMPT-ui-polish.md`; the owner pre-approved sections A and B). The per-item record with files, tests, screenshots and gate results is `docs/loops/ui-polish-progress.md`. All 22 items are done (FN-05 after the owner approved its API addition).

| Item | What was built |
|---|---|
| UX-01 | Every color from theme tokens (`--brand` with `TODO(owner): brand color`, `--success`, `--overlay`, `--qr-surface`, `--destructive-foreground`); a test fails on color literals or Tailwind palette classes |
| UX-02 | App shell: grouped sidebar (collapsible, remembered per session), drawer below 1024 px, account menu (profile, language, sign out) |
| UX-03 | `PageHeader` with breadcrumbs and description on every page; `AuthCard` for signed-out pages; a test fails on any other `<h1>` |
| UX-04 | Skeleton `Loading` (table, form, page), `EmptyState`, `ErrorState` and route errors with retry and the request ID (`ApiError.requestId`) |
| UX-05 | `useNotify` is the only toast path (lint rule); `window.confirm/alert/prompt` banned; session sign-out confirmed |
| UX-06 | Sign-in: `PasswordInput` (show/hide, Caps Lock), spinner, remaining lockout minutes, focus to the error |
| UX-07 | `PasswordChecklist`; a page for used or expired links |
| UX-08 | Users table on `DataTable` with row action menus (`RowActions`), `RelativeTime`; **API:** optional `sort` on `GET /users` (additive, spec section 5) |
| UX-09 | Shared `Sheet`; create and edit users in sheets; one-time link shown once and kept out of the query and mutation caches |
| UX-10 | Audit log: user, record-type and date filters with presets; drawer with a before/after field diff (`AuditDiff`); 52 action names translated |
| UX-11 | `FormField` `required` marker and `aria-required` on every validated field; `UnsavedChangesGuard` on record, settings, profile and activity forms |
| UX-12 | axe on every route; focus ring token raised to 3:1 and measured in the browser |
| UX-13 | Bulgarian layout: `FilterBar`, secondary columns hidden below 1024 px, compact chart axes; `e2e/layout.spec.ts` |
| UX-14 | 152 screenshot baselines (`pnpm e2e:visual`, macOS) with deterministic API responses and masks |
| FN-01, FN-02 | Password change with the checklist; readable session devices (`lib/userAgent.ts`) |
| FN-03 | Confirmed account actions in the users row menu (`useUserActions`, `ConfirmDialog`) |
| FN-04 | A 401 records whether a session was lost; `RequireAuth` sends to `/sign-in?next=…&expired=1` with a message, and back after signing in |
| FN-06, FN-07 | Already built; tests added (language at sign-in on another device; audit export with the current filters) |
| FN-08 | Last active Admin: role locked and Deactivate explained (`useLastAdmin`); the backend 409 was already specified and tested |
| FN-05 | Idle-timeout warning across tabs (`IdleWarning`, `sessionActivity.ts`); **API:** `GET /me` gained `session: { idle_timeout_minutes, expires_at }` (additive, owner-approved 2026-11-18) |

Also fixed on the way: the assistant's live answer remounted when the conversation reloaded and dropped an opened "save as note" form (the cause of an intermittent E2E failure); table cells with `display: flex` in stages and lists; a missing value and `null` shown as a change in the audit diff.

#### The one redirect for a lost session (`app/queryClient.ts`, `features/auth/RequireAuth.tsx`)

```ts
const handle = (error: unknown) => {
  if (isUnauthorized(error)) {
    // FN-04: someone who was signed in lost their session; a first visit did not.
    const previous: unknown = queryClient.getQueryData(ME_QUERY_KEY)
    queryClient.setQueryData(SESSION_EXPIRED_KEY, previous != null)
    queryClient.setQueryData(ME_QUERY_KEY, null)
  }
}
// RequireAuth
if (!me) {
  const expired = queryClient.getQueryData<boolean>(SESSION_EXPIRED_KEY) === true
  return <Navigate to={signInAfterUnauthorized(location, expired)} replace />
}
```

#### Leaving a form with changes (`components/UnsavedChangesGuard.tsx`)

```ts
const blocker = useBlocker(({ currentLocation, nextLocation }) =>
  when &&
  // A lost session (FN-04) goes to sign-in regardless: the changes could not be saved.
  nextLocation.pathname !== '/sign-in' &&
  (currentLocation.pathname !== nextLocation.pathname ||
    currentLocation.search !== nextLocation.search))
```

Deviations and open items:
- The visual baselines are macOS renderings and run with `pnpm e2e:visual`, not in CI. Linux baselines would need the Playwright Docker image or a CI job (proposal C-10).
- `pnpm e2e` now names its projects (`chromium`, `firefox`) so the visual project stays out of it.
- Owner decisions are listed in section C of the backlog:
  - C-01 branding, C-02 dark mode, C-04 command palette, C-05 system status, C-06 sign-in notice;
  - C-09 locked-users filter, C-10 visual baselines in CI.

## CRM UI improvements loop (2026-11-18)

Best-practice improvements after the UI polish, recorded per iteration in [`docs/loop_result.md`](loop_result.md) (branch `ui-improvements`, stacked on PR #22). Frontend only, with no API change.

- **Iteration 1:**
  - Descriptive browser-tab titles on every page (`usePageTitle`, WCAG 2.4.2).
  - Email, phone and website as links on contacts, leads and organizations (`ContactLinks`). Websites only for `http`/`https`, opened with `noopener noreferrer`.

```ts
export function websiteHref(website: string): string | null {
  const candidate = /^[a-z][a-z\d+.-]*:/i.test(website) ? website : `https://${website}`
  try {
    const url = new URL(candidate)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}
```
