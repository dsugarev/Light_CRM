"""Operator CLI and worker housekeeping against the real database."""

import io
from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import cli, worker
from app.core.config import get_settings
from app.modules.identity.models import UserSession
from tests.conftest import TEST_APP_DATABASE_URL
from tests.helpers import START, TestApp


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", TEST_APP_DATABASE_URL)
    monkeypatch.setenv("PUBLIC_URL", "https://crm.example.test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_create_admin_prints_a_one_time_link(
    test_app: TestApp, cli_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    code = await cli.create_admin("first.admin@example.test", "First Admin", "bg", None)
    assert code == 0
    out = capsys.readouterr().out
    assert "Created admin first.admin@example.test" in out
    assert "https://crm.example.test/set-password#token=" in out
    [entry] = await test_app.audit("user.created")
    assert entry.actor_type == "anonymous"


async def test_create_admin_with_password_from_stdin(
    test_app: TestApp, cli_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("Bootstrap-Admin-Pass-1\n"))
    with pytest.raises(SystemExit) as exit_info:
        await _run_main(
            [
                "create-admin",
                "--email",
                "boot@example.test",
                "--full-name",
                "Boot",
                "--password-stdin",
            ]
        )
    assert exit_info.value.code == 0
    response = await test_app.login(
        test_app.client(), "boot@example.test", "Bootstrap-Admin-Pass-1"
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"


async def _run_main(argv: list[str]) -> None:
    # cli.main calls asyncio.run, which cannot nest; run it in a worker thread.
    import asyncio

    await asyncio.to_thread(cli.main, argv)


async def test_create_admin_rejects_weak_password_and_duplicates(
    test_app: TestApp, cli_env: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert await cli.create_admin("weak@example.test", "Weak", "en", "short") == 1
    assert "password.too_short" in capsys.readouterr().err
    await test_app.create_user(email="taken@example.test")
    assert await cli.create_admin("taken@example.test", "Dup", "en", None) == 1
    assert "user.email_taken" in capsys.readouterr().err


async def test_housekeeping_removes_expired_sessions(test_app: TestApp) -> None:
    user = await test_app.create_user()
    async with test_app.sessions() as session:
        session.add_all(
            [
                UserSession(
                    user_id=user.id,
                    token_hash=f"{n:064d}",
                    created_at=START - timedelta(days=10),
                    last_seen_at=START - timedelta(days=10),
                    expires_at=START - timedelta(days=3) if n else START + timedelta(days=3),
                )
                for n in range(2)
            ]
        )
        await session.commit()
    await worker.purge_expired(test_app.app.state.engine)
    async with test_app.sessions() as session:
        remaining = (await session.execute(select(func.count()).select_from(UserSession))).scalar()
    # The worker uses the system clock: the session expiring 3 days after START stays.
    assert remaining == 1


async def test_every_limits_how_often_a_job_runs() -> None:
    calls = 0

    async def job(_: object) -> None:
        nonlocal calls
        calls += 1

    wrapped = worker.every(timedelta(hours=1), job)
    await wrapped(None)  # type: ignore[arg-type]
    await wrapped(None)  # type: ignore[arg-type]
    assert calls == 1
    assert wrapped.__name__ == "job"
