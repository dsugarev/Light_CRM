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

**Status colours (UI loop 2).** Green (`--success`), amber (`--warning`) and blue (`--info`) status badges use green and amber 800 and blue 700 on a 10% tint of the same colour: at least 5.8:1, measured from the theme tokens by `src/app/statusColors.test.tsx` (which also checks `--destructive`). Every coloured badge keeps its text label, so status is never shown by colour alone (WCAG 1.4.1). The axe pass (Chromium) was rerun after loop 2 on 2026-11-22: no violations (see `docs/loop_result.md`).

**Target size (UI loop 2, WCAG 2.5.8).** On a touch screen (`pointer: coarse`) buttons, inputs and selects are 44 px high (small buttons 40 px, the smallest icon buttons 32 px); with a mouse the compact sizes stay (32 px, the smallest 24 px, which meets the 24 px minimum). Measured in Chromium with touch emulation; `src/components/responsive.test.tsx` pins the classes. Record details stack label over value below 640 px, so they reflow without sideways scrolling (WCAG 1.4.10).

**Motion and status (UI loop 2).** With "reduce motion" set in the operating system, animations and transitions end at once (WCAG 2.3.3), checked in Chromium. A list that is loading its next page has `aria-busy="true"`; the moving bar is hidden from assistive technology.

**Warm theme (UI loop 3).** The palette is warm (cream page, warm-grey text, terracotta brand), and every pair keeps its threshold, measured from the tokens by `src/app/warmTheme.test.ts`:
- body text 17:1;
- muted text at least 5.6:1 on every surface;
- white on the terracotta button 5.7:1, and 7.3:1 on its hover shade;
- the terracotta focus ring at least 5.1:1 on page, card and sidebar;
- dashboard bars at least 3:1 against the card.

Primary buttons darken on hover rather than fading, so their text keeps contrast. The active navigation item is shown by `aria-current="page"`, by weight and by a leading bar, not by colour alone. Axe, keyboard focus-contrast and the Bulgarian 768 px layout check passed in Chromium on 2026-11-22.

**Interactivity (UI loop 3).**
- **Sales path:** an ordered list named "Sales path". The current stage has `aria-current="step"`, and passed stages carry a screen-reader "(passed)", so progress isn't shown by colour alone. Each stage button is named "Move to {stage}", which contains its visible text (WCAG 2.5.3).
- **Clickable rows:** they add mouse convenience only. The link in the row stays the single keyboard and screen-reader target, so there are no extra tab stops.
- **KPI cards:** each card is one link named by its label and stretched over the card. Keyboard focus rings the whole card.

**Assistant action cards (R1.1).**
- Each card is a region named by its title ("Create task").
- Its details are a description list, and the buttons are labelled **Confirm** and **Cancel**.
- The outcome is announced as status text ("Done.", "Not done."), and a refusal comes as an alert.
- Destructive cards are red, and also say "This changes or removes data" in text, so colour is not the only signal.
- Covered by `assistant.test.tsx`. The screen-reader walkthrough script should include confirming a card.

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

### Results (2026-11-22)

**Zoom 200% and 1024 px window: automated check done.** A Playwright script opened 20 pages, signed in as an Admin in English and again in Bulgarian, at a 1024 × 768 window and at 640 × 400 CSS pixels (200% zoom of a 1280 × 800 window):
- the dashboard, the lists, a record page of each kind, the board, tasks, the report, the profile, search and the admin pages;
- each page checked for sideways scrolling of the page and for axe WCAG 2.2 A/AA violations.

The first run found two problems, both in Bulgarian at 200% zoom, and both are fixed:
- the win/loss table scrolled sideways but could not be reached by keyboard (axe `scrollable-region-focusable`). A table wider than its container now makes the container focusable, so arrow keys scroll it; a table that fits adds no tab stop (`ui/table.tsx`, `tableFocus.test.tsx`);
- the organization page was 2 px wider than the screen, because its right column (a grid item) had no `min-w-0`.

The rerun found 0 problems on 20 pages × 2 sizes in both languages. The script is kept with the session notes; the Bulgarian 768 px layout check (`layout.spec.ts`) and axe (`accessibility.spec.ts`) keep running in CI.

**Dark theme:** not applicable to Release 1. Dark mode is not switched on (backlog C-02).

**Screen reader: still open.** It needs a person with NVDA or VoiceOver. Suggested script (about one hour):
1. sign in;
2. open a lead and qualify it;
3. convert it;
4. move the opportunity on the board by keyboard (Space, arrow keys, Space) and listen for the announcements;
5. close it as lost with a reason;
6. ask the assistant a question and listen to the streamed answer;
7. check that toasts are read.

Do this once in English and once in Bulgarian, and record the findings here.
