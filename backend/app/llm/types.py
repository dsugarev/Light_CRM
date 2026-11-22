"""What the rest of the application knows about the model: plain types and a protocol.

Nothing here imports litellm, so modules can depend on these types without loading the
provider client (import-linter: only app.llm.client imports litellm).
"""

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

Message = Mapping[str, Any]
Tool = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text as produced by the model; validated by the caller


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True, slots=True)
class TextDelta:
    """The next piece of the answer."""

    text: str


@dataclass(frozen=True, slots=True)
class Completed:
    """End of one model call: the tools it asks for (none for a final answer), and usage."""

    tool_calls: tuple[ToolCall, ...]
    usage: Usage


StreamItem = TextDelta | Completed


class LLMUnavailableError(Exception):
    """The provider failed, refused or timed out. Carries no prompt or answer text."""


class LLM(Protocol):
    def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[Tool] | None,
        *,
        model: str | None = None,
    ) -> AsyncIterator[StreamItem]:
        """One model call, streamed: `TextDelta`s, then exactly one `Completed`.

        `model` is a catalog id from app.llm.models (the Admin's choice); None means the
        default model."""
        ...
