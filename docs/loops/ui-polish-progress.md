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
