# ADR 0028: Owner answers to the requirements' open questions, and the options kept open

Status: Accepted · Date: 2026-11-18 · After Phase 8

## Context
Requirements section 8 listed eight open questions. The owner answered them on 2026-11-18. Some answers are configuration, some needed small changes, and three ask to keep an option open for later (record visibility, OAuth 2.0, mutual TLS). This ADR records each answer, what changed, and how the options can be added without rework.

## Decision
1. **LLM data flow: approved.** The assistant may send CRM content to OpenRouter and Cerebras. The code default stays `AI_ENABLED=false`, because the backend refuses to start with it on and no key, which is safer for a fresh install. A deployment switches it on with `AI_ENABLED=true` and `OPENROUTER_API_KEY` (operations guide 8). Recommended with it: OpenRouter's settings with prompt logging and training on our data turned off, and the data-processing agreement filed.
2. **Excel trackers: none shared.** A documented import format with fictional sample files (`docs/import-format.md`, `docs/import-samples/`) is the reference; a test imports the samples through the API.
3. **Pipeline stages: the defaults stay.** Admins change them in the application (**Stages**: add, rename, reorder, probability, deactivate or delete; FR-ADM-02). No change needed.
4. **SMTP: optional.** It is configuration (`SMTP_*`). With it, users also get a security notice after a password change or reset and after two-factor sign-in is turned on, off or reset (ASVS 2.2.3, 2.5.5). Without it, every flow works as before.
5. **Backups: 10 days on the server; copies on another machine.** `BACKUP_RETENTION_DAYS` defaults to 10. The 30-day retention of NFR-07 is met by the copies on the other machine (operations guide 5.1).
6. **Visibility: everyone sees everything (A1), with the option to change it later.** No setting is built now. Kept open because:
   - every read goes through the services, with the `Principal`;
   - lists use one list machinery (ADR 0017);
   - the policy lives in one module (ADR 0013).

   A later restriction (for example "Sales Reps see only their own and their team's records") is then:
   - a visibility rule in `core/policy`;
   - one filter applied in each module's list statement and `get`;
   - the same filter for search, reports, exports, the assistant's tools (they call the services) and webhook fan-out.

   The tables already carry `owner_id`.
7. **Integrations: every integration scope for now; addresses not yet known.** The three profiles of API spec 19.9 now hold every scope. Endpoints closed to integration clients stay closed whatever their scopes: administration, imports, exports, audit, GDPR, the assistant (hard rule; API spec 19.3). Clients that already exist keep their scopes until an Admin edits them. Writes need a default owner on the client. IP allowlists stay empty until the teams give their addresses.
8. **API keys stay, with OAuth 2.0 and mutual TLS kept possible.** Kept open as follows:
   - **Mutual TLS** is a proxy concern. A separate host name or port for integrations in the Caddyfile with `tls { client_auth { mode require_and_verify; trust_pool file /certs/clients-ca.pem } }`, and the API key still identifying the client (both are required). No application change.
   - **OAuth 2.0 client credentials:** a token endpoint (`POST /api/v1/oauth/token`) that exchanges a client ID and secret (or a key) for a short-lived bearer token resolving to the same integration client `Principal`. The scope checks, policy and endpoints do not change. It needs an API-spec addition and an ADR when required (API spec section 20).

## Consequences
- Requirements section 8 and the acceptance checklist record the answers.
- With every scope granted, least privilege for the integrations comes back when open question 7's detailed flows are known; narrowing a client's scopes is an Admin action, no deployment.
- NFR-07 now depends on the off-server copy; the operations guide gives an example and makes it an operator task.
