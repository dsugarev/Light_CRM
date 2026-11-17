# ADR 0023: Import through the owning modules' services, with rows kept for preview and rollback

Status: Accepted · Date: 2026-11-17 · Phase 5b

## Context
FR-IMP-01 needs an upload → mapping → validation preview → commit flow for organizations, contacts, leads and opportunities, all-or-nothing per file unless invalid rows are skipped (AC2), duplicates by the FR-PARTY-01 rules that can be skipped or updated (AC3), and a batch tag with Admin rollback (AC4). Records must obey the same rules as when created in the UI, and module internals are private (ADR 0001, import-linter). Owner decisions (Phase 5): organizations are looked up by EIK, then by name in either script; stages by English or Bulgarian name; owners by email; CSV encoding and delimiter are detected; limits 10 MB and 20,000 rows; uploaded rows are kept in the database, not on disk, for at most 7 days.

## Decision
- **Adapters, not copies.** `dataimport/adapters.py` has one adapter per record type that builds the owning module's create schema (`OrganizationCreate`, `ContactCreate`, `LeadCreate`, `OpportunityCreate`) from the mapped values and calls public functions: `party.import_create_organization`, `party.import_update` / `import_restore`, `sales.import_create_lead`, `sales.opportunities.create_opportunity(commit=False, import_batch_id=…)`, archive functions, lookups (`core.reference.find_item`, `identity.owner_id_by_email`, `party.find_organization`, `sales.links.find_open_stage`) and duplicate checks. Validation errors are the schemas' own codes, mapped back to import field names.
- **Rows in the database.** `import_batch` holds the state machine, mapping and counts; `import_row` holds each row's uploaded values (`raw`, deleted at commit), outcome and errors, and after commit the record ID, the previous values of updated records (`before`) and the record's `updated_at` right after the commit (`stamp`). The worker deletes uncommitted batches after 7 days.
- **One transaction per commit.** Creations and updates run in the request's session without intermediate commits; any failure rolls everything back (AC2). Validation is repeated per row at commit time, so a list value retired between validation and commit fails the whole commit instead of writing partial data.
- **Rollback by stamp.** A record whose `updated_at` differs from its stamp was changed after the import and is kept and reported; otherwise created records are archived through their module (so guards such as "organization has open opportunities" apply) and updated ones get `before` back.
- **`import_batch_id` on all four imported tables.** Architecture section 4 lists the column on `lead` and `opportunity`; it is added to `organization` and `contact` as well, because AC4 requires every imported record to be tagged (additive change, migration 0007).
- `python-multipart` 0.0.33 (owner approval) handles uploads; `openpyxl` reads XLSX in read-only mode with cached values, so formulas never run.

## Consequences
- An imported record is indistinguishable from one created in the UI (same validation, audit entries, timeline events), plus its batch tag.
- Large commits are synchronous: 5,000 organizations commit in about 7 seconds on the developer machine (Phase 5b record), so 20,000 rows take about half a minute. An asynchronous job would be an additive change if needed.
- Rollback processes records one by one through the modules' archive functions, which commit individually; the per-row result is stored, so a partial rollback is visible.
