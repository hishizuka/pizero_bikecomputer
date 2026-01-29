import io
import shutil
import sqlite3
import tempfile

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
            abs(pos_x1 - pos_x0) / tile_size * (self.width() * self.map_cuesheet_ratio),
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
        tile_size = map_config[map_name]["tile_size"]

        # Use cached tile info if available
        cached = self._cached_tiles.get(map_name)
        if cached and cached["z"] == z:
            z_draw = cached["z_draw"]
            z_conv_factor = cached["z_conv_factor"]
            tile_x = cached["tile_x"]
            tile_y = cached["tile_y"]
            tiles = cached["tiles"]
        else:
            # Resolve tile range and effective zoom level once.
            z_draw, z_conv_factor, tile_x, tile_y = self.init_draw_map(
                map_config, map_name, z, p0, p1, expand, tile_size
            )
            tiles = self.get_tiles_for_drawing(tile_x, tile_y, z_conv_factor, expand)

        if not use_mbtiles:
            await self.maptile_with_values.download_maptiles(
                tiles,
                map_config,
                map_name,
                z_draw,
                additional_download=True,
            )

        if use_mbtiles:
            self.con = sqlite3.connect(
                f"file:./maptile/{map_name}.mbtiles?mode=ro", uri=True
            )
            self.cur = self.con.cursor()

        draw_flag, add_keys, expand_keys = self.check_drawn_tile(
            use_mbtiles,
            map_config,
            map_name,
            z,
            z_draw,
            z_conv_factor,
            tile_x,
            tile_y,
            expand,
        )

        self.pre_zoomlevel[map_name] = z
        if not draw_flag:
            if use_mbtiles:
                self.cur.close()
                self.con.close()
            return False

        w_h = int(tile_size / z_conv_factor) if expand else 0
        for keys in add_keys:
            x, y = keys[0:2] if not expand else expand_keys[keys][0:2]
            img_file = self.get_image_file(
                use_mbtiles, map_config, map_name, z_draw, x, y
            )

            # Profiling: Image I/O
            if not expand:
                img_pil = Image.open(img_file).convert("RGBA")
            else:
                x_start, y_start = int(w_h * expand_keys[keys][2]), int(
                    w_h * expand_keys[keys][3]
                )
                img_pil = (
                    Image.open(img_file)
                    .crop((x_start, y_start, x_start + w_h, y_start + w_h))
                    .convert("RGBA")
                )

            if map_config == self.config.G_MAP_CONFIG and self.tile_modify_mode != 0:
                img_pil = self.enhance_image(img_pil)

            # Profiling: Color conversion
            if map_name.startswith(("jpn_scw", "jpn_jma_bousai")):
                imgarray = conv_image(img_pil, map_name)
            else:
                imgarray = np.asarray(img_pil)

            # Profiling: Rotation + ImageItem creation
            imgarray = np.rot90(imgarray, -1)
            imgitem = pg.ImageItem(imgarray, levels=(0, 255))
            if overlay:
                imgitem.setCompositionMode(QT_COMPOSITION_MODE_DARKEN)

            imgarray_min_x, imgarray_max_y = get_lon_lat_from_tile_xy(
                z, keys[0], keys[1]
            )
            imgarray_max_x, imgarray_min_y = get_lon_lat_from_tile_xy(
                z, keys[0] + 1, keys[1] + 1
            )

            # Profiling: addItem
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
        if use_mbtiles:
            self.cur.close()
            self.con.close()

        return True

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
        tiles = []
        for i in range(tile_x[0], tile_x[1] + 1):
            for j in range(tile_y[0], tile_y[1] + 1):
                tiles.append((i, j))
        for i in [tile_x[0] - 1, tile_x[1] + 1]:
            for j in range(tile_y[0] - 1, tile_y[1] + 2):
                tiles.append((i, j))
        for i in range(tile_x[0], tile_x[1] + 1):
            for j in [tile_y[0] - 1, tile_y[1] + 1]:
                tiles.append((i, j))

        if expand and z_conv_factor > 1:
            tiles = list(
                set(
                    map(
                        lambda x: tuple(map(lambda y: int(y / z_conv_factor), x)),
                        tiles,
                    )
                )
            )

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
    ):
        draw_flag = False
        add_keys = {}
        expand_keys = {}
        map_settings = map_config[map_name]

        if z not in self.drawn_tile[map_name] or self.pre_zoomlevel[map_name] != z:
            self.drawn_tile[map_name][z] = {}

        for i in range(tile_x[0], tile_x[1] + 1):
            for j in range(tile_y[0], tile_y[1] + 1):
                drawn_tile_key = f"{i}-{j}"
                exist_tile_key = (i, j)
                pixel_x = x_start = pixel_y = y_start = 0
                if expand:
                    pixel_x, x_start = divmod(i, z_conv_factor)
                    pixel_y, y_start = divmod(j, z_conv_factor)
                    exist_tile_key = (pixel_x, pixel_y)

                if drawn_tile_key not in self.drawn_tile[map_name][z] and self.check_tile(
                    use_mbtiles,
                    map_name,
                    z_draw,
                    exist_tile_key,
                    map_settings,
                ):
                    self.drawn_tile[map_name][z][drawn_tile_key] = True
                    add_keys[(i, j)] = True
                    draw_flag = True
                    if expand:
                        expand_keys[(i, j)] = (pixel_x, pixel_y, x_start, y_start)

        return draw_flag, add_keys, expand_keys

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
