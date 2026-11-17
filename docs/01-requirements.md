# 01 — Product Requirements: Light B2B CRM (Release 1)

Status: Draft v0.1 for owner review · Date: 2026-11-16 · Owner: Dido (Commercial)

## 1. Purpose and background

The Commercial team tracks B2B leads and opportunities in Excel files that are maintained by hand. There is no shared pipeline view, no history of who changed what, and forecasting is manual.

This product is a **light CRM** for B2B pre-sales. Release 1 covers **Lead and Opportunity Management** only. Later releases add Solution Management and Feasibility, Quote/Proposal/Contract Management, and Sales Enablement, by **extending** the same codebase and database, never by rewriting them.

The domain language follows TM Forum Open Digital Architecture (ODA), Market/Sales domain and Core Commerce / Party Management. This is alignment in naming and boundaries, not a conformance claim.

| Release | Capability | ODA / Open API reference |
|---|---|---|
| R1 (this spec) | Lead and Opportunity Management, Party basics, AI assistant, integration API for Conclusion, ERP and Billing | TMFC036, TMF699 Sales Management, TMF632 Party Management |
| R2 (future) | Product catalog, Product Offering Qualification, solution configuration, site surveys | TMF620, TMF679 |
| R3 (future) | Quote, proposal, agreement and contract management | TMF648, TMF651 |
| R4 (future) | Sales enablement, channel and partner management, advanced reporting | — |

## 2. Goals and success measures

- G1. All active leads and opportunities live in the application; the Excel trackers are retired within one month of go-live.
- G2. A sales manager can see the full pipeline and a weighted forecast in under 10 seconds, with no manual consolidation.
- G3. Every change to a lead or opportunity is attributable to a user and a time.
- G4. Adding R2–R4 capabilities requires only additive database migrations and new modules.
- G5. Conclusion, ERP and Billing can read CRM data and react to won deals through a documented, secured API, without manual re-keying of customer data.

## 3. Scope

### In scope for R1

Authentication and user management; organizations and contacts; leads with qualification; opportunities with a configurable pipeline; activities and notes; dashboard and basic reporting; Excel/CSV import and export; an AI assistant chat; English and Bulgarian UI; audit trail; an integration API for Conclusion, ERP and Billing (integration clients, scoped API keys, external references, incremental sync and webhooks).

### Out of scope for R1

Product catalog, quoting, contracts, product offering qualification, site surveys, partner portals, marketing campaign management, email/calendar sync, mobile apps, multi-currency, SSO (designed for, not delivered), AI actions that modify data. For integrations: building connectors or changes inside Conclusion, ERP or Billing (those teams consume the CRM API), the CRM calling those systems' APIs, automatic two-way master-data synchronization and conflict resolution, OAuth 2.0 client credentials, and a message broker.

## 4. Users and roles

Roughly 20 internal users, all in the Commercial team, on the company network.

| Role | Description | Key permissions |
|---|---|---|
| Admin | Application administrator | Everything, plus user management, pipeline configuration, audit log, import, GDPR tools |
| Sales Manager | Team lead | Read and edit all records, reassign owners, see team dashboards, import and export |
| Sales Rep | Account manager / seller | Read all records; create records; edit and close records they own; export own data |
| Viewer | Read-only stakeholder | Read all records and dashboards; no changes |
| Integration client | A connected application (Conclusion, ERP, Billing), not a person | Only what its granted scopes allow through the API; never user administration, settings, imports, exports, audit or the AI assistant; cannot sign in to the UI or own records |

Assumption A1: with 20 users in one team, **all users can read all commercial records**. Restriction is on editing, not on visibility.

## 5. Functional requirements

Each requirement has an ID. Acceptance criteria (AC) are written to be directly testable. Priority: **M** = must have for R1, **S** = should have, **C** = could have.

### 5.1 Authentication and access (AUTH)

**FR-AUTH-01 (M) Sign in with email and password.**
- AC1: A user with valid credentials reaches the dashboard; the session is held in a secure, HttpOnly cookie.
- AC2: Invalid credentials return a generic error that does not reveal whether the email exists.
- AC3: After 5 consecutive failed attempts the account is locked for 15 minutes and the event is audited.

**FR-AUTH-02 (M) No self-registration.** Only an Admin creates users. A new user receives a one-time, expiring link (shown to the Admin, and emailed if SMTP is configured) to set a password.

**FR-AUTH-03 (M) Password policy.** Minimum 12 characters, checked against a list of common passwords; stored only as an Argon2id hash.

**FR-AUTH-04 (M) Session management.** Idle timeout 8 hours, absolute timeout 7 days, both configurable. Sign-out invalidates the session on the server. Changing or resetting a password invalidates all the user's other sessions.

**FR-AUTH-05 (M) Role-based access control.** Every API endpoint enforces the role matrix in section 4 on the server. The UI hides actions the user cannot perform, but the server is the authority.
- AC1: A Sales Rep editing an opportunity owned by another rep receives HTTP 403.
- AC2: A Viewer calling any mutating endpoint receives HTTP 403.

**FR-AUTH-06 (M) SSO-ready.** The auth layer is built behind a provider interface, and the user record carries `auth_provider` and `external_subject`, so OpenID Connect (Microsoft Entra ID) can be added later without changing other modules. No SSO is delivered in R1.

**FR-AUTH-07 (S) Optional TOTP multi-factor authentication** per user, enforceable for Admins.

### 5.2 Organizations and contacts (PARTY)

**FR-PARTY-01 (M) Manage organizations.** Create, view, edit, archive. Fields: name (required), company registration number (EIK/UIC), VAT number, industry, size band, website, address, city, country, owner, notes.
- AC1: Creating an organization whose registration number or normalized name matches an existing one shows a duplicate warning with a link to the existing record before saving.

**FR-PARTY-02 (M) Manage contacts.** Create, view, edit, archive. Fields: first name, last name, job title, email, phone, preferred language, organization (optional link), notes.

**FR-PARTY-03 (M) Organization 360 view.** One page shows the organization with its contacts, leads, opportunities and activity timeline.

**FR-PARTY-04 (M) Search and filter.** Free-text search over name, registration number and email; filter by owner, industry, city.

### 5.3 Leads (LEAD)

**FR-LEAD-01 (M) Capture a lead.** Fields: title, company name, contact name, email, phone, source (configurable list: campaign, inbound inquiry, referral, event, cold outreach, partner, other), description, estimated value, owner. Company name alone is enough to save; a lead does not need an existing organization.

**FR-LEAD-02 (M) Lead lifecycle.** Status values: New → Contacted → Qualified → Converted, or Disqualified from any open status.
- AC1: Disqualifying requires a reason from a configurable list.
- AC2: A Converted or Disqualified lead is read-only, except that an Admin or Sales Manager may reopen a Disqualified lead.

**FR-LEAD-03 (M) Qualification (BANT).** Each lead records Budget, Authority, Need and Timeline, each as a status (unknown / no / partial / yes) plus a free-text note, and a target-profile fit flag.
- AC1: A lead can be set to Qualified only when all four BANT items are other than "unknown".
- AC2: The lead list shows a qualification score derived from the four items.

**FR-LEAD-04 (M) Convert a lead.** One action creates, in a single transaction, an opportunity plus an organization and contact (or links to existing ones chosen by the user after a duplicate check).
- AC1: After conversion the lead is Converted and links to the created opportunity; the opportunity links back to its source lead.
- AC2: If any step fails, nothing is created.
- AC3: Activities on the lead remain visible from the opportunity timeline.

**FR-LEAD-05 (M) Lead list.** Sortable, paginated table with filters for status, owner, source, created date, and free-text search. Filters are kept in the URL so views can be shared.

**FR-LEAD-06 (M) Assign and reassign owner.** Reps can assign to themselves; Managers and Admins can assign to anyone. Reassignment is audited.

### 5.4 Opportunities and pipeline (OPP)

**FR-OPP-01 (M) Manage opportunities.** Fields: name, organization (required), primary contact, owner, stage, amount (EUR), expected close date, probability, description, next step, source lead, loss reason, competitor.

**FR-OPP-02 (M) Configurable pipeline stages.** An Admin can add, rename, reorder and deactivate stages, each with a default probability and a type (open / won / lost). Default stages: Prospecting 10%, Qualification 25%, Solution & Proposal 50%, Negotiation 75%, Closed Won 100%, Closed Lost 0%.
- AC1: A stage that is in use cannot be deleted, only deactivated.
- AC2: Stage changes on an opportunity are stored as history with user, time, from-stage and to-stage.

**FR-OPP-03 (M) Pipeline board.** Kanban view with one column per open stage; cards show name, organization, amount, close date and owner; drag and drop changes the stage. Column headers show count and total amount.
- AC1: Dropping a card into a "lost" stage opens a dialog that requires a loss reason before the change is saved.
- AC2: A user without edit rights on a card cannot drag it.
- AC3: The board is usable with 300 open opportunities without visible lag.

**FR-OPP-04 (M) Opportunity list view** with the same filtering, sorting and URL-state behavior as FR-LEAD-05, plus filters for stage, close-date range and amount range.

**FR-OPP-05 (M) Close an opportunity.** Closing as Won or Lost records the actual close date. Lost requires a loss reason. Closed opportunities are read-only except for reopening by a Sales Manager or Admin.

**FR-OPP-06 (S) Stale indicator.** Opportunities with no activity for a configurable number of days (default 14) or with an expected close date in the past are flagged in the board and list.

### 5.5 Activities and notes (ACT)

**FR-ACT-01 (M) Log activities** against a lead, opportunity, organization or contact. Types: note, call, meeting, email (logged manually), task. Fields: subject, body, date and time, owner.

**FR-ACT-02 (M) Tasks.** A task has a due date, an assignee and a done flag. "My tasks" shows open tasks for the signed-in user, overdue first.

**FR-ACT-03 (M) Timeline.** Each record shows a reverse-chronological timeline that merges activities with system events (created, owner changed, stage changed, converted).

### 5.6 Dashboard and reporting (REP)

**FR-REP-01 (M) Dashboard.** Shows: open pipeline value by stage; weighted forecast by expected close month for the next 6 months; lead conversion rate; win rate and win/loss count; my open tasks. Filters: owner (me / a user / all) and period.
- AC1: Weighted forecast equals the sum of amount × probability for open opportunities in each month, and matches a figure computed independently in a test.

**FR-REP-02 (M) Export.** Any list view can be exported to XLSX or CSV with the current filters applied. Exports are audited.

**FR-REP-03 (S) Win/loss report** by loss reason, owner and period.

### 5.7 Import from Excel (IMP)

**FR-IMP-01 (M) Import organizations, contacts, leads and opportunities from XLSX or CSV.** A downloadable template is provided for each type. Available to Admin and Sales Manager.
- AC1: The user uploads a file, maps columns to fields, and sees a validation preview listing each invalid row with its reason before anything is written.
- AC2: The import is all-or-nothing per file unless the user chooses "skip invalid rows".
- AC3: Duplicates are detected using the same rules as FR-PARTY-01 and can be skipped or updated.
- AC4: Every imported record is tagged with an import batch ID, and an Admin can roll a batch back.

### 5.8 AI assistant (AI)

**FR-AI-01 (M) Chat panel.** A chat drawer is available from every page. Responses stream token by token. Conversations are saved per user and can be reopened, renamed and deleted.

**FR-AI-02 (M) Questions over CRM data.** The assistant answers natural-language questions by calling read-only server tools, for example "Which of my opportunities close this month?", "Summarize the history with Acme", "What is the pipeline value by stage?".
- AC1: Tools run with the permissions of the signed-in user.
- AC2: Answers that cite records include links to them.
- AC3: When the data does not contain the answer, the assistant says so and does not invent records or figures.

**FR-AI-03 (M) Record context.** When the panel is opened on a lead, opportunity or organization page, that record is offered as context ("Ask about this opportunity").

**FR-AI-04 (M) Drafting help.** The assistant can draft follow-up emails, call summaries and next-step suggestions from a record's data. Drafts appear in chat with a copy button; a draft can be saved as a note on the record by an explicit user click.

**FR-AI-05 (M) Read-only in R1.** The assistant has no tool that creates, changes or deletes data. (Planned next: proposed actions shown as confirmation cards that the user approves.)

**FR-AI-06 (M) Language.** The assistant replies in the language of the user's message, English or Bulgarian.

**FR-AI-07 (M) Resilience.** If the LLM provider is unavailable or slow, the chat shows a clear error and the rest of the CRM is unaffected. An Admin setting (`AI_ENABLED`) switches the assistant off entirely.

**FR-AI-08 (M) Usage controls.** Per-user rate limit and daily token budget, both configurable; token usage is recorded per request for reporting.

### 5.9 Administration (ADM)

**FR-ADM-01 (M) User management.** Create, deactivate, change role, trigger password reset. Deactivating a user ends their sessions and keeps their records.

**FR-ADM-02 (M) Reference data.** Admin manages lead sources, disqualification reasons, loss reasons, industries and pipeline stages.

**FR-ADM-03 (M) Audit log.** Admin can browse and filter the audit log by user, entity, action and date. The log records sign-ins, failed sign-ins, every create/update/delete with before and after values, exports, imports and role changes. Audit entries cannot be edited or deleted through the application.

**FR-ADM-04 (M) GDPR tools.** For a contact, an Admin can export all personal data held (JSON) and anonymize the contact, which irreversibly replaces personal fields while keeping commercial history.

### 5.10 Integration with other applications (INT)

Conclusion, ERP and Billing consume the CRM through the same REST API as the web frontend. Detailed design: `05-api-specification.md` section 19.

**FR-INT-01 (M) Integration clients.** An Admin registers one integration client per application, initially Conclusion, ERP and Billing. Each client has a name, a system code, granted scopes, a default human owner for records it creates, an optional IP allowlist, a technical contact, a rate limit and an active flag. Each client is backed by a service user that cannot sign in to the UI.
- AC1: A deactivated client's requests are refused with 401 and its webhooks are paused.
- AC2: Records and audit entries created by a client show it as the actor (for example "ERP (integration)").

**FR-INT-02 (M) API keys.** Clients authenticate with bearer API keys.
- AC1: The full key is shown only once, at creation; only a hash is stored.
- AC2: Keys have an expiry; a client can hold two active keys for rotation; a revoked or expired key is refused on the next request.
- AC3: Keys never appear in logs, audit entries or later API responses.

**FR-INT-03 (M) Scoped access.** A client can call only the endpoints its scopes allow (`05-api-specification.md` 19.3).
- AC1: A call without the required scope returns 403 with code `permission.scope_missing`.
- AC2: User administration, settings, imports, exports, audit log, GDPR tools, the AI assistant and integration administration are refused to every client.
- AC3: Clients cannot archive, restore, reassign or convert records, or reopen closed ones.
- AC4: A record created by a client must have a human owner, from the request or the client's default.

**FR-INT-04 (M) External references.** Organizations, contacts, leads and opportunities can hold one identifier per external system (for example the ERP customer number or the Billing account ID).
- AC1: An external ID is unique per system and record type; linking it to a second record returns 409.
- AC2: A client can set or remove references only for its own system; an Admin can for any system.
- AC3: A record can be found by external ID, and lists can filter on "has / has no reference in system X".
- AC4: References are shown on the record page in the UI, with a link when a URL is stored.

**FR-INT-05 (M) Incremental sync.** List endpoints for organizations, contacts, leads, opportunities and activities support pulling only records changed since a timestamp, with cursor paging.
- AC1: Archived and anonymized records are included so consumers can mirror them.
- AC2: No record is skipped or returned twice when data changes while the client is paging.

**FR-INT-06 (M) Idempotent creation.** Create and action requests from clients accept an `Idempotency-Key`; a retried request with the same key and body returns the original result without creating a duplicate.

**FR-INT-07 (M) Webhooks.** An Admin can subscribe a client's HTTPS endpoint to event types (for example `opportunity.closed_won`).
- AC1: Events are recorded in the same transaction as the change: a change that is rolled back sends no event, and an event is not lost if the receiver is down.
- AC2: Each delivery is signed (HMAC-SHA256 with a per-subscription secret) and carries a unique event ID.
- AC3: Failed deliveries are retried with backoff for up to 72 hours, then marked failed; an Admin can see delivery history and redeliver.
- AC4: A client receives only events for record types its scopes allow it to read.
- AC5: Webhook URLs must be HTTPS and on an allowlisted host.

**FR-INT-08 (M) Monitoring and audit.** Every data change made by a client is audited. Admins see, per client, last use, request and error counts for the last 24 hours, and failing webhook deliveries, with a visible alert in the admin area when deliveries are failing.

**FR-INT-09 (M) Rate limiting** per client, configurable, returning 429 with `Retry-After`.

**FR-INT-10 (M) Integration documentation.** The OpenAPI document is available to clients and shows the scope each operation needs. An integration guide with examples, webhook verification samples and a request collection is delivered for the Conclusion, ERP and Billing teams.

**FR-INT-11 (M) API stability.** The `/api/v1` contract changes only additively. Breaking changes go to a new version, with the old one kept for at least 6 months and deprecation signalled in response headers and release notes.

**FR-INT-12 (S) Admin UI for integrations.** Screens to manage clients, keys, subscriptions and the delivery log, including "send test event" and "redeliver".

### 5.11 Localization (I18N)

**FR-I18N-01 (M)** The full UI is available in English and Bulgarian with a per-user language preference; the default follows the browser language.
**FR-I18N-02 (M)** No user-facing string is hard-coded; a CI check fails when a key is missing in either language.
**FR-I18N-03 (M)** Dates, numbers and currency are formatted per locale. Currency is EUR. Timestamps are stored in UTC and displayed in Europe/Sofia.
**FR-I18N-04 (M)** Search, sort and import handle Cyrillic text correctly.

## 6. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 Performance | With 10,000 organizations, 20,000 leads and 5,000 opportunities, list and search endpoints respond in under 500 ms at p95; pages are interactive within 2 seconds on the office network. |
| NFR-02 Capacity | 20 named users, up to 20 concurrent. No horizontal scaling required; the design must not prevent it. |
| NFR-03 Availability | Business-hours service. Planned downtime is acceptable outside 08:00–19:00 Sofia time. Recovery point objective 24 hours, recovery time objective 4 hours. |
| NFR-04 Security | Follow OWASP ASVS Level 1 as the baseline and address the OWASP Top 10. Details in the architecture document, section 7. |
| NFR-05 Privacy | GDPR: data minimization, audit of access to exports, erasure by anonymization, documented data flows including the LLM provider. |
| NFR-06 Deployment | On-premises, on a company server, as Docker containers started by one Docker Compose command. Reachable only on the company network or VPN, over HTTPS. |
| NFR-07 Backup | Nightly automated PostgreSQL backup with 30-day retention and a documented, tested restore procedure. |
| NFR-08 Observability | Structured JSON logs with request IDs, a health endpoint, and error logging that never contains passwords, session tokens or chat message bodies. |
| NFR-09 Maintainability | Modular monolith with enforced module boundaries; typed code on both sides; automated lint, type check and tests in CI; additive migrations only. |
| NFR-10 Accessibility | Keyboard-operable throughout, including a non-drag way to change stage; WCAG 2.1 AA for contrast and labels. |
| NFR-11 Browser support | Current Chrome, Edge and Firefox on desktop; layouts usable down to tablet width. |
| NFR-12 Extensibility | R2–R4 capabilities can be added as new modules with new tables and foreign keys to R1 tables, with no destructive change to R1 schema. |
| NFR-13 Integration performance | Sync-mode pages of 500 records respond in under 2 seconds at p95; a webhook event is first attempted within 30 seconds of the change. Integration traffic must not degrade NFR-01 for users (enforced by per-client rate limits). |
| NFR-14 Integration availability | The API follows NFR-03. Because integrations may run outside business hours, planned downtime is announced to the integrating teams in advance, and webhook events raised during an outage are delivered afterwards. |
| NFR-15 Interoperability | API documented as OpenAPI 3.1; JSON over HTTPS; UTF-8 throughout, including Cyrillic; timestamps ISO 8601 UTC; money as decimal strings. |

## 7. Assumptions

- A1. All users may read all commercial records (section 4).
- A2. Single currency, EUR.
- A3. One pipeline for all opportunities in R1; the schema allows several later.
- A4. The server has outbound HTTPS access to `openrouter.ai` for the AI assistant.
- A5. An internal DNS name and TLS certificate will be provided by IT.
- A6. Email delivery (SMTP) is optional; every flow works without it.
- A7. Conclusion, ERP and Billing run on the company network, can call the CRM over HTTPS, and can expose an HTTPS endpoint reachable from the CRM server to receive webhooks (or else rely on periodic sync only).
- A8. Data ownership: the CRM is the master for leads, opportunities and pre-sales contact data; ERP is the master for the customer number and financial customer data; Billing is the master for billing accounts. The CRM stores only their IDs, not copies of their data.
- A9. Until the data flows are confirmed, the three integrations start read-only, plus writing back their own IDs as external references (`05-api-specification.md` 19.9).

## 8. Open questions for the owner

1. **LLM data flow.** The application is on-premises, but the AI assistant sends CRM content, including contact names, to OpenRouter and Cerebras outside the company. Does this need sign-off from the DPO or security team, and is a data processing agreement in place? Until confirmed, the build keeps `AI_ENABLED` off by default.
2. Can sample copies of the current Excel trackers be shared, so the import templates and field lists match reality?
3. Are the default pipeline stages and probabilities in FR-OPP-02 right for the team?
4. Is an internal SMTP relay available for password-reset emails and task reminders?
5. Where should nightly backups be stored, and who owns restore?
6. Is A1 (everyone can see everything) acceptable, or do some accounts need restricted visibility?
7. Integration data flows, for each of Conclusion, ERP and Billing:
   a. What does the application do, and what is the business trigger (for example "deal won → create customer")? For Conclusion, what is its purpose with respect to the CRM?
   b. Which records and fields does it need to read, and does it need to create or change anything in the CRM (which would need write scopes)?
   c. Which identifier does it own that the CRM should store (customer number, billing account ID…), and on which record?
   d. Can it receive signed webhooks over HTTPS, or will it only poll?
   e. Who is its technical contact, and which network addresses will it call from?
8. Is there a company policy that requires OAuth 2.0 or mutual TLS for system-to-system APIs, instead of API keys?

## 9. Glossary

- **Lead** — an unqualified prospect or inquiry, not yet tied to a confirmed organization.
- **Opportunity** — a qualified potential deal with an organization, with a value, a stage and an expected close date.
- **Party** — TM Forum term for an organization or individual the business deals with.
- **BANT** — Budget, Authority, Need, Timeline.
- **Weighted forecast** — amount multiplied by stage probability, summed over open opportunities.
