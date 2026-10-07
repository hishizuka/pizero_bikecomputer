from pyqtgraph.Qt import QtCore
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject
from modules.qt_map_assets import build_wind_vane_picture


class WindVaneItem(GraphicsObject):
    """A fixed-pixel wind direction marker centered at its map position."""

    def __init__(self, angle, color, size):
        super().__init__()
        self.setFlag(self.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setCacheMode(self.CacheMode.DeviceCoordinateCache)
        self._picture = build_wind_vane_picture(angle, tuple(color), size)
        self._bounding = QtCore.QRectF(self._picture.boundingRect())

    def paint(self, painter, *args):
        self._picture.play(painter)

    def boundingRect(self):
        return self._bounding
