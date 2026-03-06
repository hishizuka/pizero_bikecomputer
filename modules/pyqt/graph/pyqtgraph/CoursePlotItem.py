import numpy as np

from pyqtgraph import functions as fn
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject


__all__ = ["CoursePlotItem"]


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


def _build_segment_points(x, y, brushes):
    if x is None or y is None or np.isscalar(x) or np.isscalar(y):
        return []
    if brushes is not None and np.isscalar(brushes):
        brushes = None

    n = min(len(x), len(y))
    if brushes is not None:
        n = min(n, len(brushes))
    if n < 2:
        return []

    segments = []
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
            segments.append((current_points, current_color))
            current_points = [start_point, end_point]
            current_color = seg_color
            continue

        current_points.append(end_point)

    if current_points is not None:
        segments.append((current_points, current_color))

    return segments


def _points_to_polyline(points):
    polyline = QtGui.QPolygonF()
    for x_pos, y_pos in points:
        polyline.append(QtCore.QPointF(x_pos, y_pos))
    return polyline


def _points_to_path(points):
    path = QtGui.QPainterPath()
    if not points:
        return path

    first_x, first_y = points[0]
    path.moveTo(first_x, first_y)
    for x_pos, y_pos in points[1:]:
        path.lineTo(x_pos, y_pos)
    return path


class CoursePlotItem(GraphicsObject):
    def __init__(self, **opts):
        """
        Valid keyword options are:
        x, y, width, brushes, outline_width, outline_color

        Example uses:

            CoursePlotItem(x=lon, y=lat, brushes=[np.nan,(color0-1),(color1-2),(color2-3),(color3-4)], width=6)

        """
        GraphicsObject.__init__(self)
        self.opts = dict(
            x=None,
            y=None,
            width=None,
            brushes=None,
            outline_width=None,
            outline_color=(0, 0, 0, 160),
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

        x = _as_array(self.opts.get("x"))
        y = _as_array(self.opts.get("y"))
        brushes = _as_array(self.opts.get("brushes"))
        width = 1 if self.opts.get("width") is None else self.opts.get("width")
        outline_width = self.opts.get("outline_width")
        outline_color = self.opts.get("outline_color")
        segments = _build_segment_points(x, y, brushes)

        # Pass 1: draw dark outline for contrast
        outline_pen = None
        if outline_width is not None:
            outline_pen = fn.mkPen(color=outline_color, width=outline_width)
            outline_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            outline_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)

        # Pass 2: draw colored course line on top
        for seg_points, seg_color in segments:
            seg_lines = _points_to_polyline(seg_points)
            seg_path = _points_to_path(seg_points)

            if outline_pen is not None:
                p.setPen(outline_pen)
                p.drawPolyline(seg_lines)

            if seg_color is None:
                pen = fn.mkPen(width=width)
            else:
                pen = fn.mkPen(color=seg_color, width=width)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPolyline(seg_lines)

            stroke_width = max(
                outline_pen.widthF() if outline_pen is not None else 0.0,
                pen.widthF(),
                1.0,
            )
            stroker = QtGui.QPainterPathStroker()
            stroker.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            stroker.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            stroker.setWidth(stroke_width)
            self._shape.addPath(stroker.createStroke(seg_path))

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
