"""Qt binding-neutral controller; GPU work belongs to each page adapter."""

import asyncio

from modules._qt_ver import QtCore, QtGui, USE_PYSIDE6
from modules.app_logger import app_logger
from modules.map.session import MapSession
from modules.map.policy import clamp_zoom
from modules.map.style import MAP_CONTROLS_STYLE, MAP_LAYER_ORDER
from modules.qt_map_assets import position_marker_images
from modules.qt_map_hud import HudImage, map_controls_rects
from modules.utils.map import get_zoom_delta_from_tile_size

Signal = QtCore.Signal if USE_PYSIDE6 else QtCore.pyqtSignal
Slot = QtCore.Slot if USE_PYSIDE6 else QtCore.pyqtSlot
Property = QtCore.Property if USE_PYSIDE6 else QtCore.pyqtProperty


class MapController(QtCore.QObject):
    frameReady = Signal()
    signal_move_x_plus = Signal()
    signal_move_x_minus = Signal()
    signal_move_y_plus = Signal()
    signal_move_y_minus = Signal()
    signal_zoom_plus = Signal()
    signal_zoom_minus = Signal()
    signal_change_move = Signal()
    signal_search_route = Signal()
    followingChanged = Signal()
    errorChanged = Signal()

    def __init__(self, config, parent=None, ready=True):
        super().__init__(parent)
        self.session = MapSession(config)
        self.position_images = position_marker_images()
        self.frame = None
        self._frame_key = None
        self.hud = HudImage()
        self.hud_image = QtGui.QImage()
        self._overlay_task = None
        self._route_task = None
        self.active = False
        self._ready = ready
        self._move_factor = 1
        self.signal_zoom_plus.connect(lambda: self.zoom(1))
        self.signal_zoom_minus.connect(lambda: self.zoom(-1))
        self.signal_move_x_plus.connect(lambda: self._move(-1, 0))
        self.signal_move_x_minus.connect(lambda: self._move(1, 0))
        self.signal_move_y_plus.connect(lambda: self._move(0, 1))
        self.signal_move_y_minus.connect(lambda: self._move(0, -1))
        self.signal_change_move.connect(self._change_move)
        self.signal_search_route.connect(self.search_route)
        self.error = ""
        self._task = None
        self._requested = False
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(config.G_DRAW_INTERVAL)
        self.timer.timeout.connect(self.request_frame)
        self._draw_timer = QtCore.QTimer(self)
        self._draw_timer.setSingleShot(True)
        self._draw_timer.setInterval(33)
        self._draw_timer.timeout.connect(self._draw)

    @Property(bool, notify=followingChanged)
    def following(self):
        return self.session.state.follow

    @Property("QVariantMap", constant=True)
    def controlsStyle(self):
        return MAP_CONTROLS_STYLE

    @Property("QVariantMap", constant=True)
    def layerOrder(self):
        return MAP_LAYER_ORDER

    @Property(str, notify=errorChanged)
    def errorText(self):
        return self.error

    @Slot(bool)
    def setActive(self, active):
        self.active = active
        if active and self._ready:
            self._frame_key = None
            self.timer.start()
            self.request_frame()
        else:
            self.timer.stop()
            self._draw_timer.stop()
            self._requested = False
            if self._task is not None:
                self._task.cancel()
            self.frame = None

    def set_ready(self):
        self._ready = True
        self.setActive(self.active)

    @Slot(int, int, float)
    def resize(self, width, height, pixel_ratio=1.0):
        if width > 0 and height > 0:
            self.session.state.resize(width, height, pixel_ratio)
            self.position_images = position_marker_images(pixel_ratio)
            self.request_frame()

    @Slot(float, float)
    def pan(self, dx, dy):
        following = self.following
        self.session.state.pan(dx, dy)
        if following:
            self.followingChanged.emit()
        self.request_frame()

    @Slot(int)
    def zoom(self, delta):
        state = self.session.state
        zoom = clamp_zoom(state.view.zoom + delta)
        if zoom != state.view.zoom:
            state.set_zoom(zoom)
            self.request_frame()

    @Slot(int)
    def wheelZoom(self, delta):
        if not self.following and delta:
            self.zoom(1 if delta > 0 else -1)

    @property
    def lock_status(self):
        return self.following

    def lock_on(self):
        self.setFollow(True)

    def lock_off(self):
        self.setFollow(False)

    @Slot(bool)
    def setFollow(self, following):
        if following != self.following:
            self.session._applied_view = None
            self.session.state.set_follow(following)
            self.followingChanged.emit()
            self.request_frame()

    @Slot()
    def toggleFollow(self):
        self.setFollow(not self.following)

    def _move(self, dx, dy):
        view = self.session.state.view
        self.pan(
            dx * view.width / (2 * self._move_factor),
            dy * view.height / (2 * self._move_factor),
        )

    def _change_move(self):
        self._move_factor = 32 if self._move_factor == 1 else 1
        self.session.move_adjust_mode = self._move_factor == 32
        self.request_frame()

    def reset_map(self):
        self.session.source = None
        view = self.session.cached_frame().snapshot.view
        self.session._auto_zoom = (
            view.zoom + 2 - get_zoom_delta_from_tile_size(view.tile_size)
        )
        self.request_frame()

    def reset_course(self):
        self.session._course_arrays = None
        self.session.course_focus.reset()
        self.session.state.set_course([], [], [])
        self.request_frame()

    init_course = reset_course

    remove_overlay = reset_map

    @Property(bool, notify=frameReady)
    def hasOverlays(self):
        return self.session.config.map.overlays.has_overlays

    @Property(bool, notify=frameReady)
    def hasTimes(self):
        return self.session.config.map.overlays.has_times

    @Property(bool, constant=True)
    def hasRouteSearch(self):
        return self.session.config.G_GOOGLE_ROUTES_API["HAVE_API_TOKEN"]

    @Property(bool, notify=frameReady)
    def canSearchRoute(self):
        return self.session.state.position is not None and (
            self.session.config.map.can_search_route(self.following)
        )

    @Slot()
    def search_route(self):
        if self.canSearchRoute and (
            self._route_task is None or self._route_task.done()
        ):
            position, view = self.session.state.position, self.session.state.view
            self._route_task = asyncio.create_task(
                self._search_route(
                    (position.longitude, position.latitude),
                    (view.longitude, view.latitude),
                )
            )

    async def _search_route(self, start, destination):
        try:
            await self.session.config.map.search_route(start, destination)
        except Exception as exc:
            app_logger.exception("Map route search failed")
            self.set_error(str(exc))

    @Property(bool, constant=True)
    def pointerControls(self):
        return self.session.config.uses_pointer_navigation

    @Property(bool, notify=frameReady)
    def hasPreviousTime(self):
        return self.session.config.map.overlays.can_shift_time(False)

    @Property(bool, notify=frameReady)
    def hasNextTime(self):
        return self.session.config.map.overlays.can_shift_time(True)

    @Slot()
    def change_map_overlays(self):
        self.session.config.map.change_map_overlays()

    @Slot(bool)
    def update_overlay_time(self, forward=True):
        if self._overlay_task is None or self._overlay_task.done():
            self._overlay_task = asyncio.create_task(
                self.session.config.map.update_overlay_time(forward)
            )

    @Slot()
    def request_frame(self):
        if not self.active or not self._ready:
            return
        if not self._draw_timer.isActive():
            self._draw_timer.start()
        self._requested = True
        if self._task is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # Initial QML construction precedes starting the qasync loop.
                QtCore.QTimer.singleShot(0, self.request_frame)
                return
            self._task = loop.create_task(self._prepare())
            self._task.add_done_callback(self._finished)

    refresh_map = request_frame
    enable_overlay_button = request_frame
    reset_track = request_frame

    def _finished(self, task):
        self._task = None
        if self.active and self._requested:
            self.request_frame()

    async def _prepare(self):
        try:
            while self.active and self._requested:
                self._requested = False
                await self.session.prepare()
                # Loaded tiles enter the CPU cache; drawing always uses the latest view.
                if self.active:
                    self.set_error("")
                    if not self._draw_timer.isActive():
                        self._draw_timer.start()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            app_logger.exception("GPU map preparation failed")
            self.set_error(str(exc))

    def _draw(self):
        if not self.active or not self._ready:
            return
        try:
            self.frame = self.session.cached_frame()
            view = self.frame.snapshot.view
            controls = (
                map_controls_rects(
                    view.width / view.pixel_ratio, self.hasTimes, self.hasRouteSearch
                )
                if self.pointerControls
                else ()
            )
            self.hud_image = self.hud.render(
                self.frame, include_instruction=False, controls=controls, split=True
            )
            frame = self.frame
            overlay = frame.overlay
            key = (
                frame.snapshot,
                frame.traffic_offset,
                frame.tile_namespace,
                tuple((key, id(pixels)) for key, pixels in frame.tiles.items()),
                overlay.namespace if overlay else None,
                (
                    tuple((key, id(pixels)) for key, pixels in overlay.tiles.items())
                    if overlay
                    else ()
                ),
                self.hud_image.cacheKey(),
                frame.hud.winds,
                frame.hud.instruction_name,
                frame.hud.instruction_distance,
                self.following,
                self.canSearchRoute,
                self.hasOverlays,
                self.hasTimes,
                self.hasPreviousTime,
                self.hasNextTime,
            )
            if key == self._frame_key:
                return
            self._frame_key = key
            self.frameReady.emit()
        except Exception as exc:
            app_logger.exception("GPU map snapshot failed")
            self.set_error(str(exc))

    @Slot(str)
    def set_error(self, message):
        if message != self.error:
            self.error = message
            self.errorChanged.emit()

    async def close(self):
        self.setActive(False)
        if self._route_task is not None:
            self._route_task.cancel()
            await asyncio.gather(self._route_task, return_exceptions=True)
        if self._overlay_task is not None:
            self._overlay_task.cancel()
            await asyncio.gather(self._overlay_task, return_exceptions=True)
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)


class MapImage:
    """Readback adapter for QWidget and software Qt Quick composition."""

    def __init__(self):
        self.output = None

    def render(self, frame):
        from modules.map.offscreen import OffscreenMap

        images = position_marker_images(frame.snapshot.view.pixel_ratio)
        if self.output is None:
            self.output = OffscreenMap(images)
        self.output.renderer.position_images = images
        pixels = self.output.render(frame)
        height, width = pixels.shape[:2]
        image = QtGui.QImage(
            pixels.data,
            width,
            height,
            width * 4,
            QtGui.QImage.Format.Format_RGBA8888,
        ).copy()
        image.setDevicePixelRatio(frame.snapshot.view.pixel_ratio)
        return image

    def close(self):
        if self.output is not None:
            self.output.close()
            self.output = None
