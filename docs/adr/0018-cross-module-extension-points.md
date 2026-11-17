# ADR 0018: Cross-module extension points (search, organisation figures, reference lists)

Status: Accepted · Date: 2026-11-17 · Phase 3

## Context
Module dependencies point one way: `sales → party → identity` (ADR 0001). Yet lower modules present data owned by higher ones: the organisation 360 view shows open leads (and, from Phase 4, opportunities and pipeline value), global search spans organisations, contacts, leads and opportunities, and `/reference/{list}` serves lists owned by several modules.

## Decision
Lower layers define small extension points; higher modules register with them in `app.main` at start-up. No lower module imports a higher one.

- **Search** (`app/core/search.py`): `SearchProvider(type, search)`; party registers `organization` and `contact`, sales registers `lead` (opportunity in Phase 4). `GET /search` runs the providers for the requested types, five results each.
- **Organisation figures** (`party.service.OrganizationStats`): callables returning partial counts, merged into `counts` of `GET /organizations/{id}`. Sales registers `open_leads` now; Phase 4 adds open opportunities and pipeline value. The same pattern will provide the "archive blocked while open opportunities" guard.
- **Reference lists** (`app/core/reference.py`, ADR 0016): each module registers its `ReferenceList`s.
- Routes that belong to a higher module but live under a lower module's path (e.g. `GET /organizations/{id}/leads`) are declared in the higher module's router.
- Access wording such as "Contributor (rules in service)" is an `AccessLevel` value of its own with the roles of its base level, so the route catalog and matrix match the spec text exactly.

## Consequences
- Adding a module that contributes to search or the 360 view means registering a provider; existing modules stay untouched.
- Providers run inside the request's database session; they must stay cheap (indexed counts and capped queries).
