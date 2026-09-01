import math
import os
import shutil
from urllib.parse import urlparse


def normalize_maptile_ext(ext, default="png"):
    if ext is None:
        return default
    ext = str(ext).strip().lower()
    if ext.startswith("."):
        ext = ext[1:]
    if not ext:
        return default
    if ext == "pngraw":
        return "png"
    return ext


def get_maptile_ext_from_url(url, default="png"):
    if not url:
        return default
    try:
        path = urlparse(str(url)).path
    except Exception:
        path = str(url)
    _, ext = os.path.splitext(path)
    if not ext:
        return default
    return normalize_maptile_ext(ext, default=default)


def get_maptile_filename(map_name, z, x, y, map_settings=None):
    basetime = None
    validtime = None
    ext = "png"
    if map_settings:
        basetime = map_settings.get("basetime")
        validtime = map_settings.get("validtime")
        ext = map_settings.get("ext", ext)
    if basetime and validtime:
        return f"maptile/{map_name}/{basetime}/{validtime}/{z}/{x}/{y}.{ext}"
    else:
        return f"maptile/{map_name}/{z}/{x}/{y}.{ext}"


def get_native_tile_zoom(map_settings, zoom):
    if "native_zoom_levels" in map_settings:
        return max(
            (level for level in map_settings["native_zoom_levels"] if level <= zoom),
            default=None,
        )

    min_zoomlevel = map_settings.get("min_zoomlevel")
    if min_zoomlevel is not None and zoom < min_zoomlevel:
        return None

    max_zoomlevel = map_settings.get("max_zoomlevel")
    if max_zoomlevel is not None and zoom > max_zoomlevel:
        return max_zoomlevel

    return zoom


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
    if not os.path.exists(path) or basetime is None:
        return

    files = os.listdir(path)
    dirs = [f for f in files if f != basetime and os.path.isdir(os.path.join(path, f))]
    for d in dirs:
        shutil.rmtree(os.path.join(path, d))
