import numpy as np

from pyqtgraph import functions as fn
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject


__all__ = ["CoursePlotItem"]


class CoursePlotItem(GraphicsObject):
    def __init__(self, **opts):
        """
        Valid keyword options are:
        x, y, width, brush

        Example uses:

            CoursePlotItem(x=lon, y=lat, brush=[np.nan,(color0-1),(color1-2),(color2-3),(color3-4)], width=6)

        """
        GraphicsObject.__init__(self)
        self.opts = dict(
            x=None,
            y=None,
            width=None,
            brushes=None,
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

        def asarray(x):
            if x is None or np.isscalar(x) or isinstance(x, np.ndarray):
                return x
            return np.array(x)

        x = asarray(self.opts.get("x"))
        y = asarray(self.opts.get("y"))
        brushes = asarray(self.opts.get("brushes"))
        width = self.opts.get("width")

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
                p.setPen(fn.mkPen(color=pre_color, width=width))
                p.drawPolyline(lines)
                points = 0
            else:
                points += 1

            pre_color = color

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
