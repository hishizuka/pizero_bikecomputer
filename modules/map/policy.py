"""Display decisions shared with the optimized legacy map."""

import math

from modules.utils.map import get_zoom_delta_from_tile_size

COURSE_POINT_MIN_ZOOM = 13


def clamp_zoom(zoom):
    return max(0, min(22, zoom))


def tile_zoom(zoom, source_size, target_size):
    return clamp_zoom(
        zoom
        + get_zoom_delta_from_tile_size(source_size)
        - get_zoom_delta_from_tile_size(target_size)
    )


def map_position(config, gps):
    """GPS already retains the last fix; use the legacy order when it is absent."""
    lon, lat = gps["lon"], gps["lat"]
    if not (math.isnan(lon) or math.isnan(lat)):
        return lon, lat
    return fallback_position(config)


def fallback_position(config):
    if config.map.track.last_position is not None:
        return config.map.track.last_position
    course = config.logger.course
    if course.is_set:
        return course.longitude[0], course.latitude[0]
    return config.G_DUMMY_POS_X, config.G_DUMMY_POS_Y


def axis_range_changed(start, end, view_px, previous, epsilon_px=20):
    if previous is None:
        return True
    prev_start, prev_end, prev_view_px = previous
    if abs(prev_view_px - view_px) >= 0.5:
        return True
    span, prev_span = abs(end - start), abs(prev_end - prev_start)
    if span <= 0 or prev_span <= 0:
        return True
    data_per_px = max(span, prev_span) / view_px
    move_px = max(abs(start - prev_start), abs(end - prev_end)) / data_per_px
    span_delta_px = abs(span - prev_span) / data_per_px
    return max(move_px, span_delta_px) >= epsilon_px


def course_point_start(course, count, forward=True):
    return max(0, min(int(course.index.course_points_index), count)) if forward else 0
