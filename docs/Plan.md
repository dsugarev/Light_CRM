# Implementation log

What has been built, phase by phase, with the key code. The specifications in `docs/01`–`05` say what to build; this file records what exists, how it works, how it was verified, and what was deferred or decided along the way.

| Phase | Status | Branch |
|---|---|---|
| 0 — Foundation | Done, merged (PR #1) | `phase-0-foundation` |
| 1 — Identity, access and audit | Built, awaiting owner review | `phase-1-identity` |

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
| GitHub Actions | on the Phase 1 pull request |

### Definition of done

| # | Item | State |
|---|---|---|
| 1 | AC tests named with requirement IDs | Done for FR-AUTH-01..06, FR-ADM-01, FR-ADM-03, FR-I18N-01..03 |
| 2 | `docker compose up` works | Done |
| 3 | Lint, types, suites green | Done locally; CI on the PR |
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

1. Owner review of PR for Phase 1.
2. Confirm the password link lifetimes (72 h / 2 h).
3. SMTP relay details when available (open question 4); set `SMTP_*` in `.env`.
