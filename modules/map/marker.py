"""Current-position textures supplied by the host; no image file or Qt access."""

import math

import numpy as np

from .geometry import heading_angle
from .style import POSITION_MARKER_CANVAS_SIZE
from .gl import COMMON_VS, GL, Texture, VertexBuffer, gl

_DTYPE = np.dtype([("offset", np.float32, 2), ("uv", np.float32, 2)])
_VS = COMMON_VS + """
attribute vec2 a_offset;
attribute vec2 a_uv;
uniform vec2 u_anchor;
uniform vec2 u_rot;
varying vec2 v_uv;
void main() {
    vec2 o = vec2(a_offset.x * u_rot.x - a_offset.y * u_rot.y,
                  a_offset.x * u_rot.y + a_offset.y * u_rot.x);
    v_uv = a_uv;
    gl_Position = px_to_clip(floor(to_px(u_anchor) + 0.5) + o, 0.0);
}
"""
_FS = """
precision mediump float;
uniform sampler2D u_tex;
varying vec2 v_uv;
void main() { gl_FragColor = texture2D(u_tex, v_uv); }
"""


class PositionMarker:
    def __init__(self, resources, images):
        self.program = resources.program(_VS, _FS, ["a_offset", "a_uv"])
        self.vbo = VertexBuffer(resources, _DTYPE)
        self.textures = {
            fix: Texture(resources, 1, 1, filter_=GL.LINEAR) for fix in (True, False)
        }
        self.images = None
        self.set_images(images)
        # Geometry is in logical pixels; the host may supply a HiDPI texture.
        w = h = POSITION_MARKER_CANVAS_SIZE
        records = np.array(
            [
                ((-w / 2, -h / 2), (0, 0)),
                ((w / 2, -h / 2), (1, 0)),
                ((w / 2, h / 2), (1, 1)),
                ((-w / 2, h / 2), (0, 1)),
            ],
            dtype=_DTYPE,
        )
        self.vbo.upload(records)

    def set_images(self, images):
        if images is self.images:
            return
        for fix, texture in self.textures.items():
            rgba = images[fix]
            texture.height, texture.width = rgba.shape[:2]
            texture.bind()
            gl.glPixelStorei(GL.UNPACK_ALIGNMENT, 1)
            gl.glTexImage2D(
                GL.TEXTURE_2D,
                0,
                GL.RGBA,
                texture.width,
                texture.height,
                0,
                GL.RGBA,
                GL.UNSIGNED_BYTE,
                rgba.ctypes.data,
            )
        self.images = images

    def draw(self, target, quads, transform, anchor, heading, fix, pixel_ratio=1.0):
        program = self.program.use()
        program.set_transform(transform, target.viewport, target.flip)
        program.set("u_anchor", *anchor)
        angle = math.radians(heading_angle(heading))
        program.set(
            "u_rot", math.cos(angle) * pixel_ratio, math.sin(angle) * pixel_ratio
        )
        program.set("u_tex", 0)
        self.textures[fix].bind()
        gl.glEnable(GL.BLEND)
        gl.glBlendFunc(GL.ONE, GL.ONE_MINUS_SRC_ALPHA)
        calls = quads.draw(self.vbo, program)
        gl.glDisable(GL.BLEND)
        VertexBuffer.unbind(program)
        return calls
