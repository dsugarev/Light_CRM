# Release notes

## v1.0.0: Release 1 (to be tagged on the owner's acceptance)

The first release of Light CRM: lead and opportunity management for the Commercial team, an AI assistant, and an integration API for Conclusion, ERP and Billing. On-premises, one Docker Compose stack.

### What is in it
- **Accounts and access** (Phases 1, 8a): invitation links, password policy, lockout, session timeouts, four roles, optional two-factor sign-in (can be required for Admins), audit log of every change, sign-in and export.
- **Organizations and contacts** (Phase 2): duplicate warnings across scripts, the organization 360 view, search in Cyrillic and Latin.
- **Leads** (Phase 3): capture, BANT qualification, lifecycle, assignment, conversion.
- **Opportunities and activities** (Phase 4): configurable pipeline, Kanban board (drag or choose), closing with reasons, stale marking, notes, calls, meetings, emails, tasks and record timelines.
- **Reports, export and import** (Phase 5): dashboard, win/loss report, Excel/CSV export of every list, Excel/CSV import with preview and rollback.
- **Integration API** (Phase 6): one API for the web app and integrated systems, scoped API keys, sync mode, external IDs, idempotency, signed webhooks with retries and a delivery log, an integration guide and Postman collection.
- **AI assistant** (Phase 7): chat drawer with streamed answers from read-only tools, record context, drafts saved as notes on request, daily budgets. Off by default.
- **Hardening** (Phase 8): GDPR export and anonymization; OWASP ASVS Level 1 review; accessibility checks; backup restore drill; operations, user (English, Bulgarian) and integration-readiness guides.

### Owner answers to the open questions (2026-11-18, ADR 0028)
The assistant's data flow is approved; a documented import format with samples replaces tracker copies; the default stages stay (editable); SMTP is optional and adds security notices; backups stay 10 days on the server and are copied to another machine; everyone sees everything for now; the integrations get every integration scope for now; API keys stay, with OAuth 2.0 or mutual TLS possible later.

### Before go-live (owner)
- The integrating teams' addresses and detailed flows (open question 7).
- The ASVS open items (`docs/security/asvs-l1.md`) and the manual accessibility checks (`docs/accessibility.md`).
- The live assistant evaluation passed 20/20 on 2026-11-18 (`docs/assistant-eval.md`); rerun it before switching the assistant on in production.
- The user acceptance checklist (`docs/acceptance-checklist.md`), then tag `v1.0.0`.

### Upgrading from a pre-release build
Follow the operations guide, section 4. After this release's upgrade, restart `proxy` and `backup` (`docker compose restart proxy backup`): the Content-Security-Policy and the certificate mount changed.
