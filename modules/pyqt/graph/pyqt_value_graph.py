import numpy as np

from modules._qt_qtwidgets import pg, qasync
from modules.pyqt.pyqt_screen_widget import ScreenWidget

HOLIZONTAL_ITEMS = 4
VERTICAL_ITEMS = 2


def build_item_layout(elements, cols, widget_name):
    item_layout = {}
    for i, element in enumerate(elements):
        item_layout[element] = (i // cols, i % cols)

    plot_y = (len(elements) + cols - 1) // cols
    item_layout[widget_name] = (plot_y, 0, -1, -1)

    return item_layout, plot_y


class PerformanceGraphWidget(ScreenWidget):
    elements = ("Power", "HR", "W'bal(Norm)", "LapTime")
    item_layout = {}

    # for Power
    # brush = pg.mkBrush(color=(0,160,255,64))
    brush = pg.mkBrush(color=(0, 255, 255))
    # pen2 = pg.mkPen(color=(255,255,255,0), width=0.01) #transparent and thin line
    pen1 = pg.mkPen(color=(255, 255, 255), width=0.01)  # transparent and thin line
    legend_pen1 = pg.mkPen(color=(0, 255, 255), width=3)
    # for HR, wbal
    pen2 = pg.mkPen(color=(255, 0, 0), width=2)

    def __init__(self, parent, config):
        s = config.display.resolution
        cols = VERTICAL_ITEMS if s[0] < s[1] else HOLIZONTAL_ITEMS
        self.item_layout, plot_y = build_item_layout(
            self.elements, cols, self.__class__.__name__
        )
        self.plot_x = 0
        self.plot_y = plot_y

        self.display_item = config.G_GUI_PERFORMANCE_GRAPH_DISPLAY_ITEM
        self.item = {
            "POWER": {
                "name": "POWER",
                "legend_name": "Power",
                "graph_key": "power_graph",
                "yrange": [config.G_GUI_MIN_POWER, config.G_GUI_MAX_POWER],
            },
            "HR": {
                "name": "HR",
                "legend_name": "HR",
                "graph_key": "hr_graph",
                "yrange": [config.G_GUI_MIN_HR, config.G_GUI_MAX_HR],
            },
            "W_BAL": {
                "name": "W_BAL",
                "legend_name": "W'bal(Norm)",
                "graph_key": "w_bal_graph",
                "yrange": [config.G_GUI_MIN_W_BAL, config.G_GUI_MAX_W_BAL],
            },
        }
        self.plot_data_x1 = []
        for i in range(config.G_GUI_PERFORMANCE_GRAPH_DISPLAY_RANGE + 1):
            self.plot_data_x1.append(i)
        self.power_bar_x0 = np.asarray(self.plot_data_x1[:-1], dtype=np.float32)
        self.power_bar_x1 = np.asarray(self.plot_data_x1[1:], dtype=np.float32)
        self.empty_bar_data = np.asarray([], dtype=np.float32)

        super().__init__(parent, config, self.item_layout)

    def setup_ui_extra(self):
        # 1st graph: POWER
        plot = pg.PlotWidget()
        plot.setBackground(None)
        self.p1 = plot.plotItem

        # 2nd graph: HR or W_BAL
        self.p2 = pg.ViewBox()
        self.p1.showAxis("right")
        self.p1.scene().addItem(self.p2)
        self.p1.getAxis("right").linkToView(self.p2)
        self.p2.setXLink(self.p1)
        self.p1.vb.sigResized.connect(self._sync_overlay_view)

        self.power_view = self.p1.vb
        self.power_bar_item = pg.BarGraphItem(
            x0=self.empty_bar_data,
            x1=self.empty_bar_data,
            height=self.empty_bar_data,
            brush=self.brush,
            pen=self.pen1,
        )
        self.power_bar_item.setZValue(1)
        self.power_view.addItem(self.power_bar_item)
        self.secondary_curve = pg.PlotCurveItem(pen=self.pen2, connect="finite")
        self.p2.addItem(self.secondary_curve)
        self.legend = self.p1.addLegend(offset=(8, 8))
        self.legend_power_item = pg.PlotCurveItem(
            pen=self.legend_pen1,
            connect="finite",
        )
        self.legend.addItem(
            self.legend_power_item,
            self.item[self.display_item[0]]["legend_name"],
        )
        self.legend.addItem(
            self.secondary_curve,
            self.item[self.display_item[1]]["legend_name"],
        )
        self.legend.setZValue(1000)

        plot.setXRange(0, self.config.G_GUI_PERFORMANCE_GRAPH_DISPLAY_RANGE)
        self.p1.setYRange(*self.item[self.display_item[0]]["yrange"])
        self.p2.setYRange(*self.item[self.display_item[1]]["yrange"])
        plot.setMouseEnabled(x=False, y=False)

        # self.p1.setLabels(left=self.item[self.display_item[0]]['name'])
        # self.p1.getAxis('right').setLabel(self.display_item[self.item[1]]['name'])

        # p2 on p1
        self.p1.setZValue(-100)

        self.layout.addWidget(plot, self.plot_y, self.plot_x, -1, -1)
        self._sync_overlay_view()

    def _sync_overlay_view(self):
        scene_rect = self.p1.vb.sceneBoundingRect()
        self.p2.setGeometry(scene_rect)
        self.p2.linkedViewChanged(self.p1.vb, self.p2.XAxis)

    def set_font_size(self, length):
        self.font_size = int(length / 7)
        self.set_minimum_size()

    @qasync.asyncSlot()
    async def update_display(self):
        super().update_display()
        
        # all_nan = {'hr_graph': True, 'power_graph': True}
        all_nan = {
            self.item[self.display_item[0]]["graph_key"]: True,
            self.item[self.display_item[1]]["graph_key"]: True,
        }
        for key in all_nan.keys():
            chk = np.isnan(self.sensor.values["integrated"][key])
            if False in chk:
                all_nan[key] = False

        power_key = self.item[self.display_item[0]]["graph_key"]
        if not all_nan[power_key]:
            # change max for power
            if self.display_item[0] == "POWER":
                power_max = 100 * (
                    int(
                        np.nanmax(
                            self.sensor.values["integrated"][power_key]
                        )
                        / 100
                    )
                    + 1
                )
                if self.item[self.display_item[0]]["yrange"][1] != power_max:
                    self.item[self.display_item[0]]["yrange"][1] = power_max
                    self.p1.setYRange(*self.item[self.display_item[0]]["yrange"])

            power_data = np.asarray(
                self.sensor.values["integrated"][power_key],
                dtype=np.float32,
            ).copy()
            self.power_bar_item.setOpts(
                x0=self.power_bar_x0,
                x1=self.power_bar_x1,
                height=power_data,
            )
            self.power_view.update()
        else:
            self.power_bar_item.setOpts(
                x0=self.empty_bar_data,
                x1=self.empty_bar_data,
                height=self.empty_bar_data,
            )
            self.power_view.update()

        secondary_key = self.item[self.display_item[1]]["graph_key"]
        if not all_nan[secondary_key]:
            self.secondary_curve.setData(self.sensor.values["integrated"][secondary_key])
        else:
            self.secondary_curve.setData([])


class AccelerationGraphWidget(ScreenWidget):
    elements = ("Motion", "M_Stat")
    item_layout = {}

    # for acc
    pen1 = pg.mkPen(color=(0, 0, 255), width=3)
    pen2 = pg.mkPen(color=(255, 0, 0), width=3)
    pen3 = pg.mkPen(color=(0, 0, 0), width=2)

    g_range = 0.3

    def __init__(self, parent, config):
        s = config.display.resolution
        cols = VERTICAL_ITEMS if s[0] < s[1] else HOLIZONTAL_ITEMS
        self.item_layout, plot_y = build_item_layout(
            self.elements, cols, self.__class__.__name__
        )
        self.plot_x = 0
        self.plot_y = plot_y

        super().__init__(parent, config, self.item_layout)

    def setup_ui_extra(self):
        plot = pg.PlotWidget()
        plot.setBackground(None)
        self.p1 = plot.plotItem
        self.p1.showGrid(y=True)
        # self.p1.setLabels(left='HR')

        self.p2 = pg.ViewBox()
        self.p1.scene().addItem(self.p2)
        self.p2.setXLink(self.p1)
        self.p3 = pg.ViewBox()
        self.p1.scene().addItem(self.p3)
        self.p3.setXLink(self.p1)
        self.p1.vb.sigResized.connect(self._sync_overlay_views)

        self.acc_curve_x = pg.PlotCurveItem(pen=self.pen1, connect="finite")
        self.acc_curve_y = pg.PlotCurveItem(pen=self.pen2, connect="finite")
        self.acc_curve_z = pg.PlotCurveItem(pen=self.pen3, connect="finite")
        self.p1.addItem(self.acc_curve_x)
        self.p2.addItem(self.acc_curve_y)
        self.p3.addItem(self.acc_curve_z)
        self.legend = self.p1.addLegend(offset=(8, 8))
        self.legend.addItem(self.acc_curve_x, "ACC X")
        self.legend.addItem(self.acc_curve_y, "ACC Y")
        self.legend.addItem(self.acc_curve_z, "ACC Z")
        self.legend.setZValue(1000)

        plot.setXRange(0, self.config.G_GUI_ACC_TIME_RANGE)
        plot.setMouseEnabled(x=False, y=False)

        self.layout.addWidget(plot, self.plot_y, self.plot_x, -1, -1)
        self._sync_overlay_views()

    def _sync_overlay_views(self):
        scene_rect = self.p1.vb.sceneBoundingRect()
        self.p2.setGeometry(scene_rect)
        self.p2.linkedViewChanged(self.p1.vb, self.p2.XAxis)
        self.p3.setGeometry(scene_rect)
        self.p3.linkedViewChanged(self.p1.vb, self.p3.XAxis)

    def start(self):
        self.timer.start(self.config.G_REALTIME_GRAPH_INTERVAL)

    def set_font_size(self, length):
        self.font_size = int(length / 7)
        self.set_minimum_size()

    @qasync.asyncSlot()
    async def update_display(self):
        super().update_display()

        X = 0
        Y = 1
        Z = 2

        v = self.sensor.sensor_i2c.graph_values["g_acc"]
        all_nan = {X: True, Y: True, Z: True}
        for key in all_nan.keys():
            chk = np.isnan(v[key])
            if False in chk:
                all_nan[key] = False
        m = [x for x in v[0] if not np.isnan(x)]
        median = None
        if len(m):
            median = m[-1]

        if median is not None:
            self.p1.setYRange(-self.g_range, self.g_range)
            self.p2.setYRange(-self.g_range, self.g_range)
            self.p3.setYRange(-self.g_range, self.g_range)

        if not all_nan[X]:
            self.acc_curve_x.setData(v[X])
        else:
            self.acc_curve_x.setData([])

        if not all_nan[Y]:
            self.acc_curve_y.setData(v[Y])
        else:
            self.acc_curve_y.setData([])

        if not all_nan[Z]:
            self.acc_curve_z.setData(v[Z])
        else:
            self.acc_curve_z.setData([])


class AltitudeGraphWidget(ScreenWidget):
    elements = ("Grade", "Grade(spd)", "Altitude", "Alt.(GPS)")
    item_layout = {}

    # for altitude_raw
    pen1 = pg.mkPen(color=(0, 0, 0), width=2)
    pen2 = pg.mkPen(color=(255, 0, 0), width=3)

    def __init__(self, parent, config):
        s = config.display.resolution
        cols = VERTICAL_ITEMS if s[0] < s[1] else HOLIZONTAL_ITEMS
        self.item_layout, plot_y = build_item_layout(
            self.elements, cols, self.__class__.__name__
        )
        self.plot_x = 0
        self.plot_y = plot_y

        super().__init__(parent, config, self.item_layout)

    def setup_ui_extra(self):
        plot = pg.PlotWidget()
        plot.setBackground(None)
        self.p1 = plot.plotItem
        self.p1.showGrid(y=True)

        self.p2 = pg.ViewBox()
        self.p1.scene().addItem(self.p2)
        self.p2.setXLink(self.p1)
        self.p1.vb.sigResized.connect(self._sync_overlay_view)

        self.altitude_curve = pg.PlotCurveItem(pen=self.pen1, connect="finite")
        self.altitude_gps_curve = pg.PlotCurveItem(pen=self.pen2, connect="finite")
        self.p1.addItem(self.altitude_curve)
        self.p2.addItem(self.altitude_gps_curve)
        self.legend = self.p1.addLegend(offset=(8, 8))
        self.legend.addItem(self.altitude_curve, "Altitude")
        self.legend.addItem(self.altitude_gps_curve, "Alt.(GPS)")
        self.legend.setZValue(1000)

        plot.setXRange(0, self.config.G_GUI_PERFORMANCE_GRAPH_DISPLAY_RANGE)
        plot.setMouseEnabled(x=False, y=False)

        self.y_range = 15
        self.y_shift = 0  # self.y_ra  nge * 0.25

        self.layout.addWidget(plot, self.plot_y, self.plot_x, -1, -1)
        self._sync_overlay_view()

    def _sync_overlay_view(self):
        scene_rect = self.p1.vb.sceneBoundingRect()
        self.p2.setGeometry(scene_rect)
        self.p2.linkedViewChanged(self.p1.vb, self.p2.XAxis)

    def set_font_size(self, length):
        self.font_size = int(length / 7)
        self.set_minimum_size()

    @qasync.asyncSlot()
    async def update_display(self):
        super().update_display()

        v = self.sensor.values["integrated"]
        all_nan = {"altitude_graph": True, "altitude_gps_graph": True}
        for key in all_nan.keys():
            chk = np.isnan(v[key])
            if False in chk:
                all_nan[key] = False
        m = [x for x in v["altitude_graph"] if not np.isnan(x)]
        median = None
        if len(m):
            median = m[-1]

        if not all_nan["altitude_graph"]:
            self.y_range = max(
                abs(min(v["altitude_graph"]) - median),
                abs(max(v["altitude_graph"]) - median),
            )

            if np.isnan(self.y_range) or self.y_range < 15:
                self.y_range = 15
            else:
                self.y_range = 10 * (int(self.y_range / 10) + 1)

            if median is not None:
                self.p1.setYRange(median - self.y_range, median + self.y_range)

            self.altitude_curve.setData(v["altitude_graph"])
        else:
            self.altitude_curve.setData([])

        if not all_nan["altitude_gps_graph"]:
            if median is not None:
                self.p2.setYRange(
                    median - self.y_range + self.y_shift,
                    median + self.y_range + self.y_shift,
                )

            self.altitude_gps_curve.setData(v["altitude_gps_graph"])
        else:
            self.altitude_gps_curve.setData([])
