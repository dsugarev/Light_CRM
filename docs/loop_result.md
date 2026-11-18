# CRM UI improvements — loop results

A loop applying CRM UI best practices to Light CRM after the UI polish (PR #22). Branch `ui-improvements`, stacked on `ui-polish`.

**Rules kept:**
- frontend changes only, with no new endpoints or dependencies;
- nothing from the owner-decision list (`docs/loops/ui-polish-backlog.md` section C: branding, dark mode, command palette, system status page, sign-in notice);
- tests with every change, the full quality gate, and documents kept current (`docs/Plan.md`, `docs/Test_strategy.md`).

## Iteration 1 — page titles and contact details as links (2026-11-18)

| Best practice | Before | After |
|---|---|---|
| Every page names itself in the browser tab (WCAG 2.4.2 *Page Titled*; several CRM tabs stay apart) | Every tab said "Light CRM" | "Leads · Light CRM", "Акме ЕООД · Light CRM", "Вход · Light CRM": the page header's title, in the user's language. Error and not-found pages too |
| One click to act on a record's details | Email was a link on contacts and leads; phone only on contacts; the organization website and the emails in an organization's contact list were plain text | Email (`mailto:`), phone (`tel:`, dialled without spaces or punctuation) and website links on contact, lead and organization pages and in the organization's contact list |
| External links are safe | — | Websites open in a new tab with `rel="noopener noreferrer"`. A missing scheme becomes `https://`. Anything that is not `http`/`https` (for example `javascript:`) stays plain text |

**Code:**
- `frontend/src/components/usePageTitle.ts`, used by `PageHeader`, `AuthCard` and `ErrorMessage`; `AppLayout` no longer overwrites the title.
- `frontend/src/components/ContactLinks.tsx` (`EmailLink`, `PhoneLink`, `WebsiteLink`) and `frontend/src/lib/url.ts` (`websiteHref`).
- Used in `features/leads/LeadPage.tsx`, `features/organizations/OrganizationPage.tsx` and `features/contacts/ContactPages.tsx`. Empty values still show "Not set".

**Tests:**
- `src/components/pageTitlesAndLinks.test.tsx`, 13 cases:
  - titles on a list, a record, sign-in in Bulgarian and the not-found page;
  - `tel:` digits, `mailto:`, the website link target and `rel`;
  - only http(s) addresses become links; `javascript:` stays text; empty values render nothing.
- `e2e/shell.spec.ts`: "the browser tab names the page" (Leads, then Audit log).

**Gate:**
- Frontend: lint, prettier, typecheck, Vitest 270/270, i18n 1200 keys.
- Playwright Chromium: 45/48 in a run that took 4.1 minutes under host load. The 3 failures were timeouts in the accessibility, assistant and identity specs, which this change does not touch; they passed alone (10/10).
- Visual 4/4 (no baseline changed); backend pytest 1305 passed.

## Iteration 2 — recently viewed records (2026-11-18)

| Best practice | Before | After |
|---|---|---|
| Get back to what you were working on in one click | Users had to search or browse lists again | A **Recently viewed** card on the home page: the last 8 organizations, contacts, leads and opportunities this user opened, newest first, with type and "x minutes ago", kept current across tabs |
| Shared-computer privacy | — | Kept per user in this browser only (`localStorage`, never sent to the server), cleared on sign-out |
| No dead links | — | A record that answers 404 (deleted) is dropped from the list when it is opened |

**Code:**
- `frontend/src/features/recent/`:
  - `recentRecords.ts`: the per-user store (max 8, deduplicated, `clearAllRecent`);
  - `useRecentRecords.ts`: `useSyncExternalStore` over the `storage` event and a same-tab event, plus `useTrackRecent`, called by the organization, contact, lead and opportunity pages once the record has loaded;
  - `RecentlyViewed.tsx`: the home page card.
- `AppLayout` clears the list on sign-out.
- New texts `home.recent.*` in en/bg.

**Tests:**
- `src/features/recent/recentlyViewed.test.tsx`, 7 cases:
  - nothing shown before a record is opened;
  - opened records are listed newest first without duplicates, with the right links and types;
  - only the latest 8 are kept;
  - each user's records stay apart;
  - a 404 record is forgotten;
  - sign-out clears the list;
  - Bulgarian type labels.
- The two 768 px home baselines were updated: the visual test opens records before that pass, so the (masked) card now appears there. The visual suite then passed twice in a row.

**Gate:**
- Frontend: lint, prettier, typecheck, Vitest 277/277, i18n 1205 keys.
- Playwright Chromium 48/48. Visual 4/4 (twice).
- Axe on the home page with the card, en/bg at 1440 and 768 px: no violations.
- Backend: pytest 1305 passed.
