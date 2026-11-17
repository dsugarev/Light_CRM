"""Background worker: `python -m app.worker`.

Runs registered jobs in a loop until SIGTERM/SIGINT. Webhook delivery from the
outbox (Phase 6) and housekeeping jobs are registered here as they are built.
"""

import asyncio
import contextlib
import logging
import signal
from collections.abc import Awaitable, Callable, Sequence

from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings, get_settings
from app.core.db import create_engine
from app.core.logging import configure_logging

Job = Callable[[AsyncEngine], Awaitable[None]]

# Jobs run once per poll interval, in order. Empty until Phase 6.
JOBS: Sequence[Job] = ()

logger = logging.getLogger("app.worker")


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
