from __future__ import annotations

import argparse
import asyncio
import contextlib
import math
import time
from typing import Protocol

from modules.sensor.cycling_sensor import (
    MAX_CADENCE_RPM,
    MAX_SPEED_MPS,
    REVOLUTION_SPIKE_THRESHOLD,
    SPEED_SPIKE_THRESHOLD,
    MetricReading,
    SensorConnectionStatus,
    counter_delta,
    revolution_rate,
)

from .health import BleMeasurementProcessor, BleSessionHealth

CSC_SERVICE_UUID = "00001816-0000-1000-8000-00805f9b34fb"
WHEEL_EVENT_TIME_MODULUS = 1 << 16
WHEEL_REVOLUTION_MODULUS = 1 << 32
CRANK_EVENT_TIME_MODULUS = 1 << 16
CRANK_REVOLUTION_MODULUS = 1 << 16
CSC_EVENT_TIME_HZ = 1024.0


class CscMeasurementLike(Protocol):
    cumulative_wheel_revs: int | None
    last_wheel_event_time: int | None
    cumulative_crank_revs: int | None
    last_crank_event_time: int | None


class CscSpeedProcessor(BleMeasurementProcessor):
    """Convert protocol counters into speed and distance without BLE dependencies."""

    def __init__(
        self,
        wheel_circumference: float,
        *,
        notification_interval: float = 1.0,
        health: BleSessionHealth | None = None,
    ):
        if wheel_circumference <= 0 or not math.isfinite(wheel_circumference):
            raise ValueError("wheel_circumference must be positive")
        if notification_interval <= 0:
            raise ValueError("notification_interval must be positive")
        self.wheel_circumference = wheel_circumference
        self.notification_interval = notification_interval
        super().__init__(health)
        self.speed = MetricReading()
        self.distance = 0.0
        self._previous_wheel: tuple[int, int] | None = None
        self._last_wheel_change_received_at: float | None = None
        self._last_event_interval: float | None = None
        self._stopped = False

    @property
    def has_baseline(self) -> bool:
        return self._previous_wheel is not None

    def set_suspended(self) -> None:
        self.status = SensorConnectionStatus.SUSPENDED
        self.speed = MetricReading()
        self._clear_measurement_baseline()

    def on_disconnected(self) -> None:
        self.status = SensorConnectionStatus.DISCONNECTED
        self.speed = MetricReading()
        self._clear_measurement_baseline()

    def reset_distance(self) -> None:
        self.distance = 0.0

    def handle_measurement(
        self,
        measurement: CscMeasurementLike,
        *,
        received_at: float | None = None,
        accumulate_distance: bool = True,
    ) -> None:
        timestamp = time.monotonic() if received_at is None else received_at
        self._record_notification(timestamp)

        wheel_revs = measurement.cumulative_wheel_revs
        wheel_event_time = measurement.last_wheel_event_time
        if wheel_revs is None or wheel_event_time is None:
            return

        self.status = SensorConnectionStatus.CONNECTED
        previous = self._previous_wheel
        if previous is None:
            self._set_baseline(wheel_revs, wheel_event_time, timestamp)
            self.speed = MetricReading(0.0, timestamp, timestamp)
            return

        previous_revs, previous_event_time = previous

        # A normal UINT32 rollover starts near the upper limit. Other decreases
        # are treated as a sensor reset to avoid a multi-billion-revolution jump.
        if wheel_revs < previous_revs and previous_revs < 0xF0000000:
            self._set_baseline(wheel_revs, wheel_event_time, timestamp)
            self.speed = MetricReading(0.0, timestamp, timestamp)
            return

        revolution_delta = counter_delta(
            wheel_revs, previous_revs, WHEEL_REVOLUTION_MODULUS
        )
        event_delta = counter_delta(
            wheel_event_time, previous_event_time, WHEEL_EVENT_TIME_MODULUS
        )
        self._previous_wheel = (wheel_revs, wheel_event_time)

        if revolution_delta == 0:
            self.speed = MetricReading(
                self.speed.value,
                self.speed.measured_at,
                timestamp,
            )
            return
        if event_delta == 0 or revolution_delta >= REVOLUTION_SPIKE_THRESHOLD:
            return

        speed = self.wheel_circumference * revolution_rate(
            revolution_delta,
            event_delta,
            CSC_EVENT_TIME_HZ,
        )
        if speed > MAX_SPEED_MPS:
            return
        if self.speed.is_available and (
            speed - self.speed.value >= SPEED_SPIKE_THRESHOLD
        ):
            return

        self._last_event_interval = event_delta / (CSC_EVENT_TIME_HZ * revolution_delta)
        self._last_wheel_change_received_at = timestamp
        self._stopped = False
        self.speed = MetricReading(speed, timestamp, timestamp)
        if accumulate_distance:
            self.distance += self.wheel_circumference * revolution_delta

    def tick(self, now: float | None = None) -> None:
        """Update the stopped state while preserving a live BLE connection."""
        if self.status != SensorConnectionStatus.CONNECTED:
            return
        if self._last_wheel_change_received_at is None:
            return
        timestamp = time.monotonic() if now is None else now
        event_interval = self._last_event_interval
        if event_interval is None:
            return
        stop_cutoff = event_interval * 2 + self.notification_interval * 2
        if timestamp - self._last_wheel_change_received_at < stop_cutoff:
            return
        if not self._stopped:
            self.speed = MetricReading(
                0.0,
                self._last_wheel_change_received_at + stop_cutoff,
                self.speed.received_at,
            )
            self._stopped = True

    def _set_baseline(
        self, wheel_revs: int, wheel_event_time: int, received_at: float
    ) -> None:
        self._previous_wheel = (wheel_revs, wheel_event_time)
        self._last_wheel_change_received_at = received_at
        self._last_event_interval = None
        self._stopped = False

    def _clear_measurement_baseline(self) -> None:
        """Rebase after a gap so fallback and sensor distance cannot overlap."""
        self._previous_wheel = None
        self._last_wheel_change_received_at = None
        self._last_event_interval = None
        self._stopped = False


class CscCadenceProcessor(BleMeasurementProcessor):
    """Convert protocol crank counters into cadence without BLE dependencies."""

    def __init__(
        self,
        *,
        notification_interval: float = 1.0,
        health: BleSessionHealth | None = None,
    ):
        if notification_interval <= 0:
            raise ValueError("notification_interval must be positive")
        self.notification_interval = notification_interval
        super().__init__(health)
        self.cadence = MetricReading()
        self._previous_crank: tuple[int, int] | None = None
        self._last_crank_change_received_at: float | None = None
        self._last_event_interval: float | None = None
        self._stopped = False

    @property
    def has_baseline(self) -> bool:
        return self._previous_crank is not None

    def set_suspended(self) -> None:
        self.status = SensorConnectionStatus.SUSPENDED
        self.cadence = MetricReading()
        self._clear_measurement_baseline()

    def on_disconnected(self) -> None:
        self.status = SensorConnectionStatus.DISCONNECTED
        self.cadence = MetricReading()
        self._clear_measurement_baseline()

    def handle_measurement(
        self,
        measurement: CscMeasurementLike,
        *,
        received_at: float | None = None,
    ) -> None:
        timestamp = time.monotonic() if received_at is None else received_at
        self._record_notification(timestamp)

        crank_revs = measurement.cumulative_crank_revs
        crank_event_time = measurement.last_crank_event_time
        if crank_revs is None or crank_event_time is None:
            return

        self.status = SensorConnectionStatus.CONNECTED
        previous = self._previous_crank
        if previous is None:
            self._set_baseline(crank_revs, crank_event_time, timestamp)
            self.cadence = MetricReading(0.0, timestamp, timestamp)
            return

        previous_revs, previous_event_time = previous

        if crank_revs < previous_revs and previous_revs < 0xF000:
            self._set_baseline(crank_revs, crank_event_time, timestamp)
            self.cadence = MetricReading(0.0, timestamp, timestamp)
            return

        revolution_delta = counter_delta(
            crank_revs,
            previous_revs,
            CRANK_REVOLUTION_MODULUS,
        )
        event_delta = counter_delta(
            crank_event_time,
            previous_event_time,
            CRANK_EVENT_TIME_MODULUS,
        )
        self._previous_crank = (crank_revs, crank_event_time)

        if revolution_delta == 0:
            self.cadence = MetricReading(
                self.cadence.value,
                self.cadence.measured_at,
                timestamp,
            )
            return
        if event_delta == 0 or revolution_delta >= REVOLUTION_SPIKE_THRESHOLD:
            return

        cadence = 60.0 * revolution_rate(
            revolution_delta,
            event_delta,
            CSC_EVENT_TIME_HZ,
        )
        if cadence > MAX_CADENCE_RPM:
            return

        self._last_event_interval = event_delta / (CSC_EVENT_TIME_HZ * revolution_delta)
        self._last_crank_change_received_at = timestamp
        self._stopped = False
        self.cadence = MetricReading(cadence, timestamp, timestamp)

    def tick(self, now: float | None = None) -> None:
        if self.status != SensorConnectionStatus.CONNECTED:
            return
        if self._last_crank_change_received_at is None:
            return
        timestamp = time.monotonic() if now is None else now
        event_interval = self._last_event_interval
        if event_interval is None:
            return
        stop_cutoff = event_interval * 2 + self.notification_interval * 2
        if timestamp - self._last_crank_change_received_at < stop_cutoff:
            return
        if not self._stopped:
            self.cadence = MetricReading(
                0.0,
                self._last_crank_change_received_at + stop_cutoff,
                self.cadence.received_at,
            )
            self._stopped = True

    def _set_baseline(
        self,
        crank_revs: int,
        crank_event_time: int,
        received_at: float,
    ) -> None:
        self._previous_crank = (crank_revs, crank_event_time)
        self._last_crank_change_received_at = received_at
        self._last_event_interval = None
        self._stopped = False

    def _clear_measurement_baseline(self) -> None:
        self._previous_crank = None
        self._last_crank_change_received_at = None
        self._last_event_interval = None
        self._stopped = False


async def _run_cli(args: argparse.Namespace) -> None:
    from .cycling import (
        BleCyclingSession,
        PROFILE_CSCS,
        discover_cycling_devices,
    )

    if not args.device:
        print("Scanning for Cycling Speed and Cadence Service devices...")
        print("Rotate the wheel during the scan if the sensor is asleep.")
        devices = await discover_cycling_devices(
            args.scan_seconds,
            profiles=(PROFILE_CSCS,),
        )
        if not devices:
            print("No CSCS devices found.")
            return
        for _device, candidate in devices:
            rssi = "?" if candidate.rssi is None else str(candidate.rssi)
            print(
                f"id={candidate.identifier} name={candidate.name or '(unknown)'} "
                f"rssi={rssi}"
            )
        return

    health = BleSessionHealth()
    processor = CscSpeedProcessor(args.wheel_circumference, health=health)
    session = BleCyclingSession(
        args.device,
        speed_processor=processor,
        scan_timeout=args.scan_seconds,
        log=lambda message: print(f"[CSCS] {message}"),
    )
    stop_event = asyncio.Event()
    session_task = asyncio.create_task(session.run(stop_event))
    started_at = time.monotonic()
    try:
        while args.duration <= 0 or time.monotonic() - started_at < args.duration:
            processor.tick()
            processor.report_notification_silence()
            speed = processor.speed.value
            speed_kmh = speed * 3.6 if math.isfinite(speed) else math.nan
            print(
                f"status={processor.status.value:12s} "
                f"speed={speed_kmh:6.1f} km/h distance={processor.distance:8.1f} m"
            )
            await asyncio.sleep(1.0)
    finally:
        stop_event.set()
        session_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await session_task
        print(f"health={health.snapshot().as_dict()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan or monitor a BLE CSCS sensor")
    parser.add_argument("--device", help="opaque Bleak/CoreBluetooth device identifier")
    parser.add_argument("--scan-seconds", type=float, default=15.0)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--wheel-circumference", type=float, default=2.105)
    asyncio.run(_run_cli(parser.parse_args()))


if __name__ == "__main__":
    main()
