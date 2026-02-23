from datetime import timedelta

import numpy as np

from modules._qt_qtwidgets import pg
from modules.utils.geo import calc_y_mod, get_mod_lat, get_width_distance
from modules.utils.map import get_maptile_filename


class MapStateMixin:
    _OVERLAY_ATTRS = {
        "WIND": ("G_WIND_OVERLAY_MAP_CONFIG", "G_WIND_OVERLAY_MAP"),
        "RAIN": ("G_RAIN_OVERLAY_MAP_CONFIG", "G_RAIN_OVERLAY_MAP"),
        "HEATMAP": ("G_HEATMAP_OVERLAY_MAP_CONFIG", "G_HEATMAP_OVERLAY_MAP"),
    }

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
    _overlay_refresh_time_cache = None

    @staticmethod
    def _get_interval_aligned_time(map_settings):
        current_time = map_settings["current_time_func"]()
        delta_minutes = current_time.minute % map_settings["time_interval"]
        if delta_minutes > map_settings["time_interval"] / 2:
            delta_minutes -= map_settings["time_interval"]
        current_time += timedelta(minutes=-delta_minutes)
        return current_time.replace(second=0, microsecond=0)

    @staticmethod
    def _get_interval_cutoff_time(map_settings):
        current_time = map_settings["current_time_func"]()
        delta_minutes = current_time.minute % map_settings["time_interval"]
        delta_seconds = delta_minutes * 60 + current_time.second
        delta_seconds_cutoff = map_settings["update_minutes"] * 60 + 15
        if delta_seconds < delta_seconds_cutoff:
            delta_minutes += map_settings["time_interval"]
        current_time += timedelta(minutes=-delta_minutes)
        return current_time.replace(second=0, microsecond=0)

    def _get_overlay_refresh_time_key(self, overlay_type, map_settings):
        # refresh_time_mode is shared by any time-series overlay.
        # fallback keeps existing behavior when mode is not set in map config.
        refresh_mode = map_settings.get("refresh_time_mode")
        if refresh_mode is None:
            refresh_mode = "cutoff" if overlay_type == "RAIN" else "aligned"

        if refresh_mode == "cutoff":
            return self._get_interval_cutoff_time(map_settings)
        return self._get_interval_aligned_time(map_settings)

    def _cache_overlay_refresh_time_key(self, overlay_type, overlay_map, time_key):
        if not isinstance(self._overlay_refresh_time_cache, dict):
            self._overlay_refresh_time_cache = {}
        self._overlay_refresh_time_cache[overlay_type] = {
            "map_name": overlay_map,
            "time_key": time_key,
        }

    def _get_overlay_map_config_and_name(self, overlay_type):
        attr_names = self._OVERLAY_ATTRS.get(overlay_type)
        if attr_names is None:
            return None, None
        config_name_attr, map_name_attr = attr_names
        return (
            getattr(self.config, config_name_attr),
            getattr(self.config, map_name_attr),
        )

    def _setup_map_state_items(self):
        self.map_pos["x"] = self.config.G_DUMMY_POS_X
        self.map_pos["y"] = self.config.G_DUMMY_POS_Y
        self._overlay_refresh_time_cache = {}
        self._last_applied_x_range = None
        self._last_applied_y_range = None
        self._last_applied_x_bounds = None
        self._last_applied_y_bounds = None

        self.point["size"] = 29
        self._init_direction_arrows()
        self._init_center_point()

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
        if previous_state is None:
            return True

        prev_start, prev_end, prev_view_px = previous_state
        if abs(prev_view_px - view_px) >= 0.5:
            return True

        span = abs(end - start)
        prev_span = abs(prev_end - prev_start)
        if span <= 0 or prev_span <= 0:
            return True

        data_per_px = max(span, prev_span) / view_px
        if data_per_px <= 0:
            return True

        move_px = max(abs(start - prev_start), abs(end - prev_end)) / data_per_px
        span_delta_px = abs(span - prev_span) / data_per_px
        return max(move_px, span_delta_px) >= self.view_range_update_epsilon_px

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
        self.center_point.setZValue(50)
        self.center_point_data = {
            "pos": [np.nan, np.nan],
            "size": 15,
            "pen": {"color": (0, 0, 0), "width": 2},
        }
        self.center_point_location = []
        self.plot.addItem(self.center_point)

    @staticmethod
    def _normalize_display_value(value):
        try:
            if np.isnan(value):
                return None
        except Exception:
            pass
        return value

    def _get_overlay_display_state(self):
        overlay_type = self.overlay_order[self.overlay_index]
        overlay_map = None
        overlay_time_key = None
        overlay_basetime = None
        overlay_validtime = None
        overlay_subdomain = None
        map_settings = None

        _, overlay_map = self._get_overlay_map_config_and_name(overlay_type)
        if overlay_type in ("RAIN", "WIND"):
            map_config, _ = self._get_overlay_map_config_and_name(overlay_type)
            if map_config:
                map_settings = map_config.get(overlay_map)
            if map_settings:
                overlay_time_key = self._get_overlay_refresh_time_key(
                    overlay_type, map_settings
                )

        if map_settings:
            overlay_basetime = map_settings.get("basetime")
            overlay_validtime = map_settings.get("validtime")
            overlay_subdomain = map_settings.get("subdomain")
            if overlay_type in ("RAIN", "WIND"):
                self._cache_overlay_refresh_time_key(
                    overlay_type, overlay_map, overlay_time_key
                )

        return (
            overlay_map,
            overlay_time_key,
            overlay_basetime,
            overlay_validtime,
            overlay_subdomain,
        )

    def _get_course_display_state(self):
        course_index_value = None
        course_on_status = None
        try:
            course_index_value = self.course.index.value
            course_on_status = self.course.index.on_course_status
        except Exception:
            pass
        return course_index_value, course_on_status

    def _get_active_map_names(self):
        """Return list of currently active map names (base + overlays)."""
        names = [self.config.G_MAP]
        overlay_type = self.overlay_order[self.overlay_index]
        _, overlay_map = self._get_overlay_map_config_and_name(overlay_type)
        if overlay_map:
            names.append(overlay_map)
        return names

    def _cleanup_cached_tiles(self):
        """Remove cache entries for inactive maps."""
        active = set(self._get_active_map_names())
        for key in list(self._cached_tiles.keys()):
            if key not in active:
                del self._cached_tiles[key]
        if hasattr(self, "_cleanup_tile_runtime_cache"):
            self._cleanup_tile_runtime_cache(active)

    def _get_map_config_for_name(self, map_name):
        """Return the map config dict for a given map_name."""
        map_configs = {self.config.G_MAP: self.config.G_MAP_CONFIG}
        for overlay_type in self._OVERLAY_ATTRS:
            map_config, overlay_map = self._get_overlay_map_config_and_name(
                overlay_type
            )
            if overlay_map:
                map_configs[overlay_map] = map_config
        return map_configs.get(map_name)

    def _get_zoom_for_map(self, map_name, map_config):
        """Return the zoom level to use for a given map."""
        if map_name == self.config.G_MAP:
            return self.zoomlevel
        # For overlay maps, adjust zoom based on tile size difference
        base_tile_size = self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"]
        overlay_tile_size = map_config[map_name]["tile_size"]
        return self.zoomlevel + int(base_tile_size / overlay_tile_size) - 1

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
        map_config = self._get_map_config_for_name(map_name)
        if map_config is None or map_name not in map_config:
            return False

        map_settings = map_config[map_name]
        z = self._get_zoom_for_map(map_name, map_config)
        tile_size = map_settings.get("tile_size", 256)
        max_zoomlevel = map_settings.get("max_zoomlevel")
        expand = max_zoomlevel is not None and z > max_zoomlevel

        z_draw, z_conv_factor, tile_x, tile_y = self.init_draw_map(
            map_config, map_name, z, p0, p1, expand, tile_size
        )
        tiles = self.get_tiles_for_drawing(tile_x, tile_y, z_conv_factor, expand)

        # Cache the result
        self._cached_tiles[map_name] = {
            "z": z,
            "z_draw": z_draw,
            "tiles": tiles,
            "tile_x": tile_x,
            "tile_y": tile_y,
            "z_conv_factor": z_conv_factor,
            "expand": expand,
        }

        # Check for pending downloads
        existing_tiles = self.maptile_with_values.existing_tiles
        for tile in tiles:
            filename = get_maptile_filename(map_name, z_draw, *tile, map_settings)
            if existing_tiles.get(filename) is False:
                return True
        return False

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
        course_index_value, course_on_status = self._get_course_display_state()

        display_key = (
            norm(gps_values.get("lon")),
            norm(gps_values.get("lat")),
            norm(gps_values.get("track")),
            norm(gps_values.get("mode")),
            norm(self.map_pos.get("x")),
            norm(self.map_pos.get("y")),
            self.lock_status,
            self.move_adjust_mode,
            self.zoomlevel,
            self.overlay_index,
            self.config.G_MAP,
            overlay_map,
            overlay_time_key,
            overlay_basetime,
            overlay_validtime,
            overlay_subdomain,
            self.tile_modify_mode,
            self.plot.width(),
            self.plot.height(),
            course_index_value,
            course_on_status,
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
        if self.track_timestamp is None:
            reasons.append("track_init")
        if not getattr(self.logger, "short_log_available", True):
            reasons.append("short_log_unavailable")
        if len(getattr(self.logger, "short_log_lat", [])):
            reasons.append("short_log_pending")
        if self.pre_zoomlevel.get(self.config.G_MAP) != self.zoomlevel:
            reasons.append("zoom_changed")
        if not main_drawn:
            reasons.append("main_tile_missing")
        if hasattr(self, "_has_tile_batch_pending") and self._has_tile_batch_pending():
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
        self.point["pos"] = [self.gps_values["lon"], self.gps_values["lat"]]
        if np.isnan(self.gps_values["lon"]) or np.isnan(self.gps_values["lat"]):
            if (
                self.track_last_lon_pos is not None
                and self.track_last_lat_pos is not None
            ):
                self.point["pos"] = [self.track_last_lon_pos, self.track_last_lat_pos]
            elif len(self.track_tail_lon) and len(self.track_tail_lat):
                self.point["pos"] = [self.track_tail_lon[-1], self.track_tail_lat[-1]]
            elif len(self.track_history_lon) and len(self.track_history_lat):
                self.point["pos"] = [
                    self.track_history_lon[-1],
                    self.track_history_lat[-1],
                ]
            elif self.course.is_set:
                self.point["pos"] = [
                    self.course.longitude[0],
                    self.course.latitude[0],
                ]
            else:
                self.point["pos"] = [
                    self.config.G_DUMMY_POS_X,
                    self.config.G_DUMMY_POS_Y,
                ]

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
        x_move = y_move = 0
        if (
            self.lock_status
            and len(self.course.distance)
            and self.course.index.on_course_status
        ):
            index = self.course.get_index_with_distance_cutoff(
                self.course.index.value,
                get_width_distance(self.map_pos["y"], self.map_area["w"]) / 1000,
            )
            x2 = self.course.longitude[index]
            y2 = self.course.latitude[index]
            x_delta = x2 - self.map_pos["x"]
            y_delta = y2 - self.map_pos["y"]
            x_move = 0.25 * self.map_area["w"]
            y_move = 0.25 * self.map_area["h"]
            if x_delta > x_move:
                self.map_pos["x"] += x_move
            elif x_delta < -x_move:
                self.map_pos["x"] -= x_move
            if y_delta > y_move:
                self.map_pos["y"] += y_move
            elif y_delta < -y_move:
                self.map_pos["y"] -= y_move
        elif not self.lock_status:
            if self.move_pos["x"] > 0:
                x_move = self.map_area["w"] / 2
            elif self.move_pos["x"] < 0:
                x_move = -self.map_area["w"] / 2
            if self.move_pos["y"] > 0:
                y_move = self.map_area["h"] / 2
            elif self.move_pos["y"] < 0:
                y_move = -self.map_area["h"] / 2
            self.map_pos["x"] += x_move / self.move_factor
            self.map_pos["y"] += y_move / self.move_factor
        self.move_pos["x"] = self.move_pos["y"] = 0

        self.map_area["w"], self.map_area["h"] = self.get_geo_area(
            self.map_pos["x"],
            self.map_pos["y"],
        )

    def _update_current_and_center_items(self):
        self.point["pos"][1] *= self.y_mod
        self.location.append(self.point)

        if not np.isnan(self.gps_values["track"]):
            self.current_point.setSymbol(
                self.direction_arrows[
                    self.get_arrow_angle_index(self.gps_values["track"])
                ]
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
        force_apply = getattr(self, "_last_display_key", None) is None

        x_applied = False
        y_applied = False

        if not np.isnan(x_start) and not np.isnan(x_end):
            x_state = (x_start, x_end, view_width)
            if force_apply or self._should_apply_axis_range(
                x_start, x_end, view_width, self._last_applied_x_range
            ):
                self.plot.setXRange(x_start, x_end, padding=0)
                self._last_applied_x_range = x_state
                self._last_applied_x_bounds = (x_start, x_end)
                x_applied = True

        if not np.isnan(y_start) and not np.isnan(y_end):
            y_start_mod = get_mod_lat(y_start)
            y_end_mod = get_mod_lat(y_end)
            y_state = (y_start_mod, y_end_mod, view_height)
            if force_apply or self._should_apply_axis_range(
                y_start_mod, y_end_mod, view_height, self._last_applied_y_range
            ):
                self.plot.setYRange(y_start_mod, y_end_mod, padding=0)
                self._last_applied_y_range = y_state
                self._last_applied_y_bounds = (y_start, y_end)
                y_applied = True

        if x_applied:
            applied_x_start, applied_x_end = x_start, x_end
        elif self._last_applied_x_bounds is not None:
            applied_x_start, applied_x_end = self._last_applied_x_bounds
        else:
            applied_x_start, applied_x_end = x_start, x_end

        if y_applied:
            applied_y_start, applied_y_end = y_start, y_end
        elif self._last_applied_y_bounds is not None:
            applied_y_start, applied_y_end = self._last_applied_y_bounds
        else:
            applied_y_start, applied_y_end = y_start, y_end

        # Return the effective bounds currently shown on screen.
        # When range updates are skipped by px-threshold, downstream drawing should
        # reuse the last applied bounds to keep tile/HUD coordinates consistent.
        return applied_x_start, applied_x_end, applied_y_start, applied_y_end
