import math
import os
import shutil


def get_maptile_filename(map_name, z, x, y, basetime=None, validtime=None):
    if basetime and validtime:
        return f"maptile/{map_name}/{basetime}/{validtime}/{z}/{x}/{y}.png"
    else:
        return f"maptile/{map_name}/{z}/{x}/{y}.png"


def get_lon_lat_from_tile_xy(z, x, y):
    n = 2.0**z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))

    return lon, lat


def get_tilexy_and_xy_in_tile(z, x, y, tile_size):
    n = 2.0**z
    _y = math.radians(y)
    x_in_tile, tile_x = math.modf((x + 180.0) / 360.0 * n)
    y_in_tile, tile_y = math.modf(
        (1.0 - math.log(math.tan(_y) + (1.0 / math.cos(_y))) / math.pi) / 2.0 * n
    )

    return (
        int(tile_x),
        int(tile_y),
        int(x_in_tile * tile_size),
        int(y_in_tile * tile_size),
    )


def remove_maptiles(map_name, basetime):
    path = os.path.join("maptile", map_name)
    if os.path.exists(path):
        files = os.listdir(path)
        dirs = [f for f in files if basetime is not None and f != basetime and os.path.isdir(os.path.join(path, f))]
        for d in dirs:
            shutil.rmtree(os.path.join(path, d))
