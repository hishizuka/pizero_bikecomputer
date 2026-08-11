from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum

MAX_SPEED_MPS = 65.0
MAX_CADENCE_RPM = 255.0
MAX_POWER_WATTS = 65535.0
SPEED_SPIKE_THRESHOLD = 15.0
POWER_SPIKE_THRESHOLD = 500.0
REVOLUTION_SPIKE_THRESHOLD = 6553


class SensorConnectionStatus(str, Enum):
    INACTIVE = "inactive"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    SUSPENDED = "suspended"


def revolution_rate(
    revolution_delta: int,
    event_time_delta: int,
    event_time_hz: float,
) -> float:
    """Return revolutions per second from protocol counter deltas."""
    if revolution_delta < 0:
        raise ValueError("revolution_delta must not be negative")
    if event_time_delta <= 0:
        raise ValueError("event_time_delta must be positive")
    if event_time_hz <= 0 or not math.isfinite(event_time_hz):
        raise ValueError("event_time_hz must be positive")
    return revolution_delta * event_time_hz / event_time_delta


def counter_delta(current: int, previous: int, modulus: int) -> int:
    """Return a forward counter delta including one or more rollovers."""
    return (current - previous) % modulus


@dataclass(frozen=True, slots=True)
class MetricReading:
    """Protocol-neutral value with separate measurement and reception times."""

    value: float = math.nan
    measured_at: float | None = None
    received_at: float | None = None

    @property
    def is_available(self) -> bool:
        return math.isfinite(self.value)

    def is_fresh(self, max_age: float, now: float | None = None) -> bool:
        if max_age < 0:
            raise ValueError("max_age must not be negative")
        if not self.is_available or self.received_at is None:
            return False
        current = time.monotonic() if now is None else now
        return 0 <= current - self.received_at <= max_age
