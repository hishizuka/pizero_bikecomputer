import numpy as np

from modules._qt_qtwidgets import pg
from modules.map.style import POSITION_MARKER_SIZE, MAP_LAYER_ORDER
from modules.map.follow import CourseFocus
from modules.utils.geo import calc_y_mod, get_mod_lat
from modules.map.overlays import MapOverlays
from modules.map.policy import axis_range_changed, map_position, tile_zoom


class MapStateMixin:
    # map position
    map_area = {
        "w": np.nan,
        "h": np.nan,
    }  # width(longitude diff) and height(latitude diff)
    move_pos = {"x": 0, "y": 0}
    map_pos = {"x": np.nan, "y": np.nan}  # center

    # current point
    location = []

    # misc
    arrow_direction_num = 16
    # calculate these ony once
    arrow_direction_angle_unit = 360 / arrow_direction_num
    arrow_direction_angle_unit_half = arrow_direction_angle_unit / 2
    y_mod = 1.22  # 31/25 at Tokyo(N35)
    view_range_update_epsilon_px = 20

    def _setup_map_state_items(self):
        self.map_pos["x"] = self.config.G_DUMMY_POS_X
        self.map_pos["y"] = self.config.G_DUMMY_POS_Y
        self.course_focus = CourseFocus()
        self._last_applied_x_range = None
        self._last_applied_y_range = None
        self._last_applied_x_bounds = None
        self._last_applied_y_bounds = None

        self.point["size"] = POSITION_MARKER_SIZE
        self._init_direction_arrows()
        self._init_center_point()

    def _get_map_heading_value(self):
        return self.config.map.heading(self.sensor.values)

    def _get_viewport_px_size(self):
        view_box = self.plot.getViewBox()
        view_width = float(view_box.width())
        view_height = float(view_box.height())
        if view_width <= 0:
            view_width = float(self.plot.width())
        if view_height <= 0:
            view_height = float(self.plot.height())
        return max(1.0, view_width), max(1.0, view_height)

    def _should_apply_axis_range(self, start, end, view_px, previous_state):
        return axis_range_changed(
            start, end, view_px, previous_state, self.view_range_update_epsilon_px
        )

    def _init_direction_arrows(self):
        self.direction_arrows = []
        array_symbol_base = np.array(
            [
                [-0.45, -0.5],
                [0, -0.3],
                [0.45, -0.5],
                [0, 0.5],
                [-0.45, -0.5],
            ]
        )
        self.direction_arrows.append(
            pg.arrayToQPath(
                array_symbol_base[:, 0], -array_symbol_base[:, 1], connect="all"
            )
        )
        self.current_point.setSymbol(self.direction_arrows[0])
        for i in range(1, self.arrow_direction_num):
            rad = np.deg2rad(i * 360 / self.arrow_direction_num)
            cos_rad = np.cos(rad)
            sin_rad = np.sin(rad)
            rot = np.array([[cos_rad, sin_rad], [-sin_rad, cos_rad]])
            array_symbol_conv = np.dot(rot, array_symbol_base.T).T
            self.direction_arrows.append(
                pg.arrayToQPath(
                    array_symbol_conv[:, 0], -array_symbol_conv[:, 1], connect="all"
                )
            )

    def _init_center_point(self):
        self.center_point = pg.ScatterPlotItem(pxMode=True, symbol="+")
        self.center_point.setZValue(MAP_LAYER_ORDER["center"])
        self.center_point_data = {
            "pos": [np.nan, np.nan],
            "size": 15,
            "pen": {"color": (0, 0, 0), "width": 2},
        }
        self.center_point_location = []
        self.plot.addItem(self.center_point)

    @staticmethod
    def _normalize_display_value(value):
        return None if np.isnan(value) else value

    def _get_overlay_display_state(self):
        overlays = self.config.map.overlays
        maps, name = overlays.source()
        settings = maps[name] if overlays.has_times else {}
        return (
            name,
            MapOverlays.refresh_time(overlays.kind, settings) if settings else None,
            settings.get("basetime"),
            settings.get("validtime"),
            settings.get("subdomain"),
        )

    def _get_active_map_names(self):
        """Return list of currently active map names (base + overlays)."""
        _, name = self.config.map.overlays.source()
        return [self.config.G_MAP] + ([name] if name is not None else [])

    def _cleanup_cached_tiles(self):
        """Remove cache entries for inactive maps."""
        active = set(self._get_active_map_names())
        for key in list(self._cached_tiles.keys()):
            if key not in active:
                del self._cached_tiles[key]
        self._cleanup_tile_runtime_cache(active)

    def _get_zoom_for_map(self, map_name, map_config):
        return tile_zoom(
            self.zoomlevel,
            self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"],
            map_config[map_name]["tile_size"],
        )

    def _has_pending_downloads(self):
        """Check if any tiles in current view are downloading for active maps."""
        x_start, x_end, y_start, y_end = self._get_view_bounds()
        if np.any(np.isnan([x_start, x_end, y_start, y_end])):
            return False

        p0 = {"x": min(x_start, x_end), "y": min(y_start, y_end)}
        p1 = {"x": max(x_start, x_end), "y": max(y_start, y_end)}

        for map_name in self._get_active_map_names():
            if self._has_pending_downloads_for_map(map_name, p0, p1):
                return True
        return False

    def _has_pending_downloads_for_map(self, map_name, p0, p1):
        """Check and cache tiles for a specific map."""
        map_config = (
            self.config.G_MAP_CONFIG
            if map_name == self.config.G_MAP
            else self.config.map.overlays.source()[0]
        )

        map_settings = map_config[map_name]
        z = self._get_zoom_for_map(map_name, map_config)
        tile_size = map_settings["tile_size"]
        draw_params = self.init_draw_map(map_config, map_name, z, p0, p1, tile_size)
        if draw_params is None:
            return False
        z_draw = draw_params[0]
        tiles = self._get_tiles_for_view(map_name, z, draw_params)

        return self.config.map.tiles.has_pending(map_settings, map_name, z_draw, tiles)

    def _build_display_key(self):
        gps_values = self.gps_values
        norm = self._normalize_display_value

        (
            overlay_map,
            overlay_time_key,
            overlay_basetime,
            overlay_validtime,
            overlay_subdomain,
        ) = self._get_overlay_display_state()
        display_key = (
            norm(gps_values["lon"]),
            norm(gps_values["lat"]),
            norm(self._get_map_heading_value()),
            norm(gps_values["mode"]),
            norm(self.map_pos["x"]),
            norm(self.map_pos["y"]),
            self.lock_status,
            self.move_adjust_mode,
            self.zoomlevel,
            self.config.G_COURSE_TRAFFIC_SIDE,
            self.overlay_index,
            self.config.G_MAP,
            overlay_map,
            overlay_time_key,
            overlay_basetime,
            overlay_validtime,
            overlay_subdomain,
            self.plot.width(),
            self.plot.height(),
            self.course.index.value,
            self.course.index.on_course_status,
            (
                gps_values.get("timestamp")
                if self.course_focus.active and not self.course.index.on_course_status
                else None
            ),
            self.course.weather_revision,
            self.course_points.is_set,
        )
        return display_key, overlay_map

    def _get_redraw_reasons(self, overlay_map):
        main_drawn = self.drawn_tile.get(self.config.G_MAP, {}).get(self.zoomlevel, {})
        reasons = []

        if not self.course_loaded:
            reasons.append("course_not_loaded")
        if self.move_pos["x"] != 0:
            reasons.append("move_x")
        if self.move_pos["y"] != 0:
            reasons.append("move_y")
        reasons.extend(
            self.track.redraw_reasons(
                self.logger, self._track_history, self._track_tail
            )
        )
        if self.pre_zoomlevel.get(self.config.G_MAP) != self.zoomlevel:
            reasons.append("zoom_changed")
        if not main_drawn:
            reasons.append("main_tile_missing")
        if self._has_tile_batch_pending():
            reasons.append("tile_batch_pending")
        if self._has_pending_downloads():
            reasons.append("pending_downloads")
        if overlay_map and not self.drawn_tile.get(overlay_map):
            reasons.append("overlay_tile_missing")

        return reasons

    def _clear_display_buffers(self):
        self.location.clear()
        self.center_point_location.clear()

    def _update_point_state(self):
        self.point["pos"] = list(map_position(self.config, self.gps_values))

        self.y_mod = calc_y_mod(self.point["pos"][1])
        if self.gps_values["mode"] == 3:
            self.point["brush"] = self.point_color["fix"]
        else:
            self.point["brush"] = self.point_color["lost"]

        if self.lock_status:
            self.map_pos["x"] = self.point["pos"][0]
            self.map_pos["y"] = self.point["pos"][1]

    def _update_map_area_and_move(self):
        self.map_area["w"], self.map_area["h"] = self.get_geo_area(
            self.map_pos["x"],
            self.map_pos["y"],
        )
        if self.lock_status:
            self.map_pos["x"], self.map_pos["y"] = self.course_focus.center(
                self.course,
                self.map_pos["x"],
                self.map_pos["y"],
                self.map_area["w"],
                self.map_area["h"],
                True,
                self.gps_values.get("timestamp"),
            )
        else:
            self.course_focus.reset()
            self.map_pos["x"] += (
                np.sign(self.move_pos["x"])
                * self.map_area["w"]
                / (2 * self.move_factor)
            )
            self.map_pos["y"] += (
                np.sign(self.move_pos["y"])
                * self.map_area["h"]
                / (2 * self.move_factor)
            )
        self.move_pos["x"] = self.move_pos["y"] = 0

        self.map_area["w"], self.map_area["h"] = self.get_geo_area(
            self.map_pos["x"],
            self.map_pos["y"],
        )

    def _update_current_and_center_items(self):
        self.point["pos"][1] *= self.y_mod
        self.location.append(self.point)

        heading_value = self._get_map_heading_value()
        if np.isfinite(heading_value):
            self.current_point.setSymbol(
                self.direction_arrows[self.get_arrow_angle_index(heading_value)]
            )
        self.current_point.setData(self.location)

        if not self.lock_status:
            self.center_point_data["size"] = 7.5 if self.move_adjust_mode else 15
            self.center_point_data["pos"][0] = self.map_pos["x"]
            self.center_point_data["pos"][1] = get_mod_lat(self.map_pos["y"])
            self.center_point_location.append(self.center_point_data)
            self.center_point.setData(self.center_point_location)
        else:
            self.center_point.setData([])

    def _get_view_bounds(self):
        x_start = self.map_pos["x"] - self.map_area["w"] / 2
        x_end = x_start + self.map_area["w"]
        y_start = self.map_pos["y"] - self.map_area["h"] / 2
        y_end = y_start + self.map_area["h"]
        return x_start, x_end, y_start, y_end

    def _apply_view_ranges(self, x_start, x_end, y_start, y_end):
        view_width, view_height = self._get_viewport_px_size()
        force_apply = self._last_display_key is None

        if not np.isnan(x_start) and not np.isnan(x_end):
            if force_apply or self._should_apply_axis_range(
                x_start, x_end, view_width, self._last_applied_x_range
            ):
                self.plot.setXRange(x_start, x_end, padding=0)
                self._last_applied_x_range = (x_start, x_end, view_width)
                self._last_applied_x_bounds = (x_start, x_end)

        if not np.isnan(y_start) and not np.isnan(y_end):
            y_start_mod = get_mod_lat(y_start)
            y_end_mod = get_mod_lat(y_end)
            if force_apply or self._should_apply_axis_range(
                y_start_mod, y_end_mod, view_height, self._last_applied_y_range
            ):
                self.plot.setYRange(y_start_mod, y_end_mod, padding=0)
                self._last_applied_y_range = (y_start_mod, y_end_mod, view_height)
                self._last_applied_y_bounds = (y_start, y_end)

        # Return the effective bounds currently shown on screen.
        # When range updates are skipped by px-threshold, downstream drawing should
        # reuse the last applied bounds to keep tile/HUD coordinates consistent.
        return (
            *(self._last_applied_x_bounds or (x_start, x_end)),
            *(self._last_applied_y_bounds or (y_start, y_end)),
        )
