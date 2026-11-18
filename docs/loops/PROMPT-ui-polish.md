# Ralph loop prompt — UI polish after Phase 1

You are running in an automated loop. This same prompt is given to you again after every iteration. Each iteration completes **exactly one** backlog item, leaves the repository green and committed, and records what happened.

## Authority for this loop

- The owner has **pre-approved** the items in sections A and B of `docs/loops/ui-polish-backlog.md`. For those items only, do not stop to propose a breakdown or wait for approval, despite the general rule in `CLAUDE.md`.
- Every other rule in `CLAUDE.md` still applies: frontend/backend separation, layering, additive migrations only, API catalog, security, i18n in English and Bulgarian, audit, tests with every change, no new dependencies without approval.
- Do not start Phase 2 or any other phase. Do not build section C items.

## Each iteration

1. **Orient.** Read `CLAUDE.md`, `docs/loops/ui-polish-backlog.md` and the last entries of `docs/loops/ui-polish-progress.md` (create it if missing). Run `git status` and `git log --oneline -5`.
2. **Repair first.** If the working tree is dirty from an interrupted iteration, or the quality gate is failing, the iteration's job is to fix that, commit, log it, and end the iteration.
3. **Pick.** Take the first `[ ]` item in section A; when A has none, the first `[ ]` in section B. If the item refers to a screen or endpoint that does not exist yet and is not part of Phase 0 or Phase 1, mark it `[-]` with a one-line reason, log it, and end the iteration.
4. **Implement** the smallest change that meets the item's acceptance criteria. Prefer shared, reusable components in `frontend/src/components/` that later phases will use. Every new string goes into both `en` and `bg` translation files.
5. **Test.** Add or update tests that prove the acceptance criteria (component tests, and Playwright where the item says so). Name tests after the item ID, for example `UX-06 shows caps lock warning`.
6. **Look at it.** For any visible change, start the stack, take Playwright screenshots of the affected pages in English and Bulgarian at 1440 and 768 px wide, open and inspect them, and fix what looks wrong (alignment, overflow, contrast, spacing). Run the axe check on those pages. Do not commit these working screenshots.
7. **Quality gate.** Run the full gate from `CLAUDE.md` (backend: ruff, mypy, import-linter, pytest; frontend: lint, typecheck, Vitest, API types up to date, i18n key check; Playwright journeys affected). Everything must pass. Never weaken, skip or delete a test to get there.
8. **Commit** one Conventional Commit for the item, for example `feat(ui): UX-06 improve sign-in page`. Do not push.
9. **Record.** Mark the item `[x]` in the backlog and append to `docs/loops/ui-polish-progress.md`:
   `## <item ID> — <date/time>` with what changed, files touched, tests added, anything noticed for later. Commit the backlog and progress update with the item or as `chore(loop): ...`.

## When stuck

If an item still fails the gate after three genuine attempts in this iteration, revert its uncommitted changes, mark it `[!]`, explain the blocker and what you tried in the progress log, commit, and move on next iteration. If the blocker needs an owner decision (design choice, missing asset, spec conflict), say so explicitly in the log; do not guess.

## Ideas you have along the way

Do not build them. Add them as new entries in section C of the backlog with one line of reasoning.

## Finishing

When no `[ ]` items remain in sections A and B, run the full quality gate once more. If it passes and the working tree is clean, write a final summary at the end of the progress log (done, blocked with reasons, not applicable, new section C proposals), commit it, and then output exactly:

<promise>UI_POLISH_COMPLETE</promise>

Output that line only when all of this is true. Never output it to escape the loop early, and never because an item is hard; use `[!]` for that.
