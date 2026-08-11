from __future__ import annotations

import argparse
import asyncio
import contextlib
import math
import time
from typing import Protocol

from modules.sensor.cycling_sensor import MetricReading, SensorConnectionStatus

from .health import BleMeasurementProcessor, BleSessionHealth

HRS_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
MAX_HEART_RATE = 255
HEART_RATE_STALE_CUTOFF = 15.0
RR_INTERVAL_HZ = 1024.0


class HeartRateMeasurementLike(Protocol):
    sensor_contact: bool | None
    bpm: int
    rr_interval: list[int] | tuple[int, ...]
    energy_expended: int | None


class HrsHeartRateProcessor(BleMeasurementProcessor):
    """Normalize HRS measurements to the existing heart-rate value boundary."""

    notification_silence_cutoff = HEART_RATE_STALE_CUTOFF

    def __init__(
        self,
        *,
        stale_cutoff: float = HEART_RATE_STALE_CUTOFF,
        health: BleSessionHealth | None = None,
    ):
        if stale_cutoff <= 0 or not math.isfinite(stale_cutoff):
            raise ValueError("stale_cutoff must be positive")
        self.stale_cutoff = stale_cutoff
        super().__init__(health)
        self.heart_rate = MetricReading()
        self.sensor_contact: bool | None = None
        self.energy_expended: int | None = None
        self.rr_intervals: tuple[float, ...] = ()

    def set_suspended(self) -> None:
        self.status = SensorConnectionStatus.SUSPENDED
        self._clear_reading()

    def on_disconnected(self) -> None:
        self.status = SensorConnectionStatus.DISCONNECTED
        self._clear_reading()

    def handle_measurement(
        self,
        measurement: HeartRateMeasurementLike,
        *,
        received_at: float | None = None,
    ) -> None:
        timestamp = time.monotonic() if received_at is None else received_at
        self._record_notification(timestamp)

        self.status = SensorConnectionStatus.CONNECTED
        self.heart_rate = MetricReading(
            float(min(measurement.bpm, MAX_HEART_RATE)),
            timestamp,
            timestamp,
        )
        self.sensor_contact = measurement.sensor_contact
        self.energy_expended = measurement.energy_expended
        self.rr_intervals = tuple(
            raw_interval / RR_INTERVAL_HZ for raw_interval in measurement.rr_interval
        )

    def tick(self, now: float | None = None) -> None:
        if self.status != SensorConnectionStatus.CONNECTED:
            return
        if self._last_notification_received_at is None:
            return
        timestamp = time.monotonic() if now is None else now
        if timestamp - self._last_notification_received_at < self.stale_cutoff:
            return
        self._clear_reading()

    def _clear_reading(self) -> None:
        self.heart_rate = MetricReading()
        self.sensor_contact = None
        self.energy_expended = None
        self.rr_intervals = ()


async def _run_cli(args: argparse.Namespace) -> None:
    from .cycling import (
        BleCyclingSession,
        PROFILE_HRS,
        discover_cycling_devices,
    )

    if not args.device:
        print("Scanning for Heart Rate Service devices...")
        devices = await discover_cycling_devices(
            args.scan_seconds,
            adapter=args.adapter,
            profiles=(PROFILE_HRS,),
        )
        if not devices:
            print("No HRS devices found.")
            return
        for _device, candidate in devices:
            rssi = "?" if candidate.rssi is None else str(candidate.rssi)
            print(
                f"id={candidate.identifier} name={candidate.name or '(unknown)'} "
                f"rssi={rssi}"
            )
        return

    health = BleSessionHealth()
    processor = HrsHeartRateProcessor(health=health)
    session = BleCyclingSession(
        args.device,
        heart_rate_processor=processor,
        adapter=args.adapter,
        scan_timeout=args.scan_seconds,
        log=lambda message: print(f"[HRS] {message}"),
    )
    stop_event = asyncio.Event()
    session_task = asyncio.create_task(session.run(stop_event))
    started_at = time.monotonic()
    try:
        while args.duration <= 0 or time.monotonic() - started_at < args.duration:
            processor.tick()
            processor.report_notification_silence()
            rr_text = ",".join(f"{value:.3f}" for value in processor.rr_intervals)
            print(
                f"status={processor.status.value:12s} "
                f"heart_rate={processor.heart_rate.value:5.0f} bpm "
                f"contact={processor.sensor_contact} rr=[{rr_text}] s"
            )
            await asyncio.sleep(1.0)
    finally:
        stop_event.set()
        session_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await session_task
        print(f"health={health.snapshot().as_dict()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan or monitor a BLE HRS sensor")
    parser.add_argument("--device", help="opaque Bleak/CoreBluetooth device identifier")
    parser.add_argument("--adapter", help="BlueZ adapter, for example hci0")
    parser.add_argument("--scan-seconds", type=float, default=15.0)
    parser.add_argument("--duration", type=float, default=60.0)
    asyncio.run(_run_cli(parser.parse_args()))


if __name__ == "__main__":
    main()
