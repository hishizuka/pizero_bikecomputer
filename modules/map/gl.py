"""GPU resources and drawing primitives borrowed from the GPU 2D prototype.

All handles belong to one renderer and the caller's current context. This
module neither creates a context nor owns the caller's framebuffer.
"""

import ctypes as C
import math
from dataclasses import dataclass

import numpy as np

from .gl_api import clear_depth, compile_program, gl


class GL:
    TRIANGLES = 0x0004
    FLOAT, UNSIGNED_BYTE, UNSIGNED_SHORT = 0x1406, 0x1401, 0x1403
    UNSIGNED_SHORT_5_6_5 = 0x8363
    RGB, RGBA, LUMINANCE = 0x1907, 0x1908, 0x1909
    ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 0x8892, 0x8893
    STATIC_DRAW, DYNAMIC_DRAW = 0x88E4, 0x88E8
    TEXTURE_2D, TEXTURE0 = 0x0DE1, 0x84C0
    TEXTURE_MIN_FILTER, TEXTURE_MAG_FILTER = 0x2801, 0x2800
    TEXTURE_WRAP_S, TEXTURE_WRAP_T = 0x2802, 0x2803
    NEAREST, LINEAR, CLAMP_TO_EDGE = 0x2600, 0x2601, 0x812F
    FRAMEBUFFER, COLOR_ATTACHMENT0 = 0x8D40, 0x8CE0
    FRAMEBUFFER_COMPLETE = 0x8CD5
    COLOR_BUFFER_BIT, DEPTH_BUFFER_BIT = 0x4000, 0x0100
    BLEND, DEPTH_TEST, SCISSOR_TEST = 0x0BE2, 0x0B71, 0x0C11
    ZERO, ONE = 0, 1
    SRC_ALPHA, ONE_MINUS_SRC_ALPHA = 0x0302, 0x0303
    FUNC_ADD, MIN_EXT = 0x8006, 0x8007
    LESS = 0x0201
    UNPACK_ALIGNMENT = 0x0CF5


# Every vertex shader maps positions with the same affine transform:
#   px = p.x * u_ax + p.y * u_ay + u_off     (screen pixels, y down)
# and u_flip = -1 keeps memory row 0 at the top (as QImage and the panel scan out).
COMMON_VS = """
uniform vec2 u_ax;
uniform vec2 u_ay;
uniform vec2 u_off;
uniform vec2 u_viewport;
uniform float u_flip;
vec2 to_px(vec2 p) { return p.x * u_ax + p.y * u_ay + u_off; }
vec4 px_to_clip(vec2 s, float z) {
    return vec4(s.x / u_viewport.x * 2.0 - 1.0,
                u_flip * (1.0 - s.y / u_viewport.y * 2.0), z, 1.0);
}
"""


class Program:
    def __init__(
        self, resources, vertex_source: str, fragment_source: str, attributes: list[str]
    ):
        self.id = compile_program(
            vertex_source, fragment_source, attributes, resources.desktop
        )
        resources.program_ids.append(self.id)
        self.attributes = attributes
        self._locations: dict[str, int] = {}
        self._values: dict[str, tuple] = {}

    def use(self) -> "Program":
        gl.glUseProgram(self.id)
        return self

    def loc(self, name: str) -> int:
        location = self._locations.get(name)
        if location is None:
            location = gl.glGetUniformLocation(self.id, name.encode())
            self._locations[name] = location
        return location

    def set(self, name: str, *values) -> None:
        # skip unchanged values: every GL call costs ~20 us through ctypes on a Pi Zero
        if self._values.get(name) == values:
            return
        self._values[name] = values
        location = self.loc(name)
        if (
            len(values) == 1
            and isinstance(values[0], int)
            and not isinstance(values[0], bool)
        ):
            gl.glUniform1i(location, values[0])
            return
        (gl.glUniform1f, gl.glUniform2f, gl.glUniform3f, gl.glUniform4f)[
            len(values) - 1
        ](location, *[float(v) for v in values])

    def set_transform(
        self, transform: "Transform", viewport: tuple[int, int], flip: float
    ) -> None:
        self.set("u_ax", *transform.ax)
        self.set("u_ay", *transform.ay)
        self.set("u_off", *transform.off)
        self.set("u_viewport", *viewport)
        self.set("u_flip", float(flip))


def _gen(fn) -> int:
    handle = C.c_uint()
    fn(1, C.byref(handle))
    return handle.value


class VertexBuffer:
    """Structured vertex records; field 'x' feeds attribute 'a_x'."""

    def __init__(self, resources, dtype: np.dtype, dynamic: bool = False):
        self.id = resources.buffer()
        self.dtype = np.dtype(dtype)
        self.usage = GL.DYNAMIC_DRAW if dynamic else GL.STATIC_DRAW
        self.capacity = 0
        self.count = 0
        self._layouts = {}

    def upload(self, records: np.ndarray) -> None:
        records = np.ascontiguousarray(records, dtype=self.dtype)
        gl.glBindBuffer(GL.ARRAY_BUFFER, self.id)
        if records.nbytes > self.capacity:
            gl.glBufferData(
                GL.ARRAY_BUFFER, records.nbytes, records.ctypes.data, self.usage
            )
            self.capacity = records.nbytes
        elif records.nbytes:
            gl.glBufferSubData(GL.ARRAY_BUFFER, 0, records.nbytes, records.ctypes.data)
        self.count = len(records)

    def layout(self, program: Program):
        """Cache attribute index, size, type, normalization and byte offset."""
        cache = self._layouts
        layout = cache.get(program.id)
        if layout is None:
            layout = []
            for index, attribute in enumerate(program.attributes):
                field, offset = self.dtype.fields[attribute[2:]][:2]
                size = int(np.prod(field.shape)) if field.shape else 1
                kind = GL.UNSIGNED_BYTE if field.base == np.uint8 else GL.FLOAT
                layout.append(
                    (index, size, kind, 1 if kind == GL.UNSIGNED_BYTE else 0, offset)
                )
            cache[program.id] = layout
        return layout

    def bind(self, program: Program, first_vertex: int = 0) -> None:
        gl.glBindBuffer(GL.ARRAY_BUFFER, self.id)
        stride = self.dtype.itemsize
        base = first_vertex * stride
        for index, size, kind, normalized, offset in self.layout(program):
            gl.glEnableVertexAttribArray(index)
            gl.glVertexAttribPointer(
                index, size, kind, normalized, stride, C.c_void_p(base + offset)
            )

    @staticmethod
    def unbind(program: Program) -> None:
        for index in range(len(program.attributes)):
            gl.glDisableVertexAttribArray(index)


class QuadIndex:
    """Shared 16-bit index buffer for quads (4 vertices, 2 triangles each)."""

    MAX_QUADS = 16000  # 64,000 vertices per draw (< 65,536)

    def __init__(self, resources):
        base = (np.arange(self.MAX_QUADS, dtype=np.uint16) * 4)[:, None]
        indices = (base + np.array([0, 1, 2, 0, 2, 3], dtype=np.uint16)).ravel()
        self.id = resources.buffer()
        gl.glBindBuffer(GL.ELEMENT_ARRAY_BUFFER, self.id)
        gl.glBufferData(
            GL.ELEMENT_ARRAY_BUFFER, indices.nbytes, indices.ctypes.data, GL.STATIC_DRAW
        )

    def draw(
        self,
        vbo: VertexBuffer,
        program: Program,
        first_quad: int = 0,
        quads: int | None = None,
    ) -> int:
        """Draw the requested quads in chunks; return the draw-call count."""
        total = vbo.count // 4 if quads is None else quads
        calls = 0
        gl.glBindBuffer(GL.ELEMENT_ARRAY_BUFFER, self.id)
        start = first_quad
        while total > 0:
            chunk = min(total, self.MAX_QUADS)
            # rebinding the attribute base keeps vertex numbers of one draw below 65,536
            vbo.bind(program, start * 4)
            gl.glDrawElements(GL.TRIANGLES, chunk * 6, GL.UNSIGNED_SHORT, None)
            calls += 1
            start += chunk
            total -= chunk
        return calls


class Texture:
    def __init__(
        self,
        resources,
        width: int,
        height: int,
        fmt: int = GL.RGBA,
        kind: int = GL.UNSIGNED_BYTE,
        filter_: int = GL.NEAREST,
    ):
        self.width, self.height, self.fmt, self.kind = width, height, fmt, kind
        self.id = resources.texture()
        gl.glBindTexture(GL.TEXTURE_2D, self.id)
        for name, value in (
            (GL.TEXTURE_MIN_FILTER, filter_),
            (GL.TEXTURE_MAG_FILTER, filter_),
            (GL.TEXTURE_WRAP_S, GL.CLAMP_TO_EDGE),
            (GL.TEXTURE_WRAP_T, GL.CLAMP_TO_EDGE),
        ):
            gl.glTexParameteri(GL.TEXTURE_2D, name, value)
        gl.glTexImage2D(GL.TEXTURE_2D, 0, fmt, width, height, 0, fmt, kind, None)

    def upload(self, x: int, y: int, pixels: np.ndarray) -> None:
        pixels = np.ascontiguousarray(pixels)
        gl.glBindTexture(GL.TEXTURE_2D, self.id)
        gl.glPixelStorei(GL.UNPACK_ALIGNMENT, 1)
        gl.glTexSubImage2D(
            GL.TEXTURE_2D,
            0,
            x,
            y,
            pixels.shape[1],
            pixels.shape[0],
            self.fmt,
            self.kind,
            pixels.ctypes.data,
        )

    def bind(self, unit: int = 0) -> None:
        gl.glActiveTexture(GL.TEXTURE0 + unit)
        gl.glBindTexture(GL.TEXTURE_2D, self.id)


@dataclass
class Transform:
    """Affine map from data coordinates to screen pixels (x right, y down)."""

    ax: tuple[float, float]
    ay: tuple[float, float]
    off: tuple[float, float]

    @staticmethod
    def screen() -> "Transform":
        return Transform((1.0, 0.0), (0.0, 1.0), (0.0, 0.0))

    @staticmethod
    def ranges(
        x_range, y_range, rect, origin=(0.0, 0.0), rotation_deg=0.0
    ) -> "Transform":
        """Map x_range/y_range (y up) onto rect=(x, y, w, h) pixels.

        Data are stored relative to origin (float32 precision), so ranges are
        shifted by origin too. rotation_deg turns the view clockwise about the
        rect center (heading-up maps).
        """
        x0, x1 = x_range[0] - origin[0], x_range[1] - origin[0]
        y0, y1 = y_range[0] - origin[1], y_range[1] - origin[1]
        sx = rect[2] / (x1 - x0)
        sy = -rect[3] / (y1 - y0)
        cx, cy = rect[0] + rect[2] / 2, rect[1] + rect[3] / 2
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        c, s = math.cos(math.radians(rotation_deg)), math.sin(
            math.radians(rotation_deg)
        )
        ax = (c * sx, s * sx)
        ay = (-s * sy, c * sy)
        off = (cx - ax[0] * mx - ay[0] * my, cy - ax[1] * mx - ay[1] * my)
        return Transform(ax, ay, off)

    def apply(self, x, y):
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        return (
            x * self.ax[0] + y * self.ay[0] + self.off[0],
            x * self.ax[1] + y * self.ay[1] + self.off[1],
        )


class GpuResources:
    """Context-local ownership, including shader sharing within one renderer."""

    def __init__(self):
        version = gl.glGetString(0x1F02)
        if version is None:
            raise RuntimeError("A current OpenGL context is required")
        self.desktop = not version.startswith(b"OpenGL ES")
        self.program_ids = []
        self.buffers = []
        self.textures = []
        self._programs = {}

    def program(self, vertex_source, fragment_source, attributes):
        key = (vertex_source, fragment_source, tuple(attributes))
        if key not in self._programs:
            self._programs[key] = Program(
                self, vertex_source, fragment_source, attributes
            )
        return self._programs[key]

    def buffer(self):
        handle = _gen(gl.glGenBuffers)
        self.buffers.append(handle)
        return handle

    def texture(self):
        handle = _gen(gl.glGenTextures)
        self.textures.append(handle)
        return handle

    def close(self):
        current = C.c_int()
        gl.glGetIntegerv(0x8B8D, C.byref(current))  # GL_CURRENT_PROGRAM
        if current.value in self.program_ids:
            gl.glUseProgram(0)
        for program in self.program_ids:
            gl.glDeleteProgram(program)
        self.program_ids.clear()
        self._programs.clear()
        for handles, delete in (
            (self.buffers, gl.glDeleteBuffers),
            (self.textures, gl.glDeleteTextures),
        ):
            if handles:
                delete(len(handles), (C.c_uint * len(handles))(*handles))
                handles.clear()


@dataclass(frozen=True, slots=True)
class RenderTarget:
    """Caller-owned full-map FBO with a depth attachment (at least 16 bits).

    flip=-1 writes top-to-bottom rows for readback/panel scanout; flip=+1
    uses normal GL texture orientation. Width, height and viewport origin x/y
    are physical pixels; the FBO can contain the map and additional host UI.
    The host must restore graphics state before its own subsequent drawing.
    """

    framebuffer: int
    width: int
    height: int
    flip: float = -1.0
    x: int = 0
    y: int = 0

    @property
    def viewport(self):
        return (float(self.width), float(self.height))

    def begin(self):
        gl.glBindFramebuffer(GL.FRAMEBUFFER, self.framebuffer)
        gl.glViewport(self.x, self.y, self.width, self.height)
        for state in (GL.SCISSOR_TEST, GL.DEPTH_TEST, GL.BLEND, 0x0B44, 0x0B90):
            gl.glDisable(state)  # cull and stencil state can be left by the host
        gl.glColorMask(1, 1, 1, 1)
        gl.glDepthMask(1)
        gl.glBlendEquation(GL.FUNC_ADD)
        gl.glClearColor(1.0, 1.0, 1.0, 1.0)
        clear_depth(1.0)
        gl.glClear(GL.COLOR_BUFFER_BIT | GL.DEPTH_BUFFER_BIT)
