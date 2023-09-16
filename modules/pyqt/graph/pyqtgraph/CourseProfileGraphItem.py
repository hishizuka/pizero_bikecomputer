import numpy as np

from pyqtgraph import functions as fn
from pyqtgraph import getConfigOption
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject


__all__ = ["CourseProfileGraphItem"]


class CourseProfileGraphItem(GraphicsObject):
    def __init__(self, **opts):
        """
        Valid keyword options are:
        x, y, pen, brush

        Example uses:

            CourseProfileGraphItem(x=range(5), y=[1,5,2,4,3], brush=[np.nan,(color0-1),(color1-2),(color2-3),(color3-4)])


        """
        GraphicsObject.__init__(self)
        self.opts = dict(
            x=None,
            y=None,
            pen=None,
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

        pen = self.opts["pen"]

        if pen is None:
            pen = getConfigOption("foreground")

        def asarray(x):
            if x is None or np.isscalar(x) or isinstance(x, np.ndarray):
                return x
            return np.array(x)

        x = asarray(self.opts.get("x"))
        y = asarray(self.opts.get("y"))
        brushes = asarray(self.opts.get("brushes"))

        p.setPen(fn.mkPen(pen))
        pre_color = None
        color = None
        points = 0
        polygon = None
        n = len(x if not np.isscalar(x) else y)
        for i in range(n):
            if i == 0:
                continue
            if brushes is not None:
                # gradation
                # grad = QtGui.QLinearGradient(x[i], 0, x[i], y[i])
                # grad.setColorAt(0, fn.mkColor([x*0.5 for x in brushes[i]]))
                # grad.setColorAt(1, fn.mkColor(brushes[i]))
                # p.setBrush(grad)
                color = tuple(brushes[i])
                # p.setBrush(fn.mkBrush(color))

            if np.isnan(y[i]):
                continue

            if points == 0:
                polygon = QtGui.QPolygonF()
                polygon.append(QtCore.QPointF(x[i - 1], -100))
                polygon.append(QtCore.QPointF(x[i - 1], y[i - 1]))

            polygon.append(QtCore.QPointF(x[i], y[i]))

            if (i > 1 and pre_color != color) or (i == n - 1):
                polygon.append(QtCore.QPointF(x[i], -100))
                p.setBrush(fn.mkBrush(pre_color))
                p.drawPolygon(polygon)
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
