# ADR 0032: The assistant reads users, settings, lists and the team's tasks

Status: Accepted · Date: 2026-11-22 · Phase 10 (Release 1.1) · Extends ADR 0006 (read tools) and ADR 0030 (actions with confirmation)

## Context
The assistant could propose user administration, settings changes and list changes (ADR 0030), but it could not *read* any of them. Questions such as "How many users are there in the system?" got the same answer from all three models (ADR 0031): "I don't have a tool to query the users". The model was right: no tool existed. Its only task tool was `my_tasks`, so a manager could not ask about a colleague's or the team's overdue tasks either.

The owner asked for the assistant to handle the most common read and write tasks in the CRM.

## Decision
1. **New reading tools, with the same access as the screens:**
   - `list_users`:
     - **Admins** get the total, counts by status (active, locked, deactivated) and active users by role, plus each user's name, role, status and last sign-in date. This is what Admin → Users shows.
     - **Other roles** get the number of active colleagues and their names, as the owner and assignee pickers show them.
   - `get_settings`: **Admins only.** It returns the values on Admin → Settings, the AI model in use and the models that can be chosen. Other roles get `not_allowed_for_role`.
   - `list_values`: **everyone.** It returns the pipeline stages (with type and default probability) and the configurable lists (industries, lead sources, disqualification and loss reasons), as the forms offer them. Admins may also ask for inactive values.
2. **`list_activities` gains filters:** `owner_name`, `assignee_name`, `open_tasks_only`, `overdue_only`, `due_from`/`due_to` and `occurred_from`/`occurred_to`. The activity API already allows every signed-in user to list everyone's activities with these filters.
3. **What never reaches the model:**
   - email addresses;
   - sign-in secrets, sessions, API keys and two-factor details;
   - the audit log.

   The only sign-in detail sent is the date of an Admin-visible last sign-in.
4. **Writes stay as in ADR 0030:** proposals that the user confirms, checked against the user's permissions. The evaluation now also covers creating a lead, closing a deal as won, reassigning a deal, logging a call in Bulgarian and deactivating a user.

## Consequences
- The data sent to the model provider now includes colleagues' names and, for Admins, their roles and account status. This is internal staff data, not customer data, and it follows the data flow already approved in ADR 0028 and ADR 0031.
- Every model in the catalog is evaluated on the new cases (`docs/assistant-eval.md`, run 7).
