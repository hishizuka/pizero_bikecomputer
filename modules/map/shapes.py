"""Lines and filled shapes kept on the GPU.

Lines: every segment is a quad around a capsule. The vertex shader projects
both end points and extrudes the quad to a constant pixel width; the fragment
shader keeps the pixels within half the width of the segment, so caps and
joins come out round (like Qt RoundCap/RoundJoin) and the edge is
antialiased over one pixel. Translucent lines (the course outline) are drawn
"hard" with a depth write so each pixel is blended exactly once where
segments overlap at joins.

Fills: triangles or quads with per-vertex colors (course arrows, profile
polygons, bars, legend blocks).
"""

from __future__ import annotations

import numpy as np

from .gl import COMMON_VS, GL, VertexBuffer, gl

LINE_DTYPE = np.dtype(
    [
        ("p0", np.float32, 2),
        ("p1", np.float32, 2),
        ("corner", np.float32, 2),
        ("color", np.uint8, 4),
    ]
)
FILL_DTYPE = np.dtype([("pos", np.float32, 2), ("color", np.uint8, 4)])

_LINE_VS = COMMON_VS + """
attribute vec2 a_p0;
attribute vec2 a_p1;
attribute vec2 a_corner;
attribute vec4 a_color;
uniform float u_half;
uniform vec4 u_color;
uniform float u_z;
varying vec2 v_pos;
varying vec2 v_s0;
varying vec2 v_s1;
varying vec4 v_color;
void main() {
    vec2 s0 = to_px(a_p0);
    vec2 s1 = to_px(a_p1);
    vec2 d = s1 - s0;
    float len = length(d);
    vec2 dir = len > 0.0001 ? d / len : vec2(1.0, 0.0);
    vec2 n = vec2(-dir.y, dir.x);
    float r = u_half + 1.0;
    vec2 pos = mix(s0, s1, a_corner.x)
             + dir * (a_corner.x * 2.0 - 1.0) * r + n * a_corner.y * r;
    v_pos = pos;
    v_s0 = s0;
    v_s1 = s1;
    v_color = u_color.a > 0.0 ? u_color : a_color;
    gl_Position = px_to_clip(pos, u_z);
}
"""
_LINE_FS = """
precision highp float;
uniform float u_half;
uniform float u_hard;
varying vec2 v_pos;
varying vec2 v_s0;
varying vec2 v_s1;
varying vec4 v_color;
void main() {
    vec2 pa = v_pos - v_s0;
    vec2 ba = v_s1 - v_s0;
    float h = clamp(dot(pa, ba) / max(dot(ba, ba), 0.000001), 0.0, 1.0);
    float dist = length(pa - ba * h);
    if (u_hard > 0.5) {
        if (dist > u_half) discard;
        gl_FragColor = v_color;
    } else {
        float coverage = clamp(u_half + 0.5 - dist, 0.0, 1.0);
        if (coverage <= 0.0) discard;
        gl_FragColor = vec4(v_color.rgb, v_color.a * coverage);
    }
}
"""
_FILL_VS = COMMON_VS + """
attribute vec2 a_pos;
attribute vec4 a_color;
varying vec4 v_color;
void main() {
    v_color = a_color;
    gl_Position = px_to_clip(to_px(a_pos), 0.0);
}
"""
_FILL_FS = """
precision mediump float;
varying vec4 v_color;
void main() { gl_FragColor = v_color; }
"""

_CORNERS = np.array([[0, -1], [0, 1], [1, 1], [1, -1]], dtype=np.float32)


def _rgba(color) -> tuple[int, int, int, int]:
    color = tuple(int(c) for c in color)
    return color if len(color) == 4 else (*color, 255)


class LineLayer:
    """Polylines stored once (static) or per frame (dynamic) as capsule segments."""

    def __init__(self, resources, dynamic=False):
        self.program = resources.program(
            _LINE_VS, _LINE_FS, ["a_p0", "a_p1", "a_corner", "a_color"]
        )
        self.vbo = VertexBuffer(resources, LINE_DTYPE, dynamic=dynamic)

    def set_polylines(self, polylines, origin=(0.0, 0.0)):
        """Store (x, y, segment_colors or None); NaN points break the line.

        Color i belongs to the segment ending at point i.
        """
        parts = []
        for x, y, colors in polylines:
            x = np.asarray(x, dtype=np.float64) - origin[0]
            y = np.asarray(y, dtype=np.float64) - origin[1]
            if len(x) < 2:
                continue
            valid = (
                np.isfinite(x[:-1])
                & np.isfinite(y[:-1])
                & np.isfinite(x[1:])
                & np.isfinite(y[1:])
            )
            if colors is None:
                rgba = np.zeros((len(x) - 1, 4), dtype=np.uint8)
            else:
                rgba = np.asarray(colors, dtype=np.float64)[1:]
                ok = np.isfinite(rgba).all(axis=1)
                rgba = np.where(ok[:, None], rgba, 0)
                if rgba.shape[1] == 3:
                    rgba = np.column_stack([rgba, np.where(ok, 255, 0)])
                rgba = rgba.astype(np.uint8)
            seg = np.zeros(int(valid.sum()) * 4, dtype=LINE_DTYPE)
            p0 = np.column_stack([x[:-1], y[:-1]])[valid]
            p1 = np.column_stack([x[1:], y[1:]])[valid]
            seg["p0"] = np.repeat(p0, 4, axis=0)
            seg["p1"] = np.repeat(p1, 4, axis=0)
            seg["corner"] = np.tile(_CORNERS, (len(p0), 1))
            seg["color"] = np.repeat(rgba[valid], 4, axis=0)
            parts.append(seg)
        records = np.concatenate(parts) if parts else np.zeros(0, dtype=LINE_DTYPE)
        self.vbo.upload(records)

    def draw(self, target, quads, transform, width, color=None, hard=False, depth=None):
        """Override segment colors; depth (0..1) enables draw-once blending."""
        if self.vbo.count == 0:
            return 0
        program = self.program.use()
        program.set_transform(transform, target.viewport, target.flip)
        program.set("u_half", width / 2.0)
        rgba = (
            (0.0, 0.0, 0.0, 0.0)
            if color is None
            else tuple(c / 255.0 for c in _rgba(color))
        )
        program.set("u_color", *rgba)
        program.set("u_hard", 1.0 if hard else 0.0)
        program.set("u_z", 0.0 if depth is None else depth * 2.0 - 1.0)
        gl.glEnable(GL.BLEND)
        gl.glBlendFuncSeparate(
            GL.SRC_ALPHA, GL.ONE_MINUS_SRC_ALPHA, GL.ONE, GL.ONE_MINUS_SRC_ALPHA
        )
        if depth is not None:
            gl.glEnable(GL.DEPTH_TEST)
            gl.glDepthFunc(GL.LESS)
        calls = quads.draw(self.vbo, program)
        if depth is not None:
            gl.glDisable(GL.DEPTH_TEST)
        gl.glDisable(GL.BLEND)
        VertexBuffer.unbind(program)
        return calls


class FillLayer:
    """Colored quads (4 vertices each) drawn with the shared quad index buffer."""

    def __init__(self, resources, dynamic=False):
        self.program = resources.program(_FILL_VS, _FILL_FS, ["a_pos", "a_color"])
        self.vbo = VertexBuffer(resources, FILL_DTYPE, dynamic=dynamic)

    def set_quads(self, corners: np.ndarray, colors: np.ndarray, origin=(0.0, 0.0)):
        """corners: (n, 4, 2) data coordinates; colors: (n, 3|4) per quad."""
        corners = np.asarray(corners, dtype=np.float64).reshape(-1, 4, 2) - np.asarray(
            origin
        )
        colors = np.asarray(colors)
        if colors.ndim == 2 and colors.shape[1] == 3:
            colors = np.column_stack([colors, np.full(len(colors), 255)])
        records = np.zeros(len(corners) * 4, dtype=FILL_DTYPE)
        records["pos"] = corners.reshape(-1, 2)
        records["color"] = np.repeat(
            np.asarray(colors, dtype=np.uint8).reshape(-1, 4), 4, axis=0
        )
        self.vbo.upload(records)

    def set_polygons(self, polygons, fill_color, origin=(0.0, 0.0)):
        """Star-shaped polygons (course chevrons) as fans around vertex 3 (the notch),
        emitted as degenerate quads (two triangles per quad) for the quad index buffer.
        """
        quads = []
        for polygon in polygons:
            p = np.asarray(polygon, dtype=np.float64)
            n = len(p)
            hub = p[3 % n]
            ring = [p[(3 + k) % n] for k in range(1, n)]
            for a, b in zip(ring[:-1], ring[1:]):
                quads.append((hub, a, b, b))
        if not quads:
            self.vbo.upload(np.zeros(0, dtype=FILL_DTYPE))
            return
        self.set_quads(
            np.array(quads), np.tile(_rgba(fill_color), (len(quads), 1)), origin
        )

    def draw(self, target, quads, transform, blend=False):
        if self.vbo.count == 0:
            return 0
        program = self.program.use()
        program.set_transform(transform, target.viewport, target.flip)
        if blend:
            gl.glEnable(GL.BLEND)
            gl.glBlendFuncSeparate(
                GL.SRC_ALPHA, GL.ONE_MINUS_SRC_ALPHA, GL.ONE, GL.ONE_MINUS_SRC_ALPHA
            )
        calls = quads.draw(self.vbo, program)
        if blend:
            gl.glDisable(GL.BLEND)
        VertexBuffer.unbind(program)
        return calls


def polygon_outlines(polygons):
    """Closed polygon edges as polylines for LineLayer."""
    lines = []
    for polygon in polygons:
        p = np.asarray(polygon, dtype=np.float64)
        closed = np.vstack([p, p[:1]])
        lines.append((closed[:, 0], closed[:, 1], None))
    return lines
