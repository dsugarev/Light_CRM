"""Operator CLI."""

import json
from pathlib import Path

import pytest

from app import cli


def test_FR_INT_10_export_openapi_writes_document(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"
    cli.main(["export-openapi", "--output", str(target)])
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["openapi"].startswith("3.1")
    assert "/api/health/ready" in document["paths"]


def test_export_openapi_defaults_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["export-openapi"])
    assert json.loads(capsys.readouterr().out)["info"]["title"] == "Light CRM API"


def test_command_is_required() -> None:
    with pytest.raises(SystemExit):
        cli.main([])
