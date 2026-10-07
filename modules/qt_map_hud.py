"""Shared map HUD parts rendered on the GUI thread for QWidget and Qt Quick."""

from functools import lru_cache
import math

from modules._qt_ver import QtCore, QtGui
from modules.map.content import (
    DEFAULT_INSTRUCTION_ICON,
    INSTRUCTION_ICONS,
    instruction_distance_text,
)
from modules.map.overlays import legend_pixels
from modules.map.style import (
    COURSE_POINT_ICON_SIZE,
    COURSE_POINT_MARKER_SIZE,
    MAP_CONTROLS_STYLE,
)
from modules.qt_map_assets import (
    build_course_point_marker_pixmap,
    instruction_icon_image,
)


def _image(width, height, ratio):
    image = QtGui.QImage(
        round(width * ratio),
        round(height * ratio),
        QtGui.QImage.Format.Format_RGBA8888_Premultiplied,
    )
    image.setDevicePixelRatio(ratio)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    return image


def _font_key():
    return QtGui.QGuiApplication.font().toString()


@lru_cache(maxsize=64)
def _text_image(html, ratio, font_key):
    font = QtGui.QFont()
    font.fromString(font_key)
    document = QtGui.QTextDocument()
    document.setDefaultFont(font)
    document.setDocumentMargin(0)
    document.setHtml(html)
    document.adjustSize()
    image = _image(
        math.ceil(document.size().width()) + 2,
        math.ceil(document.size().height()) + 2,
        ratio,
    )
    image.fill(QtCore.Qt.GlobalColor.white)
    painter = QtGui.QPainter(image)
    painter.translate(1, 1)
    document.drawContents(painter)
    painter.end()
    return image


def attribution_image(text, ratio):
    return _text_image(
        '<div style="text-align:right;font-size:small;color:black">' + text + "</div>",
        ratio,
        _font_key(),
    )


def scale_image(text, bar_width, ratio):
    return _scale_image(text, round(bar_width), ratio, _font_key())


@lru_cache(maxsize=32)
def _scale_image(text, bar_width, ratio, font_key):
    label = _text_image(
        '<div style="text-align:center;color:black">'
        + text.replace("\n", "<br />")
        + "</div>",
        ratio,
        font_key,
    )
    size = label.deviceIndependentSize()
    width, height = max(bar_width, size.width()), size.height() + 12
    image = _image(width, height, ratio)
    painter = QtGui.QPainter(image)
    painter.drawImage(QtCore.QPointF(round((width - size.width()) / 2), 0), label)
    x, y = round((width - bar_width) / 2), size.height()
    for rect in (
        QtCore.QRectF(x, y, 3, 12),
        QtCore.QRectF(x + bar_width - 3, y, 3, 12),
        QtCore.QRectF(x, y + 9, bar_width, 3),
    ):
        painter.fillRect(rect, QtCore.Qt.GlobalColor.black)
    painter.end()
    return image


def legend_image(spec, ratio):
    values = spec["label_values"]
    labels = tuple(
        str(value) + ("~" if i == 1 and isinstance(value, (int, float)) else "")
        for i, value in enumerate(values)
    )
    return _legend_image(
        tuple(map(tuple, spec["colors"])),
        labels,
        spec["block_width"],
        spec["height"],
        ratio,
        _font_key(),
    )


@lru_cache(maxsize=16)
def _legend_image(colors, labels, block_width, bar_height, ratio, font_key):
    left, right = (
        _text_image(
            '<span style="font-size:small;color:black">' + text + "</span>",
            ratio,
            font_key,
        )
        for text in labels
    )
    ls, rs = left.deviceIndependentSize(), right.deviceIndependentSize()
    width, height = ls.width() + 4 + 120 + 4 + rs.width(), max(
        12, ls.height(), rs.height()
    )
    image = _image(width, height, ratio)
    pixels = legend_pixels(colors, block_width, bar_height)
    bar = QtGui.QImage(
        pixels.data,
        pixels.shape[1],
        pixels.shape[0],
        pixels.shape[1] * 4,
        QtGui.QImage.Format.Format_RGBA8888,
    )
    painter = QtGui.QPainter(image)
    painter.drawImage(QtCore.QPointF(0, round((height - ls.height()) / 2)), left)
    painter.drawImage(
        QtCore.QPointF(width - rs.width(), round((height - rs.height()) / 2)), right
    )
    painter.drawImage(
        QtCore.QRectF(ls.width() + 4, round((height - 12) / 2), 120, 12), bar
    )
    painter.end()
    return image


def instruction_image(name, distance, ratio):
    return _instruction_image(
        INSTRUCTION_ICONS.get(name, DEFAULT_INSTRUCTION_ICON),
        instruction_distance_text(distance).strip(),
        ratio,
        _font_key(),
    )


@lru_cache(maxsize=32)
def _instruction_image(icon_path, text, ratio, font_key):
    icon = instruction_icon_image(icon_path, ratio)
    font = QtGui.QFont()
    font.fromString(font_key)
    font.setPixelSize(28)
    metrics = QtGui.QFontMetricsF(font)
    glyphs = QtGui.QPainterPath()
    glyphs.addText(QtCore.QPointF(0, 0), font, text)
    ink = glyphs.boundingRect()
    width = math.ceil(
        6 + 36 + 8 + max(metrics.horizontalAdvance(text), ink.right()) + 6
    )
    height = math.ceil(max(36, ink.height()) + 2)
    image = _image(width, height, ratio)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.black, 1))
    painter.setBrush(QtGui.QColor(0, 128, 0))
    painter.drawRoundedRect(QtCore.QRectF(0.5, 0.5, width - 1, height - 1), 10, 10)
    size = icon.deviceIndependentSize()
    # Center the visible icon and glyphs, rather than their unequal line boxes.
    painter.drawImage(
        QtCore.QPointF(6 + (36 - size.width()) / 2, (height - size.height()) / 2), icon
    )
    painter.setFont(font)
    painter.setPen(QtCore.Qt.GlobalColor.white)
    painter.drawText(QtCore.QPointF(6 + 36 + 8, height / 2 - ink.center().y()), text)
    painter.end()
    return image


def instruction_position(size, width, height, controls=()):
    rect = QtCore.QRectF(
        QtCore.QPointF(
            round(max(0, min(width - size.width(), (width - size.width()) / 2))),
            round(
                max(0, min(height - size.height(), height * 0.15 - size.height() / 2))
            ),
        ),
        size,
    )
    for control in controls:
        if rect.adjusted(-4, -4, 4, 4).intersects(control):
            rect.moveTop(control.bottom() + 4)
    return rect.topLeft()


def map_controls_rects(width, has_times, has_route=False):
    style = MAP_CONTROLS_STYLE
    bw, bh = style["button_width"], style["button_height"]
    padding, spacing = style["padding"], style["spacing"]
    right_width = padding * 2 + bw * (2 if has_times else 1)
    right_height = padding * 2 + bh * (2 if has_times else 1)
    if has_times:
        right_width += spacing
        right_height += spacing
    left_height = padding * 2 + bh * 3 + spacing * 2
    if has_route:
        left_height += bh + spacing + style["route_spacing"]
    return (
        QtCore.QRectF(0, 0, padding * 2 + bw, left_height),
        QtCore.QRectF(width - right_width, 0, right_width, right_height),
    )


def hud_position(kind, size, width, height, attribution_height=0):
    x = 6 if kind == "scale" else width - (10 if kind == "legend" else 6) - size.width()
    y = height - 6 - size.height()
    if kind == "legend":
        y += 1 - attribution_height
    return QtCore.QPointF(round(max(0, x)), round(max(0, y)))


class HudImage:
    def __init__(self):
        self.key = None
        self.image = QtGui.QImage()
        self.fixed_parts = {}
        self.instruction_image = QtGui.QImage()
        self.instruction_rect = QtCore.QRectF()

    @staticmethod
    def _draw_markers(painter, hud, ratio, width, height):
        for x, y, icon in hud.markers:
            marker = build_course_point_marker_pixmap(
                icon,
                COURSE_POINT_MARKER_SIZE,
                COURSE_POINT_ICON_SIZE,
                pixel_ratio=ratio,
            )
            painter.drawPixmap(
                QtCore.QPointF(
                    x - COURSE_POINT_MARKER_SIZE / 2, y - COURSE_POINT_MARKER_SIZE / 2
                ),
                marker,
            )
        if hud.center_size:
            painter.setPen(QtGui.QPen(QtCore.Qt.GlobalColor.black, 2))
            x, y, half = width / 2, height / 2, hud.center_size / 2
            painter.drawLine(QtCore.QPointF(x - half, y), QtCore.QPointF(x + half, y))
            painter.drawLine(QtCore.QPointF(x, y - half), QtCore.QPointF(x, y + half))

    def render(self, frame, include_instruction=True, controls=(), split=False):
        view, hud = frame.snapshot.view, frame.hud
        if hud is None:
            return self.image
        legend = hud.legend
        key = (
            include_instruction,
            split,
            view.width,
            view.height,
            view.pixel_ratio,
            _font_key(),
            tuple((r.x(), r.y(), r.width(), r.height()) for r in controls),
            hud.scale_text,
            round(hud.scale_width),
            hud.attribution,
            hud.markers,
            hud.center_size,
            hud.instruction_name,
            (
                None
                if hud.instruction_distance is None
                else instruction_distance_text(hud.instruction_distance)
            ),
            None if legend is None else legend["key"],
        )
        if key == self.key:
            return self.image
        self.key = key
        self.fixed_parts = {}
        self.instruction_image = QtGui.QImage()
        self.instruction_rect = QtCore.QRectF()
        ratio = view.pixel_ratio
        width, height = view.width / ratio, view.height / ratio
        image = _image(width, height, ratio)
        painter = QtGui.QPainter(image)
        self._draw_markers(painter, hud, ratio, width, height)
        parts = {}
        if hud.scale_text:
            parts["scale"] = scale_image(hud.scale_text, hud.scale_width, ratio)
        if hud.attribution:
            parts["attribution"] = attribution_image(hud.attribution, ratio)
        if legend is not None:
            parts["legend"] = legend_image(legend, ratio)
        attribution_height = (
            parts["attribution"].deviceIndependentSize().height()
            if hud.attribution
            else 0
        )
        self.fixed_parts = {
            kind: (
                part,
                hud_position(
                    kind,
                    part.deviceIndependentSize(),
                    width,
                    height,
                    attribution_height,
                ),
            )
            for kind, part in parts.items()
        }
        if not split:
            for part, pos in self.fixed_parts.values():
                painter.drawImage(pos, part)
        if hud.instruction_distance is not None:
            instruction = instruction_image(
                hud.instruction_name, hud.instruction_distance, ratio
            )
            size = instruction.deviceIndependentSize()
            pos = instruction_position(size, width, height, controls)
            self.instruction_rect = QtCore.QRectF(pos, size)
            self.instruction_image = instruction
            if include_instruction:
                painter.drawImage(pos, instruction)
        painter.end()
        self.image = image
        return image
