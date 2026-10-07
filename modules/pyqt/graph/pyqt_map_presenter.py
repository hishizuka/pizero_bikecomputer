"""Render a PyQt-controlled map directly into Sharp DRM presenter buffers."""

import ctypes as C
import os
from contextlib import contextmanager

import numpy as np

from modules.qt._qt_qtwidgets import QtCore, Signal, USE_PYQT6
from modules.display.sharp_presenter import SharpPresenter, presenter_paths
from modules.map.gl import GL, RenderTarget, gl
from modules.map.gl_api import compile_program, gl_check
from modules.map.renderer import MapRenderer2D
from modules.qt.qt_map_assets import position_marker_images


class GbmContext:
    """Own the VC4 EGL context independently of Qt's linuxfb platform."""

    def __init__(self):
        self.gbm = C.CDLL("libgbm.so.1")
        self.egl = C.CDLL("libEGL.so.1")
        self.fd = os.open(presenter_paths()["render_node"], os.O_RDWR)
        self.device = self.display = self.context = self.surface = None
        self.gbm.gbm_create_device.argtypes = [C.c_int]
        self.gbm.gbm_create_device.restype = C.c_void_p
        self.gbm.gbm_device_destroy.argtypes = [C.c_void_p]
        for name, args, result in (
            ("eglGetPlatformDisplay", [C.c_uint, C.c_void_p, C.c_void_p], C.c_void_p),
            ("eglInitialize", [C.c_void_p] * 3, C.c_uint),
            ("eglBindAPI", [C.c_uint], C.c_uint),
            (
                "eglChooseConfig",
                [
                    C.c_void_p,
                    C.POINTER(C.c_int),
                    C.POINTER(C.c_void_p),
                    C.c_int,
                    C.POINTER(C.c_int),
                ],
                C.c_uint,
            ),
            ("eglCreateContext", [C.c_void_p] * 4, C.c_void_p),
            ("eglCreatePbufferSurface", [C.c_void_p] * 3, C.c_void_p),
            ("eglMakeCurrent", [C.c_void_p] * 4, C.c_uint),
            ("eglGetCurrentContext", [], C.c_void_p),
            ("eglGetCurrentDisplay", [], C.c_void_p),
            ("eglGetCurrentSurface", [C.c_uint], C.c_void_p),
            ("eglQueryAPI", [], C.c_uint),
            ("eglDestroySurface", [C.c_void_p] * 2, C.c_uint),
            ("eglDestroyContext", [C.c_void_p] * 2, C.c_uint),
            ("eglTerminate", [C.c_void_p], C.c_uint),
        ):
            function = getattr(self.egl, name)
            function.argtypes, function.restype = args, result
        try:
            self.device = self.gbm.gbm_create_device(self.fd)
            if not self.device:
                raise RuntimeError("GBM device creation failed")
            self.display = self.egl.eglGetPlatformDisplay(0x31D7, self.device, None)
            major, minor = C.c_int(), C.c_int()
            if not self.display or not self.egl.eglInitialize(
                self.display, C.byref(major), C.byref(minor)
            ):
                raise RuntimeError("VC4 EGL initialization failed")
            previous_api = self.egl.eglQueryAPI()
            if not self.egl.eglBindAPI(0x30A0):
                raise RuntimeError("OpenGL ES API selection failed")
            try:
                attributes = (C.c_int * 5)(0x3033, 1, 0x3040, 4, 0x3038)
                config, count = C.c_void_p(), C.c_int()
                if (
                    not self.egl.eglChooseConfig(
                        self.display, attributes, C.byref(config), 1, C.byref(count)
                    )
                    or not count.value
                ):
                    raise RuntimeError("VC4 EGL pbuffer config is unavailable")
                context_attributes = (C.c_int * 3)(0x3098, 2, 0x3038)
                self.context = self.egl.eglCreateContext(
                    self.display, config, None, context_attributes
                )
                surface_attributes = (C.c_int * 5)(0x3057, 1, 0x3056, 1, 0x3038)
                self.surface = self.egl.eglCreatePbufferSurface(
                    self.display, config, surface_attributes
                )
                if not self.context or not self.surface:
                    raise RuntimeError("VC4 EGL context creation failed")
            finally:
                if previous_api:
                    self.egl.eglBindAPI(previous_api)
        except Exception:
            self.close()
            raise

    @contextmanager
    def current(self):
        previous = (
            self.egl.eglGetCurrentDisplay(),
            self.egl.eglGetCurrentSurface(0x3059),
            self.egl.eglGetCurrentSurface(0x305A),
            self.egl.eglGetCurrentContext(),
        )
        previous_api = self.egl.eglQueryAPI()
        self.egl.eglBindAPI(0x30A0)
        if not self.egl.eglMakeCurrent(
            self.display, self.surface, self.surface, self.context
        ):
            self.egl.eglBindAPI(previous_api)
            raise RuntimeError("VC4 EGL makeCurrent failed")
        try:
            yield
        finally:
            self.egl.eglMakeCurrent(self.display, None, None, None)
            if previous[0]:
                self.egl.eglMakeCurrent(*previous)
            if previous_api:
                self.egl.eglBindAPI(previous_api)

    def close(self):
        if self.display:
            if self.surface:
                self.egl.eglDestroySurface(self.display, self.surface)
            if self.context:
                self.egl.eglDestroyContext(self.display, self.context)
            self.egl.eglTerminate(self.display)
            self.display = None
        if self.device:
            self.gbm.gbm_device_destroy(self.device)
            self.device = None
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class PyQtMapPresenter(QtCore.QObject):
    buffer_available = Signal()

    def __init__(self, width, height, parent=None):
        """Create and close this object while the map's EGL context is current."""
        super().__init__(parent)
        self.presenter = SharpPresenter(width, height)
        self.notifier = QtCore.QSocketNotifier(
            self.presenter.event_fd, QtCore.QSocketNotifier.Type.Read, self
        )
        self.notifier.activated.connect(self._dispatch)

    def _dispatch(self, *_args):
        self.presenter.dispatch()
        self.buffer_available.emit()

    def acquire(self):
        return self.presenter.acquire()

    def submit(self, buffer_index):
        self.presenter.submit(buffer_index)

    def close(self):
        self.notifier.setEnabled(False)
        self.presenter.close()


class PresentedMap(QtCore.QObject):
    buffer_available = Signal()

    def __init__(self, width, height, parent=None):
        super().__init__(parent)
        self.width, self.height = width, height
        self.context = GbmContext()
        self.output = self.renderer = None
        self.framebuffer = self.depth = self.texture = self.program = None
        try:
            with self.context.current():
                self.output = PyQtMapPresenter(width, height, self)
                self.output.buffer_available.connect(self.buffer_available)
                self.renderer = MapRenderer2D(position_marker_images())
                self.renderer.initialize()
                self._initialize_gl()
        except Exception:
            self.close()
            raise

    def _initialize_gl(self):
        handle = C.c_uint()
        gl.glGenFramebuffers(1, C.byref(handle))
        self.framebuffer = handle.value
        gl.glGenRenderbuffers(1, C.byref(handle))
        self.depth = handle.value
        gl.glBindRenderbuffer(0x8D41, self.depth)
        gl.glRenderbufferStorage(0x8D41, 0x81A5, self.width, self.height)
        gl.glGenTextures(1, C.byref(handle))
        self.texture = handle.value
        gl.glBindTexture(GL.TEXTURE_2D, self.texture)
        for name, value in (
            (GL.TEXTURE_MIN_FILTER, GL.LINEAR),
            (GL.TEXTURE_MAG_FILTER, GL.LINEAR),
            (GL.TEXTURE_WRAP_S, GL.CLAMP_TO_EDGE),
            (GL.TEXTURE_WRAP_T, GL.CLAMP_TO_EDGE),
        ):
            gl.glTexParameteri(GL.TEXTURE_2D, name, value)
        self.program = compile_program(
            """attribute vec2 a_pos;
attribute vec2 a_uv;
varying vec2 v_uv;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); v_uv = a_uv; }""",
            """precision mediump float;
varying vec2 v_uv;
uniform sampler2D u_image;
void main() { gl_FragColor = texture2D(u_image, v_uv); }""",
            ("a_pos", "a_uv"),
            False,
        )
        gl_check("PyQt presenter initialization")

    def _draw_overlay(self, image):
        bits = image.constBits()
        if USE_PYQT6:
            bits.setsize(image.sizeInBytes())
        pixels = np.frombuffer(bits, dtype=np.uint8)
        gl.glDisable(GL.DEPTH_TEST)
        gl.glEnable(GL.BLEND)
        gl.glBlendFunc(GL.SRC_ALPHA, GL.ONE_MINUS_SRC_ALPHA)
        gl.glActiveTexture(GL.TEXTURE0)
        gl.glBindTexture(GL.TEXTURE_2D, self.texture)
        gl.glPixelStorei(GL.UNPACK_ALIGNMENT, 1)
        gl.glTexImage2D(
            GL.TEXTURE_2D,
            0,
            GL.RGBA,
            self.width,
            self.height,
            0,
            GL.RGBA,
            GL.UNSIGNED_BYTE,
            pixels.ctypes.data,
        )
        vertices = (C.c_float * 16)(
            -1,
            -1,
            0,
            0,
            1,
            -1,
            1,
            0,
            -1,
            1,
            0,
            1,
            1,
            1,
            1,
            1,
        )
        indices = (C.c_ushort * 6)(0, 1, 2, 2, 1, 3)
        gl.glUseProgram(self.program)
        gl.glUniform1i(gl.glGetUniformLocation(self.program, b"u_image"), 0)
        gl.glBindBuffer(GL.ARRAY_BUFFER, 0)
        gl.glBindBuffer(GL.ELEMENT_ARRAY_BUFFER, 0)
        for index in (0, 1):
            gl.glEnableVertexAttribArray(index)
            gl.glVertexAttribPointer(
                index,
                2,
                GL.FLOAT,
                0,
                4 * C.sizeof(C.c_float),
                C.cast(C.byref(vertices, index * 2 * C.sizeof(C.c_float)), C.c_void_p),
            )
        gl.glDrawElements(
            GL.TRIANGLES, 6, GL.UNSIGNED_SHORT, C.cast(indices, C.c_void_p)
        )
        for index in (0, 1):
            gl.glDisableVertexAttribArray(index)
        gl_check("PyQt presenter overlay")

    def render(self, frame, overlay):
        with self.context.current():
            acquired = self.output.acquire()
            if acquired is None:
                return False
            buffer_index, renderbuffer = acquired
            gl.glBindFramebuffer(GL.FRAMEBUFFER, self.framebuffer)
            gl.glFramebufferRenderbuffer(
                GL.FRAMEBUFFER, GL.COLOR_ATTACHMENT0, 0x8D41, renderbuffer
            )
            gl.glFramebufferRenderbuffer(GL.FRAMEBUFFER, 0x8D00, 0x8D41, self.depth)
            if gl.glCheckFramebufferStatus(GL.FRAMEBUFFER) != GL.FRAMEBUFFER_COMPLETE:
                raise RuntimeError("PyQt presenter framebuffer is incomplete")
            self.renderer.position_images = position_marker_images(
                frame.snapshot.view.pixel_ratio
            )
            self.renderer.render_frame(
                frame, RenderTarget(self.framebuffer, self.width, self.height)
            )
            self._draw_overlay(overlay)
            self.output.submit(buffer_index)
            return True

    def close(self):
        if self.context is None:
            return
        with self.context.current():
            if self.renderer is not None:
                self.renderer.release()
                self.renderer = None
            for name, delete in (
                (self.framebuffer, gl.glDeleteFramebuffers),
                (self.depth, gl.glDeleteRenderbuffers),
                (self.texture, gl.glDeleteTextures),
            ):
                if name is not None:
                    delete(1, C.byref(C.c_uint(name)))
            if self.program is not None:
                gl.glDeleteProgram(self.program)
            if self.output is not None:
                self.output.close()
                self.output = None
        self.context.close()
        self.context = None
