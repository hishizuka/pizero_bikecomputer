"""Tile selection and asynchronous preparation without Qt or GPU access."""

import asyncio
import io
from collections import OrderedDict

import numpy as np
from PIL import Image

from modules.utils.map import (
    get_map_tile_range,
    get_map_tile_coordinates,
    get_map_tile_plan,
)

from .repository import TileRepository
from .policy import tile_zoom

TILE_SIZE = 256


def layer_zoom(view, tile_size):
    return tile_zoom(view.zoom, view.tile_size, tile_size)


def visible_tiles(view, settings):
    bounds = view.bounds
    plan = get_map_tile_plan(
        settings,
        layer_zoom(view, settings.get("tile_size", view.tile_size)),
        bounds,
    )
    if plan is None:
        return []
    zoom = plan[0]
    (x0, x1), (y0, y1) = get_map_tile_range(zoom, bounds)
    return [(zoom, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def download_tiles(view, settings):
    display_zoom = layer_zoom(view, settings.get("tile_size", view.tile_size))
    plan = get_map_tile_plan(settings, display_zoom, view.bounds)
    if plan is None:
        return []
    _, factor, tile_x, tile_y = plan
    return get_map_tile_coordinates(tile_x, tile_y, factor)


def prepare_tile(data, tile_size=TILE_SIZE, name=None):
    """Decode immutable RGB565 or named RGBA overlays; corrupt bytes are retried."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.size != (tile_size, tile_size):
                image = image.resize((tile_size, tile_size), Image.Resampling.NEAREST)
            if name is not None:
                from modules.helper.maptile import conv_image

                converted = conv_image(image, name)
                pixels = (
                    np.array(image.convert("RGBA")) if converted is None else converted
                )
            else:
                if "A" in image.getbands() or "transparency" in image.info:
                    image = image.convert("RGBA")
                    alpha = image.getchannel("A")
                    if alpha.getextrema()[0] < 255:
                        background = Image.new("RGB", image.size, "white")
                        background.paste(image, mask=alpha)
                        image = background
                rgb = np.asarray(image.convert("RGB"), dtype=np.uint16)
                pixels = (
                    ((rgb[..., 0] >> 3) << 11)
                    | ((rgb[..., 1] >> 2) << 5)
                    | (rgb[..., 2] >> 3)
                )
    except OSError:
        return None
    pixels.flags.writeable = False
    return pixels


class LocalTileSource:
    """Bounded CPU cache for filesystem or read-only MBTiles tile data."""

    def __init__(
        self,
        root,
        name,
        ext="png",
        use_mbtiles=False,
        capacity=64,
        tile_size=TILE_SIZE,
        repository=None,
        overlay=False,
    ):
        if capacity < 0:
            raise ValueError("Tile cache capacity cannot be negative")
        self.name = name
        self.capacity = capacity
        self.tile_size = tile_size
        self.overlay = overlay
        self.cache = OrderedDict()
        self.repository = (
            repository if repository is not None else TileRepository(root=root)
        )
        self.revision = self.repository.revision
        self.request_key = None
        self.settings = {"ext": ext, "use_mbtiles": use_mbtiles}
        self.namespace = None

    async def load(self, keys):
        """Return a frame's prepared tiles; missing tiles are retried next time."""
        if self.revision != self.repository.revision:
            self.cache.clear()
            self.revision = self.repository.revision
        revision = self.revision
        result = {}
        missing = []
        for key in dict.fromkeys(keys):
            if key in self.cache:
                result[key] = self.cache[key]
                self.cache.move_to_end(key)
            else:
                missing.append(key)
        data = await self.repository.load(self.name, self.settings, missing)
        name = self.name if self.overlay else None
        loaded = await asyncio.gather(
            *(
                asyncio.to_thread(prepare_tile, value, self.tile_size, name)
                for value in data.values()
            )
        )
        for key, pixels in zip(data, loaded):
            if pixels is None:
                self.repository.discard(self.name, self.settings, key)
                continue
            result[key] = pixels
            if revision != self.repository.revision:
                continue
            self.cache[key] = pixels
            self.cache.move_to_end(key)
            while len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
        return result
