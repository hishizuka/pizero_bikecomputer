from modules.qt._qt_qtwidgets import QT_ALIGN_CENTER, QtCore, QtGui, QtWidgets

from . import icons


class BatteryIndicator(QtWidgets.QLabel):
    NORMAL_COLOR = "#f5f5f5"
    LOW_COLOR = "#ffd166"
    CRITICAL_COLOR = "#ff4d4d"
    CHARGING_COLOR = "#2ecc71"
    TRACK_COLOR = "#555555"
    ICON_WIDTH = 30
    ICON_HEIGHT = 16
    BODY_WIDTH = ICON_WIDTH * 780 / 880
    CHARGING_WIDTH = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        # The two-pixel bottom inset aligns the icon with the text's visible center.
        self.setFixedSize(self.ICON_WIDTH, self.ICON_HEIGHT + 2)
        self._state = None
        self.hide()

    def set_level(self, percentage, charge_state):
        state = (percentage, charge_state)
        if state != self._state:
            self._state = state
            self.setFixedWidth(
                self.ICON_WIDTH
                + (self.CHARGING_WIDTH if charge_state == "charging" else 0)
            )
            self.setPixmap(self._render(percentage, charge_state))
            description = {
                "charging": "Charging",
                "discharging": "Discharging",
                "full": "Fully charged",
                "not_charging": "Not charging",
                "unknown": "Charge state unknown",
            }[charge_state]
            self.setAccessibleName(f"Battery {percentage}%, {description}")
            self.setToolTip(self.accessibleName())
        self.show()

    def _render(self, percentage, charge_state):
        charging = charge_state == "charging"
        if charging:
            color = self.CHARGING_COLOR
        elif percentage < 10:
            color = self.CRITICAL_COLOR
        elif percentage < 20:
            color = self.LOW_COLOR
        else:
            color = self.NORMAL_COLOR
        warning = not charging and percentage < 20

        # Render at device resolution so the small numerals stay sharp on HiDPI screens.
        ratio = self.devicePixelRatioF()
        pixmap = QtGui.QPixmap(
            round(self.width() * ratio), round(self.height() * ratio)
        )
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        offset = self.CHARGING_WIDTH if charging else 0
        bounds = QtCore.QRect(offset, 0, self.ICON_WIDTH, self.ICON_HEIGHT)
        size = bounds.size()
        track = icons.BatteryIcon(
            color="#242424" if warning else self.TRACK_COLOR
        ).pixmap(size)
        foreground = icons.BatteryIcon(color=color).pixmap(size)
        painter.drawPixmap(bounds, track)
        # Use the same silhouette for both layers, without a separate inner border.
        fill_rect = QtCore.QRectF(
            offset, 0, self.BODY_WIDTH * percentage / 100, self.ICON_HEIGHT
        )
        painter.save()
        painter.setClipRect(fill_rect)
        painter.drawPixmap(bounds, foreground)
        painter.restore()

        interior = QtCore.QRectF(offset, 0, self.BODY_WIDTH, self.ICON_HEIGHT)
        font = self.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(color if warning else "#ffffff"))
        painter.drawText(interior, QT_ALIGN_CENTER, str(percentage))
        # Cut the dark numerals out of the filled portion, as in phone status bars.
        painter.save()
        painter.setClipRect(fill_rect)
        painter.setPen(QtGui.QColor("#101010"))
        painter.drawText(interior, QT_ALIGN_CENTER, str(percentage))
        painter.restore()

        if charging:
            bolt = icons.BatteryBoltIcon(color=color).pixmap(QtCore.QSize(8, 12))
            painter.drawPixmap(0, 2, bolt)
        painter.end()
        return pixmap
