# Light CRM — User manuals

Manuals for people who are new to Light CRM. There is **one manual per role**, because each role sees different menus and buttons. Read the manual for your own role. Your role is shown under **your name → My profile → Role**.

| Your role | Typical person | Manual | PDF |
|---|---|---|---|
| **Sales Rep** | Account manager or seller | [Manual for Sales Reps](sales-rep.md) | [PDF](pdf/light-crm-manual-sales-rep.pdf) |
| **Sales Manager** | Team lead | [Manual for Sales Managers](sales-manager.md) | [PDF](pdf/light-crm-manual-sales-manager.pdf) |
| **Admin** | CRM administrator | [Manual for Admins](admin.md) | [PDF](pdf/light-crm-manual-admin.pdf) |
| **Viewer** | Read-only stakeholder | [Manual for Viewers](viewer.md) | [PDF](pdf/light-crm-manual-viewer.pdf) |

Connected applications (ERP, Billing, Conclusion) are not people and don't use the screens. Their teams use the [integration guide](../integration-guide.md).

## What each role can do

| | Viewer | Sales Rep | Sales Manager | Admin |
|---|:-:|:-:|:-:|:-:|
| See all organizations, contacts, leads, opportunities, dashboards and reports | ✓ | ✓ | ✓ | ✓ |
| Search, use the AI assistant | ✓ | ✓ | ✓ | ✓ |
| Export lists to Excel or CSV | | own records | ✓ | ✓ |
| Create records; log activities and tasks | | ✓ | ✓ | ✓ |
| Change and close **own** records; take over open records | | ✓ | ✓ | ✓ |
| Change and close **any** record; reassign owners | | | ✓ | ✓ |
| Reopen closed deals and disqualified leads; restore archived records | | | ✓ | ✓ |
| Import from Excel | | | ✓ | ✓ |
| Users, settings, lists, stages, audit log, roll back imports, GDPR tools, integrations | | | | ✓ |

The screens hide what a role can't do, and the server checks every action again.

## Conventions used in the manuals

- **Bold** is a button, menu or field name, exactly as on screen. *Italic* is text you type.
- Each chapter starts with a **user story** ("As a …, I want … so that …"), followed by numbered steps and a captioned screenshot. An orange frame marks the control a step is about.
- The screenshots show the English interface. Every screen also exists in Bulgarian.
- The people and companies in the screenshots (Elena Petrova, Sunrise Foods OOD and others) are **fictional**.
- Each manual ends with **troubleshooting**, a **glossary** and a one-page **quick reference**.

## Related documents

- [User guide (short), English](../user-guide.en.md) · [Bulgarian](../user-guide.bg.md): a one-page overview for all roles.
- [Import format](../import-format.md): the columns of the import files, with [samples](../import-samples/).
- [Operations guide](../operations-guide.md): installation, backup and configuration, for IT.
- [Integration guide](../integration-guide.md): the API for the ERP, Billing and Conclusion teams.

---

## Keeping the manuals current (for maintainers)

The manuals describe **Release 1 (November 2026)**. Update them in the same change as any user-facing change. Changes that need an update include a new button, a changed label, a new role permission or a new setting.

**Files**

| Path | Content |
|---|---|
| `sales-rep.md`, `sales-manager.md`, `admin.md`, `viewer.md` | The manuals (Markdown; the source of truth) |
| `images/common/`, `images/<role>/` | Screenshots, 1280 × 800, taken by `frontend/e2e/manual.spec.ts` |
| `pdf/` | PDFs generated from the Markdown |
| `manual.css` | Print style of the PDFs |

**Refresh the screenshots**

The screenshots are taken from a running stack, signed in as four fictional users (one per role) that own a few sample records:

| User | Email | Role |
|---|---|---|
| Nadia Stoyanova | `manual-admin@example.test` | Admin |
| Georgi Dimitrov | `manual-manager@example.test` | Sales Manager |
| Elena Petrova | `manual-rep@example.test` | Sales Rep |
| Ivan Kolev | `manual-viewer@example.test` | Viewer |

Elena's sample records:
- the organization *Sunrise Foods OOD*, with the contact *Petar Nikolov*;
- the opportunities *Fibre for Sunrise Foods HQ* (Qualification), *Cloud PBX for Sunrise Foods* (Prospecting) and *Mobile fleet for Sunrise Foods* (Closed Won);
- the leads *SD-WAN for 12 branches* (New) and *Managed Wi-Fi for Blue Coast Resorts* (Qualified, BANT filled);
- a call and two tasks.

Create the users with **Users → New user** and the records through the screens, on a **local or staging stack, never in production**. Then run:

```bash
# Use the stack with the scripted model for the assistant screenshots
# (COMPOSE_FILE=docker-compose.yml:docker-compose.e2e.yml); without it they are skipped.
cd frontend
MANUAL_PASSWORD='…' pnpm manual:screenshots
```

`images/common/assistant-action.png` (a confirmation card) is taken with the real assistant model on a stack where it is switched on, because the scripted test model does not propose actions; retake it by hand when the card changes.

On the local stack, the manual users' password is in `docs/users.md`. That file is kept out of git and exists only on the maintainer's machine. The script only reads: it opens pages, opens forms without saving them, and takes screenshots. To show only the sample data, it hides records left by automated test runs ("A11y …", "E2E …") **in the browser**. Review the new images before you commit them.

**Rebuild the PDFs** (needs `pandoc`, and Chromium from the frontend's Playwright install):

```bash
scripts/build-manual-pdfs.sh
```
