# ADR 0005: Additive-only migrations and separate database roles

Status: Accepted · Date: 2026-11-17 · Phase 0

## Context
R2–R4 must extend R1 without destructive changes (NFR-12, G4). Least privilege for the running application (architecture section 7).

## Decision
- All schema change through Alembic; additive only (new tables, nullable/defaulted columns, indexes). Renames/removals follow expand → migrate → contract across releases, and the contract step needs its own ADR and owner approval. Released migrations are never edited. Every migration has a working downgrade.
- Revision IDs are sequential (`0001`, `0002`, …), file names `NNNN_slug.py`.
- Two roles, created by `deploy/postgres/init-roles.sh`: `crm_migrator` owns the database and schema and runs migrations (DDL); `crm_app` is used by the backend and worker with SELECT/INSERT/UPDATE/DELETE granted through default privileges. Tables needing narrower rights (e.g. `audit_log`: INSERT/SELECT only) revoke them in their migration.
- Tests: every revision is upgraded, downgraded and re-upgraded; the models are compared with the migrated schema (no drift); the application role is shown unable to run DDL.

## Consequences
Schema mistakes are corrected with new migrations, never by editing old ones.
