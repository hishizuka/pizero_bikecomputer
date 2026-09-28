import math
from dataclasses import dataclass
from datetime import datetime
from numbers import Real


@dataclass(frozen=True)
class HeadingFusionResult:
    heading_gps_quality: float
    heading_fused_deg: float
    heading_fused_source: str


class HeadingFusion:
    GPS_FULL_QUALITY_SPEED_MPS = 5.0
    GPS_GOOD_ERROR_M = 3.0
    GPS_MAX_ERROR_M = 20.0
    SOURCE_MIN_QUALITY = 0.05
    MAX_AGE_S = 3.0

    def __init__(self, gps_speed_cutoff):
        self.gps_speed_cutoff = gps_speed_cutoff

    @staticmethod
    def _finite(value):
        return isinstance(value, Real) and math.isfinite(value)

    @staticmethod
    def _clamp(value):
        return min(1.0, max(0.0, value))

    def _age_quality(self, timestamp, now):
        if not isinstance(timestamp, datetime):
            return 0.0
        age_s = max(0.0, (now - timestamp).total_seconds())
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

    def magnetic_available(
        self,
        heading_magnetic_deg,
        heading_magnetic_timestamp,
        now,
    ):
        if not self._finite(heading_magnetic_deg):
            return False
        return (
            self._age_quality(heading_magnetic_timestamp, now)
            >= self.SOURCE_MIN_QUALITY
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
        magnetic_available = self.magnetic_available(
            heading_magnetic_deg,
            heading_magnetic_timestamp,
            now,
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
