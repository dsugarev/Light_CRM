# Notes before the business presentation (2026-11-22)

The local app at https://localhost is ready to present. It holds only the fictional sample data from the user manuals.

## Cleanup of the local database

- **Backup first.** The full database was saved to `backups/before-demo-cleanup-20261122-2237.dump`, which is not in git. `scripts/restore.sh backups/before-demo-cleanup-20261122-2237.dump` brings it back.
- **Kept:**
  - the four demo accounts: Nadia Stoyanova (Admin), Georgi Dimitrov (Sales Manager), Elena Petrova (Sales Rep) and Ivan Kolev (Viewer);
  - Elena's sample data:
    - Sunrise Foods OOD, with its contact Petar Nikolov;
    - 3 deals: Fibre for Sunrise Foods HQ, Cloud PBX for Sunrise Foods, and Mobile fleet for Sunrise Foods (won);
    - 2 leads: SD-WAN for 12 branches, and Managed Wi-Fi for Blue Coast Resorts;
    - a call and 2 tasks;
  - the original lists, pipeline stages and settings, which match a fresh installation;
  - the 91 audit entries about the kept users and records.
- **Removed:** everything the automated tests had left. That was about 16,800 organizations, 20,600 leads, about 2,000 test and service users, test integration clients, imports, chats and sessions. One assistant test task ("Call MR Z") went too.
- **Checked afterwards:**
  - all four accounts sign in, and the main screens and the dashboard load;
  - the live assistant answers "How many users are there?" correctly: 4, one per role.
- **End-to-end test accounts are gone too.** The end-to-end tests need their admin accounts back before they run again; `docs/users.md` explains how to recreate them. The tests add their own data again, so clean up before the next presentation.

## Readiness review

- **Environment.** The presenter notes pointed to the staging stack (https://localhost:8443). Staging runs an older version, without assistant actions, model choice or a working assistant. The notes now say to demo on the local app.
- **Demo accounts.** They are ready. The password is in `docs/users.md`, which exists only on the demo machine and is never committed (it is in `.gitignore`). Sign in once before the session, in separate browser profiles if you will switch roles.
- **Demo script.** Its first step would have created a second identical "SD-WAN for 12 branches" lead next to the sample one. The demo lead is now *Fibre backup for 3 hotels* for Riverside Hotels AD. The rest of the script works on the cleaned data.
- **Assistant:**
  - The free model (NVIDIA Nemotron 3 Ultra) answers in about 10–30 seconds.
  - It allows each person about 9 answers a day under the current token limit.
  - For a snappier live demo, Nadia can choose **gpt-oss-120b** in **Settings** (1–2 seconds per answer) and switch back afterwards.
  - If the network fails, the assistant says "not available right now"; show slide 10 instead. The rest of the CRM is unaffected.
- **Questions to show the assistant:**
  - *Which of my deals close this month?*
  - *Summarize the history with Sunrise Foods*
  - *Create a task due tomorrow to call Petar Nikolov about the fibre offer*, which shows the confirmation card;
  - as Nadia: *How many users are there?*
- **Q&A.** The prepared answer to "Does the assistant send data outside?" said the provider was approved, which isn't true for the free default. It now gives the honest answer: the free provider may keep prompts, which is fine for the fictional demo data. Before real customer data is used, the data protection officer must approve it, or the Admin switches to gpt-oss-120b, whose data flow is already approved.
- **Deck.** `docs/light-crm-introduction.pptx` is current; slide 10 already shows the confirmation cards.

## Limitations

- **Thin data on screen.** The dashboard, board and reports show only 3 deals. That is enough for the 5-minute demo, which builds its own lead and deal. Fuller pipeline and forecast figures would need a small set of fictional deals for the other users.
- **Free model and data protection.** The default model's provider may keep prompts. Get the DPO's approval before the assistant is used with real customer data.

## Pull requests

- **PR #30** (merged): the Admin chooses the assistant's model from gpt-oss-120b, the free Nemotron and Gemini.
- **PR #31** (merged): the assistant reads users, settings, lists and the team's tasks (ADR 0032).
- **PR #32** (open): https://github.com/dsugarev/Light_CRM/pull/32 contains:
  - the free model as the default (migration `0014`);
  - the updated manuals, screenshots and presenter notes;
  - the corrected chat text, which still called the assistant read-only;
  - these notes.

  The local app already runs this version. Merge PR #32 so that `main` matches what is presented.

## Related documents

- `docs/presenter_notes.md`: the talk, the demo script and the prepared questions
- `docs/users.md`: the demo accounts and password (local only, not in git)
- `docs/manual/`: the user manuals per role, with PDFs
- `docs/assistant-eval.md`: the live evaluation of the three models (runs 6 and 7)
