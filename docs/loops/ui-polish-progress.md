# UI polish loop — progress log

Note: the backlog was written after Phase 1; the application is now at v1.0.0, so several items may already be partly or fully met. Each entry says what was found.

## UX-01 — 2026-11-18 13:40

- **What changed:** every remaining color literal and Tailwind palette color moved to theme tokens in `frontend/src/index.css`. New tokens (light and dark): `--brand` (with `TODO(owner): brand color`; `--primary` now points to it), `--destructive-foreground`, `--success`, `--overlay`, `--qr-surface` (QR codes need a white quiet zone in both themes). Radii and spacing already came from `--radius` and Tailwind's `--spacing`.
- **Replaced:** the API status dot (`bg-emerald-500`/`bg-red-500` → `bg-success`/`bg-destructive`), the won drop zone on the board (`border-success/60`), the MFA QR background (`bg-qr-surface`), the alert-dialog backdrop (`bg-overlay/10`), the failing-deliveries badge text (`text-destructive-foreground`), and the dashboard chart fills (hex fallbacks removed).
- **Files:** `frontend/src/index.css`, `src/app/AppLayout.tsx`, `src/components/ui/alert-dialog.tsx`, `src/features/system/ApiStatus.tsx`, `src/features/profile/MfaCard.tsx`, `src/features/opportunities/BoardPage.tsx`, `src/features/reports/Dashboard.tsx`.
- **Tests:** `src/app/designTokens.test.ts`, which scans every source file except tests and the generated schema and fails on any hex/rgb/hsl/oklch literal or Tailwind palette color (`UX-01 ...`). A file with a planted `#fff bg-red-500` was confirmed to fail it.
- **Looked at:** dashboard, board and profile in en/bg at 1440 and 768 px; no visual change apart from the slightly different red and green of the status dot. Axe (`e2e/accessibility.spec.ts`, Chromium): passed.
- **Gate:** frontend lint, prettier, typecheck, Vitest 147/147, i18n 1065 keys; backend ruff, format, mypy, import-linter 14/14, pytest 1303 passed (95.56%). No backend or API change, so the generated types are unchanged.
- **For later:** clipped Y-axis labels and the weak "Weighted" chart contrast on the dashboard were already there before this change; logged as C-07.

## UX-02 — 2026-11-18 14:20

- **What changed:** the header navigation became a left sidebar grouped into **Sales** and **Administration**. Only the routes the user's permissions allow are listed, and the active route is highlighted (`aria-current="page"`). The top bar holds the menu/collapse button, the app name, search, the assistant and an account menu (base-ui `Menu`: My profile, language as radio items, Sign out). At 1024 px and wider, **Hide/Show navigation** collapses the sidebar (`aria-expanded`, `aria-controls`), and the choice lasts for the browser session (`sessionStorage`, wrapped in try/catch). Below 1024 px a **Menu** button opens the same navigation as a drawer (base-ui `Dialog`: focus trapped, Escape closes it and returns focus, and it closes after navigating). Signed-out pages keep the visible language buttons.
- **Files:** `frontend/src/app/AppLayout.tsx`, new `src/app/AppNav.tsx`, `src/app/UserMenu.tsx`, `src/app/useSidebarCollapsed.ts`, `src/features/system/useChangeLocale.ts` (the profile-saving language logic, now shared by the switcher and the menu), `src/features/system/LanguageSwitcher.tsx`, `src/i18n/{en,bg}/common.json` (7 keys each), `src/test/setup.ts` (clears `sessionStorage` between tests).
- **Tests:** `src/app/appShell.test.tsx` (5 `UX-02 ...` cases: groups and active route, rep sees no admin group, collapse remembered, Bulgarian drawer closes after navigating, user menu). `e2e/shell.spec.ts` (collapse at 1440 px survives a reload; drawer and account menu at 768 px by keyboard, with axe on the open drawer and menu). Updated for the new controls, not weakened: `app.test.tsx` (language and sign-out through the account menu) and `e2e/privacy.spec.ts` (sign out through the account menu).
- **Looked at:** home, organizations and users in en/bg at 1440 and 768 px, plus the drawer and the account menu. Axe: `accessibility.spec.ts` and `shell.spec.ts` passed.
- **Gate:** lint, prettier, typecheck, Vitest 152/152, i18n 1072 keys; Playwright Chromium 41/41; backend ruff, mypy, import-linter 14/14, pytest 1303 passed. No backend or API change. Firefox Playwright cannot start on this machine (known); CI runs it.
- **For later:** at 768 px the users table is wider than the page (the Status column is cut until you scroll the table), which belongs to UX-08/UX-13. The header search placeholder is cut in Bulgarian at 768 px (UX-13).

## UX-03 — 2026-11-18 14:30

- **Found:** `PageHeader` already existed and 27 pages used it (title and actions). Home and the signed-out pages (sign in, two-factor step, set password, forgot password) wrote their own `<h1>`.
- **What changed:** `PageHeader` now takes `description` and `breadcrumbs` besides `title` and `actions`, and renders a `<header>`. The breadcrumbs are a `nav` labelled "Breadcrumbs"; the current page is taken from the title and marked `aria-current="page"`. A new `useSectionCrumbs()` hook gives the list-page crumbs with the same labels as the menu. Breadcrumbs were added to every record, create and edit page:
  - organizations, contacts, leads (including Convert), opportunities;
  - user detail and new user;
  - audit entry, import batch;
  - integration client, deliveries and delivery.

  Edit and Convert pages lead back through the record (for example Contacts / Maria Ivanova / Edit contact). Home uses `PageHeader`. A new `AuthCard` gives the signed-out pages one shared frame and header (title plus an optional description, used by the two-factor hint).
- **Files:** `frontend/src/components/PageHeader.tsx`, new `src/components/useSectionCrumbs.ts`, new `src/components/AuthCard.tsx`, `src/app/HomePage.tsx`, the three auth pages, and 16 feature pages. `src/i18n/{en,bg}/common.json` gained `breadcrumbs.label`.
- **Tests:** `src/components/PageHeader.test.tsx` (4 `UX-03 ...` cases):
  - a scan that fails if any `.tsx` other than `PageHeader`/`AuthCard` renders an `<h1>`;
  - breadcrumbs on a record page;
  - the Bulgarian edit-page trail;
  - list pages without breadcrumbs.

  In the E2E specs, clicks on menu links now go through a new `mainNav(page)` helper in `e2e/support.ts`, because breadcrumbs repeat some link names (Organizations, Leads, …). This is the same check with a narrower locator, not a weaker one.
- **Looked at:** sign-in, home, an opportunity and its edit page, in en/bg at 1440 and 768 px.
- **Gate:** lint, prettier, typecheck, Vitest 156/156, i18n 1073 keys; Playwright Chromium 41/41 (with `--workers=2`); backend ruff, mypy, import-linter 14/14, pytest 1303 passed. No backend or API change.
- **Environment note:** the first three Playwright runs failed at random (timeouts on "Welcome", the assistant stuck on "Thinking…"). The Mac was out of memory: swap nearly full, load average up to 171 from macOS storage services and Time Machine, and Docker Desktop crashed during the third run. After restarting Docker and waiting for the load to drop, the suite passed 41/41 in 1.0 min with 2 workers. If E2E runs look flaky on this machine, check `uptime` and swap first.
- **For later (UX-11):** pages that space their children with `gap-6` add it on top of the header's `mb-6`, so the space under the header is doubled (visible on the opportunity page). The header spacing should have one owner.

## UX-04 — 2026-11-18 14:50

- **Found:** pages already used a shared `Loading` (a line of "Loading…" text) and `ErrorState` (translated message only, no retry). Tables showed "Nothing to show." as plain text; three pages had their own empty rows. The route error boundary showed a message and a link home.
- **What changed:**
  - `Loading` now draws skeletons (new `components/ui/skeleton.tsx`) in three shapes: `table` (lists), `form` (editors), `page` (records and sections, the default). It is announced once through `role="status"` with an accessible name; there is no visible "Loading…" text.
  - Each of the 60 call sites now picks its variant.
  - New `EmptyState` (inline icon, message, optional action): `DataTable` uses it, and so do the users, audit-log and deliveries tables.
  - `ErrorState` shows the server's request ID ("Reference for support: …"). `ApiError` gained `requestId`, taken from the problem body or the `X-Request-ID` header. Every query error on a page passes `onRetry`, which refetches (27 places).
  - The user-detail and audit-entry pages now use `ErrorState` instead of a fixed not-found message.
  - The route error boundary (`RouteError`/`ErrorMessage`) adds **Try again**, which reloads the page through the new `lib/reload.ts`, and the request ID when the error came from the API.
- **Files:** `frontend/src/components/{Loading,EmptyState,ErrorState,DataTable}.tsx`, `components/ui/skeleton.tsx`, `src/api/client.ts`, `src/app/{RouteError,ErrorMessage}.tsx`, `src/lib/reload.ts`, `src/i18n/{en,bg}/common.json` (`states.retry`, `states.requestId`), and 34 feature files (variants, retry, empty rows).
- **Tests:** `src/components/states.test.tsx`, 7 cases:
  - a scan that fails if any file outside `components/` uses `states.loading`/`states.empty`;
  - each skeleton variant announced without visible text;
  - an empty leads list;
  - a failed leads list showing the request ID and recovering on **Try again**;
  - the route boundary in Bulgarian with retry and request ID.
- **Looked at:** the leads list empty, failing (forced 500 with a request ID) and loading (delayed response), in en/bg at 1440 and 768 px, with axe on each state: no violations. I made the skeletons a little stronger (`bg-foreground/10`) because `bg-muted` was barely visible on white.
- **Gate:** lint, prettier, typecheck, Vitest 163/163, i18n 1075 keys; Playwright Chromium 41/41 (2 workers, 1.3 min); backend ruff, mypy, import-linter 14/14, pytest 1303 passed. No backend or API change.
- **Environment note:** the host is still short of memory (swap 9–10 GB). Earlier runs in this iteration had timeouts in Vitest (3 different tests, each passing alone) and in Playwright (assistant, accessibility). The backend logged 7–12 s on simple requests (for example creating a conversation). Every one passed on rerun, and the final full runs above are clean.
- **For later (UX-13):** at 768 px the Bulgarian lead filters shrink to unreadable stubs ("Вс⌄"); the filter row needs to wrap.

## UX-05 — 2026-11-18 15:30 — blocked `[!]` (environment, not the change)

- **Built (kept on branch `wip/ux-05-feedback`, commit `5f727e4`, not merged into `ui-polish`):**
  - `src/lib/notify.ts` (`useNotify()`: `success`, `error` mapping the backend `code` to a translated message with a generic fallback, and `warning`). Every `toast.*` call in the app now goes through it.
  - Error toasts where actions failed silently: assistant rename, delete and stop; saving the language on the profile.
  - Signing out another session on the profile now asks in `ConfirmButton` and confirms with a toast. Deactivate user and revoke all sessions already asked.
  - ESLint rules banning `window.confirm`/`alert`/`prompt` and importing `toast` from `sonner` outside `notify.ts`; checked to fire on a planted file.
  - `useErrorText` now translates when called (found while testing a failed language switch).
  - Tests: `src/lib/notify.test.tsx` (5 `UX-05 ...` cases) and the session test now requires confirmation.
  - The audit of all 63 mutations found no `window.confirm`/`alert`; the rest already showed success or error feedback (toast, inline message or the result on screen).
- **Passed:** lint (with the new rules), prettier, typecheck, Vitest 168/168, i18n 1078 keys. Screenshots of the confirm dialog and the toast in en/bg at 1440 and 768 px; axe with the dialog open: no violations. I replaced the raw browser string in the dialog text with generic wording.
- **Blocked:** three full Playwright runs failed on different steps each time: 10, 6 and 3 failures. The failures were timeouts on "Welcome", assistant answers, import and board steps. The backend logged its own requests taking 3–42 s (a sign-in 41.9 s, `GET /api/v1/me` 9.2 s; normally about 0.2 s). Host swap grew from 9 to 12.6 GB and the load average reached 48. A backend pytest run also had 2 timing failures that passed on rerun; no backend code changed. The prompt does not allow committing an item that fails the gate, so the work was moved out of `ui-polish`.
- **Owner action:** free memory on the development Mac (close apps, restart Docker Desktop or the machine), then on `wip/ux-05-feedback` run the full gate. If it is green, merge it into `ui-polish` and mark UX-05 `[x]`. Earlier items passed 41/41 when the host was quiet.
- **For later:** at 768 px the profile's sessions table needs horizontal scrolling (the Browser column is cut).

## UX-06 — 2026-11-18 15:55 — blocked `[!]` (environment, not the change)

- **Repair first:** Docker Desktop was restarted. The committed `ui-polish` code (UX-01..04) then passed Playwright 41/41 (1 worker, 2.0 min), so the host could run the gate at the start of the iteration.
- **Built (kept on branch `wip/ux-06-sign-in`, not merged into `ui-polish`):**
  - New `components/PasswordInput.tsx`: a show/hide toggle with `aria-pressed`/`aria-controls`, and a Caps Lock warning tied to the field through `aria-describedby` and cleared on blur. UX-07 and FN-01 can reuse it.
  - New `components/Spinner.tsx`.
  - Sign-in button disabled, `aria-busy` and spinner while pending; the same on the two-factor step.
  - Lockout: the unlock time as before, plus "You can try again in N minutes", computed from `locked_until` when the error arrives.
  - `FormMessage` gained `focusOnError`, which moves focus to a server error. The first invalid field was already focused by react-hook-form.
  - `autocomplete` (`username`, `current-password`, `one-time-code`) and the language switch in the signed-out header were already in place and are now asserted.
  - Tests: `src/features/auth/signInPage.test.tsx`, 7 `UX-06 ...` cases (autocomplete and language switch, show/hide, caps lock warning, busy button, lockout minutes with focus, first-field focus, Bulgarian lockout).
- **Passed:** lint, prettier, typecheck, Vitest 170/170, i18n 1080 keys. Screenshots of a locked sign-in with the password shown, en/bg at 1440 and 768 px; axe: no violations.
- **Blocked:** two full Playwright runs on the final build each ended 38/41, with different timeouts each time (assistant, opportunities board, imports, integrations; none on the sign-in page). Runs took 4.5–5.2 min against 2.0 min for the baseline, and a trace file was written truncated. Backend requests again took 2–3.5 s. The specs that failed in the first run passed when rerun (4/4). With no clean full run after three attempts, the work was moved out of `ui-polish`.
- **Owner action:** the development Mac has 8 GB of RAM, and Docker (about 3.8 GB VM), Chromium and the dev tools push it into 9–13 GB of swap. Either run the gate on a machine with more memory (or CI) or close other applications. Then on `wip/ux-05-feedback` and `wip/ux-06-sign-in` run the full gate and merge each into `ui-polish` when green. UX-06 builds on UX-04 and is independent of UX-05; the two branches touch `FormMessage` and `ConfirmButton` differently, so merge one, then rebase the other.

## Loop status — 2026-11-18 16:00

- Done on `ui-polish`: UX-01, UX-02, UX-03, UX-04.
- Blocked by the host environment, work kept on branches: UX-05 (`wip/ux-05-feedback`), UX-06 (`wip/ux-06-sign-in`).
- Open: UX-07 to UX-14 and FN-01 to FN-08. The loop is not complete. The final summary will be written when no `[ ]` items remain.
- Section C additions so far: C-07 (dashboard chart polish).

## UX-05 — 2026-11-18 16:15 — unblocked, done

- The owner freed memory on the host (swap went from 9–13 GB to about 3 GB). `wip/ux-05-feedback` was rebased onto `ui-polish` and the full gate rerun with no code change:
  - lint, prettier, typecheck, Vitest 168/168, i18n 1078 keys;
  - Playwright Chromium 41/41 (default workers, 1.1 min);
  - backend ruff, mypy, import-linter 14/14, pytest 1303 passed (95.56%).
- Merged into `ui-polish` as `feat(ui): UX-05 …`; the `[!]` became `[x]`. What was built is in the blocked entry above.

## UX-06 — 2026-11-18 16:25 — unblocked, done

- `wip/ux-06-sign-in` was rebased onto `ui-polish` (now with UX-05) with no conflicts, and the full gate rerun:
  - lint, prettier, typecheck, Vitest 175/175, i18n 1083 keys;
  - Playwright Chromium 41/41 (default workers, 52 s);
  - backend ruff, mypy, import-linter 14/14, pytest 1303 passed.
- Merged as `feat(ui): UX-06 improve sign-in page`; the `[!]` became `[x]`. What was built is in the blocked entry above.

## UX-07 — 2026-11-18 16:45

- **What changed:**
  - New `components/PasswordChecklist.tsx`, a live list of the backend policy (`identity/passwords.py`): at least 12, at most 128 characters, not a common password, both entries match. Each item has a check mark and a screen-reader state ("done" / "not yet"). The common-password list stays on the server, so that rule says "checked when you save", and the server's `password.too_common` still shows on the field. It exports `PASSWORD_MIN_LENGTH`/`PASSWORD_MAX_LENGTH` for the zod schema; FN-01 will reuse it.
  - The set/reset page uses `PasswordInput` (show/hide, Caps Lock) for both fields and `useWatch` for the live values; the static rules hint was removed.
  - A missing, used or expired link now gets its own page ("This link can no longer be used"): what happened, what to do next, **Request a new link** (to forgot-password) and **Back to sign-in**, with no form. Other errors (such as rate limiting) still show as an alert.
- **Files:** `frontend/src/components/PasswordChecklist.tsx`, `src/features/auth/SetPasswordPage.tsx`, `src/i18n/{en,bg}/{common,auth}.json`.
- **Tests:** `src/features/auth/passwordRules.test.tsx`, 10 `UX-07 ...` cases:
  - each rule met and not met (min, max, match), and the common-password rule's wording;
  - the checklist updating while typing;
  - the expired-token page with its links;
  - the incomplete link in Bulgarian.

  `setPassword.test.tsx` now expects the invalid-link page instead of an alert.
- **Looked at:** the set page with a half-typed repeat, and the expired-link page, in en/bg at 1440 and 768 px; axe: no violations. I shortened the invalid-link text because it repeated the next-step advice.
- **Gate:** lint (no warnings), prettier, typecheck, Vitest 186/186, i18n 1093 keys; Playwright Chromium 41/41 (plus the 2 screenshot specs); backend ruff, mypy, import-linter 14/14, pytest 1303 passed.

## UX-08 — 2026-11-18 17:20

- **API (additive):** `GET /api/v1/users` gained an optional `sort`: `name`, `email`, `role`, `last_login_at`, each with `-` for descending. Users who never signed in come last either way; ties go by name. The default is still name, and any other value returns 422. I updated the API spec (section 5) first, then exported `docs/api/openapi.json` and regenerated `src/api/schema.d.ts`. Router → service → repository (`_user_order`); no other endpoint changed. The full list machinery was not used because it rejects unknown parameters with 400, which would tighten the endpoint.
- **Frontend:**
  - `DataTable` is documented for reuse: TSDoc with a usage example (URL state via `useListParams`, `Pagination`, sort keys must be API sort fields). It gained optional per-row action menus (`rowActions`, `rowLabel`) through the new `components/RowActions.tsx` (base-ui Menu; link or callback items; labelled "Actions for <name>").
  - New `components/RelativeTime.tsx` and `formatRelative` (Intl.RelativeTimeFormat, en/bg): "3 hours ago" with the exact Sofia time in `title` and for screen readers.
  - The users page now runs on `DataTable` + `useListParams`: debounced search, role and status filters, sort and page all in the URL. Name, email, role and last sign-in are sortable. Status badges show active, deactivated or locked; last sign-in is relative. The row menu has Open, plus Unlock for locked users (with a toast). Errors use `ErrorState` with retry. The email column is hidden below 1024 px so the table fits at 768 px.
- **Tests:**
  - Backend: `test_FR_ADM_01_UX_08_list_sorts_by_column` (each field, both directions, never-signed-in last, 422 on an unknown value).
  - Frontend: `src/features/admin/usersTable.test.tsx`, 11 `UX-08 ...` cases (sort to URL and API with `aria-sort`, a shared URL with q/role/status/sort, an unknown sort falls back, relative time with exact title, badges, row menu unlock and open, `formatRelative` en/bg).
- **Looked at:** the users list and the row menu in en/bg at 1440 and 768 px; axe: no violations.
- **Gate:** lint, prettier, typecheck, Vitest 197/197, i18n 1096 keys, API types regenerated from the new snapshot; Playwright Chromium 41/41 (+ screenshot specs). One full run had the assistant spec time out on a "not stable" Save note button while the load average hit 17; it passed 3/3 alone and in the next full run (logged as C-08). Backend ruff, mypy, import-linter 14/14, pytest 1304 passed (95.57%).

## UX-09 — 2026-11-18 17:55

- **What changed:**
  - New shared `components/ui/sheet.tsx` (base-ui Dialog as a side panel: focus trap, Escape and backdrop close it, focus returns). The navigation drawer from UX-02 now uses it too.
  - New `features/admin/UserSheets.tsx`:
    - `CreateUserSheet`. `/admin/users/new` now shows the users list with the sheet open (the page `UserNewPage` was removed; the URL and the "New user" link still work). After creation it shows the one-time link panel (copy button, expiry, emailed or not) and a bold "Copy the link now: it is not shown again once you close this panel", with **Open the user** and **Done**.
    - `EditUserSheet`, used from the list's row menu (**Edit**) and from the user page (**Edit** in the header, replacing the inline edit card).
  - AC (link not kept after the sheet closes): the create mutation uses `gcTime: 0` and is `reset()` on every way of closing, so neither the component, the mutation cache nor the query cache holds the link afterwards. The user page's reset-link mutation got `gcTime: 0` too.
- **Also fixed:** the intermittent assistant E2E failure (C-08) was a real bug. When an answer finished, the reload replaced the live message with the stored one at a different place in the tree, which remounted it and dropped an opened "save as note" form. Live and stored messages are now one keyed list. Regression test: `FR-AI-04 save as note right after an answer` (fails without the fix, passes with it). Separate commit.
- **Files:** `frontend/src/components/ui/sheet.tsx`, `src/features/admin/{UserSheets,UsersPage,UserDetailPage}.tsx`, `src/app/{AppLayout,router}.tsx`, `src/test/render.tsx` (returns the query client), i18n (`actions.close/done/edit`, `link.onlyOnce`), `e2e/identity.spec.ts` (fills the form inside the sheet and presses Done, as a person would), `e2e/accessibility.spec.ts` (on `/admin/users/new` the modal sheet hides `main`, so it waits for the main landmark or the dialog).
- **Tests:** `src/features/admin/userSheets.test.tsx`, 4 `UX-09 ...` cases:
  - create in the sheet, then the link shown once, then Done; the link is gone from the DOM, the mutation cache and the query cache, and reopening shows an empty form;
  - Escape also forgets the link;
  - edit from the row menu;
  - edit from the user page in Bulgarian.
- **Looked at:** the form sheet and the link sheet in en/bg at 1440 and 768 px; axe with the sheet open: no violations.
- **Gate:** lint, prettier, typecheck, Vitest 202/202, i18n 1100 keys; Playwright Chromium 41/41 + 2 screenshot specs (2 workers, 1.4 min); backend ruff, mypy, import-linter 14/14, pytest 1304 passed. Runs with the default 4 workers had many timeouts while Spotlight indexing or Microsoft Teams loaded the host (load 16–28; 81 backend requests over 2 s), so E2E now runs with 2 workers.

## UX-10 — 2026-11-18 18:25

- **What changed:**
  - **Filters:** the audit log page now has a **User** select (from `GET /users`, page size 100), a **Record type** select (the 15 entity types the backend audits, translated), the action as text with an example placeholder, from/to dates, and presets **Today**, **Last 7 days** and **Last 30 days** (Sofia calendar days, applied at once). Filters, the page and the open entry are in the URL. The list runs on `DataTable`, shows the translated record type, hides the IP column below 1024 px, and shows `ErrorState` with retry.
  - **Drawer:** clicking an entry's time opens it in the shared `Sheet` (`?entry=<id>`, so the link can be shared; Escape or Close removes the parameter). The new `AuditEntryDetails` (also used by the stand-alone entry page) shows who, when, the record, IP and request ID; **Changes** as an `AuditDiff` table; and the details as formatted JSON when there are any. "Open as a page" leads to `/admin/audit-log/<id>`.
  - `AuditDiff` shows one row per field with before and after side by side. Changed fields are highlighted, marked with a dot, and announced "(changed)" to screen readers; missing and null count as the same. Nested values are formatted JSON; values wrap anywhere (long text, ids, Cyrillic). It falls back to two formatted JSON blocks when either side is not a field map. Values are always text, never HTML.
  - **Translations:** 52 audit action names were added in en/bg (organization, contact, lead, opportunity, activity, import, integration client, API key, webhook, external ID, stage, assistant conversation), plus the entity-type names.
- **Files:** `frontend/src/features/admin/{AuditLogPage,AuditEntryPage,AuditEntryDetails,AuditDiff,auditLabels}.tsx|ts`, `src/i18n/{en,bg}/admin.json`.
- **Tests:** `src/features/admin/auditViewer.test.tsx`, 10 `UX-10 ...` cases:
  - filter by user and record type;
  - each preset's range in the URL and the API;
  - the drawer with changed and unchanged rows, a long Cyrillic value and the request ID, closed with Escape;
  - a shared `?entry=` link in Bulgarian;
  - diff: a created record, nested JSON, the JSON fallback, empty fields not flagged.

  `admin.test.tsx` now expects the value as diff text (it still asserts no HTML is rendered).
- **Looked at:** the list and the drawer in en/bg at 1440 and 768 px; axe on both: no violations. Fixed after looking: empty fields flagged as changed on creation, and the action hint pushing the date fields out of line.
- **Gate:** lint, prettier, typecheck, Vitest 212/212, i18n 1184 keys; Playwright Chromium 41/41 + 2 screenshot specs; backend ruff, mypy, import-linter 14/14, pytest 1304 passed.

## UX-11 — 2026-11-18 17:35

- **Found:** 26 of 28 forms already used `FormField` (label, translated inline error, hint, ids). The exceptions were the assistant's "save as note" form and the GDPR type-to-confirm field, which used hand-made `<label>`s. Checkbox and radio labels and the BANT grid's labelled inputs are a different pattern and stay as they are.
- **What changed:**
  - **Required marker:** `FormField` gained `required`. It adds a red `*` next to the label (outside the `<label>`, so the field's name does not change; hidden from screen readers; "(required)" as a tooltip) and sets `aria-required` on the control. Spacing is consistent (baseline-aligned, so required and optional labels in one row line up).
  - **Which fields are marked:** exactly those the schemas or the server require, in every form:
    - record forms (organization name; contact first and last name; lead title and company; opportunity name and organization);
    - user, sign-in, two-factor, set/forgot password, profile details and password;
    - settings, stages, list values, imports, integrations, webhooks, external IDs;
    - lead disqualify reason, close-lost reason, activity subject and due date.
  - **Unsaved changes:** new `components/UnsavedChangesGuard.tsx`. `useBlocker` shows **Leave without saving?** (Stay on this page / Leave without saving) on in-app navigation, and a `beforeunload` handler makes the browser ask on close or reload. It is used in the organization, contact, lead and opportunity forms, settings, both profile forms and the activity form. The condition is `isDirty && !isSubmitting && !isSubmitSuccessful`, so saving (which navigates) never asks.
- **Files:** `frontend/src/components/{FormField,UnsavedChangesGuard}.tsx`, 20 feature forms, `src/i18n/{en,bg}/common.json` (`form.*`).
- **Tests:** `src/components/formConventions.test.tsx`, 8 `UX-11 ...` cases:
  - required marking (aria-required and aria-invalid, translated error as the description, marker hidden), optional fields unmarked;
  - a scan that no feature imports the bare `Label`;
  - a record form marks only its required fields;
  - leaving a changed form: stay keeps the text; leave goes; an untouched form does not ask; `beforeunload` is cancelled.

  The existing create-organization test (submit, then save anyway) shows saving does not trigger the guard.
- **Looked at:** the new-lead form with markers and the leave dialog, en/bg at 1440 and 768 px; axe with the dialog open: no violations. Fixed after looking: required labels sat 3 px lower than the optional label beside them.
- **Gate:** lint, prettier, typecheck, Vitest 220/220, i18n 1190 keys; Playwright Chromium 41/41 + 2 screenshot specs. After the final CSS-only alignment fix, one full run had 3 timeouts (reports exports and a sign-in) while the Docker VM was at 100% CPU and the load average reached 78; those specs passed alone (4/4). Backend ruff, mypy, import-linter 14/14, pytest 1304 passed.

## UX-12 — 2026-11-18 18:05

- **Found:** the skip link, landmarks, labelled controls and an axe test on 23 main pages already existed (Phase 8). UX-02..11 kept them, with axe on each new state: drawer, menus, sheets, dialogs. Not yet covered: record, edit and detail routes and the signed-out password pages. Focus rings were a 50% light grey (about 1.5:1 on links).
- **What changed:**
  - **Axe on every route:** `e2e/accessibility.spec.ts` gained `UX-12 record, edit, detail and drawer pages`. It creates an organization, contact, lead, opportunity, integration client and user through the API, then checks:
    - the contact, lead and opportunity pages and all edit pages, plus lead conversion;
    - user detail and integration client;
    - an audit entry as a page and in its drawer;
    - an import batch and a webhook delivery (present from earlier journeys);
    - the not-found page.

    It also gained `UX-12 signed-out pages`: forgot password, set password with a valid link and with a used link. With the existing test and `shell.spec.ts`, every route in `router.tsx` is now checked. Any violation fails, which is stricter than "serious or critical".
  - **Focus contrast:** the light `--ring` token went from `oklch(0.708 0 0)` to `oklch(0.45 0 0)`, and the default outline uses it at full strength. New `UX-12 focus indicators have 3:1 contrast with the page` (keyboard.spec): focuses a sidebar link, a row action button and a search input by keyboard and measures the indicator's contrast in the browser (canvas to sRGB, WCAG formula). The old value computes to about 2.6:1 even at full strength, below 3.
  - **Test fix:** the keyboard board walkthrough now runs as a fresh sales rep. The E2E admin's board had grown past the 200-Tab limit across runs, partly because the new axe test creates a deal on each run.
- **Files:** `frontend/src/index.css`, `e2e/{accessibility,keyboard}.spec.ts`, `docs/accessibility.md`.
- **Gate:** lint, prettier, typecheck, Vitest 220/220, i18n 1190 keys; Playwright Chromium 44/44; backend ruff, mypy, import-linter 14/14, pytest 1304 passed.

## UX-13 — 2026-11-18 18:40

- **How it was checked:** a temporary sweep visited every route (23 main pages, then also record, edit and convert pages: 68 checks per language) in Bulgarian and English at 1440 and 768 px. It took screenshots and measured, in the browser:
  - sideways page scrolling;
  - text clipped by its box;
  - select boxes too narrow for their chosen option;
  - tables that need sideways scrolling.

  I reviewed screenshots of the busiest pages in both languages.
- **Found and fixed (all in components, no translation shortened):**
  - **Filter rows** on organizations, contacts, leads, opportunities and users squeezed their selects (Bulgarian "Всички статуси" got 56 of 144 px at 768). New `components/FilterBar.tsx`: a wrapping row; the search takes the free space but at least 20 rem, selects size to their option, checkbox labels do not break.
  - **Wide tables** at 768 px (leads, opportunities, integrations, deliveries, profile sessions): secondary columns are hidden below 1024 px (score, owner, created; probability, weighted, owner; keys, webhooks, last used; attempts; session start). The information stays on the record or detail page. Opportunity names and organizations wrap.
  - **Stages and reference lists:** the action cells had `display: flex` on the `<td>` (buttons drawn above the row) and could not wrap; they now use an inner wrapping container. The long "Вероятност по подразбиране (%)" header wraps, stage name inputs keep 8 rem, and reference names wrap.
  - **Header search:** the placeholder "Търсене на организации и контакти" was cut even at 1440 px. The box now shows the short "Търсене / Search"; the full text stays its accessible name and tooltip.
  - **Dashboard (C-07):** Y-axis amounts were clipped ("0000000"). New `formatMoneyCompact` (Intl compact currency: "340 млн. €", "€1.3bn") with a wider axis; the weighted series uses a dark grey instead of a 1.3:1 light grey, which also makes its legend text readable.
  - Dates and numbers were already locale-formatted everywhere ("18.11.2026 г.", "1 265 236 578,00 €" / "18 Nov 2026", "€1,265,236,578.00").
- **Tests:**
  - New `e2e/layout.spec.ts`, `UX-13 Bulgarian at 768 px …`: 16 list and admin pages fail on sideways page scrolling, sideways-scrolling tables (board excluded by design) or a select that cuts its option.
  - `src/lib/format.test.ts`: 5 `UX-13 …` compact-money cases (en/bg).
  - Final sweep: 68 checks per language, no findings.
- **Gate:** lint, prettier, typecheck, Vitest 225/225, i18n 1190 keys; Playwright Chromium 45/45 (including the new layout spec); backend ruff, mypy, import-linter 14/14, pytest 1304 passed.

## UX-14 — 2026-11-18 19:00

- **What changed:**
  - New `frontend/e2e/visual.spec.ts`: 152 screenshot baselines, 38 views in English and Bulgarian at 1440 and 768 px:
    - signed out: sign-in, forgot password, a used set-password link;
    - the 23 main pages and the not-found page;
    - record, edit and convert pages for fixed-name records created by the test (organization, contact, lead, opportunity, user, integration client).
  - **Making it repeatable:** the E2E database grows with every run, so the test intercepts GET responses in the browser:
    - lists come back empty, so pages show their empty states;
    - integration clients, API keys and subscriptions come back empty;
    - sessions keep only the current one;
    - board columns have no cards.

    What still varies is masked: `<time>`, date and time text, charts, and the dashboard and win/loss figure cards. The tolerance is `maxDiffPixelRatio: 0.002`; animations are off and the caret hidden.
  - **Own project:** `visual` in `playwright.config.ts`. `pnpm e2e` now runs only `chromium` and `firefox` (so CI is unchanged); `pnpm e2e:visual` runs the baselines, and `--update-snapshots` updates them. Documented in CLAUDE.md.
- **Why not in CI:** baselines depend on the platform's font rendering. These were made on macOS (`*-visual-darwin.png`) and CI runs Linux. Linux baselines would need the Playwright Docker image or a CI job, which is new infrastructure; proposed as C-10 rather than added.
- **AC:**
  - Generated once, then two runs in a row: `4 passed` and `4 passed` (no diffs).
  - Sensitivity checked: swapping one baseline for another page's image fails with 19,972 different pixels; restoring it passes.
  - The first attempt had the dashboard figures unmasked, and both runs still passed within the pixel tolerance even though the totals change per run. They are now masked and the baselines regenerated.
- **Gate:** lint, prettier, typecheck, Vitest 225/225; Playwright Chromium 45/45 (visual excluded from the normal run); visual 4/4 twice.

## UX-14 follow-up — 2026-11-18 19:20

- One visual run after a full E2E run failed on `en-768-win-loss`: the report shows its totals in a table, not cards, and the E2E run had added won deals. The win/loss table is now masked too and the baselines regenerated. Verified: full E2E run (45/45), then the visual suite twice in a row (4/4, 4/4).

## FN-01 — 2026-11-18 19:25

- **Found:** the profile already changed the password through `POST /auth/password/change`; the backend ends the user's other sessions (FR-AUTH-04), and the page said so ("Password changed. Your other sessions were signed out.") and reloaded the sessions list.
- **What changed:** the form now reuses UX-07's `PasswordChecklist`, live from `useWatch`, and `PasswordInput` (show/hide, Caps Lock) for all three fields. The schema uses the shared `PASSWORD_MIN_LENGTH`/`PASSWORD_MAX_LENGTH`.
- **Tests:** in `src/features/profile/profile.test.tsx`:
  - `FN-01 shows the password rules live while typing`: the rules update, and each field has show/hide;
  - `FN-01 changes the password and says the other sessions were signed out`: request body, message, the sessions list reloaded with only this session left, form cleared.
- **Gate:** lint, prettier, typecheck, Vitest 227/227, i18n 1190 keys; Playwright Chromium 45/45; visual 4/4 (the password card is below the 900 px fold, so no baseline changed); backend ruff, mypy, import-linter 14/14, pytest 1304 passed.

## FN-02 — 2026-11-18 19:40

- **Found:** the profile listed sessions from `GET /me/sessions`. It showed the current one as "This session" with no button, and the others with sign-out (`DELETE /me/sessions/{id}`, confirmed since UX-05). The device column showed the raw user-agent string (truncated), and UX-13 had hidden "Signed in" below 1024 px.
- **What changed:** new `lib/userAgent.ts` (`describeUserAgent`: Edge, Opera, Firefox, Chrome, Safari on Windows, iOS, Android, macOS, ChromeOS, Linux). The device cell shows "Chrome on Windows" / "Chrome на Windows", with the full string as its tooltip, and wraps. "Signed in" is shown at every width; the IP address is the column hidden below 1024 px now.
- **Tests:**
  - `src/lib/userAgent.test.ts`: 7 `FN-02 …` cases (Chrome, Edge, Safari, Firefox, Android, a non-browser client, no user agent).
  - `profile.test.tsx`: `FN-02 lists device, start and last activity, with only the others revocable` and `FN-02 names the browser in Bulgarian too`.
  - The session fixtures now carry realistic user-agent strings, and the FN-01 check that the other session disappears asserts "Safari on iOS" (with the placeholder strings it would have passed for the wrong reason).
- **Gate:** lint, prettier, typecheck, Vitest 236/236, i18n 1191 keys; Playwright Chromium 45/45 (the layout test covers `/profile` at 768 px in Bulgarian); visual 4/4; backend ruff, mypy, import-linter 14/14, pytest 1304 passed.

## FN-03 — 2026-11-18 19:55

- **Found:** all the account actions existed on the user's own page (spec section 5 endpoints). The list's row menu (UX-08) had Open, Edit and an unconfirmed Unlock.
- **What changed:**
  - **Row menu:** new `features/admin/useUserActions.tsx`. The menu offers what fits each user:
    - Unlock, if locked and active;
    - for active users, **Create password reset link**, **Sign out everywhere** and **Deactivate** (not on yourself);
    - **Activate** for deactivated users.
  - **Confirmation:** each action is confirmed in the new controlled `components/ConfirmDialog.tsx` (the twin of `ConfirmButton` for places that cannot hold a dialog trigger), then shows a toast and refreshes the list.
  - **Reset link:** shown once in a sheet like UX-09 (link panel, copy, expiry, emailed or not, "not shown again", Done). It is held only in local state and the mutation uses `gcTime: 0` and `reset()`, so it is gone from the DOM and the caches after closing.
  - New confirmation texts (activate, unlock, reset) in en/bg. I first wrote that earlier links stop working; the backend does not void them, so the text does not say so.
- **Tests:** `src/features/admin/userActions.test.tsx`, 5 `FN-03 …` cases:
  - the actions offered for an active user, yourself and a deactivated user;
  - deactivate and sign-out-everywhere confirmed first, then the right endpoint and toast;
  - cancel does nothing;
  - reset link in Bulgarian, shown once and gone from the DOM and the mutation cache.

  The UX-08 unlock test now confirms first.
- **Looked at:** the confirmation and the link sheet, en/bg at 1440 and 768 px; axe on both: no violations.
- **Gate:** lint, prettier, typecheck, Vitest 241/241, i18n 1195 keys; Playwright Chromium 45/45 + 2 screenshot specs; visual 4/4; backend ruff, mypy, import-linter 14/14, pytest 1304 passed.

## FN-04 — 2026-11-18 20:15

- **Found:** a 401 already cleared the user and sent them to `/sign-in?next=…` (handler in `main.tsx`), but with no message. When it raced with `RequireAuth`'s own redirect, only one of the two survived.
- **What changed:**
  - **Single redirect:** `createQueryClient` no longer navigates. On a 401 it records under `SESSION_EXPIRED_KEY` whether someone *was* signed in (a first visit does not count), then clears the user. `RequireAuth`, now the only redirect, builds the target with the new `signInAfterUnauthorized`: `next=` keeps the page and query, and `expired=1` is added for a lost session.
  - **Message:** the sign-in page shows "Your session has ended. Sign in again to continue where you were." (en/bg) for `expired=1`. After signing in, the existing `next` handling returns the user to the page.
  - **Unsaved changes:** the UX-11 guard no longer blocks navigation to `/sign-in`, since unsaved changes cannot be saved without a session.
- **Files:** `frontend/src/app/queryClient.ts`, `src/main.tsx`, `src/test/render.tsx`, `src/features/auth/{sessionExpiry.ts,RequireAuth.tsx,SignInPage.tsx}`, `src/components/UnsavedChangesGuard.tsx`, i18n.
- **Tests:**
  - `src/features/auth/sessionExpiry.test.tsx`, 4 `FN-04 …` cases:
    - a lost session goes to sign-in with the message and `next`, and signing in returns to `/leads?status=new`;
    - a first visit gets no message;
    - unsaved changes do not hold the redirect back;
    - the target URL in each case.
  - **E2E** `e2e/session.spec.ts`: a rep signs in; an Admin (another browser context) signs the rep out everywhere; the rep's next navigation shows the message at `/sign-in?next=%2Fleads&expired=1`; signing in returns to `/leads`.
- **Gate:** lint, prettier, typecheck, Vitest 245/245, i18n 1196 keys; Playwright Chromium 46/46; visual 4/4; backend ruff, mypy, import-linter 14/14, pytest 1304 passed.

## FN-05 — 2026-11-18 20:20 — blocked `[!]`: needs an owner decision (API spec)

- **Blocker:** to warn 5 minutes before the idle timeout, the frontend must know the timeout. It is the setting `session_idle_timeout_minutes`, readable only through `GET /api/v1/settings`, which is **Admin only**. `GET /me` does not include it, and `GET /me/sessions` gives `last_seen_at` and the absolute `expires_at`, not the idle deadline. Section B allows backend work only "exactly as specified", and no specified endpoint provides this to every signed-in user. Guessing the default (8 h) would warn at the wrong time once an Admin changes the setting.
- **Proposal (additive, for approval):** add to `GET /api/v1/me` for user principals
  `"session": { "idle_timeout_minutes": 480, "expires_at": "<absolute expiry>" }`, documented in API spec section 4 (`/me`).
  - The frontend then keeps the time of the last request in `localStorage` and a `BroadcastChannel`, so every tab shares activity.
  - It shows the dialog at `last activity + idle − 5 min` with **Stay signed in** (`GET /me`, which refreshes `last_seen_at`) and **Sign out**; choosing in one tab closes the dialog in all.
  - Note: the backend refreshes `last_seen_at` at most every `_TOUCH_INTERVAL` (`identity/service.py`), so the client deadline should be computed from the last request minus that interval, to stay on the safe side.
- Nothing was built for FN-05.

## FN-06 — 2026-11-18 20:30

- **Found: already built (Phase 1, FR-I18N-01, kept working through UX-02/UX-05).**
  - Switching language in the account menu saves it with `PATCH /me` (`useChangeLocale`); since UX-05, a failure says so.
  - Sign-in applies the `locale` from the login response and stores it for the sign-in page.
  - `RequireAuth` switches the UI to the profile's language on any device.
  - Tested already: `FR-I18N-01 saves the language on the profile when signed in`, `FR-I18N-01 follows the language stored on the profile`.
- **Added:** `FN-06 signing in on another device applies the language saved on the profile` (`src/app/app.test.tsx`): a browser last used in English signs in as a user whose profile says Bulgarian; the UI and `<html lang>` switch to Bulgarian, and the device remembers it. No code change was needed.
- **Gate:** lint, prettier, typecheck, Vitest 246/246, i18n 1196 keys; Playwright Chromium 46/46; backend pytest 1304 passed (ruff, mypy, import-linter unchanged).

## FN-07 — 2026-11-18 20:40

- **Found: already built (Phase 5a).** The audit log header has the shared `ExportMenu` (XLSX, CSV) calling `GET /audit-log/export` with the same `filterQuery` as the list. Since UX-10 that includes the user, record type, action and the Sofia-day date range. It had no test.
- **Added:** `FN-07 exports the log with the current filters and without paging` (`src/features/admin/auditViewer.test.tsx`). From a filtered URL on page 3, the export request carries `actor_id`, `entity_type`, `action`, `occurred_at_from`/`to` as UTC instants of the Sofia days, and `format=csv`, and no `page`. The file is downloaded. No code change was needed.
- **Gate:** lint, prettier, typecheck, Vitest 247/247; Playwright Chromium 46/46; backend pytest 1304 passed.

## FN-08 — 2026-11-18 20:55

- **Found:** the backend part was already done and specified. `409 permission.last_admin` blocks demoting or deactivating the last active Admin (`identity/service.py::_ensure_not_last_admin`), it is in the error-code table of `05-api-specification.md` and the user rules (section 5), and it is tested (`test_last_admin_cannot_be_demoted_or_deactivated`). Deactivating yourself was already refused (`403`) and hidden in the UI. Because a last active Admin is necessarily the viewer, the UI cases are demoting yourself and deactivating yourself.
- **What changed:**
  - New `features/admin/useLastAdmin.ts` counts active Admins (`GET /users?role=admin&is_active=true&page_size=1`).
  - In the edit sheet (row menu and user page), the last active Admin's **Role** is a disabled select with the reason "At least one active administrator must remain." as its description. It is not registered with the form, so other changes still save with the role unchanged.
  - On the user page, an unavailable **Deactivate** now says why: the last-admin reason, or "You cannot deactivate your own account."
  - If the count was out of date, the server's 409 is shown translated in the sheet.
- **Tests:** `src/features/admin/lastAdmin.test.tsx`, 4 `FN-08 …` cases:
  - the last Admin's role is locked with the reason, and a name change saves with `role: admin`;
  - with two Admins the role is editable;
  - Deactivate is disabled on the page with the reason;
  - the server's 409 is explained.
- **Looked at:** the own user page with the reason, en/bg at 1440 and 768 px; axe: no violations. The last-Admin state itself cannot occur on the E2E stack, which has two Admins; component tests cover it.
- **Gate:** lint, prettier, typecheck, Vitest 251/251, i18n 1197 keys; Playwright Chromium 46/46 + 2 screenshot specs; visual 4/4; backend ruff, mypy, import-linter 14/14, pytest 1304 passed.

## Final summary — 2026-11-18 21:10

**Done (21):**
- UX-01 to UX-14: tokens, app shell, page header, states, feedback, sign-in, password pages, users table, user sheets, audit viewer, form conventions, accessibility, Bulgarian layout, visual baselines.
- FN-01 to FN-04: password change, sessions, row-menu account actions, session expiry.
- FN-06 to FN-08: language preference, audit export, last-admin protection.
- UX-05 and UX-06 were first blocked by the development Mac running out of memory. They passed unchanged once it was freed.

**Blocked (1):** FN-05 idle-timeout warning. The idle timeout is readable only by Admins (`GET /settings`), and section B allows only already-specified endpoints. Proposal (needs owner approval): add `session.idle_timeout_minutes` and `session.expires_at` to `GET /me`, then build the cross-tab warning as described in the FN-05 entry.

**Not applicable:** none. Several B items were already built in Release 1 (FN-06, FN-07, the backend of FN-08); they got the missing tests.

**Also fixed:** the assistant dropped an opened "save as note" form when the conversation reloaded after an answer (the cause of an intermittent E2E failure).

**API change (additive, documented):** optional `sort` on `GET /api/v1/users` (UX-08). The spec, `docs/api/openapi.json` and the generated types are updated.

**Section C proposals for the owner:**
- C-01 branding (plugs into `--brand`);
- C-02 dark mode;
- C-04 command palette;
- C-05 system status page;
- C-06 sign-in notice;
- C-09 a locked-users filter on `GET /users`;
- C-10 Linux visual baselines in CI.

C-03 (two-factor sign-in) was built in Phase 8a. C-07 (chart polish) and C-08 (assistant flake) were fixed during the loop.

**Final gate (2026-11-18 21:05):**
- frontend: lint, prettier, typecheck, Vitest 251/251, i18n 1197 keys, API types up to date;
- Playwright Chromium 46/46, visual 4/4;
- backend: ruff, mypy, import-linter 14/14, pytest 1304 passed (95.57%), OpenAPI snapshot up to date.

`docs/Plan.md`, `docs/Test_strategy.md` (section 19 and the regenerated inventory), `docs/accessibility.md`, the README and CLAUDE.md are updated. Nothing is pushed.

## FN-05 — 2026-11-18 21:50 — done after owner approval

- **Owner decision (2026-11-18):** approved the proposed additive API change.
- **API:** `GET /api/v1/me` returns `session: { "idle_timeout_minutes", "expires_at" }` for a signed-in user (`null` for integration clients). The API spec (section 4) is updated first, then the backend (`SessionTimeouts` schema, `_session_timeouts` in `identity/service.py`, `repository.get_session`), `docs/api/openapi.json` and the generated types. The setting is read live, so an Admin's change applies at the next `/me`.
- **Frontend:**
  - `api/client.ts` gained `onApiRequest` for every `/api/v1` request (health checks are left out because they do not touch the session; the 30-second status poll would otherwise have kept the warning away for ever).
  - New `features/auth/sessionActivity.ts`: the last request time in `localStorage`, shared with other tabs through the `storage` event, plus `idleSchedule`: deadline = last request − 1 min (the server's touch interval) + idle timeout, capped at the absolute expiry; the warning comes 5 minutes earlier.
  - New `features/auth/IdleWarning.tsx`, mounted in the layout: an alert dialog "Still there?" with a live countdown.
    - **Stay signed in** calls `GET /me`; that request is activity in every tab, so the dialog closes everywhere.
    - **Sign out** signs this tab out and, through `crm.signed-out`, the other tabs too. Ordinary sign-out from the account menu broadcasts as well.
    - With no answer, at the deadline the tab calls `POST /auth/logout` and goes through the FN-04 path ("Your session has ended", then back to the page).
  - Mount time counts as activity, so a value left in storage by an earlier session cannot end a new one.
- **Tests:**
  - Backend `test_FN_05_me_gives_the_session_timeouts`: the timeout and the session's expiry, the setting change shown at once, `null` for an integration client.
  - `src/features/auth/idleWarning.test.tsx`, 6 `FN-05 …` cases with fake timers: the schedule, the warning at 24 of 30 minutes and Stay, activity from another tab, the deadline leading to sign-in with the message, Sign out broadcast, another tab's sign-out in Bulgarian.
  - E2E `e2e/idle.spec.ts`: two tabs in one browser with Playwright's clock; both show the warning; Stay in one closes it in both.
- **Looked at:** the dialog in en/bg at 1440 and 768 px; axe: no violations. "Stay signed in" was made the primary button after looking.
- **Gate:** lint, prettier, typecheck, Vitest 257/257, i18n 1200 keys, API types regenerated; Playwright Chromium 47/47; visual 4/4; backend ruff, mypy, import-linter 14/14, pytest 1305 passed (95.55%).

**Addendum (21:55):** FN-05 is done after the owner approved the API addition, so all 22 items in sections A and B are now done. The second additive API change is `GET /me` → `session`.

**Final gate after rebasing on `main` (loop restart, 2026-11-18 22:30):** no `[ ]` or `[!]` items remain in sections A and B. On branch `ui-polish` (PR #22):
- frontend: lint, prettier, typecheck, Vitest 257/257, i18n 1200 keys, API types up to date;
- Playwright Chromium 47/47, visual 4/4;
- backend: ruff, mypy, import-linter 14/14, pytest 1305 passed (95.55%), OpenAPI snapshot up to date.

## CI follow-up for PR #22 — 2026-11-22

PR #22's first CI run (`44364701501`) failed two end-to-end tests on Chromium and Firefox. Both passed locally.

**`layout.spec.ts`: `/contacts` scrolled sideways by 156–176 px at 768 px.**
- CI's database holds different contact data than the local one. The contacts list had been left out of UX-13's narrow-screen trimming.
- Fixed: job title and owner are hidden below 1024 px, and name, organization and email wrap anywhere, so the table fits whatever the content.
- I could not reproduce CI's exact rows locally; the next CI run is the check.

**`session.spec.ts`: sign-in showed no "session has ended" message.**
- `useMe` caught the 401 itself and returned "no user". When the profile reload was the first request after the session ended (the order in CI), the expiry was never recorded.
- Fixed: `useMe` records a lost session the same way the query cache does.
- New test `FN-04 says so too when the profile reload is the first request after the session ended`. It fails without the fix and passes with it.

**Also cherry-picked here:** the housekeeping test fix (it compared the fixed test date with the real clock and fails from 2026-11-20 on).

**Gate:** Vitest 258/258, i18n 1200 keys; Playwright Chromium 47/47 (one sign-in timeout in `party.spec.ts` passed alone twice); visual 4/4; backend pytest 1305 passed.

**Second CI run (PR #23, run `44982236874`):** the contacts fix held. Two tests still failed:
- **`/admin/audit-log` scrolled by 6–8 px at 768 px** with CI's data. Actor, action and record now wrap too.
- **The session test failed again: my first diagnosis was incomplete.** CI's trace shows the real cause. When the session ended, **two** requests answered 401 at once (lead sources and leads). The first marked the session as expired and cleared the user; the second then saw no user and overwrote the flag with "not expired". Locally the lead sources were cached, so only one request failed.
  - Fixed: a 401 only ever *sets* the flag, and a successful sign-in resets it.
  - New test `FN-04 says so when several requests fail together as the session ends`. It fails without the fix (reproducing CI) and passes with it.
  - The earlier `useMe` change stays: it covers a real path, but it was not the cause here.

**Gate:** Vitest 259/259; Playwright Chromium 47/47; visual 4/4.
