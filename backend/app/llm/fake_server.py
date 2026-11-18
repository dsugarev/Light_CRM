"""A scripted, OpenAI-compatible chat completions server for end-to-end tests.

    python -m app.llm.fake_server [--port 8080]

It answers `POST .../chat/completions` with the demo model's script (app.llm.fake),
streamed in the provider's Server-Sent Events format, so the end-to-end stack runs the
real LiteLLM client, streaming and tool loop with production settings, only with
`LLM_API_BASE` pointing here instead of OpenRouter. "#fail" in the question answers
503, a simulated provider outage. It reads no data and holds no secrets; it is never
started in production.
"""

import argparse
import asyncio
import json
import time
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from app.llm.fake import DemoLLM
from app.llm.types import Completed, LLMUnavailableError, StreamItem, TextDelta

CHUNK_DELAY_SECONDS = 0.03


async def _script(messages: Sequence[Any], tools: Sequence[Any] | None) -> list[StreamItem]:
    return [item async for item in DemoLLM(delay_seconds=0).stream(messages, tools)]


def _chunk(model: str, delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
    return {
        "id": "chatcmpl-demo",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def events(model: str, items: Sequence[StreamItem]) -> list[dict[str, Any]]:
    """The provider's stream for one scripted call: text, tool calls, finish, usage."""
    out: list[dict[str, Any]] = [_chunk(model, {"role": "assistant", "content": ""})]
    finish = "stop"
    for item in items:
        if isinstance(item, TextDelta):
            out.append(_chunk(model, {"content": item.text}))
        elif isinstance(item, Completed):
            for index, call in enumerate(item.tool_calls):
                finish = "tool_calls"
                out.append(
                    _chunk(
                        model,
                        {
                            "tool_calls": [
                                {
                                    "index": index,
                                    "id": call.id,
                                    "type": "function",
                                    "function": {"name": call.name, "arguments": call.arguments},
                                }
                            ]
                        },
                    )
                )
            out.append(_chunk(model, {}, finish))
            usage = item.usage
            out.append(
                {
                    **_chunk(model, {}),
                    "choices": [],
                    "usage": {
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                        "total_tokens": usage.prompt_tokens + usage.completion_tokens,
                    },
                }
            )
    return out


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self._json(404, {"error": {"message": "not found"}})
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        try:
            items = asyncio.run(_script(body.get("messages") or [], body.get("tools")))
        except LLMUnavailableError:
            self._json(503, {"error": {"message": "Simulated provider outage", "code": 503}})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for event in events(str(body.get("model") or "demo"), items):
            self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
            time.sleep(CHUNK_DELAY_SECONDS)
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return  # requests carry chat content; nothing is logged


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), _Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - reached from other containers
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    make_server(args.host, args.port).serve_forever()


if __name__ == "__main__":
    main()
