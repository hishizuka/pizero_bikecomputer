import numpy as np

from modules.app_logger import app_logger
from modules._qt_qtwidgets import pg, qasync
from modules.helper.maptile import get_wind_color
from modules.pyqt.graph.pyqtgraph.CoursePlotItem import CoursePlotItem
from modules.pyqt.pyqt_cuesheet_widget import CueSheetWidget
from modules.utils.geo import get_mod_lat, get_mod_lat_np
from modules.utils.timer import Timer, log_timers


class MapCourseMixin:
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
    map_cuesheet_ratio = 1  # map:cuesheet = 1:0

    def _setup_course_widgets(self):
        self.init_cuesheet_and_instruction()

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

                if not self.config.G_IS_RASPI:
                    if self.plot_verification is not None:
                        self.plot.removeItem(self.plot_verification)
                    self.plot_verification = pg.ScatterPlotItem(pxMode=True)
                    self.plot_verification.setZValue(25)
                    test_points = []
                    for i in range(len(self.course.longitude)):
                        point = {
                            "pos": [
                                self.course.longitude[i],
                                get_mod_lat(self.course.latitude[i]),
                            ],
                            "size": 2,
                            "pen": {"color": "w", "width": 1},
                            "brush": pg.mkBrush(color=(255, 0, 0)),
                        }
                        test_points.append(point)
                    self.plot_verification.setData(test_points)
                    self.plot.addItem(self.plot_verification)

        with timers[1]:
            if self.course_points_plot is not None:
                self.plot.removeItem(self.course_points_plot)

            if not len(self.course_points.longitude):
                disable_print_timers |= True
            else:
                self.course_points_plot = pg.ScatterPlotItem(
                    pxMode=True,
                    symbol="t",
                    size=12,
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
                    course_point = {
                        "pos": [
                            self.course_points.longitude[i],
                            get_mod_lat(self.course_points.latitude[i]),
                        ],
                        "pen": {"color": color, "width": 1},
                        "symbol": symbol,
                        "brush": pg.mkBrush(color=color),
                    }
                    formatted_course_points.append(course_point)
                self.course_points_plot.setData(formatted_course_points)
                self.plot.addItem(self.course_points_plot)

        self.add_course_wind()

        if not disable_print_timers:
            app_logger.info("Plotting course:")
            log_timers(timers, text_total=f"  total        : {0:.3f} sec")

    def add_course_wind(self):
        if not self.course.has_weather:
            return

        for course_wind in self.course_winds:
            self.plot.removeItem(course_wind)

        self.course_winds = []
        for wc, wd, ws in zip(
            self.course.wind_coordinates,
            self.course.wind_direction,
            self.course.wind_speed,
        ):
            if ws is None or wd is None:
                continue
            if np.isnan(ws) or np.isnan(wd):
                continue
            arrow = pg.ArrowItem(
                angle=wd - 90,
                tipAngle=60,
                baseAngle=30,
                headLen=20,
                tailLen=20,
                tailWidth=6,
                pen={"color": "k", "width": 2},
                brush=get_wind_color(ws),
            )
            arrow.setPos(wc[0], get_mod_lat(wc[1]))
            self.course_winds.append(arrow)
            self.plot.addItem(arrow)

    def get_track(self):
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
        for plot_item in [
            self.course_plot,
            self.plot_verification,
            self.course_points_plot,
            self.instruction,
        ]:
            if plot_item is not None:
                self.plot.removeItem(plot_item)
        for course_wind in self.course_winds:
            self.plot.removeItem(course_wind)

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
            image_src = '<img src="img/summit.png">'
        self.instruction.setHtml(
            '<div style="text-align: left; vertical-align: bottom;">'
            + image_src
            + '<span style="font-size: 28px;">'
            + self.cuesheet_widget.cuesheet[0].dist.text()
            + "</span></div>"
        )
        self.instruction.setPos(
            (x_end + x_start) / 2,
            get_mod_lat(y_start)
            + (get_mod_lat(y_end) - get_mod_lat(y_start)) * 0.85,
        )
        self.plot.addItem(self.instruction)

        if auto_zoom:
            delta = self.zoom_delta_from_tilesize
            if self.cuesheet_widget.cuesheet[0].dist_num < 1000:
                if (
                    self.auto_zoomlevel_back is None
                    and self.zoomlevel < self.auto_zoomlevel - delta
                ):
                    self.auto_zoomlevel_back = self.zoomlevel
                    self.zoomlevel = self.auto_zoomlevel - delta
            else:
                if (
                    self.auto_zoomlevel_back is not None
                    and self.zoomlevel == self.auto_zoomlevel - delta
                ):
                    self.zoomlevel = self.auto_zoomlevel_back
                self.auto_zoomlevel_back = None

    def init_cuesheet_and_instruction(self):
        if (
            self.config.logger.course.course_points.is_set
            and self.config.G_CUESHEET_DISPLAY_NUM
            and self.config.G_COURSE_INDEXING
        ):
            if self.cuesheet_widget is None:
                self.cuesheet_widget = CueSheetWidget(self, self.config)
                self.cuesheet_widget.hide()

            self.map_cuesheet_ratio = 1.0

            self.instruction = pg.TextItem(
                color=(255, 255, 255),
                fill=(0, 128, 0),
                anchor=(0.5, 0.5),
                border=(0, 0, 0),
            )
            self.instruction.setZValue(100)
