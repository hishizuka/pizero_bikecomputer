"""Magnetic Fourier correction learned from delayed GPS teachers."""

import math
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime
from numbers import Real

import numpy as np

from modules.app_logger import app_logger
from modules.utils.geo import get_angle_difference
from modules.utils.magnetic_heading_confirmation import MagneticHeadingTeacher


def _features(heading):
    phi = math.radians(heading)
    return np.array(
        [1.0, math.sin(phi), math.cos(phi), math.sin(2 * phi), math.cos(2 * phi)]
    )


class _FourierModel:
    G_FORGETTING_FACTOR = 0.999
    G_RIDGE_CONSTANT = 5.0
    G_RIDGE_HARMONIC = 20.0

    def __init__(self, size):
        self.size = size
        self.S = np.zeros((size, size))
        self.b = np.zeros(size)
        self.ridge = np.diag(
            [self.G_RIDGE_CONSTANT] + [self.G_RIDGE_HARMONIC] * (size - 1)
        )
        self.theta = np.zeros(size)

    def predict(self, heading):
        return float(_features(heading)[: self.size] @ self.theta)

    def update(self, heading, target):
        x = _features(heading)[: self.size]
        self.S = self.G_FORGETTING_FACTOR * self.S + np.outer(x, x)
        self.b = self.G_FORGETTING_FACTOR * self.b + x * target
        self.theta = np.linalg.solve(self.S + self.ridge, self.b)


@dataclass(frozen=True)
class MagneticHeadingCorrectionResult:
    heading_magnetic_corrected_deg: float
    heading_magnetic_model_used: str
    heading_magnetic_model_samples: int
    heading_magnetic_current_bin_samples: int
    heading_magnetic_declination_deg: float
    teachers: tuple[MagneticHeadingTeacher, ...] = ()


@dataclass(frozen=True)
class _Observation:
    timestamp: float
    gps: float
    magnetic: float
    declination: float
    learnable: bool

    @property
    def heading(self):
        return (self.magnetic - self.declination) % 360.0


class MagneticHeadingCorrection:
    G_STATE_KEY = "magnetic_heading_correction"
    G_STATE_VERSION = 1
    G_MIN_SPEED = 5.0
    G_MIN_GPS_QUALITY = 0.8
    G_WINDOW_HALF_S = 2.0
    G_ENDPOINT_TOLERANCE_S = 0.25
    G_MAX_GAP_S = 1.5
    G_MAX_PAIR_DELTA_S = 1.0
    G_MAX_MAG_AGE_S = 3.0
    G_MAX_TURN_DEG_S = 1.5
    G_TARGET_GATE_DEG = 60.0
    G_RESIDUAL_GATE_DEG = 30.0
    G_READY_SAMPLES = 60
    G_CONFIRM_SAMPLES = 30
    G_READY_GAIN_DEG = 0.5
    G_REJECTION_WINDOW = 60
    G_REJECTION_FRACTION = 0.5
    G_RECONFIRM_MEDIAN_DEG = 10.0
    G_RECONFIRM_P95_DEG = 20.0
    G_HISTORY_LENGTH_S = 6.0
    G_DEBUG_INTERVAL_S = 30.0

    def __init__(self):
        self.calibration_epoch = 0
        self.generation = 0
        self.revision = 0
        self._date = None
        self.reset("initialize")

    @staticmethod
    def _finite(value):
        return isinstance(value, Real) and math.isfinite(value)

    def reset(self, reason, *, calibration=False):
        self.generation += 1
        self._teacher_evidence = []
        if calibration:
            self.calibration_epoch += 1
        self.f1, self.f2 = _FourierModel(3), _FourierModel(5)
        self.samples = 0
        self.bin_samples = np.zeros(8, dtype=np.int64)
        self.ready = False
        self._restoring = self._quarantined = False
        self._history = deque()
        self._pending = deque()
        self._errors = deque(maxlen=self.G_CONFIRM_SAMPLES)
        self._confirmation = deque(maxlen=self.G_CONFIRM_SAMPLES)
        self._rejections = deque(maxlen=self.G_REJECTION_WINDOW)
        self._last_gps_timestamp = None
        self._last_debug_timestamp = -math.inf
        self._debug_counts = Counter()
        self._update_ms = deque(maxlen=30)
        self.revision += 1
        app_logger.info(
            "[MAG-HEADING] reset reason=%s epoch=%s", reason, self.calibration_epoch
        )

    def snapshot(self):
        return {
            "version": self.G_STATE_VERSION,
            "calibration_epoch": self.calibration_epoch,
            "f1": {"S": self.f1.S.tolist(), "b": self.f1.b.tolist()},
            "f2": {"S": self.f2.S.tolist(), "b": self.f2.b.tolist()},
            "samples": self.samples,
            "bin_samples": self.bin_samples.tolist(),
        }

    def restore(self, state):
        # State files may contain older or incomplete layouts.
        if not isinstance(state, dict) or state.get("version") != self.G_STATE_VERSION:
            return False
        try:
            samples, epoch = state["samples"], state["calibration_epoch"]
            counts = np.asarray(state["bin_samples"], dtype=float)
            if (
                not isinstance(samples, int) or samples < 0
                or not isinstance(epoch, int) or epoch < 0
                or counts.shape != (8,) or not np.isfinite(counts).all()
                or np.any(counts < 0) or np.any(counts != np.floor(counts))
                or float(counts.sum()) != samples
            ):
                return False
            models = [_FourierModel(3), _FourierModel(5)]
            for model, name in zip(models, ("f1", "f2")):
                S = np.asarray(state[name]["S"], dtype=float)
                b = np.asarray(state[name]["b"], dtype=float)
                if (
                    S.shape != (model.size, model.size) or b.shape != (model.size,)
                    or not np.isfinite(S).all() or not np.isfinite(b).all()
                    or not np.allclose(S, S.T) or np.any(np.diag(S) < 0)
                ):
                    return False
                np.linalg.cholesky(S + model.ridge)
                model.S, model.b = S.copy(), b.copy()
                model.theta = np.linalg.solve(S + model.ridge, b)
        except (KeyError, TypeError, ValueError, OverflowError, np.linalg.LinAlgError):
            return False
        self.reset("restore")
        self.f1, self.f2 = models
        self.samples, self.calibration_epoch = samples, epoch
        self.bin_samples = counts.astype(np.int64)
        # Partial warmup can continue learning, but never applies immediately.
        self._restoring = samples >= self.G_READY_SAMPLES
        app_logger.info("[MAG-HEADING] restored samples=%s; output=NONE", samples)
        return True

    def _clear_pending(self):
        self._history.clear()
        self._pending.clear()
        self._confirmation.clear()

    def correct_heading_for_motion(self, phase_deg):
        """Evaluate a declination-free physical phase using this model revision."""
        return (
            (phase_deg - self.f1.predict(phase_deg)) % 360
            if self.ready else phase_deg
        )

    def _beats_raw(self, errors):
        if len(errors) < self.G_CONFIRM_SAMPLES:
            return False
        values = np.abs(np.asarray(errors)[:, :2])
        return (
            np.median(values[:, 1]) <= np.median(values[:, 0]) - self.G_READY_GAIN_DEG
            and np.percentile(values[:, 1], 95) <= np.percentile(values[:, 0], 95)
        )

    def _learn(self, sample):
        heading = sample.heading
        target = get_angle_difference(heading, sample.gps)
        raw_error = get_angle_difference(sample.magnetic, sample.gps)
        e1 = get_angle_difference(target, self.f1.predict(heading))
        self._teacher_evidence.append(
            MagneticHeadingTeacher(sample.timestamp, raw_error, e1, self.ready)
        )
        raw_bad = abs(target) >= self.G_TARGET_GATE_DEG
        residual_bad = (
            self.samples >= self.G_READY_SAMPLES and abs(e1) > self.G_RESIDUAL_GATE_DEG
        )
        rejected = raw_bad or residual_bad
        self._rejections.append(rejected)
        self._errors.append((raw_error, e1))
        alarm = (
            len(self._rejections) == self.G_REJECTION_WINDOW
            and sum(self._rejections) / self.G_REJECTION_WINDOW > self.G_REJECTION_FRACTION
        )
        if raw_bad:
            reason = "target_gate"
        elif residual_bad:
            reason = "residual_gate"
        elif self._quarantined:
            reason = "quarantined"
        elif self._restoring:
            reason = "restore_confirmation"
        elif alarm:
            reason = "persistent_rejection"
        else:
            reason = "accepted"
        self._debug_counts[f"teacher_{reason}"] += 1
        if alarm and not self._quarantined:
            self.ready = self._restoring = False
            self._quarantined = True
            self._confirmation.clear()
            app_logger.info(
                "[MAG-HEADING] invalidated; statistics frozen epoch=%s", self.calibration_epoch
            )
            return
        if self._quarantined or self._restoring:
            self._confirmation.append((raw_error, e1, target))
            if len(self._confirmation) == self.G_CONFIRM_SAMPLES:
                values = np.abs(np.asarray(self._confirmation))
                consistent = (
                    np.median(values[:, 1]) <= self.G_RECONFIRM_MEDIAN_DEG
                    and np.percentile(values[:, 1], 95) <= self.G_RECONFIRM_P95_DEG
                    and np.all(values[:, 2] < self.G_TARGET_GATE_DEG)
                )
                if consistent and (self._restoring or self._beats_raw(self._confirmation)):
                    self.ready = (
                        self.samples >= self.G_READY_SAMPLES
                        and self._beats_raw(self._confirmation)
                    )
                    self._quarantined = self._restoring = False
                    self._rejections.clear()
                    app_logger.info(
                        "[MAG-HEADING] reconfirmed ready=%s samples=%s", self.ready, self.samples
                    )
            return
        if rejected:
            return
        self.f1.update(heading, target)
        self.f2.update(heading, target)
        self.samples += 1
        self.bin_samples[int(heading // 45)] += 1
        self.revision += 1
        if (
            not self.ready and self.samples >= self.G_READY_SAMPLES
            and self._beats_raw(self._errors)
        ):
            self.ready = True
            app_logger.info("[MAG-HEADING] ready model=F1 samples=%s", self.samples)

    def _process_pending(self, latest_time):
        while (
            self._pending
            and self._pending[0].timestamp + self.G_WINDOW_HALF_S <= latest_time
        ):
            sample = self._pending.popleft()
            left_target = sample.timestamp - self.G_WINDOW_HALF_S
            right_target = sample.timestamp + self.G_WINDOW_HALF_S
            history = list(self._history)
            left = min(range(len(history)), key=lambda i: abs(history[i].timestamp - left_target))
            right = min(range(len(history)), key=lambda i: abs(history[i].timestamp - right_target))
            if (
                abs(history[left].timestamp - left_target) > self.G_ENDPOINT_TOLERANCE_S
                or abs(history[right].timestamp - right_target) > self.G_ENDPOINT_TOLERANCE_S
                or history[left].timestamp >= sample.timestamp
                or history[right].timestamp <= sample.timestamp
            ):
                self._debug_counts["window_endpoint"] += 1
                continue
            unwrapped = np.degrees(
                np.unwrap(np.radians([s.gps for s in history[left : right + 1]]))
            )
            turn = abs(unwrapped[-1] - unwrapped[0]) / (
                history[right].timestamp - history[left].timestamp
            )
            if turn <= self.G_MAX_TURN_DEG_S:
                self._learn(sample)
            else:
                self._debug_counts["window_turn"] += 1

    def update(
        self, *, heading_gps_deg, heading_gps_timestamp, gps_speed, gps_mode,
        heading_gps_quality, gps_position_quality_state, heading_magnetic_deg,
        heading_magnetic_timestamp, heading_magnetic_declination_deg,
        now, learning_enabled=True,
    ):
        update_start = time.perf_counter()
        self._teacher_evidence = []
        if self._date is not None and now.date() != self._date:
            self.reset("date_change")
        self._date = now.date()
        gps_time = (
            heading_gps_timestamp.timestamp()
            if isinstance(heading_gps_timestamp, datetime) else None
        )
        mag_time = (
            heading_magnetic_timestamp.timestamp()
            if isinstance(heading_magnetic_timestamp, datetime) else None
        )
        clock = now.timestamp()
        mag_valid = (
            self._finite(heading_magnetic_deg)
            and self._finite(heading_magnetic_declination_deg)
            and mag_time is not None and 0 <= clock - mag_time <= self.G_MAX_MAG_AGE_S
        )
        trusted = (
            learning_enabled and mag_valid and gps_time is not None
            and self._finite(heading_gps_deg) and self._finite(gps_mode) and gps_mode >= 3
            and self._finite(heading_gps_quality)
            and heading_gps_quality >= self.G_MIN_GPS_QUALITY
            and gps_position_quality_state == 1 and 0 <= clock - gps_time <= self.G_MAX_GAP_S
        )
        if not trusted:
            self._clear_pending()
        elif gps_time != self._last_gps_timestamp:
            if (
                self._last_gps_timestamp is not None
                and not 0 < gps_time - self._last_gps_timestamp <= self.G_MAX_GAP_S
            ):
                self._clear_pending()
            self._last_gps_timestamp = gps_time
            paired = abs(gps_time - mag_time) <= self.G_MAX_PAIR_DELTA_S
            sample = _Observation(
                gps_time, float(heading_gps_deg), float(heading_magnetic_deg),
                float(heading_magnetic_declination_deg),
                paired and self._finite(gps_speed) and gps_speed >= self.G_MIN_SPEED,
            )
            self._history.append(sample)
            if sample.learnable:
                self._pending.append(sample)
            self._debug_counts["pairs"] += 1
            self._debug_counts["learnable"] += int(sample.learnable)
            self._debug_counts["pair_mismatch"] += int(not paired)
            self._process_pending(gps_time)
            while (
                self._history
                and self._history[0].timestamp < gps_time - self.G_HISTORY_LENGTH_S
            ):
                self._history.popleft()
        if not mag_valid:
            return MagneticHeadingCorrectionResult(
                math.nan, "NONE", self.samples, 0, heading_magnetic_declination_deg,
                tuple(self._teacher_evidence),
            )
        heading = (heading_magnetic_deg - heading_magnetic_declination_deg) % 360.0
        corrected = (
            (heading - self.f1.predict(heading)) % 360.0
            if self.ready else heading_magnetic_deg
        )
        self._update_ms.append((time.perf_counter() - update_start) * 1000.0)
        if clock >= self._last_debug_timestamp + self.G_DEBUG_INTERVAL_S:
            app_logger.debug(
                "[MAG-HEADING] samples=%s bins=%s f1=%s f2=%s update_avg_ms=%.3f update_p95_ms=%.3f counts=%s",
                self.samples, self.bin_samples.tolist(), self.f1.theta.tolist(), self.f2.theta.tolist(),
                float(np.mean(self._update_ms)), float(np.percentile(self._update_ms, 95)),
                dict(self._debug_counts),
            )
            self._debug_counts.clear()
            self._last_debug_timestamp = clock
        return MagneticHeadingCorrectionResult(
            float(corrected), "F1" if self.ready else "NONE", self.samples,
            int(self.bin_samples[int(heading // 45)]),
            float(heading_magnetic_declination_deg),
            tuple(self._teacher_evidence),
        )
