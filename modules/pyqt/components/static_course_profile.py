import math

import numpy as np

from modules._qt_qtwidgets import QtCore, QtGui, pg
from modules.pyqt.graph.pyqtgraph.CourseProfileGraphItem import (
    CourseProfileAxisItem,
    CourseProfileGraphItem,
    configure_course_profile_axes,
)


class StaticCourseProfileRenderer:
    NONNEGATIVE_ALTITUDE_TOLERANCE = 0.5  # [m]

    def __init__(self):
        self.left_axis = CourseProfileAxisItem("left")
        self.plot = pg.PlotWidget(
            axisItems={
                "left": self.left_axis,
                "bottom": CourseProfileAxisItem("bottom"),
            }
        )
        self.plot.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen)
        self.plot.setBackground("white")
        self.plot.showGrid(x=False, y=True, alpha=1)
        self.plot.getPlotItem().hideButtons()
        self.plot.setMouseEnabled(x=False, y=False)
        for name in ("bottom", "left"):
            axis = self.plot.getAxis(name)
            axis.setPen(pg.mkPen(255, 255, 255, 0))
            axis.setStyle(tickLength=0)

    @staticmethod
    def _nice_step(value):
        exponent = math.floor(math.log10(value))
        fraction = value / (10**exponent)
        nice_fraction = next(step for step in (1, 2, 5, 10) if fraction <= step)
        return nice_fraction * (10**exponent)

    @classmethod
    def _altitude_range(cls, altitude):
        minimum = float(np.min(altitude))
        maximum = float(np.max(altitude))
        span = maximum - minimum or max(abs(maximum) * 0.1, 10.0)
        padding = span * 0.1
        step = cls._nice_step((span + 2 * padding) / 4)
        return math.floor((minimum - padding) / step) * step, maximum + padding

    def render(self, course, target_size):
        image = QtGui.QImage(
            *target_size,
            QtGui.QImage.Format.Format_ARGB32,
        )
        image.fill(QtGui.QColor("white"))
        if len(course.altitude) < 2:
            return image

        distance = np.asarray(course.distance, dtype=float)
        altitude = np.asarray(course.altitude, dtype=float)
        finite = np.isfinite(distance) & np.isfinite(altitude)
        if np.count_nonzero(finite) < 2:
            return image

        distance_min = float(np.min(distance[finite]))
        distance_max = float(np.max(distance[finite]))
        if distance_min == distance_max:
            return image

        altitude_min, altitude_max = self._altitude_range(altitude[finite])
        self.left_axis.minimum_label = (
            0
            if course.source_altitude_min >= -self.NONNEGATIVE_ALTITUDE_TOLERANCE
            else None
        )
        configure_course_profile_axes(
            self.plot,
            max(11, min(16, image.height() // 9)),
        )
        self.plot.clear()
        self.plot.resize(image.size())
        self.plot.addItem(
            CourseProfileGraphItem(
                x=distance,
                y=altitude,
                brushes=course.colored_altitude,
                pen=pg.mkPen(None),
                baseline=-np.inf,
            )
        )
        self.plot.setXRange(distance_min, distance_max, padding=0)
        self.plot.setYRange(altitude_min, altitude_max, padding=0)

        self.plot.show()
        painter = QtGui.QPainter(image)
        try:
            self.plot.render(painter)
        finally:
            painter.end()
            self.plot.hide()
        return image
