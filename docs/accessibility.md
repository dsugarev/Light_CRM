# Accessibility (NFR-10)

NFR-10: keyboard-operable throughout, including a non-drag way to change stage; WCAG 2.1 AA for contrast and labels. Test strategy section 5: axe checks in Playwright on every main page, and a keyboard-only pass over the board and the forms.

## Automated checks (`frontend/e2e/accessibility.spec.ts`)

axe-core (`@axe-core/playwright` 4.14.0) with the WCAG 2.0 and 2.1 A and AA rules, on the composed stack, signed in as an Admin:

- the sign-in page;
- the home dashboard;
- organizations (list, new, a record page with its timeline), contacts (list, new), leads (list, new), opportunities (list, new, board);
- my tasks, the win/loss report, search, the profile;
- administration: users (list, new), import, integrations, the delivery log, the audit log, settings, lists, stages;
- the assistant drawer when the stack runs with it;
- since the UI polish (UX-12, `UX-12 record, edit, detail and drawer pages` and `UX-12 signed-out pages`), every other route as well:
  - the contact, lead and opportunity record pages;
  - all edit pages, and lead conversion;
  - user detail, integration client, import batch and webhook delivery;
  - an audit entry as a page and in its drawer;
  - the not-found page;
  - forgot password, set password with a valid link, and with a used link;
- in `shell.spec.ts`: the navigation drawer and the account menu, open, at 768 px.

The test fails on any violation, which is stricter than the UX-12 criterion (no serious or critical ones). The check runs in CI on Chromium and Firefox with every change.

**Focus indicators (UX-12).** The light theme's focus ring token (`--ring`) is now `oklch(0.45 0 0)`, used at full strength for the default outline, so focus has more than 3:1 against the page (WCAG 1.4.11); before, it was a 50% light grey, about 1.5:1 on links. `keyboard.spec.ts` (`UX-12 focus indicators …`) focuses a sidebar link, a row action button and a search field by keyboard and measures the indicator's contrast in the browser.

| Date | Result |
|---|---|
| 2026-11-18, first run | 3 rules failed: `aria-hidden-focus` on the dashboard (2 charts), `color-contrast` on destructive buttons (14 on lists, 6 on stages, 1 on record pages, 1 in the assistant drawer) |
| 2026-11-18, after the fixes below | No violations locally |
| 2026-11-18, CI after merging #18 (run on `main`) | `color-contrast` on the red "Locked" badge in Chromium and Firefox |
| 2026-11-18, after darkening the destructive token | No violations locally (Chromium); CI covers Firefox |

Fixes:
- **Dashboard charts** are hidden from assistive technology because a screen-reader table holds the same figures, but Recharts 3 made the chart surface focusable, so keyboard focus reached hidden content. The charts now use `accessibilityLayer={false}`.
- **Destructive red** (buttons such as Archive, Delete, Deactivate, and the red badges such as "Locked") was below 4.5:1 on its light red tint. The light theme's `--destructive` token is now Tailwind's red 700 instead of red 600; the dark theme is unchanged. (The first fix darkened only the buttons; CI then found the "Locked" badge, which the local data had not shown. The check now creates a locked user first.)

**Status colours (UI loop 2).** Green (`--success`), amber (`--warning`) and blue (`--info`) status badges use green and amber 800 and blue 700 on a 10% tint of the same colour: at least 5.8:1, measured from the theme tokens by `src/app/statusColors.test.tsx` (which also checks `--destructive`). Every coloured badge keeps its text label, so status is never shown by colour alone (WCAG 1.4.1). The axe pass on the pages with badges has not yet been rerun after this change (see `docs/loop_result.md`).

**Target size (UI loop 2, WCAG 2.5.8).** On a touch screen (`pointer: coarse`) buttons, inputs and selects are 44 px high (small buttons 40 px, the smallest icon buttons 32 px); with a mouse the compact sizes stay (32 px, the smallest 24 px, which meets the 24 px minimum). Measured in Chromium with touch emulation; `src/components/responsive.test.tsx` pins the classes. Record details stack label over value below 640 px, so they reflow without sideways scrolling (WCAG 1.4.10).

**Motion and status (UI loop 2).** With "reduce motion" set in the operating system, animations and transitions end at once (WCAG 2.3.3), checked in Chromium. A list that is loading its next page has `aria-busy="true"`; the moving bar is hidden from assistive technology.

## Keyboard walkthroughs (`frontend/e2e/keyboard.spec.ts`)

Automated so they stay true: only Tab, Enter, Escape and typing, no clicks.

| Walkthrough | Result |
|---|---|
| Sign in from the email field to the home page | Works |
| The first Tab shows **Skip to main content**; Enter moves focus past the navigation | Works (added in Phase 8b; WCAG 2.4.1) |
| Create an organization from the form | Works |
| Move an opportunity to another stage on the board without dragging: the card's **Move … to** list (typing the stage name selects it) | Works (FR-OPP-03, NFR-10). Dragging also works with the keyboard (dnd-kit: Space to lift, arrows, Space to drop) |
| A confirmation dialog opens with Enter, closes with Escape, and focus returns to its button | Works |
| The assistant drawer opens with Enter with focus in the question box; Escape closes it and focus returns to the **Assistant** button | Works (focus return added in Phase 8b) |
| Move a deal on the board by keyboard runs as a fresh sales rep, so their board holds only that deal (the E2E admin's board grew past 200 tab stops across runs) | Works (UX-12) |

## Manual checks still to do by a person

Automated tools find about a third of accessibility problems. Before go-live, someone should:

- use the main journeys with a screen reader (NVDA on Windows, VoiceOver on macOS), in Bulgarian and English, especially the board, the assistant's streamed answers (`role="log"`), and toasts;
- zoom to 200 % and use a 1024 px wide window (NFR-11 tablet width);
- check visible focus on every control in the dark theme.

Record the results here.
