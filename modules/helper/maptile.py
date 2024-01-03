import os
from datetime import datetime, timedelta #datetime is necessary for map_config["current_time_func"]()
from random import random
import math
import asyncio

import numpy as np
from PIL import Image

from modules.utils.network import detect_network
from modules.helper.network import (
    get_json,
)
from modules.utils.map import (
    get_maptile_filename,
    get_tilexy_and_xy_in_tile,
)
from logger import app_logger

SCW_WIND_SPEED_ARROW = np.array([
    [189,   0, 186], # #bd00ba,   0~1[m/s]
    [159,   1, 198], # #9f01c6,   1~2[m/s]
    [130,   1, 218], # #340059,   2~3[m/s]
    [ 28,  59, 255], # #1c3bff,   3~4[m/s]
    [  0, 160, 252], # #00a0fc,   4~5[m/s]
    [  0, 200, 201], # #00c8c9,   5~6[m/s]
    [  2, 210, 136], # #005438,   6~7[m/s]
    [  0, 219,   2], # #00db02,   7~8[m/s]
    [159, 230,  51], # #9fe633,   8~9[m/s]
    [231, 220,  49], # #e7dc31,  9~10[m/s]
    [232, 173,  45], # #e8ad2d, 10~11[m/s]
    [239, 130,  41], # #ef8229, 11~12[m/s]
    [248,  80,  31], # #f8501f, 12~14[m/s]
    [252,   1,   3], # #fc0103, 14~17[m/s]
    [242,   0, 135], # #f20087, 17~25[m/s]
    [246,   1, 192], # #f601c0, 25~33[m/s]
    [251,   2, 249], # #fb02f9,   33~[m/s]
], dtype='uint8')

SCW_WIND_SPEED_ARROW_CONV = np.array([
    [160,   0, 160, 255], # #A000A0,   0~1[m/s]
    [  0,   0, 255, 255], # #00A0FF,   1~2[m/s]
    [  0, 255, 255, 255], # #00FFFF,   2~3[m/s]
    [  0, 255,   0, 255], # #00FF00,   3~4[m/s]
    [255, 160,   0, 255], # #FFA000,   4~5[m/s]
    [255, 160,   0, 255], # #FFA000,   5~6[m/s]
    [255,   0,   0, 255], # #FFFF00,   6~7[m/s]
    [255,   0,   0, 255], # #FFFF00,   7~8[m/s]
    [160,   0,   0, 255], # #FFA000,   8~9[m/s]
    [160,   0,   0, 255], # #FFA000,  9~10[m/s]
    [  0,   0,   0, 255], # #FF0000, 10~11[m/s]
    [  0,   0,   0, 255], # #FF0000, 11~12[m/s]
    [  0,   0,   0, 255], # #FF0000, 12~14[m/s]
    [  0,   0,   0, 255], # #FF0000, 14~17[m/s]
    [  0,   0,   0, 255], # #FF0000, 17~25[m/s]
    [  0,   0,   0, 255], # #FF0000, 25~33[m/s]
    [  0,   0,   0, 255], # #FF0000,   33~[m/s]
], dtype='uint8')

SCW_WIND_SPEED_COLOR = np.array([
    [189,   0, 186], # #bd00ba,   0~1[m/s]
    [159,   1, 198], # #9f01c6,   1~2[m/s]
    [130,   1, 218], # #340059,   2~3[m/s]
    [ 28,  59, 255], # #1c3bff,   3~4[m/s]
    [  0, 160, 252], # #00a0fc,   4~5[m/s]
    [  0, 200, 201], # #00c8c9,   5~6[m/s]
    [  2, 210, 136], # #005438,   6~7[m/s]
    [  0, 219,   2], # #00db02,   7~8[m/s]
    [159, 230,  51], # #9fe633,   8~9[m/s]
    [231, 220,  49], # #e7dc31,  9~10[m/s]
    [232, 173,  45], # #e8ad2d, 10~11[m/s]
    [239, 130,  41], # #ef8229, 11~12[m/s]
    [248,  80,  31], # #f8501f, 12~14[m/s]
    [252,   1,   3], # #fc0103, 14~17[m/s]
    [242,   0, 135], # #f20087, 17~25[m/s]
    [246,   1, 192], # #f601c0, 25~33[m/s]
    [251,   2, 249], # #fb02f9,   33~[m/s]
    [ 76,   0,  72], # #4C0048,   0~1[m/s]
    [ 64,   0,  80], # #400050,   1~2[m/s]
    [ 52,   0,  89], # #340059,   2~3[m/s]
    [ 13,  23, 102], # #0D1766,   3~4[m/s]
    [  0,  64, 102], # #004066,   4~5[m/s]
    [  0,  80,  80], # #005050,   5~6[m/s]
    [  0,  84,  56], # #005438,   6~7[m/s]
    [  0,  88,   0], # #005800,   7~8[m/s]
    [ 64,  92,  20], # #405C14,   8~9[m/s]
    [ 92,  88,  20], # #5C5814,  9~10[m/s]
    [ 92,  70,  18], # #5C4612, 10~11[m/s]
    [ 96,  52,  16], # #603410, 11~12[m/s]
    [ 99,  32,  12], # #63200C, 12~14[m/s]
    [102,   0,   0], # #660000, 14~17[m/s]
    [ 96,   0,  52], # #600034, 17~25[m/s]
], dtype='uint8')

SCW_WIND_SPEED_COLOR_VALUE = np.array([
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 21, 29, 33,
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 21, 29, 33,
], dtype='uint8')

SCW_WIND_ARROW_MARGIN = 8
SCW_WIND_ARROW_PIXEL_COUNT = 10

JMA_RAIN_COLOR = np.array([
    [242, 242, 255], # #F2F2FF,   0~1[mm/h]
    [160, 210, 255], # #A0D2FF,   1~5[mm/h]
    [ 33, 140, 255], # #218CFF,  5~10[mm/h]
    [  0,  65, 255], # #0041FF, 10~20[mm/h]
    [255, 245,   0], # #FFF500, 20~30[mm/h]
    [255, 153,   0], # #FF9900, 30~50[mm/h]
    [255,  40,   0], # #FF2800, 50~80[mm/h]
    [180,   0, 104], # #B40068,   80~[mm/h]
], dtype='uint8')

JMA_RAIN_COLOR_CONV = np.array([
    [180, 255, 255, 255], # #B4FFFF,   0~1[mm/h]
    [180, 180, 255, 255], # #B4B4FF,   1~5[mm/h]
    [  0, 180, 255, 255], # #00B4FF,  5~10[mm/h]
    [  0,   0, 255, 255], # #0000FF, 10~20[mm/h]
    [255, 255,   0, 255], # #FFFF00, 20~30[mm/h]
    [255, 180,   0, 255], # #FFB400, 30~50[mm/h]
    [255,   0,   0, 255], # #FF0000, 50~80[mm/h]
    [180,   0,   0, 255], # #B40000,   80~[mm/h]
], dtype='uint8')


async def get_scw_list(url, referer):
    # network check
    if not detect_network():
        return None

    try:
        response = await get_json(url, headers={"referer": referer})
    except:
        response = None
    return response


def conv_colorcode(t):
    return f"#{t[0]:02X}{t[1]:02X}{t[2]:02X}"


def get_headwind(wind_speed, wind_track, track):
    if np.any(np.isnan([wind_speed, wind_track, track])):
        return np.nan
    if wind_speed == 0:
        return 0
    # plus: headwind, minus: tailwind
    return round(math.cos(math.radians(wind_track-track)) * wind_speed, 1)


def conv_image(image, map_name):
    res = None
    if map_name.startswith("jpn_scw"):
        res = conv_image_internal(image, SCW_WIND_SPEED_ARROW, SCW_WIND_SPEED_ARROW_CONV)
    elif map_name.startswith("jpn_jma_bousai"):
        res = conv_image_internal(image, JMA_RAIN_COLOR, JMA_RAIN_COLOR_CONV)
    return res


def conv_image_internal(image, orig_colors, conv_colors):

    wing_speed_mod = []
    wing_speed_index = []
    colors = image.getcolors(image.size[0]*image.size[1])
    for c in colors:
        if c[1][0] == c[1][1] == c[1][2]:
            continue
        dist = np.linalg.norm(orig_colors - c[1][0:3], axis=1)
        min_index = np.argmin(dist)
        if dist[min_index] < 10:
            wing_speed_mod.append(c[1])
            wing_speed_index.append(min_index)
            # app_logger.debug(f"{c[1]} / {c[0]}: {dist[min_index]:.0f}")

    # mask and convert
    im_array = np.array(image)
    mask = np.zeros(im_array.shape[0:2], dtype='bool')
    for w in wing_speed_mod:
        mask = np.ma.mask_or(mask, np.all(im_array == w, axis=2))
    im_array[~mask,3] = 0 # delete background

    # conv color
    res_array = im_array.copy()
    if wing_speed_mod:
        for w, i in zip(wing_speed_mod, wing_speed_index):
            res_array[np.all(im_array == w, axis=2)] = conv_colors[i]

    return res_array


def get_next_validtime(map_settings):

    next_validtime = None
    # print(map_settings["timeline"])
    if map_settings["timeline"] is not None:
        for i, t in enumerate(map_settings["timeline"]):
            if (
                t["it"] == map_settings["validtime"]
                and t["index"] + 1 == map_settings["timeline"][i + 1]["index"]
            ):
                next_validtime = map_settings["timeline"][i + 1]["it"]
                # print(i, map_settings["validtime"], next_validtime)
                break

    return next_validtime


def get_wind_with_tile_xy(img_files, x_in_tile, y_in_tile, tilesize, tiles_cond, image, im_array):

    def get_wind_speed(color):
        dist = np.linalg.norm(SCW_WIND_SPEED_COLOR - color, axis=1)
        min_index = np.argmin(dist)
        min_label = None
        if dist[min_index] < 10:
            min_label = float(SCW_WIND_SPEED_COLOR_VALUE[min_index])
        # app_logger.debug(f"color: {color}")
        # app_logger.debug(dist)
        # app_logger.debug(f"min_index:{min_index}, min_label:{min_label}")
        return min_label, dist[min_index]

    def get_marginal_wind_speed(image, xy_in_tile, delta, image_size):
        pixels = []
        x = xy_in_tile[0]
        y = xy_in_tile[1]
        for j in range(y-delta, y+delta+1):
            if j < 0 or j > image_size[0]:
                continue
            for i in range(x-delta, x+delta+1):
                if (i == x and j == y) or i < 0 or i > image_size[1]:
                    continue
                pixels.append((i, j))
        
        labels = []
        for p in pixels:
            color = image.getpixel(p)
            if color[0] == color[1] == color[2]:
                continue
            min_label, min_dist = get_wind_speed(color)
            # app_logger.debug(f"{p}: {conv_colorcode(color)} {color}: {min_dist:.0f}, {min_label:.1f}[m/s]")
            if min_label is not None:
                labels.append(min_label)
        
        if len(labels):
            return round(np.average(labels), 1)
        else:
            return get_marginal_wind_speed(image, xy_in_tile, delta+1, image_size)

    def get_marginal_contour(x, y, contour_count, image_xy, mask, index):
        for j in range(y-1, y+1+1):
            if j < 0 or j >= image_xy[0]:
                continue
            for i in range(x-1, x+1+1):
                if i < 0 or i >= image_xy[1]:
                    continue
                if mask[j, i] and not index[j, i]:
                    index[j, i] = contour_count
                    get_marginal_contour(i, j, contour_count, image_xy, mask, index)

    xy_in_tile = np.array([x_in_tile, y_in_tile])

    if tiles_cond[0] < 0:
        xy_in_tile[0] += 256
    if tiles_cond[1] < 0:
        xy_in_tile[1] += 256
    # app_logger.debug(f"[{x_in_tile}, {y_in_tile}] -> {xy_in_tile}")

    if image is None:
        # app_logger.info(f"open image: {img_files}")
        if len(img_files) == 1:
            image = Image.open(img_files[0]).convert("RGB")
        elif len(img_files) == 2:
            if tiles_cond[0] != 0:
                image = Image.new('RGB', (tilesize*2, tilesize))
                for i, m in enumerate(img_files):
                    image.paste(Image.open(m).convert("RGB"), (tilesize*i,0))
            elif tiles_cond[1] != 0:
                image = Image.new('RGB', (tilesize, tilesize*2))
                for i, m in enumerate(img_files):
                    image.paste(Image.open(m).convert("RGB"), (0, tilesize*i))
        elif len(img_files) == 4:
            image = Image.new('RGB', (tilesize*2, tilesize*2))
            for i, m in enumerate(img_files):
                y, x = divmod(i, 2)
                image.paste(Image.open(m).convert("RGB"), (tilesize*x, tilesize*y))

    #color = image.getpixel(tuple(xy_in_tile))
    color = image.getpixel((xy_in_tile.item(0), xy_in_tile.item(1)))
    # app_logger.info(f"image.size: {image.size}")

    # get wind_speed
    wind_speed, min_dist = get_wind_speed(color)
    if color[0] == color[1] == color[2]:
        # app_logger.debug("detect gray")
        # search marginal pixel
        wind_speed = get_marginal_wind_speed(image, xy_in_tile, 1, image.size[::-1])
    # app_logger.debug(f"{conv_colorcode(color)} {color}: {min_dist:.0f}, {wind_speed:.0f}[m/s]")

    # get wind_direction
    wind_direction = 0

    # modify color palette of arrows
    wing_speed_mod = []
    colors = image.getcolors(image.size[0]*image.size[1])
    for c in colors:
        if c[1][0] == c[1][1] == c[1][2]:
            continue
        dist = np.linalg.norm(SCW_WIND_SPEED_ARROW - c[1], axis=1)
        min_index = np.argmin(dist)
        if dist[min_index] < 10:
            wing_speed_mod.append(c[1])
            # app_logger.debug(f"{conv_colorcode(c[1])} {c[1]} / {c[0]}: {dist[min_index]:.0f}")

    # extract arrows
    if im_array is None:
        # app_logger.debug("create im_array")
        im_array = np.array(image)
        mask = np.zeros(im_array.shape[0:2], dtype='bool')
        for w in wing_speed_mod:
            mask = np.ma.mask_or(
                mask, 
                (im_array[:,:,0] == w[0]) & (im_array[:,:,1] == w[1]) & (im_array[:,:,2] == w[2])
            )
        im_array[:,:,:3][mask] = [255, 255, 255]
        im_array[:,:,:3][~mask] = [0, 0, 0]
    else:
        mask = np.zeros(im_array.shape[0:2], dtype='bool')
        mask = (im_array[:,:,0] == 255)

    # detect arrows in SCW_WIND_ARROW_MARGIN*SCW_WIND_ARROW_MARGIN pixels
    x_border = [
        max(xy_in_tile[0]-SCW_WIND_ARROW_MARGIN, 0),
        min(xy_in_tile[0]+SCW_WIND_ARROW_MARGIN, im_array.shape[1])
    ]
    y_border = [
        max(xy_in_tile[1]-SCW_WIND_ARROW_MARGIN, 0),
        min(xy_in_tile[1]+SCW_WIND_ARROW_MARGIN, im_array.shape[0])
    ]

    # detect contours
    index = np.zeros((im_array.shape[0:2]), dtype="uint8")
    contour_count = 1
    # app_logger.debug(f"x_border: {x_border}, y_border: {y_border}")
    for j in range(*y_border):
        for i in range(*x_border):
            if mask[j,i] and not index[j,i]:
                index[j,i] = contour_count
                get_marginal_contour(i, j, contour_count, im_array.shape[0:2], mask, index)
                contour_count += 1
    # app_logger.debug(index[y_border[0]:y_border[1]+1, x_border[0]:x_border[1]+1])

    # get long edge, short edge, cerntroid and center of arrows to calculate direction
    stats = []
    for i in range(contour_count):
        stats.append({
            "max_width":0,
            "min_width":im_array.shape[1],
            "max_width_point": None,
            "min_width_point": None,
            "max_height":0,
            "min_height":im_array.shape[0],
            "max_height_point": None,
            "min_height_point": None,
            "centroid": np.array([0, 0]),
            "count": 1,
            "start": None,
            
        })
    for j in range(*y_border):
        for i in range(*x_border):
            if not index[j, i]:
                continue
            c = index[j, i]
            if stats[c]["max_width"] < i:
                stats[c]["max_width"] = i
                stats[c]["max_width_point"] = np.array([i, j])
            if stats[c]["min_width"] > i:
                stats[c]["min_width"] = i
                stats[c]["min_width_point"] = np.array([i, j])
            if stats[c]["max_height"] < j:
                stats[c]["max_height"] = j
                stats[c]["max_height_point"] = np.array([i, j])
            if stats[c]["min_height"] > j:
                stats[c]["min_height"] = j
                stats[c]["min_height_point"] = np.array([i, j])
            stats[c]["centroid"] = (
                stats[c]["centroid"] * (stats[c]["count"] - 1) + np.array([i, j])
            ) / stats[c]["count"]
            stats[c]["count"] += 1
    
    dist_min = np.inf
    for i in range(contour_count):
        s = stats[i]
        if s["max_width_point"] is None or s["count"] <= SCW_WIND_ARROW_PIXEL_COUNT:
            continue
        w_h = np.array([
            s["max_width"] - s["min_width"],
            s["max_height"] - s["min_height"]
        ])
        center = np.array([
            (s["max_width"] + s["min_width"]) / 2,
            (s["max_height"] + s["min_height"]) / 2
        ])

        x_y = np.array([0, 0])
        if w_h[0] > w_h[1]:
            if s["centroid"][0] > center[0]:
                x_y = s["max_width_point"] - s["min_width_point"]
                s["start"] = s["min_width_point"]
            else:
                x_y = s["min_width_point"] - s["max_width_point"]
                s["start"] = s["max_width_point"]
        else:
            if s["centroid"][1] > center[1]:
                x_y = s["max_height_point"] - s["min_height_point"]
                s["start"] = s["min_height_point"]
            else:
                x_y = s["min_height_point"] - s["max_height_point"]
                s["start"] = s["max_height_point"]

        d = round(np.degrees(np.arctan2(x_y[1], x_y[0]))) - 90
        if d < 0:
            d += 360
        # app_logger.debug(f"{i}: {w_h}, {x_y}, {d} deg, start:{s['start']}"")

        dist = np.linalg.norm(s["start"] - xy_in_tile)
        if dist < dist_min:
            wind_direction = d
            dist_min = dist
            # app_logger.debug(f"  dist: {round(dist,1)}, from {s['start']} to {xy_in_tile}")

    # app_logger.debug(stats)

    return wind_speed, wind_direction, image, im_array


class MapTileWithValues():
    config = None

    # for jpn_scw
    pre_wind_tile_xy = (np.nan, np.nan)
    pre_wind_xy_in_tile = (np.nan, np.nan)
    pre_wind_tiles = None
    pre_wind_tiles_cond = None
    pre_wind_speed = np.nan
    pre_wind_direction = np.nan
    downloaded_wind_tiles = {}
    wind_image = None
    wind_im_array = None
    scw_wind_validtime = None
    
    # for jpn_kokudo_chiri_in_DEM~
    pre_alt_tile_xy = (np.nan, np.nan)
    pre_alt_xy_in_tile = (np.nan, np.nan)
    pre_altitude = np.nan
    dem_array = None

    get_scw_lock = False

    def __init__(self, config):
        self.config = config

    @staticmethod
    def get_tiles(tile_x, tile_y, tiles_cond):
        tiles = []
        
        marginal_tiles_cond = [False]*9 # marginal 3*3 tiles
        marginal_tiles_true_index = {
            ( 0,  0): [4,],          # 1 tiles: center only
            (-1,  0): [3, 4],        # 2 tiles: tile_x-1
            (+1,  0): [4, 5],        # 2 tiles: tile_x+1
            ( 0, -1): [1, 4],        # 2 tiles: tile_y-1
            ( 0, +1): [4, 7],        # 2 tiles: tile_y+1
            (-1, -1): [0, 1, 3, 4],  # 4 tiles: tile_x-1 * tile_y-1
            (+1, -1): [1, 2, 4, 5],  # 4 tiles: tile_x+1 * tile_y-1
            (-1, +1): [3, 4, 6, 7],  # 4 tiles: tile_x-1 * tile_y+1
            (+1, +1): [4, 5, 7, 8],  # 4 tiles: tile_x+1 * tile_y+1
        }
        for i in marginal_tiles_true_index[tuple(tiles_cond)]:
            marginal_tiles_cond[i] = True
        for i, m in enumerate(marginal_tiles_cond):
            if m:
                y_delta, x_delta = divmod(i, 3)
                tiles.append([tile_x + x_delta - 1, tile_y + y_delta - 1])
        return tiles

    async def download_tiles(self, tiles, map_config, map_name, z):
        map_settings = map_config[map_name]
        download_tile = []
        for tile in tiles:
            filename = get_maptile_filename(
                map_name, z, *tile, map_settings["basetime"], map_settings["validtime"]
            )
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                self.downloaded_wind_tiles[filename] = True
                continue

            # download is in progress
            if filename in self.downloaded_wind_tiles:
                continue

            self.downloaded_wind_tiles[filename] = False
            download_tile.append(tile)

        # start downloading
        if len(download_tile):
            await self.config.network.download_maptile(
                map_config, map_name, z, download_tile,
            )

    async def update_overlay_windmap_timeline(self, map_settings, map_name):

        if map_name.startswith("jpn_scw"):

            # check lock
            if self.get_scw_lock:
                return

            # check network
            if not self.config.G_AUTO_BT_TETHERING and not detect_network():
                return

            asyncio.create_task(
                self.update_jpn_scw_timeline(map_settings, self.update_overlay_wind_basetime)
            )
            return

        if not self.update_overlay_wind_basetime(map_settings):
            return
        # basetime update
        basetime_str = map_settings["current_time"].strftime(
            map_settings["time_format"]
        )
        map_settings["basetime"] = basetime_str
        map_settings["validtime"] = map_settings["basetime"]

    async def update_jpn_scw_timeline(self, map_settings, update_basetime):
        update_basetime(map_settings)
        if map_settings["timeline_update_date"] == map_settings["current_time"]:
            return
        
        # open connection
        self.get_scw_lock = True
        f_name = self.update_jpn_scw_timeline.__name__
        if not await self.config.network.open_bt_tethering(f_name):
            return

        # app_logger.info("get_scw_list connection start...")
        url = map_settings["inittime"].format(rand=random())
        init_time_list = await get_scw_list(url, map_settings["referer"])
        if init_time_list is None:
            # close connection
            await self.config.network.close_bt_tethering(f_name)
            self.get_scw_lock = False
            return
        basetime = init_time_list[0]["it"]

        url = map_settings["fl"].format(basetime=basetime, rand=random())
        timeline = await get_scw_list(url, map_settings["referer"])
        
        # close connection
        await self.config.network.close_bt_tethering(f_name)
        self.get_scw_lock = False

        if timeline is None:
            return
        map_settings["timeline"] = timeline
        if len(timeline) < 21:
            app_logger.warning("lack of timeline")
            app_logger.warning(timeline)
        time_str = map_settings["current_time"].strftime("%H%MZ%d")
        for tl in map_settings["timeline"]:
            if tl["it"].startswith(time_str):
                map_settings["basetime"] = basetime
                map_settings["validtime"] = tl["it"]
                map_settings["subdomain"] = tl["sd"]
                map_settings["timeline_update_date"] = map_settings["current_time"]
                # app_logger.info(f"get_scw_list Success: {basetime} {tl['it']}]")
                return

    def update_overlay_wind_basetime(self, map_settings):

        # update current_time
        current_time = map_settings["current_time_func"]()
        delta_minutes = current_time.minute % map_settings["time_interval"]

        # time_interval < time_interval/2: latest measured time (not forecast)
        # time_interval > time_interval/2: next forecast time
        if delta_minutes > map_settings["time_interval"] / 2:
            delta_minutes -= map_settings["time_interval"]

        current_time += timedelta(minutes=-delta_minutes)
        current_time = current_time.replace(second=0, microsecond=0)

        if map_settings["current_time"] != current_time:
            map_settings["current_time"] = current_time
            return True
        else:
            return False

    async def update_overlay_rainmap_timeline(self, map_settings, map_name):

        if not self.update_overlay_rain_basetime(map_settings):
            return
        # basetime update
        if map_settings["time_format"] == "unix_timestamp":
            basetime_str = str(int(map_settings["current_time"].timestamp()))
        else:
            basetime_str = map_settings["current_time"].strftime(
                map_settings["time_format"]
            )
        map_settings["basetime"] = basetime_str
        map_settings["validtime"] = map_settings["basetime"]

    def update_overlay_rain_basetime(self, map_settings):

        # update current_time
        current_time = map_settings["current_time_func"]()
        delta_minutes = current_time.minute % map_settings["time_interval"]

        # latest measured time (not forecast)
        delta_seconds = delta_minutes * 60 + current_time.second
        delta_seconds_cutoff = map_settings["update_minutes"] * 60 + 15
        if delta_seconds < delta_seconds_cutoff:
            delta_minutes += map_settings["time_interval"]

        current_time += timedelta(minutes=-delta_minutes)
        current_time = current_time.replace(second=0, microsecond=0)

        if map_settings["current_time"] != current_time:
            map_settings["current_time"] = current_time
            return True
        else:
            return False

    async def get_wind(self, pos):

        map_config = self.config.G_WIND_OVERLAY_MAP_CONFIG
        map_name = self.config.G_WIND_DATA_SOURCE
        map_settings = map_config[map_name]
        z = map_settings["max_zoomlevel"]
        tilesize = map_settings["tile_size"]

        if not map_name.startswith("jpn_scw") or np.any(np.isnan(pos)):
            return np.nan, np.nan

        # initialize 
        tile_x, tile_y, x_in_tile, y_in_tile = get_tilexy_and_xy_in_tile(
            z, *pos, tilesize
        )
        await self.update_overlay_windmap_timeline(map_settings, map_name)
        if self.scw_wind_validtime != map_config[map_name]["validtime"]:
            # app_logger.debug(f"get_wind update: {self.scw_wind_validtime}, {map_config[map_name]['validtime']} / {map_config[map_name]['basetime']}")
            self.scw_wind_validtime = map_config[map_name]["validtime"]
            time_updated = True
        else:
            time_updated = False
        
        if (
            self.pre_wind_tile_xy == (tile_x, tile_y)
            and self.pre_wind_xy_in_tile == (x_in_tile, y_in_tile)
            and not time_updated
            and self.wind_image is not None
        ):
            return self.pre_wind_speed, self.pre_wind_direction
        
        # check marginal tile
        tiles_cond = [0, 0] # x:-1/0/+1, y:-1/0/+1
        for i, t in enumerate([x_in_tile, y_in_tile]):
            if t < SCW_WIND_ARROW_MARGIN:
                tiles_cond[i] = -1
            elif t > tilesize - SCW_WIND_ARROW_MARGIN:
                tiles_cond[i] = +1
        # tile check and download
        tiles = self.get_tiles(tile_x, tile_y, tiles_cond)
        await self.download_tiles(tiles, map_config, map_name, z) 

        tile_files = []
        for t in tiles:
            filename = get_maptile_filename(
                map_name, z, *t, map_settings["basetime"], map_settings["validtime"]
            )
            if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                continue
            tile_files.append(filename)
        # download in progress
        if len(tiles) != len(tile_files):
            # app_logger.debug("dl in progress... reset wind_image, wind_im_array")
            self.wind_image = None
            self.wind_im_array = None
            return self.pre_wind_speed, self.pre_wind_direction
        # app_logger.debug(f"tiles: {tiles}")
        # app_logger.debug(f"tile_cond: {tiles_cond}")

        # get wind
        if (
            self.pre_wind_tiles != tiles
            or self.pre_wind_tiles_cond != tiles_cond
            or time_updated
        ):
            # app_logger.debug("reset wind_image, wind_im_array")
            self.wind_image = None
            self.wind_im_array = None
        (
            wind_speed, wind_direction,
            self.wind_image, self.wind_im_array
        ) = get_wind_with_tile_xy(
            tile_files, x_in_tile, y_in_tile, tilesize, tiles_cond,
            self.wind_image, self.wind_im_array
        )
        # app_logger.info(f"{wind_speed} [m/s], {wind_direction} deg")

        self.pre_wind_tile_xy = (tile_x, tile_y)
        self.pre_wind_xy_in_tile = (x_in_tile, y_in_tile)
        self.pre_wind_tiles = tiles
        self.pre_wind_tiles_cond = tiles_cond
        self.pre_wind_speed = wind_speed
        self.pre_wind_direction = wind_direction
        return wind_speed, wind_direction
    
    async def get_altitude_from_tile(self, pos):
        
        if np.any(np.isnan(pos)):
            return np.nan
        
        map_config = self.config.G_DEM_MAP_CONFIG
        map_name = self.config.G_DEM_MAP
        map_settings = map_config[map_name]
        z = map_settings["fix_zoomlevel"]

        tile_x, tile_y, x_in_tile, y_in_tile = get_tilexy_and_xy_in_tile(
            z, *pos, map_settings["tile_size"]
        )
        if (
            self.pre_alt_tile_xy == (tile_x, tile_y)
            and self.pre_alt_xy_in_tile == (x_in_tile, y_in_tile)
        ):
            return self.pre_altitude

        # tile check and download
        filename = get_maptile_filename(map_name, z, tile_x, tile_y)
        if not os.path.exists(filename):
            await self.config.network.download_maptile(
                map_config, map_name, z, [[tile_x, tile_y],],
            )
            return np.nan
        if os.path.getsize(filename) == 0:
            return np.nan

        # get altitude
        if self.pre_alt_tile_xy != (tile_x, tile_y):
            self.dem_array = np.asarray(Image.open(filename))
            self.pre_alt_tile_xy = (tile_x, tile_y)
            self.pre_alt_xy_in_tile = (x_in_tile, y_in_tile)
        rgb_pos = self.dem_array[y_in_tile, x_in_tile]

        if map_name.startswith("jpn_kokudo_chiri_in_DEM"):
            altitude = rgb_pos[0] * (2**16) + rgb_pos[1] * (2**8) + rgb_pos[2]
            if altitude < 2**23:
                altitude = round(altitude * 0.01, 1)
            elif altitude == 2**23:
                altitude = np.nan
            else:
                altitude = round((altitude - 2**24) * 0.01, 1)
        elif map_name.startswith("mapbox_terrain"):
            altitude = round(-10000 + ((rgb_pos[0] * 256 * 256 + rgb_pos[1] * 256 + rgb_pos[2]) * 0.1), 1)
        else:
            altitude = np.nan

        # app_logger.info(f"{altitude}m, {filename}, {x_in_tile}, {x_in_tile}, {pos}")
        self.pre_altitude = altitude

        return altitude

