# ADR 0021: Reports owned by the data's module; one export machinery

Status: Accepted · Date: 2026-11-17 · Phase 5a

## Context
FR-REP-01..03 need aggregate figures over opportunities and leads (pipeline by stage, forecast, conversion, win/loss) and FR-REP-02 needs XLSX/CSV exports of every list with the list's filters. Architecture section 3 places a `reporting` module above `sales`, but module internals (repositories, models) are private (import-linter contracts), so reporting cannot query sales tables directly. Exports must be capped, audited and safe against spreadsheet formula injection (architecture section 7), in English or Bulgarian.

## Decision
- **Report queries live with the data.** `sales.service.reports` computes pipeline, forecast, lead conversion and win/loss from its own repository; `activity` provides the user's open/overdue task counts. The `reporting` module owns the `/reports` routes, the owner/period scope, the dashboard composition and report exports. No module reads another's tables.
- **Definitions** (owner decision, Phase 5): the default period is the current calendar year in Europe/Sofia; conversion rate = leads converted ÷ leads created in the period; win rate = won ÷ (won + lost) among opportunities closed in the period; the forecast and pipeline describe the open pipeline now.
- **Months are grouped with `to_char(date, 'YYYY-MM')`**, not `date_trunc`: on a `date` column `date_trunc` returns a timestamp in the session time zone, which shifted month boundaries by a day (found by the forecast test).
- **One export machinery in `app/core/export.py`**: modules describe columns (`key`, English and Bulgarian header) and a row builder from their response models; `build_export` applies the list statement, filters and sort, counts first (cap 50,000, `422 export.too_many_rows`), converts in batches of 500 through the module's own output function (so exports show exactly what the API shows) and renders XLSX (openpyxl, write-only) or CSV (UTF-8 with BOM). Text starting with `= + - @`, tab or CR is prefixed with `'`. Every export publishes an `<entity>.exported` domain event (audit) with format, row count, columns and filters.
- Embedded summaries used by list outputs (organization names, contact links, lead titles) are fetched in one query per batch instead of one per record, so a 50,000-row export costs a few hundred queries rather than tens of thousands.

## Consequences
- New reports are added in the module that owns the data and exposed through `reporting`; new lists get an export by declaring columns and a row builder.
- Exports are synchronous; above 50,000 rows users narrow the filters. An asynchronous export job would be a later, additive change.
- `openpyxl` (architecture) and its type stubs (`types-openpyxl`, dev only) are dependencies; Recharts (architecture) draws the dashboard, with screen-reader tables carrying the same figures.
