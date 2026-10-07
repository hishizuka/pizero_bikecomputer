"""GUI-independent map state; snapshots contain no Qt or GPU objects."""

from dataclasses import dataclass, replace
import math

import numpy as np

from modules.utils.map import MAX_MERCATOR_LATITUDE

from .projection import WORLD_WIDTH, project, unproject

MAX_LATITUDE = MAX_MERCATOR_LATITUDE


def _check_position(longitude, latitude):
    if not (-180 <= longitude <= 180 and -MAX_LATITUDE <= latitude <= MAX_LATITUDE):
        raise ValueError("Position must be within the Web Mercator map")


@dataclass(frozen=True, slots=True)
class MapView:
    longitude: float
    latitude: float
    zoom: int
    width: int
    height: int
    pixel_ratio: float = 1.0
    tile_size: int = 256
    applied_projected_bounds: tuple | None = None

    def __post_init__(self):
        _check_position(self.longitude, self.latitude)
        if not 0 <= self.zoom <= 22 or self.width <= 0 or self.height <= 0:
            raise ValueError("Map view requires zoom 0..22 and a positive size")
        if not math.isfinite(self.pixel_ratio) or self.pixel_ratio <= 0:
            raise ValueError("Map view requires a finite positive pixel ratio")
        if self.tile_size <= 0:
            raise ValueError("Map tile size must be positive")

    @property
    def projected_bounds(self):
        """Exact viewport in Mercator meters, including space outside polar tiles."""
        if self.applied_projected_bounds is not None:
            return self.applied_projected_bounds
        x, y = project(self.longitude, self.latitude)
        scale = WORLD_WIDTH / (2**self.zoom * self.tile_size * self.pixel_ratio)
        half_width, half_height = self.width * scale / 2, self.height * scale / 2
        return (
            x - half_width,
            x + half_width,
            y - half_height,
            y + half_height,
        )

    @property
    def bounds(self):
        """Geographic bounds for tile selection; longitude stays unwrapped."""
        x0, x1, y0, y1 = self.projected_bounds
        lon0, lat0 = unproject(x0, y0)
        lon1, lat1 = unproject(x1, y1)
        return lon0, lon1, lat0, lat1


@dataclass(frozen=True, slots=True)
class MapPosition:
    longitude: float
    latitude: float
    heading: float = 0.0
    fix: bool = True

    def __post_init__(self):
        _check_position(self.longitude, self.latitude)
        if not math.isfinite(self.heading):
            raise ValueError("Heading must be finite")


@dataclass(frozen=True, slots=True, eq=False)
class MapPolyline:
    longitude: np.ndarray
    latitude: np.ndarray

    def __post_init__(self):
        lon = np.array(self.longitude, dtype=np.float64, copy=True)
        lat = np.array(self.latitude, dtype=np.float64, copy=True)
        if lon.ndim != 1 or lat.shape != lon.shape:
            raise ValueError("Polyline coordinates must have matching lengths")
        lon.flags.writeable = lat.flags.writeable = False
        object.__setattr__(self, "longitude", lon)
        object.__setattr__(self, "latitude", lat)


@dataclass(frozen=True, slots=True, eq=False)
class MapCourse(MapPolyline):
    colors: np.ndarray

    def __post_init__(self):
        MapPolyline.__post_init__(self)
        colors = np.array(self.colors, dtype=np.float64, copy=True)
        if not colors.size:
            colors = colors.reshape(0, 3)
        if colors.shape not in ((len(self.longitude), 3), (len(self.longitude), 4)):
            raise ValueError("Course requires an RGB or RGBA color per point")
        colors.flags.writeable = False
        object.__setattr__(self, "colors", colors)


@dataclass(frozen=True, slots=True, eq=False)
class MapTrack:
    history: MapPolyline
    tail: MapPolyline


@dataclass(frozen=True, slots=True)
class MapSnapshot:
    view: MapView
    position: MapPosition | None
    course: MapCourse | None
    track: MapTrack | None = None


@dataclass
class MapState:
    view: MapView
    position: MapPosition | None = None
    course: MapCourse | None = None
    follow: bool = True
    track: MapTrack | None = None

    def update_position(self, longitude, latitude, heading=0.0, fix=True):
        self.position = MapPosition(longitude, latitude, heading, fix)
        if self.follow:
            self.view = replace(self.view, longitude=longitude, latitude=latitude)

    def set_follow(self, follow):
        self.follow = follow
        if follow and self.position is not None:
            self.view = replace(
                self.view,
                longitude=self.position.longitude,
                latitude=self.position.latitude,
            )

    def pan(self, dx, dy):
        """Move the map by a drag in screen pixels and suspend GPS following."""
        x0, x1, y0, y1 = self.view.projected_bounds
        lon, lat = unproject(
            (x0 + x1) / 2 - dx * (x1 - x0) / self.view.width,
            (y0 + y1) / 2 + dy * (y1 - y0) / self.view.height,
        )
        self.view = replace(
            self.view,
            longitude=(lon + 180) % 360 - 180,
            latitude=lat,
            applied_projected_bounds=None,
        )
        self.follow = False

    def set_zoom(self, zoom):
        self.view = replace(self.view, zoom=zoom)

    def resize(self, width, height, pixel_ratio=1.0):
        self.view = replace(
            self.view, width=width, height=height, pixel_ratio=pixel_ratio
        )

    def set_course(self, longitude, latitude, colors):
        course = MapCourse(longitude, latitude, colors)
        self.course = course if len(course.longitude) else None

    def snapshot(self):
        return MapSnapshot(self.view, self.position, self.course, self.track)
