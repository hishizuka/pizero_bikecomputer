import asyncio

import numpy as np

from modules._qt_qtwidgets import QtCore, QtWidgets, qasync
from modules.utils.asyncio import run_after
from modules.utils.time import (
    format_jma_validtime_local,
    format_scw_validtime_local,
    format_unix_validtime_local,
)
from .pyqt_map_button import (
    DirectionButton,
    MapLayersButton,
    MapNextButton,
    MapPrevButton,
)


class MapOverlayMixin:
    _OVERLAY_ENABLED_ATTRS = {
        "WIND": "G_USE_WIND_OVERLAY_MAP",
        "RAIN": "G_USE_RAIN_OVERLAY_MAP",
        "HEATMAP": "G_USE_HEATMAP_OVERLAY_MAP",
    }

    overlay_time = {}
    overlay_order = ["NONE", "WIND", "RAIN", "HEATMAP"]
    overlay_index = 0

    zoom_delta_from_tilesize = 0
    auto_zoomlevel = None
    auto_zoomlevel_diff = 2  # auto_zoomlevel = zoomlevel + auto_zoomlevel_diff
    auto_zoomlevel_back = None

    @staticmethod
    def _is_time_series_overlay(overlay_type):
        return overlay_type in ("WIND", "RAIN")

    def _is_overlay_enabled(self, overlay_type):
        enabled_attr = self._OVERLAY_ENABLED_ATTRS.get(overlay_type)
        return getattr(self.config, enabled_attr) if enabled_attr else True

    def _create_touch_button_group(self):
        group = QtWidgets.QWidget(self)
        group.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        group.setStyleSheet(
            "background-color: rgba(255, 255, 255, 128);" "border-radius: 8px;"
        )
        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        return group, layout

    def _setup_touch_overlay_controls(self):
        if not self.config.display.has_touch:
            return

        align_top_left = (
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft
        )
        align_top_right = (
            QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignRight
        )

        self.button_group_left, left_layout = self._create_touch_button_group()
        left_layout.addWidget(self.buttons["lock"])
        left_layout.addWidget(self.buttons["zoomup"])
        left_layout.addWidget(self.buttons["zoomdown"])

        if self.config.G_GOOGLE_DIRECTION_API["HAVE_API_TOKEN"]:
            self.buttons["go"] = DirectionButton()
            self.buttons["go"].clicked.connect(self.search_route)
            left_layout.addSpacing(4)
            left_layout.addWidget(self.buttons["go"])

        self.layout.addWidget(self.button_group_left, 0, 0, alignment=align_top_left)

        self.button_group_right, right_layout = self._create_touch_button_group()

        self.buttons["layers"] = MapLayersButton()
        right_layout.addWidget(self.buttons["layers"])
        self.buttons["layers"].clicked.connect(self.change_map_overlays)
        self.enable_overlay_button()

        self.buttons["prev_time"] = MapPrevButton()
        self.buttons["next_time"] = MapNextButton()
        self.time_button_group = QtWidgets.QWidget(self.button_group_right)
        time_layout = QtWidgets.QHBoxLayout(self.time_button_group)
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setSpacing(6)
        time_layout.addWidget(self.buttons["prev_time"])
        time_layout.addWidget(self.buttons["next_time"])
        right_layout.addWidget(self.time_button_group)
        self.buttons["prev_time"].clicked.connect(
            lambda: self.update_overlay_time(False)
        )
        self.buttons["next_time"].clicked.connect(
            lambda: self.update_overlay_time(True)
        )
        self.enable_overlay_time_and_button()

        self.layout.addWidget(self.button_group_right, 0, 4, alignment=align_top_right)

    def reset_map(self):
        self._clear_tile_items()
        self._init_overlay_state()
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

        self._cleanup_cached_tiles()
        self._last_display_key = None
        self.set_attribution()
        self.update_legend_content()

    def _init_overlay_state(self):
        self.overlay_time = {
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

    def _apply_precomputed_overlay_time(self, overlay_type, map_name, map_settings):
        cache = getattr(self, "_overlay_refresh_time_cache", None)
        if not isinstance(cache, dict):
            return
        cached = cache.get(overlay_type)
        if not isinstance(cached, dict):
            return
        if cached.get("map_name") != map_name:
            return
        time_key = cached.get("time_key")
        if time_key is None:
            return
        # Reuse per-frame time key to avoid duplicated time alignment calculations.
        map_settings["_precomputed_current_time"] = time_key

    def set_attribution(self):
        attribution_text = self.config.G_MAP_CONFIG[self.config.G_MAP]["attribution"]
        overlay_type = self.overlay_order[self.overlay_index]
        map_settings = None
        map_config, map_name = self._get_overlay_map_config_and_name(overlay_type)
        if map_config and map_name in map_config:
            map_settings = map_config[map_name]
        if map_settings is not None:
            split_char = "<br />"
            attribution_text += f"{split_char}{map_settings['attribution']}"
            extra_text = self.add_attribution_extra_text(map_settings)
            if extra_text:
                attribution_text += f" ({extra_text})"

        attribution_html = (
            '<div style="text-align: right; color: #000000; font-size: small;">'
            + attribution_text
            + "</div>"
        )

        if attribution_text != self._last_attribution_text:
            self.map_attribution.setTextWidth(-1)
            self.map_attribution.setHtml(attribution_html)
            text_width = self.map_attribution.boundingRect().width()
            if text_width > 0:
                self.map_attribution.setTextWidth(text_width)
            self._last_attribution_text = attribution_text

        if attribution_text == "":
            self.map_attribution.setZValue(-100)
        else:
            self.map_attribution.setZValue(100)

        self.update_fixed_attribution_label(
            attribution_html=attribution_html,
            visible=(attribution_text != ""),
        )

    def add_attribution_extra_text(self, map_settings):
        overlay_type = self.overlay_order[self.overlay_index]
        if overlay_type == "RAIN":
            map_name = self.config.G_RAIN_OVERLAY_MAP
            if map_name == "jpn_jma_bousai":
                return format_jma_validtime_local(
                    map_settings.get("validtime"),
                    map_settings.get("time_format"),
                )
            if map_name == "rainviewer":
                return format_unix_validtime_local(map_settings.get("validtime"))
            return ""
        if overlay_type == "WIND":
            map_name = self.config.G_WIND_OVERLAY_MAP
            if map_name.startswith("jpn_scw"):
                return format_scw_validtime_local(map_settings.get("validtime"))
        return ""

    async def update_prev_next_overlay_time(
        self, overlay_type, map_config, map_name, skip_update=False
    ):
        p_vt, p_sd, n_vt, n_sd = await self.maptile_with_values.get_prev_next_validtime(
            overlay_type,
            map_config,
            map_name,
            skip_update=skip_update,
        )

        self.overlay_time[overlay_type]["prev_time"] = p_vt
        self.overlay_time[overlay_type]["next_time"] = n_vt
        if map_name.startswith("jpn_scw"):
            self.overlay_time[overlay_type]["prev_subdomain"] = p_sd
            self.overlay_time[overlay_type]["next_subdomain"] = n_sd

        if self.config.display.has_touch:
            for key in ("prev_time", "next_time"):
                self.buttons[key].setEnabled(
                    self.overlay_time[overlay_type][key] is not None
                )

    @qasync.asyncSlot()
    async def update_overlay_time(self, goto_next=True):
        overlay_type = self.overlay_order[self.overlay_index]
        if not self._is_time_series_overlay(overlay_type):
            return

        map_config, map_name = self._get_overlay_map_config_and_name(overlay_type)
        if map_config is None or map_name is None:
            return
        map_settings = map_config[map_name]

        time_key = "next_time" if goto_next else "prev_time"
        subdomain_key = "next_subdomain" if goto_next else "prev_subdomain"
        time_value = self.overlay_time[overlay_type].get(time_key)
        if time_value is None:
            return

        map_settings["validtime"] = time_value
        if map_name.startswith("jpn_scw"):
            map_settings["subdomain"] = self.overlay_time[overlay_type].get(
                subdomain_key
            )
        elif map_name.startswith("jpn_jma_bousai"):
            basetime = self.maptile_with_values.get_jma_basetime_for_validtime(
                map_settings, time_value
            )
            if basetime:
                map_settings["basetime"] = basetime
        await self.update_display()
        await self.update_prev_next_overlay_time(
            overlay_type,
            map_config,
            map_name,
            skip_update=True,
        )

    async def draw_map_tile(self, x_start, x_end, y_start, y_end):
        p0 = {"x": min(x_start, x_end), "y": min(y_start, y_end)}
        p1 = {"x": max(x_start, x_end), "y": max(y_start, y_end)}

        prev_main_signature = self._tile_view_signature.get(self.config.G_MAP)
        await self.draw_map_tile_by_overlay(
            self.config.G_MAP_CONFIG,
            self.config.G_MAP,
            self.zoomlevel,
            p0,
            p1,
            overlay=False,
            use_mbtiles=self.config.G_MAP_CONFIG[self.config.G_MAP].get("use_mbtiles"),
        )
        current_main_signature = self._tile_view_signature.get(self.config.G_MAP)
        main_view_changed = prev_main_signature != current_main_signature

        overlay_type = self.overlay_order[self.overlay_index]
        if overlay_type == "HEATMAP":
            map_config, map_name = self._get_overlay_map_config_and_name("HEATMAP")
            if map_config and map_name:
                await self.overlay_map(main_view_changed, p0, p1, map_config, map_name)
            return
        if not self._is_time_series_overlay(overlay_type):
            return

        update_funcs = {
            "RAIN": self.maptile_with_values.update_overlay_rainmap_timeline,
            "WIND": self.maptile_with_values.update_overlay_windmap_timeline,
        }
        updated = await self.overlay_map_internal(
            overlay_type=overlay_type,
            main_view_changed=main_view_changed,
            p0=p0,
            p1=p1,
            update_func=update_funcs[overlay_type],
        )
        if overlay_type == "WIND" and updated:
            run_after(
                a_func=self.course.get_course_wind,
                b_func=self.add_course_wind,
            )

    async def overlay_map_internal(
        self,
        overlay_type,
        main_view_changed,
        p0,
        p1,
        update_func,
    ) -> bool:
        """Return True only when display_time changes after the first initialization."""

        map_config, map_name = self._get_overlay_map_config_and_name(overlay_type)
        if map_config is None or map_name is None:
            return False
        map_settings = map_config[map_name]
        self._apply_precomputed_overlay_time(overlay_type, map_name, map_settings)

        await update_func(map_settings, map_name)
        # Compute new/prev display_time
        new_display_time = f"{map_settings['basetime']}/{map_settings['validtime']}"
        prev_display_time = self.overlay_time[overlay_type]["display_time"]
        display_time_changed = prev_display_time != new_display_time

        if display_time_changed or prev_display_time is None:
            await self.update_prev_next_overlay_time(overlay_type, map_config, map_name)

        # If unchanged, just draw overlay and exit
        if not display_time_changed:
            await self.overlay_map(main_view_changed, p0, p1, map_config, map_name)
            return False

        # Changed: record and reset tiles
        self.overlay_time[overlay_type]["display_time"] = new_display_time
        self.reset_overlay(map_name)

        # Return True only if this is not the very first time (prev was already set)
        return prev_display_time is not None

    def reset_overlay(self, map_name):
        self._clear_tile_items(self.config.G_MAP)
        self._clear_tile_items(map_name)
        self.drawn_tile[self.config.G_MAP] = {}
        self.drawn_tile[map_name] = {}
        self.pre_zoomlevel[map_name] = np.nan
        self.set_attribution()

    async def overlay_map(self, main_view_changed, p0, p1, map_config, map_name):
        if main_view_changed:
            self._clear_tile_items(map_name)
            self.drawn_tile[map_name] = {}

        z = (
            self.zoomlevel
            + int(
                self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"]
                / map_config[map_name]["tile_size"]
            )
            - 1
        )
        if (
            map_config[map_name]["min_zoomlevel"]
            <= z
            <= map_config[map_name]["max_zoomlevel"]
        ):
            await self.draw_map_tile_by_overlay(
                map_config, map_name, z, p0, p1, overlay=True
            )
        elif z > map_config[map_name]["max_zoomlevel"]:
            await self.draw_map_tile_by_overlay(
                map_config,
                map_name,
                z,
                p0,
                p1,
                overlay=True,
                expand=True,
            )
        else:
            self.pre_zoomlevel[map_name] = z

    @qasync.asyncSlot()
    async def enable_overlay_time_and_button(self):
        overlay_type = self.overlay_order[self.overlay_index]

        if self._is_time_series_overlay(overlay_type):
            map_config, map_name = self._get_overlay_map_config_and_name(overlay_type)
            if map_config and map_name:
                await self.update_prev_next_overlay_time(
                    overlay_type,
                    map_config,
                    map_name,
                )

        enabled = self._is_time_series_overlay(overlay_type)
        if self.config.display.has_touch:
            self.buttons["prev_time"].setVisible(enabled)
            self.buttons["next_time"].setVisible(enabled)
            if hasattr(self, "time_button_group"):
                self.time_button_group.setVisible(enabled)

    def change_map_overlays(self):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        asyncio.create_task(self._change_map_overlays_async())

    async def _change_map_overlays_async(self):
        while self.overlay_index < len(self.overlay_order):
            self.overlay_index += 1

            if self.overlay_index == len(self.overlay_order):
                self.overlay_index = 0
                break

            overlay_name = self.overlay_order[self.overlay_index]
            if self._is_overlay_enabled(overlay_name):
                break

        self.reset_map()
        await self.enable_overlay_time_and_button()
        await self.update_display()

    def remove_overlay(self):
        if self.overlay_index != 0:
            self.overlay_index = 0
            self.reset_map()

    def enable_overlay_button(self):
        has_overlay = any(
            getattr(self.config, attr_name)
            for attr_name in self._OVERLAY_ENABLED_ATTRS.values()
        )
        self.buttons["layers"].setEnabled(has_overlay)
