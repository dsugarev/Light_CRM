"""LLM client: LiteLLM -> OpenRouter -> Cerebras (architecture 8.1).

The only module that imports litellm (an import-linter contract enforces it). The rest
of the application sees the small `LLM` protocol in app.llm.types, which the tests and
the end-to-end stack replace with a scripted model; app.llm.factory picks one.
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Sequence
from typing import Any

# LiteLLM fetches a model price list from the internet at import time unless told to
# use its bundled copy; the on-premises backend calls no host but the LLM provider.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
# In its default "DEV" mode LiteLLM loads the nearest .env file into the process
# environment at import time; configuration comes only from our settings.
os.environ.setdefault("LITELLM_MODE", "PRODUCTION")

import litellm

from app.core.config import Settings
from app.llm.types import (
    Completed,
    LLMUnavailableError,
    Message,
    StreamItem,
    TextDelta,
    Tool,
    ToolCall,
    Usage,
)

# Chat content must never reach the logs (architecture 8.4, privacy).
litellm.suppress_debug_info = True
litellm.turn_off_message_logging = True
# LiteLLM's own INFO lines (one per call) are noise in our JSON logs.
logging.getLogger("LiteLLM").setLevel(logging.WARNING)


class LiteLLMClient:
    def __init__(self, settings: Settings) -> None:
        if settings.openrouter_api_key is None:
            raise ValueError("OPENROUTER_API_KEY is not set")
        self._api_key = settings.openrouter_api_key.get_secret_value()
        self._model = settings.llm_model
        self._provider = settings.llm_provider
        self._timeout = settings.llm_timeout_seconds
        self._api_base = settings.llm_api_base or None  # compose passes "" when unset

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[Tool] | None
    ) -> AsyncIterator[StreamItem]:
        chunks: list[Any] = []
        try:
            async with asyncio.timeout(self._timeout):
                response = await litellm.acompletion(
                    model=self._model,
                    messages=list(messages),
                    tools=list(tools) if tools else None,
                    stream=True,
                    stream_options={"include_usage": True},
                    timeout=self._timeout,
                    api_key=self._api_key,
                    api_base=self._api_base,
                    # OpenRouter provider routing: Cerebras only, never another provider.
                    extra_body={"provider": {"order": [self._provider], "allow_fallbacks": False}},
                    # With tools, LiteLLM 1.108 imports its MCP gateway, which needs the
                    # optional `mcp` package; we use no MCP tools, so skip that path.
                    _skip_mcp_handler=True,
                )
                async for chunk in response:
                    chunks.append(chunk)
                    text = _delta_text(chunk)
                    if text:
                        yield TextDelta(text)
            built = litellm.stream_chunk_builder(chunks, messages=list(messages))
        except Exception as error:  # any provider, network or timeout failure
            raise LLMUnavailableError(type(error).__name__) from None
        if built is None:
            raise LLMUnavailableError("EmptyResponse")
        yield Completed(tool_calls=_tool_calls(built), usage=_usage(built))


def _delta_text(chunk: Any) -> str:
    choices = getattr(chunk, "choices", None) or []
    if not choices:
        return ""
    delta = getattr(choices[0], "delta", None)
    return getattr(delta, "content", None) or ""


def _tool_calls(response: Any) -> tuple[ToolCall, ...]:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ()
    calls = getattr(choices[0].message, "tool_calls", None) or []
    return tuple(
        ToolCall(
            id=call.id or f"call_{n}",
            name=call.function.name or "",
            arguments=call.function.arguments or "",
        )
        for n, call in enumerate(calls)
    )


def _usage(response: Any) -> Usage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return Usage()
    return Usage(
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
    )
