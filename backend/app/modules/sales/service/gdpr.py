"""The sales module's part of the GDPR tools (FR-ADM-04), registered with party."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import DomainEvent
from app.modules.party.service import AnonymizeContext, DataSubject
from app.modules.sales import repository
from app.modules.sales.service.leads import _search_text as lead_search_text


async def personal_data(session: AsyncSession, subject: DataSubject) -> Mapping[str, Any]:
    leads = await repository.leads_of_person(session, subject.contact_id, subject.email)
    opportunities = await repository.opportunities_of_contact(session, subject.contact_id)
    return {
        "leads": [
            {
                "id": str(lead.id),
                "title": lead.title,
                "company_name": lead.company_name,
                "contact_name": lead.contact_name,
                "email": lead.email,
                "phone": lead.phone,
                "status": lead.status,
                "created_at": lead.created_at.isoformat(),
            }
            for lead in leads
        ],
        "opportunities_as_primary_contact": [
            {"id": str(opp.id), "name": opp.name, "created_at": opp.created_at.isoformat()}
            for opp in opportunities
        ],
    }


async def anonymize(ctx: AnonymizeContext, subject: DataSubject) -> None:
    """Clear the person fields of leads linked to the contact or with its email. The
    leads stay (commercial history); the audit entry names the reason, not the values."""
    for lead in await repository.leads_of_person(
        ctx.session, subject.contact_id, subject.email, for_update=True
    ):
        if lead.contact_name is None and lead.email is None and lead.phone is None:
            continue
        lead.contact_name = None
        lead.email = None
        lead.phone = None
        lead.search_text = lead_search_text(lead)
        lead.version += 1
        await ctx.events.publish(
            ctx.session,
            DomainEvent(
                action="lead.updated",
                entity_type="lead",
                entity_id=lead.id,
                actor=ctx.principal,
                occurred_at=ctx.now,
                details={"reason": "contact_anonymized"},
            ),
        )
