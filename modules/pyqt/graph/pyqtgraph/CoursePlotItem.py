import numpy as np

from pyqtgraph import functions as fn
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject


__all__ = ["CoursePlotItem"]


class CoursePlotItem(GraphicsObject):
    def __init__(self, **opts):
        """
        Valid keyword options are:
        x, y, width, brush, outline_width, outline_color

        Example uses:

            CoursePlotItem(x=lon, y=lat, brush=[np.nan,(color0-1),(color1-2),(color2-3),(color3-4)], width=6)

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
        self.picture = None
        self.setOpts(**opts)

    def setOpts(self, **opts):
        self.opts.update(opts)
        self.picture = None
        self._shape = None
        self.update()
        self.informViewBoundsChanged()

    def drawPicture(self):
        self.picture = QtGui.QPicture()
        self._shape = QtGui.QPainterPath()
        p = QtGui.QPainter(self.picture)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        def asarray(x):
            if x is None or np.isscalar(x) or isinstance(x, np.ndarray):
                return x
            return np.array(x)

        x = asarray(self.opts.get("x"))
        y = asarray(self.opts.get("y"))
        brushes = asarray(self.opts.get("brushes"))
        width = self.opts.get("width")
        outline_width = self.opts.get("outline_width")
        outline_color = self.opts.get("outline_color")

        # Build segment list: [(QPolygonF, color), ...]
        segments = []
        pre_color = None
        color = None
        points = 0
        lines = None
        n = len(x if not np.isscalar(x) else y)
        for i in range(n):
            if i == 0:
                continue
            if brushes is not None:
                color = tuple(brushes[i])

            if np.isnan(y[i]):
                continue

            if points == 0:
                lines = QtGui.QPolygonF()
                lines.append(QtCore.QPointF(x[i - 1], y[i - 1]))

            lines.append(QtCore.QPointF(x[i], y[i]))

            if (i > 1 and pre_color != color) or (i == n - 1):
                segments.append((lines, pre_color))
                points = 0
            else:
                points += 1

            pre_color = color

        # Pass 1: draw dark outline for contrast
        if outline_width is not None:
            outline_pen = fn.mkPen(color=outline_color, width=outline_width)
            outline_pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            outline_pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            for seg_lines, _seg_color in segments:
                p.setPen(outline_pen)
                p.drawPolyline(seg_lines)

        # Pass 2: draw colored course line on top
        for seg_lines, seg_color in segments:
            pen = fn.mkPen(color=seg_color, width=width)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPolyline(seg_lines)

        p.end()
        self.prepareGeometryChange()

    def paint(self, p, *args):
        if self.picture is None:
            self.drawPicture()
        self.picture.play(p)

    def boundingRect(self):
        if self.picture is None:
            self.drawPicture()
        return QtCore.QRectF(self.picture.boundingRect())

    def shape(self):
        if self.picture is None:
            self.drawPicture()
        return self._shape
