"""Clock boundary used by business rules and deterministic tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current instant as an aware UTC datetime."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Deterministic clock for isolated replay tests."""

    def __init__(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("FixedClock requires an aware datetime")
        self._value = value.astimezone(UTC)

    def now(self) -> datetime:
        return self._value
