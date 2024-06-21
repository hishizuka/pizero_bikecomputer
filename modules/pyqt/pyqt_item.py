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
            border-color: #AAAAAA;
        """

    def __init__(self, right, *__args):
        self.right = right
        super().__init__(*__args)
        self.setAlignment(QT_ALIGN_CENTER)
        self.setStyleSheet(self.STYLES)


class ItemValue(QtWidgets.QLabel):
    bottom = False
    right = False ## not need

    @property
    def STYLES(self):
        bottom_border_width = "0px" if self.bottom else "1px"
        right_border_width = "0px" if self.right else "1px"
        return f"""
            border-width: 0px {right_border_width} {bottom_border_width} 0px;
            border-style: solid;
            border-color: #AAAAAA;
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
    font_size_unit = 0
    font_size_unit_set = False

    def __init__(self, config, name, font_size, right_flag, bottom_flag, *args):
        super().__init__(*args)
        self.config = config
        self.name = name

        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)

        self.label = ItemLabel(right_flag, name)
        self.value_layout = QtWidgets.QHBoxLayout()
        self.value_layout.setContentsMargins(0, 0, 0, 0)
        self.value_layout.setSpacing(0)

        self.value = ItemValue(right_flag, bottom_flag)
        self.itemformat = self.config.gui.gui_config.G_ITEM_DEF[name][0][0]
        self.unittext = self.config.gui.gui_config.G_ITEM_DEF[name][0][1]

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
        elif self.name.startswith("Speed") or "SPD" in self.name:
            self.value.setText(f"{(value * 3.6):{self.itemformat}}")  # m/s to km/h
        elif "Dist" in self.name or "DIST" in self.name:
            self.value.setText(f"{(value / 1000):{self.itemformat}}")  # m to km
        elif "Work" in self.name or "WRK" in self.name:
            self.value.setText(f"{(value / 1000):{self.itemformat}}")  # j to kj
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
            self.value.setText(f"{value:{self.itemformat}}")
        
        if self.unittext != "":
            if self.font_size_unit_set:
                self.value.setText(
                    self.value.text()
                    + f"<span style='font-size: {self.font_size_unit}px;'> {self.unittext}</span>"
                    )
            else:
                self.value.setText(self.value.text() + f"<font size=small> {self.unittext}</font>")

    def update_font_size(self, font_size):
        if not self.font_size_unit_set and self.font_size_unit != 0:
            self.font_size_unit_set = True
        self.font_size_unit = int(font_size * 0.7)
        
        for text, fsize in zip(
            [self.label, self.value], [int(font_size * 0.66), font_size]
        ):
            q = text.font()
            q.setPixelSize(fsize)
            # q.setLetterSpacing(QtGui.QFont.SpacingType.PercentageSpacing, 95)
            # q.setStyleStrategy(QtGui.QFont.NoSubpixelAntialias) # avoid subpixel antialiasing on the fonts if possible
            # q.setStyleStrategy(QtGui.QFont.NoAntialias) # don't antialias the fonts
            text.setFont(q)
