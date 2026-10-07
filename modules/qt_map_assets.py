"""Prepare existing SVG icons on the GUI side, once per display scale."""

from functools import cache, lru_cache
import math
from pathlib import Path

import numpy as np

from modules._qt_ver import QtCore, QtGui, USE_PYSIDE6
from modules.map.geometry import wind_vane_paths
from modules.map.style import (
    COURSE_POINT_MARKER_SIZE,
    COURSE_POINT_ICON_SIZE,
    COURSE_POINT_MARKER_BG_COLOR,
    COURSE_POINT_MARKER_BORDER_COLOR,
    COURSE_POINT_MARKER_BORDER_WIDTH,
    COURSE_WIND_MARKER_SIZE,
    POSITION_MARKER_BORDER,
    POSITION_MARKER_CANVAS_SIZE,
    POSITION_MARKER_COLORS,
    POSITION_MARKER_SIZE,
)


@lru_cache(maxsize=96)
def build_wind_vane_picture(angle, color, size=COURSE_WIND_MARKER_SIZE):
    path = QtGui.QPainterPath()
    for points in wind_vane_paths(angle, size):
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
    picture = QtGui.QPicture()
    painter = QtGui.QPainter(picture)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    # Preserve the legacy wind-direction convention and three outline strokes.
    color_width = size * 0.12
    for pen_color, width in (
        ((255, 255, 255), color_width + 8),
        ((0, 0, 0), color_width + 4),
        (color, color_width),
    ):
        pen = QtGui.QPen(QtGui.QColor(*pen_color), width)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.drawPath(path)
    painter.end()
    return picture


@lru_cache(maxsize=4)
def position_marker_images(pixel_ratio=1.0):
    reader = QtGui.QImageReader(
        str(Path(__file__).resolve().parents[1] / "img/near_me.svg")
    )
    # Compensate for the SVG's padding to match the legacy marker's visible size.
    icon_size = POSITION_MARKER_SIZE + 2
    reader.setScaledSize(QtCore.QSize(icon_size, icon_size) * pixel_ratio)
    source = reader.read()
    if source.isNull():
        raise RuntimeError(f"Cannot read current-position SVG: {reader.errorString()}")

    size = (
        QtCore.QSize(POSITION_MARKER_CANVAS_SIZE, POSITION_MARKER_CANVAS_SIZE)
        * pixel_ratio
    )
    mask = QtGui.QImage(size, QtGui.QImage.Format.Format_RGBA8888_Premultiplied)
    mask.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(mask)
    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    painter.translate(size.width() / 2, size.height() / 2)
    painter.scale(pixel_ratio, pixel_ratio)
    # The existing location icon points northeast; heading zero points north.
    painter.rotate(-45)
    painter.drawImage(
        QtCore.QRectF(-icon_size / 2, -icon_size / 2, icon_size, icon_size), source
    )
    painter.end()

    images = {}
    for fix, name in ((True, "fix"), (False, "lost")):
        colored = mask.copy()
        painter = QtGui.QPainter(colored)
        painter.setCompositionMode(
            QtGui.QPainter.CompositionMode.CompositionMode_SourceIn
        )
        painter.fillRect(colored.rect(), QtGui.QColor(*POSITION_MARKER_COLORS[name]))
        painter.end()

        image = QtGui.QImage(size, mask.format())
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        # Match the legacy white border, with room around the tip to avoid clipping.
        for step in range(8):
            angle = math.pi * step / 4
            painter.drawImage(
                QtCore.QPointF(
                    math.cos(angle) * POSITION_MARKER_BORDER * pixel_ratio,
                    math.sin(angle) * POSITION_MARKER_BORDER * pixel_ratio,
                ),
                mask,
            )
        painter.drawImage(0, 0, colored)
        painter.end()
        data = image.constBits()
        if not USE_PYSIDE6:
            data.setsize(image.sizeInBytes())
        pixels = np.frombuffer(data, dtype=np.uint8).reshape(
            size.height(), image.bytesPerLine()
        )
        pixels = (
            pixels[:, : size.width() * 4].reshape(size.height(), size.width(), 4).copy()
        )
        pixels.flags.writeable = False
        images[fix] = pixels
    return images


@lru_cache(maxsize=64)
def instruction_icon_image(icon_path, pixel_ratio):
    reader = QtGui.QImageReader(str(Path(__file__).resolve().parents[1] / icon_path))
    reader.setScaledSize(QtCore.QSize(36, 36) * pixel_ratio)
    source = reader.read().convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    if source.isNull():
        raise RuntimeError(f"Cannot read navigation icon: {reader.errorString()}")
    data = source.constBits()
    if not USE_PYSIDE6:
        data.setsize(source.sizeInBytes())
    pixels = (
        np.frombuffer(data, dtype=np.uint8)
        .reshape(source.height(), source.bytesPerLine())[:, : source.width() * 4]
        .reshape(source.height(), source.width(), 4)
    )
    y, x = np.nonzero(pixels[:, :, 3])
    image = source.copy(
        int(x.min()), int(y.min()), int(np.ptp(x) + 1), int(np.ptp(y) + 1)
    )
    image.setDevicePixelRatio(pixel_ratio)
    return image


@cache
def build_course_point_marker_pixmap(
    icon_path,
    marker_size=COURSE_POINT_MARKER_SIZE,
    icon_size=COURSE_POINT_ICON_SIZE,
    background_color=COURSE_POINT_MARKER_BG_COLOR,
    border_color=COURSE_POINT_MARKER_BORDER_COLOR,
    border_width=COURSE_POINT_MARKER_BORDER_WIDTH,
    pixel_ratio=1.0,
):
    pixmap = QtGui.QPixmap(QtCore.QSize(marker_size, marker_size) * pixel_ratio)
    pixmap.setDevicePixelRatio(pixel_ratio)
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

    path = Path(icon_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    icon = QtGui.QIcon(str(path))
    offset = int(round((marker_size - icon_size) / 2))
    icon.paint(painter, QtCore.QRect(offset, offset, icon_size, icon_size))
    painter.end()
    return pixmap
