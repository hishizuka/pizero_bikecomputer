"""Web Mercator (EPSG:3857) coordinates in meters, east and north positive."""

import math

import numpy as np

from modules.utils.map import MAX_MERCATOR_LATITUDE

EARTH_RADIUS = 6378137.0
WORLD_WIDTH = 2 * math.pi * EARTH_RADIUS


def project(longitude, latitude):
    if np.isscalar(longitude) and np.isscalar(latitude):
        latitude = min(max(latitude, -MAX_MERCATOR_LATITUDE), MAX_MERCATOR_LATITUDE)
        return (
            longitude * (WORLD_WIDTH / 360),
            EARTH_RADIUS * math.asinh(math.tan(math.radians(latitude))),
        )
    latitude = np.clip(latitude, -MAX_MERCATOR_LATITUDE, MAX_MERCATOR_LATITUDE)
    return (
        np.asarray(longitude) * (WORLD_WIDTH / 360),
        EARTH_RADIUS * np.arcsinh(np.tan(np.radians(latitude))),
    )


def unproject(x, y):
    if np.isscalar(x) and np.isscalar(y):
        y = min(max(y, -WORLD_WIDTH / 2), WORLD_WIDTH / 2)
        return x * (360 / WORLD_WIDTH), math.degrees(
            math.atan(math.sinh(y / EARTH_RADIUS))
        )
    y = np.clip(y, -WORLD_WIDTH / 2, WORLD_WIDTH / 2)
    return (
        np.asarray(x) * (360 / WORLD_WIDTH),
        np.degrees(np.arctan(np.sinh(y / EARTH_RADIUS))),
    )
