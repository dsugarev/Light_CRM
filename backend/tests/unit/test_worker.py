"""Background worker loop."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app import worker
from app.core.config import Settings


async def test_failing_job_does_not_stop_other_jobs(caplog: pytest.LogCaptureFixture) -> None:
    calls: list[str] = []

    async def broken(_: AsyncEngine) -> None:
        raise RuntimeError("boom")

    async def healthy(_: AsyncEngine) -> None:
        calls.append("healthy")

    await worker.run_once(None, [broken, healthy])  # type: ignore[arg-type]
    assert calls == ["healthy"]
    assert any(r.message == "job_failed" for r in caplog.records)


async def test_worker_runs_jobs_until_stopped() -> None:
    stop = asyncio.Event()
    runs = 0

    async def job(_: AsyncEngine) -> None:
        nonlocal runs
        runs += 1
        if runs == 2:
            stop.set()

    settings = Settings(worker_poll_interval_seconds=0.01)
    await asyncio.wait_for(worker.run(settings, stop, [job]), timeout=5)
    assert runs == 2
