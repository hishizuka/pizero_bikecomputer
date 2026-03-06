from modules._qt_qtwidgets import QtCore, QtWidgets, QtGui, qasync

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
        self.text_margin = 5
        self.px = self.text_margin
        self.py = 18
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self._advance)
        self.start_delay_timer = QtCore.QTimer(self)
        self.start_delay_timer.setSingleShot(True)
        self.start_delay_timer.timeout.connect(self._start_scrolling)
        self.timer_interval = 200  # [ms]
        self.start_delay_ms = 2000
        self._speed = 5
        self.textLength = 0
        self.setWordWrap(False)
        self.setStyleSheet(self.STYLES)

    def setText(self, text):
        text = "" if text is None else text
        if text == self.text():
            self.refresh_animation_state(reset_position=False)
            return
        super().setText(text)
        self.refresh_animation_state(reset_position=True)

    def _has_overflow_text(self):
        available_width = max(0, self.width() - self.text_margin * 2)
        return (
            self.config.G_CUESHEET_SCROLL
            and bool(self.text())
            and self.textLength > available_width
        )

    def _needs_scroll(self):
        return self.isVisible() and self._has_overflow_text()

    def _set_idle_position(self):
        self.px = self.text_margin

    def _schedule_scroll_start(self):
        self.timer.stop()
        if not self._needs_scroll():
            self.start_delay_timer.stop()
            return
        self.start_delay_timer.start(self.start_delay_ms)

    def _start_scrolling(self):
        if not self._needs_scroll():
            return
        self.timer.start(self.timer_interval)

    def refresh_animation_state(self, reset_position=False):
        self.textLength = self.fontMetrics().horizontalAdvance(self.text())

        if reset_position:
            self.timer.stop()
            self.start_delay_timer.stop()
            self._set_idle_position()

        if not self._has_overflow_text():
            self.stop_marquee()
            return

        if self._needs_scroll():
            if self.px == self.text_margin:
                if (
                    reset_position
                    or (
                        not self.start_delay_timer.isActive()
                        and not self.timer.isActive()
                    )
                ):
                    self._schedule_scroll_start()
            elif not self.timer.isActive():
                self.timer.start(self.timer_interval)
        else:
            self.timer.stop()
            self.start_delay_timer.stop()

        self.update()

    def stop_marquee(self):
        if self.timer.isActive():
            self.timer.stop()
        if self.start_delay_timer.isActive():
            self.start_delay_timer.stop()
        self._set_idle_position()
        self.update()

    def _advance(self):
        if not self._needs_scroll():
            self.stop_marquee()
            return

        self.px -= self._speed
        if self.px <= -self.textLength:
            self._set_idle_position()
            self._schedule_scroll_start()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_animation_state(reset_position=True)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_animation_state(reset_position=False)

    def hideEvent(self, event):
        self.stop_marquee()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        self.py = int(self.height() * 0.9)
        if not self._needs_scroll():
            painter.drawText(self.text_margin, self.py, self.text())
            return

        painter.drawText(self.px, self.py, self.text())


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
            if isinstance(text, MarqueeLabel):
                text.refresh_animation_state(reset_position=True)


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

    def start(self):
        super().start()
        for elem in self.cuesheet:
            elem.name.refresh_animation_state(reset_position=False)

    def stop(self):
        super().stop()
        for elem in self.cuesheet:
            elem.name.stop_marquee()

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
            #name_text = self.course_points.name[cp_i + i]
            #name_text = self.course_points.notes[cp_i + i]
            cuesheet_item.name.setText(name_text)
