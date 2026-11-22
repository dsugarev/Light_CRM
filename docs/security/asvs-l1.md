# OWASP ASVS 4.0.3 Level 1: checklist (Phase 8a)

NFR-04 sets OWASP ASVS Level 1 as the security baseline. This is the review done in Phase 8a: every Level 1 requirement, its status, and the evidence (code, test or configuration). Chapters without Level 1 requirements (V1 architecture) are covered by the architecture document.

**Status:** ✅ met · ⚠️ partly met or accepted deviation (reason given) · ❌ open (owner decision needed) · — not applicable.

**Summary:** 118 rows reviewed (a few rows group related IDs):
- 107 met (2.2.3 and 2.5.5 since the owner's SMTP answer, with SMTP configured; 2.1.8 and 2.1.12 since 2026-11-22);
- 5 partly met or accepted deviations: 2.1.7, 3.4.4, 3.7.1, 8.3.1, 12.4.2;
- 1 open, low risk, listed at the end for a decision: 8.3.3 (privacy notice text from the DPO);
- 5 not applicable.

Found and fixed during this review:
- API responses had no anti-caching header (8.2.1);
- the toast library's stylesheet was blocked by the Content-Security-Policy, so toasts were unstyled (14.4.3);
- a race between two "create user" requests returned 500 instead of 409.

## V2 Authentication

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 2.1.1 | Passwords at least 12 characters | ✅ | `identity/passwords.py`; `test_auth.py` password policy tests |
| 2.1.2 | Passwords of 64+ characters allowed (max 128) | ✅ | Same; limit 128 |
| 2.1.3 | No truncation; consecutive spaces kept | ✅ | Argon2id over the full input; no trimming |
| 2.1.4 | Any printable Unicode, including emoji | ✅ | No character-class restriction |
| 2.1.5 | Users can change their password | ✅ | `POST /auth/password/change` |
| 2.1.6 | Change needs the current password | ✅ | `password.current_incorrect`; test |
| 2.1.7 | Checked against breached passwords | ⚠️ | Bundled common-password list, case-insensitive. A live breach-corpus lookup (e.g. Have I Been Pwned) would send data outside the on-premises network; offline corpus can be added on request |
| 2.1.8 | Password strength meter | ✅ | Strength bar (weak to strong) with the rule checklist on set, reset and change password (2026-11-22) |
| 2.1.9 | No composition rules | ✅ | Length and common-list only |
| 2.1.10 | No periodic rotation | ✅ | None |
| 2.1.11 | Paste and password managers allowed | ✅ | Standard inputs, `autocomplete` set |
| 2.1.12 | User can show the typed password | ✅ | Show/hide button on every password field (`PasswordInput`, UX-06) |
| 2.2.1 | Anti-automation against credential stuffing | ✅ | 10 sign-ins per minute per IP; lockout after 5 failures (passwords and two-factor codes); tests |
| 2.2.2 | No weak authenticators (SMS, email codes) | ✅ | TOTP only |
| 2.2.3 | Notify after changes to credentials | ✅ | When SMTP is configured (optional, owner decision): an email after a password change or reset and after two-factor changes (`identity/emails.py`; `test_security_notices.py`). Audit entries always |
| 2.3.1 | Initial passwords random, short-lived, one-time | ✅ | One-time set-password links (72 h); no initial passwords |
| 2.5.1 | No recovery secret sent in clear text | ✅ | One-time links in the URL fragment |
| 2.5.2 | No password hints or knowledge questions | ✅ | None |
| 2.5.3 | Current password never revealed | ✅ | Stored as Argon2id only |
| 2.5.4 | No shared or default accounts | ✅ | First Admin via `create-admin`; service users cannot sign in |
| 2.5.5 | Notify on authentication factor changes | ✅ | As 2.2.3 |
| 2.5.6 | Forgotten-password flow is secure | ✅ | `forgot` always 202; 2-hour one-time link; ends all sessions |
| 2.7.x | Out-of-band verifiers | — | Not used |
| 2.8.1 | Time-based OTPs have a defined lifetime | ✅ | 30-second steps, one step of tolerance, replay refused (`identity/mfa.py`; `test_mfa.py`) |
| 2.9.x | Cryptographic verifiers | — | Not used |

## V3 Session management

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 3.1.1 | No session tokens in URLs | ✅ | Cookie only; API keys in the `Authorization` header |
| 3.2.1 | New token on authentication | ✅ | New session per sign-in; pending-MFA token is separate and grants nothing else |
| 3.2.2 | At least 64 bits of entropy | ✅ | 256-bit random tokens (`identity/tokens.py`) |
| 3.2.3 | Tokens stored in secure cookies | ✅ | No tokens in localStorage (frontend rule) |
| 3.3.1 | Logout invalidates the session | ✅ | Server-side deletion; test |
| 3.3.2 | Re-authentication within 30 days | ✅ | Absolute timeout 7 days (configurable to 30); idle timeout 8 hours |
| 3.4.1 | `Secure` attribute | ✅ | `test_auth.py`; `e2e/security.spec.ts` through Caddy |
| 3.4.2 | `HttpOnly` attribute | ✅ | Same |
| 3.4.3 | `SameSite` attribute | ✅ | `Strict` |
| 3.4.4 | `__Host-` cookie prefix | ⚠️ | Not used: `__Host-` requires `Path=/`, and the cookie is limited to `Path=/api` so the static app never receives it. With `Secure`, `HttpOnly`, `SameSite=Strict` and a host-only cookie (no `Domain`), the remaining risk (a sibling subdomain setting the cookie) does not apply to a single on-premises host name |
| 3.4.5 | Path attribute as precise as possible | ✅ | `Path=/api`; pending-MFA cookie `Path=/api/v1/auth/login` |
| 3.7.1 | Re-authenticate before sensitive changes | ⚠️ | Password change and turning off two-factor sign-in require the password. Anonymization requires typing a confirmation word, not the password |

## V4 Access control

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 4.1.1 | Enforced server-side | ✅ | `core/policy.py`; route × role matrix and integration scope matrix for every route |
| 4.1.2 | Attributes cannot be manipulated by users | ✅ | Roles and ownership read from the database per request |
| 4.1.3 | Least privilege | ✅ | Assistant actions (R1.1, ADR 0030): the model only proposes; the user confirms; the service rechecks permissions on confirmation; write tools offered by role. Roles per requirements; integrations deny-by-default with scopes; exports follow the role matrix since 2026-11-22 (Viewers none, Sales Reps own records only) |
| 4.1.5 | Fails securely | ✅ | Unknown level or missing scope refuses (`test_policy.py`) |
| 4.2.1 | No insecure direct object references | ✅ | Ownership checks on changes (Owner+); own-only conversations return 404; visibility per assumption A1 (everyone sees all records, owner decision pending as question 6) |
| 4.2.2 | CSRF protection | ✅ | Custom header + Origin check, `SameSite=Strict`; `test_security_headers.py` |
| 4.3.1 | Administrative interfaces use MFA | ✅ | Two-factor sign-in, enforceable for Admins (`mfa_required_for_admins`) |
| 4.3.2 | No directory browsing or metadata exposure | ✅ | Caddy serves the built app only; API docs off in production |

## V5 Validation, sanitization and encoding

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 5.1.1 | HTTP parameter pollution | ✅ | Unknown query parameters refused (400) by the list machinery |
| 5.1.2 | Mass assignment | ✅ | Request schemas `extra="forbid"` |
| 5.1.3 | Input validated (allow lists, types) | ✅ | Pydantic schemas; Zod on forms |
| 5.1.4 | Structured data strongly typed | ✅ | Same; dates, money as decimals |
| 5.1.5 | Redirects only to allowed destinations | ✅ | `safeNext` keeps sign-in redirects in-app |
| 5.2.1 | Untrusted HTML sanitized | ✅ | No raw HTML is rendered anywhere (`dangerouslySetInnerHTML` banned) |
| 5.2.2 | Unstructured data sanitized | ✅ | Free text stored as text, rendered escaped |
| 5.2.3 | SMTP injection | ✅ | Emails built with the standard library from fixed templates |
| 5.2.4 | No `eval` or dynamic code | ✅ | CSP `script-src 'self'`, no `unsafe-eval` (E2E check). **Fixed in 8a:** Zod 4 probed `new Function` (blocked and reported by Firefox); now `jitless` (`src/lib/zodConfig.ts`) |
| 5.2.5 | Template injection | ✅ | No user-controlled templates |
| 5.2.6 | SSRF | ✅ | Webhooks: HTTPS, host allowlist, DNS check refusing internal addresses, pinned connection (ADR 0025) |
| 5.2.7 | User-supplied SVG | — | Not accepted |
| 5.2.8 | Scriptable or Markdown content | ✅ | Assistant Markdown without raw HTML, images dropped, only in-app links (`assistant.test.tsx`) |
| 5.3.1 | Output encoding per context | ✅ | React escaping; JSON responses |
| 5.3.3 | Reflected, stored and DOM XSS | ✅ | As above; CSP |
| 5.3.4 | Parameterized queries | ✅ | SQLAlchemy only; no string-built SQL (rule) |
| 5.3.5 | No injection in other interpreters | ✅ | Exports neutralize formula injection (`=`, `+`, `-`, `@`) |
| 5.3.6 | JSON injection | ✅ | Serialized by the framework |
| 5.3.7 | LDAP injection | — | No LDAP |
| 5.3.8 | OS command injection | ✅ | No shell calls from the application |
| 5.3.9 | Local/remote file inclusion | ✅ | No file paths from users |
| 5.3.10 | XPath/XML injection | ✅ | XLSX parsed by openpyxl (defused XML); no XPath |
| 5.5.1–5.5.4 | Safe deserialization | ✅ | JSON only; no pickle or YAML from users |

## V6 Stored cryptography

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 6.2.1 | Cryptographic modules fail securely | ✅ | Fernet authenticated encryption (`core/crypto.py`); unreadable secrets refuse delivery rather than send unsigned |

## V7 Error handling and logging

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 7.1.1 | No credentials or session tokens in logs | ✅ | Request logging without headers, bodies or query strings; password-token paths masked; `test_logging.py` |
| 7.1.2 | No other sensitive data in logs | ✅ | Chat content never logged (`test_assistant.py`); webhook receivers' bodies excerpted only |
| 7.4.1 | Generic error message with an ID | ✅ | RFC 9457 problems with `code` and `request_id`; `test_security_headers.py` |

## V8 Data protection

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 8.2.1 | Anti-caching headers on sensitive responses | ✅ | **Fixed in 8a:** every `/api` response gets `Cache-Control: no-store` unless the route sets its own (`core/middleware.py`; `test_security_headers.py`; E2E) |
| 8.2.2 | No sensitive data in browser storage | ✅ | Only the UI language in localStorage |
| 8.2.3 | Data cleared from the client after the session | ✅ | Query cache cleared on sign-out |
| 8.3.1 | Sensitive data in bodies or headers, not URLs | ⚠️ | Credentials, tokens and keys never in URLs. Search terms (`q`) and filters are query parameters by design; they are not logged (the request log holds the path only) |
| 8.3.2 | Users can remove or export their data | ✅ | Contacts (the data subjects): GDPR export and anonymization (FR-ADM-04). Users are employees managed by Admins |
| 8.3.3 | Clear language about data processing | ❌ | A privacy notice for staff and contacts is the owner's or DPO's to provide; the operations guide documents the data flows |
| 8.3.4 | Sensitive data identified and handled by policy | ✅ | Data flows and retention in the operations guide (Phase 8b); NFR-05 |

## V9 Communications

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 9.1.1 | TLS for all connections | ✅ | Caddy on 443, HTTP redirected; only the proxy publishes ports |
| 9.1.2 | Strong cipher suites | ✅ | Caddy defaults (TLS 1.2+, modern suites) |
| 9.1.3 | Old protocols disabled | ✅ | Same |

## V10 Malicious code

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 10.3.1 | Update over secure channels with integrity | ✅ | Pinned dependencies with lock files (hashes); images built from the repository |
| 10.3.2 | Integrity for external resources | ✅ | No CDN or third-party scripts; CSP `'self'` |
| 10.3.3 | Protection from subdomain takeover | — | Single on-premises host name |

## V11 Business logic

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 11.1.1 | Steps in sequential order | ✅ | Import state machine (`import.invalid_state`); lead and opportunity lifecycles |
| 11.1.2 | Business limits at realistic speed | ✅ | Rate limits: users 600/min, assistant 20/10 min, exports, imports, integration clients |
| 11.1.3 | Appropriate limits per action | ✅ | Same; daily assistant token budget |
| 11.1.4 | Anti-automation on high-value flows | ✅ | Sign-in and password endpoints per IP |
| 11.1.5 | Business limits validated | ✅ | Export row cap, import size, page sizes |

## V12 Files and resources

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 12.1.1 | Large files refused | ✅ | Import 10 MB (`import.too_large`); request bodies bounded |
| 12.3.1 | No user-supplied file paths | ✅ | Uploads read in memory; no paths |
| 12.3.2–12.3.5 | Path traversal, LFI, RFI | ✅ | No file system access from user input |
| 12.4.1 | Uploads stored outside the web root | ✅ | Parsed rows in PostgreSQL; files not kept |
| 12.4.2 | Uploads scanned for malware | ⚠️ | Uploads are parsed as XLSX/CSV and never stored or served, so there is no file to scan. Revisit if file storage is added (R2+) |
| 12.5.1 | Only allowed file types served | ✅ | Caddy serves the built app; downloads are generated |
| 12.5.2 | Uploaded files never executed | ✅ | Never served |
| 12.6.1 | SSRF allowlist for outbound requests | ✅ | Webhooks (5.2.6); LLM calls only to the configured provider |

## V13 API and web services

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 13.1.1 | Same encodings and parsers everywhere | ✅ | JSON UTF-8 throughout (NFR-15) |
| 13.1.3 | No sensitive data in API URLs | ✅ | Keys in headers; one-time tokens in the request body |
| 13.2.1 | Only intended HTTP methods | ✅ | 405 for others (`request.method_not_allowed`) |
| 13.2.2 | JSON schema validation | ✅ | Pydantic; OpenAPI 3.1 contract checked in CI |
| 13.2.3 | CSRF protection for cookie-based APIs | ✅ | As 4.2.2; bearer clients exempt by design |

## V14 Configuration

| ID | Requirement (short) | Status | Evidence |
|---|---|---|---|
| 14.2.1 | Components up to date, no known vulnerabilities | ✅ | `pip-audit` and `pnpm audit` in CI; ADR 0022 ignore (dev-only) |
| 14.2.2 | Unneeded features removed | ✅ | API docs off in production; `LLM_FAKE` refused in production |
| 14.2.3 | Subresource integrity for third-party assets | ✅ | No third-party assets |
| 14.3.2 | Debug modes off in production | ✅ | `ENV=production` defaults; no reload |
| 14.3.3 | No version banners in headers | ✅ | `Server` removed (E2E check); no `X-Powered-By` |
| 14.4.1 | Content-Type with charset | ✅ | `application/json` (UTF-8 by definition); HTML from Caddy with charset |
| 14.4.2 | Downloads with `Content-Disposition: attachment` | ✅ | Exports, templates, GDPR export |
| 14.4.3 | Content-Security-Policy | ✅ | **Fixed in 8a:** the toast library's injected stylesheet is allowed by hash instead of being blocked; no CSP violation on the main pages (E2E check) |
| 14.4.4 | `X-Content-Type-Options: nosniff` | ✅ | Caddy; E2E check |
| 14.4.5 | HSTS | ✅ | `max-age=31536000; includeSubDomains`; E2E check |
| 14.4.6 | Referrer-Policy | ✅ | `strict-origin-when-cross-origin` |
| 14.4.7 | Not framed by other sites | ✅ | CSP `frame-ancestors 'none'` |
| 14.5.1 | Only allowed methods | ✅ | As 13.2.1 |
| 14.5.2 | Origin header not trusted for authorization | ✅ | Origin used only as an additional CSRF check |
| 14.5.3 | CORS allow list | ✅ | No CORS headers: same-origin only |

## Open items for the owner

| ID | Item | Recommendation |
|---|---|---|
| 2.1.8, 2.1.12 | Strength meter, show-password toggle | Done: show/hide password on every password field (UX-06, UI polish, 2026-11-18); strength meter with the password checklist (2026-11-22, `PasswordChecklist`, `passwordPolicy.ts`, tests `passwordStrength.test.tsx`) |
| 2.2.3, 2.5.5 | Email notice after password or two-factor changes | Done: sent when SMTP is configured (owner answer to open question 4) |
| 8.3.3 | Privacy notice | DPO / owner to provide; link it from the sign-in page |

Accepted deviations (3.4.4, 3.7.1, 8.3.1, 2.1.7, 12.4.2) are explained above and recorded in ADR 0027.
