# Release notes

## v1.0.1: Release 1 completion (proposed; to be tagged on `main` once the Release 1 completion PR is merged; #24 and #25 are already in)

Interface improvements after v1.0.0, the remaining Release 1 items that could be done without other teams, and manuals for new users. No database migration. The API change is limited to the export endpoints, which integrations can't call. Upgrade as in the operations guide, section 4.

### For users
- **Look and feel:**
  - a warm colour scheme with a terracotta brand colour;
  - colour-coded statuses;
  - larger touch targets on tablets;
  - lists that stay readable on narrow screens;
  - subtle loading and page transitions, which respect "reduce motion".
- **Getting around faster:**
  - a clickable **sales path** on opportunities;
  - click anywhere on a list row to open the record;
  - dashboard figures that open the list behind them;
  - **recently viewed** records on the home page;
  - page titles in browser tabs;
  - empty lists that suggest the next step.
- **Password strength** bar when setting or changing a password.
- **Exports follow the role matrix** (requirements section 4):
  - Viewers can no longer export;
  - a Sales Rep's export contains only their own records, and the screen says so;
  - Sales Managers and Admins export everything, as before.
- **Accessibility:** tables that scroll sideways can be scrolled by keyboard. The organization page no longer scrolls sideways at 200% zoom.
- **User manuals** for each role, with screenshots and PDFs, in `docs/manual/`.

### Release 1 items still open (need people outside the team)
- **The integrating teams' addresses and detailed flows (open question 7).** After that, narrow the integration scopes.
- **IT:** the nightly copy of backups to another machine, and a restore drill on the production server (operations guide, section 5).
- **ASVS 8.3.3:** a privacy notice text from the DPO, to be linked from the sign-in page.
- **Accessibility:** a screen-reader walkthrough by a person (`docs/accessibility.md`, "Results"). Zoom and 1024 px checks are done.

## v1.0.0: Release 1 (tagged 2026-11-18 on `main` 026719d after the owner's acceptance)

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
- The user acceptance checklist (`docs/acceptance-checklist.md`): accepted by the owner on 2026-11-18; `v1.0.0` tagged.

### Upgrading from a pre-release build
Follow the operations guide, section 4. After this release's upgrade, restart `proxy` and `backup` (`docker compose restart proxy backup`): the Content-Security-Policy and the certificate mount changed.
