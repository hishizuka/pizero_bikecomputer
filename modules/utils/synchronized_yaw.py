"""Align magnetic observations with continuous three-axis gyro interval rotations.

The nRF clock is shared by both sensors. Fractional intervals assume constant
body angular velocity within the transmitted average; unsent time is never
extrapolated. This cannot recover the original order of 50 Hz rotations.
"""

from collections import deque
from dataclasses import dataclass, replace
import math

import numpy as np

from .geo import get_angle_difference
from .magnetic_heading_gate import MagneticHeadingGate


def _rotation(vector):
    angle = float(np.linalg.norm(vector))
    if angle < 1e-12:
        return np.eye(3)
    x, y, z = vector / angle
    cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + math.sin(angle) * cross + (1 - math.cos(angle)) * cross @ cross


@dataclass(frozen=True)
class HeadingMotionResult:
    state: str
    magnetic_allowed: bool | None
    checked_epoch: int | None = None
    checked_seq: int | None = None
    checked_ts_ms: int | None = None
    residual_deg: float = math.nan
    predicted_heading_deg: float = math.nan
    pending_observations: int = 0
    delta_heading_deg: float = math.nan
    recovered: bool = False
    reanchor_phase_deg: float = math.nan


@dataclass(frozen=True)
class _Span:
    start_s: float
    end_s: float
    orientation: np.ndarray
    velocity: np.ndarray
    yaw_deg: float
    segment: int


class SynchronizedYaw:
    G_MAX_AGE_S = 2.0
    G_HISTORY = 64
    G_BOUNDARY_ERROR_S = 0.001000001
    G_SEED_RATE_RAD_S = 0.05
    G_MAX_ATTITUDE_AGE_S = 60.0
    G_MIN_HORIZONTAL = 0.2
    G_ROTATION_STEP_RAD = math.radians(10)
    G_MAX_INTERVAL_ROTATION_RAD = math.radians(2160)

    def __init__(self, *, acc_rest_z_sign):
        self._z_sign = acc_rest_z_sign
        self.gate = MagneticHeadingGate()
        self._epoch = None
        self._calibration_epoch = None
        self._mounting = None
        self._offset = None
        self._result = HeadingMotionResult("UNVERIFIED", None)
        self._clear_geometry()

    def _clear_geometry(self):
        self._spans = deque(maxlen=self.G_HISTORY)
        self._pending = deque()
        self._previous_imu = None
        self._orientation = None
        self._yaw = 0.0
        self._seed_time = -math.inf
        self._segment = 0
        self._previous_mag = None
        self._last_mag_seq = None
        self._checked = None
        self._checked_heading = math.nan

    def reset(self, *, physical=False):
        if physical:
            self.gate.reset()
            result = HeadingMotionResult("UNVERIFIED", None)
        else:
            gate = self.gate.invalidate()
            result = HeadingMotionResult(gate.state, gate.magnetic_allowed)
        self._clear_geometry()
        self._result = result
        if not physical:
            self._offset = None

    def observe_clock(self, sample):
        if not math.isfinite(sample.received_at):
            return
        if sample.epoch != self._epoch:
            self.reset()
            self._epoch = sample.epoch
        offset = sample.received_at - sample.ts_ms / 1000
        self._offset = offset if self._offset is None else min(self._offset, offset)

    def source_age(self, sample, now_s):
        if self._offset is None or sample.epoch != self._epoch:
            return math.inf
        return max(0.0, now_s - sample.ts_ms / 1000 - self._offset)

    def _heading(self, orientation):
        forward = orientation @ self._forward
        if np.linalg.norm(forward[:2]) < self.G_MIN_HORIZONTAL:
            return math.nan
        # Navigation coordinates are north/west/up: compass yaw is clockwise.
        return -math.degrees(math.atan2(forward[1], forward[0]))

    def _advance(self, orientation, velocity, duration):
        steps = max(
            1,
            math.ceil(
                float(np.linalg.norm(velocity)) * duration / self.G_ROTATION_STEP_RAD
            ),
        )
        step = _rotation(velocity * (duration / steps))
        heading = self._heading(orientation)
        total = 0.0
        for _ in range(steps):
            orientation = orientation @ step
            current = self._heading(orientation)
            if not math.isfinite(current) or not math.isfinite(heading):
                return orientation, math.nan
            total += get_angle_difference(current, heading)
            heading = current
        return orientation, total

    def _seed(self, interval, velocity):
        if (
            interval.acceleration is None
            or not np.isfinite(velocity).all()
            or np.linalg.norm(velocity) > self.G_SEED_RATE_RAD_S
        ):
            return False
        acceleration = np.asarray(interval.acceleration) * [1, 1, self._z_sign]
        magnitude = float(np.linalg.norm(acceleration))
        if not 0.9 <= magnitude <= 1.1:
            return False
        up = acceleration / magnitude
        forward = self._forward - (self._forward @ up) * up
        if np.linalg.norm(forward) < self.G_MIN_HORIZONTAL:
            return False
        forward /= np.linalg.norm(forward)
        self._orientation = np.vstack([forward, np.cross(up, forward), up])
        self._yaw = 0.0
        self._seed_time = interval.ts_ms / 1000
        self._segment += 1
        self._spans.append(
            _Span(
                self._seed_time,
                self._seed_time,
                self._orientation.copy(),
                np.zeros(3),
                0.0,
                self._segment,
            )
        )
        return True

    def _add_interval(self, interval, now_s):
        end = interval.ts_ms / 1000
        duration = interval.dt_us / 1_000_000
        velocity = np.asarray(interval.angular_velocity) * [1, 1, self._z_sign]
        previous = self._previous_imu
        if previous is not None and interval.seq == previous.seq:
            return
        continuous = (
            interval.continuous
            and previous is not None
            and interval.epoch == previous.epoch
            and (interval.seq - previous.seq) % 2**32 == 1
            and abs(end - duration - previous.ts_ms / 1000) <= self.G_BOUNDARY_ERROR_S
            and duration <= MagneticHeadingGate.G_MAX_INTERVAL_S
            and np.isfinite(velocity).all()
        )
        self._previous_imu = interval
        if self.source_age(interval, now_s) > self.G_MAX_AGE_S:
            self._orientation = None
            return
        if np.linalg.norm(velocity) * duration > self.G_MAX_INTERVAL_ROTATION_RAD:
            self._orientation = None
            return
        if not continuous or end - self._seed_time > self.G_MAX_ATTITUDE_AGE_S:
            self._orientation = None
        if self._orientation is None:
            self._seed(interval, velocity)
            return
        start_orientation = self._orientation.copy()
        self._orientation, delta = self._advance(start_orientation, velocity, duration)
        if not math.isfinite(delta):
            self._orientation = None
            return
        self._spans.append(
            _Span(
                end - duration,
                end,
                start_orientation,
                velocity,
                self._yaw,
                self._segment,
            )
        )
        self._yaw += delta

    def _at(self, timestamp):
        for span in reversed(self._spans):
            if span.start_s - self.G_BOUNDARY_ERROR_S <= timestamp <= span.end_s + 1e-9:
                duration = min(
                    max(timestamp - span.start_s, 0.0), span.end_s - span.start_s
                )
                _, delta = self._advance(span.orientation, span.velocity, duration)
                if math.isfinite(delta):
                    return span.yaw_deg + delta, span.segment
        return None

    def _reanchor_phase(self, now_s):
        if (
            self._result.state != "EXPIRED"
            or self._checked is None
            or self._orientation is None
            or self._previous_imu is None
            or self.source_age(self._checked, now_s) > self.G_MAX_AGE_S
            or self.source_age(self._previous_imu, now_s) > self.G_MAX_AGE_S
        ):
            return math.nan
        if np.linalg.norm(self._previous_imu.angular_velocity) > self.G_SEED_RATE_RAD_S:
            return math.nan
        return self._checked_heading

    def reanchor(self):
        """Caller must independently confirm the checked phase against good GPS."""
        if self._checked is None or not math.isfinite(self._checked_heading):
            return False
        self.gate.reset()
        gate = self.gate.update(
            timestamp_s=self._checked.ts_ms / 1000,
            heading_deg=self._checked_heading,
            delta_heading_deg=math.nan,
            continuous=False,
        )
        self._result = HeadingMotionResult(
            gate.state,
            gate.magnetic_allowed,
            self._checked.epoch,
            self._checked.seq,
            self._checked.ts_ms,
        )
        return True

    def update(
        self,
        *,
        intervals,
        observations,
        now_s,
        fixed_pitch,
        fixed_roll,
        calibration_epoch,
        transform_heading,
        model_ready=True,
    ):
        recovered = False
        for sample in intervals:
            self.observe_clock(sample)
        for sample, _ in observations:
            self.observe_clock(sample)
        mounting = (fixed_pitch, fixed_roll)
        if calibration_epoch != self._calibration_epoch or mounting != self._mounting:
            self.reset(physical=True)
            self._calibration_epoch = calibration_epoch
            self._mounting = mounting
        pitch, roll = mounting
        if not all(map(math.isfinite, mounting)):
            return HeadingMotionResult("MOUNTING_UNVERIFIED", None)
        cp, sp, cr, sr = (
            math.cos(pitch),
            math.sin(pitch),
            math.cos(roll),
            math.sin(roll),
        )
        mount = np.array(
            [[cp, sp * sr, sp * cr], [0, cr, -sr], [-sp, cp * sr, cp * cr]]
        )
        self._forward = mount.T @ np.array([1.0, 0.0, 0.0])
        # Source metadata is immutable; consume each gyro and magnetic sample once.
        for interval in intervals:
            self._add_interval(interval, now_s)
        for sample, heading in observations:
            if self._last_mag_seq == sample.seq:
                continue
            self._last_mag_seq = sample.seq
            self._pending.append((sample, heading))
            if len(self._pending) > self.G_HISTORY:
                self._pending.clear()
                self._previous_mag = None
                gate = self.gate.invalidate()
                self._result = HeadingMotionResult(gate.state, gate.magnetic_allowed)
        while self._pending:
            sample, heading = self._pending[0]
            timestamp = sample.ts_ms / 1000
            stale = self.source_age(sample, now_s) > self.G_MAX_AGE_S
            latest = self._previous_imu
            if not stale and (latest is None or timestamp > latest.ts_ms / 1000):
                break
            self._pending.popleft()
            current = None if stale else self._at(timestamp)
            previous = self._previous_mag
            continuous = (
                current is not None
                and previous is not None
                and sample.epoch == previous[0].epoch
                and (sample.seq - previous[0].seq) % 2**32 == 1
                and previous[1] is not None
                and current[1] == previous[1][1]
            )
            delta = current[0] - previous[1][0] if continuous else math.nan
            was_rejected = self._result.magnetic_allowed is False
            if not model_ready:
                # An unlearned directional response is not an independent fault.
                gate = self.gate.invalidate()
            else:
                gate = self.gate.update(
                    timestamp_s=timestamp,
                    heading_deg=heading if not stale else math.nan,
                    delta_heading_deg=delta,
                    continuous=continuous,
                    transform_heading=transform_heading,
                )
            recovered |= was_rejected and gate.magnetic_allowed is True
            self._previous_mag = (sample, current)
            self._checked = sample
            self._checked_heading = (
                heading if current is not None and not stale else math.nan
            )
            self._result = HeadingMotionResult(
                (
                    "MODEL_WARMUP"
                    if not model_ready and gate.magnetic_allowed is None
                    else gate.state
                ),
                gate.magnetic_allowed,
                sample.epoch,
                sample.seq,
                sample.ts_ms,
                gate.residual_deg,
                gate.predicted_heading_deg,
                delta_heading_deg=delta,
            )
        if self._pending:
            return replace(
                self._result,
                state="WAITING_FOR_GYRO",
                magnetic_allowed=(
                    False if self._result.magnetic_allowed is False else None
                ),
                pending_observations=len(self._pending),
                recovered=recovered,
                reanchor_phase_deg=(
                    self._reanchor_phase(now_s) if model_ready else math.nan
                ),
            )
        if self._checked is not None and (
            self.source_age(self._checked, now_s) > self.G_MAX_AGE_S
            or self._previous_imu is None
            or self.source_age(self._previous_imu, now_s) > self.G_MAX_AGE_S
        ):
            gate = self.gate.invalidate()
            self._orientation = None
            self._previous_mag = None
            self._result = HeadingMotionResult(
                "EXPIRED" if gate.magnetic_allowed is False else "STALE",
                gate.magnetic_allowed,
                self._checked.epoch,
                self._checked.seq,
                self._checked.ts_ms,
            )
        return replace(
            self._result,
            recovered=recovered,
            reanchor_phase_deg=self._reanchor_phase(now_s) if model_ready else math.nan,
        )
