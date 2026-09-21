"""Schedule rain detection and maintain two-stage notification history."""

import asyncio
from time import monotonic

import numpy as np

from modules.app_logger import app_logger
from modules.helper.rain_tiles import RainTiles
from modules.utils.map import get_rain_time


class RainHistory:
    def __init__(self):
        self.near = self.far = False
        self.interrupt_clear()

    def interrupt_clear(self):
        self.dry_since = None
        self.dry_frame = None

    def update(self, result, frame_time, verified, now):
        if result is None:
            self.interrupt_clear()
            return False
        if result.zone == "dry":
            if not verified:
                return False
            if self.dry_since is None:
                self.dry_since, self.dry_frame = now, frame_time
            elif frame_time > self.dry_frame:
                self.dry_frame = frame_time
                if now - self.dry_since >= 600:
                    self.near = self.far = False
                    self.interrupt_clear()
            return False
        self.interrupt_clear()
        if result.zone == "far":
            notify = not self.far
            self.far = True
        else:
            notify = not self.near
            self.near = self.far = True
        return notify


class RainAlert:
    def __init__(self, config, notify=None):
        self.config = config
        self.notify = notify
        self.tiles = RainTiles(config)
        self.source = config.G_RAIN_OVERLAY_MAP
        self._generation = 0
        self.reset()
        self._task = None
        self._stopping = False

    def start(self):
        self._stopping = False
        self._task = asyncio.create_task(self.run())

    async def stop(self):
        self._stopping = True
        self._generation += 1
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def reset(self):
        self._generation += 1
        self.history = RainHistory()
        self.result = self.frame = None
        self._refresh_time = None
        self._next_evaluate = 0

    def set_enabled(self, enabled):
        self.config.G_RAIN_ALERT = enabled
        self.reset()

    def position(self):
        gps = self.config.logger.sensor.values["GPS"]
        lon, lat = gps["lon"], gps["lat"]
        if (
            self.config.G_DUMMY_OUTPUT
            or not np.all(np.isfinite((lon, lat)))
            or not (-180 <= lon <= 180 and -85.05112878 < lat < 85.05112878)
        ):
            return None
        return lon, lat

    async def run(self):
        while not self._stopping:
            try:
                await self.step()
            except Exception:
                app_logger.exception("[Rain] evaluation failed")
                self.result = None
                self.history.interrupt_clear()
                self._next_evaluate = monotonic() + self.config.G_RAIN_ALERT_RECHECK
            await asyncio.sleep(1)

    async def step(self):
        source = self.config.G_RAIN_OVERLAY_MAP
        if source != self.source:
            self.source = source
            self.reset()
        if not self.config.G_RAIN_ALERT:
            return
        pos = self.position()
        if pos is None:
            self.result = None
            self.history.interrupt_clear()
            self._next_evaluate = 0
            return
        now = monotonic()
        if source not in self.config.G_RAIN_ALERT_INTERVAL_FACTOR:
            return
        time_key = get_rain_time(
            self.config.G_RAIN_OVERLAY_MAP_CONFIG[source],
            self.config.G_RAIN_ALERT_INTERVAL_FACTOR[source],
        )
        refresh = time_key != self._refresh_time
        if not refresh and now < self._next_evaluate:
            return
        generation = self._generation
        frame = self.frame
        verified = False
        self._next_evaluate = now + self.config.G_RAIN_ALERT_RECHECK
        grid = None
        if refresh:
            self._refresh_time = time_key
            latest, grid = await self.tiles.refresh(source, pos)
            if latest is not None:
                frame, verified = latest, True
            else:
                self.history.interrupt_clear()

        if generation != self._generation or source != self.config.G_RAIN_OVERLAY_MAP:
            return
        if grid is None and frame is not None and (not refresh or not verified):
            grid = await self.tiles.region(frame, pos)
        if (
            refresh
            and self.frame is not None
            and frame != self.frame
            and (grid is None or grid.analyze(pos) is None)
        ):
            frame, verified = self.frame, False
            self.history.interrupt_clear()
            grid = await self.tiles.region(frame, self.position() or pos)
        # An old frame's missing tiles may have left the provider's archive.
        if grid is None and not refresh:
            self._refresh_time = time_key
            latest, grid = await self.tiles.refresh(source, self.position() or pos)
            if latest is not None:
                frame, verified = latest, True

        if (
            generation != self._generation
            or source != self.config.G_RAIN_OVERLAY_MAP
            or not self.config.G_RAIN_ALERT
        ):
            return
        pos = self.position()
        result = grid.analyze(pos) if grid is not None and pos is not None else None
        self.frame = frame
        self.result = result if result is not None and result.zone != "dry" else None
        notify = self.history.update(
            result, frame.time if frame else 0, verified, monotonic()
        )
        if notify and self.notify is not None:
            self.notify(result.message, result.color)
