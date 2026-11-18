"""Demo and performance data (NFR-01): `python -m app.cli seed-demo`.

Inserts fictional organisations, contacts, leads and opportunities in bulk, owned
by the existing active Admins, Sales Managers and Sales Reps. It is an operator
tool for test and demo environments: it refuses to run in production, writes no
audit entries and is deterministic for a given `--seed`. No real customer data.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.core.text import normalize_company_name, search_text
from app.modules.identity.models import Role, User
from app.modules.party.models import Contact, Organization
from app.modules.sales.models import Lead, Opportunity, Pipeline

CHUNK = 1000
_BASES = (
    "Алфа", "Бета", "Гама", "Делта", "Вега", "Сириус", "Орион", "Пулсар", "Меридиан", "Хоризонт",
    "North", "Blue", "Granite", "Summit", "Harbor", "Cedar", "Atlas", "Nova", "Vertex", "Delta",
)  # fmt: skip
_WORDS = (
    "Мрежи", "Системи", "Логистик", "Комерс", "Енерджи", "Строй", "Трейд", "Медия", "Консулт",
    "Networks", "Systems", "Logistics", "Retail", "Energy", "Foods", "Media", "Labs", "Group",
)  # fmt: skip
_FORMS = ("ЕООД", "ООД", "АД", "ЕАД", "EOOD", "OOD", "AD")
_CITIES = ("София", "Пловдив", "Варна", "Бургас", "Русе", "Стара Загора", "Плевен", "Sofia")
_FIRST = ("Мария", "Иван", "Елена", "Георги", "Десислава", "Николай", "Anna", "Peter", "Sofia")
_LAST = ("Иванова", "Петров", "Георгиева", "Димитров", "Стоянова", "Колев", "Smith", "Novak")
_DEALS = ("Fibre for branches", "Cloud PBX", "SD-WAN", "Mobile fleet", "Data centre racks",
          "Оптична свързаност", "IoT пилот", "Колокация", "Резервна свързаност")  # fmt: skip
_LEAD_STATUSES = ("new", "new", "contacted", "contacted", "qualified", "disqualified")


@dataclass(frozen=True, slots=True)
class Counts:
    organizations: int = 10_000
    contacts: int = 10_000
    leads: int = 20_000
    opportunities: int = 5_000


async def _owners(session: AsyncSession) -> list[UUID]:
    statement = (
        select(User.id)
        .join(Role, Role.id == User.role_id)
        .where(
            User.is_active.is_(True),
            User.user_type == "human",
            Role.code.in_(("admin", "sales_manager", "sales_rep")),
        )
    )
    return list((await session.execute(statement)).scalars())


async def _insert(session: AsyncSession, model: Any, rows: Sequence[dict[str, Any]]) -> None:
    for start in range(0, len(rows), CHUNK):
        await session.execute(insert(model), list(rows[start : start + CHUNK]))


def _company(rng: random.Random, index: int) -> str:
    return f"{rng.choice(_BASES)} {rng.choice(_WORDS)} {index} {rng.choice(_FORMS)}"


async def seed(session: AsyncSession, counts: Counts, *, seed: int = 1) -> dict[str, int]:
    """Insert the requested volumes; returns what was created."""
    rng = random.Random(seed)  # noqa: S311 - demo data, not security
    owners = await _owners(session)
    if not owners:
        raise RuntimeError("No active Admin, Sales Manager or Sales Rep to own the records")
    pipeline = (
        await session.execute(select(Pipeline).where(Pipeline.is_default.is_(True)))
    ).scalar_one()
    open_stages = [s for s in pipeline.stages if s.is_active and s.stage_type == "open"]
    now = datetime.now(UTC)
    today = now.date()

    organizations = []
    for i in range(counts.organizations):
        name = _company(rng, i)
        city = rng.choice(_CITIES)
        organizations.append(
            {
                "id": new_id(), "name": name, "name_normalized": normalize_company_name(name),
                "city": city, "country": "BG", "owner_id": rng.choice(owners),
                "search_text": search_text(name, city),
            }
        )  # fmt: skip
    await _insert(session, Organization, organizations)

    contacts = []
    for _ in range(counts.contacts):
        first, last = rng.choice(_FIRST), rng.choice(_LAST)
        org = rng.choice(organizations)
        email = f"{new_id().hex[:12]}@example.test"
        contacts.append(
            {
                "id": new_id(), "first_name": first, "last_name": last, "email": email,
                "organization_id": org["id"], "search_text": search_text(first, last, email),
            }
        )  # fmt: skip
    await _insert(session, Contact, contacts)

    leads = []
    for i in range(counts.leads):
        title = f"{rng.choice(_DEALS)} {i}"
        company = _company(rng, counts.organizations + i)
        status = rng.choice(_LEAD_STATUSES)
        leads.append(
            {
                "id": new_id(), "title": title, "company_name": company, "status": status,
                "owner_id": rng.choice(owners), "currency": "EUR",
                "estimated_value": Decimal(rng.randrange(1_000, 200_000)),
                "bant_budget": "unknown", "bant_authority": "unknown", "bant_need": "unknown",
                "bant_timeline": "unknown", "fits_target_profile": False, "qualification_score": 0,
                "disqualified_at": now if status == "disqualified" else None,
                "search_text": search_text(title, company),
            }
        )  # fmt: skip
    await _insert(session, Lead, leads)

    opportunities = []
    for i in range(counts.opportunities):
        stage = rng.choice(open_stages)
        org = rng.choice(organizations)
        name = f"{rng.choice(_DEALS)} {i}"
        close: date = today + timedelta(days=rng.randrange(-30, 365))
        opportunities.append(
            {
                "id": new_id(), "name": name, "organization_id": org["id"],
                "owner_id": rng.choice(owners), "pipeline_id": pipeline.id, "stage_id": stage.id,
                "amount": Decimal(rng.randrange(1_000, 500_000)), "currency": "EUR",
                "probability": stage.default_probability, "expected_close_date": close,
                "search_text": search_text(name, str(org["name"])),
            }
        )  # fmt: skip
    await _insert(session, Opportunity, opportunities)
    await session.commit()
    return {
        "organizations": len(organizations),
        "contacts": len(contacts),
        "leads": len(leads),
        "opportunities": len(opportunities),
    }
