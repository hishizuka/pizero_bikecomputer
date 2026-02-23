from collections import Counter
from datetime import datetime, timezone
import time

import numpy as np

from modules.app_logger import app_logger
from modules._qt_qtwidgets import QtCore, Signal, pg, qasync
from modules.utils.geo import get_mod_lat_np
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
    _PERF_MAP_WINDOW = 30

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
        if len(self.track_history_lon) or len(self.track_tail_lon):
            app_logger.info(
                f"resume_track(init): {(datetime.now(timezone.utc) - t).total_seconds():.3f} sec"
            )

        self.layout.addWidget(self.plot, 0, 0, -1, -1)

        self._setup_touch_overlay_controls()
        self._setup_course_widgets()
        self._setup_layout_grid()
        self._setup_tile_dither_palette()
        self._init_perf_map_metrics()
        self._init_update_display_runtime()

    def _init_perf_map_metrics(self):
        self._perf_map_calls = 0
        self._perf_map_exec = 0
        self._perf_map_skip = 0
        self._perf_map_update_ms = []
        self._perf_map_draw_ms_sum = 0.0
        self._perf_map_track_ms_sum = 0.0
        self._perf_map_track_fetch_ms_sum = 0.0
        self._perf_map_track_render_ms_sum = 0.0
        self._perf_map_prepare_ms_sum = 0.0
        self._perf_map_instruction_ms_sum = 0.0
        self._perf_map_hud_ms_sum = 0.0
        self._perf_map_load_course_ms_sum = 0.0
        self._perf_map_tile_download_ms_sum = 0.0
        self._perf_map_tile_download_calls = 0
        self._perf_map_tile_check_ms_sum = 0.0
        self._perf_map_tile_io_ms_sum = 0.0
        self._perf_map_tile_conv_ms_sum = 0.0
        self._perf_map_tile_imgitem_ms_sum = 0.0
        self._perf_map_tile_plot_ms_sum = 0.0
        self._perf_map_tile_drawn_count = 0
        self._perf_map_tile_reused_count = 0
        self._perf_map_tile_retry_count = 0
        self._perf_map_exec_reason_counts = Counter()
        self._perf_map_skip_reason_counts = Counter()
        self._perf_map_redraw_reason_counts = Counter()

    def _init_update_display_runtime(self):
        self._update_display_running = False
        self._update_display_retrigger = False
        self._tile_batch_followup_scheduled = False
        self._tile_batch_followup_ms = 60

    def _run_scheduled_update_display(self):
        self._tile_batch_followup_scheduled = False
        self.update_display()

    def _schedule_tile_batch_followup(self):
        if self._tile_batch_followup_scheduled:
            return
        self._tile_batch_followup_scheduled = True
        QtCore.QTimer.singleShot(
            self._tile_batch_followup_ms,
            self._run_scheduled_update_display,
        )

    @staticmethod
    def _safe_stat(values, func, *args):
        if not values:
            return float("nan")
        return float(func(values, *args))

    @staticmethod
    def _format_perf_counter(counter):
        if not counter:
            return "-"
        return ",".join(f"{key}:{counter[key]}" for key in sorted(counter))

    def _record_perf_map_tile_breakdown(
        self,
        *,
        download_ms=0.0,
        download_calls=0,
        check_ms=0.0,
        io_ms=0.0,
        conv_ms=0.0,
        imgitem_ms=0.0,
        plot_ms=0.0,
        drawn_count=0,
        reused_count=0,
        retry_count=0,
    ):
        self._perf_map_tile_download_ms_sum += float(download_ms)
        self._perf_map_tile_download_calls += int(download_calls)
        self._perf_map_tile_check_ms_sum += float(check_ms)
        self._perf_map_tile_io_ms_sum += float(io_ms)
        self._perf_map_tile_conv_ms_sum += float(conv_ms)
        self._perf_map_tile_imgitem_ms_sum += float(imgitem_ms)
        self._perf_map_tile_plot_ms_sum += float(plot_ms)
        self._perf_map_tile_drawn_count += int(drawn_count)
        self._perf_map_tile_reused_count += int(reused_count)
        self._perf_map_tile_retry_count += int(retry_count)

    def _get_perf_map_cpu_percent(self):
        try:
            sensor = self.config.logger.sensor
            return sensor.values["integrated"].get("cpu_percent", float("nan"))
        except Exception:
            return float("nan")

    def _maybe_log_perf_map_window(self):
        if self._perf_map_calls < self._PERF_MAP_WINDOW:
            return

        update_avg_ms = self._safe_stat(self._perf_map_update_ms, np.mean)
        update_p95_ms = self._safe_stat(self._perf_map_update_ms, np.percentile, 95)
        update_max_ms = self._safe_stat(self._perf_map_update_ms, np.max)

        if self._perf_map_exec > 0:
            draw_avg_ms = self._perf_map_draw_ms_sum / self._perf_map_exec
            track_avg_ms = self._perf_map_track_ms_sum / self._perf_map_exec
            track_fetch_avg_ms = (
                self._perf_map_track_fetch_ms_sum / self._perf_map_exec
            )
            track_render_avg_ms = (
                self._perf_map_track_render_ms_sum / self._perf_map_exec
            )
        else:
            draw_avg_ms = float("nan")
            track_avg_ms = float("nan")
            track_fetch_avg_ms = float("nan")
            track_render_avg_ms = float("nan")

        if self._perf_map_track_ms_sum > 0:
            draw_track_ratio = self._perf_map_draw_ms_sum / self._perf_map_track_ms_sum
        else:
            draw_track_ratio = float("nan")

        if self._perf_map_exec > 0:
            prepare_avg_ms = self._perf_map_prepare_ms_sum / self._perf_map_exec
            instruction_avg_ms = (
                self._perf_map_instruction_ms_sum / self._perf_map_exec
            )
            hud_avg_ms = self._perf_map_hud_ms_sum / self._perf_map_exec
            load_course_avg_ms = self._perf_map_load_course_ms_sum / self._perf_map_exec
            tile_download_avg_ms = (
                self._perf_map_tile_download_ms_sum / self._perf_map_exec
            )
            tile_check_avg_ms = self._perf_map_tile_check_ms_sum / self._perf_map_exec
            tile_io_avg_ms = self._perf_map_tile_io_ms_sum / self._perf_map_exec
            tile_conv_avg_ms = self._perf_map_tile_conv_ms_sum / self._perf_map_exec
            tile_imgitem_avg_ms = (
                self._perf_map_tile_imgitem_ms_sum / self._perf_map_exec
            )
            tile_plot_avg_ms = self._perf_map_tile_plot_ms_sum / self._perf_map_exec
            tile_drawn_per_exec = self._perf_map_tile_drawn_count / self._perf_map_exec
            tile_reused_per_exec = (
                self._perf_map_tile_reused_count / self._perf_map_exec
            )
            tile_retry_per_exec = self._perf_map_tile_retry_count / self._perf_map_exec
        else:
            prepare_avg_ms = float("nan")
            instruction_avg_ms = float("nan")
            hud_avg_ms = float("nan")
            load_course_avg_ms = float("nan")
            tile_download_avg_ms = float("nan")
            tile_check_avg_ms = float("nan")
            tile_io_avg_ms = float("nan")
            tile_conv_avg_ms = float("nan")
            tile_imgitem_avg_ms = float("nan")
            tile_plot_avg_ms = float("nan")
            tile_drawn_per_exec = float("nan")
            tile_reused_per_exec = float("nan")
            tile_retry_per_exec = float("nan")

        if self._perf_map_tile_drawn_count > 0:
            tile_io_per_tile_ms = (
                self._perf_map_tile_io_ms_sum / self._perf_map_tile_drawn_count
            )
            tile_conv_per_tile_ms = (
                self._perf_map_tile_conv_ms_sum / self._perf_map_tile_drawn_count
            )
            tile_imgitem_per_tile_ms = (
                self._perf_map_tile_imgitem_ms_sum / self._perf_map_tile_drawn_count
            )
            tile_plot_per_tile_ms = (
                self._perf_map_tile_plot_ms_sum / self._perf_map_tile_drawn_count
            )
            tile_pipeline_per_tile_ms = (
                tile_io_per_tile_ms
                + tile_conv_per_tile_ms
                + tile_imgitem_per_tile_ms
                + tile_plot_per_tile_ms
            )
        else:
            tile_io_per_tile_ms = float("nan")
            tile_conv_per_tile_ms = float("nan")
            tile_imgitem_per_tile_ms = float("nan")
            tile_plot_per_tile_ms = float("nan")
            tile_pipeline_per_tile_ms = float("nan")

        cpu_percent = self._get_perf_map_cpu_percent()

        other_avg_ms = (
            update_avg_ms
            - draw_avg_ms
            - track_avg_ms
            - prepare_avg_ms
            - instruction_avg_ms
            - hud_avg_ms
            - load_course_avg_ms
        )

        app_logger.debug(
            "[PERF_MAP] "
            f"win={self._PERF_MAP_WINDOW} "
            f"calls={self._perf_map_calls} "
            f"exec={self._perf_map_exec} "
            f"skip={self._perf_map_skip} "
            f"upd_avg_ms={update_avg_ms:.3f} "
            f"upd_p95_ms={update_p95_ms:.3f} "
            f"upd_max_ms={update_max_ms:.3f} "
            f"draw_avg_ms={draw_avg_ms:.3f} "
            f"track_avg_ms={track_avg_ms:.3f} "
            f"draw_track_ratio={draw_track_ratio:.3f} "
            f"cpu={cpu_percent} "
            f"lock={int(bool(self.lock_status))} "
            f"recording={int(self.config.G_STOPWATCH_STATUS == 'START')} "
            f"zoom={self.zoomlevel}"
        )
        app_logger.debug(
            "[PERF_MAP_DETAIL] "
            f"win={self._PERF_MAP_WINDOW} "
            f"prepare_avg_ms={prepare_avg_ms:.3f} "
            f"instruction_avg_ms={instruction_avg_ms:.3f} "
            f"track_fetch_avg_ms={track_fetch_avg_ms:.3f} "
            f"track_render_avg_ms={track_render_avg_ms:.3f} "
            f"hud_avg_ms={hud_avg_ms:.3f} "
            f"load_course_avg_ms={load_course_avg_ms:.3f} "
            f"other_avg_ms={other_avg_ms:.3f} "
            f"exec_reasons={self._format_perf_counter(self._perf_map_exec_reason_counts)} "
            f"skip_reasons={self._format_perf_counter(self._perf_map_skip_reason_counts)} "
            f"redraw_reasons={self._format_perf_counter(self._perf_map_redraw_reason_counts)}"
        )
        app_logger.debug(
            "[PERF_MAP_TILE] "
            f"win={self._PERF_MAP_WINDOW} "
            f"dl_avg_ms={tile_download_avg_ms:.3f} "
            f"dl_calls={self._perf_map_tile_download_calls} "
            f"check_avg_ms={tile_check_avg_ms:.3f} "
            f"io_avg_ms={tile_io_avg_ms:.3f} "
            f"conv_avg_ms={tile_conv_avg_ms:.3f} "
            f"imgitem_avg_ms={tile_imgitem_avg_ms:.3f} "
            f"plot_avg_ms={tile_plot_avg_ms:.3f} "
            f"drawn={self._perf_map_tile_drawn_count} "
            f"reused={self._perf_map_tile_reused_count} "
            f"retry={self._perf_map_tile_retry_count} "
            f"drawn_per_exec={tile_drawn_per_exec:.3f} "
            f"reused_per_exec={tile_reused_per_exec:.3f} "
            f"retry_per_exec={tile_retry_per_exec:.3f} "
            f"io_per_tile_ms={tile_io_per_tile_ms:.3f} "
            f"conv_per_tile_ms={tile_conv_per_tile_ms:.3f} "
            f"imgitem_per_tile_ms={tile_imgitem_per_tile_ms:.3f} "
            f"plot_per_tile_ms={tile_plot_per_tile_ms:.3f} "
            f"pipeline_per_tile_ms={tile_pipeline_per_tile_ms:.3f}"
        )

        self._init_perf_map_metrics()

    def _setup_layout_grid(self):
        self.layout.setColumnMinimumWidth(0, 40)
        self.layout.setColumnStretch(1, 1)
        self.layout.setColumnMinimumWidth(2, 40)
        self.layout.setColumnMinimumWidth(3, 5)
        self.layout.setColumnMinimumWidth(4, 40)

    def resizeEvent(self, event):
        self.plot.setFixedSize(self.width(), self.height())
        self._layout_fixed_hud_overlay()
        self._relayout_fixed_instruction(force=True)

    @qasync.asyncSlot(int, int)
    async def on_drag_ended(self, dx, dy):
        if self.lock_status:
            self.timer.start()
            return

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
        if self._update_display_running:
            self._update_display_retrigger = True
            return

        self._update_display_running = True
        try:
            self._perf_map_calls += 1
            display_key, overlay_map = self._build_display_key()
            prev_display_key = self._last_display_key
            redraw_reasons = []
            exec_reason = "redraw_needed"
            if prev_display_key is None:
                exec_reason = "first_frame"
            elif display_key != prev_display_key:
                exec_reason = "display_key_changed"
            else:
                redraw_reasons = self._get_redraw_reasons(overlay_map)
                if not redraw_reasons:
                    self._perf_map_skip_reason_counts.update(["display_stable"])
                    self._perf_map_skip += 1
                    self._maybe_log_perf_map_window()
                    return

            self._perf_map_exec_reason_counts.update([exec_reason])
            if redraw_reasons:
                self._perf_map_redraw_reason_counts.update(redraw_reasons)

            update_start = time.perf_counter()
            draw_elapsed_ms = 0.0
            prepare_start = time.perf_counter()
            self._clear_display_buffers()
            self._update_point_state()
            self._update_map_area_and_move()
            self._update_current_and_center_items()

            x_start, x_end, y_start, y_end = self._get_view_bounds()
            x_start, x_end, y_start, y_end = self._apply_view_ranges(
                x_start, x_end, y_start, y_end
            )
            prepare_elapsed_ms = (time.perf_counter() - prepare_start) * 1000.0

            if not np.any(np.isnan([x_start, x_end, y_start, y_end])):
                draw_start = time.perf_counter()
                await self.draw_map_tile(x_start, x_end, y_start, y_end)
                draw_elapsed_ms = (time.perf_counter() - draw_start) * 1000.0

            load_course_elapsed_ms = 0.0
            if not self.course_loaded:
                load_course_start = time.perf_counter()
                self.load_course()
                load_course_elapsed_ms = (
                    (time.perf_counter() - load_course_start) * 1000.0
                )
                self.course_loaded = True

            instruction_start = time.perf_counter()
            await self.update_instruction(
                x_start, x_end, y_start, y_end, auto_zoom=True
            )
            instruction_elapsed_ms = (time.perf_counter() - instruction_start) * 1000.0

            # draw track
            track_fetch_start = time.perf_counter()
            track_updated = self.get_track()
            track_fetch_elapsed_ms = (
                (time.perf_counter() - track_fetch_start) * 1000.0
            )
            track_render_start = time.perf_counter()
            if self.track_history_needs_redraw:
                history_lon = self.track_history_lon
                history_lat = (
                    get_mod_lat_np(np.asarray(self.track_history_lat, dtype=np.float32))
                    if len(history_lon)
                    else []
                )
                self.track_history_plot.setData(history_lon, history_lat)
                self.track_history_needs_redraw = False
            if track_updated or self.track_tail_needs_redraw:
                tail_lon = self.track_tail_lon
                if len(tail_lon):
                    tail_lat_values = self.track_tail_lat
                    # Visually connect history and tail by reusing the latest history point.
                    if len(self.track_history_lon) and len(self.track_history_lat):
                        tail_lon = [self.track_history_lon[-1], *tail_lon]
                        tail_lat_values = [self.track_history_lat[-1], *tail_lat_values]
                    tail_lat = get_mod_lat_np(
                        np.asarray(tail_lat_values, dtype=np.float32)
                    )
                else:
                    tail_lat = []
                self.track_tail_plot.setData(tail_lon, tail_lat)
                self.track_tail_needs_redraw = False
            track_render_elapsed_ms = (
                (time.perf_counter() - track_render_start) * 1000.0
            )
            track_elapsed_ms = track_fetch_elapsed_ms + track_render_elapsed_ms

            hud_elapsed_ms = 0.0
            if not np.any(np.isnan([x_start, y_start])):
                hud_start = time.perf_counter()
                # draw scale
                scale_geom = self.draw_scale(x_start, y_start)
                # draw legend
                self.draw_legend(x_start, y_start, scale_geom)
                # draw map attribution
                self.draw_map_attribution(x_start, y_start)
                hud_elapsed_ms = (time.perf_counter() - hud_start) * 1000.0

            self._last_display_key = display_key

            update_elapsed_ms = (time.perf_counter() - update_start) * 1000.0
            self._perf_map_exec += 1
            self._perf_map_update_ms.append(update_elapsed_ms)
            self._perf_map_draw_ms_sum += draw_elapsed_ms
            self._perf_map_track_ms_sum += track_elapsed_ms
            self._perf_map_track_fetch_ms_sum += track_fetch_elapsed_ms
            self._perf_map_track_render_ms_sum += track_render_elapsed_ms
            self._perf_map_prepare_ms_sum += prepare_elapsed_ms
            self._perf_map_instruction_ms_sum += instruction_elapsed_ms
            self._perf_map_hud_ms_sum += hud_elapsed_ms
            self._perf_map_load_course_ms_sum += load_course_elapsed_ms
            self._maybe_log_perf_map_window()
        finally:
            self._update_display_running = False
            if self._update_display_retrigger:
                self._update_display_retrigger = False
                QtCore.QTimer.singleShot(0, self.update_display)
            elif self._has_tile_batch_pending():
                self._schedule_tile_batch_followup()

    def get_arrow_angle_index(self, angle):
        # Used by MapStateMixin to update the direction arrow symbol.
        return (
            int(
                (angle + self.arrow_direction_angle_unit_half)
                / self.arrow_direction_angle_unit
            )
            % self.arrow_direction_num
        )
