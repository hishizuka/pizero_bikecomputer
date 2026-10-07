"""Shared overlay selection, forecast times, attribution and color conversion."""

from datetime import timedelta
import asyncio

import numpy as np

from modules.helper.maptile import (
    JMA_RAIN_COLOR_CONV,
    OPENPORTGUIDE_WIND_STREAM_LEGEND,
    RAINVIEWER_UNIVERSAL_BLUE_LEGEND,
    SCW_WIND_SPEED_ARROW_CONV,
)
from modules.utils.map import get_rain_time
from modules.utils.time import (
    format_jma_validtime_local,
    format_scw_validtime_local,
    format_unix_validtime_local,
)


def legend_pixels(colors, block_width, height):
    pixels = np.repeat(np.asarray(colors, dtype=np.uint8)[None], block_width, axis=1)
    pixels = np.repeat(pixels, height, axis=0)
    pixels[[0, -1]] = (0, 0, 0, 255)
    pixels[:, ::block_width] = (0, 0, 0, 255)
    pixels[:, block_width - 1 :: block_width] = (0, 0, 0, 255)
    return pixels


class MapOverlays:
    order = ("NONE", "WIND", "RAIN", "HEATMAP")
    attributes = {
        "WIND": ("G_WIND_OVERLAY_MAP_CONFIG", "G_WIND_OVERLAY_MAP"),
        "RAIN": ("G_RAIN_OVERLAY_MAP_CONFIG", "G_RAIN_OVERLAY_MAP"),
        "HEATMAP": ("G_HEATMAP_OVERLAY_MAP_CONFIG", "G_HEATMAP_OVERLAY_MAP"),
    }
    enabled_attributes = {
        "WIND": "G_USE_WIND_OVERLAY_MAP",
        "RAIN": "G_USE_RAIN_OVERLAY_MAP",
        "HEATMAP": "G_USE_HEATMAP_OVERLAY_MAP",
    }

    def __init__(self, config):
        self.config = config
        self.index = 0
        self._time_lock = asyncio.Lock()
        self.time = {
            kind: dict(
                display_time=None,
                prev_time=None,
                next_time=None,
                prev_subdomain=None,
                next_subdomain=None,
            )
            for kind in ("RAIN", "WIND")
        }

    @property
    def kind(self):
        return self.order[self.index]

    def source(self, kind=None):
        attrs = self.attributes.get(self.kind if kind is None else kind)
        return (
            (getattr(self.config, attrs[0]), getattr(self.config, attrs[1]))
            if attrs
            else (None, None)
        )

    def enabled(self, kind):
        attr = self.enabled_attributes.get(kind)
        return getattr(self.config, attr) if attr else True

    @property
    def has_overlays(self):
        return any(self.enabled(kind) for kind in self.enabled_attributes)

    @property
    def has_times(self):
        return self.kind in self.time

    def can_shift_time(self, forward):
        return (
            self.has_times
            and self.time[self.kind]["next_time" if forward else "prev_time"]
            is not None
        )

    def cycle(self):
        for _ in self.order:
            self.index = (self.index + 1) % len(self.order)
            if self.enabled(self.kind):
                break

    @staticmethod
    def refresh_time(kind, settings):
        mode = settings.get("refresh_time_mode")
        if mode is None:
            mode = "cutoff" if kind == "RAIN" else "aligned"
        if mode == "cutoff":
            return get_rain_time(settings)
        current = settings["current_time_func"]()
        delta = current.minute % settings["time_interval"]
        if delta > settings["time_interval"] / 2:
            delta -= settings["time_interval"]
        return (current - timedelta(minutes=delta)).replace(second=0, microsecond=0)

    async def prepare(self, skip_update=False):
        async with self._time_lock:
            kind = self.kind
            maps, name = self.source()
            if maps is None or kind not in self.time or self.config.api is None:
                return
            settings = maps[name]
            if not skip_update:
                settings["_precomputed_current_time"] = self.refresh_time(
                    kind, settings
                )
            values = await self.config.api.maptile_with_values.get_prev_next_validtime(
                kind, maps, name, skip_update=skip_update
            )
            state = self.time[kind]
            for key, value in zip(
                ("prev_time", "prev_subdomain", "next_time", "next_subdomain"), values
            ):
                state[key] = value
            state["display_time"] = f"{settings['basetime']}/{settings['validtime']}"

    async def shift_time(self, forward):
        kind = self.kind
        await self.prepare(skip_update=True)
        if kind != self.kind:
            return
        maps, name = self.source()
        if maps is None or self.kind not in self.time:
            return
        state, settings = self.time[self.kind], maps[name]
        value = state["next_time" if forward else "prev_time"]
        if value is None:
            return
        helper = self.config.api.maptile_with_values
        settings["validtime"] = value
        if name == "rainviewer":
            helper.set_rainviewer_validtime(settings, value)
        elif name.startswith("jpn_scw"):
            settings["subdomain"] = state[
                "next_subdomain" if forward else "prev_subdomain"
            ]
        elif name.startswith("jpn_jma_bousai"):
            base = helper.get_jma_basetime_for_validtime(settings, value)
            if base:
                settings["basetime"] = base
        await self.prepare(skip_update=True)

    def time_text(self, settings):
        _, name = self.source()
        if self.kind == "RAIN":
            if name.startswith("jpn_jma_bousai"):
                return format_jma_validtime_local(
                    settings.get("validtime"), settings.get("time_format")
                )
            if name == "rainviewer":
                return format_unix_validtime_local(settings.get("validtime"))
        if self.kind == "WIND" and name.startswith("jpn_scw"):
            return format_scw_validtime_local(settings.get("validtime"))
        return ""

    def attribution(self):
        text = self.config.G_MAP_CONFIG[self.config.G_MAP].get("attribution", "")
        maps, name = self.source()
        if maps is not None:
            settings = maps[name]
            extra = self.time_text(settings)
            text += (
                "<br />" + settings["attribution"] + (f" ({extra})" if extra else "")
            )
        return text

    def legend(self):
        kind = self.kind
        if kind not in ("RAIN", "WIND") or not self.enabled(kind):
            return None
        _, name = self.source()
        if kind == "WIND" and name.startswith("jpn_scw"):
            colors, labels, width = SCW_WIND_SPEED_ARROW_CONV[:11], [0, 10], 20
        else:
            spec = {
                ("WIND", "openportguide"): (
                    OPENPORTGUIDE_WIND_STREAM_LEGEND,
                    ["L", "H"],
                    9,
                ),
                ("RAIN", "rainviewer"): (
                    RAINVIEWER_UNIVERSAL_BLUE_LEGEND,
                    ["L", "H"],
                    12,
                ),
                ("RAIN", "jpn_jma_bousai"): (JMA_RAIN_COLOR_CONV, [0, 80], 20),
            }.get((kind, name))
            if spec is None:
                return None
            colors, labels, width = spec
        return dict(
            key=(kind, name, len(colors)),
            colors=colors,
            label_values=labels,
            block_width=width,
            height=12,
        )
