import numpy as np

from modules.app_logger import app_logger
from modules._qt_qtwidgets import QtCore, QtWidgets, pg, qasync
from modules.qt_map_hud import instruction_image, instruction_position
from modules.pyqt.components.map_hud_label import MapHudLabel
from modules.qt_map_assets import build_course_point_marker_pixmap
from modules.map.geometry import offset_polyline
from modules.map.content import (
    INSTRUCTION_ICONS,
    navigation_zoom,
)
from modules.map.policy import COURSE_POINT_MIN_ZOOM, course_point_start
from modules.map.style import (
    MAP_LAYER_ORDER,
    COURSE_ARROW_SPACING,
    COURSE_ARROW_WIDTH,
    COURSE_DETAIL_MIN_ZOOM,
    COURSE_LINE_WIDTH,
    COURSE_OUTLINE_WIDTH,
    COURSE_POINT_ICON_SIZE,
    COURSE_POINT_MARKER_BG_COLOR,
    COURSE_POINT_MARKER_BORDER_COLOR,
    COURSE_POINT_MARKER_BORDER_WIDTH,
    COURSE_POINT_MARKER_SIZE,
    COURSE_WIND_MARKER_SIZE,
    DEFAULT_COURSE_POINT_ICON_PATH,
    course_offset_pixels,
)
from modules.pyqt.graph.pyqtgraph.CoursePlotItem import CoursePlotItem
from modules.pyqt.graph.pyqtgraph.WindVaneItem import WindVaneItem
from modules.utils.geo import get_mod_lat_np
from modules.utils.timer import Timer, log_timers


class MapCourseMixin:
    course_point_min_zoomlevel = COURSE_POINT_MIN_ZOOM
    course_point_show_only_forward = True
    course_point_filter_by_view_bounds = False
    course_point_icon_size = COURSE_POINT_ICON_SIZE
    course_point_marker_size = COURSE_POINT_MARKER_SIZE
    course_point_marker_bg_color = COURSE_POINT_MARKER_BG_COLOR
    course_point_marker_border_color = COURSE_POINT_MARKER_BORDER_COLOR
    course_point_marker_border_width = COURSE_POINT_MARKER_BORDER_WIDTH
    course_line_width = COURSE_LINE_WIDTH
    course_outline_width = COURSE_OUTLINE_WIDTH
    course_offset_min_zoomlevel = COURSE_DETAIL_MIN_ZOOM
    course_arrow_spacing = COURSE_ARROW_SPACING
    course_arrow_width = COURSE_ARROW_WIDTH
    course_wind_marker_size = COURSE_WIND_MARKER_SIZE

    course_plot = None
    course_plot_key = None
    plot_verification = None
    course_points_plot = None
    course_point_markers = None
    course_point_last_index = None
    course_points_plot_visible = None

    instruction = None

    def _setup_course_widgets(self):
        self.course_point_markers = []
        self.course_point_last_index = None
        self.course_winds = []
        self.course_weather_revision = -1
        self.init_instruction()

    def _remove_plot_item(self, item):
        if item is not None:
            self.plot.removeItem(item)

    def _get_course_point_marker_pixmap(self, icon_path):
        return build_course_point_marker_pixmap(
            icon_path,
            self.course_point_marker_size,
            self.course_point_icon_size,
            self.course_point_marker_bg_color,
            self.course_point_marker_border_color,
            self.course_point_marker_border_width,
            self.devicePixelRatioF(),
        )

    def _get_course_offset_pixels(self):
        return course_offset_pixels(
            self.zoomlevel,
            self.config.G_COURSE_TRAFFIC_SIDE,
            self.course_line_width,
            self.course_outline_width,
            self.course_offset_min_zoomlevel,
        )

    def _get_course_plot_key(self):
        return (
            self._get_course_offset_pixels(),
            *self._get_view_data_per_px(),
            self.config.G_COURSE_TRAFFIC_SIDE,
            self.zoomlevel >= self.course_offset_min_zoomlevel,
            id(self.course.longitude),
        )

    def _update_course_plot(self):
        self._remove_plot_item(self.course_plot)

        self.course_plot = None
        if not len(self.course.latitude):
            self.course_plot_key = self._get_course_plot_key()
            return False

        pixel_scale = self._get_view_data_per_px()
        offset_pixels = self._get_course_offset_pixels()
        x_values = self.course.longitude
        y_values = get_mod_lat_np(self.course.latitude)
        brushes = self.course.colored_altitude
        if offset_pixels:
            x_values, y_values, source_indices = offset_polyline(
                x_values, y_values, pixel_scale, offset_pixels
            )
            brushes = brushes[source_indices]

        arrows = (
            (self.course_arrow_spacing, self.course_arrow_width)
            if self.zoomlevel >= self.course_offset_min_zoomlevel
            else None
        )
        self.course_plot = CoursePlotItem(
            x=x_values,
            y=y_values,
            brushes=brushes,
            width=self.course_line_width,
            outline_width=self.course_outline_width,
            outline_color=(0, 0, 0, 160),
            pixel_scale=pixel_scale,
            arrows=arrows,
        )
        self.course_plot.setZValue(MAP_LAYER_ORDER["course"])
        self.plot.addItem(self.course_plot)
        self.course_plot_key = self._get_course_plot_key()

        if self.config.G_IS_RASPI:
            return True

        self._remove_plot_item(self.plot_verification)
        self.plot_verification = pg.ScatterPlotItem(pxMode=True)
        self.plot_verification.setZValue(25)
        self.plot_verification.setData(
            [
                {
                    "pos": [
                        x_values[i],
                        y_values[i],
                    ],
                    "size": 2,
                    "pen": {"color": "w", "width": 1},
                    "brush": pg.mkBrush(color=(255, 0, 0)),
                }
                for i in range(len(x_values))
            ]
        )
        self.plot.addItem(self.plot_verification)
        return True

    def _refresh_course_plot(self):
        key = self._get_course_plot_key()
        previous = self.course_plot_key
        plot_changed = (
            previous is None
            or previous[0] != key[0]
            or previous[3:] != key[3:]
            or any(
                abs(old - new) > abs(old) * 1e-3
                for old, new in zip(previous[1:3], key[1:3])
            )
        )
        if plot_changed:
            self._update_course_plot()
            self._update_course_point_marker_positions()
        if self.course_weather_revision != self.course.weather_revision:
            self.add_course_wind()
        elif plot_changed:
            self._update_course_wind_positions()

    def _get_course_point_plot_positions(self):
        return self.config.map.marker_layout.points(
            self.course,
            self._get_view_data_per_px(),
            self._get_course_offset_pixels(),
            self.course_point_marker_size,
            self.course_outline_width,
        )

    def _update_course_point_marker_positions(self):
        if not self.course_point_markers:
            return
        for marker, x_value, y_value in zip(
            self.course_point_markers, *self._get_course_point_plot_positions()
        ):
            marker.setPos(x_value, y_value)

    def _update_course_points_plot(self):
        self._remove_plot_item(self.course_points_plot)
        self.course_point_markers = []
        self.course_point_last_index = None

        if not len(self.course_points.longitude):
            self.course_points_plot_visible = False
            return False

        self.course_points_plot = QtWidgets.QGraphicsItemGroup()
        self.course_points_plot.setZValue(MAP_LAYER_ORDER["course_points"])
        self.course_point_markers = [None] * len(self.course_points.longitude)
        ignore_transformations = (
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        )
        x_values, y_values = self._get_course_point_plot_positions()

        for i in reversed(range(len(self.course_points.longitude))):
            icon_path = INSTRUCTION_ICONS.get(
                str(self.course_points.type[i]), DEFAULT_COURSE_POINT_ICON_PATH
            )
            marker_pixmap = self._get_course_point_marker_pixmap(icon_path)
            marker = QtWidgets.QGraphicsPixmapItem(marker_pixmap)
            marker.setParentItem(self.course_points_plot)
            marker.setTransformationMode(
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            marker.setFlag(ignore_transformations, True)
            marker_size = marker_pixmap.deviceIndependentSize()
            marker.setOffset(
                -marker_size.width() / 2.0,
                -marker_size.height() / 2.0,
            )
            marker.setPos(
                x_values[i],
                y_values[i],
            )
            self.course_point_markers[i] = marker

        self.plot.addItem(self.course_points_plot)
        self.course_points_plot_visible = True
        return True

    def _update_course_point_markers_visibility_by_course_index(self):
        marker_count = len(self.course_point_markers)
        if marker_count == 0:
            self.course_point_last_index = None
            return

        if not self.course_point_show_only_forward:
            if self.course_point_last_index is not None:
                for marker in self.course_point_markers:
                    marker.setVisible(True)
            self.course_point_last_index = 0
            return

        cp_i = course_point_start(self.course, marker_count)
        prev_cp_i = self.course_point_last_index
        if prev_cp_i is None:
            prev_cp_i = 0
        for i in range(min(prev_cp_i, cp_i), max(prev_cp_i, cp_i)):
            self.course_point_markers[i].setVisible(cp_i < prev_cp_i)
        self.course_point_last_index = cp_i

    def _update_course_point_markers_visibility_by_view_bounds(
        self, x_start=np.nan, x_end=np.nan, y_start=np.nan, y_end=np.nan
    ):
        marker_count = len(self.course_point_markers)
        if marker_count == 0:
            self.course_point_last_index = None
            return

        if np.any(np.isnan([x_start, x_end, y_start, y_end])):
            return

        lon_min, lon_max = sorted((x_start, x_end))
        lat_min, lat_max = sorted((y_start, y_end))
        cp_i = course_point_start(self.course, marker_count)
        for i, marker in enumerate(self.course_point_markers):
            visible = (
                lon_min <= self.course_points.longitude[i] <= lon_max
                and lat_min <= self.course_points.latitude[i] <= lat_max
            )
            if self.course_point_show_only_forward and i < cp_i:
                visible = False
            marker.setVisible(visible)

        self.course_point_last_index = cp_i

    def _should_show_course_points(
        self, x_start=np.nan, x_end=np.nan, y_start=np.nan, y_end=np.nan
    ):
        if self.course_points_plot is None:
            return False
        if self.zoomlevel < self.course_point_min_zoomlevel:
            return False
        if not self.course_point_filter_by_view_bounds:
            return True

        if np.any(np.isnan([x_start, x_end, y_start, y_end])):
            # Keep markers visible when bounds are unknown.
            return True

        lon_min, lon_max = sorted((x_start, x_end))
        lat_min, lat_max = sorted((y_start, y_end))
        return bool(
            np.any(
                (self.course_points.longitude >= lon_min)
                & (self.course_points.longitude <= lon_max)
                & (self.course_points.latitude >= lat_min)
                & (self.course_points.latitude <= lat_max)
            )
        )

    def _update_course_points_visibility(
        self, x_start=np.nan, x_end=np.nan, y_start=np.nan, y_end=np.nan
    ):
        if self.course_points_plot is None:
            self.course_points_plot_visible = False
            self.course_point_last_index = None
            return

        visible = self._should_show_course_points(x_start, x_end, y_start, y_end)
        if self.course_points_plot_visible == visible:
            if visible:
                if self.course_point_filter_by_view_bounds:
                    self._update_course_point_markers_visibility_by_view_bounds(
                        x_start, x_end, y_start, y_end
                    )
                else:
                    self._update_course_point_markers_visibility_by_course_index()
            return

        self.course_points_plot.setVisible(visible)
        self.course_points_plot_visible = visible
        if not visible:
            return

        if self.course_point_filter_by_view_bounds:
            self._update_course_point_markers_visibility_by_view_bounds(
                x_start, x_end, y_start, y_end
            )
        else:
            self._update_course_point_markers_visibility_by_course_index()

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
            self._update_course_points_visibility()

        self.add_course_wind()

        if has_course_plot and has_course_points:
            app_logger.info("Plotting course:")
            log_timers(timers, text_total=f"  total        : {0:.3f} sec")

    def _clear_course_winds(self):
        for course_wind in self.course_winds:
            self._remove_plot_item(course_wind)
        self.course_winds.clear()

    def add_course_wind(self):
        self._clear_course_winds()
        self.course_weather_revision = self.course.weather_revision
        for _, angle, color in self.config.map.course_wind_markers(self.course):
            vane = WindVaneItem(angle, color, self.course_wind_marker_size)
            vane.setZValue(MAP_LAYER_ORDER["wind"])
            self.course_winds.append(vane)
            self.plot.addItem(vane)
        self._update_course_wind_positions()

    def _update_course_wind_positions(self):
        if not self.course_winds:
            return
        wind_x, wind_y = self.config.map.marker_layout.winds(
            self.course,
            self.config.map.course_wind_markers(self.course),
            self._get_view_data_per_px(),
            self._get_course_offset_pixels(),
            self.config.G_COURSE_TRAFFIC_SIDE,
        )
        for vane, x_value, y_value in zip(self.course_winds, wind_x, wind_y):
            vane.setPos(x_value, y_value)

    def reset_track(self):
        self._track_history = self._track_tail = None
        self.track_history_plot.setData([], [])
        self.track_tail_plot.setData([], [])

    def reset_course(self):
        self.course_focus.reset()
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
        self.course_point_markers = []
        self.course_point_last_index = None
        self.course_points_plot_visible = False
        self._clear_course_winds()
        self.course_weather_revision = -1

    def init_course(self):
        self.course_focus.reset()
        self.init_instruction()
        self.course_plot_key = None
        self.course_weather_revision = -1
        self.course_loaded = False
        self.resizeEvent(None)

    @qasync.asyncSlot()
    async def search_route(self):
        if not self.config.map.can_search_route(self.lock_status):
            return
        await self.config.map.search_route(
            (self.point["pos"][0], self.point["pos"][1] / self.y_mod),
            (self.map_pos["x"], self.map_pos["y"]),
        )

    def update_instruction(self, auto_zoom=False):
        instruction_name, instruction_distance = self._get_instruction_data()
        if instruction_distance is None:
            self._hide_instruction()
            return

        if self.instruction is None:
            self.instruction = MapHudLabel(self._fixed_hud_overlay)

        image = instruction_image(
            instruction_name, instruction_distance, self.devicePixelRatioF()
        )
        self.instruction.set_image(image)
        self.instruction.show()

        self._relayout_fixed_instruction()

        if auto_zoom:
            self.zoomlevel, self.auto_zoomlevel_back = navigation_zoom(
                instruction_distance,
                self.zoomlevel,
                self.auto_zoomlevel - self.zoom_delta_from_tilesize,
                self.auto_zoomlevel_back,
            )

    def _get_instruction_data(self):
        return self.config.map.navigation.instruction(
            self.course, self.config.G_COURSE_INDEXING
        )

    def init_instruction(self):
        if self._get_instruction_data()[1] is not None:
            if self.instruction is None:
                self.instruction = MapHudLabel(self._fixed_hud_overlay)
        else:
            self._hide_instruction()
            if self.instruction is not None:
                self.instruction.deleteLater()
            self.instruction = None

    def _hide_instruction(self):
        if self.instruction is not None:
            self.instruction.hide()

    def _relayout_fixed_instruction(self):
        if self.instruction is None or self.instruction.isHidden():
            return

        parent = self.instruction.parentWidget()
        controls = ()
        if self.config.uses_pointer_navigation:
            self.layout.activate()
            controls = tuple(
                QtCore.QRectF(group.geometry())
                for group in (self.button_group_left, self.button_group_right)
            )
        pos = instruction_position(
            QtCore.QSizeF(self.instruction.size()),
            parent.width(),
            parent.height(),
            controls,
        )
        self.instruction.move(pos.toPoint())
