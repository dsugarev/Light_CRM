# ruff: noqa: F811 - the fixtures `llm` and `settings` come from test_assistant
"""The assistant reads users, settings, lists and anyone's tasks (FR-AI-02, ADR 0032).

Same access as the screens: Admins see the user list and the settings; everyone sees the
lists and stages and the team's activities. No email address or sign-in secret reaches
the model. The model is scripted (no network).
"""

import json
from datetime import timedelta
from typing import Any

import httpx

from app.core.principal import RoleCode
from app.modules.assistant import tools
from tests.api.test_assistant import (  # noqa: F401 - fixtures
    ScriptedLLM,
    answer,
    ask,
    call,
    conversation,
    llm,
    settings,
    tool_results,
)
from tests.api.test_opportunities import create_opp, create_org
from tests.helpers import TestApp


async def read(
    client: httpx.AsyncClient, model: ScriptedLLM, tool: str, **arguments: Any
) -> dict[str, Any]:
    """One answer in which the model calls `tool`; returns what the tool gave it."""
    model.then(call(tool, **arguments), answer("Done."))
    chat = await conversation(client)
    await ask(client, chat["id"], "Please look it up.")
    [result] = tool_results(model.calls[-1][0])
    return result


async def test_FR_AI_02_an_admin_asks_how_many_users_there_are(
    test_app: TestApp, llm: ScriptedLLM
) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN, full_name="Ада Админова")
    await test_app.create_user(RoleCode.SALES_REP, full_name="Рая Търговска")
    await test_app.create_user(RoleCode.SALES_REP, full_name="Боян Търговски", is_active=False)
    await test_app.create_user(
        RoleCode.SALES_MANAGER,
        full_name="Мира Мениджърска",
        locked_until=test_app.clock.now() + timedelta(minutes=10),
    )
    result = await read(admin, llm, "list_users")
    assert result["total_users"] == 4
    assert result["by_status"] == {"active": 2, "locked": 1, "deactivated": 1}
    assert result["active_by_role"] == {"admin": 1, "sales_rep": 1, "sales_manager": 1}
    rows = {u["name"]: (u["role"], u["status"]) for u in result["items"]}
    assert rows["Боян Търговски"] == ("sales_rep", "deactivated")
    assert rows["Мира Мениджърска"] == ("sales_manager", "locked")
    assert "@" not in json.dumps(result)  # no email addresses reach the model

    locked = await read(admin, llm, "list_users", status="locked")
    assert [u["name"] for u in locked["items"]] == ["Мира Мениджърска"]
    reps = await read(admin, llm, "list_users", role="sales_rep", status="active")
    assert [u["name"] for u in reps["items"]] == ["Рая Търговска"]


async def test_FR_AI_02_others_see_only_active_colleagues_names(
    test_app: TestApp, llm: ScriptedLLM
) -> None:
    rep, _ = await test_app.signed_in(RoleCode.SALES_REP, full_name="Рая Търговска")
    await test_app.create_user(RoleCode.ADMIN, full_name="Ада Админова")
    await test_app.create_user(RoleCode.SALES_REP, full_name="Боян Търговски", is_active=False)
    result = await read(rep, llm, "list_users")
    assert result["active_users"] == 2
    assert {u["name"] for u in result["items"]} == {"Рая Търговска", "Ада Админова"}
    assert all(set(u) == {"name"} for u in result["items"])  # no role, status or sign-in


async def test_FR_AI_02_an_admin_reads_the_settings_and_the_model_in_use(
    test_app: TestApp, llm: ScriptedLLM
) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    result = await read(admin, llm, "get_settings")
    assert result["ai_model"] == "gpt-oss-120b"
    assert result["ai_model_label"] == "gpt-oss-120b (OpenRouter, Cerebras)"
    assert result["stale_opportunity_days"] > 0
    assert "gpt-oss-120b (OpenRouter, Cerebras)" in result["ai_models_available"]

    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    assert await read(manager, llm, "get_settings") == {"error": "not_allowed_for_role"}


async def test_FR_AI_02_lists_and_pipeline_stages(test_app: TestApp, llm: ScriptedLLM) -> None:
    viewer, _ = await test_app.signed_in(RoleCode.VIEWER)
    stages = await read(viewer, llm, "list_values", list="pipeline-stages")
    names = [s["name"] for s in stages["stages"]]
    assert names[0] == "Prospecting"
    assert {s["stage_type"] for s in stages["stages"]} == {"open", "won", "lost"}
    reasons = await read(viewer, llm, "list_values", list="loss-reasons")
    assert reasons["values"]
    assert all(v["is_active"] for v in reasons["values"])
    sources = await read(viewer, llm, "list_values", list="lead-sources")
    assert sources["values"]


async def test_FR_AI_02_a_colleagues_open_and_overdue_tasks(
    test_app: TestApp, llm: ScriptedLLM
) -> None:
    manager, _ = await test_app.signed_in(RoleCode.SALES_MANAGER)
    ivan = await test_app.create_user(RoleCode.SALES_REP, full_name="Иван Задачев")
    opp = await create_opp(manager, await create_org(manager, "Задачи АД"), name="Сделка")
    now = test_app.clock.now()

    async def task(subject: str, due: timedelta, assignee: Any) -> None:
        response = await manager.post(
            "/api/v1/activities",
            json={
                "type": "task",
                "subject": subject,
                "due_at": (now + due).isoformat(),
                "opportunity_id": opp["id"],
                "assignee_id": str(assignee),
            },
        )
        assert response.status_code == 201, response.text

    await task("Late offer", -timedelta(days=2), ivan.id)
    await task("Next call", timedelta(days=3), ivan.id)
    note = await manager.post(
        "/api/v1/activities",
        json={"type": "note", "subject": "Not a task", "opportunity_id": opp["id"]},
    )
    assert note.status_code == 201, note.text

    open_tasks = await read(manager, llm, "list_activities", assignee_name="Задачев")
    assert [t["subject"] for t in open_tasks["items"]] == ["Late offer", "Next call"]
    overdue = await read(manager, llm, "list_activities", overdue_only=True)
    assert [t["subject"] for t in overdue["items"]] == ["Late offer"]
    unknown = await read(manager, llm, "list_activities", assignee_name="Никой Такъв")
    assert unknown["error"] == "owner_not_found"


def test_FR_AI_02_new_reading_tools_are_offered_to_every_role() -> None:
    for role in RoleCode:
        offered = tools.tools_for(role)
        assert {"list_users", "get_settings", "list_values"} <= set(offered)
