"""Context-local RGB565 atlas and cached tile geometry for the 2D map."""

from collections import OrderedDict

import numpy as np

from modules.utils.map import get_map_tile_range

from .gl import COMMON_VS, GL, Texture, VertexBuffer, gl
from .projection import WORLD_WIDTH
from .tiles import TILE_SIZE, layer_zoom

_DTYPE = np.dtype(
    [("pos", np.float32, 2), ("uv", np.float32, 2), ("rect", np.float32, 4)]
)
_VS = COMMON_VS + """
attribute vec2 a_pos;
attribute vec2 a_uv;
attribute vec4 a_rect;
varying vec2 v_uv;
varying vec4 v_rect;
void main() {
    v_uv = a_uv;
    v_rect = a_rect;
    gl_Position = px_to_clip(to_px(a_pos), 0.0);
}
"""
_FS = """
precision highp float;
uniform sampler2D u_tex;
varying vec2 v_uv;
varying vec4 v_rect;
void main() {
    vec2 uv = clamp(v_uv, v_rect.xy, v_rect.zw);
    gl_FragColor = vec4(texture2D(u_tex, uv).rgb, 1.0);
}
"""

_OVERLAY_FS = """
precision highp float;
uniform sampler2D u_tex;
uniform sampler2D u_scene;
uniform vec2 u_viewport;
varying vec2 v_uv;
varying vec4 v_rect;
void main() {
    vec4 over = texture2D(u_tex, clamp(v_uv, v_rect.xy, v_rect.zw));
    vec3 under = texture2D(u_scene, gl_FragCoord.xy / u_viewport).rgb;
    gl_FragColor = vec4(mix(under, min(under, over.rgb), over.a), 1.0);
}
"""


class TileLayer:
    def __init__(self, resources, size, overlay=False):
        self.size = size
        self.texture = Texture(
            resources,
            size,
            size,
            GL.RGBA if overlay else GL.RGB,
            GL.UNSIGNED_BYTE if overlay else GL.UNSIGNED_SHORT_5_6_5,
        )
        self.scene = Texture(resources, 1, 1) if overlay else None
        self.program = resources.program(
            _VS, _OVERLAY_FS if overlay else _FS, ["a_pos", "a_uv", "a_rect"]
        )
        self.vbo = VertexBuffer(resources, _DTYPE, dynamic=True)
        self.reset()

    def reset(self, tile_size=TILE_SIZE):
        """Forget tile placement when the source changes, reusing the GPU atlas."""
        if tile_size <= 0 or self.size % tile_size:
            raise ValueError("Atlas size must be a multiple of the source tile size")
        self.tile_size = tile_size
        self.per_row = self.size // tile_size
        self.cache = OrderedDict()
        self.free = list(range(self.per_row**2))[::-1]
        self.geometry_key = None

    def update(self, keys, tiles):
        """Upload prepared arrays only; protect this frame's visible atlas slots."""
        uploads = 0
        protect = set(keys)
        for key in keys:
            pixels = tiles.get(key)
            if pixels is None:
                continue
            cached = self.cache.get(key)
            if cached is not None:
                self.cache.move_to_end(key)
                if cached[0] is pixels:
                    continue
                slot = cached[1]
            else:
                if not self.free:
                    victim = next((k for k in self.cache if k not in protect), None)
                    if victim is None:
                        continue
                    self.free.append(self.cache.pop(victim)[1])
                slot = self.free.pop()
            x = slot % self.per_row * self.tile_size
            y = slot // self.per_row * self.tile_size
            self.texture.upload(x, y, pixels)
            self.cache[key] = (pixels, slot)
            uploads += 1
        return uploads

    def _update_geometry(self, keys, view, origin):
        available = tuple(
            (key, self.cache[key][1]) for key in keys if key in self.cache
        )
        zoom = layer_zoom(view, self.tile_size)
        (first_x, last_x), (first_y, last_y) = get_map_tile_range(zoom, view.bounds)
        key = (available, zoom, origin, first_x, last_x, first_y, last_y)
        if key == self.geometry_key:
            return
        records = []
        for (z, x, y), slot in available:
            sx, sy = (
                slot % self.per_row * self.tile_size,
                slot // self.per_row * self.tile_size,
            )
            u0, v0 = sx / self.size, sy / self.size
            u1, v1 = (sx + self.tile_size) / self.size, (
                sy + self.tile_size
            ) / self.size
            half = 0.5 / self.size
            uv_rect = (u0 + half, v0 + half, u1 - half, v1 - half)
            rows = 2 ** (zoom - z)
            # Clip overzoom to display-tile cells before float32 conversion.
            # Whole-world vertices lose precision at street-level zoom.
            left = max(0, first_x - x * rows) / rows
            right = min(rows, last_x - x * rows + 1) / rows
            top = max(0, first_y - y * rows) / rows
            bottom = min(rows, last_y - y * rows + 1) / rows
            unit = WORLD_WIDTH / 2**z
            x0 = (x + left) * unit - WORLD_WIDTH / 2 - origin[0]
            x1 = (x + right) * unit - WORLD_WIDTH / 2 - origin[0]
            y0 = WORLD_WIDTH / 2 - (y + bottom) * unit - origin[1]
            y1 = WORLD_WIDTH / 2 - (y + top) * unit - origin[1]
            su0, su1 = u0 + (u1 - u0) * left, u0 + (u1 - u0) * right
            sv0, sv1 = v0 + (v1 - v0) * top, v0 + (v1 - v0) * bottom
            records.extend(
                [
                    ((x0, y1), (su0, sv0), uv_rect),
                    ((x1, y1), (su1, sv0), uv_rect),
                    ((x1, y0), (su1, sv1), uv_rect),
                    ((x0, y0), (su0, sv1), uv_rect),
                ]
            )
        self.vbo.upload(np.array(records, dtype=_DTYPE))
        self.geometry_key = key

    def draw(self, target, quads, transform, keys, view, origin):
        self._update_geometry(keys, view, origin)
        if not self.vbo.count:
            return 0
        if self.scene is not None:
            scene = self.scene
            scene.bind()
            if (scene.width, scene.height) != (target.width, target.height):
                scene.width, scene.height = target.width, target.height
                gl.glTexImage2D(
                    GL.TEXTURE_2D,
                    0,
                    GL.RGBA,
                    target.width,
                    target.height,
                    0,
                    GL.RGBA,
                    GL.UNSIGNED_BYTE,
                    None,
                )
            gl.glCopyTexSubImage2D(
                GL.TEXTURE_2D, 0, 0, 0, 0, 0, target.width, target.height
            )
            scene.bind(1)
        self.texture.bind()
        program = self.program.use()
        if self.scene is not None:
            program.set("u_scene", 1)
        program.set_transform(transform, target.viewport, target.flip)
        program.set("u_tex", 0)
        calls = quads.draw(self.vbo, program)
        VertexBuffer.unbind(program)
        return calls
