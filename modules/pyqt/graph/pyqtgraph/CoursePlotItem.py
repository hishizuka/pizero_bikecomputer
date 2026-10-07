import numpy as np
from pyqtgraph import functions as fn
from pyqtgraph.Qt import QtCore, QtGui

from modules.map.geometry import direction_arrow_polygons
from modules.map.style import COURSE_ARROW_OUTLINE_WIDTH

from .colored_segments import _as_array, _build_segment_points
from .CourseGraphItem import CourseGraphItem
from .CourseGraphItem import _points_to_polygon as _points_to_polyline

__all__ = ["CoursePlotItem"]

_ARROW_OUTLINE_WIDTH = COURSE_ARROW_OUTLINE_WIDTH


def _points_to_path(points, close=False):
    path = QtGui.QPainterPath()
    first_x, first_y = points[0]
    path.moveTo(first_x, first_y)
    for x_pos, y_pos in points[1:]:
        path.lineTo(x_pos, y_pos)
    if close:
        path.closeSubpath()
    return path


class CoursePlotItem(CourseGraphItem):
    pixel_ratio = 1.0

    def paint(self, painter, *args):
        ratio = painter.device().devicePixelRatioF()
        if ratio != self.pixel_ratio:
            self.pixel_ratio = ratio
            self.picture = None
        super().paint(painter, *args)

    def __init__(self, **opts):
        """
        Valid keyword options are:
        x, y, width, brushes, outline_width, outline_color,
        pixel_scale, arrows (spacing, width)

        Example uses:

            CoursePlotItem(x=lon, y=lat, brushes=[np.nan,(color0-1),(color1-2),(color2-3),(color3-4)], width=6)

        """
        super().__init__()
        self.opts = dict(
            x=None,
            y=None,
            width=None,
            brushes=None,
            outline_width=None,
            outline_color=(0, 0, 0, 160),
            pixel_scale=None,
            arrows=None,
        )
        self.setCacheMode(self.CacheMode.DeviceCoordinateCache)
        self.setOpts(**opts)

    def drawPicture(self):
        self.picture = QtGui.QPicture()
        self._shape = QtGui.QPainterPath()
        p = QtGui.QPainter(self.picture)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        x = _as_array(self.opts["x"])
        y = _as_array(self.opts["y"])
        brushes = _as_array(self.opts["brushes"])
        width = 1 if self.opts["width"] is None else self.opts["width"]
        outline_width = self.opts["outline_width"]
        outline_color = self.opts["outline_color"]
        segments = _build_segment_points(x, y, brushes)
        vertices = []

        # Pass 1: draw dark outline for contrast
        outline_pen = None
        if outline_width is not None:
            outline_pen = fn.mkPen(
                color=outline_color, width=outline_width * self.pixel_ratio
            )
            outline_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            outline_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)

        # Pass 2: draw colored course line on top
        for seg_points, seg_color in segments:
            seg_lines = _points_to_polyline(seg_points)
            vertices.extend(seg_points)

            if outline_pen is not None:
                p.setPen(outline_pen)
                p.drawPolyline(seg_lines)

            if seg_color is None:
                pen = fn.mkPen(width=width * self.pixel_ratio)
            else:
                pen = fn.mkPen(color=seg_color, width=width * self.pixel_ratio)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPolyline(seg_lines)

        if segments and self.opts["arrows"] is not None:
            arrow_path = QtGui.QPainterPath()
            for arrow in direction_arrow_polygons(
                x, y, self.opts["pixel_scale"], *self.opts["arrows"]
            ):
                vertices.extend(arrow)
                arrow_path.addPath(_points_to_path(arrow, close=True))

            arrow_outline_pen = fn.mkPen(
                color=(0, 0, 0), width=_ARROW_OUTLINE_WIDTH * self.pixel_ratio
            )
            arrow_outline_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
            p.setPen(arrow_outline_pen)
            p.setBrush(fn.mkBrush(color=(255, 255, 255)))
            p.drawPath(arrow_path)

        p.end()
        self._bounding_rect = QtCore.QRectF()
        if vertices:
            points = np.asarray(vertices)
            scale = self.opts["pixel_scale"]
            if scale is None:
                px, py = self.pixelVectors()
                scale = (px.length(), py.length()) if px is not None else (1, 1)
            padding = max(width, outline_width or 0) / 2
            if self.opts["arrows"] is not None:
                padding = max(padding, _ARROW_OUTLINE_WIDTH * 2)
            # Include cosmetic strokes, arrow miter joins, and antialiasing.
            margin = (padding + 1) * np.abs(scale)
            low, high = points.min(axis=0) - margin, points.max(axis=0) + margin
            self._bounding_rect = QtCore.QRectF(*low, *(high - low))
            self._shape.addRect(self._bounding_rect)
