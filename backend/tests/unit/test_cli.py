"""Operator CLI."""

import json
from pathlib import Path

import pytest
from pydantic import PostgresDsn

from app import cli
from app.core.config import Environment, Settings


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


def test_NFR_01_seed_demo_is_refused_in_production(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    production = Settings(
        env=Environment.PRODUCTION,
        database_url=PostgresDsn("postgresql+asyncpg://crm_app:s3cr3t@db:5432/crm"),
        app_secret_key="x" * 48,
        app_encryption_key="y" * 48,
    )
    monkeypatch.setattr(cli, "get_settings", lambda: production)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["seed-demo", "--organizations", "1"])
    assert stopped.value.code == 1
    assert "not available in production" in capsys.readouterr().err
