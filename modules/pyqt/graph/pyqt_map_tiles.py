import io
from collections import OrderedDict
import shutil
import sqlite3
import tempfile
import time

import numpy as np
from PIL import Image, ImageEnhance

from modules._qt_qtwidgets import QT_COMPOSITION_MODE_DARKEN, pg
from modules.helper.maptile import conv_image
from modules.utils.cmd import exec_cmd
from modules.utils.geo import get_mod_lat
from modules.utils.map import (
    get_lon_lat_from_tile_xy,
    get_maptile_filename,
    get_tilexy_and_xy_in_tile,
)


class MapTileMixin:
    pre_zoomlevel = {}
    drawn_tile = {}
    _cached_tiles = {}
    _tile_view_signature = {}
    _tile_items = {}
    _tile_draw_pending = {}
    _tile_item_lru = OrderedDict()
    tile_item_lru_max = 384
    tile_batch_size_main = 3
    tile_batch_size_overlay = 2
    tile_modify_mode = 0
    tile_didder_pallete = {
        2: "000000 FFFFFF",
        8: None,
        64: None,
        #64: "000000 FF0000 00FF00 0000FF 00FFFF FF00FF FFFF00 FFFFFF",
    }

    def get_geo_area(self, x, y):
        if np.isnan(x) or np.isnan(y):
            return np.nan, np.nan

        tile_size = self.config.G_MAP_CONFIG[self.config.G_MAP]["tile_size"]

        tile_x, tile_y, _, _ = get_tilexy_and_xy_in_tile(
            self.zoomlevel,
            x,
            y,
            tile_size,
        )
        pos_x0, pos_y0 = get_lon_lat_from_tile_xy(self.zoomlevel, tile_x, tile_y)
        pos_x1, pos_y1 = get_lon_lat_from_tile_xy(self.zoomlevel, tile_x + 1, tile_y + 1)
        return (
            abs(pos_x1 - pos_x0) / tile_size * self.width(),
            abs(pos_y1 - pos_y0) / tile_size * self.height(),
        )

    @staticmethod
    def _palette_rgb_multilevel(levels=2):
        if levels < 2:
            return None

        vals = [round(i * 255 / (levels - 1)) for i in range(levels)]

        def hex2(v: int) -> str:
            return f"{v:02X}"

        colors = []
        for r in vals:
            for g in vals:
                for b in vals:
                    colors.append(f"{hex2(r)}{hex2(g)}{hex2(b)}")

        return " ".join(colors)

    def _setup_tile_dither_palette(self):
        if not shutil.which("didder"):
            return

        palette8 = self._palette_rgb_multilevel(2)
        palette64 = self._palette_rgb_multilevel(4)
        if palette8:
            self.tile_didder_pallete[8] = palette8
        if palette64:
            self.tile_didder_pallete[64] = palette64

    def _init_tile_runtime_state(self):
        if not isinstance(self._tile_view_signature, dict):
            self._tile_view_signature = {}
        if not isinstance(self._tile_items, dict):
            self._tile_items = {}
        if not isinstance(self._tile_draw_pending, dict):
            self._tile_draw_pending = {}
        if not isinstance(self._tile_item_lru, OrderedDict):
            self._tile_item_lru = OrderedDict()

    def _get_map_tile_items(self, map_name):
        items = self._tile_items.get(map_name)
        if items is None:
            items = {}
            self._tile_items[map_name] = items
        return items

    def _get_tile_pending_state(self, map_name):
        self._init_tile_runtime_state()
        state = self._tile_draw_pending.get(map_name)
        if state is None:
            state = {
                "signature": None,
                "queue": [],
                "key_set": set(),
                "expand_keys": {},
            }
            self._tile_draw_pending[map_name] = state
        return state

    def _reset_tile_pending_state(self, map_name, signature=None):
        self._tile_draw_pending[map_name] = {
            "signature": signature,
            "queue": [],
            "key_set": set(),
            "expand_keys": {},
        }

    def _clear_tile_pending_state(self, map_name=None):
        self._init_tile_runtime_state()
        if map_name is None:
            self._tile_draw_pending = {}
            return
        self._tile_draw_pending.pop(map_name, None)

    def _has_tile_batch_pending(self):
        self._init_tile_runtime_state()
        for state in self._tile_draw_pending.values():
            if state.get("queue"):
                return True
        return False

    def _mark_tile_drawn(self, map_name, z, x, y):
        self.drawn_tile.setdefault(map_name, {})
        self.drawn_tile[map_name].setdefault(z, {})
        self.drawn_tile[map_name][z][self._drawn_tile_key(x, y)] = True

    @staticmethod
    def _build_tile_view_signature(
        z,
        z_draw,
        z_conv_factor,
        tile_x,
        tile_y,
        expand,
        tile_modify_mode,
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
            expand,
            tile_modify_mode,
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

    def _remove_plot_item_safely(self, item):
        try:
            self.plot.removeItem(item)
        except Exception:
            pass

    def _is_visible_tile_drawn(self, map_name, z, tile_x, tile_y):
        map_drawn = self.drawn_tile.get(map_name, {}).get(z, {})
        if not map_drawn:
            return False
        for i, j in self._iter_visible_tile_coords(tile_x, tile_y):
            if self._drawn_tile_key(i, j) not in map_drawn:
                return False
        return True

    def _sync_visible_tile_items(self, map_name, z, tile_x, tile_y):
        self._init_tile_runtime_state()
        visible_keys = {
            (map_name, z, i, j)
            for i, j in self._iter_visible_tile_coords(tile_x, tile_y)
        }
        map_items = self._get_map_tile_items(map_name)

        for (item_z, item_x, item_y), item in list(map_items.items()):
            item_key = (map_name, item_z, item_x, item_y)
            if item_key in visible_keys:
                continue
            self._remove_plot_item_safely(item)
            del map_items[(item_z, item_x, item_y)]
            self._tile_item_lru.pop(item_key, None)

        map_drawn = {}
        for item_z, item_x, item_y in map_items.keys():
            if item_z != z:
                continue
            map_drawn[self._drawn_tile_key(item_x, item_y)] = True

        self.drawn_tile.setdefault(map_name, {})
        for map_zoom in list(self.drawn_tile[map_name].keys()):
            if map_zoom != z:
                del self.drawn_tile[map_name][map_zoom]
        self.drawn_tile[map_name][z] = map_drawn
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

            self._tile_item_lru.pop(evict_key, None)
            map_name, z, x, y = evict_key
            map_items = self._tile_items.get(map_name, {})
            item = map_items.pop((z, x, y), None)
            if item is not None:
                self._remove_plot_item_safely(item)
            map_drawn = self.drawn_tile.get(map_name, {}).get(z)
            if map_drawn is not None:
                map_drawn.pop(self._drawn_tile_key(x, y), None)

    def _cleanup_tile_runtime_cache(self, active_map_names):
        self._init_tile_runtime_state()
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
        self._init_tile_runtime_state()

        if map_name is None:
            map_names = list(self._tile_items.keys())
        else:
            map_names = [map_name]

        for target_map in map_names:
            map_items = self._tile_items.get(target_map, {})
            for item in list(map_items.values()):
                self._remove_plot_item_safely(item)
            if target_map in self._tile_items:
                self._tile_items[target_map] = {}
            self._tile_view_signature.pop(target_map, None)
            self._clear_tile_pending_state(target_map)
            if target_map in self.drawn_tile:
                self.drawn_tile[target_map] = {}

        if map_name is None:
            self._tile_item_lru.clear()
            self._clear_tile_pending_state()
        else:
            for item_key in list(self._tile_item_lru.keys()):
                if item_key[0] == map_name:
                    self._tile_item_lru.pop(item_key, None)

    async def draw_map_tile_by_overlay(
        self,
        map_config,
        map_name,
        z,
        p0,
        p1,
        overlay=False,
        expand=False,
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
        z_draw, z_conv_factor, tile_x, tile_y = self.init_draw_map(
            map_config, map_name, z, p0, p1, expand, tile_size
        )
        self._init_tile_runtime_state()

        tile_modify_mode = (
            self.tile_modify_mode if map_config == self.config.G_MAP_CONFIG else 0
        )
        view_signature = self._build_tile_view_signature(
            z,
            z_draw,
            z_conv_factor,
            tile_x,
            tile_y,
            expand,
            tile_modify_mode,
            use_mbtiles,
        )
        visible_item_keys = self._sync_visible_tile_items(map_name, z, tile_x, tile_y)
        previous_signature = self._tile_view_signature.get(map_name)
        pending_state = self._get_tile_pending_state(map_name)
        if pending_state["signature"] != view_signature:
            self._reset_tile_pending_state(map_name, signature=view_signature)
            pending_state = self._get_tile_pending_state(map_name)
        if (
            previous_signature == view_signature
            and self._is_visible_tile_drawn(map_name, z, tile_x, tile_y)
            and not pending_state["queue"]
        ):
            self._touch_visible_item_keys(visible_item_keys)
            self._evict_tile_items_by_lru(protected_keys=visible_item_keys)
            return False

        # Use cached tile info only when the viewport signature exactly matches.
        cached = self._cached_tiles.get(map_name)
        if (
            cached
            and cached.get("z") == z
            and cached.get("z_draw") == z_draw
            and cached.get("z_conv_factor") == z_conv_factor
            and cached.get("expand") == expand
            and tuple(cached.get("tile_x", ())) == tuple(tile_x)
            and tuple(cached.get("tile_y", ())) == tuple(tile_y)
        ):
            tiles = cached["tiles"]
        else:
            tiles = self.get_tiles_for_drawing(tile_x, tile_y, z_conv_factor, expand)
            self._cached_tiles[map_name] = {
                "z": z,
                "z_draw": z_draw,
                "tiles": tiles,
                "tile_x": list(tile_x),
                "tile_y": list(tile_y),
                "z_conv_factor": z_conv_factor,
                "expand": expand,
            }

        if not use_mbtiles:
            download_start = time.perf_counter()
            await self.maptile_with_values.download_maptiles(
                tiles,
                map_config,
                map_name,
                z_draw,
                additional_download=True,
            )
            tile_download_elapsed_ms += (time.perf_counter() - download_start) * 1000.0
            tile_download_calls += 1

        if use_mbtiles:
            self.con = sqlite3.connect(
                f"file:./maptile/{map_name}.mbtiles?mode=ro", uri=True
            )
            self.cur = self.con.cursor()

        try:
            check_start = time.perf_counter()
            add_keys, expand_keys = self.check_drawn_tile(
                use_mbtiles,
                map_config,
                map_name,
                z,
                z_draw,
                z_conv_factor,
                tile_x,
                tile_y,
                expand,
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
            batch_size = max(1, int(batch_size))
            draw_keys = pending_state["queue"][:batch_size]
            pending_state["queue"] = pending_state["queue"][batch_size:]
            for key in draw_keys:
                pending_state["key_set"].discard(key)

            map_items = self._get_map_tile_items(map_name)
            w_h = int(tile_size / z_conv_factor) if expand else 0
            drawn_any = False
            for keys in draw_keys:
                if (z, keys[0], keys[1]) in map_items:
                    self._mark_tile_drawn(map_name, z, keys[0], keys[1])
                    pending_state["expand_keys"].pop(keys, None)
                    tile_reused_count += 1
                    continue

                x, y = (
                    keys[0:2]
                    if not expand
                    else pending_state["expand_keys"].get(keys, keys)[0:2]
                )

                try:
                    img_file = self.get_image_file(
                        use_mbtiles, map_config, map_name, z_draw, x, y
                    )

                    io_start = time.perf_counter()
                    if not expand:
                        img_pil = Image.open(img_file).convert("RGBA")
                    else:
                        expand_val = pending_state["expand_keys"].get(keys)
                        if expand_val is None:
                            pending_state["queue"].append(keys)
                            pending_state["key_set"].add(keys)
                            continue
                        x_start, y_start = int(w_h * expand_val[2]), int(
                            w_h * expand_val[3]
                        )
                        img_pil = (
                            Image.open(img_file)
                            .crop((x_start, y_start, x_start + w_h, y_start + w_h))
                            .convert("RGBA")
                        )
                    tile_io_elapsed_ms += (time.perf_counter() - io_start) * 1000.0

                    if (
                        map_config == self.config.G_MAP_CONFIG
                        and self.tile_modify_mode != 0
                    ):
                        img_pil = self.enhance_image(img_pil)

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
                    imgitem.setZValue(-100)
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
                except Exception:
                    # Retry the tile later instead of marking it as drawn.
                    pending_state["queue"].append(keys)
                    pending_state["key_set"].add(keys)
                    tile_retry_count += 1

            self._touch_visible_item_keys(visible_item_keys)

            self._tile_view_signature[map_name] = view_signature
            self._evict_tile_items_by_lru(protected_keys=visible_item_keys)
            return drawn_any
        finally:
            record_tile_perf = getattr(self, "_record_perf_map_tile_breakdown", None)
            if callable(record_tile_perf):
                record_tile_perf(
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
            if use_mbtiles:
                self.cur.close()
                self.con.close()

    @staticmethod
    def init_draw_map(map_config, map_name, z, p0, p1, expand, tile_size):
        z_draw = z
        z_conv_factor = 1
        if expand:
            if z > map_config[map_name]["max_zoomlevel"]:
                z_draw = map_config[map_name]["max_zoomlevel"]
            elif z < map_config[map_name]["min_zoomlevel"]:
                z_draw = map_config[map_name]["min_zoomlevel"]
            z_conv_factor = 2 ** (z - z_draw)

        t0 = get_tilexy_and_xy_in_tile(z, p0["x"], p0["y"], tile_size)
        t1 = get_tilexy_and_xy_in_tile(z, p1["x"], p1["y"], tile_size)
        tile_x = sorted([t0[0], t1[0]])
        tile_y = sorted([t0[1], t1[1]])
        return z_draw, z_conv_factor, tile_x, tile_y

    @staticmethod
    def get_tiles_for_drawing(tile_x, tile_y, z_conv_factor, expand):
        tiles = list(MapTileMixin._iter_visible_tile_coords(tile_x, tile_y))
        tiles += [(i, j) for i in (tile_x[0] - 1, tile_x[1] + 1) for j in range(tile_y[0] - 1, tile_y[1] + 2)]
        tiles += [(i, j) for i in range(tile_x[0], tile_x[1] + 1) for j in (tile_y[0] - 1, tile_y[1] + 1)]

        if expand and z_conv_factor > 1:
            tiles = list({(i // z_conv_factor, j // z_conv_factor) for i, j in tiles})

        return tiles

    def check_drawn_tile(
        self,
        use_mbtiles,
        map_config,
        map_name,
        z,
        z_draw,
        z_conv_factor,
        tile_x,
        tile_y,
        expand,
        skip_keys=None,
    ):
        if skip_keys is None:
            skip_keys = set()
        add_keys = []
        expand_keys = {}
        map_settings = map_config[map_name]
        drawn_tiles = self.drawn_tile.get(map_name, {}).get(z, {})

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

            if not self.check_tile(
                use_mbtiles,
                map_name,
                z_draw,
                exist_tile_key,
                map_settings,
            ):
                continue

            add_keys.append((i, j))
            if expand:
                expand_keys[(i, j)] = (pixel_x, pixel_y, x_start, y_start)

        return add_keys, expand_keys

    def check_tile(self, use_mbtiles, map_name, z_draw, key, map_settings):
        if not use_mbtiles:
            filename = get_maptile_filename(map_name, z_draw, *key, map_settings)
            return self.maptile_with_values.check_existing_tiles(filename)
        sql = (
            "select count(*) from tiles where "
            f"zoom_level={z_draw} and tile_column={key[0]} "
            f"and tile_row={2**z_draw - 1 - key[1]}"
        )
        return (self.cur.execute(sql).fetchone())[0] == 1

    def get_image_file(self, use_mbtiles, map_config, map_name, z_draw, x, y):
        if not use_mbtiles:
            map_settings = map_config[map_name]
            return get_maptile_filename(map_name, z_draw, x, y, map_settings)
        sql = (
            "select tile_data from tiles where "
            f"zoom_level={z_draw} and tile_column={x} and tile_row={2**z_draw - 1 - y}"
        )
        return io.BytesIO((self.cur.execute(sql).fetchone())[0])

    def enhance_image(self, img_pil):
        # 0: None
        # 1: pil
        # 2: didder
        # 3: pil + didder

        if self.tile_modify_mode in [1, 3]:
            img_pil = ImageEnhance.Contrast(img_pil).enhance(2.0)

        with tempfile.NamedTemporaryFile(suffix=".png") as tmp_file:
            filename = tmp_file.name

            if self.tile_modify_mode in [2, 3] and shutil.which("didder"):
                img_pil.save(filename)
                exec_cmd(
                    [
                        "didder",
                        "-i",
                        filename,
                        "-o",
                        filename,
                        "--strength",
                        "0.8",
                        "--palette",
                        self.tile_didder_pallete[self.config.display.color],
                        "edm",
                        "--serpentine",
                        "FloydSteinberg",
                    ],
                    cmd_print=False,
                )
                img_pil = Image.open(filename).convert("RGBA")

        return img_pil

    def modify_map_tile(self):
        if self.tile_modify_mode == 3:
            self.tile_modify_mode = 0
        else:
            self.tile_modify_mode += 1
        self.config.display.screen_flash_short()
        self.reset_map()
