# Accessibility (NFR-10)

NFR-10: keyboard-operable throughout, including a non-drag way to change stage; WCAG 2.1 AA for contrast and labels. Test strategy section 5: axe checks in Playwright on every main page, and a keyboard-only pass over the board and the forms.

## Automated checks (`frontend/e2e/accessibility.spec.ts`)

axe-core (`@axe-core/playwright` 4.14.0) with the WCAG 2.0 and 2.1 A and AA rules, on the composed stack, signed in as an Admin:

- the sign-in page;
- the home dashboard;
- organizations (list, new, a record page with its timeline), contacts (list, new), leads (list, new), opportunities (list, new, board);
- my tasks, the win/loss report, search, the profile;
- administration: users (list, new), import, integrations, the delivery log, the audit log, settings, lists, stages;
- the assistant drawer when the stack runs with it.

The check runs in CI on Chromium and Firefox with every change.

| Date | Result |
|---|---|
| 2026-11-18, first run | 3 rules failed: `aria-hidden-focus` on the dashboard (2 charts), `color-contrast` on destructive buttons (14 on lists, 6 on stages, 1 on record pages, 1 in the assistant drawer) |
| 2026-11-18, after the fixes below | No violations locally |
| 2026-11-18, CI after merging #18 (run on `main`) | `color-contrast` on the red "Locked" badge in Chromium and Firefox |
| 2026-11-18, after darkening the destructive token | No violations locally (Chromium); CI covers Firefox |

Fixes:
- **Dashboard charts** are hidden from assistive technology because a screen-reader table holds the same figures, but Recharts 3 made the chart surface focusable, so keyboard focus reached hidden content. The charts now use `accessibilityLayer={false}`.
- **Destructive red** (buttons such as Archive, Delete, Deactivate, and the red badges such as "Locked") was below 4.5:1 on its light red tint. The light theme's `--destructive` token is now Tailwind's red 700 instead of red 600; the dark theme is unchanged. (The first fix darkened only the buttons; CI then found the "Locked" badge, which the local data had not shown. The check now creates a locked user first.)

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

## Manual checks still to do by a person

Automated tools find about a third of accessibility problems. Before go-live, someone should:

- use the main journeys with a screen reader (NVDA on Windows, VoiceOver on macOS), in Bulgarian and English, especially the board, the assistant's streamed answers (`role="log"`), and toasts;
- zoom to 200 % and use a 1024 px wide window (NFR-11 tablet width);
- check visible focus on every control in the dark theme.

Record the results here.
