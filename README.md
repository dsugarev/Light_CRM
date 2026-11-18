# Light CRM

A light B2B CRM for the Commercial team: lead and opportunity management, an AI assistant, and an integration API for Conclusion, ERP and Billing. On-premises, Docker Compose.

Status: **Release 1 complete, awaiting the owner's acceptance** (`v1.0.0` is tagged on acceptance; see the [acceptance checklist](docs/acceptance-checklist.md)). Users sign in; Admins manage users, lists, pipeline stages and the audit log; everyone works with organizations, contacts and leads (BANT qualification, lifecycle, assignment, conversion), opportunities on a Kanban pipeline board, activities and tasks with record timelines, with search in Cyrillic and Latin. A dashboard, a win/loss report, XLSX/CSV export of every list and Excel/CSV import with preview and rollback are available. Conclusion, ERP and Billing can be registered as integration clients with scoped API keys and use the same API, with IDs in those systems recorded on records, and receive signed webhooks with a delivery log; see the [integration guide](docs/integration-guide.md). An AI assistant (a chat drawer on every page that answers from CRM data through read-only tools, with record context, history and drafts saved as notes on request) is built and off by default. Users can turn on two-factor sign-in (it can be required for Admins), and Admins can export or anonymize a contact's personal data (GDPR). See [`docs/Plan.md`](docs/Plan.md) for what is built.

## Documentation

| Document | Contents |
|---|---|
| [`docs/01-requirements.md`](docs/01-requirements.md) | Requirements with IDs and acceptance criteria |
| [`docs/02-architecture.md`](docs/02-architecture.md) | Stack, layout, data model, security, AI design |
| [`docs/03-implementation-plan.md`](docs/03-implementation-plan.md) | Phases and definition of done |
| [`docs/04-test-strategy.md`](docs/04-test-strategy.md) | Required tests |
| [`docs/05-api-specification.md`](docs/05-api-specification.md) | Every REST endpoint, error codes, integration API |
| [`docs/integration-guide.md`](docs/integration-guide.md) | For the Conclusion, ERP and Billing teams: keys, sync, external IDs, webhooks, samples, Postman collection |
| [`docs/adr/`](docs/adr/README.md) | Architecture decision records |
| [`docs/Plan.md`](docs/Plan.md) | Implementation log: what was built, with code excerpts |
| [`docs/Test_strategy.md`](docs/Test_strategy.md) | Test record: strategy per phase, test cases performed and results |
| [`docs/api/`](docs/api/README.md) | OpenAPI snapshot and how to open the interactive API docs |
| [`docs/operations-guide.md`](docs/operations-guide.md) | Install, configuration reference, network rules, upgrade, backup and restore, security tasks, data flows, staging, troubleshooting |
| [`docs/user-guide.en.md`](docs/user-guide.en.md), [`docs/user-guide.bg.md`](docs/user-guide.bg.md) | Short user guide in English and Bulgarian |
| [`docs/integration-readiness.md`](docs/integration-readiness.md) | Staging, network rules, key handover and a checklist per integrating team |
| [`docs/accessibility.md`](docs/accessibility.md) | Accessibility checks, keyboard walkthroughs and the manual checks still to do |
| [`docs/acceptance-checklist.md`](docs/acceptance-checklist.md), [`docs/release-notes.md`](docs/release-notes.md) | User acceptance checklist for the owner; release notes |
| [`docs/security/asvs-l1.md`](docs/security/asvs-l1.md) | OWASP ASVS Level 1 checklist with evidence and open items |
| [`docs/assistant-eval.md`](docs/assistant-eval.md) | Live evaluation of the AI assistant: cases, how to run, results |

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

On first run the start script creates `.env` from `.env.example` with random database passwords and secret key (and adds settings introduced by later releases, such as `APP_SECRET_KEY`, to an existing `.env`). The CRM is then at **https://localhost**. Caddy uses its own local certificate authority, so the browser warns until you trust it (or set `CRM_TLS` to a real certificate, see `.env.example`).

There is no default account. Create the first Admin, then open the printed one-time link to set the password:

```bash
docker compose exec backend python -m app.cli create-admin --email you@company.bg --full-name "Your Name"
```

Without SMTP (`SMTP_HOST` empty) nothing is emailed: Admins create users in the UI and hand over the one-time link shown there.

Integration clients for Conclusion, ERP and Billing (read-only profiles, API spec 19.9) can be created with the command below; they start inactive and without keys. An Admin activates a client and issues its API key under **Integrations** once the owner has confirmed the data flow.

```bash
docker compose exec backend python -m app.cli create-integration-client   # --system erp|billing|conclusion|all
```

Backups run nightly into `backups/`; restore one with `scripts/restore.sh backups/<file>.dump`. A second stack for the integrating teams and acceptance tests runs with `scripts/staging.sh` (ports 8080/8443). After an upgrade, restart `proxy` and `backup`. Details: [operations guide](docs/operations-guide.md).

Webhooks are sent by the `worker` service only to hosts listed in `WEBHOOK_ALLOWED_HOSTS` (`.env`, comma-separated, exact names or `*.suffix`); the worker needs outbound HTTPS to them. Webhook signing secrets are encrypted with `APP_ENCRYPTION_KEY`, which the start script generates: keep it with the database backups, because without it stored secrets must be rotated.

The AI assistant is off (`AI_ENABLED=false`) until the owner confirms the data flow: questions and the CRM data the assistant looks up are sent to OpenRouter and Cerebras. To switch it on, set `AI_ENABLED=true` and `OPENROUTER_API_KEY` (a funded OpenRouter account) in `.env`; the backend then needs outbound HTTPS to `openrouter.ai`.

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
uv run python -m app.cli create-integration-client [--system erp|billing|conclusion|all]
uv run python -m app.cli seed-demo   # fictional NFR-01 volumes; refused in production
uv run python -m app.cli reset-mfa --email user@example.test   # lost authenticator device
uv run python scripts/assistant_eval.py   # live assistant evaluation (docs/assistant-eval.md)
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

The assistant journeys need the stack with the scripted model provider (no network, production settings otherwise):

```bash
COMPOSE_FILE=docker-compose.yml:docker-compose.e2e.yml docker compose up --build -d
```

## Layout

```
backend/    FastAPI app (app/), Alembic migrations, tests; API, worker and CLI in one image
frontend/   React SPA; built into the Caddy proxy image
deploy/     Caddyfile, PostgreSQL role setup, backup script
scripts/    start/stop for macOS, Linux, Windows
docs/       specifications, ADRs, implementation log
```
