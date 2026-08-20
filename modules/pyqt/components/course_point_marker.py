from functools import cache

from modules._qt_qtwidgets import QtCore, QtGui

DEFAULT_COURSE_POINT_ICON_PATH = "img/navi_flag_white.svg"
COURSE_POINT_MARKER_SIZE = 24
COURSE_POINT_ICON_SIZE = 16
COURSE_POINT_MARKER_BG_COLOR = (0, 128, 0, 240)
COURSE_POINT_MARKER_BORDER_COLOR = (0, 0, 0, 220)
COURSE_POINT_MARKER_BORDER_WIDTH = 1


@cache
def build_course_point_marker_pixmap(
    icon_path,
    marker_size=COURSE_POINT_MARKER_SIZE,
    icon_size=COURSE_POINT_ICON_SIZE,
    background_color=COURSE_POINT_MARKER_BG_COLOR,
    border_color=COURSE_POINT_MARKER_BORDER_COLOR,
    border_width=COURSE_POINT_MARKER_BORDER_WIDTH,
):
    pixmap = QtGui.QPixmap(marker_size, marker_size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)

    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QtGui.QPen(QtGui.QColor(*border_color), border_width))
    painter.setBrush(QtGui.QColor(*background_color))
    radius = marker_size / 2.0 - 1
    painter.drawEllipse(
        QtCore.QPointF(marker_size / 2.0, marker_size / 2.0),
        radius,
        radius,
    )

    icon = QtGui.QIcon(icon_path)
    offset = int(round((marker_size - icon_size) / 2))
    icon.paint(painter, QtCore.QRect(offset, offset, icon_size, icon_size))
    painter.end()
    return pixmap
