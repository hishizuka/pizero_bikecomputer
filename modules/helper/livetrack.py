import asyncio
import json
import math
import os
import stat
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from modules.app_logger import app_logger

# Number of samples uploaded together at the end of each LiveTrack interval.
LIVETRACK_SAMPLE_COUNT = 4


def utc_now() -> str:
    """Return a Garmin-compatible UTC timestamp with millisecond precision."""
    value = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    return value.replace("+00:00", "Z")


async def run_with_bt_tethering(
    network,
    caller_name,
    operation,
    *,
    log_prefix,
    purpose,
):
    """Run one operation while Bluetooth tethering is open."""
    app_logger.debug(f"{log_prefix} opening BT tethering for {purpose}")
    open_result = await network.open_bt_tethering(caller_name)
    if not open_result.is_success():
        app_logger.debug(f"{log_prefix} failed to open BT tethering for {purpose}")
        return "open_error", None

    try:
        value = await operation()
    finally:
        close_success = await network.close_bt_tethering(caller_name)

    if not close_success:
        app_logger.warning(f"{log_prefix} failed to close BT tethering for {purpose}")
        return "close_error", value
    return "success", value


@dataclass(frozen=True)
class LiveTrackRequest:
    garmin_stop: bool = False
    include_thingsboard: bool = True

    def merge(self, other):
        return LiveTrackRequest(
            garmin_stop=self.garmin_stop or other.garmin_stop,
            include_thingsboard=(self.include_thingsboard or other.include_thingsboard),
        )


class LiveTrackCoordinator:
    """Apply interval, locking, and pending-request rules to LiveTrack work."""

    def __init__(self, interval_getter, sample_getter, executor):
        if LIVETRACK_SAMPLE_COUNT < 1:
            raise ValueError("LIVETRACK_SAMPLE_COUNT must be at least 1")
        self._interval_getter = interval_getter
        self._sample_getter = sample_getter
        self._executor = executor
        self._last_send_at = int(time.time())
        self._interval_samples = []
        self._locked = False
        self._pending = None

    def submit(self, request, *, quick_send=False):
        if self._locked:
            if quick_send:
                if self._pending is None:
                    self._pending = (request, [self._sample_getter()])
                else:
                    pending_request, _pending_samples = self._pending
                    self._pending = (
                        pending_request.merge(request),
                        [self._sample_getter()],
                    )
            return False

        now = int(time.time())
        interval = self._interval_getter()
        if not quick_send:
            elapsed = now - self._last_send_at
            if elapsed < interval:
                next_sample_number = len(self._interval_samples) + 1
                if (
                    next_sample_number < LIVETRACK_SAMPLE_COUNT
                    and elapsed * LIVETRACK_SAMPLE_COUNT
                    >= interval * next_sample_number
                ):
                    self._interval_samples.append(self._sample_getter())
                return False

        samples = self._interval_samples
        samples.append(self._sample_getter())
        self._interval_samples = []
        self._last_send_at = now

        self._locked = True
        asyncio.create_task(self._run_locked(request, samples))
        return True

    async def _run_locked(self, request, samples):
        try:
            await self._executor(request, samples)
        finally:
            self._locked = False
            pending = self._pending
            self._pending = None
            if pending is not None:
                pending_request, pending_samples = pending
                self._locked = True
                asyncio.create_task(self._run_locked(pending_request, pending_samples))


def save_private_json(path, value):
    """Atomically save a JSON object with owner-only permissions."""
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"

    descriptor = os.open(
        temporary_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file_handle:
            file_handle.write(payload)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def load_private_json(path, default=None):
    """Load an owner-only JSON object, returning default when it is absent."""
    path = Path(path).expanduser()
    if not path.exists():
        return default

    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise RuntimeError(f"Unsafe private JSON permissions: {path}")

    with path.open(encoding="utf-8") as file_handle:
        data = json.load(file_handle)
    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid private JSON object: {path}")
    return data


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _finite_int(value):
    number = _finite_number(value)
    if number is None:
        return None
    return int(number)


def _nan_if_none(value):
    return math.nan if value is None else value


@dataclass(frozen=True)
class LiveTrackSample:
    timestamp: int
    display_timestamp: str
    latitude: float | None
    longitude: float | None
    gps_altitude_m: float | None
    altitude_m: float | None
    speed_mps: float | None
    distance_m: float | None
    heart_rate_bpm: int | None
    heart_rate_60s_bpm: int | None
    cadence_rpm: int | None
    power_w: float | None
    power_60s_w: float | None
    accumulated_power_j: float | None
    ascent_m: float | None
    heading_gps_deg: int | None
    heading_magnetic_deg: int | None
    accuracy_m: int | None
    satellite_count: int | None
    temperature_c: float | None
    activity_start_timestamp: int | None = None
    active_duration_sec: float | None = None

    def has_position(self):
        return self.latitude is not None and self.longitude is not None

    def to_thingsboard_payload(self):
        speed = math.nan if self.speed_mps is None else int(self.speed_mps * 3.6)
        distance = (
            math.nan
            if self.distance_m is None
            else float(round(self.distance_m / 1000, 1))
        )
        work = (
            math.nan
            if self.accumulated_power_j is None
            else int(self.accumulated_power_j / 1000)
        )

        return {
            "ts": self.timestamp * 1000,
            "values": {
                "timestamp": self.display_timestamp,
                "speed": speed,
                "distance": distance,
                "heartrate": _nan_if_none(self.heart_rate_60s_bpm),
                "power": _nan_if_none(self.power_60s_w),
                "work": work,
                "temperature": _nan_if_none(self.temperature_c),
                "latitude": _nan_if_none(self.latitude),
                "longitude": _nan_if_none(self.longitude),
            },
        }


def build_livetrack_sample(config):
    values = config.logger.sensor.values
    logger_values = getattr(config.logger, "values", {})
    integrated = values.get("integrated", {})
    gps = values.get("GPS", {})
    i2c = values.get("I2C", {})

    timestamp = int(time.time())
    display_timestamp = ""
    if not getattr(config, "G_DUMMY_OUTPUT", False):
        display_timestamp = datetime.fromtimestamp(timestamp).strftime("%m/%d %H:%M")

    heading_gps_deg = _finite_int(gps.get("heading_gps_deg"))
    heading_magnetic_deg = _finite_int(i2c.get("heading_magnetic_deg"))
    epx = _finite_number(gps.get("epx"))
    epy = _finite_number(gps.get("epy"))
    accuracy = None
    if epx is not None or epy is not None:
        accuracy = int(max(value for value in (epx, epy) if value is not None))

    return LiveTrackSample(
        timestamp=timestamp,
        display_timestamp=display_timestamp,
        latitude=_finite_number(gps.get("lat")),
        longitude=_finite_number(gps.get("lon")),
        gps_altitude_m=_finite_number(gps.get("alt")),
        altitude_m=_finite_number(i2c.get("altitude")),
        speed_mps=_finite_number(integrated.get("speed")),
        distance_m=_finite_number(integrated.get("distance")),
        heart_rate_bpm=_finite_int(integrated.get("heart_rate")),
        heart_rate_60s_bpm=_finite_int(integrated.get("ave_heart_rate_60s")),
        cadence_rpm=_finite_int(integrated.get("cadence")),
        power_w=_finite_number(integrated.get("power")),
        power_60s_w=_finite_number(integrated.get("ave_power_60s")),
        accumulated_power_j=_finite_number(integrated.get("accumulated_power")),
        ascent_m=_finite_number(i2c.get("total_ascent")),
        heading_gps_deg=heading_gps_deg,
        heading_magnetic_deg=heading_magnetic_deg,
        accuracy_m=accuracy,
        satellite_count=_finite_int(gps.get("used_sats")),
        temperature_c=_finite_number(integrated.get("temperature")),
        activity_start_timestamp=_finite_int(logger_values.get("start_time")),
        active_duration_sec=_finite_number(logger_values.get("count")),
    )
