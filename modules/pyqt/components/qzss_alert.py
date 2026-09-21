"""Configurable QZSS banner and icon-led fullscreen alert."""

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from modules._qt_qtwidgets import QtCore, QtGui, QtWidgets
from modules.app_logger import app_logger
from modules.helper.qzss_popup_layout import (
    message_units,
    paginate_groups,
    region_groups,
)
from modules.pyqt.components.button_widget import CloseButton
from modules.sensor.gps.ublox_support.qzss_dcr import Category, JMA_MESSAGE_TYPE
from modules.sensor.gps.ublox_support.qzss_dcr_view import build_popup_content

ROOT = Path(__file__).resolve().parents[3]
YELLOW = "#FFFF00"
FAMILY = "Noto Sans CJK JP"


@dataclass(frozen=True)
class BannerStyle:
    background: str = "black"
    foreground: str = YELLOW
    message_color: str = "white"
    message_size: int = 34


@lru_cache(maxsize=1)
def prepare_font():
    path = ROOT / "fonts/NotoSansCJKjp-Black.otf"
    if path.is_file():
        QtGui.QFontDatabase.addApplicationFont(str(path.resolve()))
    if "Black" not in QtGui.QFontDatabase.styles(FAMILY):
        app_logger.warning("QZSS: Noto Sans CJK JP Black is unavailable; using Bold")
    font.cache_clear()


@lru_cache(maxsize=64)
def font(size, bold=False):
    if bold:
        style = "Black" if "Black" in QtGui.QFontDatabase.styles(FAMILY) else "Bold"
        result = QtGui.QFontDatabase.font(FAMILY, style, 12)
        result.setStyleName(style)
    else:
        result = QtGui.QFont(QtWidgets.QApplication.font())
        result.setFamilies(result.families() + [FAMILY])
        result.setBold(False)
    result.setPixelSize(size)
    return result


def text_lines(text, width, size, bold=False):
    layout = QtGui.QTextLayout(text, font(size, bold))
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    result = []
    consumed = 0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        line.setPosition(QtCore.QPointF())
        assert line.naturalTextWidth() <= width + 0.1
        result.append((layout, line, math.ceil(line.height()) + 2))
        consumed += line.textLength()
    layout.endLayout()
    assert consumed == len(text.encode("utf-16-le")) // 2
    return result


def height(lines):
    return sum(row[2] for row in lines)


def lines(text, width, size, bold=False, units=None):
    metrics = QtGui.QFontMetricsF(font(size, bold))
    units = units or [text]
    assert "".join(units) == text
    packed, current = [], ""
    for unit in units:
        if current and metrics.horizontalAdvance(current + unit) > width:
            packed.append(current)
            current = ""
        current += unit
    if current:
        packed.append(current)
    result = []
    for part in packed:
        for layout, line, _ in text_lines(part, width, size, bold):
            result.append((layout, line, math.ceil(size * 1.32)))
    return result


def draw(painter, rows, x, y, width, color, centered=False):
    painter.setPen(QtGui.QColor(color))
    for layout, line, step in rows:
        text = (
            layout.text()
            .encode("utf-16-le")[
                2 * line.textStart() : 2 * (line.textStart() + line.textLength())
            ]
            .decode("utf-16-le")
        )
        ink = QtGui.QFontMetricsF(layout.font()).tightBoundingRect(text)
        offset = (width - line.naturalTextWidth()) / 2 if centered else 0
        top = (step - ink.height()) / 2 - line.ascent() - ink.top()
        line.draw(painter, QtCore.QPointF(x + offset, y + top))
        y += step
    return y


@lru_cache(maxsize=16)
def load_icon(category):
    if category in (
        Category.EEW,
        Category.EPICENTER,
        Category.INTENSITY,
        Category.NANKAI,
    ):
        name = "qzss_earthquake.png"
    elif category in (Category.TSUNAMI, Category.NW_PACIFIC_TSUNAMI):
        name = "qzss_tsunami.png"
    else:
        return QtGui.QIcon(str(ROOT / "img/warning.svg")).pixmap(128, 128).toImage()
    image = QtGui.QImage(str(ROOT / "img" / name))
    # Both distributed PNGs are indexed: transform 33 colors, not 648² pixels.
    for index, rgba in enumerate(image.colorTable()):
        color = QtGui.QColor.fromRgba(rgba)
        if color.red() > color.blue() * 2 and color.green() > color.blue() * 2:
            level = min(255, round(255 * max(color.red(), color.green()) / 242))
            image.setColor(index, QtGui.QColor(level, level, 0, color.alpha()).rgba())
    return image.convertToFormat(QtGui.QImage.Format.Format_ARGB32)


class QzssAlertWidget(QtWidgets.QWidget):
    """Paint live alert text over the app; retain real close and page controls."""

    # Internal design choices: band (prototypes 1/2/4) or full (prototype 3).
    LAYOUT = "band"
    BAND_STYLE = BannerStyle()

    def __init__(self, parent, close_callback):
        super().__init__(parent)
        self.page_index = 0
        self.pages = [[]]
        self.close_button = CloseButton(self)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.next_button = QtWidgets.QPushButton(self)
        self.next_button.setFont(font(14))
        self.next_button.setStyleSheet(
            "QPushButton { color: white; background: black; border: 1px solid white; border-radius: 3px; padding: 0; } QPushButton:focus { border: 2px solid white; }"
        )
        self.close_button.clicked.connect(close_callback)
        self.back = close_callback
        self.next_button.clicked.connect(self.next_page)
        parent.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.Resize and not self.isHidden():
            self.page_index = 0
            self._plan()
            self._place()
        return False

    def keyPressEvent(self, event):
        if event.key() in (
            QtCore.Qt.Key.Key_Space,
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.Key.Key_Escape,
        ):
            self.back()
        else:
            super().keyPressEvent(event)

    def set_event(self, event, weather_pairs=None):
        family = self.LAYOUT
        prepare_font()
        self.event = event
        self.family = family
        self.style = self.BAND_STYLE
        self.content = build_popup_content(event, weather_pairs)
        self.title_text = self.content.title.removeprefix("[test] ").removeprefix(
            "[訓練] "
        )
        self.marker = (
            "表示テスト"
            if event.get("is_test")
            else "訓練" if event.get("is_training") else ""
        )
        self.rows = list(self.content.regions + self.content.supplement)
        self.action = self.content.action
        self.icon = load_icon(
            event["category_no"] if event["message_type"] == JMA_MESSAGE_TYPE else None
        )
        if family == "band":
            occupied = [
                x
                for x in range(self.icon.width())
                if any(
                    self.icon.pixelColor(x, y).alpha()
                    for y in range(self.icon.height())
                )
            ]
            self.visible_icon_width = (
                (max(occupied) - min(occupied) + 1) * 70 / self.icon.width()
            )
            self.icon = self.icon.copy(
                min(occupied), 0, max(occupied) - min(occupied) + 1, self.icon.height()
            )
        self.page_index = 0
        self._plan()
        self._place()
        self.show()
        self.raise_()
        self.setFocus()

    def focusNextPrevChild(self, forward):
        buttons = (
            [self.next_button, self.close_button]
            if len(self.pages) > 1
            else [self.close_button]
        )
        current = QtWidgets.QApplication.focusWidget()
        index = buttons.index(current) if current in buttons else (-1 if forward else 0)
        buttons[(index + (1 if forward else -1)) % len(buttons)].setFocus()
        return True

    def _plan(self):
        full = self.family == "full"
        self.content_width = self.parentWidget().width() - 24
        self.icon_size = (
            (112 if self.parentWidget().height() >= 400 else 48) if full else 70
        )
        title_width = (
            self.content_width
            if full
            else self.parentWidget().width() - self.visible_icon_width - 10
        )
        title_units = (
            ["土砂災害", "警戒情報"]
            if full and self.title_text == "土砂災害警戒情報"
            else None
        )
        self.title = lines(
            self.title_text, title_width, 34 if full else 24, True, title_units
        )
        if full:
            self.title = [(layout, line, 42) for layout, line, _ in self.title]
        self.title_height = height(self.title)
        self.marker_height = 20 if self.marker else 0
        self.icon_top_gap, self.icon_bottom_gap = 12, 20
        self.header_height = (
            self.marker_height
            + self.title_height
            + self.icon_top_gap
            + self.icon_size
            + self.icon_bottom_gap
            if full
            else max(86, self.title_height + self.marker_height + 16)
        )
        self.message_size = 40 if full else self.style.message_size
        self.main = self._message_lines()
        if full and self.action:
            # Preserve a complete instruction beside the icon on long notices.
            minimum = (
                self.marker_height
                + self.title_height
                + self.icon_size
                + 24
                * (len(self.content.supplement) + min(2, len(self.content.regions)))
                + 44
                + (62 if len(self.content.regions) > 1 else 24)
            )
            while (
                minimum + height(self.main) > self.parentWidget().height()
                and self.message_size > 26
            ):
                self.message_size -= 2
                self.main = self._message_lines()
        size = 18 if self.main else 22
        metrics = QtGui.QFontMetricsF(font(size))

        def wrap_region(text):
            return lines(text, self.content_width, size)

        # Keep the lines of one long name together across page boundaries.
        regional = region_groups(
            self.content.regions,
            self.content_width,
            metrics.horizontalAdvance,
            wrap_region,
        )
        regional = [
            wrap_region(group[0]) if isinstance(group[0], str) else group
            for group in regional
        ]
        self.pinned = []
        for text in self.content.supplement:
            if self.main:
                self.pinned.extend(wrap_region(text))
            else:
                regional.append(wrap_region(text))
        if not full and len(regional) == 1 and len(regional[0]) == 1:
            joined = regional[0][0][0].text()
            if self.pinned:
                joined += "　" + "　".join(self.content.supplement)
            if metrics.horizontalAdvance(joined) <= self.content_width:
                regional = [wrap_region(joined)]
                self.pinned = []
        self.body_top = 16 if not full else 0
        self.message_gap = 16 if self.main else 0
        self.footer_gap = 14
        self.fixed_height = (
            self.header_height
            + self.body_top
            + height(self.pinned)
            + self.message_gap
            + height(self.main)
            + self.footer_gap
            + 44
        )
        available = self.parentWidget().height() - self.fixed_height
        line_height = math.ceil(size * 1.32)
        minimum_body = line_height if regional else 0
        if full and available < minimum_body:
            # Tighten spacing for long guidance without shrinking text or icons.
            gaps = (
                self.icon_top_gap
                + self.icon_bottom_gap
                + self.message_gap
                + self.footer_gap
            )
            ratio = max(0, (available + gaps - minimum_body - 2) / (gaps - 2))
            self.icon_top_gap *= ratio
            self.icon_bottom_gap *= ratio
            self.message_gap *= ratio
            self.footer_gap = 2 + (self.footer_gap - 2) * ratio
            self.header_height = (
                self.marker_height
                + self.title_height
                + self.icon_top_gap
                + self.icon_size
                + self.icon_bottom_gap
            )
            self.fixed_height = (
                self.header_height
                + height(self.pinned)
                + self.message_gap
                + height(self.main)
                + self.footer_gap
                + 44
            )
            available = self.parentWidget().height() - self.fixed_height
        self.flow_pages = []
        if available + 0.001 < minimum_body:
            # Exceptional long instructions flow across pages without losing text.
            # Normal notices retain their repeated, prominent instruction.
            groups = [[(row, "white") for row in group] for group in regional]
            groups += [[(row, "white")] for row in self.pinned]
            color = "white" if full else self.style.message_color
            groups += [[(row, color)] for row in self.main]
            self.pinned = []
            self.main = []
            self.message_gap = 0
            self.fixed_height = (
                self.header_height + self.body_top + self.footer_gap + 44
            )
            capacity = self.parentWidget().height() - self.fixed_height
            self.flow_pages = [[]]
            used = 0
            for group in groups:
                group_height = sum(row[2] for row, _ in group)
                if self.flow_pages[-1] and used + group_height > capacity:
                    self.flow_pages.append([])
                    used = 0
                for row, color in group:
                    if used + row[2] > capacity and self.flow_pages[-1]:
                        self.flow_pages.append([])
                        used = 0
                    self.flow_pages[-1].append((row, color))
                    used += row[2]
            self.pages = [[row for row, _ in page] for page in self.flow_pages]
        else:
            self.pages = paginate_groups(
                regional, max(1, int((available + 0.001) // line_height))
            )

    def _message_lines(self):
        if not self.action:
            return []
        measure = QtGui.QFontMetricsF(font(self.message_size, True)).horizontalAdvance
        rows = lines(
            self.action,
            self.content_width,
            self.message_size,
            True,
            message_units(self.action, self.content_width, measure),
        )
        if self.family == "full":
            rows = [
                (layout, line, math.ceil(self.message_size * 1.22))
                for layout, line, _ in rows
            ]
        return rows

    def _place(self):
        required = self.fixed_height + height(self.pages[self.page_index])
        full = self.family == "full"
        panel_height = (
            self.parentWidget().height() if full or len(self.pages) > 1 else required
        )
        assert panel_height <= self.parentWidget().height()
        self.setGeometry(
            0,
            self.parentWidget().height() - panel_height,
            self.parentWidget().width(),
            panel_height,
        )
        self.close_button.move(
            (self.width() - 44) // 2 if full else self.width() - 48, self.height() - 44
        )
        self.next_button.setGeometry(12, self.height() - 34, 90, 26)
        self.next_button.setText(f"{self.page_index + 1}/{len(self.pages)} 次へ")
        self.next_button.setVisible(len(self.pages) > 1)
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor("black"))
        full = self.family == "full"
        page = self.pages[self.page_index]
        spare = self.height() - self.fixed_height - height(page)
        if full:
            extra = min(12, spare / 4)
            y = max(0, (spare - 2 * extra) / 2)
            if self.marker:
                draw(
                    p,
                    lines(self.marker, self.content_width, 14),
                    12,
                    y,
                    self.content_width,
                    YELLOW,
                    True,
                )
                y += self.marker_height
            y = (
                draw(p, self.title, 12, y, self.content_width, YELLOW, True)
                + self.icon_top_gap
                + extra
            )
            p.drawImage(
                QtCore.QRectF(
                    (self.width() - self.icon_size) / 2,
                    y,
                    self.icon_size,
                    self.icon_size,
                ),
                self.icon,
            )
            y += self.icon_size + self.icon_bottom_gap + extra
        else:
            p.fillRect(
                0,
                0,
                self.width(),
                self.header_height,
                QtGui.QColor(self.style.background),
            )
            text_width = max(row[1].naturalTextWidth() for row in self.title)
            if self.marker:
                text_width = max(
                    text_width,
                    QtGui.QFontMetricsF(font(14)).horizontalAdvance(self.marker),
                )
            x = (self.width() - self.visible_icon_width - 4 - text_width) / 2
            assert x >= 3 - 0.1
            p.drawImage(
                QtCore.QRectF(
                    x, (self.header_height - 70) / 2, self.visible_icon_width, 70
                ),
                self.icon,
            )
            y = draw(
                p,
                self.title,
                x + self.visible_icon_width + 4,
                (self.header_height - self.title_height - self.marker_height) / 2,
                text_width,
                self.style.foreground,
            )
            if self.marker:
                draw(
                    p,
                    lines(self.marker, text_width, 14),
                    x + self.visible_icon_width + 4,
                    y,
                    text_width,
                    self.style.foreground,
                )
            y = self.header_height + self.body_top
        if self.flow_pages:
            for row, color in self.flow_pages[self.page_index]:
                y = draw(p, [row], 12, y, self.content_width, color, full)
        else:
            y = draw(p, page, 12, y, self.content_width, "white", full)
        y = draw(p, self.pinned, 12, y, self.content_width, "white", full)
        y += self.message_gap
        y = draw(
            p,
            self.main,
            12,
            y,
            self.content_width,
            "white" if full else self.style.message_color,
            full,
        )
        self.content_bottom = y
        assert y <= self.close_button.y() - 2, (
            self.title_text,
            y,
            self.close_button.y(),
        )
        p.end()

    def next_page(self):
        self.page_index = (self.page_index + 1) % len(self.pages)
        self._place()
