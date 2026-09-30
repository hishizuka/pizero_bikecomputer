from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject
from pyqtgraph.Qt import QtCore, QtGui


def _points_to_polygon(points):
    polygon = QtGui.QPolygonF()
    for x_pos, y_pos in points:
        polygon.append(QtCore.QPointF(x_pos, y_pos))
    return polygon


class CourseGraphItem(GraphicsObject):
    """Regenerate a course graph's picture when its drawing options change."""

    def __init__(self):
        super().__init__()
        self.picture = None

    def setOpts(self, **opts):
        self.prepareGeometryChange()
        self.opts.update(opts)
        self.picture = None
        self.update()
        self.informViewBoundsChanged()

    def paint(self, painter, *args):
        if self.picture is None:
            self.drawPicture()
        self.picture.play(painter)

    def boundingRect(self):
        if self.picture is None:
            self.drawPicture()
        return self._bounding_rect

    def shape(self):
        if self.picture is None:
            self.drawPicture()
        return self._shape
