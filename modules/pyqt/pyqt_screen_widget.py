from functools import partial

from modules.app_logger import app_logger
from modules.qt._qt_qtwidgets import QT_EXPANDING, QtCore, QtWidgets

from .pyqt_item import AscDescItem, BatteryItem, Item, WindItem


class ScreenWidget(QtWidgets.QWidget):
    layout_class = QtWidgets.QGridLayout

    def __init__(self, parent, config, item_layout=None, *, unit_wrap=False):
        self.config = config
        self.unit_wrap = unit_wrap
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
        self.layout.activate()
        self.update_unit_positions()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.FontChange:
            QtCore.QTimer.singleShot(0, self.refresh_fonts)

    def refresh_fonts(self):
        self.resizeEvent(None)
        self.update_display()

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
        short_side_items = self.max_height  # width > height
        f = 1.0  # quick hack. considering aspect ratio?
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
            self.layout.setColumnStretch(i, 1)
        for i in range(self.max_height + 1):
            self.layout.setRowStretch(i, 1)

    def add_items(self):
        # set borders
        for pos in self.item_layout.values():
            self.max_height = max(self.max_height, pos[0])
            self.max_width = max(self.max_width, pos[1])
            if len(pos) == 4:
                self.max_height = max(self.max_height, pos[2] - 1)
                self.max_width = max(self.max_width, pos[3] - 1)

        for key, pos in self.item_layout.items():
            bottom_flag = pos[0] == self.max_height
            right_flag = pos[1] == self.max_width
            if len(pos) == 4:
                bottom_flag |= pos[2] in (-1, self.max_height + 1)
                right_flag |= pos[3] in (-1, self.max_width + 1)

            if key.endswith("GraphWidget"):
                continue

            getter = self.config.gui.gui_config.G_ITEM_DEF[key][1]
            item_class = {
                "Asc. / Dsc.": AscDescItem,
                "Battery": BatteryItem,
                "Wind": WindItem,
            }.get(key, Item)
            item = item_class(
                config=self.config,
                name=key,
                font_size=self.font_size,
                bottom_flag=bottom_flag,
                right_flag=right_flag,
            )
            item.value_getter = partial(getter, self)

            self.items.append(item)

            if len(pos) == 4:
                bottom = self.max_height + 1 if pos[2] == -1 else pos[2]
                right = self.max_width + 1 if pos[3] == -1 else pos[3]
                self.layout.addLayout(
                    item,
                    pos[0],
                    pos[1],
                    bottom - pos[0],
                    right - pos[1],
                )
            else:
                self.layout.addLayout(item, pos[0], pos[1])

    # This handles by default items displays, but each screen can implement its own logic
    def update_display(self):
        for item in self.items:
            try:
                value = item.value_getter()
            except KeyError:
                continue
            except ValueError:
                # Some sensors may temporarily yield NaN; skip noisy tracebacks and render as blank
                value = float("nan")
            except Exception:  # noqa
                app_logger.exception(f"not found in items: {item.name}")
                continue

            item.update_value(value)

    def update_unit_positions(self):
        if not self.unit_wrap:
            return
        rows = {}
        for item in self.items:
            row, _, _, _ = self.layout.getItemPosition(self.layout.indexOf(item))
            rows.setdefault(row, []).append(item)
        for items in rows.values():
            below = any(item.needs_unit_wrap() for item in items)
            for item in items:
                item.set_unit_below(below)
