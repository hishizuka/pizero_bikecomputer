from datetime import datetime, timezone

import numpy as np

from modules.app_logger import app_logger
from modules._qt_qtwidgets import Signal, pg, qasync
from .pyqt_base_map import BaseMapWidget
from .pyqt_map_course import MapCourseMixin
from .pyqt_map_hud import MapHudMixin
from .pyqt_map_overlay import MapOverlayMixin
from .pyqt_map_state import MapStateMixin
from .pyqt_map_tiles import MapTileMixin


class MapWidget(
    MapOverlayMixin,
    MapTileMixin,
    MapHudMixin,
    MapCourseMixin,
    MapStateMixin,
    BaseMapWidget,
):
    # signal for physical button
    signal_search_route = Signal()

    map_attribution = pg.TextItem(
        anchor=(1, 1),
        angle=0,
        border=(255, 255, 255, 255),
        fill=(255, 255, 255, 255),
        color=(0, 0, 0),
    )

    @property
    def maptile_with_values(self):
        return self.config.api.maptile_with_values

    def setup_ui_extra(self):
        super().setup_ui_extra()

        self._setup_hud_items()
        self._setup_map_state_items()

        self.signal_search_route.connect(self.search_route)

        self.reset_map()

        t = datetime.now(timezone.utc)
        self.get_track()  # heavy when resume
        if len(self.tracks_lon):
            app_logger.info(
                f"resume_track(init): {(datetime.now(timezone.utc) - t).total_seconds():.3f} sec"
            )

        self.layout.addWidget(self.plot, 0, 0, -1, -1)

        self._setup_touch_overlay_controls()
        self._setup_course_widgets()
        self._setup_layout_grid()
        self._setup_tile_dither_palette()

    def _setup_layout_grid(self):
        self.layout.setColumnMinimumWidth(0, 40)
        self.layout.setColumnStretch(1, 1)
        self.layout.setColumnMinimumWidth(2, 40)
        self.layout.setColumnMinimumWidth(3, 5)
        self.layout.setColumnMinimumWidth(4, 40)

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
        display_key, overlay_map = self._build_display_key()
        if self._should_skip_display_update(display_key, overlay_map):
            return

        self._clear_display_buffers()
        self._update_point_state()
        self._update_map_area_and_move()
        self._update_current_and_center_items()

        x_start, x_end, y_start, y_end = self._get_view_bounds()
        self._apply_view_ranges(x_start, x_end, y_start, y_end)

        if not np.any(np.isnan([x_start, x_end, y_start, y_end])):
            await self.draw_map_tile(x_start, x_end, y_start, y_end)

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
            scale_geom = self.draw_scale(x_start, y_start)
            # draw legend
            self.draw_legend(x_start, y_start, scale_geom)
            # draw map attribution
            self.draw_map_attribution(x_start, y_start)

        self._last_display_key = display_key

    def get_arrow_angle_index(self, angle):
        # Used by MapStateMixin to update the direction arrow symbol.
        return (
            int(
                (angle + self.arrow_direction_angle_unit_half)
                / self.arrow_direction_angle_unit
            )
            % self.arrow_direction_num
        )
