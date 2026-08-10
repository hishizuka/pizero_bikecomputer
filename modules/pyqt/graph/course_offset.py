import math

import numpy as np

_EPSILON = 1e-9
_UTURN_DOT_THRESHOLD = -0.95
_MITER_LIMIT = 2.0
_ARROW_LENGTH_RATIO = 33 / 22
_ARROW_SLOPE_RATIO = 13 / 22


def _cross_2d(vector_a, vector_b):
    return vector_a[0] * vector_b[1] - vector_a[1] * vector_b[0]


def _line_intersection(point_a, direction_a, point_b, direction_b):
    denominator = _cross_2d(direction_a, direction_b)
    if abs(denominator) <= _EPSILON:
        return (point_a + point_b) / 2
    return (
        point_a
        + (_cross_2d(point_b - point_a, direction_b) / denominator) * direction_a
    )


def _miter_point(point, tangents, offset_pixels):
    side = np.sign(offset_pixels)
    radius = abs(offset_pixels)
    normals = side * np.column_stack((-tangents[:, 1], tangents[:, 0]))
    intersection = _line_intersection(
        point + radius * normals[0],
        tangents[0],
        point + radius * normals[1],
        tangents[1],
    )
    if np.linalg.norm(intersection - point) <= _MITER_LIMIT * radius:
        return intersection
    return None


def _to_pixels(x_values, y_values, pixel_scale):
    points = np.column_stack((x_values, y_values)).astype(np.float64)
    origin = points[0]
    scale = np.asarray(pixel_scale)
    return (points - origin) / scale, origin, scale


def _direction_arrow_polygon(tip, tangent, width):
    half_width = width / 2
    length = _ARROW_LENGTH_RATIO * width
    slope_length = _ARROW_SLOPE_RATIO * width
    normal = half_width * np.array((-tangent[1], tangent[0]))
    shoulder = tip - slope_length * tangent
    tail = tip - length * tangent
    notch = tail + slope_length * tangent
    return np.array(
        (tip, shoulder + normal, tail + normal, notch, tail - normal, shoulder - normal)
    )


def _turn_arc(center, normal_start, normal_end, radius, side):
    dot = np.dot(normal_start, normal_end)
    cross = _cross_2d(normal_start, normal_end)
    angle_delta = math.atan2(cross, dot)
    if abs(cross) < _EPSILON and dot < 0:
        # An exact reversal has no turn direction in the source path.
        angle_delta = -side * math.pi

    angle_start = math.atan2(normal_start[1], normal_start[0])
    step_count = max(3, math.ceil(abs(angle_delta) / (math.pi / 6)))
    angles = np.linspace(angle_start, angle_start + angle_delta, step_count + 1)
    return center + radius * np.column_stack((np.cos(angles), np.sin(angles)))


def _offset_run(points, source_indices, offset_pixels):
    if len(points) < 2:
        return points.tolist(), source_indices.tolist()

    keep = np.r_[np.linalg.norm(np.diff(points, axis=0), axis=1) > _EPSILON, True]
    points = points[keep]
    source_indices = source_indices[keep]
    if len(points) < 2:
        return points.tolist(), source_indices.tolist()

    tangents = np.diff(points, axis=0)
    tangents /= np.linalg.norm(tangents, axis=1)[:, np.newaxis]
    side = 1.0 if offset_pixels > 0 else -1.0
    radius = abs(offset_pixels)
    normals = side * np.column_stack((-tangents[:, 1], tangents[:, 0]))
    output_points = [points[0] + radius * normals[0]]
    output_indices = [source_indices[0]]

    for i in range(1, len(points) - 1):
        tangent_previous, tangent_next = tangents[i - 1 : i + 1]
        normal_previous, normal_next = normals[i - 1 : i + 1]
        source_index = source_indices[i]

        if np.dot(tangent_previous, tangent_next) < _UTURN_DOT_THRESHOLD:
            arc = _turn_arc(points[i], normal_previous, normal_next, radius, side)
            output_points.extend(arc)
            output_indices.extend((source_index,) * len(arc))
            continue

        intersection = _miter_point(points[i], tangents[i - 1 : i + 1], offset_pixels)
        if intersection is not None:
            output_points.append(intersection)
            output_indices.append(source_index)
        else:
            # A bevel avoids long spikes at very sharp corners.
            output_points.extend(
                (
                    points[i] + radius * normal_previous,
                    points[i] + radius * normal_next,
                )
            )
            output_indices.extend((source_index, source_index))

    output_points.append(points[-1] + radius * normals[-1])
    output_indices.append(source_indices[-1])
    return output_points, output_indices


def offset_polyline(x_values, y_values, pixel_scale, offset_pixels):
    """Offset a polyline to its travel-relative side in display-pixel space."""
    pixel_points, origin, scale = _to_pixels(x_values, y_values, pixel_scale)
    output_points, source_indices = _offset_run(
        pixel_points, np.arange(len(pixel_points)), offset_pixels
    )
    output_points = np.asarray(output_points) * scale + origin
    return (
        output_points[:, 0],
        output_points[:, 1],
        np.asarray(source_indices, dtype=np.int32),
    )


def offset_points_by_segment(
    course_x,
    course_y,
    point_x,
    point_y,
    segment_indices,
    pixel_scale,
    offset_pixels,
):
    """Offset points using segment normals and corner miters."""
    point_x = np.asarray(point_x)
    point_y = np.asarray(point_y)
    scale = np.asarray(pixel_scale)
    origin = np.array((course_x[0], course_y[0]))
    course_points = (np.column_stack((course_x, course_y)) - origin) / scale
    point_pixels = (np.column_stack((point_x, point_y)) - origin) / scale
    deltas = np.diff(course_points, axis=0)
    lengths = np.linalg.norm(deltas, axis=1)
    valid_segments = np.flatnonzero(lengths > _EPSILON)
    if not len(valid_segments):
        return point_x.copy(), point_y.copy()

    segment_indices = np.clip(segment_indices, 0, len(deltas) - 1)
    valid_positions = np.minimum(
        np.searchsorted(valid_segments, segment_indices), len(valid_segments) - 1
    )
    tangents = deltas[valid_segments] / lengths[valid_segments, np.newaxis]
    selected = valid_segments[valid_positions]
    selected_tangents = tangents[valid_positions]
    normals = np.column_stack((-selected_tangents[:, 1], selected_tangents[:, 0]))
    output_points = point_pixels + offset_pixels * normals
    for i, (segment_index, position) in enumerate(zip(selected, valid_positions)):
        if (
            not position
            or np.linalg.norm(point_pixels[i] - course_points[segment_index]) > _EPSILON
        ):
            continue
        tangent_previous, tangent_next = tangents[position - 1 : position + 1]
        if np.dot(tangent_previous, tangent_next) < _UTURN_DOT_THRESHOLD:
            continue
        intersection = _miter_point(
            course_points[segment_index],
            tangents[position - 1 : position + 1],
            offset_pixels,
        )
        if intersection is not None:
            output_points[i] = intersection

    output = output_points * scale + origin
    return output[:, 0], output[:, 1]


def direction_arrow_polygons(
    x_values,
    y_values,
    pixel_scale,
    spacing_pixels,
    width_pixels,
):
    """Build closed travel-direction chevrons at fixed pixel intervals."""
    pixel_points, origin, scale = _to_pixels(x_values, y_values, pixel_scale)
    deltas = np.diff(pixel_points, axis=0)
    lengths = np.linalg.norm(deltas, axis=1)
    cumulative = np.cumsum(lengths)
    distances = np.arange(spacing_pixels / 2, cumulative[-1], spacing_pixels)
    segment_indices = np.searchsorted(cumulative, distances, side="right")
    segment_starts = np.r_[0, cumulative[:-1]][segment_indices]
    tangents = deltas[segment_indices] / lengths[segment_indices, np.newaxis]
    tips = (
        pixel_points[segment_indices]
        + (distances - segment_starts)[:, np.newaxis] * tangents
    )
    return [
        _direction_arrow_polygon(tip, tangent, width_pixels) * scale + origin
        for tip, tangent in zip(tips, tangents)
    ]
