# ADR 0029: Exports follow the role matrix

Status: Accepted · Date: 2026-11-22 · Release 1 completion

## Context
The requirements' role table (section 4) gives export rights per role:
- **Sales Rep:** "export own data";
- **Sales Manager:** "import and export";
- **Viewer:** "read … no changes". The backend permission set gives Viewers no `data.export`.

Phase 5a built the export endpoints as "Signed-in" (API spec 14), and nothing checked `data.export`. As a result, every signed-in user could export every list they could see. The difference came up while the user manuals were being written. The owner decided on 2026-11-22 that exports follow the requirements.

## Decision
- **Viewers may not export.** Every export endpoint returns `403 permission.denied`, and the export buttons are hidden.
- **A Sales Rep's export holds only the records they own.** The service replaces any `owner_id` filter with the caller. The audit entry's `filters` shows the applied `owner_ids`. The screen says **Your records only** next to the export buttons.
- **Sales Managers and Admins** export what they filtered, as before.
- The rule lives in one policy function, `core.policy.export_owner_ids`. Every export service applies it, including report exports. The routes declare the level "Contributor (rules in service)", so the authorization matrix also covers the route level.
- The audit log export stays Admin-only. GDPR personal-data exports are unchanged (Admin).

## Consequences
- Seeing a record and exporting it are now different rights for Sales Reps: they still see every record (assumption A1).
- Integration clients are not affected; they never had access to exports (API spec 19.3).
- This is a tightening of `/api/v1`, but only for the web application's own export endpoints, which no integrated system can call.
- If visibility is ever restricted (ADR 0028, decision 6), exports inherit that restriction through the same services.
