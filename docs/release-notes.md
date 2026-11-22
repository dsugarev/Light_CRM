# Release notes

## v1.1.0: Assistant actions with confirmation, and a choice of AI model (proposed; Phases 9 and 10, R1.1)

### For users
- **The assistant can do things for you.** Ask it to create a task, log a call, move or close a deal, create a lead, organization or contact, reassign a record, and more.
  - It shows a **card** with exactly what will happen; nothing changes until you press **Confirm**.
  - It works with your permissions, and confirmed changes are audited as yours "via assistant".
  - Admins can also manage users, settings, lists and stages this way.
- **Kept on the screens:** password links, API keys, GDPR tools and imports.
- **Better answers:** the assistant finds contacts, a colleague's records, win/loss and conversion figures and an organization's full history (PR #28). An answer built on a tool call the model only imagined is never shown.
- **The model in use is shown** under the question box (Phase 10).
- **The assistant answers more questions** (ADR 0032): the team's and a colleague's tasks (open, overdue, due or logged in a period), the pipeline stages and the lists. Admins can also ask about users (how many, roles, locked or deactivated accounts) and the current settings and AI model.

### For administrators
- **Choose the AI model for everyone** in **Settings → AI assistant** (Phase 10, FR-AI-10, ADR 0031):
  - NVIDIA Nemotron 3 Ultra, free, through OpenRouter: **the new default** (migration `0014` switches installations still on gpt-oss-120b);
  - gpt-oss-120b through OpenRouter and Cerebras (the default until now);
  - Gemini 3.5 Flash through Google, with the new `GEMINI_API_KEY` in `.env`.

  A model without its key is greyed out. The free and Gemini options are marked "the provider may keep or use prompts": check with the DPO before using them with real data (operations guide 8.1).
- **Live evaluation** (28 questions, `docs/assistant-eval.md` run 6): Gemini 3.5 Flash 28/28, Nemotron 3 Ultra 28/28, gpt-oss-120b 27/28 (one case that passes on rerun). The free Nemotron model needs an OpenRouter account with at least 10 USD of credits bought, or OpenRouter allows only 50 free requests a day.
- Three additive migrations (`0012_assistant_actions`, `0013_ai_model_setting`, `0014_free_model_by_default`).
- The assistant uses about 12,000 tokens per answer; consider raising `AI_DAILY_TOKEN_BUDGET` (default 200,000, roughly 16 answers per user per day).

## v1.0.1: Release 1 completion (tagged 2026-11-22 on `main` 56cfa38; PRs #24, #25 and #26)

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
