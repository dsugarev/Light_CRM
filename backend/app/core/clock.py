"""Injectable clock: code asks the clock for "now" so tests can control time."""

from datetime import UTC, datetime, timedelta
from typing import Protocol

from fastapi import Request


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Test clock: fixed until moved with `advance`."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock
