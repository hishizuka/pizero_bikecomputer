import numpy as np

TOTAL_ASCENT_THRESHOLD = 2  # [m]
COURSE_ALTITUDE_RESAMPLE_DISTANCE = 20  # [m]
COURSE_ALTITUDE_GAUSSIAN_SIGMA = 75  # [m]
_COURSE_ALTITUDE_GAUSSIAN_TRUNCATE = 4


def update_altitude_reference(value, previous, threshold=TOTAL_ASCENT_THRESHOLD):
    if np.isnan(value):
        return previous, 0.0
    if np.isnan(previous):
        return value, 0.0

    difference = value - previous
    if abs(difference) > threshold:
        return value, difference
    return previous, 0.0


def calculate_thresholded_ascent(altitude, threshold=TOTAL_ASCENT_THRESHOLD):
    if not len(altitude):
        return np.nan

    previous = np.nan
    total_ascent = 0.0
    for value in altitude:
        previous, difference = update_altitude_reference(
            value,
            previous,
            threshold,
        )
        if difference > 0:
            total_ascent += difference
    return total_ascent


def calculate_course_total_ascent(
    distance,
    altitude,
    spacing=COURSE_ALTITUDE_RESAMPLE_DISTANCE,
    sigma=COURSE_ALTITUDE_GAUSSIAN_SIGMA,
):
    if not len(distance) or len(distance) != len(altitude):
        return np.nan

    distance = np.asarray(distance, dtype=float)
    altitude = np.asarray(altitude, dtype=float)
    valid = np.isfinite(distance) & np.isfinite(altitude)
    distance = distance[valid]
    altitude = altitude[valid]
    if not len(distance):
        return np.nan

    distance, unique_index = np.unique(distance, return_index=True)
    altitude = altitude[unique_index]
    if len(distance) < 2:
        return 0.0

    grid = np.arange(distance[0], distance[-1], spacing)
    grid = np.append(grid, distance[-1])
    profile = np.interp(grid, distance, altitude)

    radius = int(_COURSE_ALTITUDE_GAUSSIAN_TRUNCATE * sigma / spacing + 0.5)
    offsets = np.arange(-radius, radius + 1) * spacing
    kernel = np.exp(-0.5 * (offsets / sigma) ** 2)
    kernel /= np.sum(kernel)
    profile = np.convolve(
        np.pad(profile, radius, mode="edge"),
        kernel,
        mode="valid",
    )

    altitude_difference = np.diff(profile)
    return float(np.sum(altitude_difference[altitude_difference > 0]))
