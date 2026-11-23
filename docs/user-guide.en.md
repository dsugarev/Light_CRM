# Light CRM: user guide

A short guide for the Commercial team. The application is in English and Bulgarian: change the language under **My profile** (your name, top right) or with the language switch.

New to Light CRM? The step-by-step [manual for your role](manual/README.md) has screenshots for every task.

## Signing in

Open the address you were given and sign in with your work email and password. After five wrong attempts the account is locked for 15 minutes. **Forgot your password?** sends a reset link if email is set up; otherwise ask an Admin for a link.

**Two-factor sign-in** (recommended; it can be required for Admins): **My profile → Two-factor sign-in → Set up two-factor sign-in**. Scan the QR code with an authenticator app (Microsoft Authenticator, Google Authenticator and similar), enter the 6-digit code, and keep the ten recovery codes somewhere safe. From then on, after your password you enter the current code from the app, or one recovery code if you don't have your phone.

## Finding your way

| Menu | What is there |
|---|---|
| **Home** | Your dashboard: pipeline by stage, forecast, lead conversion, wins and losses, your open and overdue tasks. Click a figure's card to open the list behind it |
| **Organizations**, **Contacts** | Customers and prospects, and the people there. A duplicate warning appears when an organization with the same name or registration number exists |
| **Leads** | Unqualified prospects: capture, **Mark as contacted**, qualify with BANT (budget, authority, need, timeline), **Qualify**, **Convert** into an opportunity, or **Disqualify** with a reason |
| **Opportunities**, **Board** | Deals with amount, stage and expected close date. On the board, drag a card to another stage, or use the card's **Move … to** list. On an opportunity's page, the **sales path** across the top shows the passed, current and next stages; click a stage to move the deal there. Closing as lost asks for a reason |
| **My tasks** | Tasks assigned to you, overdue first |
| **Reports** | Win/loss report; every list can be exported to Excel or CSV |
| **Search** (top bar) | Finds organizations, contacts, leads and opportunities in Cyrillic or Latin |

In any list, click anywhere on a row to open the record (Ctrl-click or Cmd-click opens it in a new tab).

Every record has a **timeline** with its notes, calls, meetings, emails and tasks and its history of changes. Log an activity from the record's page.

Sales Reps change their own records; Sales Managers and Admins change all. Viewers read only.

## The AI assistant

If your Admin has switched it on, the **Assistant** button in the top bar opens a chat on the right. Ask in English or Bulgarian, for example "Which of my opportunities close this month?" or "Draft a follow-up email for this opportunity". On a lead, opportunity or organization page it offers to answer about that record.

- It can also **do things for you**: "Create a task due tomorrow to call Petar for Sunrise Foods", "Move this deal to Negotiation", "Log a call with Petar: he wants a quote". It prepares a **card**; nothing changes until you press **Confirm** (or **Cancel**). It works with your permissions, and every confirmed change is in the audit log as made by you via the assistant. Tasks and other activities always belong to a record: name it, or ask on the record's page.
- It also answers about the team and the set-up: "Which tasks of the team are overdue?", "What open tasks does Ivan have?", "What are our pipeline stages?". Admins can ask "How many users are there?" or "Which AI model do we use?".
- Passwords, API keys, personal-data export or anonymization and imports are done on the screens, not through the assistant.
- Records it mentions are links. **Copy** copies an answer; **Save as note** saves a draft as a note on a record, after you have checked and edited it.
- It can be wrong: check figures before you use them. It says so when the CRM does not hold the answer.
- There is a daily limit per person, shown under the question box.
- The AI model that answers is shown under the question box too. Your Admin chooses it for everyone in **Settings**. The default is a free model (NVIDIA Nemotron 3 Ultra), which takes about 10–30 seconds per answer.

## For Sales Managers and Admins

- **Import** (managers): prepare the file as in the [import format](import-format.md) (samples included), upload it, map the columns, preview the rows with their problems, and import the valid ones. An Admin can roll a batch back.
- **Users**, **Settings**, **Lists**, **Stages**, **Audit log**, **Integrations** (Admins): see the operations guide.
- **Personal data (GDPR)** on a contact's page (Admins): *Export personal data* downloads everything held about the person; *Anonymize contact* removes the person's details for good (type ANONYMIZE to confirm).

## Help

If something fails, tell the Admin what you were doing and the time; the Admin can find it in the logs.
