from modules.app_logger import app_logger
from modules._qt_qtwidgets import (
    QT_ALIGN_CENTER,
    QT_ALIGN_RIGHT,
    QT_NO_FOCUS,
    QtWidgets,
    qasync,
)
from .pyqt_menu_widget import MenuWidget

##################################
# adjust widgets
##################################


class UnitLabel(QtWidgets.QLabel):
    STYLES = """
      QLabel {
        font-size: 25px;
        padding: 5px;
      }
    """

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setStyleSheet(self.STYLES)
        self.setAlignment(QT_ALIGN_CENTER)


class AdjustButton(QtWidgets.QPushButton):
    STYLES = """
      QPushButton{
        font-size: 15px;
        padding: 2px;
        margin: 1px;
        border: 1px solid #AAAAAA;
        border-radius: 5%;
      }

      QPushButton:pressed{
        background-color: black;
      }

      QPushButton:focus {
        background-color: black;
        color: white;
      }
    """

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setFixedSize(50, 30)
        self.setStyleSheet(self.STYLES)


class AdjustEdit(QtWidgets.QLineEdit):
    STYLES = """
      QLineEdit {
        font-size: 35px;
        padding: 5px;
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
        self.make_menu_layout(QtWidgets.QGridLayout)

        max_width = 5
        horizontal = True
        if self.parent().size().height() > self.parent().size().width():
            horizontal = False
            max_width = 2

        self.display = AdjustEdit("")
        self.menu_layout.addWidget(self.display, 0, 0, 1, max_width)

        unit_label = UnitLabel(self.unit)
        self.menu_layout.addWidget(unit_label, 0, max_width)

        num_buttons = {}
        cols = 5 if horizontal else 3
        grid_position = []
        for i in range(1, 10):
            grid_position.append((1 + (i - 1) // cols, (i - 1) % cols))
        if horizontal:
            grid_position.append((2, 4)) # 0
            grid_position.append((1, 5)) # clear button
            grid_position.append((2, 5)) # set button
        else:
            grid_position.append((4, 1)) # 0
            grid_position.append((4, 0)) # clear button
            grid_position.append((4, 2)) # set button

        for i in [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]:
            num_buttons[i] = AdjustButton(str(i))
            num_buttons[i].clicked.connect(self.digit_clicked)
            self.menu_layout.addWidget(num_buttons[i], *grid_position.pop(0))

        clear_button = AdjustButton("x")
        clear_button.clicked.connect(self.clear)
        self.menu_layout.addWidget(clear_button, *grid_position[0])

        set_button = AdjustButton("Set")
        set_button.clicked.connect(self.set_value)
        self.menu_layout.addWidget(set_button, *grid_position[1])

        if not self.config.display.has_touch:
            self.focus_widget = num_buttons[1]

        self.init_extra()

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
        await self.sensor_i2c.update_sealevel_pa(value)


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

    def preprocess(self):
        self.display.setText(str(int(self.config.G_WHEEL_CIRCUMFERENCE * 1000)))


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
