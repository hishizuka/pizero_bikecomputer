import math
from dataclasses import dataclass

from modules.qt._qt_qtwidgets import QtCore, QtGui
from modules.qt.qt_map_assets import build_course_point_marker_pixmap
from modules.utils.map import get_native_tile_zoom


@dataclass(frozen=True)
class GeoPoint:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class StaticMapMarker:
    point: GeoPoint
    label: str = ""
    color: str = "#D7191C"
    radius: int = 5
    icon_path: str = ""


@dataclass(frozen=True)
class StaticMapScene:
    path: tuple[GeoPoint, ...]
    markers: tuple[StaticMapMarker, ...] = ()
    line_color: str = "#1565C0"
    line_width: int = 4


@dataclass(frozen=True)
class StaticMapRender:
    image: QtGui.QImage
    complete: bool


@dataclass(frozen=True)
class StaticMapViewport:
    left: float
    top: float
    width: float
    height: float
    tile_x_min: int
    tile_x_max: int
    tile_y_min: int
    tile_y_max: int


def world_pixel(point, zoom, tile_size):
    latitude = max(-85.05112878, min(85.05112878, float(point.latitude)))
    longitude = float(point.longitude)
    scale = (2**zoom) * tile_size
    x = (longitude + 180.0) / 360.0 * scale
    latitude_rad = math.radians(latitude)
    y = (1.0 - math.asinh(math.tan(latitude_rad)) / math.pi) / 2.0 * scale
    return x, y


def _unwrap_x(values, world_width):
    unwrapped = [values[0]]
    for value in values[1:]:
        previous = unwrapped[-1]
        candidates = (value - world_width, value, value + world_width)
        unwrapped.append(min(candidates, key=lambda item: abs(item - previous)))
    return unwrapped


def build_static_map_viewport(points, zoom, tile_size, target_size):
    width, height = target_size
    projected = [world_pixel(point, zoom, tile_size) for point in points]
    world_width = (2**zoom) * tile_size
    x_values = _unwrap_x([point[0] for point in projected], world_width)
    y_values = [point[1] for point in projected]

    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    x_span = x_max - x_min
    y_span = y_max - y_min
    source_scale = tile_size / 256
    view_width = max(width * source_scale, x_span * 1.18)
    view_height = max(height * source_scale, y_span * 1.18)

    target_ratio = width / height
    if view_width / view_height < target_ratio:
        view_width = view_height * target_ratio
    else:
        view_height = view_width / target_ratio

    center_x = (x_min + x_max) / 2
    center_y = (y_min + y_max) / 2
    left = center_x - view_width / 2
    top = center_y - view_height / 2

    return StaticMapViewport(
        left=left,
        top=top,
        width=view_width,
        height=view_height,
        tile_x_min=math.floor(left / tile_size),
        tile_x_max=math.floor((left + view_width) / tile_size),
        tile_y_min=max(0, math.floor(top / tile_size)),
        tile_y_max=min(
            2**zoom - 1,
            math.floor((top + view_height) / tile_size),
        ),
    )


class StaticMapRenderer:
    MAX_TILES = 64

    def __init__(self, config, zoom, map_name=None, fit_bounds=False, max_zoom=16):
        self.config = config
        self.zoom = zoom
        self.map_name = map_name
        self.fit_bounds = fit_bounds
        self.max_zoom = max_zoom

    @staticmethod
    def _point_span(points, zoom, tile_size):
        projected = [world_pixel(point, zoom, tile_size) for point in points]
        world_width = (2**zoom) * tile_size
        x_values = _unwrap_x([point[0] for point in projected], world_width)
        y_values = [point[1] for point in projected]
        return max(x_values) - min(x_values), max(y_values) - min(y_values)

    def _fit_zoom(self, points, settings, target_size, initial_zoom):
        if not self.fit_bounds:
            return initial_zoom
        minimum_zoom = settings.get("min_zoomlevel", 0)
        maximum_zoom = min(
            settings.get("max_zoomlevel", self.max_zoom),
            self.max_zoom,
        )
        source_scale = settings["tile_size"] / 256
        available_width = target_size[0] * source_scale
        available_height = target_size[1] * source_scale
        zoom = initial_zoom

        def fits(candidate):
            span_x, span_y = self._point_span(
                points,
                candidate,
                settings["tile_size"],
            )
            return (
                span_x * 1.18 <= available_width and span_y * 1.18 <= available_height
            )

        while zoom > minimum_zoom and not fits(zoom):
            zoom -= 1
        while zoom < maximum_zoom and fits(zoom + 1):
            zoom += 1
        return zoom

    def _map_source(self, points, target_size):
        map_name = self.map_name or self.config.G_MAP
        settings = self.config.G_MAP_CONFIG[map_name]
        maximum_zoom = min(
            settings.get("max_zoomlevel", self.max_zoom),
            self.max_zoom,
        )
        initial_zoom = max(
            settings.get("min_zoomlevel", self.zoom),
            min(maximum_zoom, self.zoom),
        )
        zoom = self._fit_zoom(points, settings, target_size, initial_zoom)
        native_zoom = get_native_tile_zoom(settings, zoom)
        return map_name, settings, native_zoom if native_zoom is not None else zoom

    @staticmethod
    def _tiles(viewport):
        return [
            [x, y]
            for x in range(viewport.tile_x_min, viewport.tile_x_max + 1)
            for y in range(viewport.tile_y_min, viewport.tile_y_max + 1)
        ]

    @staticmethod
    def _target_point(point, viewport, zoom, tile_size, target_size, reference_x):
        x, y = world_pixel(point, zoom, tile_size)
        world_width = (2**zoom) * tile_size
        x = min(
            (x - world_width, x, x + world_width),
            key=lambda value: abs(value - reference_x),
        )
        width, height = target_size
        return QtCore.QPointF(
            (x - viewport.left) / viewport.width * width,
            (y - viewport.top) / viewport.height * height,
        )

    @staticmethod
    def _draw_label(painter, point, label, target_size):
        font = painter.font()
        font.setPixelSize(max(9, min(target_size) // 24))
        font.setBold(True)
        painter.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        text_rect = metrics.boundingRect(label).adjusted(-3, -2, 3, 2)
        x = min(
            max(2, int(point.x() + 7)),
            max(2, target_size[0] - text_rect.width() - 2),
        )
        y = min(
            max(text_rect.height(), int(point.y() - 7)),
            target_size[1] - 2,
        )
        text_rect.moveBottomLeft(QtCore.QPoint(x, y))
        painter.fillRect(text_rect, QtGui.QColor(0, 0, 0, 165))
        painter.setPen(QtGui.QColor("white"))
        painter.drawText(text_rect, QtCore.Qt.AlignmentFlag.AlignCenter, label)

    def _draw_scene(self, painter, scene, viewport, zoom, tile_size, target_size):
        reference_x = viewport.left + viewport.width / 2
        points = [
            self._target_point(
                point,
                viewport,
                zoom,
                tile_size,
                target_size,
                reference_x,
            )
            for point in scene.path
        ]
        if len(points) >= 2:
            path = QtGui.QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            painter.setPen(
                QtGui.QPen(
                    QtGui.QColor("white"),
                    scene.line_width + 3,
                    QtCore.Qt.PenStyle.SolidLine,
                    QtCore.Qt.PenCapStyle.RoundCap,
                    QtCore.Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPath(path)
            painter.setPen(
                QtGui.QPen(
                    QtGui.QColor(scene.line_color),
                    scene.line_width,
                    QtCore.Qt.PenStyle.SolidLine,
                    QtCore.Qt.PenCapStyle.RoundCap,
                    QtCore.Qt.PenJoinStyle.RoundJoin,
                )
            )
            painter.drawPath(path)

        for marker in scene.markers:
            point = self._target_point(
                marker.point,
                viewport,
                zoom,
                tile_size,
                target_size,
                reference_x,
            )
            if marker.icon_path:
                pixmap = build_course_point_marker_pixmap(marker.icon_path)
                painter.drawPixmap(
                    int(round(point.x() - pixmap.width() / 2)),
                    int(round(point.y() - pixmap.height() / 2)),
                    pixmap,
                )
                continue
            radius = marker.radius
            painter.setPen(QtGui.QPen(QtGui.QColor("white"), 2))
            painter.setBrush(QtGui.QColor(marker.color))
            painter.drawEllipse(point, radius, radius)
            if marker.label:
                self._draw_label(painter, point, marker.label, target_size)

    async def render(self, scene, target_size):
        all_points = (*scene.path, *(marker.point for marker in scene.markers))
        map_name, settings, zoom = self._map_source(all_points, target_size)
        tile_size = settings["tile_size"]
        viewport = build_static_map_viewport(
            all_points,
            zoom,
            tile_size,
            target_size,
        )
        width, height = target_size
        image = QtGui.QImage(
            width,
            height,
            QtGui.QImage.Format.Format_ARGB32,
        )
        image.fill(QtGui.QColor("#E5E7EB"))

        tiles = self._tiles(viewport)
        if len(tiles) > self.MAX_TILES:
            tiles = []
        repository = self.config.map.tiles
        await repository.request(self.config.G_MAP_CONFIG, map_name, zoom, tiles)
        keys = [(zoom, x, y) for x, y in tiles]
        raw = await repository.load(map_name, settings, keys)

        complete = bool(tiles)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        try:
            for x, y in tiles:
                key = (zoom, x, y)
                data = raw.get(key)
                tile = (
                    QtGui.QImage.fromData(data) if data is not None else QtGui.QImage()
                )
                if tile.isNull():
                    repository.discard(map_name, settings, key)
                    complete = False
                    continue
                target_rect = QtCore.QRectF(
                    (x * tile_size - viewport.left) / viewport.width * width,
                    (y * tile_size - viewport.top) / viewport.height * height,
                    tile_size / viewport.width * width,
                    tile_size / viewport.height * height,
                )
                painter.drawImage(target_rect, tile)

            painter.fillRect(image.rect(), QtGui.QColor(255, 255, 255, 45))
            self._draw_scene(
                painter,
                scene,
                viewport,
                zoom,
                tile_size,
                target_size,
            )

            attribution = settings["attribution"]
            if attribution:
                font = painter.font()
                font.setPixelSize(max(7, min(target_size) // 28))
                painter.setFont(font)
                painter.setPen(QtGui.QColor(30, 30, 30, 210))
                painter.drawText(
                    image.rect().adjusted(2, 2, -2, -2),
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignBottom,
                    attribution,
                )
        finally:
            painter.end()

        return StaticMapRender(
            image=image,
            complete=complete,
        )
