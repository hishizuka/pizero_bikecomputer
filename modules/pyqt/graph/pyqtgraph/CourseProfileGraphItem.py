import numpy as np

from pyqtgraph import functions as fn
from pyqtgraph import getConfigOption
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject


__all__ = ["CourseProfileGraphItem"]


def _as_array(values):
    if values is None or np.isscalar(values) or isinstance(values, np.ndarray):
        return values
    return np.asarray(values)


def _segment_color(brushes, index):
    if brushes is None:
        return None

    brush = brushes[index]
    if np.isscalar(brush):
        return None if not np.isfinite(brush) else brush

    brush_array = np.asarray(brush)
    if brush_array.size == 0:
        return None
    if np.issubdtype(brush_array.dtype, np.number) and not np.isfinite(
        brush_array
    ).all():
        return None

    return tuple(brush_array.tolist())


def _resolve_baseline(y, baseline):
    if baseline is not None:
        return float(baseline)

    if y is None or np.isscalar(y):
        return 0.0

    finite_y = np.asarray(y)[np.isfinite(y)]
    if finite_y.size == 0:
        return 0.0

    min_y = float(np.min(finite_y))
    max_y = float(np.max(finite_y))
    margin = max((max_y - min_y) * 0.05, 1.0)
    return min(0.0, min_y - margin)


def _close_polygon(points, baseline):
    if len(points) < 2:
        return []
    return [(points[0][0], baseline), *points, (points[-1][0], baseline)]


def _build_polygon_points(x, y, brushes, baseline):
    if x is None or y is None or np.isscalar(x) or np.isscalar(y):
        return []
    if brushes is not None and np.isscalar(brushes):
        brushes = None

    n = min(len(x), len(y))
    if brushes is not None:
        n = min(n, len(brushes))
    if n < 2:
        return []

    polygons = []
    current_points = None
    current_color = None

    for i in range(1, n):
        if not (
            np.isfinite(x[i - 1])
            and np.isfinite(y[i - 1])
            and np.isfinite(x[i])
            and np.isfinite(y[i])
        ):
            current_points = None
            current_color = None
            continue

        seg_color = _segment_color(brushes, i)
        start_point = (float(x[i - 1]), float(y[i - 1]))
        end_point = (float(x[i]), float(y[i]))

        if current_points is None:
            current_points = [start_point, end_point]
            current_color = seg_color
            continue

        if seg_color != current_color:
            polygons.append((_close_polygon(current_points, baseline), current_color))
            current_points = [start_point, end_point]
            current_color = seg_color
            continue

        current_points.append(end_point)

    if current_points is not None:
        polygons.append((_close_polygon(current_points, baseline), current_color))

    return polygons


def _points_to_polygon(points):
    polygon = QtGui.QPolygonF()
    for x_pos, y_pos in points:
        polygon.append(QtCore.QPointF(x_pos, y_pos))
    return polygon


class CourseProfileGraphItem(GraphicsObject):
    def __init__(self, **opts):
        """
        Valid keyword options are:
        x, y, pen, brushes, baseline

        Example uses:

            CourseProfileGraphItem(x=range(5), y=[1,5,2,4,3], brushes=[np.nan,(color0-1),(color1-2),(color2-3),(color3-4)])


        """
        GraphicsObject.__init__(self)
        self.opts = dict(
            x=None,
            y=None,
            pen=None,
            brushes=None,
            baseline=None,
        )
        self._shape = None
        self._bounding_rect = None
        self.picture = None
        self.setOpts(**opts)

    def setOpts(self, **opts):
        self.prepareGeometryChange()
        self.opts.update(opts)
        self.picture = None
        self._shape = None
        self._bounding_rect = None
        self.update()
        self.informViewBoundsChanged()

    def drawPicture(self):
        self.picture = QtGui.QPicture()
        self._shape = QtGui.QPainterPath()
        p = QtGui.QPainter(self.picture)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        pen = self.opts["pen"]
        if pen is None:
            pen = getConfigOption("foreground")
        pen = fn.mkPen(pen)

        x = _as_array(self.opts.get("x"))
        y = _as_array(self.opts.get("y"))
        brushes = _as_array(self.opts.get("brushes"))
        baseline = _resolve_baseline(y, self.opts.get("baseline"))

        p.setPen(pen)
        for polygon_points, color in _build_polygon_points(x, y, brushes, baseline):
            polygon = _points_to_polygon(polygon_points)
            brush_color = pen.color() if color is None else color
            p.setBrush(fn.mkBrush(brush_color))
            p.drawPolygon(polygon)
            self._shape.addPolygon(polygon)

        p.end()
        self._bounding_rect = QtCore.QRectF(self.picture.boundingRect())

    def paint(self, p, *args):
        if self.picture is None:
            self.drawPicture()
        self.picture.play(p)

    def boundingRect(self):
        if self.picture is None:
            self.drawPicture()
        return QtCore.QRectF() if self._bounding_rect is None else self._bounding_rect

    def shape(self):
        if self.picture is None:
            self.drawPicture()
        return self._shape
