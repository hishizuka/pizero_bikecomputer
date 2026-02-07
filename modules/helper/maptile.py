import os
from datetime import datetime, timedelta, timezone  #datetime is necessary for map_config["current_time_func"]()
import locale
from random import random
import math
import asyncio

import numpy as np
from PIL import Image

from modules.utils.network import detect_network_async
from modules.helper.network import (
    get_json,
)
from modules.utils.map import (
    get_maptile_filename,
    get_tilexy_and_xy_in_tile,
)
from modules.app_logger import app_logger

SCW_WIND_SPEED_ARROW = np.array([
    [190,   0, 180], #   0~1[m/s]
    [160,   0, 200], #   1~2[m/s]
    [130,   0, 220], #   2~3[m/s]
    [ 30,  60, 255], #   3~4[m/s]
    [  0, 160, 255], #   4~5[m/s]
    [  0, 200, 200], #   5~6[m/s]
    [  0, 210, 140], #   6~7[m/s]
    [  0, 220,   0], #   7~8[m/s]
    [160, 230,  50], #   8~9[m/s]
    [230, 220,  50], #  9~10[m/s]
    [230, 175,  45], # 10~11[m/s]
    [240, 130,  40], # 11~12[m/s]
    [248,  80,  30], # 12~14[m/s]
    [255,   0,   0], # 14~17[m/s]
    [240,   0, 130], # 17~25[m/s]
    [248,   0, 190], # 25~33[m/s]
    [255,   0, 255], #   33~[m/s]
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
    [190,   0, 180], #   0~1[m/s]
    [160,   0, 200], #   1~2[m/s]
    [130,   0, 220], #   2~3[m/s]
    [ 30,  60, 255], #   3~4[m/s]
    [  0, 160, 255], #   4~5[m/s]
    [  0, 200, 200], #   5~6[m/s]
    [  0, 210, 140], #   6~7[m/s]
    [  0, 220,   0], #   7~8[m/s]
    [160, 230,  50], #   8~9[m/s]
    [230, 220,  50], #  9~10[m/s]
    [230, 175,  45], # 10~11[m/s]
    [240, 130,  40], # 11~12[m/s]
    [248,  80,  30], # 12~14[m/s]
    [255,   0,   0], # 14~17[m/s]
    [240,   0, 130], # 17~25[m/s]
    [248,   0, 190], # 25~33[m/s]
    [255,   0, 255], #   33~[m/s]
    [ 76,   0,  72], #   0~1[m/s]
    [ 64,   0,  80], #   1~2[m/s]
    [ 52,   0,  88], #   2~3[m/s]
    [ 12,  24, 102], #   3~4[m/s]
    [  0,  64, 102], #   4~5[m/s]
    [  0,  80,  80], #   5~6[m/s]
    [  0,  84,  56], #   6~7[m/s]
    [  0,  88,   0], #   7~8[m/s]
    [ 64,  92,  20], #   8~9[m/s]
    [ 92,  88,  20], #  9~10[m/s]
    [ 92,  70,  18], # 10~11[m/s]
    [ 96,  52,  16], # 11~12[m/s]
    [ 99,  32,  12], # 12~14[m/s]
    [102,   0,   0], # 14~17[m/s]
    [ 96,   0,  52], # 17~25[m/s]
    [ 99,   0,  76], # 25~33[m/s]
    [102,   0, 102], #   33~[m/s]
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

# Downsampled Universal Blue palette for legend use (light -> strong).
RAINVIEWER_UNIVERSAL_BLUE_LEGEND = np.array([
    [199, 255, 255, 127], # #C7FFFF7F
    [191, 255, 255, 255], # #BFFFFF
    [127, 191, 255, 255], # #7FBFFF
    [ 79, 143, 255, 255], # #4F8FFF
    [ 47, 111, 255, 255], # #2F6FFF
    [ 15,  79, 255, 255], # #0F4FFF
    [  0,  47, 255, 255], # #002FFF
    [  0,  15, 255, 255], # #000FFF
    [  0,   0, 255, 255], # #0000FF
], dtype='uint8')

# OpenPortGuide wind_stream legend (Bft 0-1 ... >12).
OPENPORTGUIDE_WIND_STREAM_LEGEND = np.array([
    [160,   0, 200, 255], # 0-1
    [130,   0, 220, 255], # 1-2
    [ 30,  60, 255, 255], # 2-3
    [  0, 160, 255, 255], # 3-4
    [  0, 200, 200, 255], # 4-5
    [  0, 210, 140, 255], # 5-6
    [  0, 220,   0, 255], # 6-7
    [160, 230,  50, 255], # 7-8
    [230, 220,  50, 255], # 8-9
    [230, 175,  45, 255], # 9-10
    [240, 130,  40, 255], # 10-11
    [250,  60,  60, 255], # 11-12
    [240,   0, 130, 255], # >12
], dtype='uint8')

# Downsampled NEXRAD Level III palette for legend use (light -> strong).
RAINVIEWER_NEXRAD_LEGEND = np.array([
    [  4, 233, 231, 255], # #04E9E7
    [  0, 172, 243, 255], # #00ACF3
    [  0, 153,  98, 255], # #009962
    [  5, 155,   3, 255], # #059B03
    [251, 245,   0, 255], # #FBF500
    [250, 158,   0, 255], # #FA9E00
    [215,   0,   0, 255], # #D70000
    [214,  32, 231, 255], # #D620E7
    [255, 255, 255, 255], # #FFFFFF
], dtype='uint8')


async def get_scw_list(url, referer):
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
    rad_diff = math.radians(wind_track-track)
    # plus: headwind, minus: tailwind
    return round(math.cos(rad_diff) * wind_speed, 1)
    # abs(round(math.sin(rad_diff) * wind_speed, 1))  # crosswind


def conv_image(image, map_name):
    res = None
    if map_name.startswith("jpn_scw"):
        res = conv_image_internal(image, SCW_WIND_SPEED_ARROW, SCW_WIND_SPEED_ARROW_CONV)
    elif map_name.startswith("jpn_jma_bousai"):
        res = conv_image_internal(image, JMA_RAIN_COLOR, JMA_RAIN_COLOR_CONV)
    return res


def build_jma_timeline(past_list, forecast_list, time_format):
    if not time_format:
        return []

    def normalize_time_list(raw_list):
        if not isinstance(raw_list, list):
            return {}
        time_map = {}
        for item in raw_list:
            if not isinstance(item, dict):
                continue
            basetime = item.get("basetime")
            validtime = item.get("validtime")
            if not basetime or not validtime:
                continue
            try:
                datetime.strptime(validtime, time_format)
            except Exception:
                continue
            time_map[validtime] = {
                "basetime": basetime,
                "validtime": validtime,
            }
        return time_map

    forecast_map = normalize_time_list(forecast_list)
    past_map = normalize_time_list(past_list)
    # Prefer past entries when validtime overlaps.
    forecast_map.update(past_map)
    timeline = list(forecast_map.values())
    timeline.sort(key=lambda t: t["validtime"])
    return timeline


def get_wind_color(wind_speed):
    if wind_speed < 0:
        return [0, 0, 0, 0]
    idx = int(wind_speed)
    if idx > len(SCW_WIND_SPEED_ARROW_CONV):
        idx = -1
    return list(SCW_WIND_SPEED_ARROW_CONV[idx])


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


def get_scw_prev_next_validtime(map_settings):

    # prev/next * validtime/subdomain
    p_vt = n_vt = None
    p_sd = n_sd = None
    if map_settings["timeline"] is None:
        return p_vt, p_sd, n_vt, n_sd
    for i, tl in enumerate(map_settings["timeline"]):
        if tl["it"] == map_settings["validtime"]:
            if i > 0:
                p_vt = map_settings["timeline"][i - 1]["it"]
                p_sd = map_settings["timeline"][i - 1]["sd"]
            if i < len(map_settings["timeline"]) - 1:
                n_vt = map_settings["timeline"][i + 1]["it"]
                n_sd = map_settings["timeline"][i + 1]["sd"]
            break

    return p_vt, p_sd, n_vt, n_sd


def get_jma_prev_next_validtime(map_settings):
    p_vt = n_vt = None
    timeline = map_settings.get("timeline") or []
    current_vt = map_settings.get("validtime")
    if not timeline or not current_vt:
        return p_vt, n_vt
    for i, tl in enumerate(timeline):
        if tl.get("validtime") == current_vt:
            if i > 0:
                p_vt = timeline[i - 1].get("validtime")
            if i < len(timeline) - 1:
                n_vt = timeline[i + 1].get("validtime")
            break
    return p_vt, n_vt


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
    existing_tiles = {}
    wind_image = None
    wind_im_array = None
    scw_wind_validtime = None
    
    # for jpn_kokudo_chiri_in_DEM~
    pre_alt_map_name = None
    pre_alt_tile_xy = (np.nan, np.nan, np.nan)
    pre_alt_xy_in_tile = (np.nan, np.nan, np.nan)
    pre_altitude = np.nan
    dem_array = None

    get_scw_lock = False

    def __init__(self, config):
        self.config = config

    @property
    def network(self):
        return self.config.network

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

    def check_existing_tiles(self, filename):
        return self.existing_tiles.get(filename, False)

    def delete_existing_tiles(self, filenames):
        for f in filenames:
            self.existing_tiles.pop(f, None)

    async def download_maptiles(self, tiles, map_config, map_name, z, additional_download=False):
        download_tile = []
        map_settings = map_config[map_name]

        for tile in tiles:
            filename = get_maptile_filename(
                map_name, z, *tile, map_settings
            )
            
            # the file has already been downloaded.
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                self.existing_tiles[filename] = True
                continue

            # 404 not found. do nothing anymore with this file.
            elif os.path.exists(filename) and os.path.getsize(filename) == 0:
                continue

            # download is in progress
            elif filename in self.existing_tiles:
                continue

            # entry to download tiles
            self.existing_tiles[filename] = False
            download_tile.append(tile)

        # start downloading
        if len(download_tile):
            if not await self.network.download_maptiles(
                map_config, map_name, z, download_tile, additional_download=additional_download
            ):
                # failed to put queue, then retry (can't connect internet anymore)
                for tile in download_tile:
                    filename = get_maptile_filename(
                        map_name, z, *tile, map_settings
                    )
                    if filename in self.existing_tiles:
                        self.existing_tiles.pop(filename)

    async def update_overlay_windmap_timeline(self, map_settings, map_name, wait=False):
        if map_name.startswith("jpn_scw"):
            # check lock
            if self.get_scw_lock:
                return
            # Skip if there is no connectivity path available.
            if not self.network.check_network_with_bt_tethering():
                return

            if wait:
                await self.update_jpn_scw_timeline(map_settings, self.update_overlay_wind_basetime)
            else:
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
        bt_open_result = await self.network.open_bt_tethering(f_name)
        if not bt_open_result.is_success():
            self.get_scw_lock = False
            return

        # app_logger.info("get_scw_list connection start...")
        url = map_settings["inittime"].format(rand=random())
        init_time_list = await get_scw_list(url, map_settings["referer"])
        if init_time_list is None:
            # close connection
            await self.network.close_bt_tethering(f_name)
            self.get_scw_lock = False
            return
        basetime = init_time_list[0]["it"]

        url = map_settings["fl"].format(basetime=basetime, rand=random())
        timeline = await get_scw_list(url, map_settings["referer"])
        
        # close connection
        await self.network.close_bt_tethering(f_name)
        self.get_scw_lock = False

        if timeline is None:
            return
        map_settings["timeline"] = timeline
        if len(timeline) < 21:
            app_logger.warning(f"lack of timeline {len(timeline)}/21")
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

    async def update_jpn_jma_bousai_timeline(self, map_settings):
        self.update_overlay_rain_basetime(map_settings)
        current_time = map_settings.get("current_time")
        if current_time is None:
            return

        if (
            map_settings.get("timeline_update_date") == current_time
            and map_settings.get("timeline")
        ):
            return

        if not await detect_network_async(cache=False):
            return

        past_url = map_settings.get("past_time_list")
        forecast_url = map_settings.get("forcast_time_list")
        if not past_url and not forecast_url:
            return

        past_list = await get_json(past_url) if past_url else None
        forecast_list = await get_json(forecast_url) if forecast_url else None
        if not past_list and not forecast_list:
            return

        time_format = map_settings.get("time_format")
        timeline = build_jma_timeline(past_list, forecast_list, time_format)
        if not timeline:
            return

        map_settings["timeline"] = timeline
        map_settings["timeline_update_date"] = current_time

        current_str = current_time.strftime(time_format)
        selected = None
        for item in timeline:
            if item["validtime"] <= current_str:
                selected = item
            else:
                break
        if selected is None:
            selected = timeline[0]
        map_settings["basetime"] = selected["basetime"]
        map_settings["validtime"] = selected["validtime"]

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

    @staticmethod
    def get_jma_basetime_for_validtime(map_settings, validtime):
        if not validtime:
            return None
        for item in map_settings.get("timeline") or []:
            if item.get("validtime") == validtime:
                return item.get("basetime")
        return None

    async def get_prev_next_validtime(
        self, overlay_type, map_config, map_name, skip_update=False
    ):
        map_settings = map_config[map_name]
        # timeline update
        ufunc_map = {
            "RAIN": self.update_overlay_rainmap_timeline,
            "WIND": self.update_overlay_windmap_timeline,
        }
        ufunc = ufunc_map.get(overlay_type)
        if ufunc and not skip_update:
            await ufunc(map_settings, map_name)

        p_vt, p_sd, n_vt, n_sd = None, None, None, None
        if map_name.startswith("jpn_scw"):
            p_vt, p_sd, n_vt, n_sd = get_scw_prev_next_validtime(map_settings)
        elif map_name.startswith("jpn_jma_bousai"):
            p_vt, n_vt = get_jma_prev_next_validtime(map_settings)
        elif map_settings['validtime'] is not None:
            time_fmt = map_settings["time_format"]
            def parse(s):
                if time_fmt == "unix_timestamp":
                    return datetime.fromtimestamp(int(s), tz=timezone.utc)
                return datetime.strptime(s, time_fmt)

            vt = parse(map_settings["validtime"])
            bt = parse(map_settings["basetime"])
            td = timedelta(minutes=map_settings["time_interval"])

            p_vt_dt, n_vt_dt = vt - td, vt + td
            min_vt = bt + timedelta(minutes=map_settings["min_validtime"])
            max_vt = bt + timedelta(minutes=map_settings["max_validtime"])

            def format_time(dt):
                return str(int(dt.timestamp())) if time_fmt == "unix_timestamp" else dt.strftime(time_fmt)

            p_vt = format_time(p_vt_dt) if p_vt_dt >= min_vt else None
            n_vt = format_time(n_vt_dt) if n_vt_dt <= max_vt else None

        return p_vt, p_sd, n_vt, n_sd

    async def update_overlay_rainmap_timeline(self, map_settings, map_name):

        if map_name.startswith("jpn_jma_bousai"):
            await self.update_jpn_jma_bousai_timeline(map_settings)
            return

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

    async def get_wind(self, pos, forcast_time=None):
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
        wait = False
        if forcast_time is not None:
            wait = True
        await self.update_overlay_windmap_timeline(map_settings, map_name, wait)
        if self.scw_wind_validtime != map_config[map_name]["validtime"]:
            # app_logger.debug(f"get_wind update: {self.scw_wind_validtime}, {map_config[map_name]['validtime']} / {map_config[map_name]['basetime']}")
            self.scw_wind_validtime = map_config[map_name]["validtime"]
            time_updated = True
        else:
            time_updated = False

        if (
            forcast_time is None
            and self.pre_wind_tile_xy == (tile_x, tile_y)
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

        _map_config = map_config
        _map_settings = map_settings
        if forcast_time is not None:
            if map_settings["timeline"] is None:
                return np.nan, np.nan
            current_locale = locale.getlocale(locale.LC_TIME)
            locale.setlocale(locale.LC_TIME, "C")
            _map_config = map_config.copy()
            _map_config[map_name] = map_config[map_name].copy()
            _map_settings = _map_config[map_name]
            closest = min(
                _map_settings["timeline"], 
                key = lambda d: abs(
                    datetime.strptime(d["it"], _map_settings["time_format"]).replace(tzinfo=timezone.utc) - forcast_time
                )
            )
            _map_config[map_name]["validtime"] = closest["it"]
            _map_config[map_name]["subdomain"] = closest["sd"]
            locale.setlocale(locale.LC_TIME, current_locale)
        await self.download_maptiles(tiles, _map_config, map_name, z)

        tile_files = []
        for t in tiles:
            filename = get_maptile_filename(
                map_name, z, *t, _map_settings
            )
            if not self.check_existing_tiles(filename):
                continue
            tile_files.append(filename)
        # download in progress
        if len(tiles) != len(tile_files):
            # app_logger.debug("dl in progress... reset wind_image, wind_im_array")
            self.wind_image = None
            self.wind_im_array = None
            if forcast_time is None:
                return self.pre_wind_speed, self.pre_wind_direction
            else:
                return np.nan, np.nan
        # app_logger.debug(f"tiles: {tiles}")
        # app_logger.debug(f"tile_cond: {tiles_cond}")

        # get wind
        if (
            forcast_time is None
            and (
                self.pre_wind_tiles != tiles
                or self.pre_wind_tiles_cond != tiles_cond
                or time_updated
            )
        ):
            # app_logger.debug("reset wind_image, wind_im_array")
            self.wind_image = None
            self.wind_im_array = None

        cur_image = None if forcast_time is not None else self.wind_image
        cur_array = None if forcast_time is not None else self.wind_im_array
        (
            wind_speed, wind_direction,
            self.wind_image, self.wind_im_array
        ) = get_wind_with_tile_xy(
            tile_files, x_in_tile, y_in_tile, tilesize, tiles_cond,
            cur_image, cur_array
        )
        # app_logger.info(f"{wind_speed} [m/s], {wind_direction} deg")

        if forcast_time is None:
            self.pre_wind_tile_xy = (tile_x, tile_y)
            self.pre_wind_xy_in_tile = (x_in_tile, y_in_tile)
            self.pre_wind_tiles = tiles
            self.pre_wind_tiles_cond = tiles_cond
            self.pre_wind_speed = wind_speed
            self.pre_wind_direction = wind_direction
        
        return wind_speed, wind_direction
    
    async def get_altitude_from_tile(self, pos, map_config=None):
        if np.any(np.isnan(pos)):
            return np.nan
        
        if map_config is None:
            map_config = self.config.G_DEM_MAP_CONFIG
        map_name = self.config.G_DEM_MAP
        map_settings = map_config[map_name]
        z = map_settings["fix_zoomlevel"]

        if self.pre_alt_map_name != map_name:
            # Reset altitude cache when DEM source changes.
            self.pre_alt_map_name = map_name
            self.pre_alt_tile_xy = (np.nan, np.nan, np.nan)
            self.pre_alt_xy_in_tile = (np.nan, np.nan, np.nan)
            self.pre_altitude = np.nan
            self.dem_array = None

        pre_zoom = self.pre_alt_tile_xy[2]
        if not np.isnan(pre_zoom):
            tile_x, tile_y, x_in_tile, y_in_tile = get_tilexy_and_xy_in_tile(
                int(pre_zoom), *pos, map_settings["tile_size"]
            )
            if (
                self.pre_alt_tile_xy == (tile_x, tile_y, int(pre_zoom))
                and self.pre_alt_xy_in_tile == (x_in_tile, y_in_tile, int(pre_zoom))
            ):
                return self.pre_altitude

        zoom_candidates = [z, z - 1, z - 2]
        zoom_candidates = [zoom for zoom in zoom_candidates if zoom >= 0]

        for zoom in zoom_candidates:
            map_config_for_zoom = map_config
            if "retry_url" in map_settings and zoom < map_settings["fix_zoomlevel"]:
                map_config_for_zoom = map_config.copy()
                map_config_for_zoom[map_name] = map_settings.copy()
                map_config_for_zoom[map_name]["url"] = map_settings["retry_url"]

            tile_x, tile_y, x_in_tile, y_in_tile = get_tilexy_and_xy_in_tile(
                zoom, *pos, map_settings["tile_size"]
            )
            tiles = [(tile_x, tile_y), ]
            await self.download_maptiles(tiles, map_config_for_zoom, map_name, zoom)

            filename = get_maptile_filename(map_name, zoom, tile_x, tile_y, map_config_for_zoom[map_name])
            if not self.check_existing_tiles(filename):
                if self.network.get_file_download_status(filename) == 404:
                    continue
                return np.nan

            # get altitude
            self.dem_array = np.asarray(Image.open(filename))
            rgb_pos = self.dem_array[y_in_tile, x_in_tile]

            r, g, b = int(rgb_pos[0]), int(rgb_pos[1]), int(rgb_pos[2]) 
            v = (r << 16) | (g << 8) | b
            if map_name.startswith("jpn_kokudo_chiri_in_DEM"):
                if v < (1 << 23):
                    altitude = round(v * 0.01, 1)
                elif v == (1 << 23):
                    altitude =  np.nan
                else:
                    altitude =  round(((v - (1 << 24)) * 0.01), 1)
            elif map_name.startswith("mapbox_terrain"):
                altitude =  round(-10000 + (v * 0.1), 1)
            elif map_name.startswith("mapterhorn"):
                altitude = round((v / 256.0) - 32768.0, 1)
            else:
                altitude = np.nan

            # app_logger.info(f"{altitude}m, {filename}, {x_in_tile}, {x_in_tile}, {pos}")
            self.pre_alt_tile_xy = (tile_x, tile_y, zoom)
            self.pre_alt_xy_in_tile = (x_in_tile, y_in_tile, zoom)
            self.pre_altitude = altitude
            return altitude

        return np.nan
