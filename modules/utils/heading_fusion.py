import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from numbers import Real

from .geo import get_angle_difference
from .magnetic_heading_confirmation import MagneticHeadingConfirmation


@dataclass(frozen=True)
class HeadingFusionResult:
    heading_gps_quality: float
    heading_deg: float
    heading_source: str
    heading_selection_reason: str = "LEGACY"
    heading_magnetic_state: str = "UNVERIFIED"


class HeadingFusion:
    G_FALLBACK_MIN_QUALITY = 0.2
    G_FALLBACK_MIN_SPEED_MPS = 2.0
    G_WHEEL_MIN_SPEED_MPS = 1.0
    G_WHEEL_SPEED_ERROR_MPS = 1.0
    G_WHEEL_SPEED_ERROR_FRACTION = 0.15
    G_LEARNING_MIN_SPEED_MPS = 5.0
    G_REANCHOR_SAMPLES = 5
    G_REANCHOR_ERROR_DEG = 5.0
    G_REANCHOR_TURN_DEG_S = 1.5
    G_REANCHOR_MAX_AGE_S = 1.5
    GPS_FULL_QUALITY_SPEED_MPS = 5.0
    GPS_GOOD_ERROR_M = 3.0
    GPS_MAX_ERROR_M = 20.0
    SOURCE_MIN_QUALITY = 0.05
    MAX_AGE_S = 3.0

    def __init__(self, gps_speed_cutoff, *, magnetic_primary=False):
        self.gps_speed_cutoff = gps_speed_cutoff
        self.magnetic_primary = magnetic_primary
        self.magnetic_confirmation = MagneticHeadingConfirmation()
        self._reanchor_history = deque(maxlen=self.G_REANCHOR_SAMPLES)

    def reset(self):
        self.magnetic_confirmation.reset()
        self._reanchor_history.clear()

    def acknowledge_magnetic_recovery(self):
        # The synchronized gate already required distinct consistent observations.
        self.magnetic_confirmation.externally_rejected = False

    def confirm_magnetic_reanchor(
        self,
        *,
        eligible,
        inputs,
        heading_deg,
        observation_id,
        wheel_speed,
        wheel_available,
        position_state,
        now,
    ):
        timestamp = inputs["heading_gps_timestamp"]
        age = (
            (now - timestamp).total_seconds()
            if isinstance(timestamp, datetime)
            else math.inf
        )
        error = get_angle_difference(heading_deg, inputs["heading_gps_deg"])
        valid = (
            eligible
            and wheel_available
            and self.wheel_speed_matches(wheel_speed, inputs["gps_speed"])
            and wheel_speed >= self.G_LEARNING_MIN_SPEED_MPS
            and inputs["gps_speed"] >= self.G_LEARNING_MIN_SPEED_MPS
            and inputs["gps_mode"] >= 3
            and position_state == 1
            and inputs["heading_gps_quality"] >= 0.8
            and 0 <= age <= self.G_REANCHOR_MAX_AGE_S
            and self._finite(error)
            and abs(error) <= self.G_REANCHOR_ERROR_DEG
        )
        if not valid:
            self._reanchor_history.clear()
            return False
        if self._reanchor_history:
            previous_time, previous_heading, previous_id = self._reanchor_history[-1]
            if timestamp == previous_time or observation_id == previous_id:
                return False
            dt = (timestamp - previous_time).total_seconds()
            turn = abs(
                get_angle_difference(inputs["heading_gps_deg"], previous_heading)
            )
            if (
                not 0 < dt <= self.G_REANCHOR_MAX_AGE_S
                or turn > self.G_REANCHOR_TURN_DEG_S * dt
            ):
                self._reanchor_history.clear()
        self._reanchor_history.append(
            (timestamp, inputs["heading_gps_deg"], observation_id)
        )
        return len(self._reanchor_history) == self.G_REANCHOR_SAMPLES

    def wheel_speed_matches(self, wheel_speed, gps_speed):
        return (
            self._finite(wheel_speed)
            and self._finite(gps_speed)
            and abs(wheel_speed - gps_speed)
            <= max(
                self.G_WHEEL_SPEED_ERROR_MPS,
                self.G_WHEEL_SPEED_ERROR_FRACTION * wheel_speed,
            )
        )

    def learning_allowed(self, *, wheel_speed, wheel_available, gps_speed):
        return (
            wheel_available
            and self.wheel_speed_matches(wheel_speed, gps_speed)
            and wheel_speed >= self.G_LEARNING_MIN_SPEED_MPS
            and gps_speed >= self.G_LEARNING_MIN_SPEED_MPS
            and not self.magnetic_confirmation.externally_rejected
        )

    @staticmethod
    def _finite(value):
        return isinstance(value, Real) and math.isfinite(value)

    @staticmethod
    def _clamp(value):
        return min(1.0, max(0.0, value))

    def _age_quality(self, timestamp, now):
        if not isinstance(timestamp, datetime):
            return 0.0
        age_s = (now - timestamp).total_seconds()
        if age_s < 0:
            return 0.0
        return self._clamp(1.0 - age_s / self.MAX_AGE_S)

    def gps_quality(
        self,
        heading_gps_deg,
        heading_gps_timestamp,
        gps_speed,
        gps_mode,
        gps_epx,
        gps_epy,
        now,
    ):
        if (
            not self._finite(heading_gps_deg)
            or not self._finite(gps_mode)
            or gps_mode < 3
        ):
            return 0.0

        if self._finite(gps_speed):
            if gps_speed <= self.gps_speed_cutoff:
                return 0.0
            speed_range = self.GPS_FULL_QUALITY_SPEED_MPS - self.gps_speed_cutoff
            speed_quality = self._clamp(
                (gps_speed - self.gps_speed_cutoff) / speed_range
            )
        else:
            # The timestamp proves this retained heading was produced while moving.
            speed_quality = 1.0

        errors = [value for value in (gps_epx, gps_epy) if self._finite(value)]
        if errors:
            horizontal_error = max(errors)
            error_range = self.GPS_MAX_ERROR_M - self.GPS_GOOD_ERROR_M
            error_quality = self._clamp(
                (self.GPS_MAX_ERROR_M - horizontal_error) / error_range
            )
        else:
            error_quality = 0.5

        return (
            speed_quality
            * error_quality
            * self._age_quality(heading_gps_timestamp, now)
        )

    def update(
        self,
        *,
        heading_gps_deg,
        heading_gps_timestamp,
        gps_speed,
        gps_mode,
        gps_epx,
        gps_epy,
        heading_magnetic_deg,
        heading_magnetic_timestamp,
        now=None,
        gps_position_quality_state=0,
        wheel_speed=math.nan,
        wheel_available=False,
        magnetic_model_used="NONE",
        magnetic_model_generation=0,
        magnetic_teachers=(),
        physical_ready=True,
        magnetic_allowed=None,
    ):
        if now is None:
            now = datetime.now()

        gps_quality = self.gps_quality(
            heading_gps_deg,
            heading_gps_timestamp,
            gps_speed,
            gps_mode,
            gps_epx,
            gps_epy,
            now,
        )
        magnetic_available = (
            self._finite(heading_magnetic_deg)
            and self._age_quality(heading_magnetic_timestamp, now)
            >= self.SOURCE_MIN_QUALITY
        )

        if self.magnetic_primary:
            return self._select_magnetic_primary(
                gps_quality=gps_quality,
                gps_heading=heading_gps_deg,
                gps_speed=gps_speed,
                position_state=gps_position_quality_state,
                wheel_speed=wheel_speed,
                wheel_available=wheel_available,
                magnetic_heading=heading_magnetic_deg,
                magnetic_available=magnetic_available,
                now=now,
                model_used=magnetic_model_used,
                generation=magnetic_model_generation,
                teachers=magnetic_teachers,
                physical_ready=physical_ready,
                magnetic_allowed=magnetic_allowed,
            )

        if gps_quality >= self.SOURCE_MIN_QUALITY:
            return HeadingFusionResult(
                gps_quality,
                heading_gps_deg % 360.0,
                "GPS",
            )
        if magnetic_available:
            return HeadingFusionResult(
                gps_quality,
                heading_magnetic_deg % 360.0,
                "MAGNETIC",
            )
        return HeadingFusionResult(
            gps_quality,
            math.nan,
            "INVALID",
        )

    def _select_magnetic_primary(
        self,
        *,
        gps_quality,
        gps_heading,
        gps_speed,
        position_state,
        wheel_speed,
        wheel_available,
        magnetic_heading,
        magnetic_available,
        now,
        model_used,
        generation,
        teachers,
        physical_ready,
        magnetic_allowed,
    ):
        magnetic = self.magnetic_confirmation.update(
            now_s=now.timestamp(),
            generation=generation,
            model_used=model_used,
            teachers=teachers,
            magnetic_available=magnetic_available,
            physical_ready=physical_ready,
            external_allowed=magnetic_allowed,
        )
        if magnetic.allowed:
            return HeadingFusionResult(
                gps_quality,
                magnetic_heading % 360.0,
                "MAGNETIC",
                "MAGNETIC_PRIMARY",
                magnetic.reason,
            )
        if not wheel_available or not self._finite(wheel_speed):
            gps_reason = "WHEEL_UNAVAILABLE"
        elif wheel_speed < self.G_WHEEL_MIN_SPEED_MPS:
            gps_reason = "WHEEL_STOPPED"
        elif position_state != 1:
            gps_reason = "GPS_POSITION_UNACCEPTED"
        elif not self._finite(gps_speed) or gps_speed < self.G_FALLBACK_MIN_SPEED_MPS:
            gps_reason = "GPS_SLOW_OR_HELD"
        elif gps_quality < self.G_FALLBACK_MIN_QUALITY:
            gps_reason = "GPS_QUALITY_LOW"
        elif not self.wheel_speed_matches(wheel_speed, gps_speed):
            gps_reason = "GPS_WHEEL_SPEED_MISMATCH"
        else:
            return HeadingFusionResult(
                gps_quality,
                gps_heading % 360.0,
                "GPS",
                "GPS_FALLBACK",
                magnetic.reason,
            )
        return HeadingFusionResult(
            gps_quality,
            math.nan,
            "INVALID",
            gps_reason,
            magnetic.reason,
        )
