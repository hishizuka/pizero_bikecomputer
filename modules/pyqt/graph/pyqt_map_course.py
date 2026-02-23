import asyncio

import numpy as np
from crdp import rdp

from modules.app_logger import app_logger
from modules._qt_qtwidgets import QtCore, QtWidgets, pg, qasync
from modules.helper.maptile import get_wind_color
from modules.pyqt.graph.pyqtgraph.CoursePlotItem import CoursePlotItem
from modules.pyqt.graph.pyqtgraph.WindVaneItem import WindVaneItem
from modules.utils.geo import get_mod_lat, get_mod_lat_np
from modules.utils.timer import Timer, log_timers


class MapCourseMixin:
    _COURSE_POINT_SYMBOLS = {"Left": "t3", "Right": "t2"}
    _INSTRUCTION_ICON_MAP = {
        "Right": '<img src="img/navi_turn_right_white.svg">',
        "Left": '<img src="img/navi_turn_left_white.svg">',
        "Summit": '<img src="img/summit.png">',
    }

    # tracks
    track_history_lon = []
    track_history_lat = []
    track_history_raw_lon = []
    track_history_raw_lat = []
    track_tail_lon = []
    track_tail_lat = []
    track_last_lon_pos = None
    track_last_lat_pos = None
    track_timestamp = None
    track_history_needs_redraw = True
    track_tail_needs_redraw = True
    track_tail_limit = 320
    track_history_rdp_interval = 900
    track_history_rdp_last_source_len = 0
    track_history_rdp_running = False
    track_history_rdp_task = None

    course_plot = None
    plot_verification = None
    course_points_plot = None
    course_winds = []

    instruction = None
    instruction_visible = False
    instruction_html_cache = None
    instruction_pos_cache = None
    instruction_anchor_x_ratio = 0.5
    instruction_anchor_y_ratio = 0.15

    def _setup_course_widgets(self):
        self.init_instruction()

    def _remove_plot_item(self, item):
        if item is not None:
            self.plot.removeItem(item)

    def _update_course_plot(self):
        self._remove_plot_item(self.course_plot)

        if not len(self.course.latitude):
            return False

        self.course_plot = CoursePlotItem(
            x=self.course.longitude,
            y=get_mod_lat_np(self.course.latitude),
            brushes=self.course.colored_altitude,
            width=7,
            outline_width=11,
            outline_color=(0, 0, 0, 160),
        )
        self.course_plot.setZValue(20)
        self.plot.addItem(self.course_plot)

        if self.config.G_IS_RASPI:
            return True

        self._remove_plot_item(self.plot_verification)
        self.plot_verification = pg.ScatterPlotItem(pxMode=True)
        self.plot_verification.setZValue(25)
        self.plot_verification.setData(
            [
                {
                    "pos": [
                        self.course.longitude[i],
                        get_mod_lat(self.course.latitude[i]),
                    ],
                    "size": 2,
                    "pen": {"color": "w", "width": 1},
                    "brush": pg.mkBrush(color=(255, 0, 0)),
                }
                for i in range(len(self.course.longitude))
            ]
        )
        self.plot.addItem(self.plot_verification)
        return True

    def _update_course_points_plot(self):
        self._remove_plot_item(self.course_points_plot)

        if not len(self.course_points.longitude):
            return False

        self.course_points_plot = pg.ScatterPlotItem(
            pxMode=True,
            symbol="t",
            size=12,
        )
        self.course_points_plot.setZValue(40)
        color = (255, 0, 0)
        self.course_points_plot.setData(
            [
                {
                    "pos": [
                        self.course_points.longitude[i],
                        get_mod_lat(self.course_points.latitude[i]),
                    ],
                    "pen": {"color": color, "width": 1},
                    "symbol": self._COURSE_POINT_SYMBOLS.get(
                        self.course_points.type[i], "t"
                    ),
                    "brush": pg.mkBrush(color=color),
                }
                for i in reversed(range(len(self.course_points.longitude)))
            ]
        )
        self.plot.addItem(self.course_points_plot)
        return True

    def load_course(self):
        timers = [
            Timer(auto_start=False, text="  course plot  : {0:.3f} sec"),
            Timer(auto_start=False, text="  course points: {0:.3f} sec"),
        ]

        has_course_plot = False
        with timers[0]:
            has_course_plot = self._update_course_plot()

        has_course_points = False
        with timers[1]:
            has_course_points = self._update_course_points_plot()

        self.add_course_wind()

        if has_course_plot and has_course_points:
            app_logger.info("Plotting course:")
            log_timers(timers, text_total=f"  total        : {0:.3f} sec")

    def add_course_wind(self):
        if not self.course.has_weather:
            return

        for course_wind in self.course_winds:
            self._remove_plot_item(course_wind)

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
            vane = WindVaneItem(
                angle=wd,
                brush=get_wind_color(ws),
                pen={"color": "k", "width": 2},
                size=42,
                offset_ratio=0.25,
            )
            vane.setPos(wc[0], get_mod_lat(wc[1]))
            vane.setZValue(35)
            self.course_winds.append(vane)
            self.plot.addItem(vane)

    def get_track(self):
        track_updated = False
        (self.track_timestamp, lon, lat) = self.logger.update_track(
            self.track_timestamp
        )
        if len(lon) and len(lat):
            lon_new = np.asarray(lon, dtype=np.float32)
            lat_new = np.asarray(lat, dtype=np.float32)
            self.track_last_lon_pos = float(lon_new[-1])
            self.track_last_lat_pos = float(lat_new[-1])
            self.track_tail_lon.extend(lon_new.tolist())
            self.track_tail_lat.extend(lat_new.tolist())
            track_updated = True
            self.track_tail_needs_redraw = True
            self._compact_track_tail()
            self._queue_track_history_rdp()

        return track_updated

    def _compact_track_tail(self):
        if len(self.track_tail_lon) <= self.track_tail_limit:
            return

        # Keep half of the tail window and move the older half into history.
        tail_keep = max(1, self.track_tail_limit // 2)
        move_count = len(self.track_tail_lon) - tail_keep
        if move_count <= 0:
            return

        moved_lon = self.track_tail_lon[:move_count]
        moved_lat = self.track_tail_lat[:move_count]
        del self.track_tail_lon[:move_count]
        del self.track_tail_lat[:move_count]

        self.track_history_raw_lon.extend(moved_lon)
        self.track_history_raw_lat.extend(moved_lat)
        # Reflect newly moved points immediately; background RDP will compact later.
        self.track_history_lon.extend(moved_lon)
        self.track_history_lat.extend(moved_lat)
        self.track_history_needs_redraw = True
        self.track_tail_needs_redraw = True

    def _queue_track_history_rdp(self):
        raw_len = len(self.track_history_raw_lon)
        # Start RDP after raw history reaches half of the interval threshold.
        rdp_min_points = max(3, self.track_history_rdp_interval // 2)
        if raw_len < rdp_min_points:
            return
        if self.track_history_rdp_running:
            return
        if (
            raw_len - self.track_history_rdp_last_source_len
            < self.track_history_rdp_interval
        ):
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        source_len = raw_len
        raw_lon = np.asarray(self.track_history_raw_lon, dtype=np.float32)
        raw_lat = np.asarray(self.track_history_raw_lat, dtype=np.float32)
        self.track_history_rdp_last_source_len = source_len
        self.track_history_rdp_running = True
        self.track_history_rdp_task = loop.create_task(
            self._run_track_history_rdp(raw_lon, raw_lat, source_len)
        )

    async def _run_track_history_rdp(self, raw_lon, raw_lat, source_len):
        def simplify_track(lon_values, lat_values):
            if len(lon_values) < 3:
                return lon_values.tolist(), lat_values.tolist()
            try:
                cond = np.array(
                    rdp(
                        np.column_stack([lon_values, lat_values]),
                        epsilon=0.0001,
                        return_mask=True,
                    )
                )
                return lon_values[cond].tolist(), lat_values[cond].tolist()
            except Exception:
                return lon_values.tolist(), lat_values.tolist()

        try:
            simplified_lon, simplified_lat = await asyncio.to_thread(
                simplify_track,
                raw_lon,
                raw_lat,
            )
            if source_len < len(self.track_history_raw_lon):
                simplified_lon.extend(self.track_history_raw_lon[source_len:])
                simplified_lat.extend(self.track_history_raw_lat[source_len:])
            # Keep history source compact for subsequent async RDP passes.
            self.track_history_raw_lon = simplified_lon.copy()
            self.track_history_raw_lat = simplified_lat.copy()
            self.track_history_lon = simplified_lon
            self.track_history_lat = simplified_lat
            self.track_history_needs_redraw = True
            self.track_history_rdp_last_source_len = len(self.track_history_raw_lon)
        except asyncio.CancelledError:
            raise
        finally:
            self.track_history_rdp_running = False
            self.track_history_rdp_task = None

    def reset_track(self):
        if (
            self.track_history_rdp_task is not None
            and not self.track_history_rdp_task.done()
        ):
            self.track_history_rdp_task.cancel()

        for attr_name, value in (
            ("track_history_lon", []),
            ("track_history_lat", []),
            ("track_history_raw_lon", []),
            ("track_history_raw_lat", []),
            ("track_tail_lon", []),
            ("track_tail_lat", []),
            ("track_last_lon_pos", None),
            ("track_last_lat_pos", None),
        ):
            setattr(self, attr_name, value)
        self.track_history_needs_redraw = True
        self.track_tail_needs_redraw = True
        self.track_history_rdp_running = False
        self.track_history_rdp_task = None
        self.track_history_rdp_last_source_len = 0

        if getattr(self, "track_history_plot", None) is not None:
            self.track_history_plot.setData([], [])
        if getattr(self, "track_tail_plot", None) is not None:
            self.track_tail_plot.setData([], [])

    def reset_course(self):
        self._hide_instruction()
        if self.instruction is not None:
            self.instruction.deleteLater()
        self.instruction = None
        for plot_item in [
            self.course_plot,
            self.plot_verification,
            self.course_points_plot,
        ]:
            self._remove_plot_item(plot_item)
        for course_wind in self.course_winds:
            self._remove_plot_item(course_wind)

    def init_course(self):
        self.init_instruction()
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

    async def update_instruction(self, *_view_bounds, auto_zoom=False):
        if (
            not self.course_points.is_set
            or not self.config.G_COURSE_INDEXING
        ):
            self._hide_instruction()
            return

        instruction_name, instruction_distance = self._get_instruction_data()
        if instruction_distance is None:
            self._hide_instruction()
            return

        if self.instruction is None:
            self._create_instruction_item()

        image_src = self._INSTRUCTION_ICON_MAP.get(
            instruction_name,
            '<img src="img/navi_flag_white.svg">',
        )

        if instruction_distance > 1000:
            instruction_distance_text = f"{instruction_distance / 1000:4.1f}km "
        else:
            instruction_distance_text = f"{instruction_distance:6.0f}m  "

        instruction_html = (
            '<div style="text-align: left; vertical-align: bottom;">'
            + image_src
            + '<span style="font-size: 28px;">'
            + instruction_distance_text
            + "</span></div>"
        )

        if instruction_html != self.instruction_html_cache:
            self.instruction.setText(instruction_html)
            self.instruction.adjustSize()
            self.instruction_html_cache = instruction_html
            self.instruction_pos_cache = None

        if not self.instruction_visible:
            self.instruction.show()
            self.instruction_visible = True
            self.instruction_pos_cache = None

        self._relayout_fixed_instruction()

        if auto_zoom:
            delta = self.zoom_delta_from_tilesize
            if instruction_distance < 1000:
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

    def _get_instruction_data(self):
        cp_i = int(getattr(self.course.index, "course_points_index", 0))
        cp_i = max(0, cp_i)

        point_distances = self.course_points.distance
        point_names = self.course_points.type

        if cp_i >= len(point_distances):
            return "", None

        current_distance = float(getattr(self.course.index, "distance", 0.0))
        for i in range(cp_i, len(point_distances)):
            dist_m = float(point_distances[i]) * 1000 - current_distance
            if dist_m < 0:
                continue
            name = str(point_names[i]) if i < len(point_names) else ""
            return name, dist_m

        return "", None

    def init_instruction(self):
        if (
            self.config.logger.course.course_points.is_set
            and self.config.G_COURSE_INDEXING
        ):
            if self.instruction is None:
                self._create_instruction_item()
        else:
            self._hide_instruction()
            if self.instruction is not None:
                self.instruction.deleteLater()
            self.instruction = None

    def _create_instruction_item(self):
        parent = getattr(self, "_fixed_hud_overlay", None)
        if parent is None:
            parent = self.plot

        self.instruction = QtWidgets.QLabel(parent)
        self.instruction.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.instruction.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self.instruction.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.instruction.setWordWrap(False)
        self.instruction.setMargin(0)
        self.instruction.setContentsMargins(0, 0, 0, 0)
        self.instruction.setStyleSheet(
            "QLabel {"
            "color: #FFFFFF;"
            "background-color: rgba(0, 128, 0, 255);"
            "border: 1px solid #000000;"
            "border-radius: 10px;"
            "padding: 0px;"
            "}"
        )
        self.instruction.hide()
        self.instruction_visible = False
        self.instruction_html_cache = None
        self.instruction_pos_cache = None

    def _hide_instruction(self):
        if self.instruction is not None and self.instruction_visible:
            self.instruction.hide()
        self.instruction_visible = False
        self.instruction_html_cache = None
        self.instruction_pos_cache = None

    def _relayout_fixed_instruction(self, force=False):
        if self.instruction is None or not self.instruction_visible:
            return

        parent = self.instruction.parentWidget()
        if parent is None:
            return

        center_x = parent.width() * self.instruction_anchor_x_ratio
        center_y = parent.height() * self.instruction_anchor_y_ratio
        x_pos = int(round(center_x - self.instruction.width() / 2))
        y_pos = int(round(center_y - self.instruction.height() / 2))
        x_pos = max(0, min(x_pos, max(0, parent.width() - self.instruction.width())))
        y_pos = max(0, min(y_pos, max(0, parent.height() - self.instruction.height())))
        pos_key = (x_pos, y_pos, parent.width(), parent.height())
        if force or pos_key != self.instruction_pos_cache:
            self.instruction.move(x_pos, y_pos)
            self.instruction_pos_cache = pos_key
