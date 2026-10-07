"""Course look-ahead shared by map pages, independent of Qt and rendering."""

import numpy as np

from modules.utils.geo import get_width_distance
from modules.utils.map import MAX_MERCATOR_LATITUDE


class CourseFocus:
    def __init__(self):
        self.reset()

    def reset(self):
        self.active = False
        self.off_samples = 0
        self.sample = None
        self.directions = (0, 0)

    @staticmethod
    def axis_direction(delta, span, previous):
        if span <= 0 or abs(delta) <= (0.20 if previous else 0.30) * span:
            return 0
        if delta > 0.30 * span:
            return 1
        if delta < -0.30 * span:
            return -1
        return previous

    def center(self, course, longitude, latitude, width, height, following, sample):
        if not following or not course.is_set:
            self.reset()
            return longitude, latitude
        if course.index.on_course_status:
            self.active, self.off_samples = True, 0
        elif sample != self.sample and self.active:
            self.off_samples += 1
            if self.off_samples >= 3:
                self.active = False
        # Repeated snapshots of one GPS sample must not advance off-course release.
        self.sample = sample
        if not self.active:
            self.directions = (0, 0)
            return longitude, latitude
        start = max(0, min(int(course.index.value), len(course.longitude) - 1))
        end = course.get_index_with_distance_cutoff(
            start, get_width_distance(latitude, width) / 1000
        )
        if end <= start:
            indices = np.array([end])
        else:
            indices = np.arange(start, end + 1, max(1, (end - start) // 8))
            if indices[-1] != end:
                indices = np.append(indices, end)
        weights = np.linspace(1.0, 2.0, len(indices))
        target = (
            float(np.average(course.longitude[indices], weights=weights)),
            float(np.average(course.latitude[indices], weights=weights)),
        )
        self.directions = tuple(
            self.axis_direction(delta, span, previous)
            for delta, span, previous in zip(
                (target[0] - longitude, target[1] - latitude),
                (width, height),
                self.directions,
            )
        )
        longitude += self.directions[0] * width * 0.25
        latitude += self.directions[1] * height * 0.25
        return (longitude + 180) % 360 - 180, max(
            -MAX_MERCATOR_LATITUDE, min(MAX_MERCATOR_LATITUDE, latitude)
        )
