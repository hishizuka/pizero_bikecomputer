import asyncio

from modules.app_logger import app_logger
from modules._qt_qtwidgets import QtCore, QtWidgets, QtGui, qasync
from modules.pyqt.components import SECONDARY_BACKGROUND_COLOR, icons
from modules.sensor.ble.identity import format_ble_identity
from .pyqt_menu_widget import MenuWidget, ListWidget, ListItemWidget

STATUS_CONNECTED = "connected"
STATUS_CONNECTING = "connecting"
STATUS_DISCONNECTED = "disconnected"
STATUS_INACTIVE = "inactive"


class ConnectionStatusIndicator(QtWidgets.QWidget):
    COLORS = {
        STATUS_CONNECTED: QtGui.QColor("#15904E"),
        STATUS_CONNECTING: QtGui.QColor("#15904E"),
        STATUS_DISCONNECTED: QtGui.QColor("#C33D3D"),
        STATUS_INACTIVE: QtGui.QColor("#8D9791"),
    }
    TOOLTIPS = {
        STATUS_CONNECTED: "Connected",
        STATUS_CONNECTING: "Connecting",
        STATUS_DISCONNECTED: "Disconnected",
        STATUS_INACTIVE: "Not configured or inactive",
    }

    def __init__(self, status=None, parent=None):
        super().__init__(parent=parent)
        self.status = None
        self.angle = 0
        self.setFixedSize(22, 22)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.rotate)
        self.setVisible(False)
        self.set_status(status)

    def set_status(self, status):
        if status == self.status:
            return
        if status not in self.COLORS:
            self.status = None
            self.setVisible(False)
            self.timer.stop()
            return

        self.status = status
        self.setToolTip(self.TOOLTIPS[status])
        self.setVisible(True)
        if status == STATUS_CONNECTING and self.isVisible():
            self.timer.start()
        else:
            self.timer.stop()
        self.update()

    def rotate(self):
        self.angle = (self.angle + 30) % 360
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self.status == STATUS_CONNECTING:
            self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    @staticmethod
    def _rounded_pen(color, width):
        pen = QtGui.QPen(color)
        pen.setWidthF(width)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        return pen

    def paintEvent(self, event):
        if self.status is None:
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        rect = QtCore.QRectF(2.5, 2.5, side - 5, side - 5)
        color = self.COLORS[self.status]

        if self.status == STATUS_CONNECTED:
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(rect)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(self._rounded_pen(QtGui.QColor("#FFFFFF"), 2.0))
            path = QtGui.QPainterPath()
            path.moveTo(side * 0.30, side * 0.51)
            path.lineTo(side * 0.44, side * 0.65)
            path.lineTo(side * 0.70, side * 0.36)
            painter.drawPath(path)
        elif self.status == STATUS_CONNECTING:
            painter.translate(side / 2, side / 2)
            painter.rotate(self.angle)
            painter.translate(-side / 2, -side / 2)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(self._rounded_pen(color, 2.2))
            painter.drawArc(rect, 25 * 16, 125 * 16)
            painter.drawArc(rect, 205 * 16, 125 * 16)
            painter.drawLine(
                QtCore.QPointF(side * 0.69, side * 0.20),
                QtCore.QPointF(side * 0.77, side * 0.31),
            )
            painter.drawLine(
                QtCore.QPointF(side * 0.69, side * 0.20),
                QtCore.QPointF(side * 0.58, side * 0.22),
            )
            painter.drawLine(
                QtCore.QPointF(side * 0.31, side * 0.80),
                QtCore.QPointF(side * 0.23, side * 0.69),
            )
            painter.drawLine(
                QtCore.QPointF(side * 0.31, side * 0.80),
                QtCore.QPointF(side * 0.42, side * 0.78),
            )
        elif self.status == STATUS_DISCONNECTED:
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(rect)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(self._rounded_pen(QtGui.QColor("#FFFFFF"), 2.0))
            painter.drawLine(
                QtCore.QPointF(side * 0.34, side * 0.34),
                QtCore.QPointF(side * 0.66, side * 0.66),
            )
            painter.drawLine(
                QtCore.QPointF(side * 0.66, side * 0.34),
                QtCore.QPointF(side * 0.34, side * 0.66),
            )
        else:
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(self._rounded_pen(color, 1.8))
            painter.drawEllipse(rect)
            painter.drawLine(
                QtCore.QPointF(side * 0.34, side * 0.50),
                QtCore.QPointF(side * 0.66, side * 0.50),
            )


class FullWidthSeparatorListItemWidget(ListItemWidget):
    def get_title_style(self):
        return "padding-left: 14px;"

    def setup_ui(self):
        super().setup_ui()
        if self.has_detail_row:
            self.detail_row.setStyleSheet("")

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        pen = QtGui.QPen(QtGui.QColor("#AAAAAA"))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        y = self.height() - 0.5
        painter.drawLine(QtCore.QPointF(0.5, y), QtCore.QPointF(self.width() - 0.5, y))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        title_size = max(16, min(22, int(self.height() * 0.4)))
        self.resize_label(self.title_label, title_size)
        if self.has_detail_row:
            detail_size = max(14, min(18, int(self.height() * 0.34)))
            self.resize_label(self.detail_label, detail_size)


class SectionListItemWidget(QtWidgets.QWidget):
    BACKGROUND_COLOR = QtGui.QColor(SECONDARY_BACKGROUND_COLOR)

    def __init__(self, parent, title):
        super().__init__(parent=parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        self.label = QtWidgets.QLabel(title)
        self.label.setStyleSheet(
            "color: black; background-color: transparent; letter-spacing: 1px;"
        )
        layout.addWidget(self.label)

    def set_selected(self, selected):
        pass

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), self.BACKGROUND_COLOR)
        super().paintEvent(event)

    def resizeEvent(self, event):
        q = self.label.font()
        q.setPixelSize(max(9, min(12, int(self.height() * 0.48))))
        self.label.setFont(q)
        super().resizeEvent(event)


class SensorActionListItemWidget(FullWidthSeparatorListItemWidget):
    def __init__(
        self,
        parent,
        title,
        action=None,
        button_type="submenu",
        value="",
        enabled=True,
    ):
        self.action = action
        self.button_type = button_type
        self.value = value
        self.toggle_status = False
        super().__init__(parent, title)
        self.onoff_button(enabled)

    def setup_ui(self):
        super().setup_ui()
        self.outer_layout.setStretch(0, 1)
        self.value_label = QtWidgets.QLabel(self.value)
        self.value_label.setContentsMargins(4, 0, 4, 0)
        self.value_label.setStyleSheet("color: #15904E;")
        self.outer_layout.addWidget(self.value_label)
        self.right_icon = None
        if self.button_type == "toggle":
            self.right_icon = icons.MenuToggleIcon(self)
        elif self.button_type == "submenu":
            self.right_icon = icons.MenuRightIcon(self)
        if self.right_icon is not None:
            self.outer_layout.addWidget(self.right_icon)
            self.right_icon.apply_trailing_margin(self.outer_layout)

    def setText(self, text):
        self.title = text
        self.title_label.setText(text)

    def text(self):
        return self.title_label.text()

    def set_value(self, value):
        self.value = value
        self.value_label.setText(value)

    def change_toggle(self, status):
        self.toggle_status = bool(status)
        if self.button_type == "toggle" and self.right_icon is not None:
            self.right_icon.toggle(self.toggle_status, self.selected or self.hasFocus())

    def onoff_button(self, status):
        self.setEnabled(bool(status))
        self.update_selection_style()

    def disable(self):
        self.onoff_button(False)

    def enable(self):
        self.onoff_button(True)

    def update_selection_style(self):
        active = self.selected or self.hasFocus()
        if active:
            style = "color: white;"
        elif not self.isEnabled():
            style = "color: #AAAAAA;"
        else:
            style = ""
        self.setStyleSheet(style)
        self.update()
        if self.right_icon is None:
            return
        if self.button_type == "toggle":
            self.right_icon.toggle(self.toggle_status, active)
        else:
            self.right_icon.hover(active)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_label(
            self.value_label,
            max(14, min(18, int(min(self.width(), self.height()) * 0.3))),
        )


class SensorPairingListItemWidget(SensorActionListItemWidget):
    def get_title_style(self):
        return (
            f"{super().get_title_style()} "
            "padding-top: 2%; border-bottom: 1px solid #AAAAAA;"
        )

    def setup_ui(self):
        super().setup_ui()
        self.protocol_icon = ProtocolIconLabel(parent=self)
        self.outer_layout.insertWidget(0, self.protocol_icon)
        self.status_indicator = ConnectionStatusIndicator(parent=self)
        self.outer_layout.insertWidget(
            self.outer_layout.indexOf(self.right_icon), self.status_indicator
        )
        self.set_pairing()

    def set_pairing(self, protocol=None, sensor_id="", sensor_name=""):
        paired = protocol is not None
        if paired and protocol in ("Bluetooth", "BLE"):
            self.setText(sensor_name or sensor_id)
            self.setToolTip(format_ble_identity(sensor_name, sensor_id))
        elif paired and protocol == "ANT+":
            self.setText(sensor_id)
            self.setToolTip(f"ANT+ {sensor_id}")
        else:
            self.setText("Pair Sensor")
            self.setToolTip("")
        self.set_value("")
        self.value_label.setVisible(False)
        self.right_icon.setVisible(not paired)
        self.protocol_icon.set_protocol(protocol)
        self.update_selection_style()

    def set_connection_status(self, status):
        self.status_indicator.set_status(status)

    def update_selection_style(self):
        super().update_selection_style()
        self.protocol_icon.set_reverse(self.selected or self.hasFocus())


class ProtocolIconLabel(QtWidgets.QLabel):
    ICON_SIZE = 24
    LABEL_WIDTH = 38

    def __init__(self, protocol=None, parent=None):
        super().__init__(parent=parent)
        self.protocol = None
        self.reverse = False
        self.setFixedSize(self.LABEL_WIDTH, self.ICON_SIZE)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setVisible(False)
        self.set_protocol(protocol)

    def set_protocol(self, protocol):
        if protocol == self.protocol:
            return
        self.protocol = protocol
        self.setVisible(protocol is not None)
        self.setToolTip(protocol or "")
        self.update_icon()

    def set_reverse(self, reverse):
        reverse = bool(reverse)
        if reverse == self.reverse:
            return
        self.reverse = reverse
        self.update_icon()

    def update_icon(self):
        self.setContentsMargins(0, 0, 0, 0)
        if self.protocol == "ANT+":
            icon_cls = (
                icons.AntPlusReverseIcon if self.reverse else icons.AntPlusStandardIcon
            )
            color = None
            if icons.ANT_PLUS_ICONS_AVAILABLE:
                # Asymmetric margins shift the wider artwork four pixels right.
                self.setContentsMargins(8, 0, 0, 0)
                self.setText("")
                self.setStyleSheet("")
            else:
                self.clear()
                self.setText("(ANT+)")
                color = "#FFFFFF" if self.reverse else "#000000"
                self.setStyleSheet(
                    f"color: {color}; font-size: 8px; font-weight: bold;"
                )
                return
        elif self.protocol in ("Bluetooth", "BLE"):
            self.setText("")
            self.setStyleSheet("")
            color = "#FFFFFF" if self.reverse else "#000000"
            icon_cls = icons.BluetoothIcon
        else:
            self.clear()
            self.setStyleSheet("")
            return
        self.setPixmap(icons.get_pixmap(icon_cls, self.ICON_SIZE, color))


class SensorMenuWidget(MenuWidget):
    PAGE_ROLES = {
        "Heart Rate": "HR",
        "Speed": "SPD",
        "Cadence": "CDC",
        "Power": "PWR",
        "Light": "LGT",
        "Control": "CTRL",
        "Temperature": "TEMP",
    }
    PAGES = (*PAGE_ROLES, "Internal Sensors")

    def setup_menu(self):
        self.add_buttons(
            tuple(
                (
                    page,
                    "submenu",
                    lambda _checked=False, page=page: self.change_page(
                        page, preprocess=True
                    ),
                )
                for page in self.PAGES
            )
        )
        self.status_indicators = {}
        for page, role in self.PAGE_ROLES.items():
            indicator = ConnectionStatusIndicator(
                self.get_role_connection_status(role),
                parent=self.buttons[page],
            )
            button_layout = self.buttons[page].layout()
            button_layout.insertStretch(0, 1)
            button_layout.insertWidget(1, indicator)
            self.status_indicators[page] = indicator

        self.status_timer = QtCore.QTimer(parent=self)
        self.status_timer.setInterval(500)
        self.status_timer.timeout.connect(self.update_connection_statuses)

    def preprocess(self):
        self.update_connection_statuses()
        self.status_timer.start()

    def on_back_menu(self):
        self.status_timer.stop()

    def get_role_connection_status(self, role):
        if self.config.sensor_uses(role, self.config.SENSOR_PROTOCOL_BLE):
            return self.sensor_ble.get_sensor_connection_status(role)
        return self.sensor_ant.get_sensor_connection_status(role)

    def update_connection_statuses(self):
        for page, role in self.PAGE_ROLES.items():
            self.status_indicators[page].set_status(
                self.get_role_connection_status(role)
            )


class InternalSensorMenuWidget(MenuWidget):
    MAP_HEADING_BUTTON = "Map Magnetic Heading"
    MAG_CALIBRATION_BUTTON = "Mag Calibration"
    PITCH_ROLL_CALIBRATION_BUTTON = "Pitch/Roll Calibration"

    def setup_menu(self):
        gps_action = (
            self.gps_menu if "GPS" in self.config.gui.gui_config.G_GUI_INDEX else None
        )
        button_conf = (
            # Name(page_name), button_attribute, connected functions, layout
            ("GPS", "submenu", gps_action),
            ("Adjust Altitude", "submenu", self.adjust_altitude),
            (
                self.MAP_HEADING_BUTTON,
                "toggle",
                lambda: self.onoff_map_heading(True),
            ),
            (self.MAG_CALIBRATION_BUTTON, "dialog", self.calib_mag),
            (
                self.PITCH_ROLL_CALIBRATION_BUTTON,
                "dialog",
                self.calib_pitch_roll,
            ),
        )
        self.add_buttons(button_conf)
        self.update_button_status()

    def preprocess(self):
        self.update_button_status()

    def gps_menu(self):
        self.change_page("GPS", preprocess=True)

    def adjust_altitude(self):
        self.change_page("Adjust Altitude")

    def onoff_map_heading(self, change=True):
        map_widget = self.config.gui.map_widget
        if map_widget is None:
            self.buttons[self.MAP_HEADING_BUTTON].change_toggle(False)
            return

        if change:
            map_widget.set_map_heading_source(
                not map_widget.use_magnetic_heading_for_map
            )
        self.buttons[self.MAP_HEADING_BUTTON].change_toggle(
            map_widget.use_magnetic_heading_for_map
        )

    def calib_mag(self):
        self.config.gui.calib_mag()
        self.update_button_status()

    def calib_pitch_roll(self):
        self.config.gui.calib_pitch_roll()
        self.update_button_status()

    def update_button_status(self):
        self.onoff_map_heading(change=False)
        self.buttons[self.MAG_CALIBRATION_BUTTON].onoff_button(
            self.sensor_i2c.motion_sensor["MAG"]
        )
        self.buttons[self.PITCH_ROLL_CALIBRATION_BUTTON].onoff_button(
            self.sensor_i2c.motion_sensor["ACC"]
            or self.sensor_i2c.motion_sensor["QUATERNION"]
        )


class SensorConnectionMenuWidget(ListWidget):
    SENSOR_BUTTON = "Sensor"
    REMOVE_SENSOR_BUTTON = "Remove Sensor"
    SENSOR_ROLE = None

    def setup_menu(self):
        super().setup_menu()
        self.list.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.status_timer = QtCore.QTimer(parent=self)
        self.status_timer.setInterval(500)
        self.status_timer.timeout.connect(self.update_connection_status)
        self.refresh_sensor_state()

    def update_list(self):
        self.add_section("SENSOR")
        self.sensor_item = SensorPairingListItemWidget(
            self,
            "Pair Sensor",
            action=self.open_sensor_pairing,
            button_type="submenu",
        )
        self.buttons[self.SENSOR_BUTTON] = self.sensor_item
        self.sensor_list_item = self.add_connection_row(self.sensor_item)

        self.remove_sensor_item = SensorActionListItemWidget(
            self,
            self.REMOVE_SENSOR_BUTTON,
            action=self.confirm_remove_sensor,
            button_type=None,
            enabled=False,
        )
        self.buttons[self.REMOVE_SENSOR_BUTTON] = self.remove_sensor_item
        self.add_connection_row(self.remove_sensor_item)

        extra_items = list(self.extra_button_conf())
        if extra_items:
            self.add_section("SETTINGS")
        for name, button_type, func, *rest in extra_items:
            item = SensorActionListItemWidget(
                self,
                name,
                action=func,
                button_type=button_type,
                enabled=func is not None,
            )
            self.buttons[name] = item
            self.add_connection_row(item)

    def add_section(self, title):
        list_item = QtWidgets.QListWidgetItem(self.list)
        list_item.setData(QtCore.Qt.ItemDataRole.UserRole, "section")
        list_item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
        widget = SectionListItemWidget(self, title)
        self.list.setItemWidget(list_item, widget)

    def add_connection_row(self, widget):
        list_item = QtWidgets.QListWidgetItem(self.list)
        list_item.setData(QtCore.Qt.ItemDataRole.UserRole, "row")
        self.list.setItemWidget(list_item, widget)
        widget.enter_signal.connect(self.button_func)
        return list_item

    def extra_button_conf(self):
        return []

    def preprocess_extra(self):
        self.refresh_sensor_state()
        self.status_timer.start()
        if self.config.uses_keyboard_navigation:
            self.focus_sensor_item()

    def focus_sensor_item(self):
        self.list.setCurrentItem(self.sensor_list_item)
        self.focus_widget = self.sensor_item
        self.sensor_item.setFocus()

    def on_back_menu(self):
        self.status_timer.stop()

    @qasync.asyncSlot()
    async def button_func(self):
        item = self.selected_item
        if item is None or not item.isEnabled():
            return
        action = getattr(item, "action", None)
        if action is None:
            return
        result = action()
        if hasattr(result, "__await__"):
            await result

    def open_sensor_pairing(self):
        if self.config.G_BLE_SENSOR_TYPES[self.SENSOR_ROLE]:
            self.change_page(
                "Pair Sensor Protocol",
                preprocess=True,
                sensor_role=self.SENSOR_ROLE,
            )
            return
        self.open_ant_sensor_pairing()

    def open_ant_sensor_pairing(self):
        if self.sensor_ant.scanner.isUse:
            return
        if not self.sensor_ant.is_transport_available():
            return
        self.change_page(
            "Pair ANT+ Sensor",
            preprocess=True,
            reset=True,
            list_type=self.SENSOR_ROLE,
        )

    def confirm_remove_sensor(self):
        if not self.config.is_sensor_configured(self.SENSOR_ROLE):
            return
        self.config.gui.show_dialog(
            self.remove_sensor,
            "Remove paired sensor?",
        )

    def remove_sensor(self):
        protocol = self.config.G_SENSORS[self.SENSOR_ROLE]["PROTOCOL"]
        write_config = True
        if protocol == self.config.SENSOR_PROTOCOL_ANT:
            if not self.sensor_ant.remove_ant_sensor(self.SENSOR_ROLE):
                return
        elif protocol == self.config.SENSOR_PROTOCOL_BLE:
            self.sensor_ble.remove_ble_sensor(self.SENSOR_ROLE)
            write_config = False
        else:
            return
        if write_config:
            self.config.setting.write_config()
        self.refresh_sensor_state()
        self.list.clearSelection()
        self.selected_item = None
        if self.config.uses_keyboard_navigation:
            self.focus_sensor_item()

    def refresh_sensor_state(self):
        sensor = self.config.G_SENSORS[self.SENSOR_ROLE]
        protocol = sensor["PROTOCOL"]
        paired = self.config.is_sensor_configured(self.SENSOR_ROLE)
        if protocol == self.config.SENSOR_PROTOCOL_ANT:
            sensor_id = f"{sensor['ID']:05d}" if paired else ""
        elif protocol == self.config.SENSOR_PROTOCOL_BLE:
            sensor_id = str(sensor["ID"] or "")
        else:
            sensor_id = ""
        self.sensor_item.set_pairing(
            protocol=protocol if paired else None,
            sensor_id=sensor_id,
            sensor_name=str(sensor["NAME"] or ""),
        )
        ant_pairing_available = (
            self.sensor_ant.is_transport_available()
            and not self.sensor_ant.scanner.isUse
        )
        ble_pairing_available = self.sensor_ble.can_scan_sensor(self.SENSOR_ROLE)
        self.sensor_item.onoff_button(ant_pairing_available or ble_pairing_available)
        self.remove_sensor_item.onoff_button(paired)
        self.update_connection_status()

    def update_connection_status(self):
        if not self.config.is_sensor_configured(self.SENSOR_ROLE):
            status = None
        elif self.config.sensor_uses(self.SENSOR_ROLE, self.config.SENSOR_PROTOCOL_ANT):
            status = self.sensor_ant.get_sensor_connection_status(self.SENSOR_ROLE)
        else:
            status = self.sensor_ble.get_sensor_connection_status(self.SENSOR_ROLE)
        self.sensor_item.set_connection_status(status)

    def resizeEvent(self, event):
        ListWidget.resizeEvent(self, event)
        row_height = self.size_hint.height()
        section_height = max(20, min(26, row_height // 2))
        for index in range(self.list.count()):
            list_item = self.list.item(index)
            if list_item.data(QtCore.Qt.ItemDataRole.UserRole) == "section":
                height = section_height
            else:
                height = row_height
            list_item.setSizeHint(QtCore.QSize(self.top_bar.width(), height))


class HeartRateMenuWidget(SensorConnectionMenuWidget):
    SENSOR_ROLE = "HR"


class CadenceMenuWidget(SensorConnectionMenuWidget):
    SENSOR_ROLE = "CDC"


class PowerMenuWidget(SensorConnectionMenuWidget):
    SENSOR_ROLE = "PWR"


class TemperatureMenuWidget(SensorConnectionMenuWidget):
    SENSOR_ROLE = "TEMP"


class SpeedMenuWidget(SensorConnectionMenuWidget):
    SENSOR_ROLE = "SPD"

    def extra_button_conf(self):
        return [
            ("Wheel Size", "submenu", self.adjust_wheel_circumference),
            ("Auto Stop", "toggle", lambda: self.onoff_auto_stop(True)),
            ("Auto Stop Cutoff", "submenu", self.adjust_autostop_cutoff),
            ("Gross Ave Speed", "submenu", self.adjust_gross_average_speed),
        ]

    def preprocess(self):
        super().preprocess()
        self.onoff_auto_stop(False)

    def refresh_sensor_state(self):
        super().refresh_sensor_state()
        self.onoff_auto_stop(False)

    def adjust_wheel_circumference(self):
        self.change_page("Wheel Size", preprocess=True)

    def adjust_autostop_cutoff(self):
        self.change_page("Auto Stop Cutoff", preprocess=True)

    def adjust_gross_average_speed(self):
        self.change_page("Gross Ave Speed", preprocess=True)

    def onoff_auto_stop(self, change=True):
        if change:
            pre_status = self.config.G_AUTOSTOP_STATUS
            self.config.G_AUTOSTOP_STATUS = not pre_status
            app_logger.info(
                "Auto Stop changed from "
                f"{self.onoff_status_text(pre_status)} to "
                f"{self.onoff_status_text(self.config.G_AUTOSTOP_STATUS)}"
            )
            self.config.logger.sync_stopwatch_status_to_manual()
            self.config.setting.write_config()
        self.buttons["Auto Stop"].change_toggle(self.config.G_AUTOSTOP_STATUS)
        self.buttons["Auto Stop Cutoff"].onoff_button(self.config.G_AUTOSTOP_STATUS)

    @staticmethod
    def onoff_status_text(status):
        return "ON" if status else "OFF"


class LightMenuWidget(SensorConnectionMenuWidget):
    SENSOR_ROLE = "LGT"
    AUTO_CONTROL_BUTTON = "Auto Control"

    def extra_button_conf(self):
        return [
            (
                self.AUTO_CONTROL_BUTTON,
                "toggle",
                lambda: self.onoff_auto_control(True),
            )
        ]

    def onoff_auto_control(self, change=True):
        if change:
            enabled = not self.config.G_AUTO_LIGHT
            self.config.G_AUTO_LIGHT = enabled
            self.sensor_ant.set_auto_light_enabled(enabled)
            self.config.setting.write_config()
        self.buttons[self.AUTO_CONTROL_BUTTON].change_toggle(self.config.G_AUTO_LIGHT)

    def refresh_sensor_state(self):
        super().refresh_sensor_state()
        self.onoff_auto_control(False)

    def update_connection_status(self):
        super().update_connection_status()
        self.buttons[self.AUTO_CONTROL_BUTTON].onoff_button(
            self.sensor_ant.is_sensor_available("LGT")
        )


class SensorProtocolMenuWidget(MenuWidget):
    ANT_BUTTON = "ANT+"
    BLE_BUTTON = "Bluetooth"

    def __init__(self, parent, page_name, config):
        self.sensor_role = None
        super().__init__(parent, page_name, config)

    def setup_menu(self):
        self.add_buttons(
            (
                (self.ANT_BUTTON, "submenu", self.open_ant_pairing),
                (self.BLE_BUTTON, "submenu", self.open_ble_pairing),
            )
        )

    def preprocess(self, sensor_role=None):
        self.sensor_role = sensor_role
        self.buttons[self.ANT_BUTTON].setEnabled(
            bool(
                sensor_role
                and self.sensor_ant.is_transport_available()
                and not self.sensor_ant.scanner.isUse
            )
        )
        self.buttons[self.BLE_BUTTON].setEnabled(
            bool(sensor_role and self.sensor_ble.can_scan_sensor(sensor_role))
        )
        if self.config.uses_keyboard_navigation:
            for name in (self.ANT_BUTTON, self.BLE_BUTTON):
                button = self.buttons[name]
                if button.isEnabled():
                    self.focus_widget = button
                    break

    def open_ant_pairing(self):
        if self.sensor_role is None or not self.buttons[self.ANT_BUTTON].isEnabled():
            return
        self.change_page(
            "Pair ANT+ Sensor",
            preprocess=True,
            reset=True,
            list_type=self.sensor_role,
            paired_return_page=self.back_index_key,
        )

    def open_ble_pairing(self):
        if self.sensor_role is None or not self.buttons[self.BLE_BUTTON].isEnabled():
            return
        self.change_page(
            "Pair BLE Sensor",
            preprocess=True,
            reset=True,
            list_type=self.sensor_role,
            paired_return_page=self.back_index_key,
        )


class ANTListWidget(ListWidget):
    def __init__(self, parent, page_name, config):
        self.ant_sensor_types = {}
        self.paired_return_page = None
        super().__init__(parent, page_name, config)

    def preprocess(self, **kwargs):
        self.paired_return_page = kwargs.pop("paired_return_page", None)
        super().preprocess(**kwargs)

    def setup_menu(self):
        super().setup_menu()
        self.list.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.search_indicator = ConnectionStatusIndicator(
            STATUS_CONNECTING, parent=self
        )
        self.right_button_layout.addWidget(self.search_indicator)
        self.timer = QtCore.QTimer(parent=self)
        self.timer.timeout.connect(self.update_display)

    async def button_func_extra(self):
        if self.selected_item is None:
            return
        if not self.sensor_ant.is_transport_available():
            return

        app_logger.info(f"connect {self.list_type}: {self.selected_item.id}")

        ant_id = int(self.selected_item.id)
        if self.config.sensor_uses(self.list_type, self.config.SENSOR_PROTOCOL_BLE):
            self.sensor_ble.remove_ble_sensor(self.list_type)
        self.sensor_ant.connect_ant_sensor(
            self.list_type,  # sensor type
            ant_id,  # ID
            self.ant_sensor_types[ant_id][0],  # id_type
            self.ant_sensor_types[ant_id][1],  # connection status
        )
        self.sensor_ble.connect_cycling_sensors()
        self.config.setting.write_config()
        if self.paired_return_page is not None:
            self.back_index_key = self.paired_return_page

    def on_back_menu(self):
        self.timer.stop()
        if self.sensor_ant.is_transport_available():
            self.sensor_ant.searcher.stop_search()
        # button update
        back_index_key = self.back_index_key
        gui_index = self.config.gui.gui_config.G_GUI_INDEX
        if back_index_key in gui_index:
            index = gui_index[back_index_key]
            self.parentWidget().widget(index).refresh_sensor_state()
        else:
            app_logger.warning(
                f"on_back_menu skipped update: back_index_key {back_index_key} missing in G_GUI_INDEX"
            )

    def preprocess_extra(self):
        if not self.sensor_ant.is_transport_available():
            return
        self.ant_sensor_types.clear()
        self.sensor_ant.searcher.search(self.list_type)
        self.timer.start(self.config.G_DRAW_INTERVAL)

    def update_display(self):
        if not self.sensor_ant.is_transport_available():
            return
        detected_sensors = self.sensor_ant.searcher.getSearchList()

        for ant_id, ant_type_array in detected_sensors.items():
            if ant_id in self.ant_sensor_types:
                continue

            ant_type, connected = ant_type_array
            ant_id_str = f"{ant_id:05d}"
            self.ant_sensor_types[ant_id] = (ant_type, connected)
            ant_item = ANTListItemWidget(
                self,
                ant_id_str,
                STATUS_CONNECTED if connected else None,
            )
            self.add_list_item(ant_item)
            app_logger.debug(f"Adding ANT+ sensor: {self.list_type} {ant_id_str}")


class ANTListItemWidget(FullWidthSeparatorListItemWidget):
    id = None

    def __init__(self, parent, ant_id, status=None):
        self.id = ant_id
        self.connection_status = status
        super().__init__(parent, ant_id)

    def setup_ui(self):
        super().setup_ui()
        self.outer_layout.setStretch(0, 1)
        self.status_indicator = ConnectionStatusIndicator(
            self.connection_status, parent=self
        )
        self.outer_layout.addWidget(self.status_indicator)
        self.right_icon = icons.MenuRightIcon(self)
        self.outer_layout.addWidget(self.right_icon)
        self.right_icon.apply_trailing_margin(self.outer_layout)
        self.enter_signal.connect(self.parentWidget().button_func)

    def update_selection_style(self):
        super().update_selection_style()
        self.right_icon.hover(self.selected or self.hasFocus())


class BLEListWidget(ListWidget):
    SCAN_TIMEOUT = 10.0

    def __init__(self, parent, page_name, config):
        self.candidates = {}
        self.paired_return_page = None
        self.scan_task = None
        self.scan_generation = 0
        super().__init__(parent, page_name, config)

    def setup_menu(self):
        super().setup_menu()
        self.list.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.search_indicator = ConnectionStatusIndicator(parent=self)
        self.right_button_layout.addWidget(self.search_indicator)

    def preprocess(self, **kwargs):
        self.paired_return_page = kwargs.pop("paired_return_page", None)
        super().preprocess(**kwargs)

    def preprocess_extra(self):
        self.cancel_scan()
        self.candidates.clear()
        self.scan_generation += 1
        generation = self.scan_generation
        self.search_indicator.set_status(STATUS_CONNECTING)
        self.scan_task = asyncio.create_task(self.scan(generation))

    async def scan(self, generation):
        try:
            candidates = await self.sensor_ble.discover_sensors(
                self.list_type, timeout=self.SCAN_TIMEOUT
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            app_logger.warning(f"BLE sensor scan failed: {exc}")
            candidates = []

        if generation != self.scan_generation:
            return
        self.search_indicator.set_status(None)
        if not candidates:
            item = FullWidthSeparatorListItemWidget(self, "No sensors found")
            item.setEnabled(False)
            self.add_list_item(item)
            return

        for candidate in candidates:
            if candidate.identifier in self.candidates:
                continue
            self.candidates[candidate.identifier] = candidate
            item = BLEListItemWidget(self, candidate)
            self.add_list_item(item)
            app_logger.debug(
                f"Adding BLE sensor: {candidate.identifier} " f"{candidate.name or ''}"
            )

        if self.config.uses_keyboard_navigation and self.list.count():
            self.list.setCurrentRow(0)
            item = self.list.itemWidget(self.list.item(0))
            if item is not None:
                item.setFocus()

    async def button_func_extra(self):
        if self.selected_item is None:
            return
        candidate = self.selected_item.candidate
        profiles = candidate.profiles
        profile = profiles[0] if len(profiles) == 1 else None
        if self.config.sensor_uses(self.list_type, self.config.SENSOR_PROTOCOL_ANT):
            self.sensor_ant.remove_ant_sensor(self.list_type)
        self.sensor_ble.set_ble_sensor(
            self.list_type,
            candidate.identifier,
            candidate.name or "",
            profile,
        )
        if self.paired_return_page is not None:
            self.back_index_key = self.paired_return_page

    def cancel_scan(self):
        if self.scan_task is not None and not self.scan_task.done():
            self.scan_task.cancel()
        self.scan_task = None

    def on_back_menu(self):
        self.scan_generation += 1
        self.cancel_scan()
        self.search_indicator.set_status(None)
        back_index_key = self.back_index_key
        gui_index = self.config.gui.gui_config.G_GUI_INDEX
        if back_index_key not in gui_index:
            return
        widget = self.parentWidget().widget(gui_index[back_index_key])
        widget.refresh_sensor_state()


class BLEListItemWidget(FullWidthSeparatorListItemWidget):
    def __init__(self, parent, candidate):
        self.candidate = candidate
        rssi = "" if candidate.rssi is None else f"  {candidate.rssi} dBm"
        detail = f"{candidate.identifier}{rssi}"
        super().__init__(parent, candidate.name or "Unnamed sensor", detail=detail)

    def setup_ui(self):
        super().setup_ui()
        self.outer_layout.setStretch(0, 1)
        self.right_icon = icons.MenuRightIcon(self)
        self.outer_layout.addWidget(self.right_icon)
        self.right_icon.apply_trailing_margin(self.outer_layout)
        self.enter_signal.connect(self.parentWidget().button_func)

    def update_selection_style(self):
        super().update_selection_style()
        self.right_icon.hover(self.selected or self.hasFocus())


class ControlMenuWidget(SensorConnectionMenuWidget):
    SENSOR_ROLE = "CTRL"
    FAKE_TRAINER_BUTTON = "Fake Trainer for Zwift"

    def extra_button_conf(self):
        return [
            (
                self.FAKE_TRAINER_BUTTON,
                "toggle",
                lambda: self.onoff_fake_trainer(True),
            )
        ]

    def preprocess(self):
        super().preprocess()
        self.onoff_fake_trainer(False)

    def refresh_sensor_state(self):
        super().refresh_sensor_state()
        self.onoff_fake_trainer(False)

    def onoff_fake_trainer(self, change=True):
        sensor_ble = self.config.logger.sensor.sensor_ble
        if change:
            sensor_ble.toggle_fake_trainer()

        fake_trainer_status = sensor_ble.is_fake_trainer_running()
        self.buttons[self.FAKE_TRAINER_BUTTON].change_toggle(fake_trainer_status)
