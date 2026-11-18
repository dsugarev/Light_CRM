"""A scripted stand-in for the model, for development and the end-to-end stack (`LLM_FAKE`).

It follows the same protocol as the real client and behaves predictably: a question
about the pipeline calls `pipeline_summary`, any other question calls
`search_opportunities`, and the answer is built from the tool result only. A message
containing "#fail" simulates a provider outage. It never runs in production (the
settings refuse `LLM_FAKE` there).
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

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

_CYRILLIC = re.compile(r"[а-яА-Я]")
_PIPELINE = re.compile(r"pipeline|stage|фуния|етап", re.IGNORECASE)


class DemoLLM:
    def __init__(self, delay_seconds: float = 0.02) -> None:
        self._delay = delay_seconds

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[Tool] | None
    ) -> AsyncIterator[StreamItem]:
        question = _last_user_text(messages)
        if "#fail" in question:
            raise LLMUnavailableError("Simulated")
        bulgarian = bool(_CYRILLIC.search(question))
        last = messages[-1] if messages else {}
        usage = Usage(prompt_tokens=sum(len(str(m.get("content") or "")) for m in messages) // 4)
        if last.get("role") != "tool" and tools:
            name = "pipeline_summary" if _PIPELINE.search(question) else "search_opportunities"
            arguments = {"owner": "anyone"} if name == "pipeline_summary" else {"limit": 5}
            yield Completed(
                tool_calls=(ToolCall(id="call_demo", name=name, arguments=json.dumps(arguments)),),
                usage=usage,
            )
            return
        answer = _answer(_tool_result(messages), bulgarian)
        for word in re.findall(r"\S+\s*", answer):
            await asyncio.sleep(self._delay)
            yield TextDelta(word)
        yield Completed(tool_calls=(), usage=Usage(usage.prompt_tokens, len(answer) // 4))


def _last_user_text(messages: Sequence[Message]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _tool_result(messages: Sequence[Message]) -> Mapping[str, Any]:
    for message in reversed(messages):
        if message.get("role") == "tool":
            try:
                result = json.loads(str(message.get("content") or "{}"))
            except ValueError:
                return {}
            return result if isinstance(result, dict) else {}
    return {}


def _answer(result: Mapping[str, Any], bulgarian: bool) -> str:
    if "stages" in result:
        lines = [
            "Отворена фуния по етапи:" if bulgarian else "Open pipeline by stage:",
            "",
            "| Етап | Брой | Стойност (EUR) |" if bulgarian else "| Stage | Count | Value (EUR) |",
            "|---|---:|---:|",
        ]
        lines += [
            f"| {s['stage']} | {s['count']} | {s['total_amount']} |" for s in result["stages"]
        ]
        return "\n".join(lines)
    items = result.get("items") or []
    if not items:
        return (
            "Не намерих такива записи в CRM."
            if bulgarian
            else "I found no such records in the CRM."
        )
    heading = "Намерих тези възможности:" if bulgarian else "I found these opportunities:"
    rows = [f"- [{item['name']}]({item['url']})" for item in items]
    return "\n".join([heading, "", *rows])
