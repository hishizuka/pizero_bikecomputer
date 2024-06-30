from modules._pyqt import QtCore, QtWidgets, QtGui, qasync

from .pyqt_screen_widget import ScreenWidget

#################################
# values only widget
#################################


# https://stackoverflow.com/questions/46505130/creating-a-marquee-effect-in-pyside/
class MarqueeLabel(QtWidgets.QLabel):
    STYLES = """
      QLabel {
        border-bottom: 1px solid #CCCCCC;
      }
    """

    def __init__(self, config, parent=None):
        QtWidgets.QLabel.__init__(self, parent)
        self.config = config
        self.px = 0
        self.py = 18
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer_interval = 200  # [ms]
        self._speed = 5
        self.textLength = 0
        self.setWordWrap(False)
        self.setStyleSheet(self.STYLES)

    def setText(self, text):
        super().setText(text)
        self.textLength = self.fontMetrics().horizontalAdvance(text)
        if self.textLength > self.width() and self.config.G_CUESHEET_SCROLL:
            self.timer.start(self.timer_interval)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        self.py = int(self.height() * 0.9)
        if self.textLength <= self.width() or not self.config.G_CUESHEET_SCROLL:
            painter.drawText(self.px + 5, self.py, self.text())
            return

        if self.px <= -self.fontMetrics().horizontalAdvance(self.text()):
            self.px = self.width()
        painter.drawText(self.px, self.py, self.text())
        painter.translate(self.px, 0)
        self.px -= self._speed


class DistanceLabel(QtWidgets.QLabel):
    STYLES = """
      QLabel {
        padding: 0px 0px 0px 0px;
      }
    """

    def __init__(self, *__args):
        super().__init__(*__args)
        self.setWordWrap(False)
        self.setStyleSheet(self.STYLES)


class CueSheetItem(QtWidgets.QVBoxLayout):
    dist = None
    name = None

    dist_num = 0

    def __init__(self, parent, config):
        self.config = config

        QtWidgets.QVBoxLayout.__init__(self)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)

        self.dist = DistanceLabel()
        self.name = MarqueeLabel(self.config)

        self.addWidget(self.dist)
        self.addWidget(self.name)

    def reset(self):
        self.dist.setText("")
        self.name.setText("")

    def update_font_size(self, font_size):
        for text, fsize in zip(
            [self.dist, self.name], [int(font_size * 0.9), font_size]
        ):
            q = text.font()
            q.setPixelSize(fsize)
            # q.setStyleStrategy(QtGui.QFont.NoSubpixelAntialias) #avoid subpixel antialiasing on the fonts if possible
            # q.setStyleStrategy(QtGui.QFont.NoAntialias) #don't antialias the fonts
            text.setFont(q)


class CueSheetWidget(ScreenWidget):
    STYLES = """
      border-color: #000000;
      border-style: solid;
      border-width: 0px 0px 0px 1px;
    """

    cuesheet = None
    layout_class = QtWidgets.QVBoxLayout

    def __init__(self, parent, config, item_layout=None):
        s = config.display.resolution
        if s[0] < s[1]:
            config.G_CUESHEET_DISPLAY_NUM = 5
        super().__init__(parent, config, item_layout)

    def set_font_size(self, length):
        self.font_size = int(length / 7)

    def setup_ui_extra(self):
        self.cuesheet = []
        self.setStyleSheet(self.STYLES)

        for i in range(self.config.G_CUESHEET_DISPLAY_NUM):
            cuesheet_point_layout = CueSheetItem(self, self.config)
            self.cuesheet.append(cuesheet_point_layout)
            self.layout.addLayout(cuesheet_point_layout)

    def reset(self):
        for elem in self.cuesheet:
            elem.reset()

    def resizeEvent(self, event):
        self.set_font_size(min(self.size().height(), self.size().width()))
        for i in self.cuesheet:
            i.update_font_size(int(self.font_size))  # for 3 rows

    @qasync.asyncSlot()
    async def update_display(self):
        if not self.course_points.is_set or not self.config.G_CUESHEET_DISPLAY_NUM:
            return

        cp_i = self.course.index.course_points_index

        # cuesheet
        for i, cuesheet_item in enumerate(self.cuesheet):
            if cp_i + i > len(self.course_points.distance) - 1:
                cuesheet_item.reset()
                continue
            dist = cuesheet_item.dist_num = (
                self.course_points.distance[cp_i + i] * 1000
                - self.course.index.distance
            )
            if dist < 0:
                continue
            dist_text = f"{dist / 1000:4.1f}km " if dist > 1000 else f"{dist:6.0f}m  "
            cuesheet_item.dist.setText(dist_text)
            name_text = self.course_points.type[cp_i + i]
            cuesheet_item.name.setText(name_text)
