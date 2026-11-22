"""Assistant actions with confirmation (FR-AI-09, ADR 0030).

The model never changes data. A proposal tool calls one of the `propose_*` builders
below. The builder resolves names to IDs, checks the user's role and ownership, loads the
target record (for its label and `version`), and returns a `Proposal`: the exact service
request, plus the card text in the language of the question. The service stores it.
Only the user's confirmation runs it, through `execute()`, which calls the same service
function as the REST endpoint, with the confirming user's `Principal`.

Adding an action: a builder, an executor in `EXECUTORS`, a title in `TITLES`, a test.
Excluded on purpose (ADR 0030):
- one-time secrets (password reset links, API keys, webhook secrets);
- GDPR operations, imports, the user's own security settings;
- reordering lists and stages;
- IDs in other systems (they live in the integration module).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import reference as reference_lists
from app.core import runtime_settings
from app.core.config import Settings
from app.core.errors import AppError
from app.core.events import DomainEvent, EventBus
from app.core.policy import MANAGER_ROLES, can_edit_owned
from app.core.principal import Principal, RoleCode
from app.core.reference import ReferenceItemCreate, ReferenceItemUpdate, ReferenceList
from app.core.runtime_settings import RuntimeSettingsUpdate
from app.llm import models
from app.modules.activity import service as activity
from app.modules.activity.schemas import ActivityCreate, ActivityUpdate
from app.modules.identity import service as identity
from app.modules.identity.schemas import MeUpdate, UserCreate, UserUpdate
from app.modules.party import service as party
from app.modules.party.schemas import (
    ContactCreate,
    ContactUpdate,
    OrganizationCreate,
    OrganizationUpdate,
)
from app.modules.sales import service as sales
from app.modules.sales.schemas import (
    AssignRequest,
    CloseRequest,
    ConvertRequest,
    DisqualifyRequest,
    LeadCreate,
    LeadUpdate,
    MoveRequest,
    OpportunityCreate,
    OpportunityUpdate,
    ReopenRequest,
    StageCreate,
    StageUpdate,
)

SOFIA = ZoneInfo("Europe/Sofia")
PROPOSAL_TTL = timedelta(minutes=30)
MAX_PROPOSALS_PER_ANSWER = 5
TASK_HOUR = time(9, 0)

Locale = Literal["en", "bg"]
EntityType = Literal["organization", "contact", "lead", "opportunity", "activity"]


class ActionError(Exception):
    """A proposal that cannot be made; the model reads `code` and `extra`."""

    def __init__(self, code: str, **extra: Any) -> None:
        super().__init__(code)
        self.code = code
        self.extra = extra

    def payload(self) -> dict[str, Any]:
        return {"error": self.code, **self.extra}


@dataclass(frozen=True, slots=True)
class Proposal:
    action: str
    details: list[tuple[str, str]]  # (label, value), localized
    request: dict[str, Any]  # JSON-safe; runs exactly as stored
    target_type: str | None = None
    target_id: UUID | None = None
    target_label: str | None = None
    target_version: int | None = None
    destructive: bool = False


@dataclass(slots=True)
class Reader:
    """What a proposal builder needs: reads only, as the user."""

    session: AsyncSession
    events: EventBus
    settings: Settings
    now: datetime
    principal: Principal
    locale: Locale
    reference_lists: Mapping[str, ReferenceList] = field(default_factory=dict)

    def sales(self) -> sales.Context:
        return sales.Context(self.session, self.events, self.settings, self.now)

    def party(self) -> party.Context:
        return party.Context(self.session, self.events, self.settings, self.now)

    def activity(self) -> activity.Context:
        return activity.Context(self.session, self.events, self.settings, self.now)

    def t(self, key: str) -> str:
        en, bg = LABELS.get(key, (key, key))
        return bg if self.locale == "bg" else en


# --- Card text ------------------------------------------------------------------------------

TITLES: dict[str, tuple[str, str]] = {
    "organization.create": ("Create organization", "Създаване на организация"),
    "organization.update": ("Edit organization", "Промяна на организация"),
    "organization.archive": ("Archive organization", "Архивиране на организация"),
    "organization.restore": ("Restore organization", "Възстановяване на организация"),
    "contact.create": ("Create contact", "Създаване на контакт"),
    "contact.update": ("Edit contact", "Промяна на контакт"),
    "contact.archive": ("Archive contact", "Архивиране на контакт"),
    "contact.restore": ("Restore contact", "Възстановяване на контакт"),
    "lead.create": ("Create lead", "Създаване на потенциален клиент"),
    "lead.update": ("Edit lead", "Промяна на потенциален клиент"),
    "lead.archive": ("Archive lead", "Архивиране на потенциален клиент"),
    "lead.restore": ("Restore lead", "Възстановяване на потенциален клиент"),
    "lead.assign": ("Assign lead", "Прехвърляне на потенциален клиент"),
    "lead.mark_contacted": ("Mark lead as contacted", "Отбелязване на контакт"),
    "lead.qualify": ("Qualify lead", "Квалифициране"),
    "lead.disqualify": ("Disqualify lead", "Дисквалифициране"),
    "lead.reopen": ("Reopen lead", "Повторно отваряне"),
    "lead.convert": ("Convert lead to opportunity", "Превръщане във възможност"),
    "opportunity.create": ("Create opportunity", "Създаване на възможност"),
    "opportunity.update": ("Edit opportunity", "Промяна на възможност"),
    "opportunity.archive": ("Archive opportunity", "Архивиране на възможност"),
    "opportunity.restore": ("Restore opportunity", "Възстановяване на възможност"),
    "opportunity.assign": ("Assign opportunity", "Прехвърляне на възможност"),
    "opportunity.move": ("Move opportunity", "Преместване на възможност"),
    "opportunity.close_won": ("Close as won", "Приключване като спечелена"),
    "opportunity.close_lost": ("Close as lost", "Приключване като загубена"),
    "opportunity.reopen": ("Reopen opportunity", "Повторно отваряне на възможност"),
    "activity.create.task": ("Create task", "Създаване на задача"),
    "activity.create.note": ("Log note", "Бележка"),
    "activity.create.call": ("Log call", "Обаждане"),
    "activity.create.meeting": ("Log meeting", "Среща"),
    "activity.create.email": ("Log email", "Имейл"),
    "activity.update": ("Edit activity", "Промяна на активност"),
    "activity.complete": ("Mark task as done", "Задачата е изпълнена"),
    "activity.reopen": ("Reopen task", "Повторно отваряне на задача"),
    "activity.archive": ("Archive activity", "Архивиране на активност"),
    "profile.update": ("Update my profile", "Промяна на моя профил"),
    "user.create": ("Create user", "Създаване на потребител"),
    "user.update": ("Edit user", "Промяна на потребител"),
    "user.deactivate": ("Deactivate user", "Деактивиране на потребител"),
    "user.activate": ("Activate user", "Активиране на потребител"),
    "user.unlock": ("Unlock user", "Отключване на потребител"),
    "user.revoke_sessions": ("Sign user out everywhere", "Изход от всички сесии"),
    "settings.update": ("Change settings", "Промяна на настройките"),
    "reference.add": ("Add list value", "Добавяне на стойност"),
    "reference.update": ("Edit list value", "Промяна на стойност"),
    "reference.delete": ("Delete list value", "Изтриване на стойност"),
    "stage.add": ("Add pipeline stage", "Добавяне на етап"),
    "stage.update": ("Edit pipeline stage", "Промяна на етап"),
    "stage.delete": ("Delete pipeline stage", "Изтриване на етап"),
}

LABELS: dict[str, tuple[str, str]] = {
    "record": ("Record", "Запис"),
    "name": ("Name", "Име"),
    "title": ("Title", "Заглавие"),
    "company": ("Company", "Фирма"),
    "subject": ("Subject", "Тема"),
    "details": ("Details", "Подробности"),
    "due": ("Due", "Краен срок"),
    "when": ("When", "Кога"),
    "assignee": ("Assigned to", "Възложена на"),
    "owner": ("Owner", "Собственик"),
    "new_owner": ("New owner", "Нов собственик"),
    "linked": ("Linked to", "Свързана с"),
    "organization": ("Organization", "Организация"),
    "amount": ("Amount (EUR)", "Сума (EUR)"),
    "close_date": ("Expected close", "Очаквано приключване"),
    "actual_close": ("Close date", "Дата на приключване"),
    "stage": ("Stage", "Етап"),
    "reason": ("Reason", "Причина"),
    "note": ("Note", "Бележка"),
    "competitor": ("Competitor", "Конкурент"),
    "role": ("Role", "Роля"),
    "email": ("Email", "Имейл"),
    "language": ("Language", "Език"),
    "list": ("List", "Списък"),
    "code": ("Code", "Код"),
    "probability": ("Probability (%)", "Вероятност (%)"),
    "type": ("Type", "Тип"),
    "today": ("today", "днес"),
}

ROLE_NAMES = {
    "admin": ("Admin", "Администратор"),
    "sales_manager": ("Sales Manager", "Търговски мениджър"),
    "sales_rep": ("Sales Rep", "Търговски представител"),
    "viewer": ("Viewer", "Наблюдател"),
}


def title_of(action: str, request: Mapping[str, Any], locale: Locale) -> str:
    key = action
    if action == "activity.create":
        key = f"activity.create.{request['body'].get('type', 'note')}"
    en, bg = TITLES.get(key, (action, action))
    return bg if locale == "bg" else en


def _fmt_when(value: datetime | date | None, locale: Locale) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        local = value.astimezone(SOFIA)
        return local.strftime("%d.%m.%Y %H:%M" if locale == "bg" else "%d %b %Y, %H:%M")
    return value.strftime("%d.%m.%Y" if locale == "bg" else "%d %b %Y")


def _money(value: Any) -> str:
    return f"{float(value):,.2f}".replace(",", " ")


# --- Name and record resolution ----------------------------------------------------------------


async def person(r: Reader, name: str) -> tuple[UUID, str]:
    """A colleague by name ('me' is the user); ambiguous or unknown names are errors."""
    if name.strip().casefold() in {"me", "myself", "аз", "мен"}:
        return r.principal.user_id, r.principal.display_name
    found = await identity.people_named(r.session, name)
    exact = [p for p in found if p[1].casefold() == name.strip().casefold()]
    if len(exact) == 1:
        return exact[0]
    if len(found) == 1:
        return found[0]
    if not found:
        raise ActionError("owner_not_found", name=name)
    raise ActionError("ambiguous_person", candidates=[p[1] for p in found])


async def _pipeline(r: Reader) -> Any:
    pipelines = await sales.list_pipelines(r.sales())
    return next((p for p in pipelines if p.is_default), pipelines[0])


async def stage(r: Reader, name: str, types: Sequence[str] = ("open",)) -> tuple[UUID, str]:
    pipeline = await _pipeline(r)
    wanted = name.strip().casefold()
    candidates = [s for s in pipeline.stages if s.is_active and s.stage_type in types]
    for s in candidates:
        if wanted in (s.name_en.casefold(), s.name_bg.casefold()):
            return s.id, s.name_bg if r.locale == "bg" else s.name_en
    raise ActionError("stage_not_found", options=[s.name_en for s in candidates])


async def reference_value(r: Reader, list_name: str, text: str) -> tuple[UUID, str]:
    ref = r.reference_lists.get(list_name)
    if ref is None:
        raise ActionError("list_not_found", options=sorted(r.reference_lists))
    found = await reference_lists.find_item(r.session, ref, text)
    items = await reference_lists.all_items(r.session, ref)
    if found is None:
        raise ActionError("value_not_found", options=[i.name_en for i in items if i.is_active])
    item = next(i for i in items if i.id == found)
    return found, item.name_bg if r.locale == "bg" else item.name_en


def when(value: str | None, *, default_hour: time = TASK_HOUR) -> datetime | None:
    """ISO date or date-time from the model; a bare date means 09:00 in Sofia."""
    if not value:
        return None
    try:
        if len(value.strip()) <= 10:
            return datetime.combine(date.fromisoformat(value.strip()), default_hour, SOFIA)
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as error:
        raise ActionError("invalid_arguments", fields=["date"]) from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=SOFIA)


@dataclass(frozen=True, slots=True)
class Target:
    entity_type: str
    id: UUID
    label: str
    owner_id: UUID | None
    version: int | None
    record: Any


async def load(r: Reader, entity_type: str, entity_id: UUID) -> Target:
    try:
        match entity_type:
            case "organization":
                org = await party.get_organization(r.party(), entity_id)
                return Target(entity_type, org.id, org.name, org.owner.id, None, org)
            case "contact":
                c = await party.get_contact(r.party(), entity_id)
                return Target(entity_type, c.id, c.full_name, c.owner.id, None, c)
            case "lead":
                lead = await sales.get_lead(r.sales(), entity_id)
                return Target(entity_type, lead.id, lead.title, lead.owner.id, lead.version, lead)
            case "opportunity":
                o = await sales.opportunities.get(r.sales(), entity_id)
                return Target(entity_type, o.id, o.name, o.owner.id, o.version, o)
            case "activity":
                a = await activity.get_activity(r.activity(), entity_id)
                return Target(entity_type, a.id, a.subject, a.owner.id, a.version, a)
    except AppError as error:
        raise ActionError("not_found", entity_type=entity_type) from error
    raise ActionError("invalid_arguments", fields=["entity_type"])


# --- Permission pre-checks (the service checks again on confirmation) -------------------------


def need_contributor(r: Reader) -> None:
    if r.principal.role not in (RoleCode.ADMIN, RoleCode.SALES_MANAGER, RoleCode.SALES_REP):
        raise ActionError("permission.denied")


def need_manager(r: Reader) -> None:
    if r.principal.role not in MANAGER_ROLES:
        raise ActionError("permission.denied", hint="Only Sales Managers and Admins may do this")


def need_admin(r: Reader) -> None:
    if r.principal.role is not RoleCode.ADMIN:
        raise ActionError("permission.denied", hint="Only Admins may do this")


def need_owner(r: Reader, target: Target) -> None:
    need_contributor(r)
    if not can_edit_owned(r.principal, target.owner_id):
        raise ActionError("permission.denied", hint="Only the owner or a manager may change it")


def need_task_rights(r: Reader, target: Target) -> None:
    need_contributor(r)
    assignee = getattr(target.record, "assignee", None)
    if can_edit_owned(r.principal, target.owner_id):
        return
    if assignee is not None and assignee.id == r.principal.user_id:
        return
    raise ActionError("permission.denied", hint="Only the owner, the assignee or a manager")


def _validate(model: type[BaseModel], data: Mapping[str, Any]) -> dict[str, Any]:
    # A missing value from the model is "not given", never "clear the field".
    given = {key: value for key, value in data.items() if value is not None}
    try:
        return model.model_validate(given).model_dump(mode="json", exclude_none=True)
    except ValidationError as error:
        fields = [".".join(str(p) for p in e["loc"]) or "arguments" for e in error.errors()]
        raise ActionError("invalid_arguments", fields=fields) from error


def _target_proposal(
    action: str,
    target: Target,
    details: list[tuple[str, str]],
    request: dict[str, Any],
    *,
    destructive: bool = False,
) -> Proposal:
    return Proposal(
        action=action,
        details=details,
        request=request,
        target_type=target.entity_type,
        target_id=target.id,
        target_label=target.label,
        target_version=target.version,
        destructive=destructive,
    )


# --- Builders: creating records ----------------------------------------------------------------


async def propose_activity(
    r: Reader,
    *,
    type: str,
    subject: str,
    body: str | None,
    due: str | None,
    occurred: str | None,
    assignee_name: str | None,
    link: Target | None,
) -> Proposal:
    need_contributor(r)
    data: dict[str, Any] = {"type": type, "subject": subject, "body": body}
    details: list[tuple[str, str]] = [(r.t("subject"), subject)]
    if type == "task":
        due_at = when(due) or datetime.combine(r.now.astimezone(SOFIA).date(), TASK_HOUR, SOFIA)
        data["due_at"] = due_at.isoformat()
        details.append((r.t("due"), _fmt_when(due_at, r.locale)))
        if assignee_name:
            assignee_id, assignee = await person(r, assignee_name)
        else:
            assignee_id, assignee = r.principal.user_id, r.principal.display_name
        data["assignee_id"] = str(assignee_id)
        details.append((r.t("assignee"), assignee))
    else:
        occurred_at = when(occurred)
        if occurred_at:
            data["occurred_at"] = occurred_at.isoformat()
        details.append((r.t("when"), _fmt_when(occurred_at, r.locale) or r.t("today")))
    if body:
        details.append((r.t("details"), body))
    if link is None:
        # FR-ACT-01: every activity belongs to a lead, opportunity, organization or contact.
        raise ActionError(
            "link_required",
            hint="Ask which lead, opportunity, organization or contact it belongs to; "
            "search for it and pass link_type and link_id",
        )
    data[f"{link.entity_type}_id"] = str(link.id)
    details.append((r.t("linked"), link.label))
    request = {"body": _validate(ActivityCreate, data)}
    return Proposal("activity.create", details, request)


async def propose_lead(r: Reader, fields: Mapping[str, Any]) -> Proposal:
    need_contributor(r)
    data = dict(fields)
    details = [
        (r.t("title"), str(data.get("title", ""))),
        (r.t("company"), str(data.get("company_name", ""))),
    ]
    if source := data.pop("source", None):
        data["source_id"], label = await reference_value(r, "lead-sources", str(source))
        details.append(("Source" if r.locale == "en" else "Източник", label))
    if data.get("estimated_value") is not None:
        details.append((r.t("amount"), _money(data["estimated_value"])))
    if owner := data.pop("owner_name", None):
        owner_id, owner_label = await person(r, str(owner))
        data["owner_id"] = str(owner_id)
        details.append((r.t("owner"), owner_label))
    return Proposal("lead.create", details, {"body": _validate(LeadCreate, data)})


async def propose_opportunity(r: Reader, fields: Mapping[str, Any], org: Target) -> Proposal:
    need_contributor(r)
    data = dict(fields)
    data["organization_id"] = str(org.id)
    details = [(r.t("name"), str(data.get("name", ""))), (r.t("organization"), org.label)]
    if stage_name := data.pop("stage", None):
        stage_id, stage_label = await stage(r, str(stage_name))
        data["stage_id"] = str(stage_id)
        details.append((r.t("stage"), stage_label))
    if data.get("amount") is not None:
        details.append((r.t("amount"), _money(data["amount"])))
    if data.get("expected_close_date"):
        details.append((r.t("close_date"), str(data["expected_close_date"])))
    if owner := data.pop("owner_name", None):
        owner_id, owner_label = await person(r, str(owner))
        data["owner_id"] = str(owner_id)
        details.append((r.t("owner"), owner_label))
    return Proposal("opportunity.create", details, {"body": _validate(OpportunityCreate, data)})


async def propose_organization(
    r: Reader, fields: Mapping[str, Any], *, create_anyway: bool
) -> Proposal:
    need_contributor(r)
    data = dict(fields)
    details = [(r.t("name"), str(data.get("name", "")))]
    if industry := data.pop("industry", None):
        data["industry_id"], label = await reference_value(r, "industries", str(industry))
        details.append(("Industry" if r.locale == "en" else "Индустрия", label))
    for key in ("city", "registration_number", "website"):
        if data.get(key):
            details.append((key.replace("_", " ").capitalize(), str(data[key])))
    if not create_anyway:
        matches = await party.duplicate_check(
            r.party(),
            name=str(data.get("name", "")),
            registration_number=data.get("registration_number"),
        )
        found = [m.name for m in getattr(matches, "matches", [])] if matches else []
        if found:
            raise ActionError(
                "possible_duplicates",
                matches=found,
                hint="Tell the user; propose again with create_anyway=true only if they confirm",
            )
    data["confirm_duplicate"] = True
    return Proposal("organization.create", details, {"body": _validate(OrganizationCreate, data)})


async def propose_contact(r: Reader, fields: Mapping[str, Any], org: Target | None) -> Proposal:
    need_contributor(r)
    data = dict(fields)
    details = [(r.t("name"), f"{data.get('first_name', '')} {data.get('last_name', '')}".strip())]
    if data.get("job_title"):
        details.append(("Position" if r.locale == "en" else "Длъжност", str(data["job_title"])))
    if data.get("email"):
        details.append((r.t("email"), str(data["email"])))
    if org is not None:
        data["organization_id"] = str(org.id)
        details.append((r.t("organization"), org.label))
    data["confirm_duplicate"] = True
    return Proposal("contact.create", details, {"body": _validate(ContactCreate, data)})


# --- Builders: changing records ----------------------------------------------------------------

UPDATE_MODELS: dict[str, type[BaseModel]] = {
    "organization": OrganizationUpdate,
    "contact": ContactUpdate,
    "lead": LeadUpdate,
    "opportunity": OpportunityUpdate,
    "activity": ActivityUpdate,
}
NAME_FIELDS = {"industry": ("industries", "industry_id"), "source": ("lead-sources", "source_id")}


async def propose_update(r: Reader, target: Target, changes: Mapping[str, Any]) -> Proposal:
    if target.entity_type == "activity":
        need_task_rights(r, target)
    else:
        need_owner(r, target)
    data = dict(changes)
    if not data:
        raise ActionError("invalid_arguments", fields=["changes"])
    details: list[tuple[str, str]] = [(r.t("record"), target.label)]
    for key, (list_name, id_field) in NAME_FIELDS.items():
        if key in data:
            data[id_field], label = await reference_value(r, list_name, str(data.pop(key)))
            details.append((key.capitalize(), label))
    if "assignee_name" in data:
        assignee_id, assignee = await person(r, str(data.pop("assignee_name")))
        data["assignee_id"] = str(assignee_id)
        details.append((r.t("assignee"), assignee))
    for key in ("due_at", "occurred_at"):
        if data.get(key):
            moment = when(str(data[key]))
            data[key] = moment.isoformat() if moment else None
    for key, value in data.items():
        if key.endswith("_id"):
            continue
        shown = (
            _money(value) if key in {"amount", "estimated_value"} and value is not None else value
        )
        details.append((key.replace("_", " ").capitalize(), str(shown)))
    if target.version is not None:
        data["version"] = target.version
    body = _validate(UPDATE_MODELS[target.entity_type], data)
    return _target_proposal(f"{target.entity_type}.update", target, details, {"body": body})


async def propose_archive_or_restore(r: Reader, target: Target, step: str) -> Proposal:
    if step == "restore":
        need_manager(r)
    elif target.entity_type == "activity":
        need_task_rights(r, target)
    else:
        need_owner(r, target)
    return _target_proposal(
        f"{target.entity_type}.{step}",
        target,
        [(r.t("record"), target.label)],
        {},
        destructive=step == "archive",
    )


async def propose_assign(r: Reader, target: Target, owner_name: str) -> Proposal:
    need_contributor(r)
    owner_id, owner_label = await person(r, owner_name)
    if r.principal.role not in MANAGER_ROLES and owner_id != r.principal.user_id:
        raise ActionError(
            "permission.denied", hint="Sales Reps can only take records over themselves"
        )
    body = {"owner_id": str(owner_id), "version": target.version}
    details = [(r.t("record"), target.label), (r.t("new_owner"), owner_label)]
    return _target_proposal(f"{target.entity_type}.assign", target, details, {"body": body})


async def propose_lead_step(
    r: Reader, target: Target, step: str, *, reason: str | None, note: str | None
) -> Proposal:
    details = [(r.t("record"), target.label)]
    if step == "reopen":
        need_manager(r)
        return _target_proposal("lead.reopen", target, details, {"version": target.version})
    need_owner(r, target)
    if step in {"mark_contacted", "qualify"}:
        return _target_proposal(f"lead.{step}", target, details, {"version": target.version})
    if step == "disqualify":
        if not reason:
            raise ActionError("invalid_arguments", fields=["reason"], hint="A reason is required")
        reason_id, reason_label = await reference_value(r, "disqualification-reasons", reason)
        details.append((r.t("reason"), reason_label))
        if note:
            details.append((r.t("note"), note))
        body = _validate(
            DisqualifyRequest,
            {"reason_id": str(reason_id), "note": note, "version": target.version},
        )
        return _target_proposal(
            "lead.disqualify", target, details, {"body": body}, destructive=True
        )
    if step == "convert":
        preview = await sales.conversion_preview(r.sales(), r.principal, target.id)
        organization: dict[str, Any]
        if preview.organization.linked is not None:
            organization = {"existing_id": str(preview.organization.linked.id)}
            org_label = preview.organization.linked.name
        elif preview.organization.matches:
            raise ActionError(
                "possible_duplicates",
                matches=[m.name for m in preview.organization.matches],
                hint="Converting needs a choice of organization; suggest the Convert page",
            )
        else:
            suggested = preview.organization.suggested
            organization = {"new": {"name": suggested.name, "confirm_duplicate": True}}
            org_label = suggested.name
        contact: dict[str, Any] | None = None
        suggested_contact = getattr(preview.contact, "suggested", None)
        linked_contact = getattr(preview.contact, "linked", None)
        if linked_contact is not None:
            contact = {"existing_id": str(linked_contact.id)}
        elif suggested_contact is not None and not preview.contact.matches:
            contact = {
                "new": {
                    **suggested_contact.model_dump(exclude_none=True),
                    "confirm_duplicate": True,
                }
            }
        opp = preview.opportunity
        body = _validate(
            ConvertRequest,
            {
                "version": target.version,
                "organization": organization,
                "contact": contact,
                "opportunity": {
                    "name": opp.name,
                    "amount": str(opp.amount) if opp.amount is not None else None,
                    "stage_id": str(opp.stage.id),
                },
            },
        )
        details += [(r.t("organization"), org_label), (r.t("name"), opp.name)]
        if opp.amount is not None:
            details.append((r.t("amount"), _money(opp.amount)))
        return _target_proposal("lead.convert", target, details, {"body": body})
    raise ActionError("invalid_arguments", fields=["step"])


async def propose_opportunity_step(
    r: Reader,
    target: Target,
    step: str,
    *,
    stage_name: str | None,
    loss_reason: str | None,
    competitor: str | None,
    close_date: str | None,
) -> Proposal:
    details = [(r.t("record"), target.label)]
    if step == "reopen":
        need_manager(r)
        stage_id, stage_label = await stage(r, stage_name or "Prospecting")
        details.append((r.t("stage"), stage_label))
        body = _validate(ReopenRequest, {"stage_id": str(stage_id), "version": target.version})
        return _target_proposal("opportunity.reopen", target, details, {"body": body})
    need_owner(r, target)
    if step == "move":
        if not stage_name:
            raise ActionError("invalid_arguments", fields=["stage"])
        stage_id, stage_label = await stage(r, stage_name)
        details.append((r.t("stage"), stage_label))
        body = _validate(MoveRequest, {"stage_id": str(stage_id), "version": target.version})
        return _target_proposal("opportunity.move", target, details, {"body": body})
    if step in {"close_won", "close_lost"}:
        data: dict[str, Any] = {
            "outcome": "won" if step == "close_won" else "lost",
            "version": target.version,
        }
        if step == "close_lost":
            if not loss_reason:
                raise ActionError(
                    "invalid_arguments", fields=["loss_reason"], hint="A loss reason is required"
                )
            data["loss_reason_id"], label = await reference_value(r, "loss-reasons", loss_reason)
            details.append((r.t("reason"), label))
            data["loss_reason_id"] = str(data["loss_reason_id"])
        if competitor:
            data["competitor"] = competitor
            details.append((r.t("competitor"), competitor))
        if close_date:
            data["actual_close_date"] = close_date
        details.append((r.t("actual_close"), close_date or r.t("today")))
        body = _validate(CloseRequest, data)
        return _target_proposal(
            f"opportunity.{step}", target, details, {"body": body}, destructive=step == "close_lost"
        )
    raise ActionError("invalid_arguments", fields=["step"])


async def propose_task_step(r: Reader, target: Target, step: str) -> Proposal:
    need_task_rights(r, target)
    if getattr(target.record, "type", None) != "task":
        raise ActionError(
            "invalid_arguments", fields=["activity_id"], hint="Only tasks can be completed"
        )
    return _target_proposal(
        f"activity.{step}", target, [(r.t("subject"), target.label)], {"version": target.version}
    )


async def propose_profile(r: Reader, full_name: str | None, locale: str | None) -> Proposal:
    data = _validate(MeUpdate, {"full_name": full_name, "locale": locale})
    if not data:
        raise ActionError("invalid_arguments", fields=["full_name", "locale"])
    details = []
    if "full_name" in data:
        details.append((r.t("name"), data["full_name"]))
    if "locale" in data:
        details.append((r.t("language"), "English" if data["locale"] == "en" else "Български"))
    return Proposal("profile.update", details, {"body": data})


# --- Builders: administration (Admins) ----------------------------------------------------------


async def _user_target(r: Reader, name_or_email: str) -> tuple[UUID, str]:
    return await person(r, name_or_email)


async def propose_admin(r: Reader, action: str, params: Mapping[str, Any]) -> Proposal:
    need_admin(r)
    p = dict(params)
    if action == "user.create":
        body = _validate(
            UserCreate, {k: p.get(k) for k in ("email", "full_name", "role", "locale")}
        )
        role_en, role_bg = ROLE_NAMES.get(body["role"], (body["role"], body["role"]))
        details = [
            (r.t("name"), body["full_name"]),
            (r.t("email"), body["email"]),
            (r.t("role"), role_bg if r.locale == "bg" else role_en),
        ]
        return Proposal(action, details, {"body": body})
    if action in {
        "user.update",
        "user.deactivate",
        "user.activate",
        "user.unlock",
        "user.revoke_sessions",
    }:
        user_id, label = await _user_target(r, str(p.get("user") or ""))
        details = [(r.t("name"), label)]
        request: dict[str, Any] = {"user_id": str(user_id)}
        if action == "user.update":
            body = _validate(
                UserUpdate, {k: p.get(k) for k in ("email", "full_name", "role", "locale")}
            )
            if not body:
                raise ActionError("invalid_arguments", fields=["changes"])
            for key, value in body.items():
                details.append((key.replace("_", " ").capitalize(), str(value)))
            request["body"] = body
        return Proposal(
            action,
            details,
            request,
            target_type="user",
            target_id=user_id,
            target_label=label,
            destructive=action in {"user.deactivate", "user.revoke_sessions"},
        )
    if action == "settings.update":
        keys = (
            "session_idle_timeout_minutes",
            "session_absolute_timeout_minutes",
            "stale_opportunity_days",
            "mfa_required_for_admins",
            "ai_model",
        )
        body = _validate(RuntimeSettingsUpdate, {k: p.get(k) for k in keys})
        if not body:
            raise ActionError("invalid_arguments", fields=list(keys))
        if "ai_model" in body and models.unavailable_reason(body["ai_model"], r.settings):
            raise ActionError(
                "ai_model_unavailable",
                options=[o.id for o in models.CATALOG if models.available(o, r.settings)],
            )
        details = [(k.replace("_", " ").capitalize(), str(v)) for k, v in body.items()]
        return Proposal(action, details, {"body": body})
    if action.startswith("reference."):
        list_name = str(p.get("list") or "")
        ref = r.reference_lists.get(list_name)
        if ref is None:
            raise ActionError("list_not_found", options=sorted(r.reference_lists))
        details = [(r.t("list"), list_name)]
        if action == "reference.add":
            body = _validate(
                ReferenceItemCreate, {k: p.get(k) for k in ("code", "name_en", "name_bg")}
            )
            details += [
                (r.t("code"), body["code"]),
                (r.t("name"), f"{body['name_en']} / {body['name_bg']}"),
            ]
            return Proposal(action, details, {"list": list_name, "body": body})
        item_id, label = await reference_value(r, list_name, str(p.get("value") or ""))
        details.append((r.t("name"), label))
        request = {"list": list_name, "item_id": str(item_id)}
        if action == "reference.update":
            body = _validate(
                ReferenceItemUpdate, {k: p.get(k) for k in ("name_en", "name_bg", "is_active")}
            )
            if not body:
                raise ActionError("invalid_arguments", fields=["name_en", "name_bg", "is_active"])
            details += [(k.replace("_", " ").capitalize(), str(v)) for k, v in body.items()]
            request["body"] = body
        return Proposal(action, details, request, destructive=action == "reference.delete")
    if action.startswith("stage."):
        pipeline = await _pipeline(r)
        if action == "stage.add":
            body = _validate(
                StageCreate,
                {k: p.get(k) for k in ("name_en", "name_bg", "default_probability", "stage_type")},
            )
            details = [
                (r.t("name"), f"{body['name_en']} / {body['name_bg']}"),
                (r.t("probability"), str(body["default_probability"])),
            ]
            return Proposal(action, details, {"pipeline_id": str(pipeline.id), "body": body})
        stage_id, label = await stage(r, str(p.get("stage") or ""), types=("open", "won", "lost"))
        details = [(r.t("stage"), label)]
        request = {"pipeline_id": str(pipeline.id), "stage_id": str(stage_id)}
        if action == "stage.update":
            body = _validate(
                StageUpdate,
                {k: p.get(k) for k in ("name_en", "name_bg", "default_probability", "is_active")},
            )
            if not body:
                raise ActionError("invalid_arguments", fields=["changes"])
            details += [(k.replace("_", " ").capitalize(), str(v)) for k, v in body.items()]
            request["body"] = body
        return Proposal(action, details, request, destructive=action == "stage.delete")
    raise ActionError("not_allowed", hint="This action is not available through the assistant")


# --- Execution (only after the user's confirmation) ---------------------------------------------


class ViaAssistantBus(EventBus):
    """Publishes through the application's bus, marking every event `via: assistant`, so
    the audit log shows which changes were confirmed in the assistant (ADR 0030)."""

    def __init__(self, inner: EventBus) -> None:
        super().__init__()
        self._inner = inner

    async def publish(self, session: AsyncSession, event: DomainEvent) -> None:
        await self._inner.publish(
            session, replace(event, details={**event.details, "via": "assistant"})
        )


@dataclass(slots=True)
class Executor:
    """Everything the services need, as the REST routes build it."""

    session: AsyncSession
    events: EventBus
    settings: Settings
    now: datetime
    mailer: Any
    ip: str | None
    user_agent: str | None
    external_filter: Any
    organization_stats: Sequence[Any]
    organization_archive_guards: Sequence[Any]
    personal_data_providers: Sequence[Any]
    contact_anonymizers: Sequence[Any]
    reference_lists: Mapping[str, ReferenceList]

    def party(self) -> party.Context:
        return party.Context(
            session=self.session,
            events=self.events,
            settings=self.settings,
            now=self.now,
            organization_stats=self.organization_stats,
            external_filter=self.external_filter,
            organization_archive_guards=self.organization_archive_guards,
            personal_data_providers=self.personal_data_providers,
            contact_anonymizers=self.contact_anonymizers,
        )

    def sales(self) -> sales.Context:
        return sales.Context(
            self.session, self.events, self.settings, self.now, self.external_filter
        )

    def activity(self) -> activity.Context:
        return activity.Context(self.session, self.events, self.settings, self.now)

    def identity(self) -> identity.Context:
        return identity.Context(
            session=self.session,
            events=self.events,
            settings=self.settings,
            mailer=self.mailer,
            now=self.now,
            ip=self.ip,
            user_agent=self.user_agent,
        )


@dataclass(slots=True)
class Outcome:
    entity_type: str | None = None
    entity_id: UUID | None = None
    label: str | None = None
    # Shown once to the user, never stored (a new user's set-password link).
    once: dict[str, Any] | None = None

    def result(self) -> dict[str, Any] | None:
        if self.entity_type is None or self.entity_id is None:
            return None
        return {
            "entity_type": self.entity_type,
            "entity_id": str(self.entity_id),
            "label": self.label or "",
        }


Run = Callable[[Executor, Principal, Any], Awaitable[Outcome]]


def _uid(value: Any) -> UUID:
    return UUID(str(value))


async def _org_create(x: Executor, p: Principal, a: Any) -> Outcome:
    org = await party.create_organization(
        x.party(), p, OrganizationCreate.model_validate(a.request["body"])
    )
    return Outcome("organization", org.id, org.name)


async def _org_update(x: Executor, p: Principal, a: Any) -> Outcome:
    org = await party.update_organization(
        x.party(), p, a.target_id, OrganizationUpdate.model_validate(a.request["body"])
    )
    return Outcome("organization", org.id, org.name)


async def _org_archive(x: Executor, p: Principal, a: Any) -> Outcome:
    await party.archive_organization(x.party(), p, a.target_id)
    return Outcome("organization", a.target_id, a.target_label)


async def _org_restore(x: Executor, p: Principal, a: Any) -> Outcome:
    org = await party.restore_organization(x.party(), p, a.target_id)
    return Outcome("organization", org.id, org.name)


async def _contact_create(x: Executor, p: Principal, a: Any) -> Outcome:
    c = await party.create_contact(x.party(), p, ContactCreate.model_validate(a.request["body"]))
    return Outcome("contact", c.id, c.full_name)


async def _contact_update(x: Executor, p: Principal, a: Any) -> Outcome:
    c = await party.update_contact(
        x.party(), p, a.target_id, ContactUpdate.model_validate(a.request["body"])
    )
    return Outcome("contact", c.id, c.full_name)


async def _contact_archive(x: Executor, p: Principal, a: Any) -> Outcome:
    await party.archive_contact(x.party(), p, a.target_id)
    return Outcome("contact", a.target_id, a.target_label)


async def _contact_restore(x: Executor, p: Principal, a: Any) -> Outcome:
    c = await party.restore_contact(x.party(), p, a.target_id)
    return Outcome("contact", c.id, c.full_name)


async def _lead_create(x: Executor, p: Principal, a: Any) -> Outcome:
    lead = await sales.create_lead(x.sales(), p, LeadCreate.model_validate(a.request["body"]))
    return Outcome("lead", lead.id, lead.title)


async def _lead_update(x: Executor, p: Principal, a: Any) -> Outcome:
    lead = await sales.update_lead(
        x.sales(), p, a.target_id, LeadUpdate.model_validate(a.request["body"])
    )
    return Outcome("lead", lead.id, lead.title)


async def _lead_archive(x: Executor, p: Principal, a: Any) -> Outcome:
    await sales.archive_lead(x.sales(), p, a.target_id)
    return Outcome("lead", a.target_id, a.target_label)


async def _lead_restore(x: Executor, p: Principal, a: Any) -> Outcome:
    lead = await sales.restore_lead(x.sales(), p, a.target_id)
    return Outcome("lead", lead.id, lead.title)


async def _lead_assign(x: Executor, p: Principal, a: Any) -> Outcome:
    lead = await sales.assign(
        x.sales(), p, a.target_id, AssignRequest.model_validate(a.request["body"])
    )
    return Outcome("lead", lead.id, lead.title)


async def _lead_mark_contacted(x: Executor, p: Principal, a: Any) -> Outcome:
    lead = await sales.mark_contacted(x.sales(), p, a.target_id, a.request["version"])
    return Outcome("lead", lead.id, lead.title)


async def _lead_qualify(x: Executor, p: Principal, a: Any) -> Outcome:
    lead = await sales.qualify(x.sales(), p, a.target_id, a.request["version"])
    return Outcome("lead", lead.id, lead.title)


async def _lead_disqualify(x: Executor, p: Principal, a: Any) -> Outcome:
    lead = await sales.disqualify(
        x.sales(), p, a.target_id, DisqualifyRequest.model_validate(a.request["body"])
    )
    return Outcome("lead", lead.id, lead.title)


async def _lead_reopen(x: Executor, p: Principal, a: Any) -> Outcome:
    lead = await sales.reopen(x.sales(), p, a.target_id, a.request["version"])
    return Outcome("lead", lead.id, lead.title)


async def _lead_convert(x: Executor, p: Principal, a: Any) -> Outcome:
    done = await sales.convert(
        x.sales(), p, a.target_id, ConvertRequest.model_validate(a.request["body"])
    )
    return Outcome("opportunity", done.opportunity.id, done.opportunity.name)


async def _opp_create(x: Executor, p: Principal, a: Any) -> Outcome:
    o = await sales.opportunities.create(
        x.sales(), p, OpportunityCreate.model_validate(a.request["body"])
    )
    return Outcome("opportunity", o.id, o.name)


async def _opp_update(x: Executor, p: Principal, a: Any) -> Outcome:
    o = await sales.opportunities.update(
        x.sales(), p, a.target_id, OpportunityUpdate.model_validate(a.request["body"])
    )
    return Outcome("opportunity", o.id, o.name)


async def _opp_archive(x: Executor, p: Principal, a: Any) -> Outcome:
    await sales.opportunities.archive(x.sales(), p, a.target_id)
    return Outcome("opportunity", a.target_id, a.target_label)


async def _opp_restore(x: Executor, p: Principal, a: Any) -> Outcome:
    o = await sales.opportunities.restore(x.sales(), p, a.target_id)
    return Outcome("opportunity", o.id, o.name)


async def _opp_assign(x: Executor, p: Principal, a: Any) -> Outcome:
    body = AssignRequest.model_validate(a.request["body"])
    o = await sales.opportunities.assign(x.sales(), p, a.target_id, body.owner_id, body.version)
    return Outcome("opportunity", o.id, o.name)


async def _opp_move(x: Executor, p: Principal, a: Any) -> Outcome:
    o = await sales.opportunities.move(
        x.sales(), p, a.target_id, MoveRequest.model_validate(a.request["body"])
    )
    return Outcome("opportunity", o.id, o.name)


async def _opp_close(x: Executor, p: Principal, a: Any) -> Outcome:
    o = await sales.opportunities.close(
        x.sales(), p, a.target_id, CloseRequest.model_validate(a.request["body"])
    )
    return Outcome("opportunity", o.id, o.name)


async def _opp_reopen(x: Executor, p: Principal, a: Any) -> Outcome:
    o = await sales.opportunities.reopen(
        x.sales(), p, a.target_id, ReopenRequest.model_validate(a.request["body"])
    )
    return Outcome("opportunity", o.id, o.name)


async def _activity_create(x: Executor, p: Principal, a: Any) -> Outcome:
    item = await activity.create_activity(
        x.activity(), p, ActivityCreate.model_validate(a.request["body"])
    )
    return Outcome("activity", item.id, item.subject)


async def _activity_update(x: Executor, p: Principal, a: Any) -> Outcome:
    item = await activity.update_activity(
        x.activity(), p, a.target_id, ActivityUpdate.model_validate(a.request["body"])
    )
    return Outcome("activity", item.id, item.subject)


async def _activity_complete(x: Executor, p: Principal, a: Any) -> Outcome:
    item = await activity.complete_task(x.activity(), p, a.target_id, a.request["version"])
    return Outcome("activity", item.id, item.subject)


async def _activity_reopen(x: Executor, p: Principal, a: Any) -> Outcome:
    item = await activity.reopen_task(x.activity(), p, a.target_id, a.request["version"])
    return Outcome("activity", item.id, item.subject)


async def _activity_archive(x: Executor, p: Principal, a: Any) -> Outcome:
    await activity.archive_activity(x.activity(), p, a.target_id)
    return Outcome("activity", a.target_id, a.target_label)


async def _profile_update(x: Executor, p: Principal, a: Any) -> Outcome:
    me = await identity.update_me(x.identity(), p, MeUpdate.model_validate(a.request["body"]))
    return Outcome("user", me.id, me.full_name)


async def _user_create(x: Executor, p: Principal, a: Any) -> Outcome:
    created = await identity.create_user(
        x.identity(), p, UserCreate.model_validate(a.request["body"])
    )
    link = created.set_password.model_dump(mode="json")
    return Outcome("user", created.user.id, created.user.full_name, once={"set_password": link})


async def _user_update(x: Executor, p: Principal, a: Any) -> Outcome:
    user = await identity.update_user(
        x.identity(), p, _uid(a.request["user_id"]), UserUpdate.model_validate(a.request["body"])
    )
    return Outcome("user", user.id, user.full_name)


def _user_step(step: Callable[..., Awaitable[Any]]) -> Run:
    async def run(x: Executor, p: Principal, a: Any) -> Outcome:
        user_id = _uid(a.request["user_id"])
        await step(x.identity(), p, user_id)
        return Outcome("user", user_id, a.target_label)

    return run


async def _settings_update(x: Executor, p: Principal, a: Any) -> Outcome:
    await runtime_settings.update(
        x.session,
        p,
        RuntimeSettingsUpdate.model_validate(a.request["body"]),
        events=x.events,
        now=x.now,
        ai_model_check=lambda model_id: models.unavailable_reason(model_id, x.settings),
    )
    return Outcome()


def _ref(x: Executor, a: Any) -> ReferenceList:
    ref = x.reference_lists.get(a.request["list"])
    if ref is None:
        raise ActionError("list_not_found")
    return ref


async def _reference_add(x: Executor, p: Principal, a: Any) -> Outcome:
    await reference_lists.add_value(
        x.session,
        x.events,
        x.now,
        p,
        _ref(x, a),
        ReferenceItemCreate.model_validate(a.request["body"]),
    )
    return Outcome()


async def _reference_update(x: Executor, p: Principal, a: Any) -> Outcome:
    await reference_lists.change_value(
        x.session,
        x.events,
        x.now,
        p,
        _ref(x, a),
        _uid(a.request["item_id"]),
        ReferenceItemUpdate.model_validate(a.request["body"]),
    )
    return Outcome()


async def _reference_delete(x: Executor, p: Principal, a: Any) -> Outcome:
    await reference_lists.remove_value(
        x.session, x.events, x.now, p, _ref(x, a), _uid(a.request["item_id"])
    )
    return Outcome()


async def _stage_add(x: Executor, p: Principal, a: Any) -> Outcome:
    await sales.add_stage(
        x.sales(), p, _uid(a.request["pipeline_id"]), StageCreate.model_validate(a.request["body"])
    )
    return Outcome()


async def _stage_update(x: Executor, p: Principal, a: Any) -> Outcome:
    await sales.update_stage(
        x.sales(),
        p,
        _uid(a.request["pipeline_id"]),
        _uid(a.request["stage_id"]),
        StageUpdate.model_validate(a.request["body"]),
    )
    return Outcome()


async def _stage_delete(x: Executor, p: Principal, a: Any) -> Outcome:
    await sales.delete_stage(
        x.sales(), p, _uid(a.request["pipeline_id"]), _uid(a.request["stage_id"])
    )
    return Outcome()


EXECUTORS: dict[str, Run] = {
    "organization.create": _org_create,
    "organization.update": _org_update,
    "organization.archive": _org_archive,
    "organization.restore": _org_restore,
    "contact.create": _contact_create,
    "contact.update": _contact_update,
    "contact.archive": _contact_archive,
    "contact.restore": _contact_restore,
    "lead.create": _lead_create,
    "lead.update": _lead_update,
    "lead.archive": _lead_archive,
    "lead.restore": _lead_restore,
    "lead.assign": _lead_assign,
    "lead.mark_contacted": _lead_mark_contacted,
    "lead.qualify": _lead_qualify,
    "lead.disqualify": _lead_disqualify,
    "lead.reopen": _lead_reopen,
    "lead.convert": _lead_convert,
    "opportunity.create": _opp_create,
    "opportunity.update": _opp_update,
    "opportunity.archive": _opp_archive,
    "opportunity.restore": _opp_restore,
    "opportunity.assign": _opp_assign,
    "opportunity.move": _opp_move,
    "opportunity.close_won": _opp_close,
    "opportunity.close_lost": _opp_close,
    "opportunity.reopen": _opp_reopen,
    "activity.create": _activity_create,
    "activity.update": _activity_update,
    "activity.complete": _activity_complete,
    "activity.reopen": _activity_reopen,
    "activity.archive": _activity_archive,
    "profile.update": _profile_update,
    "user.create": _user_create,
    "user.update": _user_update,
    "user.deactivate": _user_step(identity.deactivate_user),
    "user.activate": _user_step(identity.activate_user),
    "user.unlock": _user_step(identity.unlock_user),
    "user.revoke_sessions": _user_step(identity.revoke_user_sessions),
    "settings.update": _settings_update,
    "reference.add": _reference_add,
    "reference.update": _reference_update,
    "reference.delete": _reference_delete,
    "stage.add": _stage_add,
    "stage.update": _stage_update,
    "stage.delete": _stage_delete,
}

URLS = {
    "organization": "/organizations/",
    "contact": "/contacts/",
    "lead": "/leads/",
    "opportunity": "/opportunities/",
    "user": "/admin/users/",
}


def url_of(entity_type: str | None, entity_id: Any) -> str | None:
    if entity_type is None or entity_id is None:
        return None
    if entity_type == "activity":
        return "/tasks"
    prefix = URLS.get(entity_type)
    return f"{prefix}{entity_id}" if prefix else None
