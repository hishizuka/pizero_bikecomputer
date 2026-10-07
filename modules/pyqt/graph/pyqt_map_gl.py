"""Small QWidget page for the shared GPU map, with CPU image composition."""

from modules.display.sharp_presenter import presenter_paths
from modules._qt_qtwidgets import QtCore, QtGui, QtWidgets
from modules.app_logger import app_logger
from modules.qt_map import MapController, MapImage
from modules.pyqt.components.map_hud_label import MapHudLabel
from .pyqt_map_button import (
    LockButton,
    ZoomInButton,
    ZoomOutButton,
    create_map_controls,
)


class GpuMapWidget(QtWidgets.QWidget):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground)
        self.controller = MapController(config, self)
        self.output = MapImage()
        self.image = QtGui.QImage()
        self.presenter = None
        self.presenter_failed = False
        self.capturing_overlay = False
        self.use_presenter = (
            config.G_USE_PYQT_GPU_MAP_PRESENTER
            and config.G_IS_RASPI
            and config.G_DISPLAY_PARAM["USE_DRM"]
            and not config.show_button_box
            and all(path.exists() for path in presenter_paths().values())
        )
        self._drag = None
        self.buttons = [LockButton(self), ZoomInButton(self), ZoomOutButton(self)]
        self.buttons[0].clicked.connect(self.controller.toggleFollow)
        self.buttons[1].clicked.connect(lambda: self.controller.zoom(1))
        self.buttons[2].clicked.connect(lambda: self.controller.zoom(-1))
        self.controls_layout = QtWidgets.QGridLayout(self)
        self.controls_layout.setContentsMargins(0, 0, 0, 0)
        self.controls_layout.setSpacing(0)
        controls = dict(zip(("lock", "zoomup", "zoomdown"), self.buttons))
        (
            self.button_group_left,
            self.button_group_right,
            self.time_button_group,
        ) = create_map_controls(
            self,
            self.controls_layout,
            controls,
            self.controller,
            self.controller.hasRouteSearch,
        )
        self.route_button = controls.get("go")
        self.layer_button = controls["layers"]
        self.time_buttons = [controls["prev_time"], controls["next_time"]]
        self.hud_overlay = MapHudLabel(self)
        self.fixed_hud = {
            kind: MapHudLabel(self) for kind in ("scale", "attribution", "legend")
        }
        self.controller.followingChanged.connect(self._update_lock)
        self.controller.frameReady.connect(self._render)
        self.controller.errorChanged.connect(self.update)
        self._update_lock()
        config.map.register(self.controller)

    @property
    def lock_status(self):
        return self.controller.following

    def _update_lock(self):
        self.buttons[0].change_status(self.controller.following)
        if self.route_button is not None:
            self.route_button.setEnabled(self.controller.canSearchRoute)

    def _pan(self, dx, dy):
        ratio = self.devicePixelRatioF()
        self.controller.pan(dx * ratio, dy * ratio)

    def start(self):
        if self.use_presenter and not self.presenter_failed and self.presenter is None:
            ratio = self.devicePixelRatioF()
            try:
                from .pyqt_map_presenter import PresentedMap

                self.presenter = PresentedMap(
                    round(self.width() * ratio), round(self.height() * ratio), self
                )
                self.presenter.buffer_available.connect(self._render)
                app_logger.info("PyQt GPU map Sharp presenter enabled")
            except Exception:
                self.presenter_failed = True
                app_logger.exception("PyQt GPU map presenter unavailable; using QImage")
        self.controller.setActive(True)

    def stop(self):
        self._drag = None
        self.controller.setActive(False)
        if self.presenter is not None:
            self.presenter.close()
            self.presenter = None
        self.output.close()
        self.image = QtGui.QImage()
        self.hud_overlay.clear()
        for label in self.fixed_hud.values():
            label.clear()
            label.hide()

    async def close_map(self):
        self.stop()
        await self.controller.close()

    def showEvent(self, event):
        self._resize_map()
        self.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.stop()
        super().hideEvent(event)

    def resizeEvent(self, event):
        if self.presenter is not None:
            self.presenter.close()
            self.presenter = None
        self._resize_map()
        self._layout_controls()
        super().resizeEvent(event)

    def _layout_controls(self):
        self.button_group_left.setVisible(self.controller.pointerControls)
        self.button_group_right.setVisible(self.controller.pointerControls)
        self.layer_button.setEnabled(self.controller.hasOverlays)
        self.time_button_group.setVisible(self.controller.hasTimes)
        if self.route_button is not None:
            self.route_button.setEnabled(self.controller.canSearchRoute)

    def _resize_map(self):
        ratio = self.devicePixelRatioF()
        size = self.size() * ratio
        self.controller.resize(size.width(), size.height(), ratio)

    def event(self, event):
        result = super().event(event)
        if event.type() == QtCore.QEvent.Type.DevicePixelRatioChange:
            self._resize_map()
        return result

    def _render(self):
        try:
            if self.controller.frame is None:
                return
            for button, enabled in zip(
                self.time_buttons,
                (self.controller.hasPreviousTime, self.controller.hasNextTime),
            ):
                button.setEnabled(enabled)
            self._layout_controls()
            for kind, label in self.fixed_hud.items():
                part = self.controller.hud.fixed_parts.get(kind)
                label.setVisible(part is not None)
                if part is not None:
                    image, pos = part
                    label.set_image(image)
                    label.move(pos.toPoint())
                    label.raise_()
            self.hud_overlay.set_image(self.controller.hud.instruction_image)
            self.hud_overlay.setGeometry(
                self.controller.hud.instruction_rect.toAlignedRect()
            )
            self.hud_overlay.raise_()
            self.hud_overlay.show()
            if self.presenter is not None:
                if not self.presenter.render(
                    self.controller.frame, self._overlay_image()
                ):
                    return
            else:
                self.image = self.output.render(self.controller.frame)
                self.update()
        except Exception as exc:
            app_logger.exception("GPU map rendering failed")
            if self.presenter is not None:
                self.presenter.close()
                self.presenter = None
                self.presenter_failed = True
                self._render()
            else:
                self.controller.set_error(str(exc))
                self.controller.setActive(False)
                self.output.close()

    def _overlay_image(self):
        ratio = self.devicePixelRatioF()
        image = QtGui.QImage(
            round(self.width() * ratio),
            round(self.height() * ratio),
            QtGui.QImage.Format.Format_RGBA8888,
        )
        image.setDevicePixelRatio(ratio)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        self.capturing_overlay = True
        try:
            self.render(image)
        finally:
            self.capturing_overlay = False
        return image

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        if not self.capturing_overlay:
            painter.fillRect(self.rect(), QtCore.Qt.GlobalColor.white)
            painter.drawImage(self.rect(), self.image)
        painter.drawImage(self.rect(), self.controller.hud_image)
        if self.controller.error:
            painter.drawText(
                self.rect(),
                int(QtCore.Qt.AlignmentFlag.AlignCenter),
                "地図を描画できません\n" + self.controller.error,
            )

    def mousePressEvent(self, event):
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and not self.controller.following
        ):
            self._drag = event.position()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            if self.controller.following:
                self._drag = None
                return
            delta = event.position() - self._drag
            self._drag = event.position()
            self._pan(delta.x(), delta.y())

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.mouseMoveEvent(event)
            self._drag = None

    def wheelEvent(self, event):
        if self.controller.following:
            event.ignore()
        else:
            self.controller.wheelZoom(event.angleDelta().y())
            event.accept()
