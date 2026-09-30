import numpy as np
from pyqtgraph import functions as fn
from pyqtgraph import getConfigOption
from pyqtgraph.graphicsItems.AxisItem import AxisItem
from pyqtgraph.Qt import QtCore, QtGui

from .colored_segments import _as_array, _build_segment_points
from .CourseGraphItem import CourseGraphItem, _points_to_polygon

__all__ = [
    "CourseProfileAxisItem",
    "CourseProfileGraphItem",
    "configure_course_profile_axes",
]


class CourseProfileAxisItem(AxisItem):
    minimum_label = None

    def tickStrings(self, values, scale, spacing):
        labels = super().tickStrings(values, scale, spacing)
        if self.minimum_label is None:
            return labels
        return [
            label if value >= self.minimum_label else ""
            for value, label in zip(values, labels)
        ]


def configure_course_profile_axes(plot, font_size):
    font = QtGui.QFont()
    font.setPixelSize(font_size)
    font.setBold(True)
    grid_pen = fn.mkPen(color=(190, 190, 190))
    for name in ("bottom", "left"):
        axis = plot.getAxis(name)
        axis.tickFont = font
        axis.setTickPen(grid_pen)
        axis.setStyle(maxTickLevel=0)


def _resolve_baseline(y, baseline):
    if baseline is not None and np.isfinite(baseline):
        return float(baseline)

    if y is None or np.isscalar(y):
        return 0.0

    finite_y = np.asarray(y)[np.isfinite(y)]
    if finite_y.size == 0:
        return 0.0

    min_y = float(np.min(finite_y))
    max_y = float(np.max(finite_y))
    if baseline == -np.inf:
        # Qt requires finite polygon coordinates, so extend beyond any profile view.
        return min_y - max(max_y - min_y, 100.0)

    margin = max((max_y - min_y) * 0.05, 1.0)
    return min(0.0, min_y - margin)


def _build_polygon_points(x, y, brushes, baseline):
    return [
        ([(points[0][0], baseline), *points, (points[-1][0], baseline)], color)
        for points, color in _build_segment_points(x, y, brushes)
    ]


class CourseProfileGraphItem(CourseGraphItem):
    def __init__(self, **opts):
        """
        Valid keyword options are:
        x, y, pen, brushes, baseline

        Example uses:

            CourseProfileGraphItem(x=range(5), y=[1,5,2,4,3], brushes=[np.nan,(color0-1),(color1-2),(color2-3),(color3-4)])


        """
        super().__init__()
        self.opts = dict(
            x=None,
            y=None,
            pen=None,
            brushes=None,
            baseline=None,
        )
        self.setOpts(**opts)

    def drawPicture(self):
        self.picture = QtGui.QPicture()
        self._shape = QtGui.QPainterPath()
        p = QtGui.QPainter(self.picture)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        pen = self.opts["pen"]
        if pen is None:
            pen = getConfigOption("foreground")
        pen = fn.mkPen(pen)

        x = _as_array(self.opts["x"])
        y = _as_array(self.opts["y"])
        brushes = _as_array(self.opts["brushes"])
        baseline = _resolve_baseline(y, self.opts["baseline"])

        p.setPen(pen)
        for polygon_points, color in _build_polygon_points(x, y, brushes, baseline):
            polygon = _points_to_polygon(polygon_points)
            brush_color = pen.color() if color is None else color
            p.setBrush(fn.mkBrush(brush_color))
            p.drawPolygon(polygon)
            self._shape.addPolygon(polygon)

        p.end()
        self._bounding_rect = QtCore.QRectF(self.picture.boundingRect())
