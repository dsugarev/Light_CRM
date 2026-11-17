"""Global quick search (API spec section 12) as a registry of per-type providers.

Each module registers a provider for its record type at start-up (app.main), so
search spans modules without core or lower modules importing higher ones
(ADR 0018). Results are capped per type.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import AccessLevel
from app.core.auth import endpoint
from app.core.db import DbSession
from app.core.text import search_terms

RESULTS_PER_TYPE = 5
SearchType = Literal["organization", "contact", "lead", "opportunity"]


class SearchHit(BaseModel):
    type: SearchType
    id: UUID
    label: str
    detail: str | None


class SearchResults(BaseModel):
    items: list[SearchHit]


Provider = Callable[[AsyncSession, list[list[str]], int], Awaitable[list[SearchHit]]]


@dataclass(frozen=True, slots=True)
class SearchProvider:
    type: SearchType
    search: Provider


router = APIRouter(prefix="/search", tags=["search"])


@router.get(
    "",
    summary="Quick search across organizations, contacts, leads, opportunities; 5 per type",
    **endpoint(AccessLevel.SIGNED_IN, scope="organizations:read"),
)
async def search(
    request: Request,
    session: DbSession,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    types: Annotated[list[SearchType] | None, Query()] = None,
) -> SearchResults:
    providers: Mapping[str, SearchProvider] = request.app.state.search_providers
    wanted = [t for t in providers if types is None or t in types]
    terms = search_terms(q)
    hits: list[SearchHit] = []
    for name in wanted:
        hits += await providers[name].search(session, terms, RESULTS_PER_TYPE)
    return SearchResults(items=hits)
