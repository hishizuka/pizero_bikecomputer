import numpy as np

from modules._qt_qtwidgets import qasync
from modules.utils.map import get_zoom_delta_from_tile_size
from modules.map.policy import clamp_zoom
from modules.map.overlays import MapOverlays
from .pyqt_map_button import create_map_controls


class MapOverlayMixin:
    overlay_order = MapOverlays.order

    @property
    def overlay_index(self):
        return self.config.map.overlays.index

    @overlay_index.setter
    def overlay_index(self, value):
        self.config.map.overlays.index = value

    zoom_delta_from_tilesize = 0
    auto_zoomlevel = None
    auto_zoomlevel_diff = 2  # auto_zoomlevel = zoomlevel + auto_zoomlevel_diff
    auto_zoomlevel_back = None

    def _setup_touch_overlay_controls(self):
        if not self.config.uses_pointer_navigation:
            return

        (
            self.button_group_left,
            self.button_group_right,
            self.time_button_group,
        ) = create_map_controls(
            self,
            self.layout,
            self.buttons,
            self,
            self.config.G_GOOGLE_ROUTES_API["HAVE_API_TOKEN"],
        )
        self.enable_overlay_button()
        self.enable_overlay_time_and_button()

    def reset_map(self):
        self._clear_tile_items()
        self._init_overlay_state()
        zoom_delta_from_tilesize = get_zoom_delta_from_tile_size(
            self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"]
        )
        self.zoomlevel = clamp_zoom(
            self.zoomlevel + self.zoom_delta_from_tilesize - zoom_delta_from_tilesize
        )
        self.zoom_delta_from_tilesize = zoom_delta_from_tilesize
        self.auto_zoomlevel = self.zoomlevel + self.auto_zoomlevel_diff

        for key in [
            self.config.G_MAP,
            self.config.G_HEATMAP_OVERLAY_MAP,
            self.config.G_RAIN_OVERLAY_MAP,
            self.config.G_WIND_OVERLAY_MAP,
        ]:
            self.drawn_tile[key] = {}
            self.pre_zoomlevel[key] = np.nan

        self._cleanup_cached_tiles()
        self._last_display_key = None
        self.set_attribution()
        self.update_legend_content()

    def _init_overlay_state(self):
        self._overlay_display_time = {kind: None for kind in ("RAIN", "WIND")}

    def set_attribution(self):
        attribution_text = self.config.map.overlays.attribution()
        self.update_fixed_attribution_label(
            attribution_text=attribution_text,
            visible=(attribution_text != ""),
        )

    @qasync.asyncSlot()
    async def update_overlay_time(self, goto_next=True):
        await self.config.map.update_overlay_time(goto_next)

    async def draw_map_tile(self, x_start, x_end, y_start, y_end):
        p0 = {"x": min(x_start, x_end), "y": min(y_start, y_end)}
        p1 = {"x": max(x_start, x_end), "y": max(y_start, y_end)}

        await self.draw_map_tile_by_overlay(
            self.config.G_MAP_CONFIG,
            self.config.G_MAP,
            self.zoomlevel,
            p0,
            p1,
            overlay=False,
            use_mbtiles=self.config.G_MAP_CONFIG[self.config.G_MAP]["use_mbtiles"],
        )
        overlays = self.config.map.overlays
        map_config, map_name = overlays.source()
        if map_config is None:
            return
        if overlays.has_times:
            kind = overlays.kind
            await overlays.prepare()
            if kind != overlays.kind:
                self._update_display_retrigger = True
                return
            display_time = overlays.time[kind]["display_time"]
            if self._overlay_display_time[kind] != display_time:
                self._overlay_display_time[kind] = display_time
                self.reset_overlay(map_name)
        await self.overlay_map(p0, p1, map_config, map_name)

    def reset_overlay(self, map_name):
        self._clear_tile_items(map_name)
        self.drawn_tile[map_name] = {}
        self.pre_zoomlevel[map_name] = np.nan

    async def overlay_map(self, p0, p1, map_config, map_name):
        z = self._get_zoom_for_map(map_name, map_config)
        await self.draw_map_tile_by_overlay(
            map_config,
            map_name,
            z,
            p0,
            p1,
            overlay=True,
        )

    def enable_overlay_time_and_button(self):
        if not self.config.uses_pointer_navigation:
            return
        if self.config.G_GOOGLE_ROUTES_API["HAVE_API_TOKEN"]:
            self.buttons["go"].setEnabled(
                self.config.map.can_search_route(self.lock_status)
            )
        overlays = self.config.map.overlays
        for forward, key in enumerate(("prev_time", "next_time")):
            self.buttons[key].setVisible(overlays.has_times)
            self.buttons[key].setEnabled(overlays.can_shift_time(forward))
        self.time_button_group.setVisible(overlays.has_times)

    def change_map_overlays(self):
        self.config.map.change_map_overlays()

    remove_overlay = reset_map

    def enable_overlay_button(self):
        if self.config.uses_pointer_navigation:
            self.buttons["layers"].setEnabled(self.config.map.overlays.has_overlays)
