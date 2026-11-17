# Implementation log

What has been built, phase by phase, with the key code. The specifications in `docs/01`–`05` say what to build; this file records what exists, how it works, how it was verified, and what was deferred or decided along the way.

| Phase | Status | Branch |
|---|---|---|
| 0 — Foundation | Built, CI green, awaiting owner review | `phase-0-foundation` (PR #1) |
| 1 — Identity, access and audit | Not started | — |

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
