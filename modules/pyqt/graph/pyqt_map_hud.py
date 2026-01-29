import numpy as np

from modules._qt_qtwidgets import pg
from modules.helper.maptile import (
    JMA_RAIN_COLOR_CONV,
    OPENPORTGUIDE_WIND_STREAM_LEGEND,
    RAINVIEWER_NEXRAD_LEGEND,
    SCW_WIND_SPEED_ARROW_CONV,
)
from modules.utils.geo import get_mod_lat, get_width_distance


class MapHudMixin:
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
    scale_lat_round = 2
    # UI padding for map HUD elements (scale/attribution/legend) in px.
    hud_padding_px = 6
    hud_scale_height_px = 8
    hud_scale_width_px = 40
    hud_gap_px = 4
    legend_item = None
    legend_labels = None
    legend_label_values = None
    _legend_img = None
    _legend_layout_cache = None
    _legend_spec_key = None

    def _setup_hud_items(self):
        self.track_plot = self.plot.plot(pen=self.track_pen)
        self.scale_plot = self.plot.plot(pen=self.scale_pen)

        self.current_point.setZValue(40)
        self.track_plot.setZValue(30)
        self.scale_text.setZValue(100)
        self.map_attribution.setZValue(100)

        self.plot.addItem(self.map_attribution)
        self.plot.addItem(self.scale_text)
        self.plot.addItem(self.current_point)

        self.map_attribution.textItem.document().setDocumentMargin(0)
        self.scale_text.textItem.document().setDocumentMargin(0)

        self._last_attribution_text = None
        self._last_scale_key = None

        self.legend_item = pg.ImageItem()
        self.legend_item.setOpts(axisOrder="row-major")
        self.legend_item.setZValue(95)
        self.legend_item.setVisible(False)
        self.plot.addItem(self.legend_item)

        self.legend_labels = self._create_legend_label_items(
            count=2,
            z_value=96,
        )

    def draw_scale(self, x_start, y_start):
        scale_factor = 10
        data_per_px_x, data_per_px_y = self._get_view_data_per_px()
        use_px = data_per_px_x > 0 and data_per_px_y > 0

        if use_px:
            padding_x = data_per_px_x * self.hud_padding_px
            padding_y = data_per_px_y * self.hud_padding_px
            scale_height = data_per_px_y * self.hud_scale_height_px
            scale_width = data_per_px_x * self.hud_scale_width_px
            scale_x1 = x_start + padding_x
            scale_y1 = get_mod_lat(y_start) + padding_y
            scale_y2 = scale_y1 + scale_height
        else:
            scale_width = self.map_area["w"] / scale_factor
            scale_x1 = x_start + self.map_area["w"] / 25
            scale_y1_raw = y_start + self.map_area["h"] / 25
            scale_y2_raw = scale_y1_raw + self.map_area["h"] / 30
            scale_y1 = get_mod_lat(scale_y1_raw)
            scale_y2 = get_mod_lat(scale_y2_raw)

        scale_dist = get_width_distance(y_start, scale_width)
        num = scale_dist / (10 ** int(np.log10(scale_dist)))
        modify = 1
        if 1 < num < 2:
            modify = 2 / num
        elif 2 < num < 5:
            modify = 5 / num
        elif 5 < num < 10:
            modify = 10 / num

        scale_x2 = scale_x1 + scale_width * modify
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
            self.scale_text.setPlainText(f"{scale_label}{scale_unit}\n(z{self.zoomlevel})")
            self._last_scale_key = scale_key
        self.scale_text.setPos((scale_x1 + scale_x2) / 2, scale_y2)
        return scale_x1, scale_x2, scale_y2

    def update_legend_content(self):
        spec = self._get_legend_spec()
        if spec is None:
            self._legend_spec_key = None
            self._legend_img = None
            self.legend_label_values = None
            self._legend_layout_cache = None
            self._set_legend_visible(False)
            return
        if spec["key"] == self._legend_spec_key:
            return

        self._legend_spec_key = spec["key"]
        self.legend_label_values = spec["label_values"]
        self._legend_img = self._build_legend_image(
            spec["colors"],
            block_width=spec["block_width"],
            height=spec["height"],
        )
        self.legend_item.setImage(
            self._legend_img,
            levels=(0, 255),
            axisOrder="row-major",
        )
        self._set_legend_label_texts(self.legend_label_values)
        self._legend_layout_cache = None

    def draw_legend(self, x_start, y_start, scale_geom):
        if not self._should_show_legend(scale_geom):
            self._set_legend_visible(False)
            self._legend_layout_cache = None
            return

        data_per_px_x, data_per_px_y = self._get_view_data_per_px()
        if data_per_px_x == 0 or data_per_px_y == 0:
            return
        padding_x = data_per_px_x * self.hud_padding_px
        padding_y = data_per_px_y * self.hud_padding_px
        gap_mod = data_per_px_y * self.hud_gap_px
        right_edge = x_start + self.map_area["w"] - padding_x
        bottom_mod = get_mod_lat(y_start) + padding_y

        legend_rect, label_positions = self._calc_legend_layout(
            x_start,
            y_start,
            data_per_px_x,
            data_per_px_y,
            legend_width_px=120,
            legend_height_px=12,
            right_edge=right_edge,
            bottom_mod=bottom_mod,
            gap_mod=gap_mod,
            label_items=self.legend_labels,
        )
        layout_cache = self._get_legend_layout_cache(label_positions)
        if self._legend_layout_cache == layout_cache and self.legend_item.isVisible():
            return
        self.legend_item.setRect(legend_rect)
        for item, pos in label_positions:
            item.setPos(*pos)
            item.setVisible(True)
        self.legend_item.setVisible(True)
        self._legend_layout_cache = layout_cache

    def _get_legend_spec(self):
        overlay_type = self.overlay_order[self.overlay_index]
        if (
            overlay_type == "WIND"
            and self.config.G_USE_WIND_OVERLAY_MAP
            and self.config.G_WIND_OVERLAY_MAP.startswith("jpn_scw")
        ):
            return {
                "key": ("WIND", self.config.G_WIND_OVERLAY_MAP, 11),
                "colors": SCW_WIND_SPEED_ARROW_CONV[:11],
                "label_values": [0, 10],
                "block_width": 20,
                "height": 12,
            }
        if (
            overlay_type == "WIND"
            and self.config.G_USE_WIND_OVERLAY_MAP
            and self.config.G_WIND_OVERLAY_MAP == "openportguide"
        ):
            return {
                "key": (
                    "WIND",
                    self.config.G_WIND_OVERLAY_MAP,
                    len(OPENPORTGUIDE_WIND_STREAM_LEGEND),
                ),
                "colors": OPENPORTGUIDE_WIND_STREAM_LEGEND,
                "label_values": ["L", "H"],
                "block_width": 9,
                "height": 12,
            }
        if (
            overlay_type == "RAIN"
            and self.config.G_USE_RAIN_OVERLAY_MAP
            and self.config.G_RAIN_OVERLAY_MAP == "rainviewer"
        ):
            return {
                "key": (
                    "RAIN",
                    self.config.G_RAIN_OVERLAY_MAP,
                    len(RAINVIEWER_NEXRAD_LEGEND),
                ),
                "colors": RAINVIEWER_NEXRAD_LEGEND,
                "label_values": ["L", "H"],
                "block_width": 12,
                "height": 12,
            }
        if (
            overlay_type == "RAIN"
            and self.config.G_USE_RAIN_OVERLAY_MAP
            and self.config.G_RAIN_OVERLAY_MAP == "jpn_jma_bousai"
        ):
            return {
                "key": (
                    "RAIN",
                    self.config.G_RAIN_OVERLAY_MAP,
                    len(JMA_RAIN_COLOR_CONV),
                ),
                "colors": JMA_RAIN_COLOR_CONV,
                "label_values": [0, 80],
                "block_width": 20,
                "height": 12,
            }
        return None

    def _should_show_legend(self, scale_geom):
        return scale_geom is not None and self._legend_spec_key is not None

    def _set_legend_visible(self, visible):
        self.legend_item.setVisible(visible)
        for item in self.legend_labels:
            item.setVisible(visible)

    @staticmethod
    def _build_legend_image(colors, block_width, height):
        img = np.zeros((height, block_width * len(colors), 4), dtype=np.uint8)
        for i, color in enumerate(colors):
            x0 = i * block_width
            img[:, x0 : x0 + block_width, :] = color
        border = np.array([0, 0, 0, 255], dtype=np.uint8)
        for i in range(len(colors)):
            x0 = i * block_width
            x1 = x0 + block_width - 1
            img[0, x0 : x0 + block_width, :] = border
            img[height - 1, x0 : x0 + block_width, :] = border
            img[:, x0, :] = border
            img[:, x1, :] = border
        return img

    def _create_legend_label_items(self, count, z_value):
        labels = []
        for _ in range(count):
            item = pg.TextItem(
                text="",
                anchor=(0.5, 0.5),
                border=(255, 255, 255, 255),
                fill=(255, 255, 255, 255),
                color=(0, 0, 0),
            )
            item.setHtml('<span style="font-size: small; color: #000000;"></span>')
            item.textItem.document().setDocumentMargin(0)
            item.setZValue(z_value)
            item.setVisible(False)
            self.plot.addItem(item)
            labels.append(item)
        return labels

    def _set_legend_label_texts(self, values):
        if not values:
            for item in self.legend_labels:
                item.setHtml('<span style="font-size: small; color: #000000;"></span>')
            return
        last_value = values[-1]
        for i, item in enumerate(self.legend_labels):
            if i >= len(values):
                item.setHtml('<span style="font-size: small; color: #000000;"></span>')
                continue
            value = values[i]
            is_numeric = isinstance(value, (int, float, np.integer, np.floating))
            label = f"{value}~" if is_numeric and value == last_value else str(value)
            item.setHtml(
                '<span style="font-size: small; color: #000000;">' + label + "</span>"
            )

    def _get_view_data_per_px(self):
        view_box = self.plot.getViewBox()
        view_range = view_box.viewRange()
        view_height = view_box.height()
        view_width = view_box.width()
        if view_height <= 0:
            view_height = self.plot.height()
        if view_width <= 0:
            view_width = self.plot.width()
        data_per_px_y = 0
        data_per_px_x = 0
        if view_height > 0:
            data_per_px_y = abs(view_range[1][1] - view_range[1][0]) / view_height
        if view_width > 0:
            data_per_px_x = abs(view_range[0][1] - view_range[0][0]) / view_width
        return data_per_px_x, data_per_px_y

    def _calc_legend_layout(
        self,
        x_start,
        y_start,
        data_per_px_x,
        data_per_px_y,
        legend_width_px,
        legend_height_px,
        right_edge=None,
        bottom_mod=None,
        gap_mod=None,
        label_items=None,
    ):
        legend_width = legend_width_px * data_per_px_x
        legend_height_mod = legend_height_px * data_per_px_y
        if right_edge is None:
            right_edge = x_start + self.map_area["w"]

        if bottom_mod is None:
            bottom_mod = get_mod_lat(y_start)
        attr_height_mod = self.map_attribution.boundingRect().height() * data_per_px_y
        if gap_mod is None:
            gap_mod = self.hud_gap_px * data_per_px_y

        legend_y1 = bottom_mod + attr_height_mod + gap_mod
        legend_y2 = legend_y1 + legend_height_mod

        if label_items is None:
            label_items = self.legend_labels
        left_item = label_items[0]
        right_item = label_items[-1]
        gap_x_mod = self.hud_gap_px * data_per_px_x
        edge_padding_mod = self.hud_gap_px * data_per_px_x
        left_width_mod = left_item.boundingRect().width() * data_per_px_x
        right_width_mod = right_item.boundingRect().width() * data_per_px_x

        legend_x1 = (
            right_edge
            - legend_width
            - gap_x_mod
            - right_width_mod
            - edge_padding_mod
        )
        legend_rect = pg.QtCore.QRectF(
            legend_x1,
            legend_y1,
            legend_width,
            legend_y2 - legend_y1,
        )

        label_y = legend_y1 + (legend_y2 - legend_y1) / 2
        left_x = legend_x1 - gap_x_mod - left_width_mod / 2
        right_x = legend_x1 + legend_width + gap_x_mod + right_width_mod / 2
        return legend_rect, (
            (left_item, (left_x, label_y)),
            (right_item, (right_x, label_y)),
        )

    @staticmethod
    def _get_legend_layout_cache(label_positions):
        def r(v):
            return round(v, 6)

        label_cache = []
        for item, pos in label_positions:
            label_cache.append((item.toPlainText(), r(pos[0]), r(pos[1])))
        return tuple(label_cache)

    def draw_map_attribution(self, x_start, y_start):
        data_per_px_x, data_per_px_y = self._get_view_data_per_px()
        if data_per_px_x > 0 and data_per_px_y > 0:
            padding_x = data_per_px_x * self.hud_padding_px
            padding_y = data_per_px_y * self.hud_padding_px
            x_pos = x_start + self.map_area["w"] - padding_x
            y_pos = get_mod_lat(y_start) + padding_y
        else:
            x_pos = x_start + self.map_area["w"]
            y_pos = get_mod_lat(y_start)
        self.map_attribution.setPos(x_pos, y_pos)
