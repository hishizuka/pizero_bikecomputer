"""Application data and tile preparation shared by the two Qt map pages."""

from dataclasses import dataclass, replace
import math

from modules.utils.map import get_zoom_delta_from_tile_size

from .state import MAX_LATITUDE, MapSnapshot, MapState, MapView
from .style import course_offset_pixels
from .content import MapHud, map_hud, navigation_zoom
from .follow import CourseFocus
from .policy import axis_range_changed, fallback_position, map_position, clamp_zoom
from .projection import unproject
from .tiles import LocalTileSource, download_tiles, layer_zoom, visible_tiles


@dataclass(frozen=True, slots=True)
class PreparedTileLayer:
    view: MapView
    settings: dict
    tiles: dict
    namespace: tuple


@dataclass(frozen=True, slots=True)
class PreparedMapFrame:
    snapshot: MapSnapshot
    tiles: dict
    settings: dict
    traffic_offset: float
    tile_namespace: tuple
    overlay: PreparedTileLayer | None = None
    hud: MapHud | None = None


class MapSession:
    def __init__(self, config):
        self.config = config
        tile_size = config.G_MAP_CONFIG[config.G_MAP]["tile_size"]
        self.state = MapState(
            MapView(
                config.G_DUMMY_POS_X,
                config.G_DUMMY_POS_Y,
                clamp_zoom(13 - get_zoom_delta_from_tile_size(tile_size)),
                256,
                256,
                tile_size=tile_size,
            )
        )
        self.source = None
        self._course_arrays = None
        self._overlay_source = None
        self._auto_zoom = (
            self.state.view.zoom + 2 - get_zoom_delta_from_tile_size(tile_size)
        )
        self._auto_zoom_back = None
        self.course_focus = CourseFocus()
        self.move_adjust_mode = False
        self._applied_view = None

    def sync(self):
        """Read already initialized application fields without copying each course."""
        logger = self.config.logger
        if logger is None:
            return
        course = logger.course
        self.state.track = self.config.map.track.snapshot
        arrays = (course.longitude, course.latitude, course.colored_altitude)
        if self._course_arrays is None or any(
            a is not b for a, b in zip(arrays, self._course_arrays)
        ):
            self.state.set_course(*arrays)
            self._course_arrays = arrays
        gps = logger.sensor.values["GPS"]
        lon, lat = map_position(self.config, gps)
        if not (-180 <= lon <= 180 and -MAX_LATITUDE <= lat <= MAX_LATITUDE):
            lon, lat = fallback_position(self.config)
        heading = self.config.map.heading(logger.sensor.values)
        if not math.isfinite(heading):
            heading = self.state.position.heading if self.state.position else 0.0
        self.state.update_position(lon, lat, heading, gps["mode"] == 3)
        view = self.state.view
        lon0, lon1, lat0, lat1 = view.bounds
        center = self.course_focus.center(
            course,
            lon,
            lat,
            lon1 - lon0,
            lat1 - lat0,
            self.state.follow,
            gps.get("timestamp"),
        )
        if self.state.follow:
            self.state.view = replace(view, longitude=center[0], latitude=center[1])

    def display_view(self):
        """Hold each automatic camera axis until the legacy pixel threshold is met."""
        view, previous = self.state.view, self._applied_view
        if (
            previous is None
            or not self.state.follow
            or (view.zoom, view.tile_size, view.pixel_ratio)
            != (previous.zoom, previous.tile_size, previous.pixel_ratio)
        ):
            self._applied_view = view
            return view
        bounds = list(view.projected_bounds)
        old_bounds = previous.projected_bounds
        for axis, size in ((0, view.width), (2, view.height)):
            start, end = bounds[axis : axis + 2]
            old_start, old_end = old_bounds[axis : axis + 2]
            old_size = previous.width if axis == 0 else previous.height
            if not axis_range_changed(
                start,
                end,
                size / view.pixel_ratio,
                (old_start, old_end, old_size / previous.pixel_ratio),
            ):
                bounds[axis : axis + 2] = old_bounds[axis : axis + 2]
        if tuple(bounds) == old_bounds and (view.width, view.height) == (
            previous.width,
            previous.height,
        ):
            return previous
        longitude, latitude = unproject(
            (bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2
        )
        self._applied_view = replace(
            view,
            longitude=longitude,
            latitude=latitude,
            applied_projected_bounds=tuple(bounds),
        )
        return self._applied_view

    def _tile_source(self, name, settings, source, overlay=False):
        key = (name, settings["ext"], settings["use_mbtiles"], settings["tile_size"])
        if overlay:
            key += tuple(
                settings.get(k) for k in ("basetime", "validtime", "subdomain")
            )
        key += (self.config.map.tiles.revision,)
        if source is None or key != source.namespace:
            source = LocalTileSource(
                "maptile",
                *key[:3],
                tile_size=key[3],
                repository=self.config.map.tiles,
                overlay=overlay,
            )
            source.settings = settings
            source.namespace = key
        return source

    def overlay_frame(self, view):
        overlays = self.config.map.overlays
        settings_map, name = overlays.source()
        if settings_map is None or not overlays.enabled(overlays.kind):
            return None
        settings = dict(settings_map[name])
        self._overlay_source = self._tile_source(
            name, settings, self._overlay_source, overlay=True
        )
        keys = visible_tiles(view, settings)
        tiles = {
            key: self._overlay_source.cache[key]
            for key in keys
            if key in self._overlay_source.cache
        }
        return PreparedTileLayer(view, settings, tiles, self._overlay_source.namespace)

    def cached_frame(self):
        """Snapshot current state and cached tiles without waiting for I/O."""
        self.sync()
        name = self.config.G_MAP
        settings = dict(self.config.G_MAP_CONFIG[name])
        self.source = self._tile_source(name, settings, self.source)
        tile_size = settings["tile_size"]
        if self.state.view.tile_size != tile_size:
            view = self.state.view
            self.state.view = replace(
                view, zoom=layer_zoom(view, tile_size), tile_size=tile_size
            )
        snapshot = replace(self.state.snapshot(), view=self.display_view())
        keys = visible_tiles(snapshot.view, settings)
        tiles = {
            key: self.source.cache[key] for key in keys if key in self.source.cache
        }
        offset = course_offset_pixels(
            snapshot.view.zoom, self.config.G_COURSE_TRAFFIC_SIDE
        )
        overlay = self.overlay_frame(snapshot.view)
        hud = map_hud(
            self.config,
            snapshot.view,
            offset,
            0 if self.state.follow else 7.5 if self.move_adjust_mode else 15,
        )
        return PreparedMapFrame(
            snapshot, tiles, settings, offset, self.source.namespace, overlay, hud
        )

    async def prepare(self):
        if self.config.logger is not None:
            track = self.state.track
            if self.config.map.track.redraw_reasons(
                self.config.logger,
                track.history if track else None,
                track.tail if track else None,
            ):
                await self.config.map.track.update(self.config.logger)
        await self.config.map.overlays.prepare()
        frame = self.cached_frame()
        zoom = self.state.view.zoom
        target = clamp_zoom(self._auto_zoom)
        new_zoom, self._auto_zoom_back = navigation_zoom(
            frame.hud.instruction_distance, zoom, target, self._auto_zoom_back
        )
        if new_zoom != zoom:
            self.state.set_zoom(new_zoom)
            frame = self.cached_frame()
        keys = visible_tiles(frame.snapshot.view, frame.settings)
        source = self.source
        tiles = await self.prepare_tiles(
            source, frame.snapshot.view, frame.settings, keys
        )
        overlay = frame.overlay
        if overlay is not None:
            overlay_source = self._overlay_source
            overlay_keys = visible_tiles(overlay.view, overlay.settings)
            overlay = replace(
                overlay,
                tiles=await self.prepare_tiles(
                    overlay_source, overlay.view, overlay.settings, overlay_keys
                ),
            )
        return replace(frame, tiles=tiles, overlay=overlay)

    async def prepare_tiles(self, source, view, settings, keys):
        if not keys:
            return {}
        download = download_tiles(view, settings)
        request_key = (keys[0][0], tuple(download))
        complete = all(key in source.cache for key in keys)
        if source.request_key != request_key or not complete:
            await self.config.map.tiles.request(
                {source.name: settings},
                source.name,
                keys[0][0],
                download,
                additional_download=True,
            )
            source.request_key = request_key
        return (
            {key: source.cache[key] for key in keys}
            if complete
            else await source.load(keys)
        )
