import datetime
import io
import os
import sqlite3

import numpy as np
from PIL import Image

from logger import app_logger
from modules._pyqt import QtCore, QtGui, pg, qasync
from modules.pyqt.pyqt_cuesheet_widget import CueSheetWidget
from modules.pyqt.graph.pyqtgraph.CoursePlotItem import CoursePlotItem
from modules.utils.geo import (
    calc_y_mod,
    get_mod_lat,
    get_mod_lat_np,
    get_width_distance,
)
from modules.utils.map import (
    get_maptile_filename,
    get_lon_lat_from_tile_xy,
    get_tilexy_and_xy_in_tile,
    remove_maptiles,
)
from modules.utils.timer import Timer, log_timers
from .pyqt_base_map import BaseMapWidget


class MapWidget(BaseMapWidget):
    # map position
    map_area = {
        "w": np.nan,
        "h": np.nan,
    }  # width(longitude diff) and height(latitude diff)
    move_pos = {"x": 0, "y": 0}
    map_pos = {"x": np.nan, "y": np.nan}  # center

    # current point
    location = []

    # tracks
    tracks_lat = np.array([])
    tracks_lon = np.array([])
    tracks_lat_pos = None
    tracks_lon_pos = None
    tracks_timestamp = None

    course_plot = None
    plot_verification = None
    course_points_plot = None
    instruction = None

    cuesheet_widget = None

    # misc
    arrow_direction_num = 16
    # calculate these ony once
    arrow_direction_angle_unit = 360 / arrow_direction_num
    arrow_direction_angle_unit_half = arrow_direction_angle_unit / 2

    y_mod = 1.22  # 31/25 at Tokyo(N35)
    pre_zoomlevel = {}

    drawn_tile = {}
    existing_tiles = {}
    map_cuesheet_ratio = 1  # map:cuesheet = 1:0

    zoom_delta_from_tilesize = 0
    auto_zoomlevel = None
    auto_zoomlevel_diff = 2  # auto_zoomlevel = zoomlevel + auto_zoomlevel_diff
    auto_zoomlevel_back = None

    # signal for physical button
    signal_search_route = QtCore.pyqtSignal()

    track_pen = pg.mkPen(color=(0, 170, 255), width=4)
    scale_pen = pg.mkPen(color=(0, 0, 0), width=3)

    scale_text = pg.TextItem(
        text="",
        anchor=(0.5, 1),
        angle=0,
        border=(255, 255, 255, 255),
        fill=(255, 255, 255, 255),
        color=(0, 0, 0),
    )

    map_attribution = pg.TextItem(
        anchor=(1, 1),
        angle=0,
        border=(255, 255, 255, 255),
        fill=(255, 255, 255, 255),
        color=(0, 0, 0),
    )

    def setup_ui_extra(self):
        super().setup_ui_extra()

        self.map_pos["x"] = self.config.G_DUMMY_POS_X
        self.map_pos["y"] = self.config.G_DUMMY_POS_Y

        # self.plot.showGrid(x=True, y=True, alpha=1)
        self.track_plot = self.plot.plot(pen=self.track_pen)
        self.scale_plot = self.plot.plot(pen=self.scale_pen)

        self.current_point.setZValue(40)
        self.track_plot.setZValue(30)
        self.scale_text.setZValue(100)
        self.map_attribution.setZValue(100)

        self.plot.addItem(self.map_attribution)
        self.plot.addItem(self.scale_text)

        # current point
        self.point["size"] = 29

        self.direction_arrows = []
        array_symbol_base = np.array(
            [
                [-0.45, -0.5],
                [0, -0.3],
                [0.45, -0.5],
                [0, 0.5],
                [-0.45, -0.5],
            ]
        )  # 0 or 360 degree
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
            R = np.array([[cos_rad, sin_rad], [-sin_rad, cos_rad]])
            array_symbol_conv = np.dot(R, array_symbol_base.T).T
            self.direction_arrows.append(
                pg.arrayToQPath(
                    array_symbol_conv[:, 0], -array_symbol_conv[:, 1], connect="all"
                )
            )

        # center point (displays while moving the map)
        self.center_point = pg.ScatterPlotItem(pxMode=True, symbol="+")
        self.center_point.setZValue(50)
        self.center_point_data = {
            "pos": [np.nan, np.nan],
            "size": 15,
            "pen": {"color": (0, 0, 0), "width": 2},
        }
        self.center_point_location = []

        # connect signal
        self.signal_search_route.connect(self.search_route)

        self.reset_map()

        # self.load_course()
        t = datetime.datetime.utcnow()
        self.get_track()  # heavy when resume
        if len(self.tracks_lon):
            app_logger.info(
                f"resume_track(init): {(datetime.datetime.utcnow() - t).total_seconds():.3f} sec"
            )

        # map
        self.layout.addWidget(self.plot, 0, 0, 4, 3)

        if self.config.display.has_touch():
            # zoom
            self.layout.addWidget(self.buttons["zoomdown"], 0, 0)
            self.layout.addWidget(self.buttons["lock"], 1, 0)
            self.layout.addWidget(self.buttons["zoomup"], 2, 0)
            # arrow
            self.layout.addWidget(self.buttons["left"], 0, 2)
            self.layout.addWidget(self.buttons["up"], 1, 2)
            self.layout.addWidget(self.buttons["down"], 2, 2)
            self.layout.addWidget(self.buttons["right"], 3, 2)

            if self.config.G_GOOGLE_DIRECTION_API["HAVE_API_TOKEN"]:
                self.layout.addWidget(self.buttons["go"], 3, 0)
                self.buttons["go"].clicked.connect(self.search_route)

        # cue sheet and instruction
        self.init_cuesheet_and_instruction()

        # for expanding column
        self.layout.setColumnMinimumWidth(0, 40)
        self.layout.setColumnStretch(1, 1)
        self.layout.setColumnMinimumWidth(2, 40)

    def reset_map(self):
        # adjust zoom level for large tiles
        zoom_delta_from_tilesize = (
            int(self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"] / 256) - 1
        )
        self.zoomlevel += self.zoom_delta_from_tilesize - zoom_delta_from_tilesize
        self.zoom_delta_from_tilesize = zoom_delta_from_tilesize
        if self.zoomlevel < 1:
            self.zoomlevel = 1
        self.auto_zoomlevel = self.zoomlevel + self.auto_zoomlevel_diff

        for key in [
            self.config.G_MAP,
            self.config.G_HEATMAP_OVERLAY_MAP,
            self.config.G_RAIN_OVERLAY_MAP,
            self.config.G_WIND_OVERLAY_MAP,
        ]:
            self.drawn_tile[key] = {}
            self.existing_tiles[key] = {}
            self.pre_zoomlevel[key] = np.nan

        attribution_text = self.config.G_MAP_CONFIG[self.config.G_MAP]["attribution"]
        if self.config.G_USE_HEATMAP_OVERLAY_MAP:
            attribution_text += (
                "<br />"
                + self.config.G_HEATMAP_OVERLAY_MAP_CONFIG[
                    self.config.G_HEATMAP_OVERLAY_MAP
                ]["attribution"]
            )
        if self.config.G_USE_RAIN_OVERLAY_MAP:
            attribution_text += (
                "<br />"
                + self.config.G_RAIN_OVERLAY_MAP_CONFIG[self.config.G_RAIN_OVERLAY_MAP][
                    "attribution"
                ]
            )
        if self.config.G_USE_WIND_OVERLAY_MAP:
            attribution_text += (
                "<br />"
                + self.config.G_WIND_OVERLAY_MAP_CONFIG[self.config.G_WIND_OVERLAY_MAP][
                    "attribution"
                ]
            )
        self.map_attribution.setHtml(
            '<div style="text-align: right;"><span style="color: #000; font-size: 10px;">'
            + attribution_text
            + "</span></div>"
        )
        if attribution_text == "":
            self.map_attribution.setZValue(-100)
        else:
            self.map_attribution.setZValue(100)

    def init_cuesheet_and_instruction(self):
        # init cuesheet_widget
        if (
            self.config.logger.course.course_points.is_set
            and self.config.G_CUESHEET_DISPLAY_NUM
            and self.config.G_COURSE_INDEXING
        ):
            if self.cuesheet_widget is None:
                self.cuesheet_widget = CueSheetWidget(self, self.config)
                self.cuesheet_widget.hide()  # adhoc

            self.map_cuesheet_ratio = 1.0

            # init instruction
            self.instruction = pg.TextItem(
                color=(0, 0, 0),
                anchor=(0.5, 0.5),
                fill=(255, 255, 255, 192),
                border=(0, 0, 0),
            )
            self.instruction.setZValue(100)

    def resizeEvent(self, event):
        if (
            not self.course_points.is_set
            or not self.config.G_CUESHEET_DISPLAY_NUM
            or not self.config.G_COURSE_INDEXING
        ):
            self.map_cuesheet_ratio = 1.0
        # if self.config.G_CUESHEET_DISPLAY_NUM:
        else:
            # self.cuesheet_widget.setFixedWidth(int(self.width()*(1-self.map_cuesheet_ratio)))
            # self.cuesheet_widget.setFixedHeight(self.height())
            pass
        self.plot.setFixedWidth(int(self.width() * (self.map_cuesheet_ratio)))
        self.plot.setFixedHeight(self.height())

    # override for long press
    def switch_lock(self):
        if self.buttons["lock"].isDown():
            if self.buttons["lock"]._state == 0:
                self.buttons["lock"]._state = 1
            else:
                self.button_press_count["lock"] += 1
                # long press
                if (
                    self.button_press_count["lock"]
                    == self.config.button_config.G_BUTTON_LONG_PRESS
                ):
                    self.change_move()
        elif self.buttons["lock"]._state == 1:
            self.buttons["lock"]._state = 0
            self.button_press_count["lock"] = 0
        # short press
        else:
            super().switch_lock()

    def load_course(self):
        timers = [
            Timer(auto_start=False, text="course plot  : {0:.3f} sec"),
            Timer(auto_start=False, text="course points: {0:.3f} sec"),
        ]

        with timers[0]:
            if self.course_plot is not None:
                self.plot.removeItem(self.course_plot)
            if not len(self.course.latitude):
                app_logger.warning("Course has no points")
            else:
                self.course_plot = CoursePlotItem(
                    x=self.course.longitude,
                    y=get_mod_lat_np(self.course.latitude),
                    brushes=self.course.colored_altitude,
                    width=6,
                )
                self.course_plot.setZValue(20)
                self.plot.addItem(self.course_plot)

                # test
                if not self.config.G_IS_RASPI:
                    if self.plot_verification is not None:
                        self.plot.removeItem(self.plot_verification)
                    self.plot_verification = pg.ScatterPlotItem(pxMode=True)
                    self.plot_verification.setZValue(25)
                    test_points = []
                    for i in range(len(self.course.longitude)):
                        p = {
                            "pos": [
                                self.course.longitude[i],
                                get_mod_lat(self.course.latitude[i]),
                            ],
                            "size": 2,
                            "pen": {"color": "w", "width": 1},
                            "brush": pg.mkBrush(color=(255, 0, 0)),
                        }
                        test_points.append(p)
                    self.plot_verification.setData(test_points)
                    self.plot.addItem(self.plot_verification)

        with timers[1]:
            if self.course_points_plot is not None:
                self.plot.removeItem(self.course_points_plot)

            if not len(self.course_points.longitude):
                app_logger.warning("No course points found")

            else:
                self.course_points_plot = pg.ScatterPlotItem(
                    pxMode=True, symbol="t", size=12
                )
                self.course_points_plot.setZValue(40)
                formatted_course_points = []

                for i in reversed(range(len(self.course_points.longitude))):
                    color = (255, 0, 0)
                    symbol = "t"
                    if self.course_points.type[i] == "Left":
                        symbol = "t3"
                    elif self.course_points.type[i] == "Right":
                        symbol = "t2"
                    cp = {
                        "pos": [
                            self.course_points.longitude[i],
                            get_mod_lat(self.course_points.latitude[i]),
                        ],
                        "pen": {"color": color, "width": 1},
                        "symbol": symbol,
                        "brush": pg.mkBrush(color=color),
                    }
                    formatted_course_points.append(cp)
                self.course_points_plot.setData(formatted_course_points)
                self.plot.addItem(self.course_points_plot)

        app_logger.info("Plotting course:")
        log_timers(timers, text_total=f"total        : {0:.3f} sec")

    @qasync.asyncSlot()
    async def update_display(self):
        # display current position
        if len(self.location):
            self.plot.removeItem(self.current_point)
            self.location.pop()
        # display center point
        if len(self.center_point_location):
            self.plot.removeItem(self.center_point)
            self.center_point_location.pop()

        # current position
        self.point["pos"] = [self.gps_values["lon"], self.gps_values["lat"]]
        # dummy position
        if np.isnan(self.gps_values["lon"]) or np.isnan(self.gps_values["lat"]):
            # recent point(from log or pre_point) / course start / dummy
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
        # update y_mod (adjust for lat:lon=1:1)
        self.y_mod = calc_y_mod(self.point["pos"][1])
        # add position circle to map
        if self.gps_values["mode"] == 3:  # NMEA_MODE_3D
            self.point["brush"] = self.point_color["fix"]
        else:
            self.point["brush"] = self.point_color["lost"]

        # center position
        if self.lock_status:
            self.map_pos["x"] = self.point["pos"][0]
            self.map_pos["y"] = self.point["pos"][1]

        # set width and height
        self.map_area["w"], self.map_area["h"] = self.get_geo_area(
            self.map_pos["x"], self.map_pos["y"]
        )

        # move
        x_move = y_move = 0
        if (
            self.lock_status
            and len(self.course.distance)
            and self.course.index.on_course_status
        ):
            index = self.course.get_index_with_distance_cutoff(
                self.course.index.value,
                # get some forward distance [m]
                get_width_distance(self.map_pos["y"], self.map_area["w"]) / 1000,
            )
            x2 = self.course.longitude[index]
            y2 = self.course.latitude[index]
            x_delta = x2 - self.map_pos["x"]
            y_delta = y2 - self.map_pos["y"]
            # slide from center
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
            self.map_pos["x"], self.map_pos["y"]
        )

        ###########
        # drawing #
        ###########

        # current point
        # print(self.point['pos'])
        self.point["pos"][1] *= self.y_mod
        self.location.append(self.point)

        if not np.isnan(self.gps_values["track"]):
            self.current_point.setSymbol(
                self.direction_arrows[
                    self.get_arrow_angle_index(self.gps_values["track"])
                ]
            )

        self.current_point.setData(self.location)
        self.plot.addItem(self.current_point)

        # center point
        if not self.lock_status:
            if self.move_adjust_mode:
                self.center_point_data["size"] = 7.5
            else:
                self.center_point_data["size"] = 15
            self.center_point_data["pos"][0] = self.map_pos["x"]
            self.center_point_data["pos"][1] = get_mod_lat(self.map_pos["y"])
            self.center_point_location.append(self.center_point_data)
            self.center_point.setData(self.center_point_location)
            self.plot.addItem(self.center_point)

        # set x and y ranges
        x_start = self.map_pos["x"] - self.map_area["w"] / 2
        x_end = x_start + self.map_area["w"]
        y_start = self.map_pos["y"] - self.map_area["h"] / 2
        y_end = y_start + self.map_area["h"]

        if not np.isnan(x_start) and not np.isnan(x_end):
            self.plot.setXRange(x_start, x_end, padding=0)
        if not np.isnan(y_start) and not np.isnan(y_end):
            self.plot.setYRange(get_mod_lat(y_start), get_mod_lat(y_end), padding=0)

        if not np.any(np.isnan([x_start, x_end, y_start, y_end])):
            await self.draw_map_tile(x_start, x_end, y_start, y_end)

        # TODO shouldn't be there but does not plot if removed !
        if not self.course_loaded:
            self.load_course()
            self.course_loaded = True

        await self.update_cuesheet_and_instruction(
            x_start, x_end, y_start, y_end, auto_zoom=True
        )

        # draw track
        self.get_track()
        self.track_plot.setData(self.tracks_lon, self.tracks_lat)

        if not np.any(np.isnan([x_start, y_start])):
            # draw scale
            self.draw_scale(x_start, y_start)
            # draw map attribution
            self.draw_map_attribution(x_start, y_start)

    def get_track(self):
        # get track from SQL
        # not good (input & output)    #conversion coordinate
        (self.tracks_timestamp, lon, lat) = self.logger.update_track(
            self.tracks_timestamp
        )
        if len(lon) and len(lat):
            self.tracks_lon_pos = lon[-1]
            self.tracks_lat_pos = lat[-1]
            self.tracks_lon = np.append(self.tracks_lon, np.array(lon))
            self.tracks_lat = np.append(self.tracks_lat, get_mod_lat_np(np.array(lat)))

    def reset_track(self):
        self.tracks_lon = np.array([])
        self.tracks_lat = np.array([])

    def reset_course(self):
        for p in [
            self.course_plot,
            self.plot_verification,
            self.course_points_plot,
            self.instruction,
        ]:
            if p is not None:
                self.plot.removeItem(p)

        if self.cuesheet_widget is not None:
            self.cuesheet_widget.reset()

    def init_course(self):
        self.init_cuesheet_and_instruction()
        self.course_loaded = False
        self.resizeEvent(None)

    @qasync.asyncSlot()
    async def search_route(self):
        if self.lock_status:
            return

        await self.course.search_route(
            self.point["pos"][0],
            self.point["pos"][1] / self.y_mod,
            self.map_pos["x"],
            self.map_pos["y"],
        )
        self.init_course()

    async def draw_map_tile(self, x_start, x_end, y_start, y_end):
        # get tile coordinates of display border points
        p0 = {"x": min(x_start, x_end), "y": min(y_start, y_end)}
        p1 = {"x": max(x_start, x_end), "y": max(y_start, y_end)}

        # map
        drawn_main_map = await self.draw_map_tile_by_overlay(
            self.config.G_MAP_CONFIG,
            self.config.G_MAP,
            self.zoomlevel,
            p0,
            p1,
            overlay=False,
            use_mbtiles=self.config.G_MAP_CONFIG[self.config.G_MAP]["use_mbtiles"],
        )

        await self.overlay_heatmap(drawn_main_map, p0, p1)
        await self.overlay_rainmap(drawn_main_map, p0, p1)
        await self.overlay_windmap(drawn_main_map, p0, p1)

    async def overlay_heatmap(self, drawn_main_map, p0, p1):
        if not self.config.G_USE_HEATMAP_OVERLAY_MAP:
            return
        await self.overlay_map(
            drawn_main_map,
            p0,
            p1,
            self.config.G_HEATMAP_OVERLAY_MAP_CONFIG,
            self.config.G_HEATMAP_OVERLAY_MAP,
        )

    async def overlay_rainmap(self, drawn_main_map, p0, p1):
        if not self.config.G_USE_RAIN_OVERLAY_MAP:
            return

        map_config = self.config.G_RAIN_OVERLAY_MAP_CONFIG
        map_name = self.config.G_RAIN_OVERLAY_MAP
        if self.update_overlay_basetime(map_config, map_name):
            # basetime update
            if map_config[map_name]["time_format"] == "unix_timestamp":
                basetime_str = str(int(map_config[map_name]["nowtime"].timestamp()))
            else:
                basetime_str = map_config[map_name]["nowtime"].strftime(
                    map_config[map_name]["time_format"]
                )

            map_config[map_name]["basetime"] = basetime_str
            map_config[map_name]["validtime"] = map_config[map_name]["basetime"]

            # re-draw from self.config.G_MAP
            return

        await self.overlay_map(drawn_main_map, p0, p1, map_config, map_name)

    async def overlay_windmap(self, drawn_main_map, p0, p1):
        if not self.config.G_USE_WIND_OVERLAY_MAP:
            return

        map_config = self.config.G_WIND_OVERLAY_MAP_CONFIG
        map_name = self.config.G_WIND_OVERLAY_MAP
        if self.update_overlay_basetime(map_config, map_name):
            # basetime update
            if "jpn_scw" in map_name:
                init_time_list = await self.config.api.get_scw_list(
                    map_config[map_name], "inittime"
                )
                if init_time_list is not None:
                    map_config[map_name]["basetime"] = init_time_list[0]["it"]

                timeline = await self.config.api.get_scw_list(
                    map_config[map_name], "fl"
                )
                if timeline is not None:
                    map_config[map_name]["fl"] = timeline
                    time_str = map_config[map_name]["nowtime"].strftime("%H%M")
                    for tl in map_config[map_name]["fl"]:
                        if tl["it"][0:4] == time_str:
                            map_config[map_name]["validtime"] = tl["it"]
                            map_config[map_name]["subdomain"] = tl["sd"]
                            break
            else:
                basetime_str = map_config[map_name]["nowtime"].strftime(
                    map_config[map_name]["time_format"]
                )
                map_config[map_name]["basetime"] = basetime_str
                map_config[map_name]["validtime"] = map_config[map_name]["basetime"]

            # re-draw from self.config.G_MAP
            return

        await self.overlay_map(drawn_main_map, p0, p1, map_config, map_name)

    def update_overlay_basetime(self, map_config, map_name):
        config = map_config[map_name]

        # update basetime
        nowtime = config["nowtime_func"]()
        delta_minutes = nowtime.minute % config["time_interval"]
        delta_seconds = delta_minutes * 60 + nowtime.second
        delta_seconds_cutoff = config["update_minutes"] * 60 + 15

        if delta_seconds < delta_seconds_cutoff:
            delta_minutes = delta_minutes + config["time_interval"]
        nowtime_mod = (nowtime + datetime.timedelta(minutes=-delta_minutes)).replace(
            second=0, microsecond=0
        )

        if config["nowtime"] != nowtime_mod:
            # clear tile
            self.drawn_tile[self.config.G_MAP] = {}
            self.drawn_tile[map_name] = {}
            self.existing_tiles[map_name] = {}
            self.pre_zoomlevel[map_name] = np.nan
            remove_maptiles(map_name)

            config["nowtime"] = nowtime_mod
            return True

        return False

    async def overlay_map(self, drawn_main_map, p0, p1, map_config, map_name):
        if drawn_main_map:
            self.drawn_tile[map_name] = {}

        z = (
            self.zoomlevel
            + int(
                self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"]
                / map_config[map_name]["tile_size"]
            )
            - 1
        )
        # supported zoom levels
        if (
            map_config[map_name]["min_zoomlevel"]
            <= z
            <= map_config[map_name]["max_zoomlevel"]
        ):
            await self.draw_map_tile_by_overlay(
                map_config, map_name, z, p0, p1, overlay=True
            )
        # above maximum zoom level: expand max zoomlevel tiles
        elif z > map_config[map_name]["max_zoomlevel"]:
            await self.draw_map_tile_by_overlay(
                map_config, map_name, z, p0, p1, overlay=True, expand=True
            )
        else:
            self.pre_zoomlevel[map_name] = z

    async def draw_map_tile_by_overlay(
        self,
        map_config,
        map_name,
        z,
        p0,
        p1,
        overlay=False,
        expand=False,
        use_mbtiles=False,
    ):
        tile_size = map_config[map_name]["tile_size"]

        # specify tile range and zoomlevel
        # z: current zoomlevel from map widget
        # z_draw: actual zoomlevel of map tile (for overlay map tiles which have limited zoomlevel)
        # tile_x, tile_y: tile range in zoomlevel z
        z_draw, z_conv_factor, tile_x, tile_y = self.init_draw_map(
            map_config, map_name, z, p0, p1, expand, tile_size
        )

        if not use_mbtiles:
            # prepare tiles for download
            tiles = self.get_tiles_for_drawing(tile_x, tile_y, z_conv_factor, expand)

            # download
            if z not in self.existing_tiles[map_name]:
                self.existing_tiles[map_name][z_draw] = {}
            await self.download_tiles(tiles, map_config, map_name, z_draw)

        # tile check
        if use_mbtiles:
            self.con = sqlite3.connect(
                f"file:./maptile/{map_name}.mbtiles?mode=ro", uri=True
            )
            self.cur = self.con.cursor()

        draw_flag, add_keys, expand_keys = self.check_drawn_tile(
            use_mbtiles, map_name, z, z_draw, z_conv_factor, tile_x, tile_y, expand
        )

        self.pre_zoomlevel[map_name] = z
        if not draw_flag:
            if use_mbtiles:
                self.cur.close()
                self.con.close()
            return False

        # draw only the necessary tiles
        w_h = int(tile_size / z_conv_factor) if expand else 0
        for keys in add_keys:
            x, y = keys[0:2] if not expand else expand_keys[keys][0:2]
            img_file = self.get_image_file(use_mbtiles, map_name, z_draw, x, y)
            if not expand:
                imgarray = np.rot90(
                    np.asarray(Image.open(img_file).convert("RGBA")), -1
                )
            else:
                x_start, y_start = int(w_h * expand_keys[keys][2]), int(
                    w_h * expand_keys[keys][3]
                )
                imgarray = np.rot90(
                    np.asarray(
                        Image.open(img_file)
                        .crop((x_start, y_start, x_start + w_h, y_start + w_h))
                        .convert("RGBA")
                    ),
                    -1,
                )

            imgitem = pg.ImageItem(imgarray)
            if overlay:
                imgitem.setCompositionMode(QtGui.QPainter.CompositionMode_Darken)
            imgarray_min_x, imgarray_max_y = get_lon_lat_from_tile_xy(
                z, keys[0], keys[1]
            )
            imgarray_max_x, imgarray_min_y = get_lon_lat_from_tile_xy(
                z, keys[0] + 1, keys[1] + 1
            )

            self.plot.addItem(imgitem)
            imgitem.setZValue(-100)
            imgitem.setRect(
                pg.QtCore.QRectF(
                    imgarray_min_x,
                    get_mod_lat(imgarray_min_y),
                    imgarray_max_x - imgarray_min_x,
                    get_mod_lat(imgarray_max_y) - get_mod_lat(imgarray_min_y),
                )
            )
        if use_mbtiles:
            self.cur.close()
            self.con.close()

        return True

    @staticmethod
    def init_draw_map(map_config, map_name, z, p0, p1, expand, tile_size):
        z_draw = z
        z_conv_factor = 1
        if expand:
            if z > map_config[map_name]["max_zoomlevel"]:
                z_draw = map_config[map_name]["max_zoomlevel"]
            elif z < map_config[map_name]["min_zoomlevel"]:
                z_draw = map_config[map_name]["min_zoomlevel"]
            # z_draw = min(z, map_config[map_name]['max_zoomlevel'])
            z_conv_factor = 2 ** (z - z_draw)

        # tile range
        t0 = get_tilexy_and_xy_in_tile(z, p0["x"], p0["y"], tile_size)
        t1 = get_tilexy_and_xy_in_tile(z, p1["x"], p1["y"], tile_size)
        tile_x = sorted([t0[0], t1[0]])
        tile_y = sorted([t0[1], t1[1]])
        return z_draw, z_conv_factor, tile_x, tile_y

    @staticmethod
    def get_tiles_for_drawing(tile_x, tile_y, z_conv_factor, expand):
        tiles = []
        for i in range(tile_x[0], tile_x[1] + 1):
            for j in range(tile_y[0], tile_y[1] + 1):
                tiles.append((i, j))
                # tiles.append((int(i/z_conv_factor), int(j/z_conv_factor)))
        for i in [tile_x[0] - 1, tile_x[1] + 1]:
            for j in range(tile_y[0] - 1, tile_y[1] + 2):
                tiles.append((i, j))
                # tiles.append((int(i/z_conv_factor), int(j/z_conv_factor)))
        for i in range(tile_x[0], tile_x[1] + 1):
            for j in [tile_y[0] - 1, tile_y[1] + 1]:
                tiles.append((i, j))
                # tiles.append((int(i/z_conv_factor), int(j/z_conv_factor)))

        if expand and z_conv_factor > 1:
            tiles = list(
                set(
                    map(
                        lambda x: tuple(map(lambda y: int(y / z_conv_factor), x)), tiles
                    )
                )
            )

        return tiles

    async def download_tiles(self, tiles, map_config, map_name, z_draw):
        download_tile = []
        for tile in tiles:
            filename = get_maptile_filename(map_name, z_draw, *tile)
            key = "{0}-{1}".format(*tile)

            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                self.existing_tiles[map_name][z_draw][key] = True
                continue

            # download is in progress
            if key in self.existing_tiles[map_name][z_draw]:
                continue

            # entry to download tiles
            self.existing_tiles[map_name][z_draw][key] = False
            download_tile.append(tile)

        # start downloading
        if len(download_tile):
            if not await self.config.network.download_maptile(
                map_config, map_name, z_draw, download_tile, additional_download=True
            ):
                # failed to put queue, then retry
                for tile in download_tile:
                    key = "{0}-{1}".format(*tile)
                    if key in self.existing_tiles[map_name][z_draw]:
                        self.existing_tiles[map_name][z_draw].pop(key)

    def check_drawn_tile(
        self, use_mbtiles, map_name, z, z_draw, z_conv_factor, tile_x, tile_y, expand
    ):
        draw_flag = False
        add_keys = {}
        expand_keys = {}

        if z not in self.drawn_tile[map_name] or self.pre_zoomlevel[map_name] != z:
            self.drawn_tile[map_name][z] = {}

        for i in range(tile_x[0], tile_x[1] + 1):
            for j in range(tile_y[0], tile_y[1] + 1):
                drawn_tile_key = "{0}-{1}".format(i, j)
                exist_tile_key = (i, j)
                pixel_x = x_start = pixel_y = y_start = 0
                if expand:
                    pixel_x, x_start = divmod(i, z_conv_factor)
                    pixel_y, y_start = divmod(j, z_conv_factor)
                    exist_tile_key = (pixel_x, pixel_y)

                if drawn_tile_key not in self.drawn_tile[map_name][
                    z
                ] and self.check_tile(use_mbtiles, map_name, z_draw, exist_tile_key):
                    self.drawn_tile[map_name][z][drawn_tile_key] = True
                    add_keys[(i, j)] = True
                    draw_flag = True
                    if expand:
                        expand_keys[(i, j)] = (pixel_x, pixel_y, x_start, y_start)

        return draw_flag, add_keys, expand_keys

    def check_tile(self, use_mbtiles, map_name, z_draw, key):
        cond = False
        if not use_mbtiles:
            exist_tile_key = "{0}-{1}".format(*key)  # (z_draw, i, j)
            if (exist_tile_key, True) in self.existing_tiles[map_name][z_draw].items():
                cond = True
        else:
            sql = (
                f"select count(*) from tiles where "
                f"zoom_level={z_draw} and tile_column={key[0]} and tile_row={2**z_draw - 1 - key[1]}"
            )
            if (self.cur.execute(sql).fetchone())[0] == 1:
                cond = True
        return cond

    def get_image_file(self, use_mbtiles, map_name, z_draw, x, y):
        if not use_mbtiles:
            img_file = get_maptile_filename(map_name, z_draw, x, y)
        else:
            sql = (
                f"select tile_data from tiles where "
                f"zoom_level={z_draw} and tile_column={x} and tile_row={2**z_draw - 1 - y}"
            )
            img_file = io.BytesIO((self.cur.execute(sql).fetchone())[0])
        return img_file

    def draw_scale(self, x_start, y_start):
        # draw scale at left bottom
        scale_factor = 10
        scale_dist = get_width_distance(y_start, self.map_area["w"]) / scale_factor
        num = scale_dist / (10 ** int(np.log10(scale_dist)))
        modify = 1
        if 1 < num < 2:
            modify = 2 / num
        elif 2 < num < 5:
            modify = 5 / num
        elif 5 < num < 10:
            modify = 10 / num
        scale_x1 = x_start + self.map_area["w"] / 25
        scale_x2 = scale_x1 + self.map_area["w"] / scale_factor * modify
        scale_y1 = y_start + self.map_area["h"] / 25
        scale_y2 = scale_y1 + self.map_area["h"] / 30
        scale_y1 = get_mod_lat(scale_y1)
        scale_y2 = get_mod_lat(scale_y2)
        self.scale_plot.setData(
            [scale_x1, scale_x1, scale_x2, scale_x2],
            [scale_y2, scale_y1, scale_y1, scale_y2],
        )

        scale_unit = "m"
        scale_label = round(scale_dist * modify)
        if scale_label >= 1000:
            scale_label = int(scale_label / 1000)
            scale_unit = "km"
        self.scale_text.setPlainText(f"{scale_label}{scale_unit}\n(z{self.zoomlevel})")
        self.scale_text.setPos((scale_x1 + scale_x2) / 2, scale_y2)

    def draw_map_attribution(self, x_start, y_start):
        # draw map attribution at right bottom
        self.map_attribution.setPos(x_start + self.map_area["w"], get_mod_lat(y_start))

    async def update_cuesheet_and_instruction(
        self, x_start, x_end, y_start, y_end, auto_zoom=False
    ):
        if (
            not self.course_points.is_set
            or not self.config.G_CUESHEET_DISPLAY_NUM
            or not self.config.G_COURSE_INDEXING
        ):
            return
        await self.cuesheet_widget.update_display()

        if self.instruction is not None:
            self.plot.removeItem(self.instruction)
        image_src = '<img src="img/navi_flag.png">'  # svg
        if self.cuesheet_widget.cuesheet[0].name.text() == "Right":
            image_src = '<img src="img/navi_turn_right.svg">'
        elif self.cuesheet_widget.cuesheet[0].name.text() == "Left":
            image_src = '<img src="img/navi_turn_left.svg">'
        elif self.cuesheet_widget.cuesheet[0].name.text() == "Summit":
            image_src = '<img src="img/summit.png">'  # svg
        self.instruction.setHtml(
            '<div style="text-align: left; vertical-align: bottom;">'
            + image_src
            + '<span style="font-size: 28px;">'
            + self.cuesheet_widget.cuesheet[0].dist.text()
            + "</span></div>"
        )
        self.instruction.setPos(
            (x_end + x_start) / 2,
            (get_mod_lat(y_start) + (get_mod_lat(y_end) - get_mod_lat(y_start)) * 0.85),
        )
        self.plot.addItem(self.instruction)

        if auto_zoom:
            delta = self.zoom_delta_from_tilesize
            # print(self.zoomlevel, self.cuesheet_widget.cuesheet[0].dist_num, self.auto_zoomlevel_back)
            if self.cuesheet_widget.cuesheet[0].dist_num < 1000:
                if (
                    self.auto_zoomlevel_back is None
                    and self.zoomlevel < self.auto_zoomlevel - delta
                ):
                    self.auto_zoomlevel_back = self.zoomlevel
                    self.zoomlevel = self.auto_zoomlevel - delta
                    # print("zoom in",  self.auto_zoomlevel_back, self.zoomlevel)
            else:
                if (
                    self.auto_zoomlevel_back is not None
                    and self.zoomlevel == self.auto_zoomlevel - delta
                ):
                    self.zoomlevel = self.auto_zoomlevel_back
                    # print("zoom out", self.auto_zoomlevel_back, self.zoomlevel)
                self.auto_zoomlevel_back = None

    def get_geo_area(self, x, y):
        if np.isnan(x) or np.isnan(y):
            return np.nan, np.nan
        tile_x, tile_y, _, _ = get_tilexy_and_xy_in_tile(
            self.zoomlevel,
            x,
            y,
            self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"],
        )
        pos_x0, pos_y0 = get_lon_lat_from_tile_xy(self.zoomlevel, tile_x, tile_y)
        pos_x1, pos_y1 = get_lon_lat_from_tile_xy(
            self.zoomlevel, tile_x + 1, tile_y + 1
        )
        return (
            abs(pos_x1 - pos_x0)
            / self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"]
            * (self.width() * self.map_cuesheet_ratio),
            abs(pos_y1 - pos_y0)
            / self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"]
            * self.height(),
        )

    def get_arrow_angle_index(self, angle):
        return (
            int(
                (angle + self.arrow_direction_angle_unit_half)
                / self.arrow_direction_angle_unit
            )
            % self.arrow_direction_num
        )
