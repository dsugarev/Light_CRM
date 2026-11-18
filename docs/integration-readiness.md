# Integration readiness: Conclusion, ERP, Billing

Release 1 is ready for the three integrating teams to build and test against. This kit is the plan for getting each of them from "not connected" to "running in production" (implementation plan, Phase 8). The technical reference for the teams is `docs/integration-guide.md` with the Postman collection.

**Status (2026-11-18):** the CRM side is ready. Each team's flow depends on the answers to requirements open questions 7 and 8; until then the three clients exist, inactive and read-only (API spec 19.9).

## 1. Environment

There is no staging server (owner decision); the teams use the **staging stack**, a second stack on the CRM host with fictional data and its own keys (operations guide, section 9):

```bash
scripts/staging.sh init        # then set CRM_SITE_ADDRESS, CRM_PUBLIC_URL, CRM_TLS, WEBHOOK_ALLOWED_HOSTS
scripts/staging.sh up
scripts/staging.sh seed staging.admin@company.bg "Staging Admin"
```

- Address for the teams: `https://<staging host>:8443/api/v1` (OpenAPI document and interactive docs at `/api/docs`, available because staging runs with `ENV=test`).
- Staging keys start with `crm_test_`; production keys with `crm_prod_`. A key works only on its own stack.
- Data is fictional (`seed-demo`: 10,000 organizations, 10,000 contacts, 20,000 leads, 5,000 opportunities). Teams must not load real customer data into staging.

## 2. Network rules (for the network team)

| Rule | Staging | Production |
|---|---|---|
| Team servers → CRM host, HTTPS | port 8443 | port 443 |
| CRM host (worker) → each team's webhook host, HTTPS | as listed in `.env.staging` `WEBHOOK_ALLOWED_HOSTS` | as listed in `.env` `WEBHOOK_ALLOWED_HOSTS` |

Each team gives: the addresses its calls come from (for the client's optional IP allowlist) and the host name of its webhook receiver (open question 7e). Webhook receivers must be HTTPS with a certificate the CRM host trusts; plain HTTP is accepted only outside production.

## 3. Handing over a key

1. An Admin opens **Integrations → client**, checks the scopes against the agreed profile, sets the technical contact, and activates the client.
2. **Create key** with a label (for example "staging 2026-11"). The full key is shown once.
3. Send it through the company's secret-sharing channel (not email or chat in clear text); the team stores it in its secret manager. Never paste keys into tickets.
4. If the team receives webhooks, the Admin creates the subscription and hands over its signing secret the same way.
5. Rotation: create the second key, the team switches, then revoke the first. Keys expire after 12 months.

## 4. Checklist per team

Each team works through these in staging; the Admin records the dates. The same list, with production keys, is the go-live check.

| # | Step | Conclusion | ERP | Billing |
|---|---|---|---|---|
| 1 | Open questions 7a–e answered: purpose, trigger, records and fields, identifier owned, webhooks or polling, contact and addresses | ☐ | ☐ | ☐ |
| 2 | Profile agreed: scopes (read; write only if 7b says so), default owner for records it creates, IP allowlist | ☐ | ☐ | ☐ |
| 3 | Network rules for staging in place (section 2) | ☐ | ☐ | ☐ |
| 4 | Client activated, key handed over (section 3); `GET /api/v1/me` returns the client's system and scopes | ☐ | ☐ | ☐ |
| 5 | Sync: a full first load with `updated_since` and cursors, then incremental runs; no record missed or repeated | ☐ | ☐ | ☐ |
| 6 | Writes (if agreed): creates with `Idempotency-Key`, updates with `version`, a `409` handled | ☐ | ☐ | ☐ |
| 7 | External IDs: the team's identifier written with `PUT .../external-references/{system}` and found again by filter | ☐ | ☐ | ☐ |
| 8 | Webhooks (if used): the receiver verifies signatures (sample code in the guide, or `deploy/examples/webhook_receiver.py`), deduplicates by event ID, answers 2xx within 10 seconds; a test event and a redelivery succeed | ☐ | ☐ | ☐ |
| 9 | Errors: `401` (expired or revoked key), `403 permission.scope_missing`, `429` with `Retry-After` handled | ☐ | ☐ | ☐ |
| 10 | End-to-end business flow run (for example, opportunity won → customer created in ERP → ERP number written back) and signed off by the team and the CRM owner | ☐ | ☐ | ☐ |
| 11 | Production: client profile, key, subscription and network rules created; first production sync watched | ☐ | ☐ | ☐ |

## 5. What the CRM side has verified

- Every route is closed to integration clients unless it declares a scope, and each scope is enforced (integration scope matrix, every route, in CI).
- The Phase 6 exit test runs the ERP flow end to end with an API key only: sync, signed `opportunity.closed_won` webhook, write-back of the ERP number, refusal of everything outside the scopes (`backend/tests/api/test_phase6_exit.py`).
- The integration guide's Python sample is executed by the tests; the Postman collection is checked against the routes.

## 6. Open

- Requirements open questions 7 (data flows per system) and 8 (OAuth 2.0 or mutual TLS policy instead of API keys).
- Webhook receiver host names and caller addresses from each team.
