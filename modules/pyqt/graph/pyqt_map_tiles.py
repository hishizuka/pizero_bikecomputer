import io
import time
from collections import OrderedDict

import numpy as np
from PIL import Image

from modules.qt._qt_qtwidgets import QT_COMPOSITION_MODE_DARKEN, pg
from modules.helper.maptile import conv_image
from modules.map.style import MAP_LAYER_ORDER
from modules.utils.geo import get_mod_lat
from modules.utils.map import (
    get_lon_lat_from_tile_xy,
    get_map_geo_area,
    get_map_tile_plan,
    get_map_tile_coordinates,
)


class MapTileMixin:
    tile_item_lru_max = 384
    tile_parent_cache_max = 4
    tile_batch_size_main = 3
    tile_batch_size_overlay = 2

    def get_geo_area(self, x, y):
        if np.isnan(x) or np.isnan(y):
            return np.nan, np.nan

        return get_map_geo_area(
            self.zoomlevel,
            x,
            y,
            self.width(),
            self.height(),
            self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"],
        )

    def _load_tile_image(self, data, key, map_name, expanded):
        cache_key = (map_name, *key)
        cached = self._tile_parent_cache.pop(cache_key, None) if expanded else None
        if cached is not None and cached[0] is data:
            image = cached[1]
        else:
            with Image.open(io.BytesIO(data)) as source:
                image = source.copy()
        if expanded:
            self._tile_parent_cache[cache_key] = (data, image)
            while len(self._tile_parent_cache) > self.tile_parent_cache_max:
                self._tile_parent_cache.popitem(last=False)
        return image

    def _init_tile_runtime_state(self):
        self.pre_zoomlevel = {}
        self.drawn_tile = {}
        self._cached_tiles = {}
        self._tile_view_signature = {}
        self._tile_items = {}
        self._tile_draw_pending = {}
        self._tile_item_lru = OrderedDict()
        self._tile_parent_cache = OrderedDict()

    def _get_map_tile_items(self, map_name):
        return self._tile_items.setdefault(map_name, {})

    def _get_tile_pending_state(self, map_name, signature):
        state = self._tile_draw_pending.get(map_name)
        if state is None or state["signature"] != signature:
            state = {
                "signature": signature,
                "queue": [],
                "key_set": set(),
                "expand_keys": {},
            }
            self._tile_draw_pending[map_name] = state
        return state

    def _has_tile_batch_pending(self):
        return any(state["queue"] for state in self._tile_draw_pending.values())

    def _mark_tile_drawn(self, map_name, z, x, y):
        self.drawn_tile.setdefault(map_name, {}).setdefault(z, {})[
            self._drawn_tile_key(x, y)
        ] = True

    @staticmethod
    def _build_tile_view_signature(
        z,
        z_draw,
        z_conv_factor,
        tile_x,
        tile_y,
        use_mbtiles,
    ):
        return (
            z,
            z_draw,
            z_conv_factor,
            tile_x[0],
            tile_x[1],
            tile_y[0],
            tile_y[1],
            bool(use_mbtiles),
        )

    @staticmethod
    def _iter_visible_tile_coords(tile_x, tile_y):
        for i in range(tile_x[0], tile_x[1] + 1):
            for j in range(tile_y[0], tile_y[1] + 1):
                yield i, j

    @staticmethod
    def _drawn_tile_key(x, y):
        return f"{x}-{y}"

    def _is_visible_tile_drawn(self, map_name, z, tile_x, tile_y):
        map_drawn = self.drawn_tile.get(map_name, {}).get(z, {})
        if not map_drawn:
            return False
        for i, j in self._iter_visible_tile_coords(tile_x, tile_y):
            if self._drawn_tile_key(i, j) not in map_drawn:
                return False
        return True

    def _sync_visible_tile_items(self, map_name, z, tile_x, tile_y):
        visible_keys = {
            (map_name, z, i, j)
            for i, j in self._iter_visible_tile_coords(tile_x, tile_y)
        }
        map_items = self._get_map_tile_items(map_name)

        for (item_z, item_x, item_y), item in list(map_items.items()):
            item_key = (map_name, item_z, item_x, item_y)
            if item_key in visible_keys:
                continue
            self.plot.removeItem(item)
            del map_items[(item_z, item_x, item_y)]
            del self._tile_item_lru[item_key]

        map_drawn = {}
        for item_z, item_x, item_y in map_items.keys():
            if item_z != z:
                continue
            map_drawn[self._drawn_tile_key(item_x, item_y)] = True

        self.drawn_tile[map_name] = {z: map_drawn}
        return visible_keys

    def _touch_tile_item_lru(self, item_key):
        self._tile_item_lru.pop(item_key, None)
        self._tile_item_lru[item_key] = True

    def _touch_visible_item_keys(self, visible_item_keys):
        for item_key in visible_item_keys:
            if item_key in self._tile_item_lru:
                self._touch_tile_item_lru(item_key)

    def _evict_tile_items_by_lru(self, protected_keys=None):
        if protected_keys is None:
            protected_keys = set()

        while len(self._tile_item_lru) > self.tile_item_lru_max:
            evict_key = None
            for item_key in self._tile_item_lru.keys():
                if item_key in protected_keys:
                    continue
                evict_key = item_key
                break
            if evict_key is None:
                break

            del self._tile_item_lru[evict_key]
            map_name, z, x, y = evict_key
            item = self._tile_items[map_name].pop((z, x, y))
            self.plot.removeItem(item)
            del self.drawn_tile[map_name][z][self._drawn_tile_key(x, y)]

    def _cleanup_tile_runtime_cache(self, active_map_names):
        active = set(active_map_names)

        for map_name in list(self._tile_items.keys()):
            if map_name in active:
                continue
            self._clear_tile_items(map_name)

        for map_name in list(self._tile_view_signature.keys()):
            if map_name not in active:
                del self._tile_view_signature[map_name]
        for map_name in list(self._tile_draw_pending.keys()):
            if map_name not in active:
                del self._tile_draw_pending[map_name]

    def _clear_tile_items(self, map_name=None):
        if map_name is None:
            map_names = list(self._tile_items.keys())
        else:
            map_names = [map_name]

        self._tile_parent_cache = OrderedDict(
            (key, image)
            for key, image in self._tile_parent_cache.items()
            if map_name is not None and key[0] != map_name
        )

        for target_map in map_names:
            map_items = self._tile_items.get(target_map, {})
            for item in map_items.values():
                self.plot.removeItem(item)
            if target_map in self._tile_items:
                self._tile_items[target_map] = {}
            self._tile_view_signature.pop(target_map, None)
            self._tile_draw_pending.pop(target_map, None)
            if target_map in self.drawn_tile:
                self.drawn_tile[target_map] = {}

        if map_name is None:
            self._tile_item_lru.clear()
            self._tile_draw_pending.clear()
        else:
            for item_key in list(self._tile_item_lru.keys()):
                if item_key[0] == map_name:
                    del self._tile_item_lru[item_key]

    async def draw_map_tile_by_overlay(
        self,
        map_config,
        map_name,
        z,
        p0,
        p1,
        overlay=False,
        use_mbtiles=False,
    ):
        tile_download_elapsed_ms = 0.0
        tile_download_calls = 0
        tile_check_elapsed_ms = 0.0
        tile_io_elapsed_ms = 0.0
        tile_conv_elapsed_ms = 0.0
        tile_imgitem_elapsed_ms = 0.0
        tile_plot_elapsed_ms = 0.0
        tile_drawn_count = 0
        tile_reused_count = 0
        tile_retry_count = 0

        tile_size = map_config[map_name]["tile_size"]

        # Always resolve the current viewport first.
        draw_params = self.init_draw_map(map_config, map_name, z, p0, p1, tile_size)
        if draw_params is None:
            self.pre_zoomlevel[map_name] = z
            return False
        z_draw, z_conv_factor, tile_x, tile_y = draw_params
        expand = z_conv_factor > 1

        view_signature = self._build_tile_view_signature(
            z,
            z_draw,
            z_conv_factor,
            tile_x,
            tile_y,
            use_mbtiles,
        )
        visible_item_keys = self._sync_visible_tile_items(map_name, z, tile_x, tile_y)
        previous_signature = self._tile_view_signature.get(map_name)
        pending_state = self._get_tile_pending_state(map_name, view_signature)
        if (
            previous_signature == view_signature
            and self._is_visible_tile_drawn(map_name, z, tile_x, tile_y)
            and not pending_state["queue"]
        ):
            self._touch_visible_item_keys(visible_item_keys)
            self._evict_tile_items_by_lru(protected_keys=visible_item_keys)
            return False

        tiles = self._get_tiles_for_view(map_name, z, draw_params)

        repository = self.config.map.tiles
        map_settings = dict(map_config[map_name])
        download_start = time.perf_counter()
        await repository.request(
            map_config, map_name, z_draw, tiles, additional_download=True
        )
        tile_download_elapsed_ms += (time.perf_counter() - download_start) * 1000.0
        tile_download_calls += int(not use_mbtiles)

        source_keys = [
            (z_draw, i // z_conv_factor, j // z_conv_factor)
            for i, j in self._iter_visible_tile_coords(tile_x, tile_y)
        ]
        io_start = time.perf_counter()
        raw_tiles = await repository.load(map_name, map_settings, source_keys)
        tile_io_elapsed_ms += (time.perf_counter() - io_start) * 1000.0

        try:
            check_start = time.perf_counter()
            add_keys, expand_keys = self.check_drawn_tile(
                map_name,
                z,
                z_draw,
                z_conv_factor,
                tile_x,
                tile_y,
                raw_tiles,
                skip_keys=pending_state["key_set"],
            )
            tile_check_elapsed_ms += (time.perf_counter() - check_start) * 1000.0
            if add_keys:
                pending_state["queue"].extend(add_keys)
                pending_state["key_set"].update(add_keys)
                pending_state["expand_keys"].update(expand_keys)

            self.pre_zoomlevel[map_name] = z
            if not pending_state["queue"]:
                self._tile_view_signature[map_name] = view_signature
                self._touch_visible_item_keys(visible_item_keys)
                self._evict_tile_items_by_lru(protected_keys=visible_item_keys)
                return False

            batch_size = (
                self.tile_batch_size_overlay if overlay else self.tile_batch_size_main
            )
            draw_keys = pending_state["queue"][:batch_size]
            pending_state["queue"] = pending_state["queue"][batch_size:]
            for key in draw_keys:
                pending_state["key_set"].discard(key)

            map_items = self._get_map_tile_items(map_name)
            drawn_any = False
            for keys in draw_keys:
                if (z, keys[0], keys[1]) in map_items:
                    self._mark_tile_drawn(map_name, z, keys[0], keys[1])
                    pending_state["expand_keys"].pop(keys, None)
                    tile_reused_count += 1
                    continue

                x, y = (
                    keys[0:2] if not expand else pending_state["expand_keys"][keys][0:2]
                )

                try:
                    io_start = time.perf_counter()
                    source_key = (z_draw, x, y)
                    data = raw_tiles.get(source_key)
                    if data is None:
                        raise FileNotFoundError(source_key)
                    img_pil = self._load_tile_image(data, source_key, map_name, expand)
                    if expand:
                        expand_val = pending_state["expand_keys"][keys]
                        img_pil = img_pil.crop(
                            self.get_tile_crop_box(
                                tile_size, z_conv_factor, *expand_val[2:]
                            )
                        )
                    if not map_name.startswith(("jpn_scw", "jpn_jma_bousai")):
                        img_pil = img_pil.convert("RGBA")
                    tile_io_elapsed_ms += (time.perf_counter() - io_start) * 1000.0

                    conv_start = time.perf_counter()
                    if map_name.startswith(("jpn_scw", "jpn_jma_bousai")):
                        imgarray = conv_image(img_pil, map_name)
                    else:
                        imgarray = np.asarray(img_pil)
                    tile_conv_elapsed_ms += (time.perf_counter() - conv_start) * 1000.0

                    imgitem_start = time.perf_counter()
                    imgarray = np.rot90(imgarray, -1)
                    imgitem = pg.ImageItem(imgarray, levels=(0, 255))
                    if overlay:
                        imgitem.setCompositionMode(QT_COMPOSITION_MODE_DARKEN)
                    tile_imgitem_elapsed_ms += (
                        time.perf_counter() - imgitem_start
                    ) * 1000.0

                    imgarray_min_x, imgarray_max_y = get_lon_lat_from_tile_xy(
                        z, keys[0], keys[1]
                    )
                    imgarray_max_x, imgarray_min_y = get_lon_lat_from_tile_xy(
                        z, keys[0] + 1, keys[1] + 1
                    )

                    plot_start = time.perf_counter()
                    self.plot.addItem(imgitem)
                    imgitem.setZValue(MAP_LAYER_ORDER["overlay" if overlay else "base"])
                    imgitem.setRect(
                        pg.QtCore.QRectF(
                            imgarray_min_x,
                            get_mod_lat(imgarray_min_y),
                            imgarray_max_x - imgarray_min_x,
                            get_mod_lat(imgarray_max_y) - get_mod_lat(imgarray_min_y),
                        )
                    )
                    tile_plot_elapsed_ms += (time.perf_counter() - plot_start) * 1000.0
                    map_items[(z, keys[0], keys[1])] = imgitem
                    item_key = (map_name, z, keys[0], keys[1])
                    self._touch_tile_item_lru(item_key)
                    self._mark_tile_drawn(map_name, z, keys[0], keys[1])
                    pending_state["expand_keys"].pop(keys, None)
                    tile_drawn_count += 1
                    drawn_any = True
                except (OSError, ValueError):
                    repository.discard(map_name, map_settings, (z_draw, x, y))
                    self._tile_parent_cache.pop((map_name, z_draw, x, y), None)
                    # Retry the tile later instead of marking it as drawn.
                    pending_state["queue"].append(keys)
                    pending_state["key_set"].add(keys)
                    tile_retry_count += 1

            self._touch_visible_item_keys(visible_item_keys)

            self._tile_view_signature[map_name] = view_signature
            self._evict_tile_items_by_lru(protected_keys=visible_item_keys)
            return drawn_any
        finally:
            self._record_perf_map_tile_breakdown(
                download_ms=tile_download_elapsed_ms,
                download_calls=tile_download_calls,
                check_ms=tile_check_elapsed_ms,
                io_ms=tile_io_elapsed_ms,
                conv_ms=tile_conv_elapsed_ms,
                imgitem_ms=tile_imgitem_elapsed_ms,
                plot_ms=tile_plot_elapsed_ms,
                drawn_count=tile_drawn_count,
                reused_count=tile_reused_count,
                retry_count=tile_retry_count,
            )

    @staticmethod
    def get_tile_crop_box(tile_size, z_conv_factor, offset_x, offset_y):
        width = tile_size / z_conv_factor
        x, y = int(width * offset_x), int(width * offset_y)
        # A display tile can cover less than one source pixel at high zoom.
        size = max(1, int(width))
        return x, y, x + size, y + size

    @staticmethod
    def init_draw_map(map_config, map_name, z, p0, p1, tile_size):
        return get_map_tile_plan(
            map_config[map_name], z, (p0["x"], p1["x"], p0["y"], p1["y"])
        )

    get_tiles_for_drawing = staticmethod(get_map_tile_coordinates)

    def _get_tiles_for_view(self, map_name, z, draw_params):
        z_draw, z_conv_factor, tile_x, tile_y = draw_params
        cached = self._cached_tiles.get(map_name)
        if cached is None or (
            cached["z"],
            cached["z_draw"],
            cached["z_conv_factor"],
            cached["tile_x"],
            cached["tile_y"],
        ) != (z, z_draw, z_conv_factor, tile_x, tile_y):
            cached = {
                "z": z,
                "z_draw": z_draw,
                "z_conv_factor": z_conv_factor,
                "tile_x": tile_x,
                "tile_y": tile_y,
                "tiles": self.get_tiles_for_drawing(tile_x, tile_y, z_conv_factor),
            }
            self._cached_tiles[map_name] = cached
        return cached["tiles"]

    def check_drawn_tile(
        self,
        map_name,
        z,
        z_draw,
        z_conv_factor,
        tile_x,
        tile_y,
        available,
        skip_keys=None,
    ):
        if skip_keys is None:
            skip_keys = set()
        add_keys = []
        expand_keys = {}
        drawn_tiles = self.drawn_tile.get(map_name, {}).get(z, {})
        expand = z_conv_factor > 1

        for i, j in self._iter_visible_tile_coords(tile_x, tile_y):
            drawn_tile_key = self._drawn_tile_key(i, j)
            if drawn_tile_key in drawn_tiles:
                continue
            if (i, j) in skip_keys:
                continue

            exist_tile_key = (i, j)
            pixel_x = x_start = pixel_y = y_start = 0
            if expand:
                pixel_x, x_start = divmod(i, z_conv_factor)
                pixel_y, y_start = divmod(j, z_conv_factor)
                exist_tile_key = (pixel_x, pixel_y)

            if (z_draw, *exist_tile_key) not in available:
                continue

            add_keys.append((i, j))
            if expand:
                expand_keys[(i, j)] = (pixel_x, pixel_y, x_start, y_start)

        return add_keys, expand_keys
