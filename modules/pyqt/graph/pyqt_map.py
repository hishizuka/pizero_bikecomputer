import io
import sqlite3
from datetime import datetime, timezone
import shutil
import tempfile

import numpy as np
from PIL import Image, ImageEnhance

from modules.app_logger import app_logger
from modules._qt_qtwidgets import QT_COMPOSITION_MODE_DARKEN, pg, qasync, Signal
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
)
from modules.utils.timer import Timer, log_timers
from modules.utils.cmd import exec_cmd
from modules.utils.asyncio import run_after
from .pyqt_base_map import BaseMapWidget
from .pyqt_map_button import (
    DirectionButton,
    MapLayersButton,
    MapNextButton,
    MapPrevButton,
)
from modules.helper.maptile import (
    conv_image,
    get_wind_color,
)


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
    course_winds = []
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
    map_cuesheet_ratio = 1  # map:cuesheet = 1:0

    zoom_delta_from_tilesize = 0
    auto_zoomlevel = None
    auto_zoomlevel_diff = 2  # auto_zoomlevel = zoomlevel + auto_zoomlevel_diff
    auto_zoomlevel_back = None

    # signal for physical button
    signal_search_route = Signal()

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

    overlay_time = {
        "RAIN": {
            "display_time": None,
            "prev_time": None,
            "next_time": None,
        },
        "WIND": {
            "display_time": None,
            "prev_time": None,
            "next_time": None,
            "prev_subdomain": None,  # for jpn_scw
            "next_subdomain": None,  # for jpn_scw
        },
    }
    overlay_order = ["NONE", "WIND", "RAIN", "HEATMAP"]
    overlay_order_index = {
        "WIND": 1,
        "RAIN": 2,
        "HEATMAP": 3,
    }
    overlay_index = 0

    tile_modify_mode = 0
    tile_didder_pallete = {
        2: "000000 FFFFFF",
        8: None,
        64: None,
        #64: "000000 FF0000 00FF00 0000FF 00FFFF FF00FF FFFF00 FFFFFF",
    }
    scale_lat_round = 2

    @property
    def maptile_with_values(self):
        return self.config.api.maptile_with_values

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
        self.plot.addItem(self.current_point)

        self._last_attribution_text = None
        self._last_scale_key = None

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
        self.plot.addItem(self.center_point)

        # connect signal
        self.signal_search_route.connect(self.search_route)

        self.reset_map()

        # self.load_course()
        t = datetime.now(timezone.utc)
        self.get_track()  # heavy when resume
        if len(self.tracks_lon):
            app_logger.info(
                f"resume_track(init): {(datetime.now(timezone.utc) - t).total_seconds():.3f} sec"
            )

        # map
        max_height = 4
        if self.config.display.has_touch and self.config.G_GOOGLE_DIRECTION_API["HAVE_API_TOKEN"]:
            max_height += 1
        self.layout.addWidget(self.plot, 0, 0, max_height, 3)

        if self.config.display.has_touch:
            # zoom
            self.layout.addWidget(self.buttons["zoomdown"], 0, 0)
            self.layout.addWidget(self.buttons["lock"], 1, 0)
            self.layout.addWidget(self.buttons["zoomup"], 2, 0)
            # arrow
            self.layout.addWidget(self.buttons["left"], 0, 4)
            self.layout.addWidget(self.buttons["up"], 1, 4)
            self.layout.addWidget(self.buttons["down"], 2, 4)
            self.layout.addWidget(self.buttons["right"], 3, 4)
            
            if self.config.G_GOOGLE_DIRECTION_API["HAVE_API_TOKEN"]:
                self.buttons["go"] = DirectionButton()
                self.layout.addWidget(self.buttons["go"], max_height-2, 0)
                self.buttons["go"].clicked.connect(self.search_route)

            self.buttons["layers"] = MapLayersButton()
            self.layout.addWidget(self.buttons["layers"], max_height-1, 0)
            self.buttons["layers"].clicked.connect(self.change_map_overlays)
            self.enable_overlay_button()

            # for time series of overlay map tiles
            self.buttons["prev_time"] = MapPrevButton()
            self.buttons["next_time"] = MapNextButton()
            self.layout.addWidget(self.buttons["prev_time"], max_height-1, 2)
            self.layout.addWidget(self.buttons["next_time"], max_height-1, 4)
            self.buttons["prev_time"].clicked.connect(lambda: self.update_overlay_time(False))
            self.buttons["next_time"].clicked.connect(lambda: self.update_overlay_time(True))
            self.enable_overlay_time_and_button()

        # cue sheet and instruction
        self.init_cuesheet_and_instruction()

        # for expanding column
        self.layout.setColumnMinimumWidth(0, 40)
        self.layout.setColumnStretch(1, 1)
        self.layout.setColumnMinimumWidth(2, 40)
        self.layout.setColumnMinimumWidth(3, 5)
        self.layout.setColumnMinimumWidth(4, 40)

        def palette_rgb_multilevel(levels=2):
            if levels < 2:
                return

            # Evenly spaced step values from 0 to 255 (e.g., 2 levels → [0,255], 4 levels → [0,85,170,255])
            vals = [round(i * 255 / (levels - 1)) for i in range(levels)]

            def hex2(v: int) -> str:
                return f"{v:02X}"

            colors = []
            for r in vals:
                for g in vals:
                    for b in vals:
                        colors.append(f"{hex2(r)}{hex2(g)}{hex2(b)}")

            return " ".join(colors)

        if shutil.which("didder"):
            self.tile_didder_pallete[8] = palette_rgb_multilevel(2)
            self.tile_didder_pallete[64] = palette_rgb_multilevel(4)

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
            self.pre_zoomlevel[key] = np.nan

        self.set_attribution()

    def set_attribution(self):

        attribution_text = self.config.G_MAP_CONFIG[self.config.G_MAP]["attribution"]
        map_settings = None
        if self.overlay_index == self.overlay_order_index["HEATMAP"]:
            map_settings = self.config.G_HEATMAP_OVERLAY_MAP_CONFIG[self.config.G_HEATMAP_OVERLAY_MAP]
        elif self.overlay_index == self.overlay_order_index["RAIN"]:
            map_settings = self.config.G_RAIN_OVERLAY_MAP_CONFIG[self.config.G_RAIN_OVERLAY_MAP]
        elif self.overlay_index == self.overlay_order_index["WIND"]:
            map_settings = self.config.G_WIND_OVERLAY_MAP_CONFIG[self.config.G_WIND_OVERLAY_MAP]
        if map_settings is not None:
            split_char = " / " if self.config.gui.horizontal else "<br />"
            attribution_text += f"{split_char}{map_settings['attribution']}"
            b, v = self.add_attribution_extra_text(map_settings)
            if b != "" and v != "":
                attribution_text += f" ({b}/{v})"

        if attribution_text != self._last_attribution_text:
            self.map_attribution.setHtml(
                '<span style="color: #000000; font-size: small;">'
                + attribution_text
                + "</span>"
            )
            self._last_attribution_text = attribution_text

        if attribution_text == "":
            self.map_attribution.setZValue(-100)
        else:
            self.map_attribution.setZValue(100)

    def add_attribution_extra_text(self, map_settings):
        basetime_str = validtime_str = ""
        if self.overlay_index == self.overlay_order_index["RAIN"]:
            if self.config.G_RAIN_OVERLAY_MAP == "jpn_jma_bousai" and map_settings['basetime'] is not None:
                basetime_str = map_settings['basetime'][-6:]
                validtime_str = map_settings['validtime'][-6:]
        elif self.overlay_index == self.overlay_order_index["WIND"]:
            if self.config.G_WIND_OVERLAY_MAP.startswith("jpn_scw") and map_settings['basetime'] is not None:
                basetime_str = map_settings['basetime'][:4]
                validtime_str = map_settings['validtime'][:4]
        return basetime_str, validtime_str

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
                # color=(0, 0, 0),
                # fill=(255, 255, 255, 192),
                color=(255, 255, 255),
                fill=(0, 128, 0),
                anchor=(0.5, 0.5),
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
            Timer(auto_start=False, text="  course plot  : {0:.3f} sec"),
            Timer(auto_start=False, text="  course points: {0:.3f} sec"),
        ]

        disable_print_timers = False
        with timers[0]:
            if self.course_plot is not None:
                self.plot.removeItem(self.course_plot)

            if not len(self.course.latitude):
                disable_print_timers |= True
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
                disable_print_timers |= True
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

        self.add_course_wind()

        if not disable_print_timers:
            app_logger.info("Plotting course:")
            log_timers(timers, text_total=f"  total        : {0:.3f} sec")

    def add_course_wind(self):
        if not self.course.has_weather:
            return

        for cs in self.course_winds:
            self.plot.removeItem(cs)

        self.course_winds = []
        for wc, wd, ws in zip(self.course.wind_coordinates, self.course.wind_direction, self.course.wind_speed):
            arrow = pg.ArrowItem(
                angle=wd-90,
                tipAngle=60,
                baseAngle=30,
                headLen=20,
                tailLen=20,
                tailWidth=6,
                pen={'color': 'k', 'width': 2},
                brush=get_wind_color(ws)
            )
            arrow.setPos(wc[0], get_mod_lat(wc[1]))
            self.course_winds.append(arrow)
            self.plot.addItem(arrow)

    @qasync.asyncSlot(int, int)
    async def on_drag_ended(self, dx, dy):
        w, h = self.get_geo_area(self.map_pos["x"], self.map_pos["y"])

        widget_width = self.plot.width()
        widget_height = self.plot.height()

        if widget_width == 0 or widget_height == 0:
            return

        dlon = (dx / widget_width) * w
        dlat = (dy / widget_height) * h

        dlat = -dlat

        self.map_pos["x"] -= dlon
        self.map_pos["y"] -= dlat

        await self.update_display()

        self.timer.start()

    @qasync.asyncSlot()
    async def update_display(self):

        # display current position
        if len(self.location):
            self.location.clear()
        # display center point
        if len(self.center_point_location):
            self.center_point_location.clear()

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
        else:
            self.center_point.setData([])

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
        for cs in self.course_winds:
            self.plot.removeItem(cs) 

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

        self.config.logger.reset_course(delete_course_file=True, replace=False)
        await self.course.search_route(
            self.point["pos"][0],
            self.point["pos"][1] / self.y_mod,
            self.map_pos["x"],
            self.map_pos["y"],
        )
        self.init_course()

    async def update_prev_next_overlay_time(self, overlay_type, map_config, map_name):
        p_vt, p_sd, n_vt, n_sd = await self.maptile_with_values.get_prev_next_validtime(
            overlay_type, map_config, map_name
        )

        # update overlay_time
        self.overlay_time[overlay_type]["prev_time"] = p_vt
        self.overlay_time[overlay_type]["next_time"] = n_vt
        if map_name.startswith("jpn_scw"):
            self.overlay_time[overlay_type]["prev_subdomain"] = p_sd
            self.overlay_time[overlay_type]["next_subdomain"] = n_sd
        
        # update button status
        if self.config.display.has_touch:
            for key in ("prev_time", "next_time"):
                self.buttons[key].setEnabled(self.overlay_time[overlay_type][key] is not None)

    @qasync.asyncSlot()
    async def update_overlay_time(self, goto_next=True):
        overlay_type = self.overlay_order[self.overlay_index]
        if overlay_type not in ["WIND", "RAIN"]:
            return
        
        map_config = getattr(self.config, f"G_{overlay_type}_OVERLAY_MAP_CONFIG")
        map_name = getattr(self.config, f"G_{overlay_type}_OVERLAY_MAP")
        map_settings = map_config[map_name]

        time = "next_time" if goto_next else "prev_time"
        sd = "next_subdomain" if goto_next else "prev_subdomain"
        time_value = self.overlay_time[overlay_type].get(time)

        if time_value is not None:
            map_settings["validtime"] = time_value
            if map_name.startswith("jpn_scw"):
                map_settings["subdomain"] = self.overlay_time[overlay_type].get(sd)
            elif map_name.startswith("jpn_jma_bousai"):
                vt = datetime.strptime(map_settings["validtime"], map_settings["time_format"])
                ct = map_settings["current_time"]
                if vt < ct:
                    map_settings["basetime"] = map_settings["validtime"]
                else:
                    map_settings["basetime"] = ct.strftime(map_settings["time_format"])
            self.update_display()  # or await self.overlay_map(False, p0, p1, map_config, map_name)
            await self.update_prev_next_overlay_time(overlay_type, map_config, map_name)

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
            use_mbtiles=self.config.G_MAP_CONFIG[self.config.G_MAP].get("use_mbtiles"),
        )

        if self.overlay_index == self.overlay_order_index["HEATMAP"]:
            await self.overlay_heatmap(drawn_main_map, p0, p1)
        elif self.overlay_index == self.overlay_order_index["RAIN"]:
            await self.overlay_rainmap(drawn_main_map, p0, p1)
        elif self.overlay_index == self.overlay_order_index["WIND"]:
            await self.overlay_windmap(drawn_main_map, p0, p1)

    async def overlay_heatmap(self, drawn_main_map, p0, p1):
        await self.overlay_map(
            drawn_main_map,
            p0,
            p1,
            self.config.G_HEATMAP_OVERLAY_MAP_CONFIG,
            self.config.G_HEATMAP_OVERLAY_MAP,
        )

    async def overlay_rainmap(self, drawn_main_map, p0, p1):
        await self.overlay_map_internal(
            overlay_type="RAIN",
            drawn_main_map=drawn_main_map,
            p0=p0,
            p1=p1,
            update_func=self.maptile_with_values.update_overlay_rainmap_timeline,
        )

    async def overlay_windmap(self, drawn_main_map, p0, p1):
        updated = await self.overlay_map_internal(
            overlay_type="WIND",
            drawn_main_map=drawn_main_map,
            p0=p0,
            p1=p1,
            update_func=self.maptile_with_values.update_overlay_windmap_timeline,
        )
        if updated:
            run_after(
                a_func=self.course.get_course_wind,
                b_func=self.add_course_wind,
            )

    async def overlay_map_internal(self, overlay_type, drawn_main_map, p0, p1, update_func) -> bool:
        """
        Update overlay tiles' timeline and return whether this was a *change after initialization*.

        Returns
        -------
        bool
            True  : display_time changed from a previous value (i.e., not the very first set).
            False : no change, or this was the initial set (prev was None).
        """

        # Resolve map config/name once
        map_config = getattr(self.config, f"G_{overlay_type}_OVERLAY_MAP_CONFIG")
        map_name = getattr(self.config, f"G_{overlay_type}_OVERLAY_MAP")
        map_settings = map_config[map_name]

        # Let the timeline updater modify basetime/validtime for the current overlay map
        await update_func(map_settings, map_name)

        # Compute new/prev display_time
        new_display_time = f"{map_settings['basetime']}/{map_settings['validtime']}"
        prev_display_time = self.overlay_time[overlay_type]["display_time"]

        # If unchanged, just draw overlay and exit
        if prev_display_time == new_display_time:
            await self.overlay_map(drawn_main_map, p0, p1, map_config, map_name)
            return False

        # Changed: record and reset tiles
        self.overlay_time[overlay_type]["display_time"] = new_display_time
        self.reset_overlay(map_name)

        # Return True only if this is not the very first time (prev was already set)
        return prev_display_time is not None

    def reset_overlay(self, map_name):
        # clear tile because overlay map changes over time
        self.drawn_tile[self.config.G_MAP] = {}
        self.drawn_tile[map_name] = {}
        self.pre_zoomlevel[map_name] = np.nan
        self.set_attribution()

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
            await self.maptile_with_values.download_maptiles(tiles, map_config, map_name, z_draw, additional_download=True)

        # tile check
        if use_mbtiles:
            self.con = sqlite3.connect(
                f"file:./maptile/{map_name}.mbtiles?mode=ro", uri=True
            )
            self.cur = self.con.cursor()

        draw_flag, add_keys, expand_keys = self.check_drawn_tile(
            use_mbtiles, map_config, map_name, z, z_draw, z_conv_factor, tile_x, tile_y, expand
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
            img_file = self.get_image_file(use_mbtiles, map_config, map_name, z_draw, x, y)
            if not expand:
                img_pil = Image.open(img_file).convert("RGBA")
            else:
                x_start, y_start = int(w_h * expand_keys[keys][2]), int(
                    w_h * expand_keys[keys][3]
                )
                img_pil = Image.open(img_file).crop((
                    x_start, y_start, x_start + w_h, y_start + w_h
                )).convert("RGBA")

            if (
                map_config == self.config.G_MAP_CONFIG
                and self.tile_modify_mode != 0
            ):
                img_pil = self.enhance_image(img_pil)

            if map_name.startswith(("jpn_scw", "jpn_jma_bousai")):
                imgarray = conv_image(img_pil, map_name)
            else:
                imgarray = np.asarray(img_pil)
            imgarray = np.rot90(imgarray, -1)

            imgitem = pg.ImageItem(imgarray, levels=(0,255))
            if overlay:
                imgitem.setCompositionMode(QT_COMPOSITION_MODE_DARKEN)
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

    def check_drawn_tile(
        self, use_mbtiles, map_config, map_name, z, z_draw, z_conv_factor, tile_x, tile_y, expand
    ):
        draw_flag = False
        add_keys = {}
        expand_keys = {}
        basetime = map_config[map_name].get("basetime", None)
        validtime = map_config[map_name].get("validtime", None)

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

                if (
                    drawn_tile_key not in self.drawn_tile[map_name][z] 
                    and self.check_tile(
                        use_mbtiles, map_name, z_draw, exist_tile_key, basetime, validtime
                    )
                ):
                    self.drawn_tile[map_name][z][drawn_tile_key] = True
                    add_keys[(i, j)] = True
                    draw_flag = True
                    if expand:
                        expand_keys[(i, j)] = (pixel_x, pixel_y, x_start, y_start)

        return draw_flag, add_keys, expand_keys

    def check_tile(self, use_mbtiles, map_name, z_draw, key, basetime, validtime):
        if not use_mbtiles:
            filename = get_maptile_filename(
                map_name, z_draw, *key, basetime=basetime, validtime=validtime
            )
            return self.maptile_with_values.check_existing_tiles(filename)
        else:
            sql = (
                f"select count(*) from tiles where "
                f"zoom_level={z_draw} and tile_column={key[0]} and tile_row={2**z_draw - 1 - key[1]}"
            )
            return (self.cur.execute(sql).fetchone())[0] == 1

    def get_image_file(self, use_mbtiles, map_config, map_name, z_draw, x, y):
        if not use_mbtiles:
            basetime = map_config[map_name].get("basetime", None)
            validtime = map_config[map_name].get("validtime", None)
            img_file = get_maptile_filename(
                map_name, z_draw, x, y, basetime=basetime, validtime=validtime
            )
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
        lat_key = self.map_pos["y"]
        if np.isnan(lat_key):
            lat_key = y_start
        if np.isnan(lat_key):
            lat_key = None
        else:
            lat_key = round(lat_key, self.scale_lat_round)
        scale_key = (self.zoomlevel, lat_key)
        if self._last_scale_key != scale_key:
            self.scale_text.setPlainText(
                f"{scale_label}{scale_unit}\n(z{self.zoomlevel})"
            )
            self._last_scale_key = scale_key
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
        image_src = '<img src="img/navi_flag_white.svg">'
        if self.cuesheet_widget.cuesheet[0].name.text() == "Right":
            image_src = '<img src="img/navi_turn_right_white.svg">'
        elif self.cuesheet_widget.cuesheet[0].name.text() == "Left":
            image_src = '<img src="img/navi_turn_left_white.svg">'
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

        tile_size = self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"]

        tile_x, tile_y, _, _ = get_tilexy_and_xy_in_tile(
            self.zoomlevel,
            x,
            y,
            tile_size,
        )
        pos_x0, pos_y0 = get_lon_lat_from_tile_xy(self.zoomlevel, tile_x, tile_y)
        pos_x1, pos_y1 = get_lon_lat_from_tile_xy(
            self.zoomlevel, tile_x + 1, tile_y + 1
        )
        return (
            abs(pos_x1 - pos_x0) / tile_size * (self.width() * self.map_cuesheet_ratio),
            abs(pos_y1 - pos_y0) / tile_size * self.height(),
        )

    def get_arrow_angle_index(self, angle):
        return (
            int(
                (angle + self.arrow_direction_angle_unit_half)
                / self.arrow_direction_angle_unit
            )
            % self.arrow_direction_num
        )
    
    def change_map_overlays(self):
        while self.overlay_index < len(self.overlay_order):
            self.overlay_index += 1

            if self.overlay_index == len(self.overlay_order):
                self.overlay_index = 0
                break
            
            m = self.overlay_order[self.overlay_index]
            if (
                (m == "WIND" and self.config.G_USE_WIND_OVERLAY_MAP)
                or (m == "RAIN" and self.config.G_USE_RAIN_OVERLAY_MAP)
                or (m == "HEATMAP" and self.config.G_USE_HEATMAP_OVERLAY_MAP)
            ):
                break

        self.reset_map()
        self.enable_overlay_time_and_button()
        self.update_display()
    
    def remove_overlay(self):
        if self.overlay_index != 0:
            self.overlay_index = 0
            self.reset_map()
    
    def enable_overlay_button(self):
        if (
            not self.config.G_USE_HEATMAP_OVERLAY_MAP
            and not self.config.G_USE_RAIN_OVERLAY_MAP
            and not self.config.G_USE_WIND_OVERLAY_MAP
        ):
            self.buttons["layers"].setEnabled(False)
        else:
            self.buttons["layers"].setEnabled(True)

    def modify_map_tile(self):
        if self.tile_modify_mode == 3:
            self.tile_modify_mode = 0
        else:
            self.tile_modify_mode += 1
        self.config.display.screen_flash_short()
        self.reset_map()

    @qasync.asyncSlot()
    async def enable_overlay_time_and_button(self):
        overlay_type = self.overlay_order[self.overlay_index]

        if overlay_type in ("WIND", "RAIN"):
            map_config = getattr(self.config, f"G_{overlay_type}_OVERLAY_MAP_CONFIG")
            map_name = getattr(self.config, f"G_{overlay_type}_OVERLAY_MAP")
            await self.update_prev_next_overlay_time(overlay_type, map_config, map_name)

        enabled = overlay_type in ("WIND", "RAIN")
        if self.config.display.has_touch:
            self.buttons["prev_time"].setVisible(enabled)
            self.buttons["next_time"].setVisible(enabled)

    def enhance_image(self, img_pil):
        # 0: None
        # 1: pil
        # 2: didder
        # 3: pil + didder

        if self.tile_modify_mode in [1, 3]:
            img_pil = ImageEnhance.Contrast(img_pil).enhance(2.0)

        with tempfile.NamedTemporaryFile(suffix=".png") as tmp_file:
            filename = tmp_file.name

            if self.tile_modify_mode in [2, 3] and shutil.which("didder"):
                img_pil.save(filename)
                exec_cmd(
                    [
                        "didder",
                        "-i", filename,
                        "-o", filename,
                        "--strength", "0.8",
                        "--palette", self.tile_didder_pallete[self.config.display.color],
                        "edm", "--serpentine", "FloydSteinberg"
                    ],
                    cmd_print=False
                )
                img_pil = Image.open(filename).convert("RGBA")
            
        return img_pil
