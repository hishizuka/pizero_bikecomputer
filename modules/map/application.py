"""Application-wide map settings, page notifications and tile access, without Qt."""

import math

from .repository import TileRepository
from .track import TrackStore
from .content import CourseMarkerLayout, Navigation
from .overlays import MapOverlays
from modules.helper.maptile import get_wind_color


class MapApplication:
    def __init__(self, config):
        self.config = config
        self.pages = []
        self.tiles = TileRepository(config)
        self.track = TrackStore()
        self.navigation = Navigation()
        self.marker_layout = CourseMarkerLayout()
        self.overlays = MapOverlays(config)
        self.use_magnetic_heading = config.G_DEBUG
        self.route_searching = False
        self._wind_key = None
        self._wind_markers = ()

    def course_wind_markers(self, course):
        key = (id(course), course.weather_revision)
        if key != self._wind_key:
            self._wind_markers = tuple(
                (
                    index,
                    float(angle),
                    tuple(int(value) for value in get_wind_color(speed)),
                )
                for index, angle, speed in zip(
                    course.wind_course_indices, course.wind_direction, course.wind_speed
                )
                if math.isfinite(angle) and math.isfinite(speed)
            )
            self._wind_key = key
        return self._wind_markers

    def can_search_route(self, following):
        return (
            self.config.G_GOOGLE_ROUTES_API["HAVE_API_TOKEN"]
            and not following
            and not self.route_searching
        )

    async def search_route(self, start, destination):
        if not self.can_search_route(False) or not all(
            math.isfinite(value) for value in (*start, *destination)
        ):
            return
        self.route_searching = True
        self.notify("refresh_map")
        try:
            self.config.logger.reset_course(delete_course_file=True, replace=False)
            await self.config.logger.course.search_route(*start, *destination)
        finally:
            self.route_searching = False
            self.config.gui.init_course()

    def register(self, page):
        self.pages.append(page)

    def notify(self, method, *args):
        """Notify every map that implements the requested optional capability."""
        if method in ("reset_course", "init_course"):
            self.navigation.clear()
            self._wind_key = None
        elif method == "remove_overlay":
            self.overlays.index = 0
        for page in self.pages:
            handler = getattr(page, method, None)
            if callable(handler):
                handler(*args)
        if method == "remove_overlay":
            self.notify("refresh_map")

    def reset_map(self):
        self.tiles.invalidate()
        self.notify("reset_map")
        self.notify("refresh_map")

    def reset_track(self):
        self.track.reset()
        self.notify("reset_track")

    def set_external_instruction(self, name, distance):
        self.navigation.set_external(name, distance)
        self.notify("refresh_map")

    def clear_external_instruction(self):
        self.navigation.clear()
        self.notify("refresh_map")

    def change_map_overlays(self):
        self.overlays.cycle()
        self.notify("reset_map")
        self.notify("refresh_map")

    async def update_overlay_time(self, forward):
        await self.overlays.shift_time(forward)
        self.notify("refresh_map")

    def set_heading_source(self, use_magnetic):
        self.use_magnetic_heading = bool(use_magnetic)
        self.notify("refresh_map")

    def heading(self, values):
        if self.use_magnetic_heading:
            magnetic = values["I2C"]["heading_magnetic_deg"]
            if magnetic is not None and math.isfinite(magnetic):
                return magnetic
        return values["GPS"]["heading_gps_deg"]
