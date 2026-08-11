from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import json
import math
import signal
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from modules.sensor.ble.adapter import (
    BleAdapterPolicy,
    BleAdapterResolutionError,
    BleAdapterResolver,
)
from modules.sensor.ble.csc import CscSpeedProcessor
from modules.sensor.ble.cycling import (
    BleCyclingSession,
    PROFILE_CSCS,
    discover_cycling_devices,
)
from modules.sensor.ble.health import BleSessionHealth

CSV_FIELDS = (
    "elapsed_s",
    "timestamp",
    "ant_status",
    "ble_status",
    "ant_speed_mps",
    "ble_speed_mps",
    "speed_diff_mps",
    "ant_distance_m",
    "ble_distance_m",
    "distance_diff_m",
    "ant_event_age_s",
    "ant_packet_age_s",
    "ble_measurement_age_s",
    "ble_notification_age_s",
    "ant_motion_state",
    "ble_motion_state",
)


class MemoryState:
    """Prevent a diagnostic run from reading or writing ride resume state."""

    def __init__(self):
        self.values = {}

    def get_value(self, key, default_value):
        return self.values.get(key, default_value)

    def set_value(self, key, value, force_apply=False):
        self.values[key] = value


@dataclass(frozen=True, slots=True)
class SpeedSample:
    speed: float = math.nan
    distance: float = math.nan
    event_age: float = math.nan
    packet_age: float = math.nan
    status: str = "inactive"


@dataclass(frozen=True, slots=True)
class MotionTransition:
    source: str
    state: str
    elapsed_s: float


def _is_finite(value) -> bool:
    try:
        return math.isfinite(value)
    except (TypeError, ValueError):
        return False


def _age_from_datetime(value: datetime | None, now: datetime) -> float:
    if value is None:
        return math.nan
    return max(0.0, (now - value).total_seconds())


def _age_from_monotonic(value: float | None, now: float) -> float:
    if value is None:
        return math.nan
    return max(0.0, now - value)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


class SpeedComparisonStats:
    def __init__(
        self,
        *,
        moving_cutoff: float = 0.5,
        stopped_cutoff: float = 0.05,
    ):
        if stopped_cutoff < 0 or moving_cutoff <= stopped_cutoff:
            raise ValueError("motion cutoffs must define a positive hysteresis")
        self.moving_cutoff = moving_cutoff
        self.stopped_cutoff = stopped_cutoff
        self.speed_differences: list[float] = []
        self.moving_speed_differences: list[float] = []
        self.transitions: list[MotionTransition] = []
        self._motion_states = {"ANT+": "unknown", "BLE": "unknown"}
        self._armed = False
        self._has_moved = False
        self.final_distance_difference = math.nan
        self.settled_distance_difference = math.nan

    def record(
        self,
        elapsed_s: float,
        ant_speed: float,
        ble_speed: float,
        ant_distance: float,
        ble_distance: float,
    ) -> tuple[str, str]:
        both_available = _is_finite(ant_speed) and _is_finite(ble_speed)
        if both_available:
            self.speed_differences.append(ble_speed - ant_speed)
        if _is_finite(ant_distance) and _is_finite(ble_distance):
            self.final_distance_difference = ble_distance - ant_distance

        if both_available and not self._armed:
            self._motion_states["ANT+"] = self._classify_motion(ant_speed, "unknown")
            self._motion_states["BLE"] = self._classify_motion(ble_speed, "unknown")
            self._armed = True
        if both_available:
            ant_state = self._record_motion("ANT+", ant_speed, elapsed_s)
            ble_state = self._record_motion("BLE", ble_speed, elapsed_s)
            if ant_state == "moving" and ble_state == "moving":
                self._has_moved = True
                self.moving_speed_differences.append(ble_speed - ant_speed)
            elif (
                self._has_moved
                and ant_state == "stopped"
                and ble_state == "stopped"
                and _is_finite(ant_distance)
                and _is_finite(ble_distance)
            ):
                self.settled_distance_difference = ble_distance - ant_distance
        else:
            ant_state = self._motion_states["ANT+"]
            ble_state = self._motion_states["BLE"]
        return ant_state, ble_state

    def _classify_motion(self, speed: float, previous: str) -> str:
        if speed >= self.moving_cutoff:
            return "moving"
        if speed <= self.stopped_cutoff:
            return "stopped"
        return previous

    def _record_motion(self, source: str, speed: float, elapsed_s: float) -> str:
        previous = self._motion_states[source]
        if not _is_finite(speed):
            return previous
        current = self._classify_motion(speed, previous)
        if current != previous:
            if previous != "unknown":
                self.transitions.append(MotionTransition(source, current, elapsed_s))
            self._motion_states[source] = current
        return current

    def transition_differences(self) -> list[dict]:
        ant = [
            transition for transition in self.transitions if transition.source == "ANT+"
        ]
        ble = [
            transition for transition in self.transitions if transition.source == "BLE"
        ]
        differences = []
        ant_index = 0
        ble_index = 0
        while ant_index < len(ant) and ble_index < len(ble):
            ant_transition = ant[ant_index]
            ble_transition = ble[ble_index]
            if ant_transition.state == ble_transition.state:
                differences.append(
                    {
                        "state": ant_transition.state,
                        "ant_elapsed_s": ant_transition.elapsed_s,
                        "ble_elapsed_s": ble_transition.elapsed_s,
                        "ble_minus_ant_s": (
                            ble_transition.elapsed_s - ant_transition.elapsed_s
                        ),
                    }
                )
                ant_index += 1
                ble_index += 1
            elif ant_transition.elapsed_s < ble_transition.elapsed_s:
                ant_index += 1
            else:
                ble_index += 1
        return differences

    def summary(self) -> dict:
        all_speed = self._speed_summary(self.speed_differences)
        moving_speed = self._speed_summary(self.moving_speed_differences)
        return {
            "paired_sample_count": all_speed["count"],
            "speed_bias_mps": all_speed["bias_mps"],
            "speed_mae_mps": all_speed["mae_mps"],
            "speed_rmse_mps": all_speed["rmse_mps"],
            "speed_abs_p95_mps": all_speed["abs_p95_mps"],
            "speed_abs_max_mps": all_speed["abs_max_mps"],
            "moving_paired_sample_count": moving_speed["count"],
            "moving_speed_bias_mps": moving_speed["bias_mps"],
            "moving_speed_mae_mps": moving_speed["mae_mps"],
            "moving_speed_rmse_mps": moving_speed["rmse_mps"],
            "moving_speed_abs_p95_mps": moving_speed["abs_p95_mps"],
            "moving_speed_abs_max_mps": moving_speed["abs_max_mps"],
            "final_distance_difference_m": self.final_distance_difference,
            "settled_distance_difference_m": self.settled_distance_difference,
            "transitions": [asdict(transition) for transition in self.transitions],
            "transition_differences": self.transition_differences(),
        }

    @staticmethod
    def _speed_summary(differences: list[float]) -> dict:
        absolute = [abs(value) for value in differences]
        squared = [value * value for value in differences]
        count = len(differences)
        return {
            "count": count,
            "bias_mps": sum(differences) / count if count else math.nan,
            "mae_mps": sum(absolute) / count if count else math.nan,
            "rmse_mps": (math.sqrt(sum(squared) / count) if count else math.nan),
            "abs_p95_mps": _percentile(absolute, 0.95),
            "abs_max_mps": max(absolute, default=math.nan),
        }


def _resolve_adapter(policy: BleAdapterPolicy | str) -> str | None:
    if not sys.platform.startswith("linux"):
        return None
    return BleAdapterResolver().resolve(policy)


def _make_output_paths(output: str | None) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if output:
        csv_path = Path(output)
    else:
        directory = Path("tmp") / f"{datetime.now():%Y%m%d}-ble-ant-speed-compare"
        csv_path = directory / f"speed-compare-{timestamp}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    return csv_path, csv_path.with_suffix(".summary.json")


def _load_project_config(keep_all_ant: bool):
    from modules.config import Config

    original_argv = sys.argv
    sys.argv = [original_argv[0], "--gui", "None"]
    try:
        config = Config()
    finally:
        sys.argv = original_argv

    config.state = MemoryState()
    config.gui = None
    config.G_DUMMY_OUTPUT = False
    config.G_MANUAL_STATUS = "START"
    config.G_STOPWATCH_STATUS = "START"
    if not keep_all_ant:
        for role in config.G_SENSORS:
            if role != "SPD":
                config.clear_sensor(role)
    return config


def _override_ant_speed_binding(config, ant_device: int, ant_type: int) -> None:
    if not (0 < ant_device <= 0xFFFF):
        raise ValueError("ANT device ID must be between 1 and 65535")
    if ant_type not in config.G_ANT_SENSOR_TYPES["SPD"]:
        raise ValueError(f"ANT type 0x{ant_type:02X} is not a speed profile")
    config.set_sensor("SPD", config.SENSOR_PROTOCOL_ANT, ant_device, ant_type)


def _ant_speed_values(sensor_ant, config) -> dict:
    ant_id_type = config.get_ant_id_type("SPD")
    values = sensor_ant.values.get(ant_id_type, {})
    if config.G_SENSORS["SPD"]["TYPE"] == 0x0B:
        values = values.get(0x11, {})
    return values


def _read_ant_sample(sensor_ant, config, now: datetime) -> SpeedSample:
    status = sensor_ant.get_sensor_connection_status("SPD")
    values = _ant_speed_values(sensor_ant, config)
    packet_timestamp = values.get("on_data_timestamp")
    if packet_timestamp is None:
        return SpeedSample(status=status)
    return SpeedSample(
        speed=values.get("speed", math.nan),
        distance=values.get("distance", math.nan),
        event_age=_age_from_datetime(values.get("timestamp"), now),
        packet_age=_age_from_datetime(packet_timestamp, now),
        status=status,
    )


def _read_ble_sample(processor: CscSpeedProcessor, now: float) -> SpeedSample:
    reading = processor.speed
    return SpeedSample(
        speed=reading.value,
        distance=processor.distance,
        event_age=_age_from_monotonic(reading.measured_at, now),
        packet_age=_age_from_monotonic(reading.received_at, now),
        status=processor.status.value,
    )


def _csv_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return value


async def scan(args: argparse.Namespace) -> int:
    try:
        adapter = _resolve_adapter(args.adapter_policy)
    except BleAdapterResolutionError as exc:
        print(f"Adapter resolution failed: {exc}", file=sys.stderr)
        return 2
    print(f"Scanning CSCS devices on {adapter or 'platform default'}...")
    print("Rotate the wheel during the scan if the sensor is asleep.")
    devices = await discover_cycling_devices(
        args.scan_seconds,
        adapter=adapter,
        profiles=(PROFILE_CSCS,),
    )
    if not devices:
        print("No CSCS devices found.")
        return 1
    for _device, candidate in devices:
        rssi = "?" if candidate.rssi is None else candidate.rssi
        print(
            f"id={candidate.identifier} name={candidate.name or '(unknown)'} "
            f"rssi={rssi}"
        )
    return 0


async def scan_ant(args: argparse.Namespace) -> int:
    from modules.sensor.sensor_ant import SensorANT

    config = _load_project_config(keep_all_ant=False)
    config._loop = asyncio.get_running_loop()
    for role in config.G_SENSORS:
        config.clear_sensor(role)
    ant_values = {}
    sensor_ant = SensorANT(config, ant_values)
    if not sensor_ant.is_transport_available():
        print("ANT+ transport is unavailable.", file=sys.stderr)
        sensor_ant.quit()
        return 2

    ant_task = asyncio.create_task(sensor_ant.start())
    previous = None
    started_at = time.monotonic()
    print("Scanning ANT+ speed profiles. Rotate the target sensor wheel.")
    try:
        await asyncio.sleep(0.5)
        sensor_ant.searcher.search("SPD")
        while time.monotonic() - started_at < args.scan_seconds:
            detected = dict(sensor_ant.searcher.getSearchList() or {})
            if detected != previous:
                for ant_id, (ant_type, already_connected) in sorted(detected.items()):
                    print(
                        f"id={ant_id} type=0x{ant_type:02X} "
                        f"already_connected={already_connected}"
                    )
                previous = detected
            await asyncio.sleep(0.25)
    finally:
        sensor_ant.searcher.stop_search()
        sensor_ant.quit()
        with contextlib.suppress(asyncio.CancelledError):
            await ant_task
    if not previous:
        print("No ANT+ speed sensors found.")
        return 1
    return 0


async def compare(args: argparse.Namespace) -> int:
    from modules.sensor.sensor_ant import SensorANT

    config = _load_project_config(args.keep_all_ant)
    config._loop = asyncio.get_running_loop()
    if args.ant_device is not None:
        try:
            _override_ant_speed_binding(config, args.ant_device, args.ant_type)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if not config.G_ANT["STATUS"] or not config.is_sensor_configured(
        "SPD", config.SENSOR_PROTOCOL_ANT
    ):
        print("Configured ANT+ speed sensor is not available.", file=sys.stderr)
        return 2

    try:
        adapter = _resolve_adapter(args.adapter_policy)
    except BleAdapterResolutionError as exc:
        print(f"Adapter resolution failed: {exc}", file=sys.stderr)
        return 2

    csv_path, summary_path = _make_output_paths(args.output)
    ant_values = {}
    sensor_ant = SensorANT(config, ant_values)
    if not sensor_ant.is_sensor_available("SPD"):
        print(
            "ANT+ transport or configured speed sensor is unavailable.", file=sys.stderr
        )
        sensor_ant.quit()
        return 2

    health = BleSessionHealth()
    processor = CscSpeedProcessor(
        args.wheel_circumference or config.G_WHEEL_CIRCUMFERENCE,
        health=health,
    )
    ble_stop_event = asyncio.Event()
    ble_session = BleCyclingSession(
        args.ble_device,
        speed_processor=processor,
        adapter=adapter,
        scan_timeout=args.scan_seconds,
        should_accumulate=lambda: True,
        log=lambda message: print(f"[BLE-CSCS] {message}"),
    )
    ant_task = asyncio.create_task(sensor_ant.start())
    ble_task = asyncio.create_task(ble_session.run(ble_stop_event))
    run_stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signal_name, run_stop_event.set)

    stats = SpeedComparisonStats(
        moving_cutoff=args.moving_cutoff,
        stopped_cutoff=args.stopped_cutoff,
    )
    started_at = time.monotonic()
    ant_distance_base = None
    ble_distance_base = None
    next_progress_at = started_at
    print(f"ANT+ speed ID: {config.G_SENSORS['SPD']['ID']}")
    print(f"BLE device: {args.ble_device}")
    print(f"BLE adapter: {adapter or 'platform default'}")
    print(f"CSV: {csv_path}")
    print("Rotate, stop, and rotate the wheel again. Press Ctrl-C to finish.")

    try:
        with csv_path.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=CSV_FIELDS)
            writer.writeheader()
            while not run_stop_event.is_set():
                monotonic_now = time.monotonic()
                elapsed_s = monotonic_now - started_at
                if args.duration > 0 and elapsed_s >= args.duration:
                    break
                datetime_now = datetime.now()
                processor.tick(monotonic_now)
                processor.report_notification_silence(monotonic_now)
                ant = _read_ant_sample(sensor_ant, config, datetime_now)
                ble = _read_ble_sample(processor, monotonic_now)

                if (
                    ant_distance_base is None
                    and _is_finite(ant.distance)
                    and _is_finite(ble.distance)
                    and _is_finite(ant.speed)
                    and _is_finite(ble.speed)
                    and ant.status == "connected"
                    and ble.status == "connected"
                    and processor.has_baseline
                ):
                    ant_distance_base = ant.distance
                    ble_distance_base = ble.distance
                ant_distance = (
                    ant.distance - ant_distance_base
                    if ant_distance_base is not None and _is_finite(ant.distance)
                    else math.nan
                )
                ble_distance = (
                    ble.distance - ble_distance_base
                    if ble_distance_base is not None and _is_finite(ble.distance)
                    else math.nan
                )
                ant_motion, ble_motion = stats.record(
                    elapsed_s,
                    ant.speed,
                    ble.speed,
                    ant_distance,
                    ble_distance,
                )
                speed_difference = (
                    ble.speed - ant.speed
                    if _is_finite(ant.speed) and _is_finite(ble.speed)
                    else math.nan
                )
                distance_difference = (
                    ble_distance - ant_distance
                    if _is_finite(ant_distance) and _is_finite(ble_distance)
                    else math.nan
                )
                row = {
                    "elapsed_s": f"{elapsed_s:.3f}",
                    "timestamp": datetime_now.astimezone().isoformat(),
                    "ant_status": ant.status,
                    "ble_status": ble.status,
                    "ant_speed_mps": ant.speed,
                    "ble_speed_mps": ble.speed,
                    "speed_diff_mps": speed_difference,
                    "ant_distance_m": ant_distance,
                    "ble_distance_m": ble_distance,
                    "distance_diff_m": distance_difference,
                    "ant_event_age_s": ant.event_age,
                    "ant_packet_age_s": ant.packet_age,
                    "ble_measurement_age_s": ble.event_age,
                    "ble_notification_age_s": ble.packet_age,
                    "ant_motion_state": ant_motion,
                    "ble_motion_state": ble_motion,
                }
                writer.writerow({key: _csv_value(value) for key, value in row.items()})

                if monotonic_now >= next_progress_at:
                    ant_kmh = ant.speed * 3.6 if _is_finite(ant.speed) else math.nan
                    ble_kmh = ble.speed * 3.6 if _is_finite(ble.speed) else math.nan
                    print(
                        f"t={elapsed_s:6.1f}s "
                        f"ANT={ant_kmh:6.1f} BLE={ble_kmh:6.1f} km/h "
                        f"ANT:{ant.status} BLE:{ble.status}"
                    )
                    next_progress_at = monotonic_now + 1.0
                try:
                    await asyncio.wait_for(
                        run_stop_event.wait(),
                        timeout=args.sample_interval,
                    )
                except asyncio.TimeoutError:
                    pass
    finally:
        ble_stop_event.set()
        ble_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ble_task
        sensor_ant.quit()
        with contextlib.suppress(asyncio.CancelledError):
            await ant_task

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "csv": str(csv_path),
        "duration_s": time.monotonic() - started_at,
        "sample_interval_s": args.sample_interval,
        "wheel_circumference_m": processor.wheel_circumference,
        "ant_speed_id": config.G_SENSORS["SPD"]["ID"],
        "ant_speed_type": config.G_SENSORS["SPD"]["TYPE"],
        "ble_identifier": args.ble_device,
        "ble_adapter": adapter,
        "comparison": stats.summary(),
        "ble_health": health.snapshot().as_dict(),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    print(f"Summary: {summary_path}")
    print(json.dumps(summary["comparison"], indent=2, allow_nan=True))
    print(f"BLE health: {summary['ble_health']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare configured ANT+ speed with BLE CSCS on one timeline"
    )
    parser.add_argument("--scan", action="store_true", help="scan CSCS devices only")
    parser.add_argument(
        "--scan-ant",
        action="store_true",
        help="scan ANT+ speed devices only",
    )
    parser.add_argument("--ble-device", help="BLE identifier from a scan on this host")
    parser.add_argument("--ant-device", type=int, help="temporary ANT+ speed device ID")
    parser.add_argument(
        "--ant-type",
        type=lambda value: int(value, 0),
        default=0x7B,
        help="temporary ANT+ device type, default 0x7B",
    )
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--sample-interval", type=float, default=0.1)
    parser.add_argument("--scan-seconds", type=float, default=20.0)
    parser.add_argument("--wheel-circumference", type=float)
    parser.add_argument("--output")
    parser.add_argument(
        "--adapter-policy",
        choices=[policy.value for policy in BleAdapterPolicy],
        default=BleAdapterPolicy.BUILTIN.value,
    )
    parser.add_argument("--keep-all-ant", action="store_true")
    parser.add_argument("--moving-cutoff", type=float, default=0.5)
    parser.add_argument("--stopped-cutoff", type=float, default=0.05)
    return parser


async def async_main(args: argparse.Namespace) -> int:
    if args.scan and args.scan_ant:
        print("Use only one of --scan and --scan-ant.", file=sys.stderr)
        return 2
    if args.scan:
        return await scan(args)
    if args.scan_ant:
        return await scan_ant(args)
    if not args.ble_device:
        print("--ble-device is required unless --scan is used.", file=sys.stderr)
        return 2
    if args.sample_interval <= 0:
        print("--sample-interval must be positive.", file=sys.stderr)
        return 2
    return await compare(args)


def main() -> None:
    raise SystemExit(asyncio.run(async_main(build_parser().parse_args())))


if __name__ == "__main__":
    main()
