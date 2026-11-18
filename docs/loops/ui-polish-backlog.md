# UI polish and small improvements — loop backlog (after Phase 1)

Owner-approved work list for the Ralph loop defined in `PROMPT-ui-polish.md`.

Status markers: `[ ]` to do · `[x]` done · `[!]` blocked (reason in the progress log) · `[-]` not applicable (the screen or endpoint does not exist yet).

Work order: section A top to bottom, then section B. **Section C must not be built by the loop.**

Why now: Phase 1 sets the patterns every later phase reuses (app shell, tables, forms, dialogs, error handling). Polishing them now as shared components means Phases 2–8 inherit the quality instead of repeating the work.

## A. Interface polish (approved)

- [x] **UX-01 Design tokens.** All colors, radii, spacing, shadows and font sizes come from CSS variables in one theme file (shadcn/Tailwind tokens). The brand primary color is a single token with a placeholder value and a `TODO(owner): brand color` comment. AC: no hex, rgb or hsl color literals in component files (checked by a lint rule or test).
- [x] **UX-02 App shell.** Collapsible left sidebar with navigation grouped by area, active route highlighted; only routes that exist are shown. Top bar with the user menu (profile, language, sign out). Below 1024 px the sidebar becomes a drawer. AC: usable at 1440 and 768 px; keyboard reachable; state of collapse remembered for the session.
- [x] **UX-03 Page header component.** Title, optional description, breadcrumbs and an actions slot; used on every existing page. AC: no page renders its own ad-hoc header.
- [x] **UX-04 Loading, empty and error states.** Shared skeletons for tables and forms; an empty-state component (icon, message, optional action); a route error boundary showing a friendly message, a retry button and the request ID. AC: every existing page uses them; no raw "Loading…" text or blank screens.
- [x] **UX-05 Feedback and confirmation.** One toast helper that maps backend error `code`s to translated messages, with a generic fallback; one confirm-dialog component for destructive actions (deactivate user, revoke sessions). AC: no `window.confirm`/`alert`; every mutation shows success or error feedback.
- [x] **UX-06 Sign-in page.** Show/hide password, Caps Lock warning, correct `autocomplete` attributes, button disabled with spinner while pending, lockout message with remaining time from `locked_until`, focus moved to the first error, language switch on the page. AC: covered by component tests and the existing Playwright sign-in journey.
- [x] **UX-07 Set and reset password pages.** Live checklist of the password policy rules, confirm-password match, clear page for invalid or expired tokens explaining what to do next. AC: component tests for each rule and the expired-token state.
- [x] **UX-08 Users table.** Shared data-table component with search, filters for role and status, sortable columns, status badges (active, inactive, locked), last sign-in shown relative with the exact time on hover, row action menu; filters and sorting kept in the URL. AC: the data-table component is generic and documented for reuse in later phases.
- [x] **UX-09 Create and edit user.** Form in a side sheet; after creation the one-time set-password link is shown with a copy button, its expiry, and a note that it will not be shown again. AC: link never stored in frontend state after the sheet closes.
- [x] **UX-10 Audit log viewer.** Filters for user, entity type, action and date range with presets (today, 7 days, 30 days); a detail drawer showing before and after values side by side with changed fields highlighted, falling back to formatted JSON. AC: works with long values and Cyrillic text.
- [x] **UX-11 Form conventions.** Shared form field components: label, required marker, help text, inline errors translated from backend field codes, consistent spacing; a warning before leaving a page with unsaved changes. AC: all existing forms use them.
- [x] **UX-12 Accessibility.** Visible focus rings, a skip-to-content link, landmarks, labelled controls, sufficient contrast; axe check with no serious or critical violations on every page. AC: axe runs inside Playwright for every existing page.
- [ ] **UX-13 Bulgarian layout check.** No truncated or overflowing text with Bulgarian strings at 1440 and 768 px; dates and numbers formatted per locale. AC: screenshots reviewed for both languages; any fixes made in components, not by shortening translations.
- [ ] **UX-14 Visual baselines.** Playwright screenshot tests for every existing page, in English and Bulgarian, at 1440 and 768 px, with baselines committed. Done last, after the other A items. AC: suite passes twice in a row (no flaky diffs; dynamic values masked).

## B. Small functional improvements (approved, within the existing spec)

Build these only through endpoints already specified in `docs/05-api-specification.md`. If the backend part is missing, implement it exactly as specified, with tests.

- [ ] **FN-01 Change password** on the profile page (`POST /auth/password/change`), reusing the policy checklist from UX-07; other sessions are revoked and the user is told so.
- [ ] **FN-02 My sessions** on the profile page (`GET /me/sessions`, `DELETE /me/sessions/{id}`): device/browser, created, last seen, current session marked and not revocable from the list.
- [ ] **FN-03 Admin user actions** in the users table row menu: unlock, issue password-reset link (shown like UX-09), revoke all sessions, deactivate and activate, each with confirmation (spec section 5).
- [ ] **FN-04 Session expiry handling.** Any 401 sends the user to sign-in with a "session expired" message and returns them to the page they were on after signing in again. AC: Playwright test with an expired session.
- [ ] **FN-05 Idle-timeout warning.** A dialog appears 5 minutes before the idle timeout with "Stay signed in" (calls `GET /me`) and "Sign out"; it works across several open tabs of the app.
- [ ] **FN-06 Language preference.** Switching language saves it to the profile (`PATCH /me`) and it is applied at the next sign-in on any device.
- [ ] **FN-07 Audit log export** button using `GET /audit-log/export` with the current filters.
- [ ] **FN-08 Last-admin protection in the UI.** Deactivating or demoting the last active Admin is disabled with an explanation; the backend returns `409 permission.last_admin` (add the code to the error-code table in `05-api-specification.md` if missing) with a test.

## C. Proposals for owner decision (do NOT build in the loop)

These need a product or design decision. The loop may add notes here but must not implement them.

- **C-01 Company branding:** logo, brand colors and favicon (needs assets; plugs into the UX-01 token).
- **C-02 Dark mode:** cheap once UX-01 is done; is it wanted?
- **C-03 Multi-factor authentication (FR-AUTH-07):** security feature, better built as a deliberate task with review than inside a loop.
- **C-04 Command palette (Ctrl+K) with global search:** valuable once organizations and leads exist (after Phase 2/3).
- **C-05 Admin system-status page:** version, database and worker health, failing webhook deliveries (fits Phase 6).
- **C-06 Sign-in notice:** an acceptable-use or data-protection notice on the sign-in page, if company policy needs one.
- **C-07 Dashboard chart polish:** Y-axis labels of large EUR amounts are clipped ("0000000") and the light-grey "Weighted" series and legend have weak contrast; compact axis formatting and a stronger chart token would fix both.
- **C-08 Assistant "Save note" flake:** fixed (commit `fix(assistant): keep an opened note form …`): the reload after an answer remounted the message and dropped an opened note form.
- **C-09 Locked-users filter:** `GET /users` has no `is_locked` filter, so the status filter offers active/deactivated only; adding one would let admins list locked accounts directly.
