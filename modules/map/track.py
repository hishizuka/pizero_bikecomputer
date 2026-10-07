"""Shared ride history with one logger cursor and bounded recent updates."""

import asyncio
import time

import numpy as np

from modules.app_logger import app_logger
from modules.utils.crdp import rdp

from .state import MapPolyline, MapTrack


class TrackStore:
    def __init__(self, tail_limit=320, simplify_interval=900, poll_interval=1.0):
        self.tail_limit = tail_limit
        self.simplify_interval = simplify_interval
        self.poll_interval = poll_interval
        self._generation = 0
        self._fetch_task = None
        self._simplify_task = None
        self.reset()

    def reset(self):
        self._generation += 1
        if self._simplify_task is not None:
            self._simplify_task.cancel()
        self._simplify_task = None
        self.timestamp = None
        self.last_position = None
        self._last_poll = -float("inf")
        self._last_simplified = 0
        self._history = []
        self._tail = []
        self._history_frame = None
        self._tail_frame = None
        self._snapshot = None

    @staticmethod
    def _polyline(points):
        values = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        return MapPolyline(values[:, 0], values[:, 1])

    @property
    def snapshot(self):
        if self._snapshot is None:
            if self._history_frame is None:
                self._history_frame = self._polyline(self._history)
            if self._tail_frame is None:
                points = self._tail
                if points and self._history:
                    points = [self._history[-1], *points]
                self._tail_frame = self._polyline(points)
            self._snapshot = MapTrack(self._history_frame, self._tail_frame)
        return self._snapshot

    def redraw_reasons(self, logger, history, tail):
        reasons = []
        if self.timestamp is None:
            reasons.append("track_init")
        track = self.snapshot
        if track.history is not history or track.tail is not tail:
            reasons.append("track_changed")
        if not logger.short_log_available:
            reasons.append("short_log_unavailable")
        if len(logger.short_log_lat):
            reasons.append("short_log_pending")
        return reasons

    async def update(self, logger):
        # Page cancellation must not lose a batch consumed from the logger.
        if self._fetch_task is None or self._fetch_task.done():
            now = time.monotonic()
            if now - self._last_poll < self.poll_interval:
                return False
            self._last_poll = now
            self._fetch_task = asyncio.create_task(self._fetch(logger))
        return await asyncio.shield(self._fetch_task)

    async def _fetch(self, logger):
        generation = self._generation
        try:
            timestamp, lon, lat = await asyncio.to_thread(
                logger.update_track, self.timestamp
            )
        except Exception:
            app_logger.exception("Map track retrieval failed")
            return False
        if generation != self._generation:
            return False
        self.timestamp = timestamp
        if not len(lon):
            return False
        points = np.column_stack((lon, lat)).astype(np.float32)
        finite = np.flatnonzero(np.isfinite(points).all(axis=1))
        if len(finite):
            self.last_position = tuple(float(v) for v in points[finite[-1]])
        self._tail.extend(points.tolist())
        self._tail_frame = self._snapshot = None
        if len(self._tail) > self.tail_limit:
            count = len(self._tail) - max(1, self.tail_limit // 2)
            self._history.extend(self._tail[:count])
            del self._tail[:count]
            self._history_frame = None
        if (
            self._simplify_task is None
            and len(self._history) - self._last_simplified >= self.simplify_interval
        ):
            self._last_simplified = len(self._history)
            points = np.asarray(self._history, dtype=np.float32)
            self._simplify_task = asyncio.create_task(
                self._simplify(points, generation)
            )
        return True

    @staticmethod
    def _simplify_points(points):
        # Preserve gaps; nonfinite points must not connect separate segments.
        valid = np.isfinite(points).all(axis=1)
        mask = ~valid
        boundaries = np.flatnonzero(np.diff(np.r_[False, valid, False]))
        for start, end in zip(boundaries[::2], boundaries[1::2]):
            mask[start:end] = (
                rdp(points[start:end], epsilon=0.0001, return_mask=True)
                if end - start >= 3
                else True
            )
        return points[mask].tolist()

    async def _simplify(self, points, generation):
        try:
            simplified = await asyncio.to_thread(self._simplify_points, points)
            if generation == self._generation:
                self._history = simplified + self._history[len(points) :]
                self._last_simplified = len(self._history)
                self._history_frame = self._tail_frame = self._snapshot = None
        finally:
            if generation == self._generation:
                self._simplify_task = None

    async def close(self):
        if self._simplify_task is not None:
            self._simplify_task.cancel()
        tasks = [t for t in (self._fetch_task, self._simplify_task) if t is not None]
        await asyncio.gather(*tasks, return_exceptions=True)
