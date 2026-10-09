"""Experimental Qt Quick RenderControl backend for VC4 to Sharp DRM DMA-BUF."""

import glob
import os
from pathlib import Path
import tempfile

from modules.app_logger import app_logger
from modules.display.sharp_presenter import (  # noqa: F401
    PresenterStats,
    SharpPresenter,
    VC4_CARD,
    presenter_paths,
)
from modules.qml.backend.qt import (
    QtCore,
    QtGui,
    QtQml,
    QtQuick,
    Signal,
    USE_PYSIDE6,
)

RENDERER_SOFTWARE = "software"
RENDERER_DMABUF = "dmabuf"
RENDERER_ENV = "PIZERO_QML_RENDERER"
FALLBACK_ENV = "PIZERO_QML_FALLBACK_ACTIVE"
FB_DEVICE_ENV = "PIZERO_QML_FB_DEVICE"

FB_DEVICE = "/dev/fb0"

BACKEND_DIR = Path(__file__).resolve().parent
EGLFS_CONFIG = BACKEND_DIR / "eglfs-vc4.json"


def _requested_renderer(config):
    renderer = os.environ.get(RENDERER_ENV)
    if renderer is None:
        return (
            RENDERER_DMABUF if config.G_USE_QML_OPENGL_RENDERER else RENDERER_SOFTWARE
        )
    renderer = renderer.strip().lower()
    if renderer not in (RENDERER_SOFTWARE, RENDERER_DMABUF):
        app_logger.warning("Unknown QML renderer %r; using software", renderer)
        return RENDERER_SOFTWARE
    return renderer


def select_renderer(config):
    requested = _requested_renderer(config)
    if requested == RENDERER_SOFTWARE or os.environ.get(FALLBACK_ENV) == "1":
        return RENDERER_SOFTWARE

    reasons = []
    if not USE_PYSIDE6:
        reasons.append("PySide6 is required for the DMA-BUF renderer")
    if not config.G_IS_RASPI:
        reasons.append("not running on Raspberry Pi")
    if not config.G_DISPLAY_PARAM["USE_DRM"]:
        reasons.append("sharp-drm display is not active")
    for label, path in presenter_paths().items():
        if not path.exists():
            reasons.append(f"{label} not found: {path}")
    if not Path(VC4_CARD).exists():
        reasons.append(f"VC4 card not found: {VC4_CARD}")
    if not EGLFS_CONFIG.is_file():
        reasons.append(f"EGLFS config not found: {EGLFS_CONFIG}")

    connector_statuses = []
    for status_path in glob.glob("/sys/class/drm/*HDMI*/status"):
        try:
            connector_statuses.append(Path(status_path).read_text().strip())
        except OSError:
            continue
    if connector_statuses and "connected" not in connector_statuses:
        reasons.append("VC4 has no connected or forced HDMI screen")

    if reasons:
        message = "; ".join(reasons)
        app_logger.warning("QML DMA-BUF unavailable: %s", message)
        return RENDERER_SOFTWARE
    return RENDERER_DMABUF


def configure_renderer_environment(renderer, force_software=False, map_opengl=False):
    if renderer == RENDERER_DMABUF:
        os.environ["QT_QPA_PLATFORM"] = "eglfs"
        os.environ["QT_QPA_EGLFS_INTEGRATION"] = "eglfs_kms"
        os.environ["QT_QPA_EGLFS_KMS_CONFIG"] = str(EGLFS_CONFIG)
        os.environ["QT_QPA_EGLFS_HIDECURSOR"] = "1"
        os.environ["QSG_RHI_BACKEND"] = "opengl"
        os.environ.pop("QT_QUICK_BACKEND", None)
        QtQuick.QQuickWindow.setGraphicsApi(
            QtQuick.QSGRendererInterface.GraphicsApi.OpenGL
        )
        return

    if map_opengl and not force_software:
        os.environ["QSG_RHI_BACKEND"] = "opengl"
        os.environ.pop("QT_QUICK_BACKEND", None)
        # The shared shaders target desktop GL 2.1 or GLES2.
        fmt = QtGui.QSurfaceFormat()
        fmt.setVersion(2, 1)
        QtGui.QSurfaceFormat.setDefaultFormat(fmt)
        QtQuick.QQuickWindow.setGraphicsApi(
            QtQuick.QSGRendererInterface.GraphicsApi.OpenGL
        )
        return

    if force_software:
        fb_device = os.environ.get(FB_DEVICE_ENV, FB_DEVICE)
        os.environ["QT_QPA_PLATFORM"] = f"linuxfb:fb={fb_device}"
    os.environ["QT_QUICK_BACKEND"] = "software"
    os.environ.pop("QSG_RHI_BACKEND", None)
    for name in (
        "QT_QPA_EGLFS_INTEGRATION",
        "QT_QPA_EGLFS_KMS_CONFIG",
        "QT_QPA_EGLFS_HIDECURSOR",
    ):
        os.environ.pop(name, None)


def log_renderer_selection(config, renderer):
    requested = _requested_renderer(config)
    drm = "yes" if config.G_DISPLAY_PARAM["USE_DRM"] else "no"
    qpa = os.environ.get("QT_QPA_PLATFORM", "default")
    graphics = os.environ.get(
        "QSG_RHI_BACKEND",
        os.environ.get("QT_QUICK_BACKEND", "default"),
    )
    fallback = "yes" if os.environ.get(FALLBACK_ENV) == "1" else "no"
    app_logger.info(
        "QML display path selected: requested=%s drm=%s selected=%s "
        "qpa=%s graphics=%s fallback=%s",
        requested,
        drm,
        renderer,
        qpa,
        graphics,
        fallback,
    )


def software_fallback_environment():
    environment = os.environ.copy()
    environment[RENDERER_ENV] = RENDERER_SOFTWARE
    environment[FALLBACK_ENV] = "1"
    fb_device = environment.get(FB_DEVICE_ENV, FB_DEVICE)
    environment["QT_QPA_PLATFORM"] = f"linuxfb:fb={fb_device}"
    environment["QT_QUICK_BACKEND"] = "software"
    environment.pop("QSG_RHI_BACKEND", None)
    for name in (
        "QT_QPA_EGLFS_INTEGRATION",
        "QT_QPA_EGLFS_KMS_CONFIG",
        "QT_QPA_EGLFS_HIDECURSOR",
    ):
        environment.pop(name, None)
    return environment


class DmabufRenderer(QtCore.QObject):
    fatalError = Signal(str)

    def __init__(
        self,
        qml_path,
        initial_properties,
        width,
        height,
        parent=None,
    ):
        super().__init__(parent)
        self.width = width
        self.height = height
        self.context = None
        self.surface = None
        self.render_control = None
        self.quick_window = None
        self.engine = None
        self.component = None
        self.root = None
        self.output = None
        self.notifier = None
        self.current_buffer_index = None
        self.initialized = False
        self.closed = False
        self.dirty = False
        self.rendering = False
        self.frame_count = 0
        self.coalesced_requests = 0
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._render_frame)
        try:
            self._initialize(qml_path, initial_properties)
        except Exception:
            self.close()
            raise

    def _initialize(self, qml_path, initial_properties):
        surface_format = QtGui.QSurfaceFormat()
        surface_format.setRenderableType(QtGui.QSurfaceFormat.RenderableType.OpenGLES)
        surface_format.setVersion(2, 0)
        surface_format.setDepthBufferSize(16)
        surface_format.setStencilBufferSize(8)
        self.context = QtGui.QOpenGLContext()
        self.context.setFormat(surface_format)
        if not self.context.create():
            raise RuntimeError("QOpenGLContext.create() failed")

        self.surface = QtGui.QOffscreenSurface()
        self.surface.setFormat(self.context.format())
        self.surface.create()
        if not self.surface.isValid() or not self.context.makeCurrent(self.surface):
            raise RuntimeError("Creating the Qt offscreen surface failed")

        self.render_control = QtQuick.QQuickRenderControl()
        self.quick_window = QtQuick.QQuickWindow(self.render_control)
        self.engine = QtQml.QQmlEngine()
        if not self.engine.incubationController():
            self.engine.setIncubationController(
                self.quick_window.incubationController()
            )
        self.component = QtQml.QQmlComponent(
            self.engine,
            QtCore.QUrl.fromLocalFile(str(Path(qml_path).resolve())),
        )
        if self.component.isError():
            raise RuntimeError(self._qml_errors())
        self.root = self.component.createWithInitialProperties(initial_properties)
        if self.component.isError():
            raise RuntimeError(self._qml_errors())
        if not isinstance(self.root, QtQuick.QQuickItem):
            raise RuntimeError("DMA-BUF QML root is not a QQuickItem")
        self.root.setParentItem(self.quick_window.contentItem())
        self.root.setSize(QtCore.QSize(self.width, self.height))
        self.quick_window.setGeometry(0, 0, self.width, self.height)

        if not self.context.makeCurrent(self.surface):
            raise RuntimeError("QOpenGLContext.makeCurrent() failed")
        self.output = SharpPresenter(self.width, self.height)
        if not self._acquire_render_target():
            raise RuntimeError("Initial presenter buffer is unavailable")
        self.quick_window.setGraphicsDevice(
            QtQuick.QQuickGraphicsDevice.fromOpenGLContext(self.context)
        )
        if not self.render_control.initialize():
            raise RuntimeError("QQuickRenderControl.initialize() failed")
        self.initialized = True
        self.render_control.renderRequested.connect(self.request_render)
        self.render_control.sceneChanged.connect(self.request_render)
        self.notifier = QtCore.QSocketNotifier(
            self.output.event_fd,
            QtCore.QSocketNotifier.Type.Read,
            self,
        )
        self.notifier.activated.connect(self._presenter_event)
        app_logger.info(
            "QML DMA-BUF presenter initialized: %dx%d stride=%d modifier=0x%016x buffers=2",
            self.width,
            self.height,
            self.output.stride(self.current_buffer_index),
            self.output.modifier(self.current_buffer_index),
        )
        self.request_render()

    def _qml_errors(self):
        return "\n".join(error.toString() for error in self.component.errors())

    def request_render(self, *_args):
        if self.closed:
            return
        if self.dirty or self.rendering or self.timer.isActive():
            self.coalesced_requests += 1
        self.dirty = True
        if self.rendering or self.timer.isActive():
            return
        if self.current_buffer_index is None:
            try:
                if not self._acquire_render_target():
                    return
            except RuntimeError as exc:
                self.fatalError.emit(str(exc))
                return
        self.timer.start(0)

    def _acquire_render_target(self):
        acquired = self.output.acquire()
        if acquired is None:
            return False
        self.current_buffer_index, renderbuffer = acquired
        target = QtQuick.QQuickRenderTarget.fromOpenGLRenderBuffer(
            renderbuffer,
            QtCore.QSize(self.width, self.height),
        )
        target.setMirrorVertically(True)
        self.quick_window.setRenderTarget(target)
        return True

    def _presenter_event(self, *_args):
        if self.closed:
            return
        try:
            self.output.dispatch()
        except RuntimeError as exc:
            self.fatalError.emit(str(exc))
            return
        if self.dirty:
            self.request_render()

    def _render_frame(self):
        if self.closed or not self.dirty:
            return
        if self.current_buffer_index is None:
            try:
                if not self._acquire_render_target():
                    return
            except RuntimeError as exc:
                self.fatalError.emit(str(exc))
                return
        self.rendering = True
        self.dirty = False
        try:
            if not self.context.makeCurrent(self.surface):
                raise RuntimeError("QOpenGLContext.makeCurrent() failed")
            self.render_control.beginFrame()
            self.render_control.polishItems()
            self.render_control.sync()
            self.render_control.render()
            self.render_control.endFrame()
            self.output.submit(self.current_buffer_index)
            self.current_buffer_index = None
            self.frame_count += 1
        except Exception as exc:
            app_logger.exception("QML DMA-BUF render failed")
            self.fatalError.emit(str(exc))
            return
        finally:
            self.rendering = False
        if self.dirty:
            self.request_render()

    def grab(self):
        if self.closed or self.output is None:
            return None
        if self.dirty and not self.rendering:
            self._render_frame()
        fd, path_text = tempfile.mkstemp(prefix="pizero-qml-", suffix=".ppm")
        os.close(fd)
        path = Path(path_text)
        try:
            if not self.context.makeCurrent(self.surface):
                raise RuntimeError("QOpenGLContext.makeCurrent() failed")
            self.output.dump_active_ppm(path)
            image = QtGui.QImage(str(path))
            return image.copy() if not image.isNull() else None
        finally:
            path.unlink(missing_ok=True)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.timer.stop()
        if self.notifier is not None:
            self.notifier.setEnabled(False)
        if self.context is not None and self.surface is not None:
            self.context.makeCurrent(self.surface)
        if self.quick_window is not None:
            self.quick_window.setRenderTarget(QtQuick.QQuickRenderTarget())
        if self.initialized:
            self.render_control.invalidate()
            self.initialized = False
        if self.quick_window is not None:
            # Destroy Qt's graphics objects while their GL context is current,
            # before releasing the presenter buffers and the host context.
            self.quick_window.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(
                self.quick_window, QtCore.QEvent.Type.DeferredDelete
            )
            self.quick_window = None
            self.root = None
        if self.render_control is not None:
            self.render_control.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(
                self.render_control, QtCore.QEvent.Type.DeferredDelete
            )
            self.render_control = None
        stats = None
        if self.output is not None:
            try:
                self.output.restore()
                stats = self.output.get_stats()
            except RuntimeError:
                app_logger.exception("Failed to stop the Sharp presenter")
            self.output.close()
            self.output = None
        if self.context is not None:
            self.context.doneCurrent()
        if stats is None:
            app_logger.info(
                "QML DMA-BUF presenter closed: frames=%d coalesced_requests=%d",
                self.frame_count,
                self.coalesced_requests,
            )
        else:
            app_logger.info(
                "QML DMA-BUF presenter closed: frames=%d presented=%d "
                "unchanged=%d damage_rows=%d replaced_pending=%d busy=%d "
                "coalesced_requests=%d errors=%d",
                stats.submitted_frames,
                stats.presented_frames,
                stats.unchanged_frames,
                stats.damage_rows,
                stats.replaced_pending_frames,
                stats.busy_acquires,
                self.coalesced_requests,
                stats.commit_errors,
            )
