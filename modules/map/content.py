"""Scale, route markers and navigation content independent of GUI bindings."""

from dataclasses import dataclass
import math

import numpy as np

from modules.utils.geo import get_mod_lat_np, get_width_distance

from .geometry import offset_points_by_segment
from .policy import COURSE_POINT_MIN_ZOOM, course_point_start, clamp_zoom
from .projection import project
from .style import (
    DEFAULT_COURSE_POINT_ICON_PATH as DEFAULT_INSTRUCTION_ICON,
    COURSE_WIND_MARKER_SIZE,
    COURSE_OUTLINE_WIDTH,
    COURSE_POINT_MARKER_SIZE,
)

INSTRUCTION_ICONS = {
    "Straight": "img/navi_straight_white.svg",
    "Right": "img/navi_turn_right_white.svg",
    "Left": "img/navi_turn_left_white.svg",
    "Slight Right": "img/navi_turn_slight_right_white.svg",
    "Slight Left": "img/navi_turn_slight_left_white.svg",
    "Sharp Right": "img/navi_turn_sharp_right_white.svg",
    "Sharp Left": "img/navi_turn_sharp_left_white.svg",
    "Uturn Left": "img/navi_uturn_left_white.svg",
    "Uturn Right": "img/navi_uturn_right_white.svg",
    "Uturn": "img/navi_uturn_right_white.svg",
    "Summit": "img/summit.png",
}


def scale_content(latitude, longitude_per_pixel, zoom, width=40):
    distance = get_width_distance(latitude, longitude_per_pixel * width)
    if not math.isfinite(distance) or distance <= 0:
        return None
    num = distance / (10 ** int(np.log10(distance)))
    factor = 1
    for low, high in ((1, 2), (2, 5), (5, 10)):
        if low < num < high:
            factor = high / num
            break
    label, unit = round(distance * factor), "m"
    if label >= 1000:
        label, unit = int(label / 1000), "km"
    return f"{label}{unit}\n(z{zoom})", width * factor


def instruction_distance_text(distance):
    return f"{distance / 1000:4.1f}km " if distance > 1000 else f"{distance:6.0f}m  "


def navigation_zoom(distance, zoom, target, previous):
    target = clamp_zoom(target)
    if distance is not None and distance < 1000:
        if previous is None and zoom < target:
            return target, zoom
    elif distance is not None and previous is not None:
        return previous if zoom == target else zoom, None
    return zoom, previous


def course_instruction(course):
    points = course.course_points
    start = max(0, int(course.index.course_points_index))
    for i in range(start, len(points.distance)):
        distance = float(points.distance[i]) * 1000 - float(course.index.distance)
        if distance >= 0:
            return str(points.type[i]) if i < len(points.type) else "", distance
    return "", None


def _legacy_project(longitude, latitude):
    return longitude, get_mod_lat_np(latitude)


def course_point_segments(course, projection=_legacy_project):
    points = course.course_points
    if len(points.distance) == len(points.longitude):
        return np.clip(
            np.searchsorted(course.distance, points.distance, side="right") - 1,
            0,
            len(course.longitude) - 2,
        )
    indices = np.empty(len(points.longitude), dtype=np.int32)
    start = 0
    course_x, course_y = projection(course.longitude, course.latitude)
    point_x, point_y = projection(points.longitude, points.latitude)
    for i in range(len(indices)):
        delta = (course_x[start:] - point_x[i]) ** 2 + (
            course_y[start:] - point_y[i]
        ) ** 2
        nearest = start + int(np.argmin(delta))
        indices[i] = min(nearest, len(course.longitude) - 2)
        start = min(nearest + 1, len(course.longitude) - 1)
    return indices


def course_point_positions(
    course,
    scale,
    offset,
    marker_size=COURSE_POINT_MARKER_SIZE,
    outline_width=COURSE_OUTLINE_WIDTH,
    gap=4,
    projection=_legacy_project,
):
    points = course.course_points
    x, y = projection(points.longitude, points.latitude)
    if not offset or len(course.longitude) < 2:
        return x, y
    return offset_points_by_segment(
        *projection(course.longitude, course.latitude),
        x,
        y,
        course_point_segments(course, projection),
        scale,
        offset + ((outline_width + marker_size) / 2 + gap) * np.sign(offset),
    )


class Navigation:
    def __init__(self):
        self.clear()

    def clear(self):
        self.name = ""
        self.distance = None

    def set_external(self, name, distance):
        try:
            distance = float(distance)
        except (TypeError, ValueError):
            self.clear()
            return
        name = str(name).strip()
        if not name or not math.isfinite(distance) or distance < 0:
            self.clear()
            return
        self.name, self.distance = name, distance

    def instruction(self, course, indexing):
        if course.course_points.is_set and indexing:
            return course_instruction(course)
        return self.name, self.distance


def course_wind_positions(
    course, markers, scale, offset, traffic_side, projection=_legacy_project
):
    indices = np.asarray([marker[0] for marker in markers], dtype=np.int32)
    x, y = projection(course.longitude[indices], course.latitude[indices])
    if len(course.longitude) < 2:
        return x, y
    side = -1 if traffic_side == "RIGHT" else 1
    return offset_points_by_segment(
        *projection(course.longitude, course.latitude),
        x,
        y,
        np.minimum(indices, len(course.longitude) - 2),
        scale,
        offset + ((COURSE_OUTLINE_WIDTH + COURSE_WIND_MARKER_SIZE) / 2 + 4) * side,
    )


class CourseMarkerLayout:
    """Reuse world coordinates until the legacy course-layout threshold is met."""

    def __init__(self):
        self._cache = {"points": None, "winds": None}

    def _positions(self, attribute, key, scale, build):
        previous = self._cache[attribute]
        if (
            previous is None
            or previous[0] != key
            or any(
                abs(old - new) > abs(old) * 1e-3 for old, new in zip(previous[1], scale)
            )
        ):
            previous = (key, scale, build())
            self._cache[attribute] = previous
        return previous[2]

    def points(
        self,
        course,
        scale,
        offset,
        marker_size=COURSE_POINT_MARKER_SIZE,
        outline_width=COURSE_OUTLINE_WIDTH,
        projection=_legacy_project,
    ):
        points = course.course_points
        key = (
            projection,
            id(course.longitude),
            id(course.latitude),
            id(course.distance),
            id(points.longitude),
            id(points.latitude),
            id(points.distance),
            offset,
            marker_size,
            outline_width,
        )
        return self._positions(
            "points",
            key,
            scale,
            lambda: course_point_positions(
                course, scale, offset, marker_size, outline_width, projection=projection
            ),
        )

    def winds(self, course, markers, scale, offset, side, projection=_legacy_project):
        key = (
            projection,
            id(course.longitude),
            id(course.latitude),
            course.weather_revision,
            markers,
            offset,
            side,
        )
        return self._positions(
            "winds",
            key,
            scale,
            lambda: course_wind_positions(
                course, markers, scale, offset, side, projection
            ),
        )


@dataclass(frozen=True, slots=True)
class MapHud:
    scale_text: str
    scale_width: float
    attribution: str
    markers: tuple
    instruction_name: str
    instruction_distance: float | None
    legend: dict | None
    winds: tuple = ()
    center_size: float = 0


def map_hud(config, view, offset, center_size=0):
    lon0, lon1, lat0, lat1 = view.bounds
    ratio = view.pixel_ratio
    width, height = view.width / ratio, view.height / ratio
    scale = scale_content(view.latitude, (lon1 - lon0) / width, view.zoom)
    markers, winds = [], []
    name, distance = "", None
    if config.logger is not None:
        course = config.logger.course
        name, distance = config.map.navigation.instruction(
            course, config.G_COURSE_INDEXING
        )
        points = course.course_points
        x0, x1, y0, y1 = view.projected_bounds
        scale_per_pixel = ((x1 - x0) / width, (y1 - y0) / height)
        wind_markers = config.map.course_wind_markers(course)
        if wind_markers:
            xs, ys = config.map.marker_layout.winds(
                course,
                wind_markers,
                scale_per_pixel,
                offset,
                config.G_COURSE_TRAFFIC_SIDE,
                projection=project,
            )
            for (_, angle, color), x, y in zip(wind_markers, xs, ys):
                x = (x - x0) / scale_per_pixel[0]
                y = (y1 - y) / scale_per_pixel[1]
                margin = COURSE_WIND_MARKER_SIZE
                if -margin <= x <= width + margin and -margin <= y <= height + margin:
                    winds.append((float(x), float(y), angle, color))
        if points.is_set and view.zoom >= COURSE_POINT_MIN_ZOOM:
            xs, ys = config.map.marker_layout.points(
                course,
                scale_per_pixel,
                offset,
                projection=project,
            )
            start = course_point_start(course, len(xs))
            margin = COURSE_POINT_MARKER_SIZE / 2
            for i in reversed(range(start, len(xs))):
                x, y = (xs[i] - x0) / (x1 - x0) * width, (y1 - ys[i]) / (
                    y1 - y0
                ) * height
                if -margin <= x <= width + margin and -margin <= y <= height + margin:
                    markers.append(
                        (
                            float(x),
                            float(y),
                            INSTRUCTION_ICONS.get(
                                str(points.type[i]), DEFAULT_INSTRUCTION_ICON
                            ),
                        )
                    )
    return MapHud(
        *(scale or ("", 0)),
        config.map.overlays.attribution(),
        tuple(markers),
        name,
        distance,
        config.map.overlays.legend(),
        tuple(winds),
        center_size,
    )
