# ADR 0003: Server-side cookie sessions instead of JWT

Status: Accepted · Date: 2026-11-17 · Phase 0

## Context
Internal users sign in through the SPA served from the same origin as the API. Requirements: server-side sign-out, idle and absolute timeouts, invalidating all sessions on password change (FR-AUTH-04), no tokens in localStorage.

## Decision
Opaque random 256-bit session token in an `HttpOnly; Secure; SameSite=Strict; Path=/api` cookie; only its SHA-256 hash is stored in `user_session`. CSRF: SameSite plus a required `X-Requested-With` header on mutating requests plus `Origin` validation. Integrations do not use cookies (ADR 0008). Built in Phase 1.

## Consequences
- Revocation is immediate (delete the row); no token-expiry workarounds.
- One database lookup per request, negligible at this scale.
- The SPA client sends `X-Requested-With: XMLHttpRequest` on every request (already in `frontend/src/api/client.ts`).
