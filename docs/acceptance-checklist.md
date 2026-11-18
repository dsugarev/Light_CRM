# User acceptance checklist: Release 1

For the owner and a few users from the Commercial team, on the staging stack (`scripts/staging.sh`, fictional data) or on production before real data is loaded. Each line is a requirement from `docs/01-requirements.md`; the automated tests already cover them (see `docs/Test_strategy.md`), so this is the business check: does it work the way the team works?

Mark each line ✅ accepted, ❌ not accepted (with a note), or — not checked. Try each area in Bulgarian and in English at least once.

## Sign-in and users

| # | Check | Req. | Result | Note |
|---|---|---|---|---|
| 1 | An Admin creates a user; the user sets a password from the link and signs in | FR-AUTH-02, FR-ADM-01 | | |
| 2 | Five wrong passwords lock the account for 15 minutes; an Admin can unlock it | FR-AUTH-01 | | |
| 3 | A user turns on two-factor sign-in, signs out and in with a code, then with a recovery code | FR-AUTH-07 | | |
| 4 | "Require two-factor sign-in for Admins" makes an Admin without it set it up first | FR-AUTH-07 | | |
| 5 | Roles behave as expected: a Sales Rep cannot change another rep's records; a Viewer cannot change anything | FR-AUTH-05 | | |
| 6 | The interface follows each user's language; Cyrillic and Latin search both work | FR-I18N-01, FR-PARTY-04 | | |

## Organizations, contacts and leads

| # | Check | Req. | Result | Note |
|---|---|---|---|---|
| 7 | Creating an organization with an existing name or EIK warns about the duplicate | FR-PARTY-01 | | |
| 8 | The organization page shows its contacts, leads, opportunities, activities and figures | FR-PARTY-03 | | |
| 9 | A lead is captured, contacted, qualified with BANT and converted into an organization, contact and opportunity | FR-LEAD-01..04 | | |
| 10 | A lead is disqualified with a reason and reopened | FR-LEAD-03 | | |

## Opportunities, activities and reports

| # | Check | Req. | Result | Note |
|---|---|---|---|---|
| 11 | The board shows the pipeline with totals; a card moves by dragging and with the "Move … to" list | FR-OPP-03, NFR-10 | | |
| 12 | Closing as lost asks for a reason; a manager reopens a closed opportunity | FR-OPP-05 | | |
| 13 | Stale opportunities are marked (threshold under Settings) | FR-OPP-06 | | |
| 14 | Activities and tasks on records; My tasks shows overdue tasks first | FR-ACT-01..03 | | |
| 15 | The dashboard and the win/loss report match what the team expects; every list exports to Excel | FR-REP-01..03 | | |
| 16 | An Excel tracker is imported with a preview of problems, and a batch is rolled back | FR-IMP-01 | | |

## Integrations (with the teams; `docs/integration-readiness.md`)

| # | Check | Req. | Result | Note |
|---|---|---|---|---|
| 17 | Each of Conclusion, ERP and Billing completes its checklist in staging | FR-INT-01..12 | | |
| 18 | The delivery log shows webhook attempts; a failed delivery can be redelivered; the banner warns about failures | FR-INT-08, 12 | | |

## AI assistant (only after open question 1 is answered and credits are in place)

| # | Check | Req. | Result | Note |
|---|---|---|---|---|
| 19 | Questions in Bulgarian and English about the team's own pipeline get correct answers with links | FR-AI-02, 06 | | |
| 20 | On an opportunity, "Draft a follow-up email" gives a usable draft; "Save as note" stores the edited text | FR-AI-03, 04 | | |
| 21 | The live evaluation (`docs/assistant-eval.md`) passes with the production model | FR-AI-02 | Developer run 2026-11-18: 20/20 | |

## Administration, privacy and operations

| # | Check | Req. | Result | Note |
|---|---|---|---|---|
| 22 | The audit log shows changes, sign-ins and exports, with filters | FR-ADM-03 | | |
| 23 | A contact's personal data is exported, and the contact is anonymized | FR-ADM-04 | | |
| 24 | Nightly backups appear in the backup directory; the restore drill is repeated on the production server | NFR-07 | | |
| 25 | Pages respond quickly with real data volumes (lists and search under half a second) | NFR-01 | | |
| 26 | The open items in `docs/security/asvs-l1.md` are decided | NFR-04 | | |

## Sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| Owner | | | Accept / accept with listed items / not accepted |

On acceptance the release is tagged `v1.0.0` (`docs/release-notes.md`).
