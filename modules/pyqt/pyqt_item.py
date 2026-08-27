import numpy as np

from modules._qt_qtwidgets import QT_ALIGN_CENTER, QtCore, QtGui, QtWidgets
from modules.helper.maptile import get_wind_color
from modules.pyqt.graph.pyqtgraph.WindVaneItem import build_wind_vane_picture
from modules.utils import round_half_away_from_zero

UNIT_FONT_SCALE = 0.7
WIND_ITEM_SIZE_SCALE = 0.75


class ItemLabel(QtWidgets.QLabel):
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


class WindItemValue(ItemValue):
    def __init__(self, *args):
        super().__init__(*args)
        self._wind = None
        self._picture_key = None

    def set_wind(self, direction, speed):
        wind = (
            (direction, speed)
            if np.isfinite(direction) and np.isfinite(speed)
            else None
        )
        text = "-" if wind is None else ""
        if wind == self._wind and text == self.text():
            return
        self._wind = wind
        self.setText(text)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._wind is None:
            return

        direction, speed = self._wind
        size = max(
            12,
            int((min(self.width(), self.height()) - 10) * WIND_ITEM_SIZE_SCALE),
        )
        color = tuple(get_wind_color(speed))
        picture_key = (direction, color, size)
        if picture_key != self._picture_key:
            self._picture = build_wind_vane_picture(direction, color, size)
            self._picture_key = picture_key

        bounds = self._picture.boundingRect()
        value_font = self.font()
        unit_font = QtGui.QFont(value_font)
        unit_font.setPixelSize(int(value_font.pixelSize() * UNIT_FONT_SCALE))
        value_text = str(round_half_away_from_zero(speed))
        value_metrics = QtGui.QFontMetricsF(value_font)
        unit_metrics = QtGui.QFontMetricsF(unit_font)
        value_width = value_metrics.horizontalAdvance(value_text)
        unit_width = unit_metrics.horizontalAdvance(self.unit)
        gap = 2
        unit_gap = max(2, int(value_font.pixelSize() * 0.15))
        text_width = value_width + unit_gap + unit_width
        text_scale = min(
            1.0,
            (self.width() - 4 - bounds.width() - gap) / text_width,
        )
        content_width = bounds.width() + gap + text_width * text_scale
        left = (self.width() - content_width) / 2
        baseline = (
            self.height() / 2
            + (value_metrics.ascent() - value_metrics.descent()) / 2
            + 2
        )

        painter = QtGui.QPainter(self)
        painter.save()
        painter.translate(
            left + bounds.width() / 2 - bounds.center().x(),
            self.height() / 2 - bounds.center().y(),
        )
        self._picture.play(painter)
        painter.restore()

        text_left = left + bounds.width() + gap
        painter.save()
        painter.translate(text_left, 0)
        painter.scale(text_scale, 1)
        painter.setPen(self.palette().color(QtGui.QPalette.ColorRole.WindowText))
        painter.setFont(value_font)
        painter.drawText(QtCore.QPointF(0, baseline), value_text)
        painter.setFont(unit_font)
        painter.drawText(QtCore.QPointF(value_width + unit_gap, baseline), self.unit)
        painter.restore()
        painter.end()


class AscDescItemValue(ItemValue):
    def __init__(self, *args):
        super().__init__(*args)
        self._values = None
        self.horizontal_scale = 1.0

    def set_values(self, ascent, descent):
        values = (
            (ascent, descent) if np.isfinite(ascent) and np.isfinite(descent) else None
        )
        text = "-" if values is None else ""
        if values == self._values and text == self.text():
            return
        self._values = values
        self.setText(text)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._values is None:
            return

        ascent, descent = self._values
        value_text = f"{ascent:.0f} / {descent:.0f}"
        unit_text = f" {self.unit}"
        value_font = self.font()
        unit_font = QtGui.QFont(value_font)
        unit_font.setPixelSize(int(value_font.pixelSize() * UNIT_FONT_SCALE))
        value_metrics = QtGui.QFontMetricsF(value_font)
        unit_metrics = QtGui.QFontMetricsF(unit_font)
        value_width = value_metrics.horizontalAdvance(value_text)
        unit_width = unit_metrics.horizontalAdvance(unit_text)
        content_width = value_width + unit_width
        self.horizontal_scale = min(1.0, (self.width() - 4) / content_width)
        left = (self.width() - content_width * self.horizontal_scale) / 2
        baseline = (
            self.height() / 2 + (value_metrics.ascent() - value_metrics.descent()) / 2
        )

        painter = QtGui.QPainter(self)
        painter.translate(left, 0)
        painter.scale(self.horizontal_scale, 1)
        painter.setPen(self.palette().color(QtGui.QPalette.ColorRole.WindowText))
        painter.setFont(value_font)
        painter.drawText(QtCore.QPointF(0, baseline), value_text)
        painter.setFont(unit_font)
        painter.drawText(QtCore.QPointF(value_width, baseline), unit_text)
        painter.end()


#################################
# Item Class
#################################
class Item(QtWidgets.QVBoxLayout):
    value_class = ItemValue

    def __init__(self, config, name, font_size, right_flag, bottom_flag, *args):
        super().__init__(*args)
        self.config = config
        self.name = name

        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)

        self.label = ItemLabel(right_flag, name)
        self.value = self.value_class(right_flag, bottom_flag)
        gui_config = self.config.gui.gui_config
        self.itemformat, self.unittext = gui_config.G_ITEM_DEF[name][0]
        self.value_font_scale = gui_config.G_ITEM_VALUE_FONT_SCALE.get(name, 1.0)

        self.addWidget(self.label)
        self.addWidget(self.value)

        self.update_font_size(font_size)
        empty_value = (
            (np.nan,) * len(self.itemformat)
            if isinstance(self.itemformat, tuple)
            else np.nan
        )
        self.update_value(empty_value)

    def update_value(self, value):
        base_text = self.config.gui.gui_config.format_text(
            self.name,
            value,
            self.config.G_STOPWATCH_STATUS,
            self.itemformat,
            unit_template=self._unit_template,
        )

        new_text = base_text + self._unit_suffix

        # Skip updates when text is unchanged to avoid needless repaints
        if new_text == self._last_value_text:
            return

        self._last_value_text = new_text
        self.value.setText(new_text)

    def update_font_size(self, font_size):
        label_font_size = int(font_size * 0.66)
        value_font_size = int(font_size * self.value_font_scale)
        self.font_size_unit = int(value_font_size * UNIT_FONT_SCALE)
        self._unit_template = (
            f"<span style='font-size: {self.font_size_unit}px;'> {{}}</span>"
        )

        for text, fsize in (
            (self.label, label_font_size),
            (self.value, value_font_size),
        ):
            q = text.font()
            q.setPixelSize(fsize)
            # q.setLetterSpacing(QtGui.QFont.SpacingType.PercentageSpacing, 95)
            # q.setStyleStrategy(QtGui.QFont.NoSubpixelAntialias) # avoid subpixel antialiasing on the fonts if possible
            # q.setStyleStrategy(QtGui.QFont.NoAntialias) # don't antialias the fonts
            text.setFont(q)

        # Refresh cached unit suffix for the new font size and force next repaint
        self._unit_suffix = (
            self._unit_template.format(self.unittext) if self.unittext else ""
        )
        self._last_value_text = None


class WindItem(Item):
    value_class = WindItemValue

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.value.unit = self.config.gui.gui_config.G_UNIT["Wind"][1]
        self.setStretch(0, 1)
        self.setStretch(1, 2)

    def update_value(self, value):
        self.value.set_wind(*value)


class AscDescItem(Item):
    value_class = AscDescItemValue

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.value.unit = self.config.gui.gui_config.G_UNIT["Altitude"][1]

    def update_value(self, value):
        self.value.set_values(*value)
