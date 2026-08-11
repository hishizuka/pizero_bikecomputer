from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import asdict, dataclass

from modules.sensor.cycling_sensor import SensorConnectionStatus


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = position - lower_index
    return ordered[lower_index] * (1.0 - weight) + ordered[upper_index] * weight


@dataclass(frozen=True, slots=True)
class SampleSummary:
    count: int
    maximum: float
    p95: float
    p99: float


class RollingSamples:
    def __init__(self, max_samples: int = 4096):
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        self._values: deque[float] = deque(maxlen=max_samples)

    def record(self, value: float) -> None:
        if value < 0 or not math.isfinite(value):
            return
        self._values.append(value)

    def snapshot(self) -> SampleSummary:
        values = list(self._values)
        return SampleSummary(
            count=len(values),
            maximum=max(values, default=math.nan),
            p95=_percentile(values, 0.95),
            p99=_percentile(values, 0.99),
        )


@dataclass(frozen=True, slots=True)
class BleSessionHealthSnapshot:
    notification_count: int
    non_monotonic_timestamp_count: int
    connect_attempt_count: int
    connect_success_count: int
    connect_failure_count: int
    unexpected_disconnect_count: int
    stale_transition_count: int
    notification_gap: SampleSummary
    reconnect_duration: SampleSummary

    def as_dict(self) -> dict:
        return asdict(self)


class BleSessionHealth:
    """Keep low-overhead in-memory BLE counters for later load analysis."""

    def __init__(self, max_samples: int = 4096):
        self.notification_count = 0
        self.non_monotonic_timestamp_count = 0
        self.connect_attempt_count = 0
        self.connect_success_count = 0
        self.connect_failure_count = 0
        self.unexpected_disconnect_count = 0
        self.stale_transition_count = 0
        self._last_notification_at: float | None = None
        self._disconnected_at: float | None = None
        self._notification_gaps = RollingSamples(max_samples)
        self._reconnect_durations = RollingSamples(max_samples)

    def record_notification(self, received_at: float | None = None) -> None:
        timestamp = time.monotonic() if received_at is None else received_at
        self.notification_count += 1
        if self._last_notification_at is not None:
            gap = timestamp - self._last_notification_at
            if gap < 0:
                self.non_monotonic_timestamp_count += 1
            else:
                self._notification_gaps.record(gap)
        self._last_notification_at = timestamp

    def record_connect_attempt(self) -> None:
        self.connect_attempt_count += 1

    def record_connected(self, connected_at: float | None = None) -> None:
        timestamp = time.monotonic() if connected_at is None else connected_at
        self.connect_success_count += 1
        if self._disconnected_at is not None:
            self._reconnect_durations.record(timestamp - self._disconnected_at)
            self._disconnected_at = None

    def record_connect_failure(self) -> None:
        self.connect_failure_count += 1

    def record_unexpected_disconnect(
        self, disconnected_at: float | None = None
    ) -> None:
        self.unexpected_disconnect_count += 1
        self._disconnected_at = (
            time.monotonic() if disconnected_at is None else disconnected_at
        )

    def record_stale_transition(self) -> None:
        self.stale_transition_count += 1

    def snapshot(self) -> BleSessionHealthSnapshot:
        return BleSessionHealthSnapshot(
            notification_count=self.notification_count,
            non_monotonic_timestamp_count=self.non_monotonic_timestamp_count,
            connect_attempt_count=self.connect_attempt_count,
            connect_success_count=self.connect_success_count,
            connect_failure_count=self.connect_failure_count,
            unexpected_disconnect_count=self.unexpected_disconnect_count,
            stale_transition_count=self.stale_transition_count,
            notification_gap=self._notification_gaps.snapshot(),
            reconnect_duration=self._reconnect_durations.snapshot(),
        )


class BleMeasurementProcessor:
    """Share connection and notification health state across BLE profiles."""

    notification_silence_cutoff = 5.0

    def __init__(self, health: BleSessionHealth | None):
        self.health = health
        self.status = SensorConnectionStatus.INACTIVE
        self._last_notification_received_at: float | None = None
        self._stale_reported = False

    def set_connecting(self) -> None:
        self.status = SensorConnectionStatus.CONNECTING

    def set_connected(self) -> None:
        self.status = SensorConnectionStatus.CONNECTED
        self._last_notification_received_at = None
        self._stale_reported = False

    def _record_notification(self, received_at: float) -> None:
        self._last_notification_received_at = received_at
        self._stale_reported = False
        if self.health is not None:
            self.health.record_notification(received_at)

    def report_notification_silence(
        self,
        now: float | None = None,
        *,
        cutoff: float | None = None,
    ) -> None:
        if self.status != SensorConnectionStatus.CONNECTED:
            return
        if self._last_notification_received_at is None or self._stale_reported:
            return
        timestamp = time.monotonic() if now is None else now
        silence_cutoff = self.notification_silence_cutoff if cutoff is None else cutoff
        if timestamp - self._last_notification_received_at < silence_cutoff:
            return
        if self.health is not None:
            self.health.record_stale_transition()
        self._stale_reported = True
