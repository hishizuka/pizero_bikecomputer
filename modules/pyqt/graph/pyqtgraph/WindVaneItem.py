from pyqtgraph import functions as fn
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject


def build_wind_vane_picture(angle, color, size):
    path = QtGui.QPainterPath()
    path.moveTo(0, size * 0.425)
    path.lineTo(0, -size * 0.425)
    path.moveTo(-size * 0.20, -size * 0.18)
    path.lineTo(0, -size * 0.425)
    path.lineTo(size * 0.20, -size * 0.18)
    path.moveTo(size * 0.04, size * 0.225)
    path.lineTo(size * 0.25, size * 0.36)
    path.moveTo(size * 0.04, size * 0.073)
    path.lineTo(size * 0.21, size * 0.17)

    picture = QtGui.QPicture()
    painter = QtGui.QPainter(picture)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    # Preserve the legacy wind-direction convention.
    painter.rotate(angle + 180)
    color_width = size * 0.12
    for pen_color, width in (
        ("w", color_width + 8),
        ("k", color_width + 4),
        (color, color_width),
    ):
        pen = fn.mkPen(pen_color, width=width)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.drawPath(path)
    painter.end()
    return picture


class WindVaneItem(GraphicsObject):
    """A fixed-pixel wind direction marker centered at its map position."""

    def __init__(self, angle, color, size):
        super().__init__()
        self.setFlag(self.GraphicsItemFlag.ItemIgnoresTransformations)
        self._picture = build_wind_vane_picture(angle, color, size)
        self._bounding = QtCore.QRectF(self._picture.boundingRect())

    def paint(self, painter, *args):
        self._picture.play(painter)

    def boundingRect(self):
        return self._bounding
