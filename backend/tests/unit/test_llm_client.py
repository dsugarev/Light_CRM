"""LLM client (architecture 8.1; FR-AI-07): routing, streaming, tool calls, failures.

No network: LiteLLM's own offline `mock_response` and hand-built stream chunks drive
the real streaming and chunk-assembly code.
"""

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

import litellm
import pytest
from litellm.types.utils import (
    ChatCompletionDeltaToolCall,
    Delta,
    Function,
    ModelResponseStream,
    StreamingChoices,
)
from litellm.types.utils import Usage as LiteUsage
from pydantic import SecretStr, ValidationError

from app.core.config import Environment, Settings
from app.llm import client as llm_client
from app.llm.factory import create_llm
from app.llm.fake import DemoLLM
from app.llm.fake_server import make_server
from app.llm.types import Completed, LLMUnavailableError, StreamItem, TextDelta

MESSAGES = [{"role": "user", "content": "Hi"}]


def _settings(**changes: Any) -> Settings:
    return Settings(
        env=Environment.TEST,
        ai_enabled=True,
        openrouter_api_key=SecretStr("sk-or-v1-test"),
        **changes,
    )


async def _collect(stream: AsyncIterator[StreamItem]) -> list[StreamItem]:
    return [item async for item in stream]


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Calls the real litellm.acompletion offline (mock_response) and keeps the kwargs."""
    seen: dict[str, Any] = {}
    real = litellm.acompletion

    async def offline(**kwargs: Any) -> Any:
        seen.update(kwargs)
        return await real(**kwargs, mock_response="Здравейте, ето отговора")

    monkeypatch.setattr(litellm, "acompletion", offline)
    return seen


async def test_routes_to_the_configured_model_through_cerebras_only(
    captured: dict[str, Any],
) -> None:
    client = llm_client.LiteLLMClient(_settings())
    items = await _collect(client.stream(MESSAGES, None, model="gpt-oss-120b"))
    assert captured["model"] == "openrouter/openai/gpt-oss-120b"
    assert captured["extra_body"] == {"provider": {"order": ["cerebras"], "allow_fallbacks": False}}
    assert captured["api_key"] == "sk-or-v1-test"
    assert captured["stream"] is True
    assert captured["timeout"] == 60.0
    assert captured["tools"] is None
    text = "".join(i.text for i in items if isinstance(i, TextDelta))
    assert text == "Здравейте, ето отговора"
    assert len([i for i in items if isinstance(i, TextDelta)]) > 1  # streamed in pieces
    final = items[-1]
    assert isinstance(final, Completed)
    assert final.tool_calls == ()
    assert final.usage.completion_tokens > 0


async def test_FR_AI_10_without_a_choice_the_free_model_answers(
    captured: dict[str, Any],
) -> None:
    await _collect(llm_client.LiteLLMClient(_settings()).stream(MESSAGES, None))
    assert captured["model"] == "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"


async def test_FR_AI_10_free_model_routes_through_openrouter_to_nvidia_only(
    captured: dict[str, Any],
) -> None:
    client = llm_client.LiteLLMClient(_settings())
    await _collect(client.stream(MESSAGES, None, model="nemotron-3-ultra-free"))
    assert captured["model"] == "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
    assert captured["extra_body"] == {"provider": {"order": ["nvidia"], "allow_fallbacks": False}}
    assert captured["api_key"] == "sk-or-v1-test"


async def test_FR_AI_10_gemini_goes_to_google_with_its_own_key(
    captured: dict[str, Any],
) -> None:
    settings = _settings(gemini_api_key=SecretStr("gm-test"), llm_api_base="http://gateway")
    await _collect(
        llm_client.LiteLLMClient(settings).stream(MESSAGES, None, model="gemini-3.5-flash")
    )
    assert captured["model"] == "gemini/gemini-3.5-flash"
    assert captured["api_key"] == "gm-test"
    assert captured["api_base"] is None  # the OpenRouter gateway override is not for Google
    assert captured["extra_body"] is None


HISTORY: list[dict[str, Any]] = [
    {"role": "user", "content": "What is the amount of the Acme Rocket deal?"},
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "search_opportunities", "arguments": '{"query": "Acme"}'},
            }
        ],
    },
    {"role": "tool", "tool_call_id": "call_1", "content": '{"items": [], "total": 0}'},
]


async def test_FR_AI_10_gemini_sees_earlier_tool_calls_as_text_when_it_must_answer(
    captured: dict[str, Any],
) -> None:
    """Gemini answers a call without tools with another tool call and no text, even with
    tool_choice "none"; the tool loop's last round would end empty."""
    settings = _settings(gemini_api_key=SecretStr("gm-test"))
    client = llm_client.LiteLLMClient(settings)
    await _collect(client.stream(HISTORY, None, model="gemini-3.5-flash"))
    assert captured["messages"] == [
        HISTORY[0],
        {
            "role": "user",
            "content": '[Result of search_opportunities {"query": "Acme"}]\n'
            '{"items": [], "total": 0}',
        },
    ]
    captured.clear()
    tool = {"type": "function", "function": {"name": "my_tasks", "parameters": {}}}
    await _collect(client.stream(HISTORY, [tool], model="gemini-3.5-flash"))
    assert captured["messages"] == HISTORY  # with tools, the real tool messages


async def test_FR_AI_10_openrouter_models_keep_tool_messages(captured: dict[str, Any]) -> None:
    await _collect(llm_client.LiteLLMClient(_settings()).stream(HISTORY, None))
    assert captured["messages"] == HISTORY


@pytest.mark.parametrize(
    ("model", "reason"),
    [("gemini-3.5-flash", "MissingApiKey"), ("no-such-model", "UnknownModel")],
)
async def test_FR_AI_10_a_model_that_cannot_be_called_fails_the_answer(
    captured: dict[str, Any], model: str, reason: str
) -> None:
    with pytest.raises(LLMUnavailableError, match=reason):
        await _collect(llm_client.LiteLLMClient(_settings()).stream(MESSAGES, None, model=model))
    assert captured == {}


def test_FR_AI_10_a_gemini_key_alone_switches_the_assistant_on() -> None:
    settings = Settings(env=Environment.TEST, ai_enabled=True, gemini_api_key=SecretStr("gm"))
    assert isinstance(create_llm(settings), llm_client.LiteLLMClient)


async def test_tool_call_fragments_are_assembled(monkeypatch: pytest.MonkeyPatch) -> None:
    def chunk(**delta: Any) -> ModelResponseStream:
        return ModelResponseStream(
            id="r",
            model="openai/gpt-oss-120b",
            choices=[StreamingChoices(index=0, delta=Delta(**delta))],
        )

    last = ModelResponseStream(
        id="r",
        model="openai/gpt-oss-120b",
        choices=[StreamingChoices(index=0, delta=Delta(), finish_reason="tool_calls")],
    )
    last.usage = LiteUsage(prompt_tokens=40, completion_tokens=7, total_tokens=47)
    chunks = [
        chunk(
            tool_calls=[
                ChatCompletionDeltaToolCall(
                    id="call_7",
                    index=0,
                    type="function",
                    function=Function(name="search_leads", arguments='{"li'),
                )
            ]
        ),
        chunk(
            tool_calls=[
                ChatCompletionDeltaToolCall(index=0, function=Function(arguments='mit": 3}'))
            ]
        ),
        last,
    ]

    async def stream() -> AsyncIterator[ModelResponseStream]:
        for c in chunks:
            yield c

    async def fake(**_: Any) -> AsyncIterator[ModelResponseStream]:
        return stream()

    monkeypatch.setattr(litellm, "acompletion", fake)
    tools = [{"type": "function", "function": {"name": "search_leads", "parameters": {}}}]
    items = await _collect(llm_client.LiteLLMClient(_settings()).stream(MESSAGES, tools))
    [final] = items
    assert isinstance(final, Completed)
    [tool_call] = final.tool_calls
    assert (tool_call.id, tool_call.name, json.loads(tool_call.arguments)) == (
        "call_7",
        "search_leads",
        {"limit": 3},
    )
    assert (final.usage.prompt_tokens, final.usage.completion_tokens) == (40, 7)


async def test_FR_AI_07_provider_errors_become_unavailable_without_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing(**_: Any) -> Any:
        raise litellm.exceptions.APIError(
            status_code=402,
            message="Insufficient credits for prompt 'my secret question'",
            llm_provider="openrouter",
            model="openai/gpt-oss-120b",
        )

    monkeypatch.setattr(litellm, "acompletion", failing)
    with pytest.raises(LLMUnavailableError) as raised:
        await _collect(llm_client.LiteLLMClient(_settings()).stream(MESSAGES, None))
    assert str(raised.value) == "APIError"
    assert raised.value.__cause__ is None


async def test_FR_AI_07_slow_provider_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    async def slow(**_: Any) -> Any:
        await asyncio.sleep(5)

    monkeypatch.setattr(litellm, "acompletion", slow)
    client = llm_client.LiteLLMClient(_settings(llm_timeout_seconds=0.05))
    with pytest.raises(LLMUnavailableError, match="TimeoutError"):
        await _collect(client.stream(MESSAGES, None))


def test_importing_litellm_does_not_load_dotenv_files() -> None:
    """LiteLLM's default mode reads the nearest .env into os.environ on import, which
    would bypass our settings (and pull in secrets meant for other processes)."""
    import os

    assert os.environ["LITELLM_MODE"] == "PRODUCTION"
    assert "OPENROUTER_API_KEY" not in os.environ
    assert os.environ.get("ENV") != "production"


def test_message_logging_is_off() -> None:
    assert litellm.turn_off_message_logging is True
    assert litellm.suppress_debug_info is True


def test_factory_picks_the_model_from_settings() -> None:
    assert create_llm(Settings(env=Environment.TEST)) is None
    assert isinstance(create_llm(_settings(llm_fake=True)), DemoLLM)
    assert isinstance(create_llm(_settings()), llm_client.LiteLLMClient)


def test_FR_AI_07_settings_refuse_an_assistant_without_a_model() -> None:
    with pytest.raises(ValidationError, match="AI_ENABLED needs OPENROUTER_API_KEY"):
        Settings(env=Environment.TEST, ai_enabled=True)
    with pytest.raises(ValidationError, match="LLM_FAKE"):
        Settings(env=Environment.PRODUCTION, llm_fake=True)
    assert "sk-or-v1-test" not in repr(_settings())


async def test_demo_model_answers_from_the_tool_result_in_the_users_language() -> None:
    demo = DemoLLM(delay_seconds=0)
    tools = [{"type": "function", "function": {"name": "pipeline_summary"}}]
    question = [{"role": "user", "content": "Покажи фунията по етапи"}]
    [first] = await _collect(demo.stream(question, tools))
    assert isinstance(first, Completed)
    assert first.tool_calls[0].name == "pipeline_summary"
    result = {"stages": [{"stage": "Квалификация", "count": 2, "total_amount": "900.00"}]}
    follow = [*question, {"role": "tool", "tool_call_id": "x", "content": json.dumps(result)}]
    items = await _collect(demo.stream(follow, tools))
    text = "".join(i.text for i in items if isinstance(i, TextDelta))
    assert "Отворена фуния по етапи" in text
    assert "| Квалификация | 2 | 900.00 |" in text
    with pytest.raises(LLMUnavailableError):
        await _collect(demo.stream([{"role": "user", "content": "#fail now"}], tools))


async def test_real_client_against_the_scripted_provider_server() -> None:
    """The end-to-end stack's path: LiteLLM -> LLM_API_BASE -> app.llm.fake_server, with
    tool calls and text streamed in the provider's format."""
    server = make_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}/v1"
        client = llm_client.LiteLLMClient(_settings(llm_api_base=base))
        tools = [{"type": "function", "function": {"name": "pipeline_summary", "parameters": {}}}]
        question = [{"role": "user", "content": "Show the pipeline by stage"}]
        [first] = await _collect(client.stream(question, tools))
        assert isinstance(first, Completed)
        [tool_call] = first.tool_calls
        assert tool_call.name == "pipeline_summary"
        assert json.loads(tool_call.arguments) == {"owner": "anyone"}

        result = {"stages": [{"stage": "Prospecting", "count": 1, "total_amount": "10.00"}]}
        follow: list[dict[str, Any]] = [
            *question,
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {"name": tool_call.name, "arguments": tool_call.arguments},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)},
        ]
        items = await _collect(client.stream(follow, tools))
        deltas = [i for i in items if isinstance(i, TextDelta)]
        assert len(deltas) > 3
        assert "| Prospecting | 1 | 10.00 |" in "".join(d.text for d in deltas)
        final = items[-1]
        assert isinstance(final, Completed)
        assert final.tool_calls == ()
        assert final.usage.completion_tokens > 0

        with pytest.raises(LLMUnavailableError):
            await _collect(client.stream([{"role": "user", "content": "#fail"}], tools))
    finally:
        server.shutdown()
        server.server_close()
