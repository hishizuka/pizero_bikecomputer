"""Shared raw tile cache and asynchronous filesystem/MBTiles access, without Qt."""

import asyncio
import os
import sqlite3
from collections import OrderedDict
from contextlib import closing
from pathlib import Path

from modules.utils.map import get_maptile_filename, get_mbtiles_tile


class TileRepository:
    def __init__(self, config=None, root="maptile", capacity_bytes=4 * 1024 * 1024):
        if capacity_bytes < 0:
            raise ValueError("Tile cache capacity cannot be negative")
        self.config = config
        self.root = Path(root)
        self.capacity_bytes = capacity_bytes
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.revision = 0
        self._lock = asyncio.Lock()

    def invalidate(self):
        self.revision += 1
        self.cache.clear()
        self.cache_bytes = 0

    def _key(self, name, settings, key):
        z, x, y = key
        x %= 2**z
        if settings["use_mbtiles"]:
            return (str(self.root / f"{name}.mbtiles"), z, x, y)
        return (get_maptile_filename(name, z, x, y, settings, root=self.root),)

    def discard(self, name, settings, key):
        """Allow a corrupt or partially written tile to be read again."""
        prefix = self._key(name, settings, key)
        for storage_key in list(self.cache):
            if storage_key[: len(prefix)] == prefix:
                self.cache_bytes -= len(self.cache.pop(storage_key))

    @staticmethod
    def _file_keys(keys):
        result = {}
        for key, path in keys.items():
            try:
                stat = os.stat(path[0])
                result[key] = (*path, stat.st_mtime_ns, stat.st_size)
            except FileNotFoundError:
                result[key] = (*path, None, 0)
        return result

    @staticmethod
    async def _read_file(key):
        try:
            return await asyncio.to_thread(Path(key[0]).read_bytes)
        except FileNotFoundError:
            return None

    @staticmethod
    def _read_mbtiles(keys):
        path = Path(keys[0][0]).resolve()
        with closing(sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)) as db:
            return [get_mbtiles_tile(db, *key[1:]) for key in keys]

    async def load(self, name, settings, keys):
        """Share bytes across renderers; never cache missing or zero-byte tiles."""
        if not keys:
            return {}
        storage_keys = {key: self._key(name, settings, key) for key in keys}
        if not settings["use_mbtiles"]:
            storage_keys = await asyncio.to_thread(self._file_keys, storage_keys)
        async with self._lock:
            revision = self.revision
            cached = {
                key: self.cache[key]
                for key in storage_keys.values()
                if key in self.cache
            }
            missing = list(
                dict.fromkeys(
                    key for key in storage_keys.values() if key not in self.cache
                )
            )
            if missing and settings["use_mbtiles"]:
                values = await asyncio.to_thread(self._read_mbtiles, missing)
            else:
                values = await asyncio.gather(
                    *(self._read_file(key) for key in missing)
                )
            cached.update(zip(missing, values))
            if revision == self.revision:
                for storage_key, data in cached.items():
                    if not data:
                        continue
                    if storage_key not in self.cache:
                        self.cache[storage_key] = data
                        self.cache_bytes += len(data)
                    self.cache.move_to_end(storage_key)
            while self.cache_bytes > self.capacity_bytes:
                _, data = self.cache.popitem(last=False)
                self.cache_bytes -= len(data)
            return {
                key: cached[storage_key]
                for key, storage_key in storage_keys.items()
                if cached[storage_key]
            }

    def has_pending(self, settings, name, zoom, tiles):
        if settings["use_mbtiles"] or self.config.api is None:
            return False
        pending = self.config.api.maptile_with_values.existing_tiles
        return any(
            pending.get(get_maptile_filename(name, zoom, x % 2**zoom, y, settings))
            is False
            for x, y in tiles
            if 0 <= y < 2**zoom
        )

    async def request(self, map_config, name, zoom, tiles, additional_download=False):
        """Use the existing downloader and its shared pending/404 tracking."""
        if map_config[name]["use_mbtiles"] or self.config.api is None:
            return
        coordinates = list(
            dict.fromkeys((x % 2**zoom, y) for x, y in tiles if 0 <= y < 2**zoom)
        )
        if coordinates:
            await self.config.api.maptile_with_values.download_maptiles(
                coordinates,
                map_config,
                name,
                zoom,
                additional_download=additional_download,
            )
