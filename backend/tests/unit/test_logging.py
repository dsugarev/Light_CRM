"""Structured JSON logs carry the request ID (NFR-08)."""

import json
import logging

import pytest

from app.core.logging import JsonFormatter, configure_logging, request_id_var


def _record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, message, None, None)
    record.__dict__.update(extra)
    return record


def test_NFR_08_log_line_is_json_with_request_id() -> None:
    token = request_id_var.set("req-123")
    try:
        line = JsonFormatter().format(_record("hello", path="/api/health/live"))
    finally:
        request_id_var.reset(token)
    entry = json.loads(line)
    assert entry["message"] == "hello"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "app.test"
    assert entry["request_id"] == "req-123"
    assert entry["path"] == "/api/health/live"
    assert entry["timestamp"].endswith("+00:00")


def test_NFR_08_log_line_without_request_context_has_no_request_id() -> None:
    entry = json.loads(JsonFormatter().format(_record("background")))
    assert "request_id" not in entry


def test_NFR_08_exceptions_are_included() -> None:
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        import sys

        record = _record("failed")
        record.exc_info = sys.exc_info()
    entry = json.loads(JsonFormatter().format(record))
    assert "RuntimeError: boom" in entry["exception"]


def test_NFR_08_configure_logging_installs_json_handler(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    logging.getLogger("app.test").info("configured")
    entry = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert entry["message"] == "configured"
    assert logging.getLogger("uvicorn.access").disabled
