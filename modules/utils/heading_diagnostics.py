"""Batch heading evidence around events without writing a sample every second."""

from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime
import json
import math
from numbers import Real
import time

from modules.app_logger import app_logger
from .geo import get_angle_difference

@dataclass(frozen=True)
class _HeadingChange:
    state: str
    start_s: float = math.nan
    end_s: float = math.nan
    delta_deg: float = math.nan
    window_s: float = math.nan
    window_delta_deg: float = math.nan

    @property
    def dt_s(self):
        return self.end_s - self.start_s

    @property
    def rate_deg_s(self):
        return self.delta_deg / self.dt_s

    def values(self, speed):
        return (
            self.state,
            self.dt_s,
            self.delta_deg,
            self.rate_deg_s,
            self.window_s,
            self.window_delta_deg,
            speed * abs(math.radians(self.rate_deg_s)),
        )


class HeadingChangeMonitor:
    """Measure relative changes for diagnostics, without declaring a sensor faulty."""

    G_MAX_GAP_S = 1.5
    G_MAX_AGE_S = 2.0
    G_HISTORY_S = 6.0
    G_MAX_SAMPLES = 64
    G_MIN_GPS_SPEED_MPS = 5.0
    G_MIN_GPS_QUALITY = 0.8
    G_ALIGNMENT_S = 0.05
    G_COLUMNS = (
        "state",
        "dt_s",
        "delta_deg",
        "rate_deg_s",
        "window_s",
        "window_delta_deg",
        "implied_lateral_accel_mps2",
    )
    G_COMPARISON_COLUMNS = (
        "state",
        "endpoint_offset_s",
        "delta_error_deg",
        "rate_error_deg_s",
        "window_endpoint_offset_s",
        "window_delta_error_deg",
    )

    def __init__(self):
        self._history = {
            name: deque(maxlen=self.G_MAX_SAMPLES) for name in ("gps", "mag")
        }
        self._generation = None
        self._last_clock = -math.inf

    def _observe(self, name, timestamp, phase, usable, clock, transform):
        history = self._history[name]
        if not usable or not math.isfinite(phase):
            history.clear()
            return _HeadingChange("FILTERED")
        if not isinstance(timestamp, datetime):
            history.clear()
            return _HeadingChange("UNAVAILABLE")
        end = timestamp.timestamp()
        if not 0 <= clock - end <= self.G_MAX_AGE_S:
            history.clear()
            return _HeadingChange("STALE")
        if history and end == history[-1][0]:
            return _HeadingChange("HELD")
        if history and end < history[-1][0]:
            history.clear()
            return _HeadingChange("CLOCK_REVERSED")
        previous = history[-1] if history else None
        state = "UPDATED"
        if previous is None:
            state = "WARMUP"
        elif end - previous[0] > self.G_MAX_GAP_S:
            history.clear()
            state = "GAP"
        while history and end - history[0][0] > self.G_HISTORY_S:
            history.popleft()
        history.append((end, phase))
        if state != "UPDATED":
            return _HeadingChange(state)
        # Evaluate all physical phases with one current model, so coefficient or
        # readiness changes cannot masquerade as a physical rotation.
        angles = [transform(item[1]) if transform else item[1] for item in history]
        window_delta = sum(
            get_angle_difference(right, left) for left, right in zip(angles, angles[1:])
        )
        return _HeadingChange(
            state,
            previous[0],
            end,
            get_angle_difference(angles[-1], angles[-2]),
            end - history[0][0],
            window_delta,
        )

    def update(
        self,
        *,
        now,
        inputs,
        position_state,
        wheel_speed,
        wheel_available,
        generation,
        physical_ready,
        transform_heading=None,
    ):
        clock = now.timestamp()
        if generation != self._generation or clock < self._last_clock:
            for history in self._history.values():
                history.clear()
        self._generation, self._last_clock = generation, clock
        gps_usable = (
            all(
                math.isfinite(inputs[key])
                for key in (
                    "gps_mode",
                    "gps_speed",
                    "heading_gps_quality",
                )
            )
            and inputs["gps_mode"] >= 3
            and inputs["gps_speed"] >= self.G_MIN_GPS_SPEED_MPS
            and inputs["heading_gps_quality"] >= self.G_MIN_GPS_QUALITY
            and position_state == 1
        )
        gps = self._observe(
            "gps",
            inputs["heading_gps_timestamp"],
            inputs["heading_gps_deg"],
            gps_usable,
            clock,
            None,
        )
        phase = (
            inputs["heading_magnetic_deg"] - inputs["heading_magnetic_declination_deg"]
        ) % 360
        magnetic = self._observe(
            "mag",
            inputs["heading_magnetic_timestamp"],
            phase,
            physical_ready,
            clock,
            transform_heading,
        )
        speed = (
            wheel_speed
            if wheel_available and math.isfinite(wheel_speed) and wheel_speed >= 0
            else (
                inputs["gps_speed"]
                if gps_usable and gps.state in {"UPDATED", "WARMUP", "HELD", "GAP"}
                else math.nan
            )
        )
        comparison = ("UNAVAILABLE",) + (math.nan,) * 5
        if gps.state == magnetic.state == "UPDATED":
            offset = max(
                abs(gps.start_s - magnetic.start_s), abs(gps.end_s - magnetic.end_s)
            )
            window_offset = max(
                abs(gps.end_s - gps.window_s - magnetic.end_s + magnetic.window_s),
                abs(gps.end_s - magnetic.end_s),
            )
            aligned = offset <= self.G_ALIGNMENT_S
            comparison = (
                "ALIGNED" if aligned else "UNALIGNED",
                offset,
                (
                    get_angle_difference(magnetic.delta_deg, gps.delta_deg)
                    if aligned
                    else math.nan
                ),
                magnetic.rate_deg_s - gps.rate_deg_s if aligned else math.nan,
                window_offset,
                (
                    magnetic.window_delta_deg - gps.window_delta_deg
                    if window_offset <= self.G_ALIGNMENT_S
                    else math.nan
                ),
            )
        return (gps.values(speed), magnetic.values(speed), comparison)


class HeadingEventLogger:
    G_RELATIVE_COLUMNS = {
        "gps": HeadingChangeMonitor.G_COLUMNS,
        "mag": HeadingChangeMonitor.G_COLUMNS,
        "comparison": HeadingChangeMonitor.G_COMPARISON_COLUMNS,
    }
    G_PRE_SECONDS = 10.0
    G_POST_SECONDS = 8.0
    G_MAX_EVENT_SECONDS = 60.0
    G_MIN_EMIT_SECONDS = 15.0
    G_SUMMARY_SECONDS = 60.0
    G_MAX_SAMPLES = 96
    G_TURN_DEG = 5.0
    G_CANDIDATE_TURN_DEG_S = 8.0
    G_MIN_WHEEL_SPEED = 1.0
    G_COLUMNS = (
        "time",
        "monotonic",
        "gps_time",
        "mag_time",
        "gps_deg",
        "mag_deg",
        "f1_deg",
        "final_deg",
        "source",
        "reason",
        "mag_state",
        "gps_quality",
        "position_state",
        "gps_speed",
        "gps_mode",
        "gps_epx",
        "gps_epy",
        "wheel_speed",
        "wheel_available",
        "learning",
        "model",
        "model_samples",
        "model_generation",
        "declination",
        "gyro_state",
        "gyro_allowed",
        "gyro_epoch",
        "gyro_seq",
        "gyro_ts_ms",
        "gyro_delta_deg",
        "gyro_prediction_deg",
        "gyro_residual_deg",
        "pending",
        "recovered",
        "attitude",
        "gyro_intervals_supported",
        "relative",
    )

    def __init__(self):
        self._buffer = deque(maxlen=self.G_MAX_SAMPLES)
        self._rows = None
        self._events = []
        self._event_started = self._last_trigger = -math.inf
        self._last_emit = -math.inf
        self._last_summary = None
        self._counts = Counter()
        self._previous = None
        self._active = False
        self._event_id = 0
        self._changes = HeadingChangeMonitor()

    @classmethod
    def _value(cls, value):
        if isinstance(value, datetime):
            return value.isoformat(timespec="milliseconds")
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, Real):
            if not math.isfinite(value):
                return None
            return int(value) if isinstance(value, int) else round(float(value), 4)
        if isinstance(value, (tuple, list)):
            return [cls._value(item) for item in value]
        return value

    @staticmethod
    def _json(value):
        return json.dumps(value, separators=(",", ":"), allow_nan=False)

    def _turning(self, sample):
        previous = self._previous
        if (
            previous is None
            or not sample["wheel_available"]
            or sample["wheel_speed"] is None
            or sample["wheel_speed"] < self.G_MIN_WHEEL_SPEED
            or not 0 < sample["monotonic"] - previous["monotonic"] <= 2.5
        ):
            return False
        if (
            sample["gyro_delta_deg"] is not None
            and (sample["gyro_epoch"], sample["gyro_seq"])
            != (previous["gyro_epoch"], previous["gyro_seq"])
            and abs(sample["gyro_delta_deg"]) >= self.G_TURN_DEG
        ):
            return True
        for change in sample["relative"][:2]:
            if change[0] == "UPDATED" and abs(change[3]) >= self.G_CANDIDATE_TURN_DEG_S:
                return True
        return False

    def record(
        self,
        *,
        now,
        inputs,
        integrated,
        motion,
        wheel_speed,
        wheel_available,
        learning,
        recording,
        generation,
        attitude=None,
        supports_gyro_intervals=False,
        physical_ready=True,
        transform_heading=None,
    ):
        clock = time.monotonic()
        wheel_available, learning = bool(wheel_available), bool(learning)
        relative = self._changes.update(
            now=now,
            inputs=inputs,
            position_state=integrated["gps_position_quality_state"],
            wheel_speed=wheel_speed,
            wheel_available=wheel_available,
            generation=generation,
            physical_ready=physical_ready,
            transform_heading=transform_heading,
        )
        gyro_values = (
            (
                motion.magnetic_allowed,
                motion.checked_epoch,
                motion.checked_seq,
                motion.checked_ts_ms,
                motion.delta_heading_deg,
                motion.predicted_heading_deg,
                motion.residual_deg,
                motion.pending_observations,
                motion.recovered,
            )
            if motion is not None
            else (None,) * 7 + (0, False)
        )
        values = (
            now,
            clock,
            inputs["heading_gps_timestamp"],
            inputs["heading_magnetic_timestamp"],
            inputs["heading_gps_deg"],
            inputs["heading_magnetic_deg"],
            integrated["heading_magnetic_corrected_deg"],
            integrated["heading_deg"],
            integrated["heading_source"],
            integrated["heading_selection_reason"],
            integrated["heading_magnetic_state"],
            integrated["heading_gps_quality"],
            integrated["gps_position_quality_state"],
            inputs["gps_speed"],
            inputs["gps_mode"],
            inputs["gps_epx"],
            inputs["gps_epy"],
            wheel_speed,
            wheel_available,
            learning,
            integrated["heading_magnetic_model_used"],
            integrated["heading_magnetic_model_samples"],
            generation,
            inputs["heading_magnetic_declination_deg"],
            integrated["heading_gyro_state"],
            *gyro_values,
            attitude,
            bool(supports_gyro_intervals),
            relative,
        )
        row = [self._value(value) for value in values]
        sample = dict(zip(self.G_COLUMNS, row, strict=True))
        if not recording:
            if self._active:
                self.flush("ride_end")
            self._active = False
            self._last_summary = None
            self._counts.clear()
            self._previous = sample
            self._buffer.append(row)
            return

        reasons = []
        previous = self._previous
        if not self._active:
            reasons.append("ride_start")
            self._last_summary = clock
        else:
            if sample["source"] != previous["source"]:
                reasons.append("source_change")
            if (
                sample["gyro_allowed"] is False
                and previous["gyro_allowed"] is not False
            ):
                reasons.append("magnetic_rejection")
            if sample["recovered"]:
                reasons.append("magnetic_recovery")
            if sample["gyro_state"] == "REANCHORED_GPS":
                reasons.append("gps_reanchor")
            if sample["mag_state"] == "ABSOLUTE_HOLD" != previous["mag_state"]:
                reasons.append("absolute_hold")
            if sample["model_generation"] != previous["model_generation"]:
                reasons.append("calibration_reset")
        if self._turning(sample):
            reasons.append("turn")
        self._active = True
        self._previous = sample
        self._counts["samples"] += 1
        self._counts["source:" + sample["source"]] += 1
        self._counts["gyro:" + sample["gyro_state"]] += 1
        self._counts["learning"] += int(learning)
        while self._buffer and clock - self._buffer[0][1] > self.G_PRE_SECONDS:
            self._buffer.popleft()
        if reasons:
            if self._rows is None:
                self._rows = deque(self._buffer, maxlen=self.G_MAX_SAMPLES)
                self._event_started = clock
            # Consecutive turn samples extend the window, not the event list.
            if reasons != ["turn"] or not self._events:
                self._events.append([sample["time"], reasons])
            self._last_trigger = clock
        if self._rows is not None:
            self._rows.append(row)
            if clock - self._last_emit >= self.G_MIN_EMIT_SECONDS and (
                clock - self._last_trigger >= self.G_POST_SECONDS
                or clock - self._event_started >= self.G_MAX_EVENT_SECONDS
            ):
                self.flush("window_end")
        self._buffer.append(row)
        if clock - self._last_summary >= self.G_SUMMARY_SECONDS:
            self._summary(sample)
            self._last_summary = clock

    def _summary(self, sample):
        app_logger.info(
            "[HEADING-STATS] %s",
            self._json(
                {
                    "time": sample["time"],
                    "counts": dict(self._counts),
                    "latest": sample,
                    "relative_columns": self.G_RELATIVE_COLUMNS,
                }
            ),
        )
        self._counts.clear()

    def flush(self, reason="shutdown"):
        if self._rows is None:
            return
        self._event_id += 1
        payload = {
            "version": 2,
            "id": self._event_id,
            "end": reason,
            "events": self._events,
            "columns": self.G_COLUMNS,
            "attitude_columns": (
                "fixed_pitch_rad",
                "fixed_roll_rad",
                "pitch_rad",
                "roll_rad",
                "acc_mod_g",
                "gyro_mod_rad_s",
                "mag_corrected_axes_uT",
            ),
            "samples": list(self._rows),
            "relative_columns": self.G_RELATIVE_COLUMNS,
        }
        app_logger.info("[HEADING-EVENT] %s", self._json(payload))
        self._rows = None
        self._events = []
        self._last_emit = time.monotonic()
