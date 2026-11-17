# Light CRM

A light B2B CRM for the Commercial team: lead and opportunity management, an AI assistant, and an integration API for Conclusion, ERP and Billing. On-premises, Docker Compose.

Status: **Phase 1 (identity, access and audit)**. Users sign in, Admins manage users and see the audit log; leads and opportunities follow in later phases. See [`docs/Plan.md`](docs/Plan.md) for what is built.

## Documentation

| Document | Contents |
|---|---|
| [`docs/01-requirements.md`](docs/01-requirements.md) | Requirements with IDs and acceptance criteria |
| [`docs/02-architecture.md`](docs/02-architecture.md) | Stack, layout, data model, security, AI design |
| [`docs/03-implementation-plan.md`](docs/03-implementation-plan.md) | Phases and definition of done |
| [`docs/04-test-strategy.md`](docs/04-test-strategy.md) | Required tests |
| [`docs/05-api-specification.md`](docs/05-api-specification.md) | Every REST endpoint, error codes, integration API |
| [`docs/adr/`](docs/adr/README.md) | Architecture decision records |
| [`docs/Plan.md`](docs/Plan.md) | Implementation log: what was built, with code excerpts |
| [`docs/Test_strategy.md`](docs/Test_strategy.md) | Test record: strategy per phase, test cases performed and results |
| [`docs/api/`](docs/api/README.md) | OpenAPI snapshot and how to open the interactive API docs |

## Run it

Prerequisite: Docker (Docker Desktop on macOS/Windows, Docker Engine with the Compose plugin on Linux).

```bash
scripts/start-mac.sh        # or scripts/start-linux.sh
scripts/stop-mac.sh         # or scripts/stop-linux.sh
```

```powershell
.\scripts\start-windows.ps1
.\scripts\stop-windows.ps1
```

On first run the start script creates `.env` from `.env.example` with random database passwords. The CRM is then at **https://localhost**. Caddy uses its own local certificate authority, so the browser warns until you trust it (or set `CRM_TLS` to a real certificate, see `.env.example`).

There is no default account. Create the first Admin, then open the printed one-time link to set the password:

```bash
docker compose exec backend python -m app.cli create-admin --email you@company.bg --full-name "Your Name"
```

Without SMTP (`SMTP_HOST` empty) nothing is emailed: Admins create users in the UI and hand over the one-time link shown there.

## Develop

Development stack (backend with hot reload on http://localhost:8000, interactive API docs at http://localhost:8000/api/docs, PostgreSQL on localhost:5432 with a `crm_test` database):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
cd frontend && pnpm install && pnpm dev   # http://localhost:5173, proxies /api to :8000
```

Backend (from `backend/`, needs uv and a PostgreSQL with the roles from `deploy/postgres/init-roles.sh`):

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run python -m app.worker
uv run python -m app.cli export-openapi --output openapi.json
uv run python -m app.cli create-admin --email admin@example.test --full-name "Admin"
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest
```

Frontend (from `frontend/`, needs Node 24+ and pnpm):

```bash
pnpm install
pnpm dev
pnpm lint && pnpm typecheck
pnpm test
pnpm check:i18n
pnpm generate:api [openapi.json]   # regenerate src/api/schema.d.ts (default: running backend)
pnpm e2e                           # Playwright against https://localhost (E2E_BASE_URL to override);
                                   # needs E2E_ADMIN_EMAIL_EN/_BG and E2E_ADMIN_PASSWORD (see e2e/support.ts)
```

## Layout

```
backend/    FastAPI app (app/), Alembic migrations, tests; API, worker and CLI in one image
frontend/   React SPA; built into the Caddy proxy image
deploy/     Caddyfile, PostgreSQL role setup, backup script
scripts/    start/stop for macOS, Linux, Windows
docs/       specifications, ADRs, implementation log
```
