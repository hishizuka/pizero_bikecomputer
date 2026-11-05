import math
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from numbers import Real


class DistanceSource(IntEnum):
    NONE = 0
    ANT = 1
    BLE = 2
    GPS = 3


class GPSPositionQualityState(IntEnum):
    UNVERIFIED = 0
    ACCEPTED = 1
    REJECTED = 2


class GPSPositionQualityReason(IntEnum):
    NONE = 0
    BASIC_INVALID = 1
    NO_WHEEL = 2
    WINDOW_WARMUP = 3
    LOW_SPEED = 4
    WHEEL_DISTANCE_MISMATCH = 5
    RECOVERY_WAIT = 6


@dataclass(frozen=True)
class GPSPositionQualityResult:
    state: GPSPositionQualityState
    reason: GPSPositionQualityReason
    distance_ratio: float
    distance_error: float


class GPSPositionQuality:
    WINDOW_SAMPLES = 10
    MIN_SAMPLE_DT_S = 0.5
    MAX_SAMPLE_DT_S = 1.5
    MAX_WHEEL_STEP_M = 100.0
    MIN_SPEED_MPS = 2.0
    MIN_WHEEL_DISTANCE_FACTOR = 0.65
    REJECT_MIN_ERROR_M = 7.0
    REJECT_LOW_RATIO = 0.80
    REJECT_HIGH_RATIO = 1.40
    RECOVERY_MAX_ERROR_M = 5.0
    RECOVERY_LOW_RATIO = 0.90
    RECOVERY_HIGH_RATIO = 1.10
    RECOVERY_SAMPLES = 3

    def __init__(self):
        self._samples = deque(maxlen=self.WINDOW_SAMPLES)
        self._wheel_source = DistanceSource.NONE
        self._rejected = False
        self._recovery_samples = 0

    @staticmethod
    def _finite(value):
        return isinstance(value, Real) and math.isfinite(value)

    @staticmethod
    def _is_wheel_source(distance_source):
        return distance_source in (DistanceSource.ANT, DistanceSource.BLE)

    def reset(self):
        self._samples.clear()
        self._wheel_source = DistanceSource.NONE
        self._rejected = False
        self._recovery_samples = 0

    def _clear_window(self):
        self._samples.clear()
        self._wheel_source = DistanceSource.NONE
        self._recovery_samples = 0

    def _append_sample(
        self,
        distance_source,
        wheel_step_m,
        gps_step_m,
        dt_s,
    ):
        if not self._is_wheel_source(distance_source):
            self._clear_window()
            return False
        if self._wheel_source not in (DistanceSource.NONE, distance_source):
            self._clear_window()
        self._wheel_source = distance_source
        if (
            not self._finite(wheel_step_m)
            or not self._finite(gps_step_m)
            or not self._finite(dt_s)
            or wheel_step_m < 0
            or wheel_step_m > self.MAX_WHEEL_STEP_M
            or gps_step_m < 0
            or not self.MIN_SAMPLE_DT_S <= dt_s <= self.MAX_SAMPLE_DT_S
        ):
            self._clear_window()
            return False
        self._samples.append((wheel_step_m, gps_step_m, dt_s))
        return True

    def update(
        self,
        *,
        gps_basic_valid,
        gps_step_m,
        wheel_step_m,
        distance_source,
        dt_s,
    ):
        distance_source = DistanceSource(distance_source)
        sample_valid = self._append_sample(
            distance_source,
            wheel_step_m,
            gps_step_m,
            dt_s,
        )
        window_ready = sample_valid and len(self._samples) == self.WINDOW_SAMPLES
        distance_ratio = math.nan
        distance_error = math.nan
        evaluable = False
        trigger = False
        recovery_stable = False

        if window_ready:
            wheel_distance = sum(sample[0] for sample in self._samples)
            gps_distance = sum(sample[1] for sample in self._samples)
            duration = sum(sample[2] for sample in self._samples)
            if wheel_distance > 0:
                distance_ratio = gps_distance / wheel_distance
                distance_error = gps_distance - wheel_distance
                evaluable = (
                    wheel_distance / duration >= self.MIN_SPEED_MPS
                    and wheel_distance
                    >= self.MIN_SPEED_MPS
                    * self.WINDOW_SAMPLES
                    * self.MIN_WHEEL_DISTANCE_FACTOR
                )

        if evaluable:
            trigger = (
                distance_error <= -self.REJECT_MIN_ERROR_M
                and distance_ratio <= self.REJECT_LOW_RATIO
            ) or (
                distance_error >= self.REJECT_MIN_ERROR_M
                and distance_ratio >= self.REJECT_HIGH_RATIO
            )
            recovery_stable = (
                abs(distance_error) <= self.RECOVERY_MAX_ERROR_M
                and self.RECOVERY_LOW_RATIO
                <= distance_ratio
                <= self.RECOVERY_HIGH_RATIO
            )

        if trigger:
            self._rejected = True
            self._recovery_samples = 0
        elif self._rejected and gps_basic_valid is True and evaluable:
            if recovery_stable:
                self._recovery_samples += 1
                if self._recovery_samples >= self.RECOVERY_SAMPLES:
                    self._rejected = False
                    self._recovery_samples = 0
            else:
                self._recovery_samples = 0

        if trigger:
            state = GPSPositionQualityState.REJECTED
            reason = GPSPositionQualityReason.WHEEL_DISTANCE_MISMATCH
        elif gps_basic_valid is not True:
            state = GPSPositionQualityState.REJECTED
            reason = GPSPositionQualityReason.BASIC_INVALID
        elif self._rejected:
            state = GPSPositionQualityState.REJECTED
            reason = GPSPositionQualityReason.RECOVERY_WAIT
        elif not self._is_wheel_source(distance_source):
            state = GPSPositionQualityState.UNVERIFIED
            reason = GPSPositionQualityReason.NO_WHEEL
        elif not window_ready:
            state = GPSPositionQualityState.UNVERIFIED
            reason = GPSPositionQualityReason.WINDOW_WARMUP
        elif not evaluable:
            state = GPSPositionQualityState.UNVERIFIED
            reason = GPSPositionQualityReason.LOW_SPEED
        else:
            state = GPSPositionQualityState.ACCEPTED
            reason = GPSPositionQualityReason.NONE

        return GPSPositionQualityResult(
            state,
            reason,
            distance_ratio,
            distance_error,
        )
