import numpy as np

from modules._qt_qtwidgets import pg, qasync, Signal
from modules.pyqt.pyqt_screen_widget import ScreenWidget
from .pyqt_map_button import (
    ZoomInButton,
    ZoomOutButton,
    LockButton,
    ArrowNorthButton,
    ArrowSouthButton,
    ArrowWestButton,
    ArrowEastButton,
)


class BaseMapWidget(ScreenWidget):
    max_height = 1
    max_width = 3

    buttons = None
    lock_status = True
    button_press_count = None

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
        self.button_press_count = {}
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
        self.buttons["left"] = ArrowWestButton()
        self.buttons["right"] = ArrowEastButton()
        self.buttons["up"] = ArrowNorthButton()
        self.buttons["down"] = ArrowSouthButton()
        self.buttons["lock"].clicked.connect(self.switch_lock)
        self.buttons["right"].clicked.connect(self.move_x_plus)
        self.buttons["left"].clicked.connect(self.move_x_minus)
        self.buttons["up"].clicked.connect(self.move_y_plus)
        self.buttons["down"].clicked.connect(self.move_y_minus)
        self.buttons["zoomdown"].clicked.connect(self.zoom_minus)
        self.buttons["zoomup"].clicked.connect(self.zoom_plus)

        # long press
        self.buttons["lock"].setAutoRepeat(True)
        self.buttons["lock"].setAutoRepeatDelay(1000)
        self.buttons["lock"].setAutoRepeatInterval(1000)
        self.buttons["lock"]._state = 0
        self.button_press_count["lock"] = 0

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
