# ADR 0008: One API for the frontend and integrations, with scoped API keys

Status: Accepted · Date: 2026-11-17 · Phase 0

## Context
Conclusion, ERP and Billing need CRM data. A separate integration API would duplicate business rules and drift.

## Decision
Integrations call the same `/api/v1` endpoints and services as the SPA, authenticated with bearer API keys (`crm_<env>_<key_id>_<secret>`, SHA-256 hash stored, shown once). Code works with a `Principal` (user or integration client); one policy function combines role, ownership and scopes. Integration access is deny-by-default: only endpoints in API spec 19.3 with their scope declared on the route. The `Principal` and policy are built in Phase 1; clients and keys in Phase 6.

## Consequences
One set of business rules and tests; the authorization matrix covers roles and scopes together. OAuth 2.0 client credentials can be added later on the same client model.
