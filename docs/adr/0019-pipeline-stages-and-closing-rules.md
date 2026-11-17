# ADR 0019: Pipeline stages, closing and the stale rule

Status: Accepted · Date: 2026-11-17 · Phase 4a

## Context
FR-OPP-02 asks for configurable stages with a default probability; FR-OPP-03 for a Kanban board; FR-OPP-05 for closing as won or lost with a loss reason and reopening by managers; FR-OPP-06 for flagging stale opportunities. The API specification (section 10) lets `move` reach a lost stage when a loss reason is sent, so the same outcome would have had two paths with different rules. The owner accepted the Phase 4 recommendations on 2026-11-17.

## Decision
- **Stages are rows with a type.** `pipeline_stage` has `stage_type` `open | won | lost` (a check constraint; the list of types is fixed by the domain, not configurable). Names are stored in English and Bulgarian. One default pipeline is seeded in migration 0005 (Prospecting 10, Qualification 25, Solution & Proposal 50, Negotiation 75, Closed Won 100, Closed Lost 0).
- **One path per outcome.** `move` changes between active open stages only; `close` is the only way to won or lost (lost requires a loss reason) and `reopen` (Manager+) the only way back. The board's Won and Lost drop areas call `close`; Lost asks for the reason first. The specification's `move` row was changed accordingly (v0.5).
- **Closing uses the first active stage of the type**, in pipeline order, and that stage's default probability (100 / 0). Every pipeline keeps at least one active stage of each type (`409 stage.required`), so creation, closing and reopening always have a target.
- **Probability** follows the stage default until a user sets it (`probability_overridden`); moves keep an override, closing and reopening reset it, and `PATCH probability: null` returns to the default. Changing a stage's default does not rewrite existing opportunities.
- **Stage history** is its own table (`opportunity_stage_history`) written on create, move, close and reopen, so FR-OPP-02 AC2 does not depend on the audit log's retention or format.
- **Stale** is computed at read time, not stored: open, and either no activity (`last_activity_at`, else `created_at`) for `stale_opportunity_days` (runtime setting, default 14, 1–365) or an expected close date before today in Europe/Sofia. The list filter `is_stale` uses the same expression in SQL.
- **Stage deletion** is refused while any opportunity or history row references the stage (`409 stage.in_use`); deactivation hides it from new moves while existing records keep it.
- **Organisation archive guard**: party exposes `OrganizationArchiveGuard` (ADR 0018 pattern); sales registers one that returns `organization.has_open_opportunities`.

## Consequences
- The board and reports can rely on `stage_type` rather than names, which Admins may change.
- A second pipeline (out of scope in R1) needs only data and a `pipeline_id` choice; the rules are already per pipeline.
- Stale is always current with the setting; there is no job to keep a flag in sync. The query cost is one indexed comparison per row.
- Activities (Phase 4b) update `last_activity_at`, which is what makes an opportunity fresh again.
