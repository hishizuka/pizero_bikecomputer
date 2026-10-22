"""Provisional absolute magnetic admission, independent of F1 learning permission."""

from collections import deque
from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class MagneticHeadingTeacher:
    timestamp: float
    raw_error_deg: float
    f1_error_deg: float
    model_ready: bool


@dataclass(frozen=True)
class MagneticHeadingConfirmationResult:
    allowed: bool
    reason: str
    teachers: int
    median_deg: float
    p95_deg: float


class MagneticHeadingConfirmation:
    # Exploratory values from the two wheel-sensor rides, not validated limits.
    G_TEACHERS = 30
    G_HISTORY_S = 600.0
    G_MEDIAN_DEG = 5.0
    G_P95_DEG = 10.0
    G_HOLD_DEG = 25.0
    G_RECOVER_DEG = 5.0
    G_RECOVER_TEACHERS = 5

    def __init__(self):
        self.reset()

    def reset(self):
        self._generation = None
        self._history = deque(maxlen=self.G_TEACHERS)
        self._recovery = deque(maxlen=self.G_RECOVER_TEACHERS)
        self._last_teacher = -math.inf
        self._held = False
        self._credential = False
        self._ever_admitted = False
        self.externally_rejected = False

    def update(
        self,
        *,
        now_s,
        generation,
        model_used,
        teachers,
        magnetic_available,
        physical_ready=True,
        external_allowed=None,
    ):
        if generation != self._generation:
            self.reset()
            self._generation = generation
        if external_allowed is False:
            self.externally_rejected = True
        elif external_allowed is True:
            self.externally_rejected = False
        while self._history and now_s - self._history[0].timestamp > self.G_HISTORY_S:
            self._history.popleft()
        if not self._history:
            self._credential = False
        for teacher in teachers:
            # Duplicate or delayed replays cannot advance confirmation/recovery.
            if not self._last_teacher < teacher.timestamp <= now_s:
                continue
            if now_s - teacher.timestamp > self.G_HISTORY_S:
                continue
            if teacher.timestamp - self._last_teacher > self.G_HISTORY_S:
                self._recovery.clear()
            self._last_teacher = teacher.timestamp
            self._history.append(teacher)
            error = abs(
                teacher.f1_error_deg if teacher.model_ready else teacher.raw_error_deg
            )
            if error > self.G_HOLD_DEG:
                self._held = True
                self._recovery.clear()
            elif error <= self.G_RECOVER_DEG and self._held:
                self._recovery.append(teacher)
                if len(self._recovery) == self.G_RECOVER_TEACHERS:
                    self._held = False
                    if self._ever_admitted:
                        self._history = deque(self._recovery, maxlen=self.G_TEACHERS)
                        self._credential = True
                    self._recovery.clear()
            else:
                self._recovery.clear()
        errors = [
            abs(t.f1_error_deg if model_used == "F1" else t.raw_error_deg)
            for t in self._history
        ]
        median = float(np.median(errors)) if errors else math.nan
        p95 = float(np.percentile(errors, 95)) if errors else math.nan
        needed = self.G_RECOVER_TEACHERS if self._credential else self.G_TEACHERS
        if not physical_ready:
            reason = "PHYSICAL_CALIBRATION"
        elif not magnetic_available:
            reason = "MAGNETIC_MISSING_OR_STALE"
        elif self.externally_rejected:
            reason = "EXTERNAL_REJECTION"
        elif self._held:
            reason = "ABSOLUTE_HOLD"
        elif model_used != "F1":
            reason = "MODEL_NOT_READY"
        elif len(errors) < needed:
            reason = "ABSOLUTE_WARMUP"
        elif median > self.G_MEDIAN_DEG or p95 > self.G_P95_DEG:
            reason = "ABSOLUTE_RESIDUAL"
        else:
            reason = "ABSOLUTE_ONLY" if external_allowed is None else "CONFIRMED"
            self._credential = self._ever_admitted = True
        return MagneticHeadingConfirmationResult(
            reason in ("ABSOLUTE_ONLY", "CONFIRMED"),
            reason,
            len(errors),
            median,
            p95,
        )
