"""LLM client: LiteLLM to the model an Admin chose (architecture 8.1, ADR 0031).

OpenRouter models go through OpenRouter with provider routing (Cerebras for the
default, NVIDIA for the free Nemotron); Gemini goes straight to Google AI Studio.

The only module that imports litellm (an import-linter contract enforces it). The rest
of the application sees the small `LLM` protocol in app.llm.types, which the tests and
the end-to-end stack replace with a scripted model; app.llm.factory picks one.
"""

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

# LiteLLM fetches a model price list from the internet at import time unless told to
# use its bundled copy; the on-premises backend calls no host but the LLM provider.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
# In its default "DEV" mode LiteLLM loads the nearest .env file into the process
# environment at import time; configuration comes only from our settings.
os.environ.setdefault("LITELLM_MODE", "PRODUCTION")

import litellm

from app.core.config import Settings
from app.llm import models
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


@dataclass(frozen=True, slots=True)
class Route:
    """How one catalog model is called."""

    model: str
    api_key: str
    api_base: str | None
    extra_body: dict[str, Any] | None


def _secret(value: Any) -> str | None:
    return value.get_secret_value() or None if value is not None else None


class LiteLLMClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._timeout = settings.llm_timeout_seconds

    def route(self, model_id: str | None) -> Route:
        """The call for a catalog id; an unknown id or a missing key fails the answer."""
        settings = self._settings
        option = models.find(model_id or models.DEFAULT_MODEL)
        if option is None:
            raise LLMUnavailableError("UnknownModel")
        if option.key == "gemini":
            key = _secret(settings.gemini_api_key)
            if key is None:
                raise LLMUnavailableError("MissingApiKey")
            return Route(
                model=option.litellm_model or "", api_key=key, api_base=None, extra_body=None
            )
        key = _secret(settings.openrouter_api_key)
        if key is None:
            raise LLMUnavailableError("MissingApiKey")
        provider = option.provider or settings.llm_provider
        return Route(
            model=option.litellm_model or settings.llm_model,
            api_key=key,
            api_base=settings.llm_api_base or None,  # compose passes "" when unset
            # OpenRouter provider routing: this provider only, never another one.
            extra_body={"provider": {"order": [provider], "allow_fallbacks": False}},
        )

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[Tool] | None,
        *,
        model: str | None = None,
    ) -> AsyncIterator[StreamItem]:
        route = self.route(model)
        chunks: list[Any] = []
        try:
            async with asyncio.timeout(self._timeout):
                response = await litellm.acompletion(
                    model=route.model,
                    messages=list(messages),
                    tools=list(tools) if tools else None,
                    stream=True,
                    stream_options={"include_usage": True},
                    timeout=self._timeout,
                    api_key=route.api_key,
                    api_base=route.api_base,
                    extra_body=route.extra_body,
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
