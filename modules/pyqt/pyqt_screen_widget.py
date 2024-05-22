from logger import app_logger
from modules._pyqt import QT_EXPANDING, QtCore, QtWidgets, qasync
from modules.config import Config

from .pyqt_item import Item


class ScreenWidget(QtWidgets.QWidget):
    config = None
    layout_class = QtWidgets.QGridLayout
    item_layout = None
    items = None

    font_size = 12
    max_width = max_height = 0

    def __init__(self, parent, config: Config, item_layout=None):
        self.config = config
        self.items = []

        if item_layout:
            self.item_layout = item_layout

        QtWidgets.QWidget.__init__(self, parent=parent)

        self.setup_ui()

    @property
    def logger(self):
        return self.config.logger

    @property
    def sensor(self):
        return self.logger.sensor

    @property
    def course(self):
        return self.logger.course

    @property
    def course_points(self):
        return self.course.course_points

    @property
    def gps_values(self):
        return self.sensor.values["GPS"]

    def resizeEvent(self, event):
        h = self.size().height()
        w = self.size().width()
        self.set_font_size(h if h < w else w)
        for i in self.items:
            i.update_font_size(self.font_size)

    def setup_ui(self):
        self.setSizePolicy(QT_EXPANDING, QT_EXPANDING)

        # update panel setting
        self.timer = QtCore.QTimer(parent=self)
        self.timer.timeout.connect(self.update_display)

        # layout
        self.layout = self.layout_class(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.setup_ui_extra()

        self.add_items()

        # this depends on max_height so has to be done after add_items that recalculate it
        self.set_font_size(self.config.display.resolution[1])

    # call from on_change_main_page in gui_pyqt.py
    def start(self):
        self.timer.start(self.config.G_DRAW_INTERVAL)

    # call from on_change_main_page in gui_pyqt.py
    def stop(self):
        self.timer.stop()

    def setup_ui_extra(self):
        pass

    def set_font_size(self, length):
        if self.config.G_DISPLAY_ORIENTATION == "vertical":
            length *= .7
            
        # need to modify for automation and scaling
        self.font_size = int(length / 6)  # 2 rows (100px)
        if self.max_height == 2:  # 3 rows (66px)
            self.font_size = int(length / 7)
        elif self.max_height == 3:  # 4 rows (50px)
            self.font_size = int(length / 10)
        elif self.max_height >= 4:  # 5 rows~ (40px)
            self.font_size = int(length / 15)

        self.set_minimum_size()

    def set_minimum_size(self):
        w = int(self.width() / (self.max_width + 1))
        for i in range(self.max_width + 1):
            self.layout.setColumnMinimumWidth(i, w)

    def add_items(self):
        if self.item_layout:
            # set borders
            for key, pos in self.item_layout.items():
                if pos[0] > self.max_height:
                    self.max_height = pos[0]
                if pos[1] > self.max_width:
                    self.max_width = pos[1]
                if len(pos) == 4:
                    if pos[2] - 1 > self.max_height:
                        self.max_height = pos[2]
                    if pos[3] - 1 > self.max_width:
                        self.max_width = pos[3]

            for key, pos in self.item_layout.items():
                bottom_flag = False
                right_flag = False
                if pos[0] == self.max_height:
                    bottom_flag = True
                if pos[1] == self.max_width:
                    right_flag = True
                if len(pos) == 4:
                    if pos[2] - 1 == self.max_height:
                        bottom_flag = True
                    if pos[3] - 1 == self.max_width:
                        right_flag = True

                item = Item(
                    config=self.config,
                    name=key,
                    font_size=self.font_size,
                    bottom_flag=bottom_flag,
                    right_flag=right_flag,
                )

                self.items.append(item)

                if len(pos) == 4:
                    self.layout.addLayout(item, pos[0], pos[1], pos[2], pos[3])
                else:
                    self.layout.addLayout(item, pos[0], pos[1])

    # This handles by default items displays, but each screen can implement its own logic
    @qasync.asyncSlot()
    async def update_display(self):
        for item in self.items:
            try:
                item.update_value(
                    eval(self.config.gui.gui_config.G_ITEM_DEF[item.name][1])
                )
            except KeyError:
                pass
                # item.update_value(None)
                # print("KeyError :", self.config.gui.gui_config.G_ITEM_DEF[item.name][1])
                # traceback.print_exc()
            except Exception:  # noqa
                item.update_value(None)
                app_logger.exception(
                    f"###update_display### : {item.name} {eval(self.config.gui.gui_config.G_ITEM_DEF[item.name][1])}",
                )
