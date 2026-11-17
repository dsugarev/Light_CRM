"""Background worker: `python -m app.worker`.

Runs registered jobs in a loop until SIGTERM/SIGINT. Webhook delivery from the
outbox (Phase 6) and housekeeping jobs are registered here as they are built.
"""

import asyncio
import contextlib
import logging
import signal
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core import ratelimit
from app.core.clock import SystemClock
from app.core.config import Settings, get_settings
from app.core.db import create_engine, create_session_factory
from app.core.logging import configure_logging
from app.modules.dataimport import service as dataimport_service
from app.modules.identity import service as identity_service

Job = Callable[[AsyncEngine], Awaitable[None]]

logger = logging.getLogger("app.worker")


def every(interval: timedelta, job: Job) -> Job:
    """Run `job` at most once per `interval` (the loop itself polls more often)."""
    last_run: float | None = None

    async def wrapper(engine: AsyncEngine) -> None:
        nonlocal last_run
        if last_run is not None and time.monotonic() - last_run < interval.total_seconds():
            return
        last_run = time.monotonic()
        await job(engine)

    wrapper.__name__ = getattr(job, "__name__", "job")
    return wrapper


async def purge_expired(engine: AsyncEngine) -> None:
    """Housekeeping: expired sessions, stale password tokens, old rate-limit windows and
    uploaded import files older than 7 days (API spec 15)."""
    now = SystemClock().now()
    async with create_session_factory(engine)() as session:
        removed = await identity_service.purge_expired(session, now)
        removed.update(await dataimport_service.purge_expired(session, now))
    removed["rate_limit_windows"] = await ratelimit.purge_expired(engine, now)
    logger.info("housekeeping_done", extra=removed)


# Jobs run once per poll interval, in order. Phase 6 adds webhook delivery.
JOBS: Sequence[Job] = (every(timedelta(hours=1), purge_expired),)


async def run_once(engine: AsyncEngine, jobs: Sequence[Job]) -> None:
    for job in jobs:
        try:
            await job(engine)
        except Exception:
            # One failing job must not stop the others or the worker.
            logger.exception("job_failed", extra={"job": getattr(job, "__name__", repr(job))})


async def run(settings: Settings, stop: asyncio.Event, jobs: Sequence[Job] = JOBS) -> None:
    engine = create_engine(settings)
    logger.info("worker_started", extra={"jobs": len(jobs)})
    try:
        while not stop.is_set():
            await run_once(engine, jobs)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_interval_seconds)
    finally:
        await engine.dispose()
        logger.info("worker_stopped")


async def _main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    await run(settings, stop)


if __name__ == "__main__":
    asyncio.run(_main())
