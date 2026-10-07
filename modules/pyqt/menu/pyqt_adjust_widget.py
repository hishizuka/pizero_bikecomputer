from modules.app_logger import app_logger
from modules.qt._qt_qtwidgets import (
    QT_ALIGN_CENTER,
    QT_ALIGN_RIGHT,
    QT_NO_FOCUS,
    QT_STRONG_FOCUS,
    QtCore,
    QtWidgets,
    qasync,
)
from modules.pyqt.components.icons import ClearIcon, ConfirmIcon

from .pyqt_menu_widget import MenuWidget

##################################
# adjust widgets
##################################


class UnitLabel(QtWidgets.QLabel):
    STYLES = """
      QLabel {
        color: black;
        background-color: transparent;
        padding: 0;
      }
    """

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setStyleSheet(self.STYLES)
        self.setAlignment(QT_ALIGN_CENTER)


class AdjustButton(QtWidgets.QPushButton):
    STYLES = """
      QPushButton{
        color: black;
        background-color: white;
        font-weight: bold;
        padding: 0;
        border: 1px solid black;
        border-radius: 4px;
        outline: 0;
      }

      QPushButton[confirm="true"] {
        background-color: #00AA00;
        border-color: #00AA00;
      }

      QPushButton:pressed, QPushButton:focus {
        background-color: black;
        border-color: black;
        color: white;
      }
    """

    def __init__(self, text="", icon=None, confirm=False):
        super().__init__(text)
        self.icon_class = icon
        self.confirm = confirm
        self.setProperty("confirm", confirm)
        self.setStyleSheet(self.STYLES)
        if icon is not None:
            self.normal_icon = icon(color="black")
            self.active_icon = icon(color="white")
            self.pressed.connect(self.update_icon)
            self.released.connect(self.update_icon)
            self.update_icon()

    def update_icon(self):
        if self.icon_class is not None:
            active = self.confirm or self.isDown() or self.hasFocus()
            self.setIcon(self.active_icon if active else self.normal_icon)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update_icon()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update_icon()


class AdjustEdit(QtWidgets.QLineEdit):
    STYLES = """
      QLineEdit {
        color: black;
        background-color: transparent;
        font-weight: bold;
        padding: 0;
        border: none;
      }
    """

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setReadOnly(True)
        self.setAlignment(QT_ALIGN_RIGHT)
        self.setMaxLength(6)  # need to specify init_extra in each class
        self.setStyleSheet(self.STYLES)
        self.setFocusPolicy(QT_NO_FOCUS)


class AdjustWidget(MenuWidget):
    unit = ""

    def setup_menu(self):
        self.make_menu_layout(QtWidgets.QVBoxLayout)
        self.menu.setStyleSheet("background-color: white;")
        self.value = QtWidgets.QWidget()
        self.value_layout = QtWidgets.QHBoxLayout(self.value)
        self.value_layout.setContentsMargins(0, 0, 0, 0)
        self.display = AdjustEdit("")
        self.display.setAccessibleName("Value")
        self.unit_label = UnitLabel(self.unit)
        self.unit_label.setVisible(bool(self.unit))
        self.value_layout.addWidget(self.display)
        self.value_layout.addWidget(self.unit_label)
        self.display.textChanged.connect(self.update_value_width)
        self.menu_layout.addWidget(self.value, alignment=QT_ALIGN_CENTER)
        self.menu_layout.addStretch(1)

        self.keypad = QtWidgets.QWidget()
        self.keypad_layout = QtWidgets.QGridLayout(self.keypad)
        self.keypad_layout.setContentsMargins(0, 0, 0, 0)
        self.num_buttons = {}
        for i in range(1, 10):
            button = AdjustButton(str(i))
            button.clicked.connect(self.digit_clicked)
            self.num_buttons[i] = button
            self.keypad_layout.addWidget(button, (i - 1) // 3, (i - 1) % 3)

        self.clear_button = AdjustButton(icon=ClearIcon)
        self.clear_button.setAccessibleName("Clear value")
        self.clear_button.clicked.connect(self.clear)
        self.keypad_layout.addWidget(self.clear_button, 3, 0)

        self.num_buttons[0] = AdjustButton("0")
        self.num_buttons[0].clicked.connect(self.digit_clicked)
        self.keypad_layout.addWidget(self.num_buttons[0], 3, 1)

        self.set_button = AdjustButton(icon=ConfirmIcon, confirm=True)
        self.set_button.setAccessibleName("Set value")
        self.set_button.clicked.connect(self.set_value)
        self.keypad_layout.addWidget(self.set_button, 3, 2)
        self.menu_layout.addWidget(self.keypad, alignment=QT_ALIGN_CENTER)
        self.menu_layout.addStretch(1)

        for button in self.keypad.findChildren(AdjustButton):
            button.setFocusPolicy(
                QT_STRONG_FOCUS if self.config.uses_keyboard_navigation else QT_NO_FOCUS
            )

        if self.config.uses_keyboard_navigation:
            self.focus_widget = self.num_buttons[1]

        self.init_extra()
        self.resize(self.parent().size())
        # Size the header before the stack derives its minimum height.
        rows = 9 if self.height() > self.width() else 5
        self.top_bar.setFixedHeight(self.height() // rows)
        self.update_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_layout()

    def update_layout(self):
        width, height = self.width(), self.height()
        portrait = height > width
        content_height = height - self.top_bar.height()
        button_height = max(16, int(min(width * 0.24 / 1.65, content_height * 0.15)))
        button_width = int(button_height * 1.65)
        column_gap = max(4, button_height // 2)
        row_gap = max(3, int(button_height * 0.15))
        self.keypad_layout.setHorizontalSpacing(column_gap)
        self.keypad_layout.setVerticalSpacing(row_gap)
        self.keypad.setFixedSize(
            3 * button_width + 2 * column_gap, 4 * button_height + 3 * row_gap
        )
        for button in self.keypad.findChildren(AdjustButton):
            button.setFixedSize(button_width, button_height)
            font = button.font()
            font.setPixelSize(max(12, int(button_height * 0.68)))
            button.setFont(font)
            icon_size = max(12, int(button_height * 0.7))
            button.setIconSize(QtCore.QSize(icon_size, icon_size))

        font = self.display.font()
        font.setPixelSize(max(18, int(min(width * 0.19, content_height * 0.19))))
        self.display.setFont(font)
        self.display.setFixedHeight(self.display.fontMetrics().height() + 2)
        font = self.unit_label.font()
        font.setPixelSize(max(12, self.display.font().pixelSize() // 2))
        self.unit_label.setFont(font)
        self.value.setFixedHeight(self.display.height())
        self.value_layout.setSpacing(max(4, button_height // 5))
        self.update_value_width()
        # Include the line edit's descent when balancing the visible whitespace.
        self.menu_layout.setContentsMargins(
            0,
            int(content_height * 0.15) if portrait else 0,
            0,
            self.display.fontMetrics().descent(),
        )

    def update_value_width(self):
        self.display.setFixedWidth(
            self.display.fontMetrics().horizontalAdvance(self.display.text() or "0") + 6
        )
        unit_width = (
            self.unit_label.sizeHint().width() + self.value_layout.spacing()
            if self.unit
            else 0
        )
        self.value.setFixedWidth(self.display.width() + unit_width)

    def init_extra(self):
        pass

    def digit_clicked(self):
        clicked_button = self.sender()
        digit_value = int(clicked_button.text())
        if self.display.text() == "0" and digit_value == 0:
            return
        elif self.display.text() == "0" and digit_value != 0:
            self.display.setText("")
        self.display.setText(self.display.text() + str(digit_value))

    @qasync.asyncSlot()
    async def set_value(self):
        value = self.display.text()
        if value == "":
            return
        self.back()
        await self.set_value_extra(int(value))

    async def set_value_extra(self, value):
        pass

    def clear(self):
        self.display.setText("")


class AdjustAltitudeWidget(AdjustWidget):
    unit = "m"

    def init_extra(self):
        self.display.setMaxLength(4)

    async def set_value_extra(self, value):
        await self.sensor_i2c.update_sealevel_pa(value, force=True)


class AdjustWheelCircumferenceWidget(AdjustWidget):
    unit = "mm"

    def init_extra(self):
        self.display.setMaxLength(4)

    async def set_value_extra(self, value):
        pre_v = self.config.G_WHEEL_CIRCUMFERENCE
        v = value / 1000
        self.config.G_WHEEL_CIRCUMFERENCE = v
        app_logger.info(
            f"set G_WHEEL_CIRCUMFERENCE from {pre_v} to {self.config.G_WHEEL_CIRCUMFERENCE}"
        )
        self.config.setting.write_config()

    def preprocess(self):
        self.display.setText(str(int(self.config.G_WHEEL_CIRCUMFERENCE * 1000)))


class AdjustAutoStopCutoffWidget(AdjustWidget):
    unit = "km/h"

    def init_extra(self):
        self.display.setMaxLength(2)

    async def set_value_extra(self, value):
        pre_v = self.config.G_AUTOSTOP_CUTOFF
        v = value / 3.6
        self.config.G_AUTOSTOP_CUTOFF = v
        self.config.G_GPS_SPEED_CUTOFF = v
        app_logger.info(
            f"set G_AUTOSTOP_CUTOFF from {pre_v} to {self.config.G_AUTOSTOP_CUTOFF}"
        )
        self.config.setting.write_config()

    def preprocess(self):
        self.display.setText(str(int(self.config.G_AUTOSTOP_CUTOFF * 3.6)))


class AdjustGrossAverageSpeedWidget(AdjustWidget):
    unit = "km/h"

    def init_extra(self):
        self.display.setMaxLength(2)

    async def set_value_extra(self, value):
        pre_v = self.config.G_GROSS_AVE_SPEED
        self.config.G_GROSS_AVE_SPEED = value
        app_logger.info(
            f"set G_GROSS_AVE_SPEED from {pre_v} to {self.config.G_GROSS_AVE_SPEED}"
        )
        self.config.setting.write_config()

    def preprocess(self):
        self.display.setText(str(int(self.config.G_GROSS_AVE_SPEED)))


class AdjustCPWidget(AdjustWidget):
    unit = "W"

    def init_extra(self):
        self.display.setMaxLength(4)

    async def set_value_extra(self, value):
        self.config.G_POWER_CP = value

    def preprocess(self):
        self.display.setText(str(int(self.config.G_POWER_CP)))


class AdjustWPrimeBalanceWidget(AdjustWidget):
    unit = "J"

    def init_extra(self):
        self.display.setMaxLength(5)

    async def set_value_extra(self, value):
        self.config.G_POWER_W_PRIME = value

    def preprocess(self):
        self.display.setText(str(int(self.config.G_POWER_W_PRIME)))
