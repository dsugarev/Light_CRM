# ADR 0016: Industries owned by party; search and duplicates across scripts

Status: Accepted · Date: 2026-11-17 · Phase 2

## Context
Architecture 4.3 lists `industry` with the sales lookup tables, but organisations (party) reference it, and party may not depend on sales (ADR 0001). Users write company and person names in Cyrillic and Latin, and Excel data mixes both (FR-I18N-04, FR-PARTY-01 AC1).

## Decision
- `industry` is a party table. Lead sources and loss/disqualification reasons stay in sales. All lookup tables share `ReferenceItemMixin` and are served by the generic `/reference/{list}` endpoints in `app/core/reference.py`; each module registers its lists (`REFERENCE_LISTS`) at start-up. A value in use cannot be deleted (`409 reference.in_use`).
- `app/core/text.py` provides:
  - `transliterate` / `fold`: official Bulgarian Streamlined System (word-final «-ия» → "-ia"), lower case, accents stripped;
  - `normalize_company_name`: the duplicate key (folded, punctuation and legal forms such as ЕООД/OOD/Ltd removed, Latin spellings aligned with transliterated Bulgarian: c/q→k, w→v, x→ks, ph→f, kh→h), so «Акме ЕООД» = "Acme EOOD";
  - `search_text`: each field stored both as typed (lower case) and folded.
- Duplicates: same registration number or same name key → `409 conflict.duplicate` with `matches` unless `confirm_duplicate`; the duplicate-check endpoint adds trigram-similar names (`pg_trgm`, `%` operator). Contacts: same email.
- Search: every term must match `search_text` in its typed or folded form with `ILIKE`, backed by trigram GIN indexes. Full-text search (`tsvector`) is not used: partial matches over short names are what users need, and trigram indexes serve them. It can be added later if long-text search is required.
- A wrong EIK checksum is a warning (`warnings[]` in the response), not an error, so imported data with typos is accepted and visibly flagged.

## Consequences
- Phonetic alignment can join names that differ (e.g. a company truly spelled with "C" and another with "K"); this only produces a warning the user can override.
- Changing normalisation rules later requires recomputing `name_normalized` and `search_text` in a data migration.
