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

## Iteration 3 — empty lists that say what to do next (2026-11-22)

| Best practice | Before | After |
|---|---|---|
| Distinguish "no matches" from "no records" and offer the next step | Every empty list said "Nothing to show." | With a search or filter active: "No records match the search or filters." and **Clear filters**. With no filter: "There is nothing here yet." and the create action (**New organization**, **New contact**, **New lead**, **New opportunity**) for users who may create; viewers get no create button |
| Clearing keeps the user's view | — | **Clear filters** removes search, filters and "show archived" and keeps the sort |

**Code:**
- `frontend/src/components/ListEmptyState.tsx`, on the organizations, contacts, leads and opportunities lists.
- `useListParams` gained `filtered` and `clear()`.
- **Defect found and fixed:** `SearchInput` was uncontrolled and kept its old text after the URL was cleared. It now follows its `value` when that changes from outside, without disturbing text that is still waiting for the 300 ms pause.
- New texts `states.noMatches`, `states.clearFilters`, `states.noRecords` in en/bg.

**Tests:**
- `src/components/listEmptyState.test.tsx`, 4 cases:
  - the create action is offered, and not to a viewer;
  - **Clear filters** keeps the sort and empties the search box;
  - Bulgarian.
- Two existing tests now expect the specific texts instead of "Nothing to show.". They check the same behaviour.
- 16 visual baselines (the four lists, en/bg, 1440/768) were updated after reviewing the new empty state. The suite then passed twice in a row.
- Axe on the filtered empty state (Bulgarian): no violations.

**Also fixed (found by this iteration's gate):** `tests/api/test_operations.py::test_housekeeping_removes_expired_sessions` failed from 2026-11-20 on. The worker purges by the system clock, but the session meant to survive expired 3 days after the fixed test date. It is now measured from the real clock, and the test still asserts one session removed and one kept (separate commit).

**Environment note:** the machine was restarted during this iteration. This wiped the scratchpad, including the local test database on port 5433 and the E2E admins' password. The test database now runs as a throwaway `postgres:18.7-trixie` container set up with `deploy/postgres/init-roles.sh`. The two local E2E admins got a new password, hashed by the backend's own Argon2 code. No project file changed for this.

**Gate:**
- Frontend: lint, prettier, typecheck, Vitest 281/281, i18n 1208 keys.
- Playwright Chromium 48/48. Visual 4/4 (twice).
- Backend: ruff, mypy, import-linter 14/14, pytest 1305 passed.

## Summary of the loop

| # | Improvement | Value |
|---|---|---|
| 1 | Descriptive browser-tab titles; email, phone and website as safe links | Orientation with several tabs (WCAG 2.4.2); one click to email, call or open a site |
| 2 | Recently viewed records on the home page | Get back to work in progress; per user, private to the browser, cleared on sign-out |
| 3 | Empty lists with a next step (clear filters or create) | Fewer dead ends; the search box now resets correctly |

All three are frontend-only, with no API change and no new dependency. Owner-decision items (backlog section C) were not built.

## After the loop — rebased on PR #22's CI fixes (2026-11-22)

PR #22's CI found two end-to-end failures; they are fixed on `ui-polish`, see `docs/loops/ui-polish-progress.md`:
- the contacts list now fits at 768 px;
- sign-in now reports a lost session even when `/me` is the first request to fail.

`ui-improvements` was rebased onto that. One conflict, in the contacts email column, was resolved by keeping both the narrow-screen classes and the email link. The housekeeping test fix, already on `ui-polish`, was dropped here as a duplicate.

Gate on the rebased branch:
- Vitest 282/282, i18n 1208 keys;
- Playwright Chromium 47/48: one sign-in "Welcome" timeout in `opportunities.spec.ts`, which passed alone twice;
- visual 4/4;
- pytest 1305 passed.

---

# Loop 2 — colour, responsive layout and motion (started 2026-11-22)

Prompt: apply CRM UI best practices for the **colour scheme**, **responsive design** and **interface dynamics**, keep every document current, and record each improvement here. Three iterations, same branch (`ui-improvements`).

**Rules kept** (same as loop 1):
- frontend only, with no endpoint, API change or new dependency;
- no owner-decision item from `docs/loops/ui-polish-backlog.md` section C. In particular, the brand colour (C-01, the `--brand` token stays neutral) and dark mode (C-02, no theme switch) are **not** part of "improving the colour scheme";
- tests with every change and documents kept current.

**Plan:**

| Iteration | Theme | Scope |
|---|---|---|
| 1 | Colour | Semantic status colours (success, warning, info) as theme tokens with tested contrast; status badges use them consistently |
| 2 | Responsive | Lists, record pages and forms at tablet width and below (NFR-11: "usable down to tablet width") |
| 3 | Dynamics | Subtle transitions and loading feedback that respect `prefers-reduced-motion` |

## Loop 2, iteration 1 — semantic status colours (2026-11-22)

| Best practice | Before | After |
|---|---|---|
| Colour carries meaning, consistently, across the CRM | Statuses were grey (`secondary`), black (`default`), outlined or red. "Won" was black, "Qualified" black, "Active" grey. Green existed only as an icon/dot colour | Three status tokens next to `--destructive`: **success** (green), **warning** (amber), **info** (blue). Badge variants `success`, `warning`, `info` use the same light-tint pattern as `destructive` |
| One mapping per status, everywhere | Each page chose its own variant | Lead: *New* blue, *Contacted* neutral, *Qualified* green, *Converted* outlined, *Disqualified* red. Opportunity stage: open blue, *Won* green, *Lost* red; *Needs attention* (stale) amber. Imports: steps in progress blue, *Imported* green, *Rolled back* outlined. Webhook deliveries: *Delivered* green, *Retrying* amber, *Failed* red, *Waiting* outlined. *Active* users, clients, subscriptions and reference values green |
| Contrast is tested, not assumed (WCAG 1.4.3, NFR-10) | The success green (emerald 500) was 2.5:1 on white. That was acceptable for an icon next to text, too low for text | Green and amber 800 and blue 700: 7.1, 7.1 and 6.8:1 on white, and 6.1, 6.1 and 5.8:1 on the 10% badge tint. A unit test reads the tokens from `src/index.css` and fails below 4.5:1 |
| Never colour alone (WCAG 1.4.1) | — | Every coloured badge keeps its text label; colour only adds a faster scan |

**Code:**
- `frontend/src/index.css`: `--success` darkened; `--warning` and `--info` added, with dark-theme values for completeness (no theme switch is offered).
- `frontend/src/components/ui/badge.tsx`: variants `success`, `warning`, `info`.
- `LeadStatusBadge`, `StageBadge`/`StaleBadge`, the new `features/imports/ImportStatusBadge.tsx` (used by the imports list and the batch page), the delivery status badge, and the active badges on users, integration clients, webhook subscriptions and reference lists.
- The darker green also applies to the password checklist ticks, the API status dot and the *Won* column border on the board.

**Tests:**
- `src/app/statusColors.test.tsx`, 8 cases:
  - NFR-10: success, warning, info and destructive keep 4.5:1 on white and on their 10% tint (computed from the OKLCH tokens in `index.css`); the helper is checked against black on white = 21:1;
  - the lead, stage/stale and import status mappings.

**Gate:**
- Frontend: lint, prettier, typecheck, Vitest 291/291 (38 files), i18n 1208 keys.
- Backend: not touched in this iteration.
- **Not run: Playwright journeys and visual baselines.** The E2E admins' password is not recorded, and creating separate loop-only admin accounts was refused by the session's permission policy. The visual baselines that show status badges (lists, home, record pages) are expected to change. To run: set `E2E_ADMIN_EMAIL_EN/_BG` and `E2E_ADMIN_PASSWORD`, then `pnpm e2e` and `pnpm e2e:visual`, review the diffs, and update with `--update-snapshots` if correct.
- The production-like stack was rebuilt with these changes (https://localhost).

## Loop 2, iteration 2 — touch tablets and narrow screens (2026-11-22)

NFR-11 asks for layouts "usable down to tablet width". Tablets are touch devices, so this iteration covers touch target size as well as width.

| Best practice | Before | After |
|---|---|---|
| Touch targets big enough for a finger (WCAG 2.5.8 needs 24 px; 44 px is the usual touch guideline) | Buttons were 32 px (small 28 px), inputs and selects 32 px, icon buttons 24-36 px, on every device | On a **coarse pointer** (touch screen) buttons, inputs and selects are 44 px, small buttons 40 px and the smallest icon buttons 32 px. Mouse users keep the compact desktop sizes, so lists stay dense where a pointer is precise. Measured in Chromium: 32 px with a mouse, 44 px with touch emulation |
| No sideways page scroll on a narrow screen | The search box in every list's filter bar had a fixed 20 rem (320 px) minimum, wider than the content of a 360 px phone | It keeps 20 rem when there is room and takes the full width when there is not. Sign-in at 360 px: no horizontal overflow |
| Pagination fits | "Page 1 of 4 · 100 records" and the two buttons never wrapped | The summary and buttons wrap onto two lines when needed |
| Tell the user a table has more columns | A table wider than the screen scrolled sideways with nothing to show it | A soft shadow appears on the edge where more columns are hidden and disappears at either end (CSS only: covers that scroll with the content, `scroll-shadow-x` in `index.css`) |
| Record details readable on a phone | Label and value side by side always. A long Bulgarian label took the width and squeezed the value; long emails could overflow | From the `sm` breakpoint (640 px) unchanged. Below it, each label sits above its value, and long values wrap. Organization, contact, lead, opportunity, user, audit entry and profile pages |
| Controls in a row line up | — | The password field's "Show password" button matches the field's height on touch too (found in the touch screenshot) |

**Code:**
- `frontend/src/components/ui/button.tsx`, `ui/input.tsx`, `NativeSelect.tsx`, `PasswordInput.tsx`: `pointer-coarse:` sizes (Tailwind 4 variant for `@media (pointer: coarse)`).
- `frontend/src/components/FilterBar.tsx`: `[&>input]:min-w-[min(20rem,100%)]`.
- `frontend/src/components/Pagination.tsx`: `flex-wrap`.
- `frontend/src/components/ui/table.tsx` and the `scroll-shadow-x` utility in `src/index.css`.
- `frontend/src/components/detailList.ts` (`detailListClass`), used by the seven record and detail pages.

**Tests:**
- `src/components/responsive.test.tsx`, 15 cases:
  - every button size (8) and the text input grow on a coarse pointer;
  - the search box minimum never exceeds the screen; pagination wraps; the table container carries the scroll hint;
  - the detail list stacks below `sm`; no feature page hard-codes the old two-column list; the four main record pages use the shared one.
- jsdom has no layout or media queries, so the rendering was measured in Chromium (Playwright library, sign-in page, which needs no account): desktop 1440 px (mouse) button and input 32 px; tablet 768 px and phone 360 px with touch emulation 44 px; no horizontal overflow at any width. The production build was checked for the `pointer: coarse`, `scroll-shadow-x`, stacked-list and search-box rules.

**Gate:**
- Frontend: lint, prettier, typecheck, Vitest 306/306 (39 files), i18n 1208 keys; production build.
- **Not run: Playwright journeys, axe and visual baselines**, for the same reason as iteration 1 (no E2E admin credentials in this session). Desktop baselines use a mouse pointer and are not expected to change from the touch sizes. The 768 px baselines may change where a table now shows its scroll shadow.
- Stack rebuilt (https://localhost).

## Loop 2, iteration 3 — interface dynamics (2026-11-22)

| Best practice | Before | After |
|---|---|---|
| Show that something is happening (Nielsen: visibility of system status) | Lists keep the previous rows while the next page, sort or filter loads (`keepPreviousData`), with no sign of loading: on a slow connection a click seemed to do nothing | While the previous rows are shown, the table is marked `aria-busy`, the rows dim to 60% and a thin blue bar slides above them. All of it starts only after 200 ms, so fast answers do not flicker. Organizations, contacts, leads, opportunities, users, audit log, imports and My tasks |
| Navigation reads as navigation | Pages swapped instantly | The page fades in over 200 ms when the address changes. A change of search, filter, sort or page keeps the same page (no fade), so working in a list does not flash |
| Feedback on pointer interaction | Sidebar links changed background abruptly | Sidebar links fade their hover and active background (150 ms) and are taller on touch (as in iteration 2). Buttons, rows and badges already had transitions and a 1 px press |
| Respect "reduce motion" (WCAG 2.3.3, user preference) | No handling: dialogs, the drawer, skeleton pulses and toasts always moved | With "reduce motion" set in the operating system, every animation and transition finishes at once (states still change, nothing moves) and the busy bar becomes a still line |

**Code:**
- `frontend/src/components/DataTable.tsx`: `busy` prop (track, bar, `aria-busy`, dimmed body). The eight lists pass `busy={query.isPlaceholderData}`.
- `frontend/src/index.css`: `busy-track`/`busy-bar` utilities with their keyframes; the `prefers-reduced-motion: reduce` block.
- `frontend/src/app/AppLayout.tsx`: the page wrapper keyed by path with `animate-in fade-in-0` (tw-animate-css, already a dependency).
- `frontend/src/app/AppNav.tsx`: link transition and touch padding.
- Not changed: the webhook deliveries page polls and keeps its rows with its own table, not `DataTable`; it has no busy bar yet.

**Tests:**
- `src/components/motion.test.tsx`, 6 cases:
  - a busy table has `aria-busy`, a dimmed body and the (hidden from assistive technology) bar; an idle one has none of these;
  - the lead list, end to end with MSW: **Next** marks the table busy while page 2 is held back, the old rows stay, and the busy state ends with the new rows;
  - the page wrapper is replaced when the path changes and kept when only the search changes;
  - the reduced-motion block and the 200 ms delay are in the theme.
- Checked in Chromium against the rebuilt stack (sign-in page): a button's `transition-duration` is 0.15 s normally and effectively zero with `reducedMotion: 'reduce'`.

**Gate:**
- Frontend: lint, prettier, typecheck, Vitest 312/312 (40 files), i18n 1208 keys, production build. The page wrapper now remounts a page on a path change, and no existing test was affected.
- **Not run: Playwright journeys, axe and visual baselines** (no E2E admin credentials in this session; see iteration 1). Playwright's screenshots stop CSS animations, so the fade and the busy bar should not destabilise the baselines.
- Stack rebuilt (https://localhost).

## Summary of loop 2

| # | Theme | Improvement | Value |
|---|---|---|---|
| 1 | Colour | Semantic status colours (green, amber, blue, red) with tested contrast, one mapping per status | Statuses scan at a glance, consistently; text contrast ≥ 5.8:1 and never colour alone |
| 2 | Responsive | Touch-sized controls on touch screens, no forced width on narrow screens, wrapping pagination, table scroll hint, stacked record details | Usable on tablets (NFR-11) and readable on phones, with desktop density unchanged |
| 3 | Dynamics | Busy state for updating lists, page fade-in, softer navigation feedback, reduced-motion support | The interface shows that it is working; motion is short, purposeful and can be switched off |

All three are frontend-only, with no API change and no new dependency. Brand colour (C-01) and dark mode (C-02) remain owner decisions.

**Open before merging** (owner or a session with credentials):
1. Run `pnpm e2e` (journeys and axe) and `pnpm e2e:visual`. Expect baseline changes where status badges appear (iteration 1) and possibly where a 768 px table shows the scroll shadow (iteration 2). Review the diffs, then `pnpm e2e:visual --update-snapshots`.
2. ~~Commit~~ Done 2026-11-22, one commit per iteration (`feat(ui): semantic status colours …`, `feat(ui): touch-sized controls …`, `feat(ui): busy state for updating lists …`) and this documentation commit.
3. Optional follow-up: the webhook deliveries page has its own table and no busy bar.
