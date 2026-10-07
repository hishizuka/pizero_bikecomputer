from modules.qt._qt_qtwidgets import QtCore, QtWidgets, pg
from modules.map.content import scale_content
from modules.map.style import MAP_LAYER_ORDER, TRACK_COLOR, TRACK_WIDTH
from modules.qt.qt_map_hud import (
    attribution_image,
    hud_position,
    legend_image,
    scale_image,
)
from modules.pyqt.components.map_hud_label import MapHudLabel


class MapHudMixin:
    hud_scale_width_px = 40
    _fixed_hud_overlay = None
    _legend_spec_key = None

    def _setup_hud_items(self):
        self.track_pen = pg.mkPen(
            color=TRACK_COLOR, width=TRACK_WIDTH * self.devicePixelRatioF()
        )
        self.track_history_plot = self.plot.plot(pen=self.track_pen)
        self.track_history_plot.curve.setCacheMode(
            QtWidgets.QGraphicsItem.CacheMode.DeviceCoordinateCache
        )
        self.track_tail_plot = self.plot.plot(pen=self.track_pen)
        self.current_point.setZValue(MAP_LAYER_ORDER["position"])
        self.track_history_plot.setZValue(MAP_LAYER_ORDER["history"])
        self.track_tail_plot.setZValue(MAP_LAYER_ORDER["tail"])
        self.plot.addItem(self.current_point)
        self._setup_fixed_hud_overlay()

    def _setup_fixed_hud_overlay(self):
        self._fixed_hud_overlay = QtWidgets.QWidget(self)
        self._fixed_hud_overlay.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._fixed_hud_overlay.setStyleSheet("background: transparent;")
        (
            self.fixed_attribution_label,
            self.fixed_legend_widget,
            self.fixed_scale_widget,
        ) = (MapHudLabel(self._fixed_hud_overlay) for _ in range(3))
        self._layout_fixed_hud_overlay()

    def _layout_fixed_hud_overlay(self):
        overlay = self._fixed_hud_overlay
        if overlay is None:
            return
        overlay.resize(overlay.parentWidget().size())
        overlay.raise_()
        attribution = self.fixed_attribution_label
        attribution_height = attribution.height() if attribution.isVisible() else 0
        for kind, label in (
            ("attribution", attribution),
            ("scale", self.fixed_scale_widget),
            ("legend", self.fixed_legend_widget),
        ):
            label.move(
                hud_position(
                    kind,
                    QtCore.QSizeF(label.size()),
                    overlay.width(),
                    overlay.height(),
                    attribution_height,
                ).toPoint()
            )

    def update_fixed_attribution_label(self, attribution_text, visible):
        self.fixed_attribution_label.set_image(
            attribution_image(attribution_text, self.devicePixelRatioF())
        )
        self.fixed_attribution_label.setVisible(visible and bool(attribution_text))
        self._layout_fixed_hud_overlay()

    def draw_scale(self, latitude):
        data_per_px_x, data_per_px_y = self._get_view_data_per_px()
        longitude_per_pixel = (
            data_per_px_x
            if data_per_px_x > 0 and data_per_px_y > 0
            else self.map_area["w"] / 10 / self.hud_scale_width_px
        )
        scale = scale_content(
            latitude, longitude_per_pixel, self.zoomlevel, self.hud_scale_width_px
        )
        if scale is None:
            return
        text, width = scale
        self.fixed_scale_widget.set_image(
            scale_image(text, width, self.devicePixelRatioF())
        )
        self.fixed_scale_widget.show()
        self._layout_fixed_hud_overlay()

    def update_legend_content(self):
        spec = self.config.map.overlays.legend()
        self._legend_spec_key = None if spec is None else spec["key"]
        if spec is None:
            self.fixed_legend_widget.hide()
            return
        self.fixed_legend_widget.set_image(legend_image(spec, self.devicePixelRatioF()))

    def draw_legend(self):
        self.fixed_legend_widget.setVisible(
            not self.fixed_scale_widget.isHidden() and self._legend_spec_key is not None
        )
        self._layout_fixed_hud_overlay()

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
