# ruff: noqa: F811 - the fixture `llm` comes from test_assistant
"""The Admin chooses the assistant's model for everyone (FR-AI-10; ADR 0031; API spec 6.1).

Configured with an OpenRouter key only, so the Gemini option is unavailable. The model is
the scripted fake: it records which catalog model each call asked for. No live model.
"""

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.principal import RoleCode
from tests.api.test_assistant import (  # noqa: F401 - fixtures
    ScriptedLLM,
    answer,
    ask,
    conversation,
    events,
    llm,
)
from tests.api.test_assistant_actions import model_saw, propose
from tests.helpers import TestApp


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "ai_enabled": True,
            "llm_fake": False,
            "openrouter_api_key": SecretStr("sk-or-v1-test"),
            "gemini_api_key": None,
        }
    )


async def test_FR_AI_10_models_list_shows_availability_and_data_notes(test_app: TestApp) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    response = await admin.get("/api/v1/settings/ai-models")
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "gpt-oss-120b",
            "label": "gpt-oss-120b (OpenRouter, Cerebras)",
            "provider": "openrouter",
            "available": True,
            "free": False,
            "data_note": None,
        },
        {
            "id": "nemotron-3-ultra-free",
            "label": "NVIDIA Nemotron 3 Ultra (OpenRouter, free)",
            "provider": "openrouter",
            "available": True,
            "free": True,
            "data_note": "may_keep_prompts",
        },
        {
            "id": "gemini-3.5-flash",
            "label": "Gemini 3.5 Flash (Google)",
            "provider": "google",
            "available": False,
            "free": True,
            "data_note": "may_keep_prompts",
        },
    ]


@pytest.mark.parametrize("role", [RoleCode.SALES_MANAGER, RoleCode.SALES_REP, RoleCode.VIEWER])
async def test_FR_AI_10_only_admins_see_or_change_the_model(
    test_app: TestApp, role: RoleCode
) -> None:
    client, _ = await test_app.signed_in(role)
    assert (await client.get("/api/v1/settings/ai-models")).status_code == 403
    response = await client.patch("/api/v1/settings", json={"ai_model": "nemotron-3-ultra-free"})
    assert response.status_code == 403


async def test_FR_AI_10_AC1_admin_choice_applies_to_every_users_next_answer(
    test_app: TestApp, llm: ScriptedLLM
) -> None:
    admin, admin_user = await test_app.signed_in(RoleCode.ADMIN)
    rep, _ = await test_app.signed_in(RoleCode.SALES_REP)

    llm.then(answer("First."))
    chat = await conversation(rep)
    events(await ask(rep, chat["id"], "Hello"))
    assert llm.models == ["nemotron-3-ultra-free"]  # the default (owner, 2026-11-22)

    response = await admin.patch("/api/v1/settings", json={"ai_model": "gpt-oss-120b"})
    assert response.status_code == 200, response.text
    assert response.json()["ai_model"] == "gpt-oss-120b"
    [entry] = await test_app.audit("settings.updated")
    assert entry.actor_id == admin_user.id
    assert entry.before is not None
    assert entry.before["ai_model"] == "nemotron-3-ultra-free"
    assert entry.after is not None
    assert entry.after["ai_model"] == "gpt-oss-120b"

    llm.then(answer("Second."))
    events(await ask(rep, chat["id"], "Hello again"))
    assert llm.models[-1] == "gpt-oss-120b"  # no restart, no cache delay

    status = (await rep.get("/api/v1/assistant/status")).json()
    assert status["model"] == "gpt-oss-120b"
    assert status["model_label"] == "gpt-oss-120b (OpenRouter, Cerebras)"


@pytest.mark.parametrize("model", ["gemini-3.5-flash", "gpt-5-unknown"])
async def test_FR_AI_10_AC2_a_model_without_its_key_or_unknown_is_refused(
    test_app: TestApp, model: str
) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    response = await admin.patch("/api/v1/settings", json={"ai_model": model})
    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"field": "ai_model", "code": "settings.ai_model_unavailable"}
    ]
    assert (await admin.get("/api/v1/settings")).json()["ai_model"] == "nemotron-3-ultra-free"
    assert await test_app.audit("settings.updated") == []


async def test_FR_AI_10_the_assistant_offers_only_available_models(
    test_app: TestApp, llm: ScriptedLLM
) -> None:
    admin, _ = await test_app.signed_in(RoleCode.ADMIN)
    cards = await propose(
        admin,
        llm,
        "propose_admin_action",
        action="settings.update",
        params={"ai_model": "gemini-3.5-flash"},
    )
    assert cards == []

    assert model_saw(llm) == {
        "error": "ai_model_unavailable",
        "options": ["gpt-oss-120b", "nemotron-3-ultra-free"],
    }
