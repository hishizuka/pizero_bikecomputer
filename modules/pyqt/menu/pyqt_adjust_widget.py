from logger import app_logger
from modules._pyqt import QtWidgets, qasync
from .pyqt_menu_widget import MenuWidget

##################################
# adjust widgets
##################################


class AdjustWidget(MenuWidget):
    unit = ""

    def setup_menu(self):
        self.make_menu_layout(QtWidgets.QGridLayout)

        self.display = QtWidgets.QLineEdit("")
        self.display.setReadOnly(True)
        self.display.setAlignment(self.config.gui.gui_config.align_right)
        self.display.setMaxLength(6)  # need to specify init_extra in each class
        self.display.setStyleSheet(
            self.config.gui.style.G_GUI_PYQT_texteditStyle_adjustwidget
        )
        self.display.setFocusPolicy(self.config.gui.gui_config.no_focus)
        self.menu_layout.addWidget(self.display, 0, 0, 1, 5)

        self.unitLabel = QtWidgets.QLabel(self.unit)
        self.unitLabel.setStyleSheet(
            self.config.gui.style.G_GUI_PYQT_labelStyle_adjustwidget
        )
        self.unitLabel.setAlignment(self.config.gui.gui_config.align_center)
        self.menu_layout.addWidget(self.unitLabel, 0, 5)

        self.num_button = {}
        for i in [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]:
            self.num_button[i] = QtWidgets.QPushButton(str(i))
            self.num_button[i].setFixedSize(50, 30)
            self.num_button[i].setStyleSheet(
                self.config.gui.style.G_GUI_PYQT_buttonStyle_adjustwidget
            )
            self.num_button[i].clicked.connect(self.digit_clicked)
            if i == 0:
                self.menu_layout.addWidget(self.num_button[i], 2, 4)
            else:
                self.menu_layout.addWidget(
                    self.num_button[i], 1 + (i - 1) // 5, (i - 1) % 5
                )

        self.clear_button = QtWidgets.QPushButton("x")
        self.clear_button.setFixedSize(50, 30)
        self.clear_button.setStyleSheet(
            self.config.gui.style.G_GUI_PYQT_buttonStyle_adjustwidget
        )
        self.clear_button.clicked.connect(self.clear)
        self.menu_layout.addWidget(self.clear_button, 1, 5)

        self.set_button = QtWidgets.QPushButton("Set")
        self.set_button.setFixedSize(50, 30)
        self.set_button.setStyleSheet(
            self.config.gui.style.G_GUI_PYQT_buttonStyle_adjustwidget
        )
        self.menu_layout.addWidget(self.set_button, 2, 5)
        self.set_button.clicked.connect(self.set_value)

        self.menu.setLayout(self.menu_layout)
        if not self.config.display.has_touch():
            self.focus_widget = self.num_button[1]

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
        value = int(value)
        index = self.config.gui.gui_config.G_GUI_INDEX[self.back_index_key]
        self.config.gui.change_menu_page(index)
        await self.set_value_extra(value)

    async def set_value_extra(self, value):
        pass

    def clear(self):
        self.display.setText("")

    def print_value(self):
        pass


class AdjustAltitudeWidget(AdjustWidget):
    unit = "m"

    def init_extra(self):
        self.display.setMaxLength(4)

    async def set_value_extra(self, value):
        await self.config.logger.sensor.sensor_i2c.update_sealevel_pa(value)


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
