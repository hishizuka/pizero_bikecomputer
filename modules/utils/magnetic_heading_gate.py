"""Compare time-aligned magnetic heading changes with independent gyro rotation.

This component does not derive yaw from three-axis body rotation or align clocks.
The caller supplies one continuous yaw increment between successive observations.
Use physical magnetic heading before online model changes, or evaluate both ends
with the same correction model. Reset explicitly after physical calibration.
"""

from collections import deque
from dataclasses import dataclass
import math

from .geo import get_angle_difference

@dataclass(frozen=True)
class MagneticHeadingGateResult:
    state: str
    magnetic_allowed: bool | None
    predicted_heading_deg: float
    residual_deg: float


class MagneticHeadingGate:
    # Provisional thresholds for replay; road validation is required before use.
    G_REJECT_DEG = 20.0
    G_RECOVER_DEG = 8.0
    G_RECOVER_SAMPLES = 3
    G_HISTORY_S = 6.0
    G_MAX_BRIDGE_S = 6.0
    G_MAX_INTERVAL_S = 1.5

    def __init__(self):
        self.reset()

    def reset(self):
        self._history = deque()
        self._last_timestamp = None
        self._last_accepted_timestamp = None
        self._rotation = 0.0
        self._rejected = False
        self._reference = None
        self._recoveries = 0
        self._result = MagneticHeadingGateResult("UNVERIFIED", None, math.nan, math.nan)

    def _finish(self, state, allowed, predicted=math.nan, residual=math.nan):
        self._result = MagneticHeadingGateResult(state, allowed, predicted, residual)
        return self._result

    def invalidate(self):
        """Forget clock/history while retaining an already confirmed rejection."""
        rejected = self._result.magnetic_allowed is False
        self.reset()
        if rejected:
            self._rejected = True
            return self._finish("EXPIRED", False)
        return self._result

    def update(
        self,
        *,
        timestamp_s,
        heading_deg,
        delta_heading_deg,
        continuous,
        transform_heading=None,
    ):
        """Return evidence; UNVERIFIED is not permission to trust magnetic data.

        A gap during rejection latches EXPIRED until an explicit reset with an
        independently trusted reference. A stable but displaced magnetic heading
        cannot recover by becoming the new reference. Predictions are diagnostic
        inputs for the future fusion caller, not a replacement heading output.
        """
        if not math.isfinite(timestamp_s):
            raise ValueError("timestamp_s must be finite")
        if self._last_timestamp is not None and timestamp_s <= self._last_timestamp:
            # Repeated observations must not advance recovery hysteresis.
            return self._result

        previous_time = self._last_timestamp
        self._last_timestamp = timestamp_s
        valid = (
            continuous
            and math.isfinite(delta_heading_deg)
            and previous_time is not None
            and timestamp_s - previous_time <= self.G_MAX_INTERVAL_S
        )
        if not valid:
            self._history.clear()
            self._reference = None
            self._rotation = 0.0
            self._recoveries = 0
            if self._rejected:
                return self._finish("EXPIRED", False)
            if math.isfinite(heading_deg):
                self._history.append((timestamp_s, heading_deg % 360.0, 0.0))
                self._last_accepted_timestamp = timestamp_s
            return self._finish("UNVERIFIED", None)

        self._rotation += delta_heading_deg
        if self._rejected:
            if self._reference is None:
                return self._finish("EXPIRED", False)
            reference = self._reference
        else:
            while (
                self._history and timestamp_s - self._history[0][0] > self.G_HISTORY_S
            ):
                self._history.popleft()
            if not self._history:
                if math.isfinite(heading_deg):
                    self._history.append(
                        (timestamp_s, heading_deg % 360.0, self._rotation)
                    )
                    self._last_accepted_timestamp = timestamp_s
                return self._finish("UNVERIFIED", None)
            # Keep a multi-second reference so a gradual disturbance cannot hide
            # behind small differences from the immediately preceding sample.
            reference = self._history[0]

        _, ref_heading, ref_rotation = reference
        # Apply the current F1 to both physical observations. Model updates must
        # not be mistaken for sensor rotation, including a NONE/F1 transition.
        current_heading = heading_deg
        if transform_heading is not None:
            ref_heading = transform_heading(ref_heading)
            current_heading = transform_heading(heading_deg)
        predicted = (ref_heading + self._rotation - ref_rotation) % 360.0
        if timestamp_s - self._last_accepted_timestamp > self.G_MAX_BRIDGE_S:
            return self._finish("EXPIRED", False)
        if not math.isfinite(heading_deg):
            self._recoveries = 0
            return self._finish(
                "REJECTED" if self._rejected else "UNVERIFIED",
                False if self._rejected else None,
                predicted,
            )
        residual = get_angle_difference(current_heading, predicted)

        if self._rejected:
            if abs(residual) <= self.G_RECOVER_DEG:
                self._recoveries += 1
            else:
                self._recoveries = 0
            if self._recoveries < self.G_RECOVER_SAMPLES:
                return self._finish("REJECTED", False, predicted, residual)
            self._rejected = False
            self._reference = None
            self._recoveries = 0
            self._history.clear()
        elif abs(residual) > self.G_REJECT_DEG:
            self._rejected = True
            self._reference = reference
            return self._finish("REJECTED", False, predicted, residual)

        self._history.append((timestamp_s, heading_deg % 360.0, self._rotation))
        self._last_accepted_timestamp = timestamp_s
        return self._finish("CONSISTENT", True, predicted, residual)
