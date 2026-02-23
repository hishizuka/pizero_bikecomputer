import numpy as np

from modules._qt_qtwidgets import QtCore, QtGui, QtWidgets, pg
from modules.helper.maptile import (
    JMA_RAIN_COLOR_CONV,
    OPENPORTGUIDE_WIND_STREAM_LEGEND,
    RAINVIEWER_NEXRAD_LEGEND,
    SCW_WIND_SPEED_ARROW_CONV,
)
from modules.utils.geo import get_width_distance


class _FixedScaleBar(QtWidgets.QWidget):
    """Simple scale bar widget for fixed HUD overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_width = 3
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        self.setFixedSize(1, 1)

    def set_bar_size(self, width_px, height_px):
        self.setFixedSize(max(1, int(width_px)), max(1, int(height_px)))
        self.update()

    def paintEvent(self, event):
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        color = QtGui.QColor(0, 0, 0)
        width = max(1, int(self.width()))
        height = max(1, int(self.height()))
        line = max(1, min(int(self._line_width), width, height))

        # Draw filled rectangles to avoid pen clipping on tiny widgets.
        painter.fillRect(0, 0, line, height, color)
        painter.fillRect(width - line, 0, line, height, color)
        painter.fillRect(0, height - line, width, line, color)


class MapHudMixin:
    track_pen = pg.mkPen(color=(0, 170, 255), width=4)
    # UI padding for map HUD elements (scale/attribution/legend) in px.
    hud_padding_px = 6
    hud_scale_height_px = 12
    hud_scale_width_px = 40
    hud_gap_px = 4
    hud_legend_y_offset_px = 5
    hud_legend_width_px = 120
    hud_legend_height_px = 12
    legend_label_values = None
    _legend_img = None
    _legend_spec_key = None
    _fixed_hud_overlay = None
    fixed_attribution_label = None
    fixed_legend_widget = None
    fixed_legend_image_label = None
    fixed_legend_left_label = None
    fixed_legend_right_label = None
    fixed_scale_widget = None
    fixed_scale_bar_widget = None
    fixed_scale_text_label = None
    _last_fixed_attribution_html = None
    _last_fixed_legend_image_key = None
    _last_fixed_scale_text = None
    _last_fixed_scale_bar_size = None
    _fixed_hud_layout_pending = False
    _fixed_hud_size_cache = None
    _fixed_attribution_pos_cache = None
    _fixed_legend_geom_cache = None
    _fixed_scale_geom_cache = None
    _fixed_hud_overlay_dirty = True
    _fixed_legend_layout_dirty = True
    _fixed_scale_layout_dirty = True
    _HUD_TEXT_LABEL_STYLE = (
        "QLabel {"
        "color: #000000;"
        "background-color: rgba(255, 255, 255, 255);"
        "border: 1px solid rgba(255, 255, 255, 255);"
        "padding: 0px;"
        "}"
    )
    _EMPTY_LEGEND_LABEL_HTML = '<span style="font-size: small; color: #000000;"></span>'
    _LEGEND_SPEC_MAP = {
        ("WIND", "openportguide"): (
            OPENPORTGUIDE_WIND_STREAM_LEGEND,
            ["L", "H"],
            9,
        ),
        ("RAIN", "rainviewer"): (RAINVIEWER_NEXRAD_LEGEND, ["L", "H"], 12),
        ("RAIN", "jpn_jma_bousai"): (JMA_RAIN_COLOR_CONV, [0, 80], 20),
    }

    def _setup_hud_items(self):
        self.track_history_plot = self.plot.plot(pen=self.track_pen)
        self.track_tail_plot = self.plot.plot(pen=self.track_pen)
        # Keep compatibility for existing call sites while migrating to dual track layers.
        self.track_plot = self.track_tail_plot

        self.current_point.setZValue(40)
        self.track_history_plot.setZValue(30)
        self.track_tail_plot.setZValue(31)
        self.map_attribution.setZValue(100)

        self.plot.addItem(self.current_point)

        self.map_attribution.textItem.document().setDocumentMargin(0)

        self._last_attribution_text = None

        self._setup_fixed_hud_overlay()

    def _create_fixed_hud_label(self, parent, text_format, alignment):
        label = QtWidgets.QLabel(parent)
        label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        label.setTextFormat(text_format)
        label.setWordWrap(False)
        label.setMargin(0)
        label.setContentsMargins(0, 0, 0, 0)
        label.setAlignment(alignment)
        label.setStyleSheet(self._HUD_TEXT_LABEL_STYLE)
        return label

    def _setup_fixed_hud_overlay(self):
        overlay_parent = self.plot.viewport()
        self._fixed_hud_overlay = QtWidgets.QWidget(overlay_parent)
        self._fixed_hud_overlay.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self._fixed_hud_overlay.setStyleSheet("background: transparent;")

        self.fixed_attribution_label = self._create_fixed_hud_label(
            self._fixed_hud_overlay,
            QtCore.Qt.TextFormat.RichText,
            QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignBottom
        )
        self.fixed_attribution_label.hide()

        self.fixed_legend_widget = QtWidgets.QWidget(self._fixed_hud_overlay)
        self.fixed_legend_widget.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.fixed_legend_widget.setStyleSheet("background: transparent;")

        self.fixed_legend_left_label = self._create_fixed_hud_label(
            self.fixed_legend_widget,
            QtCore.Qt.TextFormat.RichText,
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter,
        )
        self.fixed_legend_right_label = self._create_fixed_hud_label(
            self.fixed_legend_widget,
            QtCore.Qt.TextFormat.RichText,
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter,
        )
        for label in (self.fixed_legend_left_label, self.fixed_legend_right_label):
            label.setText(self._EMPTY_LEGEND_LABEL_HTML)

        self.fixed_legend_image_label = QtWidgets.QLabel(self.fixed_legend_widget)
        self.fixed_legend_image_label.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.fixed_legend_image_label.setMargin(0)
        self.fixed_legend_image_label.setContentsMargins(0, 0, 0, 0)
        self.fixed_legend_image_label.setStyleSheet("background: transparent;")
        self.fixed_legend_widget.hide()

        self.fixed_scale_widget = QtWidgets.QWidget(self._fixed_hud_overlay)
        self.fixed_scale_widget.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self.fixed_scale_widget.setStyleSheet("background: transparent;")

        self.fixed_scale_text_label = self._create_fixed_hud_label(
            self.fixed_scale_widget,
            QtCore.Qt.TextFormat.PlainText,
            QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignBottom
        )
        self.fixed_scale_bar_widget = _FixedScaleBar(self.fixed_scale_widget)

        self._last_fixed_attribution_html = None
        self._last_fixed_legend_image_key = None
        self._last_fixed_scale_text = None
        self._last_fixed_scale_bar_size = None
        self._fixed_hud_layout_pending = False
        self._fixed_hud_size_cache = None
        self._fixed_attribution_pos_cache = None
        self._fixed_legend_geom_cache = None
        self._fixed_scale_geom_cache = None
        self._fixed_hud_overlay_dirty = True
        self._fixed_legend_layout_dirty = True
        self._fixed_scale_layout_dirty = True
        self._layout_fixed_hud_overlay()

    def _invalidate_fixed_hud_layout(self, include_legend=True, include_scale=True):
        self._fixed_hud_overlay_dirty = True
        self._fixed_attribution_pos_cache = None
        if include_legend:
            self._set_fixed_component_dirty("legend")
        if include_scale:
            self._set_fixed_component_dirty("scale")

    def _set_fixed_component_dirty(self, component):
        if component == "legend":
            self._fixed_legend_layout_dirty = True
            self._fixed_legend_geom_cache = None
        elif component == "scale":
            self._fixed_scale_layout_dirty = True
            self._fixed_scale_geom_cache = None

    @staticmethod
    def _set_fixed_widget_visible(widget, visible):
        if widget is None:
            return False
        changed = widget.isVisible() != visible
        widget.setVisible(visible)
        return changed

    def _ensure_fixed_hud_layout(self, include_legend=False, include_scale=False):
        if self._is_fixed_hud_parent_size_stale():
            self._invalidate_fixed_hud_layout(include_legend=True, include_scale=True)
        if self._fixed_hud_overlay_dirty:
            self._layout_fixed_hud_overlay()
        if include_scale and self._fixed_scale_layout_dirty:
            self._layout_fixed_scale_overlay()
        if include_legend and self._fixed_legend_layout_dirty:
            self._layout_fixed_legend_overlay()

    def _is_fixed_hud_parent_size_stale(self):
        overlay = self._fixed_hud_overlay
        if overlay is None:
            return False
        parent = overlay.parentWidget()
        if parent is None:
            return False
        size_key = (parent.width(), parent.height())
        return size_key != self._fixed_hud_size_cache

    def _schedule_fixed_hud_overlay_layout(self):
        if self._fixed_hud_layout_pending:
            return
        self._fixed_hud_layout_pending = True
        QtCore.QTimer.singleShot(0, self._flush_fixed_hud_overlay_layout)

    def _flush_fixed_hud_overlay_layout(self):
        self._fixed_hud_layout_pending = False
        self._layout_fixed_hud_overlay()

    def _layout_fixed_hud_overlay(self):
        overlay = self._fixed_hud_overlay
        if overlay is None:
            return

        parent = overlay.parentWidget()
        if parent is not None:
            size_key = (parent.width(), parent.height())
            if size_key != self._fixed_hud_size_cache:
                overlay.resize(parent.size())
                self._fixed_hud_size_cache = size_key
                self._invalidate_fixed_hud_layout(
                    include_legend=True, include_scale=True
                )
        overlay.raise_()

        label = self.fixed_attribution_label
        if label is not None and label.isVisible():
            x_pos = overlay.width() - label.width() - self.hud_padding_px
            y_pos = overlay.height() - label.height() - self.hud_padding_px
            x_pos = max(0, x_pos)
            y_pos = max(0, y_pos)
            pos_key = (int(x_pos), int(y_pos), label.width(), label.height())
            if pos_key != self._fixed_attribution_pos_cache:
                label.move(int(x_pos), int(y_pos))
                self._fixed_attribution_pos_cache = pos_key
        else:
            self._fixed_attribution_pos_cache = None
        self._fixed_hud_overlay_dirty = False
        if self._fixed_scale_layout_dirty:
            self._layout_fixed_scale_overlay()
        if self._fixed_legend_layout_dirty:
            self._layout_fixed_legend_overlay()

    def update_fixed_attribution_label(self, attribution_html, visible):
        label = self.fixed_attribution_label
        if label is None:
            return

        if attribution_html != self._last_fixed_attribution_html:
            label.setText(attribution_html)
            label.adjustSize()
            self._last_fixed_attribution_html = attribution_html
            self._invalidate_fixed_hud_layout(
                include_legend=True, include_scale=False
            )

        if self._set_fixed_widget_visible(label, visible):
            self._invalidate_fixed_hud_layout(
                include_legend=True, include_scale=False
            )
        self._ensure_fixed_hud_layout(include_legend=True)
        if visible:
            self._schedule_fixed_hud_overlay_layout()

    def _set_fixed_legend_image(self, image_key):
        if self.fixed_legend_image_label is None:
            return
        if self._legend_img is None:
            self.fixed_legend_image_label.clear()
            self.fixed_legend_image_label.resize(0, 0)
            self._last_fixed_legend_image_key = None
            return
        if image_key == self._last_fixed_legend_image_key:
            return

        img = np.ascontiguousarray(self._legend_img)
        height, width, channels = img.shape
        if channels != 4:
            return
        qimage = QtGui.QImage(
            img.data,
            width,
            height,
            channels * width,
            QtGui.QImage.Format.Format_RGBA8888,
        ).copy()
        pixmap = QtGui.QPixmap.fromImage(qimage).scaled(
            int(self.hud_legend_width_px),
            int(self.hud_legend_height_px),
            QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
            QtCore.Qt.TransformationMode.FastTransformation,
        )
        self.fixed_legend_image_label.setPixmap(pixmap)
        self.fixed_legend_image_label.resize(pixmap.size())
        self._last_fixed_legend_image_key = image_key
        self._set_fixed_component_dirty("legend")

    def _set_fixed_legend_label_texts(self, values):
        left_label = self.fixed_legend_left_label
        right_label = self.fixed_legend_right_label
        if left_label is None or right_label is None:
            return
        if not values:
            left_label.setText(self._EMPTY_LEGEND_LABEL_HTML)
            right_label.setText(self._EMPTY_LEGEND_LABEL_HTML)
        else:
            last_value = values[-1]
            left_value = values[0]
            right_value = values[-1]
            is_numeric_left = isinstance(
                left_value, (int, float, np.integer, np.floating)
            )
            is_numeric_right = isinstance(
                right_value, (int, float, np.integer, np.floating)
            )
            left_text = (
                f"{left_value}~"
                if is_numeric_left and left_value == last_value
                else str(left_value)
            )
            right_text = (
                f"{right_value}~"
                if is_numeric_right and right_value == last_value
                else str(right_value)
            )
            left_label.setText(
                '<span style="font-size: small; color: #000000;">'
                + left_text
                + "</span>"
            )
            right_label.setText(
                '<span style="font-size: small; color: #000000;">'
                + right_text
                + "</span>"
            )
        left_label.adjustSize()
        right_label.adjustSize()
        self._set_fixed_component_dirty("legend")

    def _layout_fixed_legend_overlay(self):
        overlay = self._fixed_hud_overlay
        widget = self.fixed_legend_widget
        image_label = self.fixed_legend_image_label
        left_label = self.fixed_legend_left_label
        right_label = self.fixed_legend_right_label
        if (
            overlay is None
            or widget is None
            or image_label is None
            or left_label is None
            or right_label is None
            or not widget.isVisible()
        ):
            self._fixed_legend_geom_cache = None
            self._fixed_legend_layout_dirty = False
            return
        pixmap = image_label.pixmap()
        if pixmap is None or pixmap.isNull():
            self._fixed_legend_geom_cache = None
            self._fixed_legend_layout_dirty = False
            return

        image_size = pixmap.size()
        image_width = image_size.width()
        image_height = image_size.height()

        left_width = left_label.width()
        left_height = left_label.height()
        right_width = right_label.width()
        right_height = right_label.height()

        gap = self.hud_gap_px
        right_edge_gap = self.hud_gap_px
        legend_width = left_width + gap + image_width + gap + right_width
        legend_height = max(image_height, left_height, right_height)

        attribution_height = 0
        if self.fixed_attribution_label is not None and self.fixed_attribution_label.isVisible():
            attribution_height = self.fixed_attribution_label.height()

        x_pos = overlay.width() - self.hud_padding_px - right_edge_gap - legend_width
        y_pos = (
            overlay.height()
            - self.hud_padding_px
            - self.hud_gap_px
            - attribution_height
            - legend_height
            + self.hud_legend_y_offset_px
        )
        x_pos = max(0, x_pos)
        y_pos = max(0, y_pos)
        left_y = int(round((legend_height - left_height) / 2))
        image_y = int(round((legend_height - image_height) / 2))
        right_y = int(round((legend_height - right_height) / 2))
        geom_key = (
            int(x_pos),
            int(y_pos),
            int(legend_width),
            int(legend_height),
            int(left_y),
            int(image_y),
            int(right_y),
            int(left_width),
            int(image_width),
        )
        if geom_key == self._fixed_legend_geom_cache:
            self._fixed_legend_layout_dirty = False
            return
        widget.setGeometry(int(x_pos), int(y_pos), int(legend_width), int(legend_height))

        left_label.move(0, left_y)
        image_label.move(left_width + gap, image_y)
        right_label.move(left_width + gap + image_width + gap, right_y)
        self._fixed_legend_geom_cache = geom_key
        self._fixed_legend_layout_dirty = False

    def draw_scale(self, x_start, y_start):
        del x_start
        scale_factor = 10
        data_per_px_x, data_per_px_y = self._get_view_data_per_px()
        if data_per_px_x > 0 and data_per_px_y > 0:
            scale_width = data_per_px_x * self.hud_scale_width_px
        else:
            scale_width = self.map_area["w"] / scale_factor

        scale_dist = get_width_distance(y_start, scale_width)
        if scale_dist <= 0 or np.isnan(scale_dist):
            return self._fixed_scale_geom_cache
        num = scale_dist / (10 ** int(np.log10(scale_dist)))
        modify = 1
        if 1 < num < 2:
            modify = 2 / num
        elif 2 < num < 5:
            modify = 5 / num
        elif 5 < num < 10:
            modify = 10 / num

        scale_unit = "m"
        scale_label = round(scale_dist * modify)
        if scale_label >= 1000:
            scale_label = int(scale_label / 1000)
            scale_unit = "km"
        scale_text = f"{scale_label}{scale_unit}\n(z{self.zoomlevel})"
        bar_width_px = self.hud_scale_width_px * modify
        bar_height_px = self.hud_scale_height_px
        self._update_fixed_scale_content(scale_text, bar_width_px, bar_height_px)
        self._ensure_fixed_hud_layout(include_scale=True)
        if self._fixed_scale_geom_cache is None:
            self._layout_fixed_scale_overlay()
        return self._fixed_scale_geom_cache

    def _update_fixed_scale_content(self, scale_text, bar_width_px, bar_height_px):
        if self.fixed_scale_text_label is None or self.fixed_scale_bar_widget is None:
            return

        bar_key = (int(round(bar_width_px)), int(round(bar_height_px)))
        if scale_text != self._last_fixed_scale_text:
            self.fixed_scale_text_label.setText(scale_text)
            self.fixed_scale_text_label.adjustSize()
            self._last_fixed_scale_text = scale_text
            self._set_fixed_component_dirty("scale")

        if bar_key != self._last_fixed_scale_bar_size:
            self.fixed_scale_bar_widget.set_bar_size(bar_key[0], bar_key[1])
            self._last_fixed_scale_bar_size = bar_key
            self._set_fixed_component_dirty("scale")

        if self._set_fixed_widget_visible(self.fixed_scale_widget, True):
            self._set_fixed_component_dirty("scale")

    def _layout_fixed_scale_overlay(self):
        overlay = self._fixed_hud_overlay
        scale_widget = self.fixed_scale_widget
        bar_widget = self.fixed_scale_bar_widget
        text_label = self.fixed_scale_text_label
        if (
            overlay is None
            or scale_widget is None
            or bar_widget is None
            or text_label is None
        ):
            self._fixed_scale_layout_dirty = False
            self._fixed_scale_geom_cache = None
            return

        bar_width = bar_widget.width()
        bar_height = bar_widget.height()
        text_width = text_label.width()
        text_height = text_label.height()
        width = max(bar_width, text_width)
        height = text_height + bar_height
        x_pos = self.hud_padding_px
        y_pos = overlay.height() - self.hud_padding_px - height
        x_pos = max(0, int(round(x_pos)))
        y_pos = max(0, int(round(y_pos)))
        text_x = int(round((width - text_width) / 2))
        bar_x = int(round((width - bar_width) / 2))
        geom_key = (
            x_pos,
            y_pos,
            int(width),
            int(height),
            int(text_x),
            int(bar_x),
            int(text_height),
            int(bar_width),
            int(bar_height),
        )
        if geom_key == self._fixed_scale_geom_cache:
            self._fixed_scale_layout_dirty = False
            return

        scale_widget.setGeometry(x_pos, y_pos, int(width), int(height))
        text_label.move(text_x, 0)
        bar_widget.move(bar_x, int(text_height))
        self._fixed_scale_geom_cache = geom_key
        self._fixed_scale_layout_dirty = False

    def update_legend_content(self):
        spec = self._get_legend_spec()
        if spec is None:
            self._legend_spec_key = None
            self._legend_img = None
            self.legend_label_values = None
            self._last_fixed_legend_image_key = None
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
        self._set_fixed_legend_label_texts(self.legend_label_values)
        self._set_fixed_legend_image(spec["key"])

    def draw_legend(self, x_start, y_start, scale_geom):
        del x_start, y_start
        if scale_geom is None or self._legend_spec_key is None:
            self._set_legend_visible(False)
            return

        self._set_legend_visible(True)
        self._ensure_fixed_hud_layout(include_legend=True)

    @staticmethod
    def _build_legend_spec(overlay_type, map_name, colors, label_values, block_width):
        return {
            "key": (overlay_type, map_name, len(colors)),
            "colors": colors,
            "label_values": label_values,
            "block_width": block_width,
            "height": 12,
        }

    def _get_legend_spec(self):
        overlay_type = self.overlay_order[self.overlay_index]
        if overlay_type == "WIND":
            if not self.config.G_USE_WIND_OVERLAY_MAP:
                return None
            map_name = self.config.G_WIND_OVERLAY_MAP
            if map_name.startswith("jpn_scw"):
                return self._build_legend_spec(
                    "WIND",
                    map_name,
                    SCW_WIND_SPEED_ARROW_CONV[:11],
                    [0, 10],
                    20,
                )
        elif overlay_type == "RAIN":
            if not self.config.G_USE_RAIN_OVERLAY_MAP:
                return None
            map_name = self.config.G_RAIN_OVERLAY_MAP
        else:
            return None

        spec = self._LEGEND_SPEC_MAP.get((overlay_type, map_name))
        if spec is None:
            return None
        colors, label_values, block_width = spec
        return self._build_legend_spec(
            overlay_type,
            map_name,
            colors,
            label_values,
            block_width,
        )

    def _set_legend_visible(self, visible):
        if self._set_fixed_widget_visible(self.fixed_legend_widget, visible):
            self._set_fixed_component_dirty("legend")

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

    def draw_map_attribution(self, x_start, y_start):
        del x_start, y_start
        # Fixed attribution does not depend on map movement; relayout only on
        # content/visibility/size changes.
        self._ensure_fixed_hud_layout(include_legend=True)
