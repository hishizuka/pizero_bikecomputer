"""Image output adapter using native CGL or surfaceless Mesa EGL contexts."""

import ctypes as C
from contextlib import contextmanager

import numpy as np

from .gl import GL, RenderTarget, gl
from .gl_api import DARWIN, gl_check
from .renderer import MapRenderer2D


class NativeContext:
    _display = None
    _users = 0

    def __init__(self):
        self.handle = None
        if DARWIN:
            self._create_cgl()
        else:
            self._create_egl()

    def _create_cgl(self):
        for name, args, result in (
            ("CGLChoosePixelFormat", [C.c_void_p, C.c_void_p, C.c_void_p], C.c_int),
            ("CGLCreateContext", [C.c_void_p] * 3, C.c_int),
            ("CGLDestroyPixelFormat", [C.c_void_p], C.c_int),
            ("CGLSetCurrentContext", [C.c_void_p], C.c_int),
            ("CGLGetCurrentContext", [], C.c_void_p),
            ("CGLDestroyContext", [C.c_void_p], C.c_int),
        ):
            function = getattr(gl, name)
            function.argtypes, function.restype = args, result
        attrs = (C.c_int * 4)(73, 99, 0x1000, 0)
        pixel_format, count, handle = C.c_void_p(), C.c_int(), C.c_void_p()
        if gl.CGLChoosePixelFormat(attrs, C.byref(pixel_format), C.byref(count)):
            raise RuntimeError("CGL pixel format creation failed")
        error = gl.CGLCreateContext(pixel_format, None, C.byref(handle))
        gl.CGLDestroyPixelFormat(pixel_format)
        if error:
            raise RuntimeError("CGL context creation failed")
        self.handle = handle.value

    def _create_egl(self):
        self.egl = C.CDLL("libEGL.so.1")
        for name, args, result in (
            ("eglGetPlatformDisplay", [C.c_uint, C.c_void_p, C.c_void_p], C.c_void_p),
            ("eglInitialize", [C.c_void_p] * 3, C.c_uint),
            ("eglBindAPI", [C.c_uint], C.c_uint),
            ("eglCreateContext", [C.c_void_p] * 4, C.c_void_p),
            ("eglMakeCurrent", [C.c_void_p] * 4, C.c_uint),
            ("eglDestroyContext", [C.c_void_p] * 2, C.c_uint),
            ("eglTerminate", [C.c_void_p], C.c_uint),
            ("eglGetCurrentContext", [], C.c_void_p),
            ("eglGetCurrentDisplay", [], C.c_void_p),
            ("eglGetCurrentSurface", [C.c_uint], C.c_void_p),
            ("eglQueryAPI", [], C.c_uint),
        ):
            function = getattr(self.egl, name)
            function.argtypes, function.restype = args, result
        if not NativeContext._users:
            display = self.egl.eglGetPlatformDisplay(0x31DD, None, None)
            major, minor = C.c_int(), C.c_int()
            if not self.egl.eglInitialize(display, C.byref(major), C.byref(minor)):
                raise RuntimeError("Mesa surfaceless EGL initialization failed")
            NativeContext._display = display
        previous_api = self.egl.eglQueryAPI()
        self.egl.eglBindAPI(0x30A0)
        attrs = (C.c_int * 3)(0x3098, 2, 0x3038)
        self.handle = self.egl.eglCreateContext(
            NativeContext._display, None, None, attrs
        )
        self.egl.eglBindAPI(previous_api)
        if not self.handle:
            if not NativeContext._users:
                self.egl.eglTerminate(NativeContext._display)
                NativeContext._display = None
            raise RuntimeError("OpenGL ES 2 context creation failed")
        NativeContext._users += 1

    @contextmanager
    def current(self):
        """Restore the GUI's current context and EGL client API after each draw."""
        if DARWIN:
            previous = gl.CGLGetCurrentContext()
            if gl.CGLSetCurrentContext(self.handle):
                raise RuntimeError("CGL makeCurrent failed")
            try:
                yield
            finally:
                gl.CGLSetCurrentContext(previous)
        else:
            api = self.egl.eglQueryAPI()
            previous = (
                self.egl.eglGetCurrentDisplay(),
                self.egl.eglGetCurrentSurface(0x3059),
                self.egl.eglGetCurrentSurface(0x305A),
                self.egl.eglGetCurrentContext(),
            )
            self.egl.eglBindAPI(0x30A0)
            if not self.egl.eglMakeCurrent(
                NativeContext._display, None, None, self.handle
            ):
                self.egl.eglBindAPI(api)
                raise RuntimeError("EGL makeCurrent failed")
            try:
                yield
            finally:
                self.egl.eglMakeCurrent(NativeContext._display, None, None, None)
                self.egl.eglBindAPI(api)
                if previous[0]:
                    self.egl.eglMakeCurrent(*previous)

    def close(self):
        if self.handle is None:
            return
        if DARWIN:
            gl.CGLDestroyContext(self.handle)
        else:
            self.egl.eglDestroyContext(NativeContext._display, self.handle)
            NativeContext._users -= 1
            if not NativeContext._users:
                self.egl.eglTerminate(NativeContext._display)
                NativeContext._display = None
        self.handle = None


def _handle(generate):
    value = C.c_uint()
    generate(1, C.byref(value))
    return value.value


class ImageTarget:
    def __init__(self, width, height):
        self.texture = _handle(gl.glGenTextures)
        gl.glBindTexture(GL.TEXTURE_2D, self.texture)
        for name, value in (
            (GL.TEXTURE_MIN_FILTER, GL.NEAREST),
            (GL.TEXTURE_MAG_FILTER, GL.NEAREST),
            (GL.TEXTURE_WRAP_S, GL.CLAMP_TO_EDGE),
            (GL.TEXTURE_WRAP_T, GL.CLAMP_TO_EDGE),
        ):
            gl.glTexParameteri(GL.TEXTURE_2D, name, value)
        gl.glTexImage2D(
            GL.TEXTURE_2D, 0, GL.RGBA, width, height, 0, GL.RGBA, GL.UNSIGNED_BYTE, None
        )
        self.depth = _handle(gl.glGenRenderbuffers)
        gl.glBindRenderbuffer(0x8D41, self.depth)
        gl.glRenderbufferStorage(0x8D41, 0x81A5, width, height)
        self.fbo = _handle(gl.glGenFramebuffers)
        gl.glBindFramebuffer(GL.FRAMEBUFFER, self.fbo)
        gl.glFramebufferTexture2D(
            GL.FRAMEBUFFER, GL.COLOR_ATTACHMENT0, GL.TEXTURE_2D, self.texture, 0
        )
        gl.glFramebufferRenderbuffer(GL.FRAMEBUFFER, 0x8D00, 0x8D41, self.depth)
        self.target = RenderTarget(self.fbo, width, height)
        self.pixels = np.empty((height, width, 4), dtype=np.uint8)
        if gl.glCheckFramebufferStatus(GL.FRAMEBUFFER) != GL.FRAMEBUFFER_COMPLETE:
            self.close()
            raise RuntimeError("Map image framebuffer is incomplete")
        gl_check("map image framebuffer")

    def read(self):
        gl.glBindFramebuffer(GL.FRAMEBUFFER, self.fbo)
        gl.glPixelStorei(0x0D05, 1)
        gl.glReadPixels(
            0,
            0,
            self.target.width,
            self.target.height,
            GL.RGBA,
            GL.UNSIGNED_BYTE,
            self.pixels.ctypes.data,
        )
        gl_check("map image readback")
        return self.pixels

    def close(self):
        for name, delete in (
            (self.fbo, gl.glDeleteFramebuffers),
            (self.depth, gl.glDeleteRenderbuffers),
            (self.texture, gl.glDeleteTextures),
        ):
            delete(1, C.byref(C.c_uint(name)))


class OffscreenMap:
    def __init__(self, position_images):
        self.context = NativeContext()
        self.renderer = MapRenderer2D(position_images)
        self.target = None
        try:
            with self.context.current():
                self.renderer.initialize()
        except Exception:
            self.context.close()
            raise

    def render(self, frame):
        view = frame.snapshot.view
        with self.context.current():
            if self.target is None or self.target.pixels.shape[:2] != (
                view.height,
                view.width,
            ):
                if self.target is not None:
                    self.target.close()
                self.target = None
                self.target = ImageTarget(view.width, view.height)
            self.renderer.render_frame(frame, self.target.target)
            return self.target.read()

    def close(self):
        if self.context.handle is None:
            return
        with self.context.current():
            self.renderer.release()
            if self.target is not None:
                self.target.close()
                self.target = None
        self.context.close()
