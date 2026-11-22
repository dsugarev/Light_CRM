# ADR 0030: The assistant proposes actions; the user confirms them

Status: Accepted · Date: 2026-11-22 · Phase 9 (Release 1.1) · Supersedes the read-only rule of ADR 0006

## Context
In Release 1 the assistant could only read (FR-AI-05, ADR 0006). Business users asked it to do things ("Create a task due tomorrow: Call Mr Z") and were told it cannot. The roadmap planned "assistant-proposed actions with user confirmation" for R1.1. On 2026-11-22 the owner asked for all main user actions to be available this way, excluding:
- one-time secrets;
- irreversible personal-data operations;
- imports;
- the user's own security settings.

The risk that made the assistant read-only remains. It reads untrusted CRM text (notes, imported data), so a planted instruction could try to make it change data.

## Decision
1. **The model never changes data.** It gets *proposal* tools. A proposal is validated, stored server-side as an `assistant_action` row, and shown to the user as a card in the chat. Only the user's **Confirm** (`POST /assistant/actions/{id}/confirm`) executes it.
2. **Exactly what was shown runs.** The stored proposal holds:
   - the action;
   - the target record and the `version` it had;
   - the validated request body.

   Confirmation calls the same service function as the REST endpoint, with the confirming user's `Principal`. If the record changed in between, the normal `409 conflict.version_mismatch` applies, and the user asks again.
3. **Permissions are checked twice.** They are checked when proposing, so that no card is offered for something the user cannot do, and again by the service on confirm. Write tools are offered to the model only for roles that can use them (Viewers get only the profile tool; administration tools only reach Admins).
4. **Limits.**
   - At most 5 proposals per answer.
   - A proposal expires after 30 minutes.
   - A proposal can be confirmed or cancelled once; it belongs to its user (others get `404`).
   - Archive, close as lost, deactivate user and delete list value or stage are marked destructive: the card is red and names the record.
5. **Audit.** Actions confirmed through the assistant are audited like any other change, by the confirming user. Their entries carry `details.via = "assistant"`, added by an event-bus wrapper used only during confirmation.
6. **Secrets never reach chats.** A user created through the assistant gets the usual one-time set-password link. It is returned only in the confirm response, shown once in the card, and never stored in `assistant_action` or sent to the model.
7. **Scope.** Allowed:
   - **records:** create, edit, archive and restore organizations, contacts, leads and opportunities;
   - **leads:** mark contacted, save qualification, qualify, disqualify, reopen, convert, assign;
   - **opportunities:** move, close won or lost, reopen, assign;
   - **activities and tasks:** create, edit, complete, reopen, archive;
   - **own profile:** name and language;
   - **administration (Admins):** create, edit, deactivate, activate and unlock users, and sign them out everywhere; settings; add, rename, (de)activate and delete list values and pipeline stages.

   Excluded:
   - password reset links, API keys, webhook secrets and integration-client administration (one-time secrets);
   - GDPR export and anonymization (irreversible, or a personal-data file);
   - imports and rollback (file based);
   - the user's own password, two-factor sign-in and sessions;
   - reordering lists and stages (done on screen);
   - IDs in other systems: they live in the `integration` module, which is the assistant's sibling layer, and the import rules keep the two independent.

## Consequences
- An injected instruction can at most produce a visible card that the user rejects; it can never change data on its own. The live evaluation includes such a case.
- One more table (`assistant_action`, additive migration), two endpoints and one SSE event (`action_proposed`). The REST API for integrations is unchanged.
- The assistant's tool schemas grow. Offering write tools by role keeps the prompt smaller for Viewers and Sales Reps.
- Future write actions are added in one place, the action registry in `assistant/actions.py`, with a test per action.
