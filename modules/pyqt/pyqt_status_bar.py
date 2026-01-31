from datetime import datetime
import time

from modules._qt_qtwidgets import (
    QT_ALIGN_CENTER,
    QT_ALIGN_V_CENTER,
    QT_EXPANDING,
    QT_FIXED,
    QT_WA_TRANSPARENT_FOR_MOUSE_EVENTS,
    QtCore,
    QtGui,
    QtWidgets,
)
from modules.helper.bluetooth.bluetooth_manager import check_bnep0
from modules.pyqt.components import icons
from modules.sensor.gps.base import NMEA_MODE_2D, NMEA_MODE_3D


class RecIndicator(QtWidgets.QWidget):
    _state = "hidden"
    _size = 14

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setFixedSize(14, 14)
        self.setAttribute(QT_WA_TRANSPARENT_FOR_MOUSE_EVENTS)
        self.setVisible(False)

    def set_state(self, state):
        if state == self._state:
            return
        self._state = state
        self.setVisible(state != "hidden")
        self.update()

    def paintEvent(self, event):
        if self._state == "hidden":
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)

        cx = (self.width() - self._size) / 2
        cy = (self.height() - self._size) / 2

        if self._state == "recording":
            # Green triangle (play icon)
            painter.setBrush(QtGui.QColor("#2ecc71"))
            triangle = QtGui.QPolygon([
                QtCore.QPoint(int(cx), int(cy)),
                QtCore.QPoint(int(cx), int(cy + self._size)),
                QtCore.QPoint(int(cx + self._size), int(cy + self._size / 2)),
            ])
            painter.drawPolygon(triangle)
        elif self._state == "stop":
            # Red square
            painter.setBrush(QtGui.QColor("#ff4d4d"))
            painter.drawRect(int(cx), int(cy), self._size, self._size)
        elif self._state == "pause":
            # Orange double bars
            painter.setBrush(QtGui.QColor("#f5a623"))
            bar_w = 3
            gap = 2
            total_w = bar_w * 2 + gap
            bar_x = (self.width() - total_w) / 2
            bar_y = cy
            painter.drawRect(int(bar_x), int(bar_y), bar_w, self._size)
            painter.drawRect(int(bar_x + bar_w + gap), int(bar_y), bar_w, self._size)

        painter.end()


class StatusBarWidget(QtWidgets.QWidget):
    BASE_BG_COLOR = "#000000"
    FLASH_YELLOW = "#ffd166"
    STYLES = f"""
      background-color: {BASE_BG_COLOR};
    """

    def __init__(self, parent, config):
        super().__init__(parent=parent)
        self.config = config
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet(self.STYLES)
        self.setSizePolicy(QT_EXPANDING, QT_FIXED)
        self.setFixedHeight(24)

        self._gps_size = 20
        self._bt_size = 20
        self._light_size = 20
        self._icon_cache = {}
        self._bt_cached = False
        self._last_bt_check = 0.0
        self._last_time = ""
        self._flash_token = 0

        self.rec_indicator = RecIndicator(self)
        self.gps_label = QtWidgets.QLabel(self)
        self.bt_label = QtWidgets.QLabel(self)
        self.light_label = QtWidgets.QLabel(self)
        self.time_label = QtWidgets.QLabel(self)

        self.gps_label.setFixedSize(self._gps_size, self._gps_size)
        self.bt_label.setFixedSize(self._bt_size, self._bt_size)
        self.light_label.setFixedSize(self._light_size, self._light_size)

        self.gps_label.setAlignment(QT_ALIGN_CENTER)
        self.bt_label.setAlignment(QT_ALIGN_CENTER)
        self.light_label.setAlignment(QT_ALIGN_CENTER)
        self.time_label.setAlignment(QT_ALIGN_V_CENTER)
        self.time_label.setStyleSheet("color: #f5f5f5;")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)
        layout.addWidget(self.rec_indicator)
        layout.addStretch(1)
        layout.addWidget(self.bt_label)
        layout.addWidget(self.light_label)
        layout.addWidget(self.gps_label)
        layout.addWidget(self.time_label)

        self._timer = QtCore.QTimer(parent=self)
        self._timer.timeout.connect(self.update_status)
        self._timer.start(1000)
        self.update_status()

    def flash_background(self, sequence):
        if not sequence:
            return
        self._flash_token += 1
        token = self._flash_token

        def step(index):
            if token != self._flash_token:
                return
            if index >= len(sequence):
                self._set_background_color(self.BASE_BG_COLOR)
                return
            color, duration = sequence[index]
            self._set_background_color(color)
            QtCore.QTimer.singleShot(int(duration * 1000), lambda: step(index + 1))

        step(0)

    def _set_background_color(self, color):
        # Keep the stylesheet minimal to avoid overriding child styles.
        self.setStyleSheet(f"background-color: {color};")

    def resizeEvent(self, event):
        font = self.time_label.font()
        font.setPixelSize(max(10, int(self.height() * 0.7)))
        font.setBold(True)
        self.time_label.setFont(font)

    def update_status(self):
        self._update_rec()
        self._update_gps()
        self._update_bt()
        self._update_light()
        self._update_time()

    def _update_rec(self):
        manual = getattr(self.config, "G_MANUAL_STATUS", "INIT")
        stopwatch = getattr(self.config, "G_STOPWATCH_STATUS", "INIT")

        if manual == "INIT":
            state = "hidden"
        elif manual == "START":
            state = "pause" if stopwatch == "STOP" else "recording"
        elif manual == "STOP":
            state = "stop"
        else:
            state = "hidden"

        self.rec_indicator.set_state(state)

    def _update_gps(self):
        mode = 0
        try:
            gps_values = self.config.logger.sensor.values.get("GPS")
            if isinstance(gps_values, dict):
                mode = int(gps_values.get("mode", 0))
        except Exception:
            mode = 0
        
        if mode >= NMEA_MODE_3D:
            color = "#2ecc71"
        elif mode == NMEA_MODE_2D:
            color = "#9a9a9a"
        else:
            color = "#00000000"

        pixmap = self._get_icon_pixmap(icons.SatelliteAltIcon, self._gps_size, color)
        self.gps_label.setPixmap(pixmap)

    def _update_bt(self):
        if not self.config.G_IS_RASPI:
            self._bt_cached = False
        else:
            now = time.time()
            if now - self._last_bt_check >= 1.0:
                self._last_bt_check = now
                self._bt_cached = check_bnep0()

        color = "#3da5ff" if self._bt_cached else "#00000000"
        pixmap = self._get_icon_pixmap(icons.BluetoothIcon, self._bt_size, color)
        self.bt_label.setPixmap(pixmap)

    def _update_light(self):
        light_state = None
        try:
            ant_values = self.config.logger.sensor.values.get("ANT+")
            ant_id = self.config.G_ANT.get("ID_TYPE", {}).get("LGT")
            if isinstance(ant_values, dict) and ant_id in ant_values:
                light_values = ant_values.get(ant_id)
                if isinstance(light_values, dict):
                    light_state = light_values.get("light_state")
        except Exception:
            light_state = None

        state = str(light_state) if light_state is not None else "OFF"
        if state == "ON":
            color = "#ffd166"
        elif state == "AUTO":
            color = "#35c98a"
        else:
            color = "#00000000"
        pixmap = self._get_icon_pixmap(icons.LightBeamIcon, self._light_size, color)
        self.light_label.setPixmap(pixmap)

    def _update_time(self):
        now_str = datetime.now().strftime("%H:%M")
        if now_str != self._last_time:
            self._last_time = now_str
            self.time_label.setText(now_str)

    def _get_icon_pixmap(self, icon_cls, size, color):
        cache_key = (icon_cls, size, color)
        pixmap = self._icon_cache.get(cache_key)
        if pixmap is not None:
            return pixmap

        icon = icon_cls(color=color)
        pixmap = icon.pixmap(QtCore.QSize(size, size))
        if pixmap.isNull():
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(QtCore.Qt.GlobalColor.transparent)

        self._icon_cache[cache_key] = pixmap
        return pixmap
