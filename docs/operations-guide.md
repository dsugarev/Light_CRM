# Operations guide

For the people who install and run Light CRM on the company server. It covers installation, configuration, upgrades, backup and restore, user and security tasks, the staging stack, and the data flows that matter for privacy (NFR-05).

The CRM is a Docker Compose stack (NFR-06):

| Service | Role |
|---|---|
| `proxy` | Caddy: HTTPS on ports 443/80 (the only published ports), security headers, the web app |
| `backend` | The API (two worker processes) |
| `worker` | Webhook delivery and housekeeping (expired sessions, rate-limit counters, old webhook events) |
| `migrate` | Runs database migrations on every start, then exits |
| `db` | PostgreSQL 18 (data in the `db-data` volume) |
| `backup` | Nightly `pg_dump` into `CRM_BACKUP_DIR` |

## 1. Install

Requirements: a Linux server (or Windows/macOS with Docker Desktop for trials), Docker Engine with Compose v2, 4 GB RAM, 20 GB disk plus backups, a DNS name on the company network and, for production, a TLS certificate from IT.

```bash
git clone <repository> light-crm && cd light-crm
scripts/start-linux.sh            # first run creates .env with generated passwords and keys
```

The first run creates `.env` from `.env.example` with random database passwords, `APP_SECRET_KEY` and `APP_ENCRYPTION_KEY`. Then edit `.env` (section 2): at least `CRM_SITE_ADDRESS`, `CRM_PUBLIC_URL` and `CRM_TLS`, and run `scripts/start-linux.sh` again.

Create the first Admin; the command prints a one-time link to set the password (valid 72 hours):

```bash
docker compose exec backend python -m app.cli create-admin --email admin@company.bg --full-name "First Admin"
```

The Admin then creates the other users under **Users**; each gets a one-time link (by email if SMTP is configured, otherwise the Admin passes it on).

Keep `.env` readable by root only (`chmod 600 .env`). Never commit it.

## 2. Configuration reference (`.env`)

Only the variables below reach the containers (see `docker-compose.yml`); everything else keeps its built-in default. After a change, run `docker compose up -d` (it recreates what changed).

### Site and security

| Variable | Default | Meaning |
|---|---|---|
| `ENV` | `production` | `production` refuses placeholder secrets, hides the API docs and refuses test-only settings. `test` is for the staging stack |
| `CRM_SITE_ADDRESS` | `localhost` | Host name users open |
| `CRM_PUBLIC_URL` | `https://localhost` | Full address, used in emailed links and the CSRF origin check |
| `CRM_TLS` | `internal` | `internal` (Caddy's own CA, trials only) or `/certs/crm.crt /certs/crm.key` for the certificate from IT |
| `CRM_CERTS_DIR` | `./certs` | Directory holding `crm.crt` (with the chain) and `crm.key`, mounted read-only into the proxy as `/certs`. After replacing the files: `docker compose restart proxy` |
| `CRM_HTTP_PORT`, `CRM_HTTPS_PORT` | 80, 443 | Published ports |
| `APP_SECRET_KEY` | generated | Signs sync cursors and two-factor sign-in steps. Changing it invalidates them (no data loss) |
| `APP_ENCRYPTION_KEY` | generated | Encrypts webhook signing secrets and two-factor secrets. **Keep it with the backups**: without it, those secrets cannot be read (section 5.4) |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` |

### Database and backups

| Variable | Default | Meaning |
|---|---|---|
| `POSTGRES_PASSWORD` | generated | Database superuser (used only by the database container and restores) |
| `CRM_MIGRATOR_PASSWORD` | generated | Owner of the schema; runs migrations and backups |
| `CRM_APP_PASSWORD` | generated | Used by the backend and worker; data access only, cannot change the schema or the audit log |
| `CRM_EXTRA_DATABASES` | empty | Extra databases on first start, e.g. `crm_test` for developers |
| `CRM_BACKUP_DIR` | `./backups` | Where nightly backups are written (put it on a different disk or a mounted share) |
| `BACKUP_TIME` | `02:00` | Local time (Europe/Sofia) of the nightly backup |
| `BACKUP_RETENTION_DAYS` | 10 | Backups older than this are deleted from the server; the copies on the other machine keep 30 days (NFR-07; owner decision, ADR 0028) |

### Users, email and limits

| Variable | Default | Meaning |
|---|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | empty, 587 | Optional mail relay (STARTTLS). With it: invitation and password-reset links by email, and a security notice to the user after a password change or reset and after two-factor sign-in is turned on, off or reset. Without it, password links are shown to Admins and "forgot password" sends nothing |
| `RATE_LIMIT_LOGIN_PER_MINUTE` | 10 | Sign-in attempts per minute per IP |
| `RATE_LIMIT_PASSWORD_PER_15_MINUTES` | 5 | Password-link requests per 15 minutes per IP |
| `RATE_LIMIT_USER_PER_MINUTE` | 600 | API requests per minute per user |

Session timeouts, the stale-opportunity threshold and "Require two-factor sign-in for Admins" are changed by an Admin under **Settings**, not here.

### Integrations

| Variable | Default | Meaning |
|---|---|---|
| `WEBHOOK_ALLOWED_HOSTS` | empty | Host names webhook subscriptions may target, comma-separated, exact or `*.suffix` (e.g. `erp.company.local,*.billing.company.local`). Empty: webhooks are off. Loopback, link-local and metadata addresses are always refused |

### AI assistant

| Variable | Default | Meaning |
|---|---|---|
| `AI_ENABLED` | `false` | Approved by the owner (2026-11-18); set to `true` together with `OPENROUTER_API_KEY` (section 8) |
| `OPENROUTER_API_KEY` | empty | Key of a funded OpenRouter account: the default model and the free Nemotron option |
| `GEMINI_API_KEY` | empty | Google AI Studio key: makes the Gemini 3.5 Flash option available (ADR 0031). `AI_ENABLED=true` needs at least one of the two keys |
| `LLM_MODEL`, `LLM_PROVIDER` | `openrouter/openai/gpt-oss-120b`, `cerebras` | The default catalog model (`gpt-oss-120b`) and its only provider (no fallbacks). The model in use is the Admin's choice in **Settings** |
| `LLM_TIMEOUT_SECONDS` | 60 | Per model call |
| `LLM_API_BASE` | empty | An OpenAI-compatible gateway instead of OpenRouter (end-to-end tests use it) |
| `AI_DAILY_TOKEN_BUDGET` | 200000 | Tokens per user per day (from midnight Sofia time). Since the assistant prepares actions (R1.1), an answer uses about 12,000 tokens, so 200,000 allow about 16 answers a day; raise it if users run out |
| `RATE_LIMIT_ASSISTANT_PER_10_MINUTES` | 20 | Questions per user per 10 minutes |
| `LLM_FAKE` | `false` | Development only; refused in production |

## 3. Network rules

| Direction | From → to | Port | Needed for |
|---|---|---|---|
| Inbound | Users' network and VPN → CRM server | 443 (and 80, redirected) | The application (NFR-06) |
| Inbound | Conclusion, ERP, Billing servers → CRM server | 443 | The integration API (API keys; optional IP allowlist per client) |
| Outbound | CRM server (`worker`) → each host in `WEBHOOK_ALLOWED_HOSTS` | 443 | Webhooks |
| Outbound | CRM server (`backend`) → `openrouter.ai` | 443 | The AI assistant, only when `AI_ENABLED=true` |
| Outbound | CRM server → the SMTP relay | 587 | Optional emails |

Nothing else is needed. The database is never published.

## 4. Upgrade

1. Read the release notes (`docs/release-notes.md`) and the PR descriptions for operator steps.
2. Take a backup now: `docker compose exec backup bash /usr/local/bin/backup.sh --now`.
3. Get the new version: `git fetch --tags && git checkout v1.x.y`.
4. Start it: `scripts/start-linux.sh` (or `docker compose up --build -d --wait`). The `migrate` service applies new migrations before the backend starts; migrations are additive only (architecture 4.2).
5. **Restart `proxy` and `backup`**: `docker compose restart proxy backup`. They read files mounted from the repository (`deploy/caddy/Caddyfile`, `deploy/backup/backup.sh`); after a checkout the running containers still see the old files.
6. Check: `curl -k https://<site>/api/health/ready` returns `{"status":"ok"}`; sign in.

Planned downtime is outside 08:00–19:00 Sofia time (NFR-03); tell the Conclusion, ERP and Billing teams in advance (NFR-14). Webhook events raised while the CRM is down are delivered after it starts.

## 5. Backup and restore (NFR-07)

### 5.1 Nightly backups

The `backup` service writes `crm-<UTC time>.dump` (PostgreSQL custom format) to `CRM_BACKUP_DIR` at `BACKUP_TIME` and deletes files older than `BACKUP_RETENTION_DAYS`. Check it each week: `ls -lh backups/` shows a file per night; `docker compose logs backup` shows each run. A backup takes a few seconds (3.5 MB with the NFR-01 demo volumes).

On demand: `docker compose exec backup bash /usr/local/bin/backup.sh --now`.

**Copy the backups to another machine every night** (owner decision): the server keeps 10 days, the other machine 30 (NFR-07). For example, on the CRM server, a cron entry at 03:00 after the 02:00 backup:

```bash
0 3 * * * rsync -a --include='crm-*.dump' --exclude='*' /opt/light-crm/backups/ backup-host:/srv/crm-backups/
```

Do not use `--delete`: it would remove the other machine's copies once the server has pruned them after 10 days. On the other machine, delete copies older than 30 days (`find /srv/crm-backups -name 'crm-*.dump' -mtime +30 -delete`). Keep `APP_ENCRYPTION_KEY` with the copies, in a separate secure place.

### 5.2 Restore

```bash
scripts/restore.sh backups/crm-20261118T073438Z.dump     # asks you to type RESTORE
```

The script stops the application services, recreates the `crm` database with its roles and grants, restores the dump as the schema owner, starts the stack (newer migrations run, so an older backup is brought up to date) and waits until it is ready. It replaces all current data.

Restoring onto a **new server**: install as in section 1, but before the first start copy the old `APP_ENCRYPTION_KEY` and `APP_SECRET_KEY` into the new `.env`, start the stack, then run `scripts/restore.sh`.

After a restore:
- users sign in again if their sessions were created after the backup;
- re-apply any GDPR anonymizations done after the backup (the audit log of the old system, or the person's request record, lists them; section 7);
- tell the integrating teams: changes after the backup time are gone, and their sync mode (`updated_since`) catches up from their last cursor.

### 5.3 Restore drill (record)

| Date | Where | Backup | Steps | Result |
|---|---|---|---|---|
| 2026-11-18 | Developer Mac (Docker Desktop), a fresh second stack (`COMPOSE_PROJECT_NAME=light-crm-drill`, ports 8080/8443) standing in for a new server | `crm-20261118T073438Z.dump`, 3.4 MB, 15,230 organizations, 20,107 leads, 5,151 opportunities, 8,094 audit entries | Empty stack up (26 s); `scripts/restore.sh` with the drill's `.env` (15 s); compare row counts of 9 tables and the migration version; sign in with a restored account and read data | Counts identical, migration 0011; sign-in and data access work. **41 s from an empty server to a working, restored CRM**, well within the 4-hour recovery time objective (NFR-03) |

Repeat the drill on the production server before go-live and once a year, and record it here.

### 5.4 Losing `APP_ENCRYPTION_KEY`

Everything restores, but webhook signing secrets and two-factor secrets cannot be read. Then:
- rotate every webhook secret (**Integrations → client → subscription → Rotate secret**) and give the new secrets to the teams;
- reset two-factor sign-in for each user who had it (`reset-mfa`, section 6); they set it up again.

## 6. Users and security tasks

| Task | How |
|---|---|
| First Admin | `docker compose exec backend python -m app.cli create-admin --email … --full-name …` |
| A user forgot the password | Admin: **Users → user → Create password reset link** (sent by email, or shown to the Admin to pass on) |
| A user is locked out (5 wrong passwords or codes) | Wait 15 minutes, or Admin: **Users → user → Unlock** |
| A user lost the authenticator phone and the recovery codes | `docker compose exec backend python -m app.cli reset-mfa --email …` (ends their sessions; audited as `user.mfa_reset`). There is deliberately no web screen for this |
| Require two-factor sign-in for Admins | Admin: **Settings → Security** |
| Someone left the company | Admin: **Users → Deactivate** (their sessions end; records stay) |
| Integration clients and keys | Admin: **Integrations**. Keys are shown once; at most two per client; expire after 12 months (24 at most). `create-integration-client` gives every integration scope for now (ADR 0028); set a default owner before a system creates records |
| Mutual TLS or OAuth 2.0 for integrations | Not configured. If company policy requires it later, see ADR 0028 for how each is added |

The audit log (**Audit log**, Admins) records every change, sign-in and export.

## 7. Data flows and retention (NFR-05)

| Data | Where it goes | Kept |
|---|---|---|
| Users, organizations, contacts, leads, opportunities, activities | The CRM database only | Until archived or anonymized; archived records stay for history |
| Exports (XLSX/CSV) and the GDPR personal-data export | The requesting user's browser; each export is audited | Not kept by the CRM |
| Imports | Rows parsed into the database for preview and rollback; files are not kept | Batches until discarded |
| Integration data | Read and written by Conclusion, ERP and Billing through the API with their scopes; webhook events to their HTTPS endpoints | Webhook events and delivery history 30 days |
| Assistant questions and the CRM data the assistant looks up | Sent to the model an Admin chose (outside the company) when `AI_ENABLED=true`: OpenRouter and Cerebras by default; OpenRouter and NVIDIA (free), or Google, if chosen (section 8.1). Answers stored in the user's chat history | Chats until the user deletes them; token usage per request kept for the budget |
| Logs | Container logs (JSON): no passwords, tokens, keys or chat text; no query strings | As configured in Docker (rotate them) |
| Backups | `CRM_BACKUP_DIR`, copied nightly to another machine | 10 days on the server; 30 days on the other machine |

**GDPR requests for a contact** (FR-ADM-04): an Admin opens the contact and uses **Personal data (GDPR)**: *Export personal data* (JSON) and *Anonymize contact*. Anonymization replaces the person's name and clears email, phone, job title, language and notes, also on linked leads; opportunities and activities stay. Two exceptions are documented here (ADR 0027):
- **the audit log is kept unchanged** for accountability, so older entries can still hold the old values;
- **free text** (activity notes, assistant chats) is not rewritten. The export lists where the person is mentioned so an Admin can edit or delete those by hand.

## 8. Switching on the AI assistant

The owner approved the data flow to OpenRouter and Cerebras on 2026-11-18 (ADR 0028). In the OpenRouter account settings, turn off prompt logging and training on your data, and file the data-processing agreement. Then set `AI_ENABLED=true` and `OPENROUTER_API_KEY` in `.env`, allow outbound HTTPS to `openrouter.ai`, run `docker compose up -d`, and run the live evaluation (`docs/assistant-eval.md`; it passed 20/20 on 2026-11-18).

### 8.1 Choosing the AI model (FR-AI-10, ADR 0031)

An Admin chooses the model for all users in **Settings → AI assistant**. The choice applies to everyone's next question without a restart, is recorded in the audit log (`settings.updated`), and is shown to users under the question box.

| Option | Needs | Data protection |
|---|---|---|
| gpt-oss-120b (OpenRouter, Cerebras), default | `OPENROUTER_API_KEY`; HTTPS to `openrouter.ai` | The approved flow (ADR 0028): turn off prompt logging and training in the OpenRouter account |
| NVIDIA Nemotron 3 Ultra (OpenRouter, free) | `OPENROUTER_API_KEY` | **The provider may keep or use prompts.** Free endpoints log prompts by the provider's terms. OpenRouter caps free models (about 20 requests a minute, and a daily cap that depends on the credit bought); answers are slower (median 12 s in the evaluation) |
| Gemini 3.5 Flash (Google) | `GEMINI_API_KEY`; HTTPS to `generativelanguage.googleapis.com` | **The provider may keep or use prompts** on Google AI Studio's free tier; a paid (billed) project keeps them out of training. **The free tier allows only 20 requests a day per project** (2026-11-22). An answer takes 2–4 requests, so that is about 5–10 answers a day for everyone: switch on billing for the Google project before choosing Gemini for daily use |

Options whose key is not set are shown greyed out and cannot be chosen. When a provider's quota or rate limit is reached, the chat shows "The assistant is not available right now" until the quota resets; choose another model in the meantime. Prompts contain customer data (names, deal values, notes), so **before choosing one of the options marked "may keep prompts" with real data**, check the provider's current terms and get the DPO's approval. To add a key: put it in `.env`, then `docker compose up -d backend` (or `scripts/start-*.sh`). Each option has a recorded live evaluation in `docs/assistant-eval.md`; run it again after a model or prompt change (`--model <id>`).

## 9. Staging stack (second stack on the same host)

There is no staging server (owner decision); a second stack with separate data, keys and ports serves the integrating teams and acceptance tests:

```bash
scripts/staging.sh init                                   # .env.staging: own secrets, ports 8080/8443, ENV=test
# edit .env.staging: CRM_SITE_ADDRESS, CRM_PUBLIC_URL, CRM_TLS, WEBHOOK_ALLOWED_HOSTS
scripts/staging.sh up
scripts/staging.sh seed staging.admin@company.bg "Staging Admin"   # Admin, fictional data, the three clients
scripts/staging.sh cli reset-mfa --email …                # any CLI command
scripts/staging.sh down                                   # stop, keep data
scripts/staging.sh destroy                                # delete staging data
```

Staging keys start with `crm_test_`, so they cannot be mistaken for production keys. Staging must never hold real customer data. See `docs/integration-readiness.md`.

## 10. Monitoring and troubleshooting

| Check | How |
|---|---|
| Is it up? | `GET /api/health/live` (process) and `/api/health/ready` (database reachable); the footer of the app shows the service status |
| Logs | `docker compose logs --since 1h backend worker proxy` (JSON lines with `request_id`; every API response carries it in the `X-Request-ID` header, and audit entries record it) |
| Webhooks failing | Admins see a banner and a badge; **Integrations → Delivery log** shows each attempt |
| Disk | Backups and the database volume; `docker system df` |
| The app shows old behaviour after an upgrade | Restart `proxy` (section 4, step 5) and reload the browser |
| Sign-in page says "too many attempts" | Per-IP limit (`RATE_LIMIT_LOGIN_PER_MINUTE`); wait a minute |
