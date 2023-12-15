import time

import numpy as np

from modules._pyqt import QT_ALIGN_CENTER, QtWidgets


class ItemLabel(QtWidgets.QLabel):
    right = False

    @property
    def STYLES(self):
        right_border_width = "0px" if self.right else "1px"
        return f"""
            border-width: 0px {right_border_width} 0px 0px;
            border-style: solid;
            border-color: #CCCCCC;
        """

    def __init__(self, right, *__args):
        self.right = right
        super().__init__(*__args)
        self.setAlignment(QT_ALIGN_CENTER)
        self.setStyleSheet(self.STYLES)


class ItemValue(QtWidgets.QLabel):
    bottom = False
    right = False

    @property
    def STYLES(self):
        bottom_border_width = "0px" if self.bottom else "1px"
        right_border_width = "0px" if self.right else "1px"
        return f"""
            border-width: 0px {right_border_width} {bottom_border_width} 0px;
            border-style: solid;
            border-color: #CCCCCC;
        """

    def __init__(self, right, bottom, *__args):
        self.right = right
        self.bottom = bottom
        super().__init__(*__args)
        self.setAlignment(QT_ALIGN_CENTER)
        self.setStyleSheet(self.STYLES)


#################################
# Item Class
#################################
class Item(QtWidgets.QVBoxLayout):
    config = None
    label = None
    value = None
    name = ""

    def __init__(self, config, name, font_size, bottom_flag, right_flag, *args):
        super().__init__(*args)
        self.config = config
        self.name = name

        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)

        self.label = ItemLabel(right_flag, name)
        self.value = ItemValue(right_flag, bottom_flag)

        self.itemformat = self.config.gui.gui_config.G_ITEM_DEF[name][0]

        self.addWidget(self.label)
        self.addWidget(self.value)

        self.update_font_size(font_size)
        self.update_value(np.nan)

    def update_value(self, value):
        if value is None:
            self.value.setText("-")
        elif isinstance(value, str):
            self.value.setText(value)
        elif np.isnan(value):
            self.value.setText("-")
        elif self.name.startswith("Speed"):
            self.value.setText(self.itemformat.format(value * 3.6))  # m/s to km/h
        elif "SPD" in self.name:
            self.value.setText(self.itemformat.format(value * 3.6))  # m/s to km/h
        elif "Dist" in self.name:
            self.value.setText(self.itemformat.format(value / 1000))  # m to km
        elif "DIST" in self.name:
            self.value.setText(self.itemformat.format(value / 1000))  # m to km
        elif "Work" in self.name:
            self.value.setText(self.itemformat.format(value / 1000))  # j to kj
        elif "WRK" in self.name:
            self.value.setText(self.itemformat.format(value / 1000))  # j to kj
        elif (
            "Grade" in self.name or "Glide" in self.name
        ) and self.config.G_STOPWATCH_STATUS != "START":
            self.value.setText("-")
        elif self.itemformat == "timer":
            # fmt = '%H:%M:%S' #default (too long)
            fmt = "%H:%M"
            if value < 3600:
                fmt = "%M:%S"
            self.value.setText(time.strftime(fmt, time.gmtime(value)))
        elif self.itemformat == "time":
            self.value.setText(time.strftime("%H:%M"))
        else:
            self.value.setText(self.itemformat.format(value))

    def update_font_size(self, font_size):
        for text, fsize in zip(
            [self.label, self.value], [int(font_size * 0.66), font_size]
        ):
            q = text.font()
            q.setPixelSize(fsize)
            # q.setStyleStrategy(QtGui.QFont.NoSubpixelAntialias) # avoid subpixel antialiasing on the fonts if possible
            # q.setStyleStrategy(QtGui.QFont.NoAntialias) # don't antialias the fonts
            text.setFont(q)
