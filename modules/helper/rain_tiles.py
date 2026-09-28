"""Load shared radar tiles at zoom 6 without changing the map's selected frame."""

import asyncio
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from modules.helper.maptile import (
    JMA_RAIN_COLOR,
    JMA_RAIN_COLOR_CONV,
    apply_rain_frame,
)
from modules.helper.rain_palette import RAINVIEWER_RAIN_RGBA
from modules.utils.map import get_maptile_filename

ZOOM = 6
TILE_SIZE = 256
WORLD = TILE_SIZE * 2**ZOOM
EARTH_CIRCUMFERENCE = 40_075_016.686
NEAR_RADIUS = 5_000
FAR_RADIUS = 10_000


def pixel_position(pos):
    lon, lat = pos
    x = (lon + 180) / 360 * WORLD
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * WORLD
    scale = EARTH_CIRCUMFERENCE * math.cos(math.radians(lat)) / WORLD
    return x, y, scale


@lru_cache(maxsize=2)
def palette(source):
    if source == "jpn_jma_bousai":
        rgba = np.column_stack(
            (JMA_RAIN_COLOR, np.full(len(JMA_RAIN_COLOR), 255))
        ).astype(np.uint8)
        colors = tuple("#%02X%02X%02X" % tuple(rgb[:3]) for rgb in JMA_RAIN_COLOR_CONV)
    else:
        rgba = np.array(
            [list(bytes.fromhex(c[1:])) for c in RAINVIEWER_RAIN_RGBA], dtype=np.uint8
        )
        colors = tuple(c[:7] for c in RAINVIEWER_RAIN_RGBA)
    return rgba, colors


@lru_cache(maxsize=2)
def _palette_lookup(source):
    rgba, _ = palette(source)
    weights = np.array([1 << 24, 1 << 16, 1 << 8, 1], dtype=np.uint32)
    # Duplicate saturated colors represent the strongest matching bin.
    mapping = dict(zip(rgba.astype(np.uint32) @ weights, range(1, len(rgba) + 1)))
    keys = np.array(sorted(mapping), dtype=np.uint32)
    values = np.array([mapping[k] for k in keys], dtype=np.int16)
    return weights, keys, values


def decode_rain(image, source):
    """Match exact RGBA colors; unknown/missing is -1, transparent is zero."""
    weights, keys, values = _palette_lookup(source)
    pixels = image.astype(np.uint32) @ weights
    index = np.searchsorted(keys, pixels).clip(0, len(keys) - 1)
    ranks = np.where(keys[index] == pixels, values[index], -1).astype(np.int16)
    ranks[image[..., 3] == 0] = 0
    return ranks


@lru_cache(maxsize=32)
def _read_tile(filename, source, modified):
    with Image.open(filename) as image:
        if image.size != (TILE_SIZE, TILE_SIZE):
            raise ValueError("Unexpected radar tile size")
        rgba = np.array(image.convert("RGBA"))
    if source == "rainviewer_coverage":
        return rgba[..., 3] == 0
    return decode_rain(rgba, source)


def read_tile(filename, source):
    try:
        return _read_tile(filename, source, Path(filename).stat().st_mtime_ns)
    except (OSError, ValueError):
        return None


@dataclass(frozen=True)
class RainResult:
    zone: str
    color: str = ""

    @property
    def size(self):
        return 18 if self.zone in ("current", "near") else 10

    @property
    def message(self):
        if self.zone == "current":
            return "Raining"
        radius = (NEAR_RADIUS if self.zone == "near" else FAR_RADIUS) // 1000
        return f"in {radius} km"


def analyze_rain(ranks, x, y, meters_per_pixel, colors):
    """Return None for unknown; zero is dry and positive ranks are precipitation."""
    ix, iy = math.floor(x), math.floor(y)
    if not (0 <= ix < ranks.shape[1] and 0 <= iy < ranks.shape[0]):
        return None
    current = ranks[iy, ix]
    if current < 0:
        return None
    if current > 0:
        return RainResult("current", colors[current - 1])

    radius = FAR_RADIUS / meters_per_pixel
    if (
        x - radius < 0
        or y - radius < 0
        or x + radius > ranks.shape[1]
        or y + radius > ranks.shape[0]
    ):
        return None

    yy, xx = np.indices(ranks.shape)
    dx, dy = xx + 0.5 - x, yy + 0.5 - y
    d2 = (dx * dx + dy * dy) * meters_per_pixel**2
    area = d2 <= FAR_RADIUS**2
    if np.any(ranks[area] < 0):
        return None
    rain = area & (ranks > 0)
    if not np.any(rain):
        return RainResult("dry")
    near = d2 <= NEAR_RADIUS**2
    zone = "near" if np.any(rain & near) else "far"
    strength = ranks[near if zone == "near" else area].max()

    return RainResult(zone, colors[strength - 1])


@dataclass(frozen=True)
class RainFrame:
    source: str
    settings: dict
    time: int


@dataclass
class RainRegion:
    ranks: np.ndarray
    origin: tuple
    colors: tuple

    def analyze(self, pos):
        x, y, scale = pixel_position(pos)
        # Use the same unwrapped x coordinates when crossing the date line.
        x += round((self.origin[0] + self.ranks.shape[1] / 2 - x) / WORLD) * WORLD
        x, y = x - self.origin[0], y - self.origin[1]
        return analyze_rain(self.ranks, x, y, scale, self.colors)


class RainTiles:
    def __init__(self, config):
        self.config = config

    async def refresh(self, source, pos):
        network = self.config.network
        async with network.bt_tethering_session(
            "rain_alert", wait_lock=True
        ) as connected:
            if not connected:
                return None, None
            frame = await self.latest(source)
            grid = await self.region(frame, pos) if frame is not None else None
            return frame, grid

    async def latest(self, source):
        settings = dict(self.config.G_RAIN_OVERLAY_MAP_CONFIG[source])
        url_key = "past_time_list" if source == "jpn_jma_bousai" else "time_list"
        host, frames = await self.config.api.maptile_with_values.get_rain_timeline(
            settings, url_key
        )
        now = datetime.now(timezone.utc).timestamp()
        frames = [frame for frame in frames if frame["time"] <= now]
        if source == "jpn_jma_bousai":
            frames = [
                frame
                for frame in frames
                if frame["basetime"] == frame["validtime"]
                and "hrpns" in frame["elements"]
            ]
        else:
            settings["host"] = host
        if not frames:
            return None
        frame = frames[-1]
        apply_rain_frame(settings, frame)
        return RainFrame(source, settings, frame["time"])

    async def _load(self, source, settings, tiles):
        network = self.config.network
        files = [
            get_maptile_filename(source, ZOOM, tx, ty, settings) for tx, ty in tiles
        ]
        existing = await asyncio.to_thread(
            lambda: [
                Path(name).is_file() and Path(name).stat().st_size > 0 for name in files
            ]
        )
        missing = [tile for tile, found in zip(tiles, existing) if not found]
        if missing:
            await network.download_maptiles({source: settings}, source, ZOOM, missing)
        await network.wait_for_files(files)
        return await asyncio.gather(
            *(asyncio.to_thread(read_tile, name, source) for name in files)
        )

    async def load(self, frame, tiles):
        arrays = await self._load(frame.source, frame.settings, tiles)
        if frame.source == "rainviewer":
            covered = await self._load(
                "rainviewer_coverage",
                {
                    "url": frame.settings["host"]
                    + "/v2/coverage/0/256/{z}/{x}/{y}/0/0_0.png"
                },
                tiles,
            )
            arrays = [
                (
                    np.where(mask, ranks, -1)
                    if ranks is not None and mask is not None
                    else None
                )
                for ranks, mask in zip(arrays, covered)
            ]
        return dict(zip(tiles, arrays))

    async def region(self, frame, pos):
        x, y, scale = pixel_position(pos)
        tile = (int(x // TILE_SIZE) % 2**ZOOM, int(y // TILE_SIZE))
        arrays = await self.load(frame, [tile])
        center = arrays[tile]
        if center is None:
            return None
        ix, iy = int(x) % TILE_SIZE, int(y) % TILE_SIZE
        colors = palette(frame.source)[1]
        if center[iy, ix] != 0:
            return RainRegion(
                center[iy : iy + 1, ix : ix + 1], (math.floor(x), math.floor(y)), colors
            )

        radius = math.ceil(FAR_RADIUS / scale) + 2
        left, top = math.floor(x) - radius, math.floor(y) - radius
        width = 2 * radius + 1
        xs = range(left // TILE_SIZE, (left + width - 1) // TILE_SIZE + 1)
        ys = range(top // TILE_SIZE, (top + width - 1) // TILE_SIZE + 1)
        tiles = [(tx % 2**ZOOM, ty) for ty in ys if 0 <= ty < 2**ZOOM for tx in xs]
        arrays.update(
            await self.load(frame, [item for item in tiles if item not in arrays])
        )
        ranks = np.full((width, width), -1, dtype=np.int16)
        for ty in ys:
            for tx in xs:
                source = arrays.get((tx % 2**ZOOM, ty))
                if source is None:
                    continue
                x0, y0 = max(left, tx * TILE_SIZE), max(top, ty * TILE_SIZE)
                x1, y1 = min(left + width, (tx + 1) * TILE_SIZE), min(
                    top + width, (ty + 1) * TILE_SIZE
                )
                ranks[y0 - top : y1 - top, x0 - left : x1 - left] = source[
                    y0 - ty * TILE_SIZE : y1 - ty * TILE_SIZE,
                    x0 - tx * TILE_SIZE : x1 - tx * TILE_SIZE,
                ]
        return RainRegion(ranks, (left, top), colors)
