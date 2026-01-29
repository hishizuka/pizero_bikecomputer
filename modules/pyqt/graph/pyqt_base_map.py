import numpy as np

from modules._qt_qtwidgets import pg, qasync, Signal, QT_MOUSEBUTTON_LEFTBUTTON
from modules.pyqt.pyqt_screen_widget import ScreenWidget
from .pyqt_map_button import (
    ZoomInButton,
    ZoomOutButton,
    LockButton,
)


class CustomPlotWidget(pg.PlotWidget):
    signal_drag_started = Signal()
    signal_drag_ended = Signal(int, int)
    signal_wheel_scroll = Signal(int)

    def __init__(self):
        super().__init__()
        self._dragging = False
        self._start_pos = None

    def mousePressEvent(self, event):
        if event.button() == QT_MOUSEBUTTON_LEFTBUTTON:
            self._dragging = True
            self._start_pos = event.position().toPoint()
            self.signal_drag_started.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QT_MOUSEBUTTON_LEFTBUTTON and self._dragging:
            self._dragging = False
            end_pos = event.position().toPoint()
            dx = end_pos.x() - self._start_pos.x()
            dy = end_pos.y() - self._start_pos.y()
            self.signal_drag_ended.emit(dx, dy)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        self.signal_wheel_scroll.emit(delta)
        event.accept()

class BaseMapWidget(ScreenWidget):
    max_height = 1
    max_width = 3

    buttons = None
    lock_status = True

    # show range from zoom
    zoom = 2000  # [m]
    zoomlevel = 13  # for MapWidget

    # load course
    course_loaded = False

    # signal for physical button
    signal_move_x_plus = Signal()
    signal_move_x_minus = Signal()
    signal_move_y_plus = Signal()
    signal_move_y_minus = Signal()
    signal_zoom_plus = Signal()
    signal_zoom_minus = Signal()
    signal_change_move = Signal()

    # for change_move
    move_adjust_mode = False
    move_factor = 1.0

    point_color = {
        # 'fix':pg.mkBrush(color=(0,0,160,128)),
        "fix": pg.mkBrush(color=(0, 0, 255)),
        # 'lost':pg.mkBrush(color=(96,96,96,128))
        "lost": pg.mkBrush(color=(170, 170, 170)),
    }

    def __init__(self, parent, config):
        self.buttons = {}
        super().__init__(parent, config)

        self.signal_move_x_plus.connect(self.move_x_plus)
        self.signal_move_x_minus.connect(self.move_x_minus)
        self.signal_move_y_plus.connect(self.move_y_plus)
        self.signal_move_y_minus.connect(self.move_y_minus)
        self.signal_zoom_plus.connect(self.zoom_plus)
        self.signal_zoom_minus.connect(self.zoom_minus)
        self.signal_change_move.connect(self.change_move)

    def setup_ui_extra(self):
        # main graph from pyqtgraph
        if self.config.display.has_touch:
            self.plot = CustomPlotWidget()
            self.plot.signal_drag_started.connect(self.on_drag_started)
            self.plot.signal_drag_ended.connect(self.on_drag_ended)
            self.plot.signal_wheel_scroll.connect(self.on_wheel_scrolled)
        else:
            self.plot = pg.PlotWidget()
        self.plot.setBackground(None)
        self.plot.hideAxis("left")
        self.plot.hideAxis("bottom")

        # current point
        self.current_point = pg.ScatterPlotItem(pxMode=True)
        self.point = {
            "pos": [np.nan, np.nan],
            "size": 20,
            "pen": {"color": "w", "width": 2},
            "brush": self.point_color["lost"],
        }

        # self.plot.setMouseEnabled(x=False, y=False)

        # make buttons
        self.buttons["lock"] = LockButton()
        self.buttons["zoomup"] = ZoomInButton()
        self.buttons["zoomdown"] = ZoomOutButton()
        self.buttons["lock"].clicked.connect(self.switch_lock)
        self.buttons["zoomdown"].clicked.connect(self.zoom_minus)
        self.buttons["zoomup"].clicked.connect(self.zoom_plus)

    # override disable
    def set_minimum_size(self):
        pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # for expanding row
        n = self.layout.rowCount()
        h = int(self.size().height() / n)
        for i in range(n):
            self.layout.setRowMinimumHeight(i, h)

    def lock_off(self):
        self.lock_status = False
        self.buttons["lock"].change_status(self.lock_status)

    def lock_on(self):
        self.lock_status = True
        self.buttons["lock"].change_status(self.lock_status)

    def switch_lock(self):
        if self.lock_status:
            self.lock_off()
        else:
            self.lock_on()

    def change_move(self):
        if not self.move_adjust_mode:
            self.move_factor = 32
            self.move_adjust_mode = True
        else:
            self.move_factor = 1.0
            self.move_adjust_mode = False

    @qasync.asyncSlot()
    async def move_x_plus(self):
        await self.move_x(+self.zoom / 2)

    @qasync.asyncSlot()
    async def move_x_minus(self):
        await self.move_x(-self.zoom / 2)

    @qasync.asyncSlot()
    async def move_y_plus(self):
        await self.move_y(+self.zoom / 2)

    @qasync.asyncSlot()
    async def move_y_minus(self):
        await self.move_y(-self.zoom / 2)

    async def move_x(self, delta):
        self.move_pos["x"] += delta
        await self.update_display()

    async def move_y(self, delta):
        self.move_pos["y"] += delta
        await self.update_display()

    @qasync.asyncSlot()
    async def zoom_plus(self):
        self.zoom /= 2
        self.zoomlevel += 1
        await self.update_display()

    @qasync.asyncSlot()
    async def zoom_minus(self):
        self.zoom *= 2
        self.zoomlevel -= 1
        await self.update_display()

    @qasync.asyncSlot()
    async def on_drag_started(self):
        self.timer.stop()

    @qasync.asyncSlot(int, int)
    async def on_drag_ended(self, dx, dy):
        self.timer.start()

    def on_wheel_scrolled(self, delta):
        if delta > 0:
            self.zoom_plus()
        else:
            self.zoom_minus()
