import os
from datetime import datetime, timedelta, timezone  #datetime is necessary for map_config["current_time_func"]()
from random import random
import asyncio

import numpy as np
from PIL import Image

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
SCW_VALUE_SEARCH_RADIUS = 8
SCW_MONTHS = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)

# Bin colors sampled from SCW forecast tiles; 80+ follows the same HSV ramp.
SCW_PRECIPITATION_COLOR = np.array(
    [
        [147, 112, 219],
        [95, 72, 232],
        [42, 32, 245],
        [0, 18, 255],
        [0, 109, 255],
        [0, 200, 255],
        [0, 255, 219],
        [0, 255, 128],
        [0, 255, 36],
        [55, 255, 0],
        [146, 255, 0],
        [237, 255, 0],
        [255, 182, 0],
        [255, 91, 0],
        [255, 0, 0],
    ],
    dtype="uint8",
)
SCW_PRECIPITATION_VALUE = np.array(
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 15, 25, 40, 65, 80]
)
SCW_CLOUD_COLOR = np.array(
    [[gray, gray, gray] for gray in range(0, 181, 20)], dtype="uint8"
)
SCW_CLOUD_VALUE = np.array([0, 15, 25, 35, 45, 55, 65, 75, 85, 100])
SCW_TEMPERATURE_COLOR = np.array(
    [
        [0, 0, 205],
        [0, 0, 227],
        [0, 0, 249],
        [0, 19, 255],
        [0, 45, 255],
        [0, 70, 255],
        [0, 96, 255],
        [0, 121, 255],
        [0, 147, 255],
        [0, 172, 255],
        [0, 198, 255],
        [0, 223, 255],
        [0, 249, 255],
        [0, 255, 219],
        [0, 255, 170],
        [0, 255, 121],
        [0, 255, 73],
        [0, 255, 24],
        [26, 255, 0],
        [77, 255, 0],
        [128, 255, 0],
        [179, 255, 0],
        [230, 255, 0],
        [255, 244, 0],
        [255, 221, 0],
        [255, 199, 0],
        [255, 176, 0],
        [255, 157, 0],
        [255, 140, 0],
        [255, 124, 0],
        [255, 107, 0],
        [255, 91, 0],
        [255, 74, 0],
        [255, 58, 0],
    ],
    dtype="uint8",
)
# Midpoints of the verified 3-4 through 36-37 degree Celsius bins.
SCW_TEMPERATURE_VALUE = np.arange(3.5, 37.5)


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
    return await get_json(url, headers={"referer": referer})


def _parse_scw_validtime(value):
    return datetime(
        int(value[10:14]),
        SCW_MONTHS.index(value[7:10]) + 1,
        int(value[5:7]),
        int(value[0:2]),
        int(value[2:4]),
        tzinfo=timezone.utc,
    )


def conv_colorcode(t):
    return f"#{t[0]:02X}{t[1]:02X}{t[2]:02X}"


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
        return list(SCW_WIND_SPEED_ARROW_CONV[-1])
    return list(SCW_WIND_SPEED_ARROW_CONV[max(idx-1, 0)])


def _get_nearest_palette_index(color, palette):
    dist = np.linalg.norm(
        palette.astype("int16") - np.asarray(color[:3], dtype="int16"), axis=1
    )
    index = np.argmin(dist)
    return int(index) if dist[index] < 10 else None


def _get_palette_values(colors, palettes):
    matches = [[] for _ in palettes]
    for color in colors:
        for palette_index, (palette, values) in enumerate(palettes):
            color_index = _get_nearest_palette_index(color, palette)
            if color_index is None:
                continue
            matches[palette_index].append(float(values[color_index]))
            break

    for palette_index, values in enumerate(matches):
        if values:
            return palette_index, values
    return None, []


def _iter_colors_at_radius(image, x, y, radius):
    width, height = image.size
    for pixel_y in range(max(y - radius, 0), min(y + radius + 1, height)):
        for pixel_x in range(max(x - radius, 0), min(x + radius + 1, width)):
            if max(abs(pixel_x - x), abs(pixel_y - y)) != radius:
                continue
            yield image.getpixel((pixel_x, pixel_y))


def _get_nearest_palette_values(image, x, y, palettes):
    color = image.getpixel((x, y))
    palette_index, values = _get_palette_values((color,), palettes)
    if values:
        return palette_index, values

    if color[0] != color[1] or color[1] != color[2]:
        return None, []

    for radius in range(1, SCW_VALUE_SEARCH_RADIUS + 1):
        palette_index, values = _get_palette_values(
            _iter_colors_at_radius(image, x, y, radius), palettes
        )
        if values:
            return palette_index, values
    return None, []


def get_precipitation_cloud_with_tile_xy(image, x_in_tile, y_in_tile):
    palette_index, values = _get_nearest_palette_values(
        image,
        x_in_tile,
        y_in_tile,
        (
            (SCW_PRECIPITATION_COLOR, SCW_PRECIPITATION_VALUE),
            (SCW_CLOUD_COLOR, SCW_CLOUD_VALUE),
        ),
    )
    if not values:
        return np.nan, np.nan

    value = float(np.median(values))
    if palette_index == 0:
        return value, np.nan
    return 0.0, value


def get_temperature_with_tile_xy(image, x_in_tile, y_in_tile):
    _, values = _get_nearest_palette_values(
        image,
        x_in_tile,
        y_in_tile,
        ((SCW_TEMPERATURE_COLOR, SCW_TEMPERATURE_VALUE),),
    )
    return float(np.median(values)) if values else np.nan


def conv_image_internal(image, orig_colors, conv_colors):

    wing_speed_mod = []
    wing_speed_index = []
    colors = image.getcolors(image.size[0]*image.size[1])
    for c in colors:
        if c[1][0] == c[1][1] == c[1][2]:
            continue
        min_index = _get_nearest_palette_index(c[1], orig_colors)
        if min_index is not None:
            wing_speed_mod.append(c[1])
            wing_speed_index.append(min_index)

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


def get_wind_with_tile_xy(
    img_files,
    x_in_tile,
    y_in_tile,
    tilesize,
    tiles_cond,
    image,
    arrow_mask,
):
    def get_marginal_contour(x, y, contour_count, mask, index):
        for j in range(y - 1, y + 2):
            if j < 0 or j >= mask.shape[0]:
                continue
            for i in range(x - 1, x + 2):
                if i < 0 or i >= mask.shape[1]:
                    continue
                if mask[j, i] and not index[j, i]:
                    index[j, i] = contour_count
                    get_marginal_contour(i, j, contour_count, mask, index)

    x = x_in_tile + (tilesize if tiles_cond[0] < 0 else 0)
    y = y_in_tile + (tilesize if tiles_cond[1] < 0 else 0)

    if image is None:
        columns = 2 if tiles_cond[0] else 1
        rows = 2 if tiles_cond[1] else 1
        image = Image.new("RGB", (tilesize * columns, tilesize * rows))
        for index, filename in enumerate(img_files):
            row, column = divmod(index, columns)
            with Image.open(filename) as tile:
                image.paste(tile.convert("RGB"), (tilesize * column, tilesize * row))

    _, wind_speeds = _get_nearest_palette_values(
        image,
        x,
        y,
        ((SCW_WIND_SPEED_COLOR, SCW_WIND_SPEED_COLOR_VALUE),),
    )
    wind_speed = round(np.average(wind_speeds), 1) if wind_speeds else np.nan

    # get wind_direction
    wind_direction = 0

    if arrow_mask is None:
        arrow_colors = [
            color
            for _, color in image.getcolors(image.size[0] * image.size[1])
            if _get_nearest_palette_index(color, SCW_WIND_SPEED_ARROW) is not None
        ]

        image_array = np.asarray(image)
        arrow_mask = np.zeros(image_array.shape[:2], dtype=bool)
        for color in arrow_colors:
            arrow_mask |= np.all(image_array == color, axis=2)

    # Detect arrows in the local search area around the requested position.
    x_border = [
        max(x - SCW_WIND_ARROW_MARGIN, 0),
        min(x + SCW_WIND_ARROW_MARGIN, arrow_mask.shape[1]),
    ]
    y_border = [
        max(y - SCW_WIND_ARROW_MARGIN, 0),
        min(y + SCW_WIND_ARROW_MARGIN, arrow_mask.shape[0]),
    ]

    local_mask = arrow_mask[
        y_border[0] : y_border[1],
        x_border[0] : x_border[1],
    ]
    index = np.zeros(local_mask.shape, dtype="uint8")
    contour_count = 1
    for j in range(local_mask.shape[0]):
        for i in range(local_mask.shape[1]):
            if local_mask[j, i] and not index[j, i]:
                index[j, i] = contour_count
                get_marginal_contour(
                    i,
                    j,
                    contour_count,
                    local_mask,
                    index,
                )
                contour_count += 1

    xy_in_search_area = np.array([x - x_border[0], y - y_border[0]])
    dist_min = np.inf
    for contour in range(1, contour_count):
        points = np.argwhere(index == contour)[:, ::-1]
        if len(points) < SCW_WIND_ARROW_PIXEL_COUNT:
            continue
        x = points[:, 0]
        y = points[:, 1]
        min_width, max_width = x.min(), x.max()
        min_height, max_height = y.min(), y.max()
        min_width_point = points[np.flatnonzero(x == min_width)[0]]
        max_width_point = points[np.flatnonzero(x == max_width)[0]]
        min_height_point = points[np.flatnonzero(y == min_height)[0]]
        max_height_point = points[np.flatnonzero(y == max_height)[0]]
        centroid = points.mean(axis=0)
        center = np.array(
            [(min_width + max_width) / 2, (min_height + max_height) / 2]
        )

        if max_width - min_width > max_height - min_height:
            if centroid[0] > center[0]:
                x_y = max_width_point - min_width_point
                start = min_width_point
            else:
                x_y = min_width_point - max_width_point
                start = max_width_point
        else:
            if centroid[1] > center[1]:
                x_y = max_height_point - min_height_point
                start = min_height_point
            else:
                x_y = min_height_point - max_height_point
                start = max_height_point

        d = round(np.degrees(np.arctan2(x_y[1], x_y[0]))) - 90
        if d < 0:
            d += 360

        dist = np.linalg.norm(start - xy_in_search_area)
        if dist < dist_min:
            wind_direction = d
            dist_min = dist

    return wind_speed, wind_direction, image, arrow_mask


class MapTileWithValues():
    config = None

    existing_tiles = {}
    
    # for jpn_kokudo_chiri_in_DEM~
    pre_alt_map_name = None
    pre_alt_tile_xy = (np.nan, np.nan, np.nan)
    pre_alt_xy_in_tile = (np.nan, np.nan, np.nan)
    pre_altitude = np.nan
    dem_array = None

    def __init__(self, config):
        self.config = config
        self.get_scw_lock = False
        self.wind_tile_cache_key = None
        self.wind_position_cache_key = None
        self.wind_result = (np.nan, np.nan)
        self.wind_image = None
        self.wind_arrow_mask = None

    @property
    def network(self):
        return self.config.network

    @staticmethod
    def get_tiles(tile_x, tile_y, tiles_cond):
        offsets = {-1: (-1, 0), 0: (0,), 1: (0, 1)}
        x_offsets = offsets[tiles_cond[0]]
        y_offsets = offsets[tiles_cond[1]]
        return [
            [tile_x + x_offset, tile_y + y_offset]
            for y_offset in y_offsets
            for x_offset in x_offsets
        ]

    @staticmethod
    def _decode_dem_altitude(rgb_pos, map_name):
        r, g, b = int(rgb_pos[0]), int(rgb_pos[1]), int(rgb_pos[2])
        value = (r << 16) | (g << 8) | b

        if map_name.startswith("jpn_kokudo_chiri_in_DEM"):
            if value < (1 << 23):
                return round(value * 0.01, 1)
            if value == (1 << 23):
                return np.nan
            return round((value - (1 << 24)) * 0.01, 1)
        if map_name.startswith("mapbox_terrain"):
            return round(-10000 + (value * 0.1), 1)
        if map_name.startswith("mapterhorn"):
            return round((value / 256.0) - 32768.0, 1)
        return np.nan

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
                await self.update_jpn_scw_timeline(map_settings)
            else:
                asyncio.create_task(self.update_jpn_scw_timeline(map_settings))
            return

        if not self.update_overlay_wind_basetime(map_settings):
            return
        # basetime update
        basetime_str = map_settings["current_time"].strftime(
            map_settings["time_format"]
        )
        map_settings["basetime"] = basetime_str
        map_settings["validtime"] = map_settings["basetime"]

    async def update_jpn_scw_timeline(self, map_settings):
        self.update_overlay_wind_basetime(map_settings)
        if map_settings["timeline_update_date"] == map_settings["current_time"]:
            return

        self.get_scw_lock = True
        try:
            f_name = self.update_jpn_scw_timeline.__name__
            async with self.network.bt_tethering_session(f_name) as connected:
                if not connected:
                    return

                # app_logger.info("get_scw_list connection start...")
                url = map_settings["inittime"].format(rand=random())
                init_time_list = await get_scw_list(url, map_settings["referer"])
                if init_time_list is None:
                    return
                basetime = init_time_list[0]["it"]

                url = map_settings["fl"].format(basetime=basetime, rand=random())
                timeline = await get_scw_list(url, map_settings["referer"])
        finally:
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

        if not self.network.check_network_with_bt_tethering():
            return

        past_url = map_settings.get("past_time_list")
        forecast_url = map_settings.get("forcast_time_list")
        if not past_url and not forecast_url:
            return

        f_name = self.update_jpn_jma_bousai_timeline.__name__
        async with self.network.bt_tethering_session(f_name) as connected:
            if not connected:
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
        current_time = map_settings.pop("_precomputed_current_time", None)
        if current_time is None:
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
        current_time = map_settings.pop("_precomputed_current_time", None)
        if current_time is None:
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

    @staticmethod
    def _get_scw_forecast_map_config(map_config, map_name, forecast_time):
        map_settings = map_config[map_name].copy()
        if map_settings["timeline"] is None:
            return None

        closest = min(
            map_settings["timeline"],
            key=lambda entry: abs(_parse_scw_validtime(entry["it"]) - forecast_time),
        )

        map_settings["validtime"] = closest["it"]
        map_settings["subdomain"] = closest["sd"]
        return {map_name: map_settings}

    @staticmethod
    def _get_scw_layer_map_config(map_name, map_settings, layer_name):
        layer = map_settings["layers"][layer_name]
        wind_layer = map_settings["layers"]["wind"]
        layer_map_name = f"{map_name}_{layer}"
        layer_settings = map_settings.copy()
        layer_settings["url"] = map_settings["url"].replace(
            f"/{wind_layer}/", f"/{layer}/"
        )
        return {layer_map_name: layer_settings}, layer_map_name

    async def _get_scw_layer_value(
        self, pos, forecast_time, map_name, layer_name, extractor
    ):
        map_config = self.config.G_WIND_OVERLAY_MAP_CONFIG
        map_settings = map_config[map_name]
        z = map_settings["max_zoomlevel"]
        tilesize = map_settings["tile_size"]
        if np.any(np.isnan(pos)):
            return None

        tile_x, tile_y, x_in_tile, y_in_tile = get_tilexy_and_xy_in_tile(
            z, *pos, tilesize
        )
        await self.update_overlay_windmap_timeline(map_settings, map_name, wait=True)
        forecast_map_config = self._get_scw_forecast_map_config(
            map_config, map_name, forecast_time
        )
        if forecast_map_config is None:
            return None

        layer_map_config, layer_map_name = self._get_scw_layer_map_config(
            map_name,
            forecast_map_config[map_name],
            layer_name,
        )
        layer_settings = layer_map_config[layer_map_name]
        tile = (tile_x, tile_y)
        await self.download_maptiles([tile], layer_map_config, layer_map_name, z)
        filename = get_maptile_filename(layer_map_name, z, *tile, layer_settings)
        if not self.check_existing_tiles(filename):
            return None

        with Image.open(filename) as image:
            return extractor(image.convert("RGB"), x_in_tile, y_in_tile)

    async def get_precipitation_cloud(self, pos, forecast_time, map_name):
        return await self._get_scw_layer_value(
            pos,
            forecast_time,
            map_name,
            "precipitation_cloud",
            get_precipitation_cloud_with_tile_xy,
        )

    async def get_temperature(self, pos, forecast_time, map_name):
        return await self._get_scw_layer_value(
            pos,
            forecast_time,
            map_name,
            "temperature",
            get_temperature_with_tile_xy,
        )

    async def get_course_weather(self, pos, forecast_time, map_name):
        wind_speed, wind_direction = await self.get_wind(pos, forecast_time, map_name)
        if np.any(np.isnan((wind_speed, wind_direction))):
            return None

        precipitation_cloud = await self.get_precipitation_cloud(
            pos, forecast_time, map_name
        )
        if precipitation_cloud is None:
            return None

        temperature = await self.get_temperature(pos, forecast_time, map_name)
        if temperature is None or np.isnan(temperature):
            return None

        precipitation, cloud_cover = precipitation_cloud
        return {
            "wind_speed": float(wind_speed),
            "wind_direction": float(wind_direction),
            "temperature": temperature,
            "precipitation": precipitation,
            "cloud_cover": cloud_cover,
        }

    async def get_wind(self, pos, forecast_time=None, map_name=None):
        map_config = self.config.G_WIND_OVERLAY_MAP_CONFIG
        if map_name is None:
            map_name = self.config.G_WIND_DATA_SOURCE
        map_settings = map_config[map_name]
        z = map_settings["max_zoomlevel"]
        tilesize = map_settings["tile_size"]
        is_current = forecast_time is None

        if np.any(np.isnan(pos)):
            return np.nan, np.nan

        # initialize
        tile_x, tile_y, x_in_tile, y_in_tile = get_tilexy_and_xy_in_tile(
            z, *pos, tilesize
        )
        await self.update_overlay_windmap_timeline(
            map_settings, map_name, wait=not is_current
        )

        # check marginal tile
        tiles_cond = [
            (
                -1
                if value < SCW_WIND_ARROW_MARGIN
                else 1 if value > tilesize - SCW_WIND_ARROW_MARGIN else 0
            )
            for value in (x_in_tile, y_in_tile)
        ]
        # tile check and download
        tiles = self.get_tiles(tile_x, tile_y, tiles_cond)

        if is_current:
            wind_tile_cache_key = (
                map_name,
                map_settings["basetime"],
                map_settings["validtime"],
                tuple(map(tuple, tiles)),
            )
            wind_position_cache_key = wind_tile_cache_key + (
                x_in_tile,
                y_in_tile,
            )
            if (
                self.wind_position_cache_key == wind_position_cache_key
                and self.wind_image is not None
            ):
                return self.wind_result

        _map_config = map_config
        _map_settings = map_settings
        if not is_current:
            _map_config = self._get_scw_forecast_map_config(
                map_config, map_name, forecast_time
            )
            if _map_config is None:
                return np.nan, np.nan
            _map_settings = _map_config[map_name]

        await self.download_maptiles(tiles, _map_config, map_name, z)

        tile_files = [
            get_maptile_filename(map_name, z, *tile, _map_settings) for tile in tiles
        ]

        # download in progress
        if not all(self.check_existing_tiles(filename) for filename in tile_files):
            if is_current:
                self.wind_image = None
                self.wind_arrow_mask = None
                self.wind_tile_cache_key = None
                self.wind_position_cache_key = None
                return self.wind_result
            return np.nan, np.nan

        if is_current and self.wind_tile_cache_key != wind_tile_cache_key:
            self.wind_image = None
            self.wind_arrow_mask = None

        (
            wind_speed,
            wind_direction,
            wind_image,
            wind_arrow_mask,
        ) = get_wind_with_tile_xy(
            tile_files,
            x_in_tile,
            y_in_tile,
            tilesize,
            tiles_cond,
            self.wind_image if is_current else None,
            self.wind_arrow_mask if is_current else None,
        )
        if is_current:
            self.wind_image = wind_image
            self.wind_arrow_mask = wind_arrow_mask
            self.wind_tile_cache_key = wind_tile_cache_key
            self.wind_position_cache_key = wind_position_cache_key
            self.wind_result = (wind_speed, wind_direction)

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
            cached_zoom = int(pre_zoom)
            tile_x, tile_y, x_in_tile, y_in_tile = get_tilexy_and_xy_in_tile(
                cached_zoom, *pos, map_settings["tile_size"]
            )
            if (
                self.pre_alt_tile_xy == (tile_x, tile_y, cached_zoom)
                and self.pre_alt_xy_in_tile == (x_in_tile, y_in_tile, cached_zoom)
            ):
                return self.pre_altitude
            if (
                self.pre_alt_tile_xy == (tile_x, tile_y, cached_zoom)
                and self.dem_array is not None
                and y_in_tile >= 0
                and x_in_tile >= 0
                and y_in_tile < self.dem_array.shape[0]
                and x_in_tile < self.dem_array.shape[1]
            ):
                altitude = self._decode_dem_altitude(
                    self.dem_array[y_in_tile, x_in_tile],
                    map_name,
                )
                self.pre_alt_xy_in_tile = (x_in_tile, y_in_tile, cached_zoom)
                self.pre_altitude = altitude
                return altitude

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
            altitude = self._decode_dem_altitude(
                self.dem_array[y_in_tile, x_in_tile],
                map_name,
            )

            # app_logger.info(f"{altitude}m, {filename}, {x_in_tile}, {x_in_tile}, {pos}")
            self.pre_alt_tile_xy = (tile_x, tile_y, zoom)
            self.pre_alt_xy_in_tile = (x_in_tile, y_in_tile, zoom)
            self.pre_altitude = altitude
            return altitude

        return np.nan
