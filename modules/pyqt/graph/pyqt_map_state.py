from datetime import timedelta

import numpy as np

from modules._qt_qtwidgets import pg
from modules.utils.geo import calc_y_mod, get_mod_lat, get_width_distance
from modules.utils.map import get_maptile_filename


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

    @staticmethod
    def _get_aligned_current_time(map_settings):
        current_time = map_settings["current_time_func"]()
        delta_minutes = current_time.minute % map_settings["time_interval"]
        if delta_minutes > map_settings["time_interval"] / 2:
            delta_minutes -= map_settings["time_interval"]
        current_time += timedelta(minutes=-delta_minutes)
        return current_time.replace(second=0, microsecond=0)

    def _setup_map_state_items(self):
        self.map_pos["x"] = self.config.G_DUMMY_POS_X
        self.map_pos["y"] = self.config.G_DUMMY_POS_Y

        self.point["size"] = 29
        self._init_direction_arrows()
        self._init_center_point()

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

        if overlay_type == "HEATMAP":
            overlay_map = self.config.G_HEATMAP_OVERLAY_MAP
        elif overlay_type == "RAIN":
            overlay_map = self.config.G_RAIN_OVERLAY_MAP
            map_settings = self.config.G_RAIN_OVERLAY_MAP_CONFIG.get(overlay_map)
            if map_settings:
                overlay_time_key = self._get_aligned_current_time(map_settings)
        elif overlay_type == "WIND":
            overlay_map = self.config.G_WIND_OVERLAY_MAP
            map_settings = self.config.G_WIND_OVERLAY_MAP_CONFIG.get(overlay_map)
            if map_settings:
                overlay_time_key = self._get_aligned_current_time(map_settings)

        if map_settings:
            overlay_basetime = map_settings.get("basetime")
            overlay_validtime = map_settings.get("validtime")
            overlay_subdomain = map_settings.get("subdomain")

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
        if overlay_type == "WIND":
            names.append(self.config.G_WIND_OVERLAY_MAP)
        elif overlay_type == "RAIN":
            names.append(self.config.G_RAIN_OVERLAY_MAP)
        elif overlay_type == "HEATMAP":
            names.append(self.config.G_HEATMAP_OVERLAY_MAP)
        return names

    def _cleanup_cached_tiles(self):
        """Remove cache entries for inactive maps."""
        active = set(self._get_active_map_names())
        for key in list(self._cached_tiles.keys()):
            if key not in active:
                del self._cached_tiles[key]

    def _get_map_config_for_name(self, map_name):
        """Return the map config dict for a given map_name."""
        if map_name == self.config.G_MAP:
            return self.config.G_MAP_CONFIG
        if map_name == self.config.G_WIND_OVERLAY_MAP:
            return self.config.G_WIND_OVERLAY_MAP_CONFIG
        if map_name == self.config.G_RAIN_OVERLAY_MAP:
            return self.config.G_RAIN_OVERLAY_MAP_CONFIG
        if map_name == self.config.G_HEATMAP_OVERLAY_MAP:
            return self.config.G_HEATMAP_OVERLAY_MAP_CONFIG
        return None

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
            self.map_cuesheet_ratio,
            self.plot.width(),
            self.plot.height(),
            course_index_value,
            course_on_status,
            self.course_points.is_set,
        )
        return display_key, overlay_map

    def _needs_redraw(self, overlay_map):
        main_drawn = self.drawn_tile.get(self.config.G_MAP, {}).get(self.zoomlevel, {})
        return (
            not self.course_loaded
            or self.move_pos["x"] != 0
            or self.move_pos["y"] != 0
            or self.tracks_timestamp is None
            or not getattr(self.logger, "short_log_available", True)
            or len(getattr(self.logger, "short_log_lat", []))
            or self.pre_zoomlevel.get(self.config.G_MAP) != self.zoomlevel
            or not main_drawn
            or self._has_pending_downloads()
            or (overlay_map and not self.drawn_tile.get(overlay_map))
        )

    def _should_skip_display_update(self, display_key, overlay_map):
        prev_display_key = self._last_display_key
        if prev_display_key is None:
            return False
        if display_key != prev_display_key:
            return False
        return not self._needs_redraw(overlay_map)

    def _clear_display_buffers(self):
        if len(self.location):
            self.location.clear()
        if len(self.center_point_location):
            self.center_point_location.clear()

    def _update_point_state(self):
        self.point["pos"] = [self.gps_values["lon"], self.gps_values["lat"]]
        if np.isnan(self.gps_values["lon"]) or np.isnan(self.gps_values["lat"]):
            if len(self.tracks_lon) and len(self.tracks_lat):
                self.point["pos"] = [self.tracks_lon_pos, self.tracks_lat_pos]
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
        if not np.isnan(x_start) and not np.isnan(x_end):
            self.plot.setXRange(x_start, x_end, padding=0)
        if not np.isnan(y_start) and not np.isnan(y_end):
            self.plot.setYRange(get_mod_lat(y_start), get_mod_lat(y_end), padding=0)
