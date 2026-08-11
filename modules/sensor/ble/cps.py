from __future__ import annotations

import argparse
import asyncio
import contextlib
import math
import time
from typing import Protocol

from modules.sensor.cycling_sensor import (
    MAX_POWER_WATTS,
    POWER_SPIKE_THRESHOLD,
    MetricReading,
    SensorConnectionStatus,
)

from .health import BleMeasurementProcessor, BleSessionHealth

CPS_SERVICE_UUID = "00001818-0000-1000-8000-00805f9b34fb"
POWER_STALE_CUTOFF = 3.0
MAX_WORK_INTERVAL = 10.0


class CpsMeasurementLike(Protocol):
    instantaneous_power: int
    cumulative_crank_revs: int | None
    last_crank_event_time: int | None


def signed_instantaneous_power(raw_power: int) -> int:
    """Correct pycycling's unsigned CPS instantaneous power decode."""
    if not 0 <= raw_power <= 0xFFFF:
        raise ValueError("instantaneous_power must be a uint16 value")
    signed_power = raw_power - 0x10000 if raw_power & 0x8000 else raw_power
    return max(0, signed_power)


class CpsPowerProcessor(BleMeasurementProcessor):
    """Normalize CPS instantaneous power and accumulate recording work."""

    def __init__(
        self,
        *,
        spike_threshold: float = POWER_SPIKE_THRESHOLD,
        stale_cutoff: float = POWER_STALE_CUTOFF,
        health: BleSessionHealth | None = None,
    ):
        if spike_threshold <= 0 or not math.isfinite(spike_threshold):
            raise ValueError("spike_threshold must be positive")
        if stale_cutoff <= 0 or not math.isfinite(stale_cutoff):
            raise ValueError("stale_cutoff must be positive")
        self.spike_threshold = spike_threshold
        self.stale_cutoff = stale_cutoff
        super().__init__(health)
        self.power = MetricReading()
        self.accumulated_power = 0.0
        self._last_work_received_at: float | None = None

    def set_connected(self) -> None:
        super().set_connected()
        self._last_work_received_at = None

    def set_suspended(self) -> None:
        self.status = SensorConnectionStatus.SUSPENDED
        self.power = MetricReading()
        self._last_work_received_at = None

    def on_disconnected(self) -> None:
        self.status = SensorConnectionStatus.DISCONNECTED
        self.power = MetricReading()
        self._last_work_received_at = None

    def reset_accumulated_power(self) -> None:
        self.accumulated_power = 0.0
        self._last_work_received_at = None

    def handle_measurement(
        self,
        measurement: CpsMeasurementLike,
        *,
        received_at: float | None = None,
        accumulate_work: bool = True,
    ) -> None:
        timestamp = time.monotonic() if received_at is None else received_at
        self._record_notification(timestamp)

        power = float(signed_instantaneous_power(measurement.instantaneous_power))
        if power > MAX_POWER_WATTS:
            self._mark_work_boundary(timestamp, accumulate_work)
            return
        if self.power.is_available:
            if power - self.power.value >= self.spike_threshold:
                self._mark_work_boundary(timestamp, accumulate_work)
                return
        elif power >= self.spike_threshold:
            self._mark_work_boundary(timestamp, accumulate_work)
            return

        self.status = SensorConnectionStatus.CONNECTED
        if accumulate_work and self._last_work_received_at is not None:
            interval = timestamp - self._last_work_received_at
            if 0 < interval <= MAX_WORK_INTERVAL:
                self.accumulated_power += power * interval
        self._last_work_received_at = timestamp if accumulate_work else None
        self.power = MetricReading(power, timestamp, timestamp)

    def tick(self, now: float | None = None) -> None:
        if self.status != SensorConnectionStatus.CONNECTED:
            return
        if self._last_notification_received_at is None:
            return
        timestamp = time.monotonic() if now is None else now
        if timestamp - self._last_notification_received_at < self.stale_cutoff:
            return
        self.power = MetricReading()
        self._last_work_received_at = None

    def _mark_work_boundary(self, timestamp: float, accumulate_work: bool) -> None:
        self._last_work_received_at = timestamp if accumulate_work else None


async def _run_cli(args: argparse.Namespace) -> None:
    from .cycling import (
        BleCyclingSession,
        PROFILE_CPS,
        discover_cycling_devices,
    )

    if not args.device:
        print("Scanning for Cycling Power Service devices...")
        devices = await discover_cycling_devices(
            args.scan_seconds,
            adapter=args.adapter,
            profiles=(PROFILE_CPS,),
        )
        if not devices:
            print("No CPS devices found.")
            return
        for _device, candidate in devices:
            rssi = "?" if candidate.rssi is None else str(candidate.rssi)
            print(
                f"id={candidate.identifier} name={candidate.name or '(unknown)'} "
                f"rssi={rssi}"
            )
        return

    health = BleSessionHealth()
    processor = CpsPowerProcessor(health=health)
    session = BleCyclingSession(
        args.device,
        power_processor=processor,
        adapter=args.adapter,
        scan_timeout=args.scan_seconds,
        should_accumulate=lambda: True,
        log=lambda message: print(f"[CPS] {message}"),
    )
    stop_event = asyncio.Event()
    session_task = asyncio.create_task(session.run(stop_event))
    started_at = time.monotonic()
    try:
        while args.duration <= 0 or time.monotonic() - started_at < args.duration:
            processor.tick()
            processor.report_notification_silence()
            print(
                f"status={processor.status.value:12s} "
                f"power={processor.power.value:6.0f} W "
                f"work={processor.accumulated_power:8.0f} J"
            )
            await asyncio.sleep(1.0)
    finally:
        stop_event.set()
        session_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await session_task
        print(f"health={health.snapshot().as_dict()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan or monitor a BLE CPS sensor")
    parser.add_argument("--device", help="opaque Bleak/CoreBluetooth device identifier")
    parser.add_argument("--adapter", help="BlueZ adapter, for example hci0")
    parser.add_argument("--scan-seconds", type=float, default=15.0)
    parser.add_argument("--duration", type=float, default=60.0)
    asyncio.run(_run_cli(parser.parse_args()))


if __name__ == "__main__":
    main()
