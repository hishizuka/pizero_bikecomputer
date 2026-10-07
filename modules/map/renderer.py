"""Minimal GPU 2D map engine shared by QWidget and Qt Quick adapters.

The caller makes its context current for initialize/render/release and owns
the target FBO. Prepared tiles and immutable map snapshots can be produced
without GPU access; drawing never opens files, creates Qt objects or presents.
"""

import ctypes as C
from dataclasses import replace
from threading import get_ident

import numpy as np


from .geometry import direction_arrow_polygons, offset_polyline, wind_vane_paths
from .gl import GpuResources, QuadIndex, Transform, gl
from .gl_api import gl_check
from .marker import PositionMarker
from .projection import project
from .shapes import FillLayer, LineLayer, polygon_outlines
from .style import (
    COURSE_ARROW_OUTLINE_WIDTH,
    COURSE_ARROW_SPACING,
    COURSE_ARROW_WIDTH,
    COURSE_DETAIL_MIN_ZOOM,
    COURSE_LINE_WIDTH,
    COURSE_OUTLINE_WIDTH,
    COURSE_WIND_MARKER_SIZE,
    TRACK_COLOR,
    TRACK_WIDTH,
)
from .tile_layer import TileLayer
from .tiles import TILE_SIZE, visible_tiles


class MapRenderer2D:
    def __init__(
        self,
        position_images,
        tile_settings=None,
        traffic_offset_px=0.0,
        atlas_size=2048,
    ):
        self.position_images = position_images
        self.tile_settings = dict(tile_settings) if tile_settings is not None else {}
        self.traffic_offset_px = traffic_offset_px
        if atlas_size < TILE_SIZE or atlas_size % TILE_SIZE:
            raise ValueError("Atlas size must be a positive multiple of 256")
        self.atlas_size = atlas_size
        self.resources = None
        self.tiles = None
        self._course = None
        self._course_world = None

    def initialize(self):
        """Allocate resources in the host's current context, on its drawing thread."""
        if self.resources is not None:
            raise RuntimeError("Renderer is already initialized")
        self.resources = GpuResources()
        self._thread = get_ident()
        try:
            size = C.c_int()
            gl.glGetIntegerv(0x0D33, C.byref(size))  # GL_MAX_TEXTURE_SIZE
            self.quads = QuadIndex(self.resources)
            self.tiles = TileLayer(self.resources, min(self.atlas_size, size.value))
            self.course_line = LineLayer(self.resources)
            self.arrow_fill = FillLayer(self.resources)
            self.arrow_outline = LineLayer(self.resources)
            self.track_layers = [LineLayer(self.resources) for _ in range(2)]
            self._track_segments = [None, None]
            self.wind_line = LineLayer(self.resources, dynamic=True)
            self._wind_key = None
            self.point_marker = PositionMarker(self.resources, self.position_images)
            self._origin = None
            self._course = None
            self._course_world = None
            self._course_key = None
            self._tile_namespace = None
            self.overlay_tiles = None
            self._overlay_namespace = None
            gl_check("map initialize")
        except Exception:
            self.release()
            raise

    def _check_thread(self):
        if self.resources is None:
            raise RuntimeError("Renderer must be initialized in the current context")
        if self._thread != get_ident():
            raise RuntimeError(
                "GPU operations must run on the renderer's drawing thread"
            )

    def release(self):
        """Release this engine's handles; leave the host context and target alive."""
        if self.resources is not None:
            self._check_thread()
            self.resources.close()
            self.resources = None
            self.tiles = None
            self.overlay_tiles = None
            self.track_layers = []
            self._track_segments = [None, None]
            self._course = None
            self._course_world = None

    def required_tiles(self, snapshot):
        return visible_tiles(snapshot.view, self.tile_settings)

    def _update_course(self, course, zoom, scale, pixel_ratio):
        if course is not self._course:
            self._course = course
            self._course_key = None
            self._course_world = (
                (*project(course.longitude, course.latitude), course.colors)
                if course is not None
                else None
            )
            if course is None:
                self.course_line.set_polylines([])
                self.arrow_fill.set_polygons([], (255, 255, 255))
                self.arrow_outline.set_polylines([])
        if course is None:
            return
        key = (zoom, *scale, self.traffic_offset_px, pixel_ratio)
        old = self._course_key
        if (
            old is not None
            and key[0] == old[0]
            and key[3:] == old[3:]
            and all(abs(a / b - 1) < 0.005 for a, b in zip(key[1:3], old[1:3]))
        ):
            return
        x, y, colors = self._course_world
        if self.traffic_offset_px and zoom >= COURSE_DETAIL_MIN_ZOOM:
            x, y, source = offset_polyline(
                x, y, scale, self.traffic_offset_px * pixel_ratio
            )
            colors = colors[source]
        self.course_line.set_polylines([(x, y, colors)], self._origin)
        arrows = (
            direction_arrow_polygons(
                x,
                y,
                scale,
                COURSE_ARROW_SPACING * pixel_ratio,
                COURSE_ARROW_WIDTH * pixel_ratio,
            )
            if zoom >= COURSE_DETAIL_MIN_ZOOM
            else []
        )
        self.arrow_fill.set_polygons(arrows, (255, 255, 255), self._origin)
        self.arrow_outline.set_polylines(polygon_outlines(arrows), self._origin)
        self._course_key = key

    def render_frame(self, frame, target):
        """Submit the same prepared frame from image and texture adapters."""
        self.tile_settings = frame.settings
        self.traffic_offset_px = frame.traffic_offset
        return self.render(
            frame.snapshot,
            target,
            frame.tiles,
            frame.tile_namespace,
            frame.overlay,
            frame.hud,
        )

    def render(
        self,
        snapshot,
        target,
        prepared_tiles,
        tile_namespace=None,
        overlay=None,
        hud=None,
    ):
        """Draw one complete map into the host's FBO, without readback or glFinish.

        The FBO must have a depth attachment; the target size must match the
        snapshot's physical pixel size. Hosts restore their own graphics state
        afterwards (Qt Quick adapters also bracket external GL commands).
        """
        self._check_thread()
        view = snapshot.view
        if (
            tile_namespace != self._tile_namespace
            or self.tiles.tile_size != view.tile_size
        ):
            self.tiles.reset(view.tile_size)
            self._tile_namespace = tile_namespace
        if (target.width, target.height) != (view.width, view.height):
            raise ValueError("Render target size must match the map view")
        if self._origin is None:
            self._origin = project(view.longitude, view.latitude)
            if snapshot.course is not None:
                course = snapshot.course
                valid = np.flatnonzero(
                    np.isfinite(course.longitude) & np.isfinite(course.latitude)
                )
                if len(valid):
                    i = valid[0]
                    self._origin = project(course.longitude[i], course.latitude[i])
        x0, x1, y0, y1 = view.projected_bounds
        transform = Transform.ranges(
            (x0, x1), (y0, y1), (0, 0, view.width, view.height), self._origin
        )
        scale = ((x1 - x0) / view.width, (y1 - y0) / view.height)
        keys = self.required_tiles(snapshot)
        target.begin()
        uploads = self.tiles.update(keys, prepared_tiles)
        calls = self.tiles.draw(target, self.quads, transform, keys, view, self._origin)
        overlay_calls, overlay_uploads = self._draw_overlay(
            overlay, view, target, transform
        )
        calls += overlay_calls
        uploads += overlay_uploads
        ratio = view.pixel_ratio
        self._update_course(snapshot.course, view.zoom, scale, ratio)
        if snapshot.course is not None:
            calls += self.course_line.draw(
                target,
                self.quads,
                transform,
                COURSE_OUTLINE_WIDTH * ratio,
                color=(0, 0, 0, 160),
                hard=True,
                depth=0.5,
            )
            calls += self.course_line.draw(
                target, self.quads, transform, COURSE_LINE_WIDTH * ratio
            )
            calls += self.arrow_fill.draw(target, self.quads, transform)
            calls += self.arrow_outline.draw(
                target,
                self.quads,
                transform,
                COURSE_ARROW_OUTLINE_WIDTH * ratio,
                color=(0, 0, 0),
            )
        calls += self._draw_track(snapshot.track, view, target, transform)
        calls += self._draw_winds(hud.winds if hud is not None else (), view, target)
        if snapshot.position is not None:
            self.point_marker.set_images(self.position_images)
            position = snapshot.position
            x, y = project(position.longitude, position.latitude)
            calls += self.point_marker.draw(
                target,
                self.quads,
                transform,
                (
                    x - self._origin[0],
                    y - self._origin[1],
                ),
                position.heading,
                position.fix,
                ratio,
            )
        return {
            "uploads": uploads,
            "pending": sum(key not in self.tiles.cache for key in keys),
            "draw_calls": calls,
        }

    def _draw_winds(self, winds, view, target):
        ratio = view.pixel_ratio
        key = (winds, ratio)
        if key != self._wind_key:
            lines = []
            for x, y, angle, color in winds:
                for path in wind_vane_paths(angle):
                    points = (np.asarray(path) + (x, y)) * ratio
                    lines.append(
                        (points[:, 0], points[:, 1], np.tile(color, (len(path), 1)))
                    )
            self.wind_line.set_polylines(lines)
            self._wind_key = key
        width = COURSE_WIND_MARKER_SIZE * 0.12 * ratio
        return sum(
            self.wind_line.draw(target, self.quads, Transform.screen(), stroke, color)
            for color, stroke in (
                ((255, 255, 255), width + 8 * ratio),
                ((0, 0, 0), width + 4 * ratio),
                (None, width),
            )
        )

    def _draw_overlay(self, overlay, view, target, transform):
        uploads = calls = 0
        if overlay is not None:
            if self.overlay_tiles is None:
                self.overlay_tiles = TileLayer(
                    self.resources, self.tiles.size, overlay=True
                )
            if overlay.namespace != self._overlay_namespace:
                self.overlay_tiles.reset(overlay.settings["tile_size"])
                self._overlay_namespace = overlay.namespace
            overlay_view = replace(overlay.view, width=view.width, height=view.height)
            overlay_keys = visible_tiles(overlay_view, overlay.settings)
            uploads = self.overlay_tiles.update(overlay_keys, overlay.tiles)
            calls = self.overlay_tiles.draw(
                target, self.quads, transform, overlay_keys, overlay_view, self._origin
            )
        return calls, uploads

    def _draw_track(self, track, view, target, transform):
        calls = 0
        ratio = view.pixel_ratio
        segments = (track.history, track.tail) if track is not None else (None, None)
        for i, (layer, segment) in enumerate(zip(self.track_layers, segments)):
            if segment is not self._track_segments[i]:
                lines = (
                    []
                    if segment is None
                    else [
                        (
                            *project(segment.longitude, segment.latitude),
                            None,
                        )
                    ]
                )
                layer.set_polylines(lines, self._origin)
                self._track_segments[i] = segment
            calls += layer.draw(
                target,
                self.quads,
                transform,
                TRACK_WIDTH * ratio,
                color=TRACK_COLOR,
                depth=0.25,
            )
        return calls
