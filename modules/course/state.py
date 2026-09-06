from dataclasses import dataclass, field

import numpy as np


def _empty_array():
    return np.array([])


@dataclass
class CourseIndex:
    cutoff: int
    value: int = 0
    course_points_index: int = 0
    on_course_status: bool = False
    altitude: float = np.nan
    distance: float = 0
    check: list[bool] = field(default_factory=list)

    def __post_init__(self):
        self.reset()

    def reset(self):
        self.value = 0
        self.course_points_index = 0
        self.distance = 0
        self.altitude = np.nan
        self.on_course_status = False
        self.check = [True] * self.cutoff


@dataclass
class CoursePoints:
    name: np.ndarray = field(default_factory=_empty_array)
    type: np.ndarray = field(default_factory=_empty_array)
    altitude: np.ndarray = field(default_factory=_empty_array)
    distance: np.ndarray = field(default_factory=_empty_array)
    latitude: np.ndarray = field(default_factory=_empty_array)
    longitude: np.ndarray = field(default_factory=_empty_array)
    notes: np.ndarray = field(default_factory=_empty_array)

    @property
    def is_set(self):
        # FIT does not require course-point fields, but an empty name array is
        # still the established indicator used by the application.
        return bool(len(self.name))

    def reset(self):
        self.name = np.array([])
        self.type = np.array([])
        self.altitude = np.array([])
        self.distance = np.array([])
        self.latitude = np.array([])
        self.longitude = np.array([])
        self.notes = np.array([])


@dataclass
class CourseData:
    """Own raw and derived data for one course instance."""

    info: dict = field(default_factory=dict)
    distance: np.ndarray = field(default_factory=_empty_array)
    altitude: np.ndarray = field(default_factory=_empty_array)
    latitude: np.ndarray = field(default_factory=_empty_array)
    longitude: np.ndarray = field(default_factory=_empty_array)
    source_altitude_min: float = np.nan
    total_ascent: float = np.nan
    course_points: CoursePoints = field(default_factory=CoursePoints)
    points_diff: np.ndarray = field(default_factory=_empty_array)
    points_diff_sum_of_squares: np.ndarray = field(default_factory=_empty_array)
    points_diff_dist: np.ndarray = field(default_factory=_empty_array)
    azimuth: np.ndarray = field(default_factory=_empty_array)
    slope: np.ndarray = field(default_factory=_empty_array)
    slope_smoothing: np.ndarray = field(default_factory=_empty_array)
    colored_altitude: np.ndarray = field(default_factory=_empty_array)
    climb_segment: list[dict] = field(default_factory=list)
    wind_course_indices: list[int] = field(default_factory=list)
    wind_timeline: list = field(default_factory=list)
    wind_speed: list[float] = field(default_factory=list)
    wind_direction: list[float] = field(default_factory=list)
    temperature: list[float] = field(default_factory=list)
    precipitation: list[float] = field(default_factory=list)
    cloud_cover: list[float] = field(default_factory=list)
