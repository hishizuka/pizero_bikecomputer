from modules.app_logger import app_logger
from modules._qt_qtwidgets import QT_EXPANDING, QtCore, QtWidgets, qasync

from .pyqt_item import Item


class ScreenWidget(QtWidgets.QWidget):
    config = None
    layout_class = QtWidgets.QGridLayout

    def __init__(self, parent, config, item_layout=None):
        self.config = config
        self.items = []
        self.item_layout = {}
        self.max_width = self.max_height = 0
        self.font_size = 20

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
        self.set_font_size(min(self.size().height(), self.size().width()))
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
        
        self.set_font_size(min(self.config.display.resolution))

    # call from on_change_main_page in gui_pyqt.py
    def start(self):
        self.timer.start(self.config.G_DRAW_INTERVAL)

    # call from on_change_main_page in gui_pyqt.py
    def stop(self):
        self.timer.stop()

    def setup_ui_extra(self):
        pass

    def set_font_size(self, length):
        # get rows/columns for own grid layout
        short_side_items = self.max_height # width > height
        f = 1.0 # quick hack. considering aspect ratio?
        if self.size().height() > self.size().width():
            short_side_items = self.max_width
            f = 0.8

        self.font_size = int(length / 6 * f)  # 2 rows/columns (100px)
        if short_side_items == 2:  # 3 rows/columns (66px)
            self.font_size = int(length / 7 * f)
        elif short_side_items == 3:  # 4 rows/columns (50px)
            self.font_size = int(length / 10 * f)
        elif short_side_items >= 4:  # 5 rows/columns~ (40px)
            self.font_size = int(length / 15 * f)

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
                    if pos[2] in [-1, self.max_height + 1]:
                        bottom_flag = True
                    if pos[3] in [-1, self.max_width + 1]:
                        right_flag = True

                if key.endswith("GraphWidget"):
                    continue

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
                    f"not found in items: {item.name} {eval(self.config.gui.gui_config.G_ITEM_DEF[item.name][1])}",
                )
