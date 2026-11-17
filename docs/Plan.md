# Implementation log

What has been built, phase by phase, with the key code. The specifications in `docs/01`–`05` say what to build; this file records what exists, how it works, how it was verified, and what was deferred or decided along the way. The test cases performed in each phase are recorded in [`Test_strategy.md`](Test_strategy.md); the API documentation is [`05-api-specification.md`](05-api-specification.md) plus the OpenAPI snapshot in [`api/`](api/README.md).

| Phase | Status | Branch |
|---|---|---|
| 0 — Foundation | Done, merged (PR #1) | `phase-0-foundation` |
| 1 — Identity, access and audit | Done, merged (PR #2), CI green | `phase-1-identity` |
| 2 — Organizations and contacts | Done, merged (PR #4) | `phase-2-party` |
| 3 — Leads | Done, merged (PR #5) | `phase-3-leads` |
| 4a — Pipelines, opportunities and board | Built; PR open, owner review after 4b | `phase-4a-opportunities` |
| 4b — Activities, timelines and lead conversion | Not started | — |

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

1. Phase 4b: activities and tasks (`/activities`, `/me/tasks`), `last_activity_at`, timelines (ADR for `timeline_event`), lead conversion, the full lead → won journey, then owner review of 4a + 4b.

