# Light CRM introduction: presenter notes

Speaker notes for [`light-crm-introduction.pptx`](light-crm-introduction.pptx), the introduction of Light CRM for business users of the Commercial team. The same notes are in the deck's notes pane; this page is for preparing and rehearsing without PowerPoint.

**Length:** 15 slides, about 22 minutes of talking, then questions and a 5-minute live demo (about 35 minutes in all).  
**Audience:** sales reps, sales managers and colleagues who follow the pipeline (finance, management).  
**Story:** one week of Elena, a fictional account manager, from the first contact with a new customer to a won deal. Every screen shown is a real Light CRM screen with fictional data.

## Before the session

- **The demo environment.** Use the local stack on the demo machine (`scripts/start-mac.sh`, https://localhost). It runs the current version, with the assistant switched on. On 2026-11-22 it was cleaned for the presentation: only the fictional sample data from the manuals is left, and a backup of the previous state is in `backups/`. The staging stack (https://localhost:8443) still runs an older version without assistant actions or model choice, so don't demo there unless it has been rebuilt. Never demo on the production system.
- **Demo accounts.** The four manual users are ready, one per role, with sample data:
  - **Elena Petrova** (Sales Rep) owns *Sunrise Foods OOD* with its contact *Petar Nikolov*, three deals (one won), two leads and two tasks;
  - **Georgi Dimitrov** (Sales Manager);
  - **Nadia Stoyanova** (Admin);
  - **Ivan Kolev** (Viewer).

  Their password is in `docs/users.md`, which exists only on the demo machine. Sign in once before the session, in separate browser profiles if you will switch roles.
- **The assistant.** It is on, and it uses the free NVIDIA Nemotron 3 Ultra by default. Answers take about 10–30 seconds. For a quicker live demo, Nadia can choose **gpt-oss-120b** in **Settings** (1–2 seconds per answer) and switch back afterwards. The free model uses about 20,000 tokens per answer, so each person gets roughly 9 answers a day under the default limit. Good questions to show:
  - *Which of my deals close this month?*
  - *Summarize the history with Sunrise Foods*
  - *Create a task due tomorrow to call Petar Nikolov about the fibre offer* (shows the confirmation card)
  - as Nadia: *How many users are there?*
- **If the network is down,** the assistant shows "not available right now". Show slide 10 instead; the rest of the CRM is unaffected.
- **Screenshots.** The dashboard figures on slides 1 and 9 come from a test database (very large totals, a 99% win rate). Mention that the data is fictional if anyone asks.
- **Handouts.** Point people to their role's manual: `docs/manual/` (Markdown) and `docs/manual/pdf/` (PDF).

## Running order

| # | Slide | Section | Minutes |
|---|---|---|---|
| 1 | Light CRM | Introduction | 1 |
| 2 | Today, our sales live in many places | Introduction | 1.5 |
| 3 | Light CRM: one shared place, built for our team | Introduction | 1.5 |
| 4 | Meet the people in our story | A week with Light CRM | 1 |
| 5 | Monday 9:00 — A new interest, captured in seconds | A week with Light CRM | 1.5 |
| 6 | Tuesday — Qualify the same way every time, convert in one step | A week with Light CRM | 2 |
| 7 | Wednesday — Move the deal forward with one click | A week with Light CRM | 2 |
| 8 | Every day — Nothing falls through the cracks | A week with Light CRM | 1.5 |
| 9 | Friday — The forecast builds itself | A week with Light CRM | 1.5 |
| 10 | Ask the assistant in plain language | A week with Light CRM | 1.5 |
| 11 | What changes in your week | What it means for you | 2 |
| 12 | The right access for every role | What it means for you | 1.5 |
| 13 | Your data is safe and every change is traceable | What it means for you | 1.5 |
| 14 | Getting started is simple | Getting started | 1.5 |
| 15 | Questions? | Getting started | 1 |

## Introduction

### Slide 1. Light CRM

*About 1 min.*

Welcome, and thank you for your time. In the next twenty minutes I will introduce Light CRM, the new system for our Commercial team. I will not start with features. I will start with a normal week of one of our account managers, Elena, and show how her week changes. Then we look at what each of you can do with your role, how your data is protected, and how we get started. Questions are welcome at any time; we also keep ten minutes at the end. The screen on the right is the real home page of the system, not a mock-up.

### Slide 2. Today, our sales live in many places

*About 1.5 min.*

Let us be honest about how we work today. Leads and deals are tracked in spreadsheets, often one per person, saved on personal drives. The history with a customer sits in someone’s mailbox, so when that person is on holiday or leaves, the history goes with them. Every Friday the managers call around to collect the forecast, and the numbers are out of date by Monday. And when you cover for a colleague, you start almost from zero. None of this is anyone’s fault; it is simply what happens without a shared system. Ask the room: which of these four do you recognise? (Usually all four.)

### Slide 3. Light CRM: one shared place, built for our team

*About 1.5 min.*

So what is Light CRM? It is one shared place for our leads, our opportunities, our customers and everything that happened with them. It was built for our team of about twenty people, so it is deliberately simple. Every screen works in English and in Bulgarian, and you choose your language in your profile. There are four roles: Sales Rep, Sales Manager, Viewer and Admin, so each person sees exactly the buttons they need. It runs on our own servers: customer data does not go to an external cloud CRM. It is connected to ERP, Billing and Conclusion through a secure interface, and it has an AI assistant you can ask about your pipeline. The assistant can also prepare changes, such as a new task or a stage move, but nothing changes until you press Confirm on its card.

## A week with Light CRM

### Slide 4. Meet the people in our story

*About 1 min.*

Our story follows four colleagues. They are fictional, but you will recognise them. Elena is an account manager, a Sales Rep in the system. Georgi leads the sales team. Ivan works in finance and follows the pipeline as a Viewer. Nadia is the CRM administrator. We follow Elena through one week, from the first contact with a new customer to a signed deal, and at each step we look at what Georgi and Ivan see. Everything you will see on the next slides is a real screen of Light CRM with fictional data.

### Slide 5. Monday 9:00 — A new interest, captured in seconds

*About 1.5 min.*

Monday morning. Elena met the IT manager of Riverside Hotels at the telecom expo; they want one network for all twelve hotels. Today this would be a note on her phone or a line in her own spreadsheet. In Light CRM she selects Leads, New lead, types a title and the company name, and saves. That is enough; the rest can come later. The screen on the right shows the safety net when a customer is created, by hand or when a lead is converted: if a company with the same name or registration number already exists, Light CRM shows it with a link first, in Cyrillic or Latin. So we stop creating the same customer three times. From this moment the lead belongs to Elena, and everyone in the team can see it.

### Slide 6. Tuesday — Qualify the same way every time, convert in one step

*About 2 min.*

On Tuesday Elena calls back. She asks the four classic questions, BANT: is there a Budget, is she talking to the person with Authority, is there a real Need, and what is the Timeline. She records each answer with a short note, and Light CRM calculates a score. The team now qualifies every lead the same way, so a score of 88 means the same for everybody. When all four questions are answered, she can mark the lead as qualified and press Convert. One step creates the customer, the contact person and the opportunity, filled in from the lead. Nothing is typed twice, and the history of the lead stays visible on the new opportunity.

### Slide 7. Wednesday — Move the deal forward with one click

*About 2 min.*

Wednesday: Elena sends a proposal. On the opportunity, the sales path at the top shows the stages: what is done, where the deal is now, and what comes next. She clicks Solution and Proposal, and the deal moves. The pipeline board below shows all her deals by stage, like cards on a wall. She can drag a card to the next column, or onto Won or Lost to close it. When a deal is lost, Light CRM asks for the reason, so we learn why we lose. Deals with no activity for two weeks, or with a close date in the past, are flagged Needs attention. Nothing is forgotten quietly. Every stage change is recorded with who and when.

### Slide 8. Every day — Nothing falls through the cracks

*About 1.5 min.*

Every day, after a call or a meeting, Elena adds two lines to the timeline of the deal: what was discussed and what is next. If something must happen later, she creates a task with a due date. My tasks shows her open tasks every morning, overdue first. The real benefit is for the team: when Elena is on holiday and the customer calls, a colleague opens the customer and sees the whole story in order: calls, meetings, emails, tasks, stage changes. No more searching in someone else’s mailbox.

### Slide 9. Friday — The forecast builds itself

*About 1.5 min.*

Friday. Elena closes the Riverside deal as won. Georgi, her manager, does not need to call anyone: he opens his home page and sees the team’s open pipeline, the forecast for the next six months, the conversion rate and the win rate, live. He can switch between the whole team and a single person, and click any figure to open the deals behind it. Ivan in finance sees the same dashboard as a Viewer: he can plan with real numbers, but he cannot change anything. The weighted forecast multiplies each deal by its probability, so it is realistic rather than optimistic. Lists can be exported to Excel when needed.

### Slide 10. Ask the assistant in plain language

*About 1.5 min.*

One more helper: the AI assistant. It opens from the top bar on every page. You ask in plain English or Bulgarian, for example which of my deals close this month, or summarise the history with this customer, or draft a follow-up email for this deal. Answers link to the records they mention. A draft can be copied, or saved as a note on the record after you have checked it. It can also prepare changes for you, for example create a task due tomorrow, log a call, or move a deal. It shows a card with exactly what will happen, and nothing changes until you press Confirm. Two important points: it sees and does only what you are allowed to, and every confirmed change is in the audit log as yours. And like any assistant it can be wrong, so check figures before you send them to a customer. The assistant is switched on by the Admin; there is a daily limit per person.

## What it means for you

### Slide 11. What changes in your week

*About 2 min.*

Here is the same week, summarised as a before and after. Capturing an interest: from a note on your phone to a shared lead in thirty seconds. Qualifying: from personal judgement to the same four questions for everyone. Following up: from reminders in your head to tasks with due dates. Forecasting: from the Friday phone round to a live dashboard. Covering for a colleague: from searching emails to the full timeline. And learning from losses: every lost deal has a reason, and the win/loss report shows the patterns. The honest part: this only works if we all enter our work in Light CRM. That is the one habit we ask you to build.

### Slide 12. The right access for every role

*About 1.5 min.*

Everyone sees all customers and deals: we are one team. What differs is who can change what. Viewers, like Ivan in finance, read everything but change nothing and do not export. Sales Reps create leads and deals and change and close their own; a colleague’s record opens read-only, and they can take it over when agreed. Reps export their own records. Sales Managers can change and reassign any record, reopen a lost deal and import data from Excel. The Admin manages users, settings, the pipeline stages, the audit log and data protection requests. The screens hide what your role cannot do, and the server checks every action again, so access is always right.

### Slide 13. Your data is safe and every change is traceable

*About 1.5 min.*

A few words on safety, because customer data is valuable. Light CRM runs on our own servers, inside the company network. Every change, every sign-in and every export is recorded in the audit log, with the person and the time, and the log cannot be edited. Permissions are checked by the server on every action. You can protect your account with two-factor sign-in, which we recommend for everyone and require for administrators. The data is backed up daily, and restoring has been tested. And for data protection, the Admin can export or anonymize the data of a person on request. One request to you: treat exported Excel files with the same care as the system itself.

## Getting started

### Slide 14. Getting started is simple

*About 1.5 min.*

How do we start? After today’s session, the Admin creates your account and you receive a one-time link. Open it, choose a password of at least twelve characters, and sign in. Each role has its own short manual with screenshots and step-by-step instructions, as Markdown and as PDF. A Sales Rep manual takes about twenty-five minutes to read; the Viewer manual ten. In the first week, please enter your open deals and log your activities, so that from the second week the dashboard is real. If something does not work, the manual has a troubleshooting page, and the Admin can help with accounts and passwords.

### Slide 15. Questions?

*About 1 min.*

To sum up: one shared place for every lead, deal and customer; the same way of qualifying for everyone; tasks so nothing is forgotten; a forecast that builds itself; and the right access for every role. On the right is where we want every deal to end: all stages done, Closed Won. I am happy to take your questions now. After that, I suggest a short live demo in the demo environment: we create a lead, qualify it, convert it and move it across the board in about five minutes. Typical questions to prepare for: Will my existing spreadsheets be imported? Yes, a manager can import Excel files after a preview. Can I use it on a tablet? Yes, it works down to tablet width. Who sees my deals? Everyone in the team can see them; only you and the managers can change them.

## Live demo script (about 5 minutes)

In the demo environment, signed in as the demo Sales Rep (Elena Petrova):

1. **Leads → New lead:** title *Fibre backup for 3 hotels*, company *Riverside Hotels AD*. Create it. (Riverside's *SD-WAN for 12 branches* is already in the sample data, so use a different title.)
2. **Mark as contacted**, then set Budget, Authority, Need and Timeline to *Yes* or *Partial* with short notes. **Save qualification**, and point at the score. Then select **Qualify**.
3. **Convert:** show the three pre-filled sections and select **Convert**. You land on the new opportunity.
4. **Sales path:** click **Solution & Proposal**. Point at the toast and the stage history.
5. **Timeline → Log activity:** a call with two lines, and a task due tomorrow. Open **My tasks**.
6. **Board → Mine:** drag the card to **Negotiation**, then onto **Won**.
7. Sign in as the demo Sales Manager, Georgi (or switch the dashboard to **Everyone**): the deal is already in the figures.

## Questions to prepare for

| Question | Answer |
|---|---|
| Will my existing spreadsheets be imported? | Yes. A Sales Manager or Admin imports Excel or CSV files with a template, a column mapping and a preview of every row before anything is saved. |
| Can I use it on a tablet? | Yes, it works down to tablet width, with larger touch targets. |
| Who can see my deals? | Everyone in the team can see all records. Only you (the owner), the Sales Managers and the Admin can change yours. |
| Can I export to Excel? | Sales Reps export their own records; Sales Managers and Admins export everything; Viewers do not export. |
| Does the AI assistant change data or send it outside? | It changes data only after you confirm its card, and only with your permissions. Your questions, and the CRM data it looks up, go to an external AI provider chosen by the Admin. The current default is a free model whose provider may keep prompts, which is fine for the fictional demo data. Before real customer data is used, the data protection officer approves the provider, or the Admin chooses the paid model (gpt-oss-120b), whose data flow is already approved. The Admin can also switch the assistant off. |
| Is it in Bulgarian? | Every screen is in English and Bulgarian; choose under **My profile → Language**. |
| What happens if I forget my password? | Use **Forgot your password?** on the sign-in page, or ask the Admin for a reset link. |
| Is it connected to ERP and Billing? | Yes, through a secure interface. The connections go live once those teams finish their side. |
