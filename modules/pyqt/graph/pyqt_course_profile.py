import numpy as np
import qasync

from modules._pyqt import QtGui, pg
from modules.pyqt.graph.pyqtgraph.CourseProfileGraphItem import CourseProfileGraphItem
from modules.utils.timer import Timer
from .pyqt_base_map import BaseMapWidget


class CourseProfileGraphWidget(BaseMapWidget):
    course_profile_plot = None
    climb_top_plot = None
    climb_detail = None

    max_zoom = 0

    # map position
    map_area = {
        "w": np.nan,
        "h": np.nan,
    }  # width(longitude diff) and height(latitude diff)
    move_pos = {"x": 0, "y": 0}
    map_pos = {"x": np.nan, "y": np.nan}  # center

    # current point
    location = []

    # remove button(up, down)
    def setup_ui_extra(self):
        super().setup_ui_extra()

        # map
        self.layout.addWidget(self.plot, 0, 0, 3, 3)

        if self.config.display.has_touch:
            # zoom
            self.layout.addWidget(self.buttons["zoomdown"], 0, 0)
            self.layout.addWidget(self.buttons["lock"], 1, 0)
            self.layout.addWidget(self.buttons["zoomup"], 2, 0)
            # arrow
            self.layout.addWidget(self.buttons["left"], 0, 2)
            self.layout.addWidget(self.buttons["right"], 1, 2)

        self.climb_detail = pg.TextItem(color=(0, 0, 0), anchor=(1.0, 1.0))
        self.climb_detail.setZValue(100)

        # for expanding column
        self.layout.setColumnMinimumWidth(0, 40)
        self.layout.setColumnStretch(1, 1)
        self.layout.setColumnMinimumWidth(2, 40)

    # load course profile and display
    def load_course(self):
        if not self.course.is_set or not len(self.course.altitude):
            return

        self.get_max_zoom()

        with Timer(
            auto_start=False, auto_log=True, text="Plotting course profile: {0:.3f} sec"
        ):
            if not self.sensor.sensor_gps.is_real:
                self.zoom = self.max_zoom

            self.plot.showGrid(x=True, y=True, alpha=1)
            self.plot.showAxis("left")
            self.plot.showAxis("bottom")
            font = QtGui.QFont()
            font.setPixelSize(16)
            font.setBold(True)
            self.plot.getAxis("bottom").tickFont = font
            # self.plot.getAxis("bottom").setStyle(tickTextOffset = 5)
            self.plot.getAxis("left").tickFont = font
            # self.plot.getAxis("left").setStyle(tickTextOffset = 5)
            # self.plot.setAutoPan()

            self.course_profile_plot = CourseProfileGraphItem(
                x=self.course.distance,
                y=self.course.altitude,
                brushes=self.course.colored_altitude,
                pen=pg.mkPen(color=(255, 255, 255, 0), width=0.01),
            )  # transparent(alpha=0) and thin line
            self.plot.addItem(self.course_profile_plot)

            self.climb_top_plot = pg.ScatterPlotItem(pxMode=True, symbol="t", size=15)
            climb_points = []
            for i in range(len(self.course.climb_segment)):
                p = {
                    "pos": [
                        self.course.climb_segment[i]["start_point_distance"],
                        self.course.climb_segment[i]["start_point_altitude"] + 10,
                    ],
                    "pen": {"color": "w", "width": 1},
                    "brush": pg.mkBrush(color=(0, 0, 0)),
                }
                climb_points.append(p)
                p = {
                    "pos": [
                        self.course.climb_segment[i]["course_point_distance"],
                        self.course.climb_segment[i]["course_point_altitude"] + 10,
                    ],
                    "pen": {"color": "w", "width": 1},
                    "brush": pg.mkBrush(color=(255, 0, 0)),
                }
                climb_points.append(p)
            self.climb_top_plot.setData(climb_points)
            self.plot.addItem(self.climb_top_plot)

    def reset_course(self):
        for p in filter(
            None, [self.course_profile_plot, self.climb_top_plot, self.climb_detail]
        ):
            self.plot.removeItem(p)
        self.plot.removeItem(self.current_point)

    def init_course(self):
        self.course_loaded = False
        self.resizeEvent(None)

    @qasync.asyncSlot()
    async def update_display(self):
        if not self.course.is_set or not len(self.course.altitude):
            return

        if not self.course_loaded:
            self.load_course()
            self.course_loaded = True

        if self.zoom == self.max_zoom:
            await self.zoom_plus()
            return

        # remove current position for reloading
        if len(self.location):
            self.plot.removeItem(self.current_point)
            self.location.pop()

        # initialize
        x_width = self.zoom / 1000
        dist_end = self.course.distance[-1]
        graph_index = self.course.index.value
        x_start = self.course.distance[graph_index]

        if self.course.index.on_course_status:
            self.point["brush"] = self.point_color["fix"]
        else:
            self.point["brush"] = self.point_color["lost"]

        # move x,y
        if self.lock_status:
            self.map_pos["x"] = x_start - x_width / 10
            if self.map_pos["x"] < 0:
                self.map_pos["x"] = 0
            self.map_pos["x_index"] = graph_index
        else:  # no lock (scroll is available)
            self.map_pos["x"] += self.move_pos["x"] / 1000
            if self.map_pos["x"] <= 0:
                self.map_pos["x_index"] = 0
            elif self.map_pos["x"] >= dist_end:
                self.map_pos["x_index"] = len(self.course.distance) - 1
            elif self.move_pos["x"] != 0:
                self.map_pos["x_index"] = self.course.get_index_with_distance_cutoff(
                    self.map_pos["x_index"], self.move_pos["x"] / 1000
                )

        x_end = self.map_pos["x"] + x_width
        if x_end >= dist_end:
            x_end_index = len(self.course.distance) - 1
            self.map_pos["x_index"] = self.course.get_index_with_distance_cutoff(
                x_end_index, -x_width
            )
        else:
            x_end_index = self.course.get_index_with_distance_cutoff(
                self.map_pos["x_index"], x_width
            )

        # check borders
        # too short course or zoom out: display all
        if x_width > dist_end:
            self.map_pos["x"] = 0
            x_end = dist_end
        # over move: fix border
        else:
            if x_end > dist_end:
                x_end = dist_end
                self.map_pos["x"] = dist_end - x_width
            if self.map_pos["x"] < 0:
                self.map_pos["x"] = 0
                x_end = x_width

        if 0 <= graph_index < len(self.course.distance) and not np.isnan(
            self.course.index.altitude
        ):
            self.point["pos"][0] = self.course.index.distance / 1000
            self.point["pos"][1] = self.course.index.altitude
            self.location.append(self.point)
            self.current_point.setData(self.location)
            self.plot.addItem(self.current_point)

        # positioning
        self.plot.setXRange(min=self.map_pos["x"], max=x_end, padding=0)
        y_min = float("inf")
        y_max = -float("inf")
        if 0 <= self.map_pos["x_index"] < x_end_index:
            y_min = np.min(self.course.altitude[self.map_pos["x_index"] : x_end_index])
            y_max = np.max(self.course.altitude[self.map_pos["x_index"] : x_end_index])

        if y_min != float("inf") and y_max != -float("inf"):
            y_range_space = (y_max - y_min) * 0.2
            y_min = int((y_min - y_range_space) / 50) * 50
            y_max = int((y_max + y_range_space) / 50 + 2) * 50
            self.plot.setYRange(min=y_min, max=y_max, padding=0)

        if self.climb_detail is not None:
            self.plot.removeItem(self.climb_detail)
        climb_index = None

        for i in range(len(self.course.climb_segment)):
            if (
                self.course.climb_segment[i]["start"]
                <= graph_index
                <= self.course.climb_segment[i]["end"]
            ):
                climb_index = i
                break

        if climb_index is None:
            self.climb_detail.setHtml("")
        else:
            summit_img = '<img src="img/summit.png">'
            altitude_up_img = '<img src="img/altitude_up.png">'
            rest_distance = (
                self.course.climb_segment[climb_index]["course_point_distance"]
                - self.course.index.distance / 1000
            )
            rest_distance_str = "{:.1f}km<br />".format(rest_distance)
            rest_altitude = (
                self.course.climb_segment[climb_index]["course_point_altitude"]
                - self.course.index.altitude
            )
            rest_altitude_str = "{:.0f}m".format(rest_altitude)
            # rest
            grade_str = "{:2.0f}%".format(
                rest_altitude / (rest_distance * 1000) * 100
            )  # rest
            # average
            # grade_str = "({:.0f}%)".format(self.course.climb_segment[climb_index]['average_grade'])
            self.climb_detail.setHtml(
                '<div style=" \
          text-align: right; \
          vertical-align: bottom; \
          font-size: 20px; \
          background-color: white; \
        ">'
                + summit_img
                + rest_distance_str
                + altitude_up_img
                + rest_altitude_str
                + grade_str
                + "</div>"
            )

        self.climb_detail.setPos(x_end, y_min)
        self.plot.addItem(self.climb_detail)

        # reset move_pos
        self.move_pos["x"] = self.move_pos["y"] = 0

    def get_max_zoom(self):
        if not self.course.is_set:
            return

        if self.max_zoom != 0:
            return

        z = self.zoom
        dist = self.course.distance[-1]

        if z / 1000 < dist:
            while z / 1000 < dist:
                z *= 2
            z *= 2
        else:
            while z / 1000 > dist:
                z /= 2
        self.max_zoom = z
