from pyqtgraph import functions as fn
from pyqtgraph.Qt import QtCore, QtGui
from pyqtgraph.graphicsItems.GraphicsObject import GraphicsObject


__all__ = ["WindVaneItem"]


class WindVaneItem(GraphicsObject):
    """A streamlined wind direction marker for map display.

    Draws a sleek arrow with a sharp tip and a deep forked (swallow-tail)
    back, so the wind direction is immediately obvious at any rotation.
    The pointed tip follows the legacy map marker convention used by
    ``pg.ArrowItem(angle=wind_direction-90)``.

    Parameters
    ----------
    angle : float
        Wind direction in degrees (meteorological: 0=N, 90=E, ...).
        Value is interpreted exactly as in the legacy implementation.
    brush : QBrush / color
        Fill colour (determined by wind speed).
    pen : QPen / color / dict
        Outline pen.
    size : float
        Overall length of the arrow in pixels (default 28).
    offset_ratio : float
        Offset ratio along the marker local Y-axis relative to ``size``.
        For example, ``0.25`` moves the marker by one quarter of its size.
    """

    def __init__(self, angle=0, brush=None, pen=None, size=28, offset_ratio=0.0):
        GraphicsObject.__init__(self)
        # Render in pixel-space so the vane stays a fixed size regardless of
        # map zoom level (same behaviour as pg.ArrowItem with pxMode=True).
        self.setFlags(
            self.flags() | self.GraphicsItemFlag.ItemIgnoresTransformations
        )
        self._angle = angle
        self._brush = fn.mkBrush(brush)
        self._pen = fn.mkPen(pen) if pen is not None else fn.mkPen("k", width=2)
        self._size = size
        self._offset_ratio = offset_ratio
        self._picture = None
        self._bounding = None

    # ----- drawing -----

    def _build(self):
        s = self._size

        # Sharp arrow pointing UP in local coordinates, tip at origin (0,0).
        # All straight lines for a crisp, angular look.
        #
        #         tip (0, 0)        <-- origin / anchor
        #          /\
        #         /  \
        #        /    \
        #  fin-L/      \fin-R      (wide swept-back fins)
        #       \      /
        #        \    /
        #         \  /
        #        notch              (deep V-fork)

        path = QtGui.QPainterPath()
        path.moveTo(0, 0)                       # tip
        path.lineTo(s * 0.24, s * 0.85)         # right fin
        path.lineTo(0, s * 0.40)                # center notch (deeper fork)
        path.lineTo(-s * 0.24, s * 0.85)        # left fin
        path.closeSubpath()                      # back to tip

        self._path = path

        # Pre-render to QPicture for fast replay
        pic = QtGui.QPicture()
        p = QtGui.QPainter(pic)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # Keep rotation compatibility with the legacy ArrowItem rendering:
        # old code used angle=(wind_direction - 90) with ArrowItem(0=left),
        # so this custom shape needs +180deg to match the same final heading.
        p.rotate(self._angle + 180)
        # Apply local Y-axis offset after rotation.
        p.translate(0, s * self._offset_ratio)

        # Main body
        p.setPen(self._pen)
        p.setBrush(self._brush)
        p.drawPath(path)

        p.end()
        self._picture = pic
        # Cache bounds once; include a small pen margin for antialias fringes.
        self._bounding = QtCore.QRectF(pic.boundingRect()).adjusted(-2, -2, 2, 2)

    def paint(self, p, *args):
        if self._picture is None:
            self._build()
        self._picture.play(p)

    def boundingRect(self):
        if self._bounding is None:
            self._build()
        return self._bounding
