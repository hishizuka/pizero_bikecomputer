import math
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse

MAX_MERCATOR_LATITUDE = 85.05112878


def get_rain_time(map_settings, multiplier=1):
    """Return the radar update slot after the provider publication delay."""
    current = map_settings["current_time_func"]()
    current -= timedelta(minutes=map_settings["update_minutes"], seconds=15)
    interval = timedelta(minutes=map_settings["time_interval"] * multiplier)
    epoch = datetime(1970, 1, 1, tzinfo=current.tzinfo)
    return current - (current - epoch) % interval


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


def get_maptile_filename(map_name, z, x, y, map_settings=None, root="maptile"):
    basetime = None
    validtime = None
    ext = "png"
    if map_settings:
        basetime = map_settings.get("basetime")
        validtime = map_settings.get("validtime")
        ext = map_settings.get("ext", ext)
    if basetime and validtime:
        return f"{root}/{map_name}/{basetime}/{validtime}/{z}/{x}/{y}.{ext}"
    else:
        return f"{root}/{map_name}/{z}/{x}/{y}.{ext}"


def get_mbtiles_tile(db, z, x, y, count=False):
    """Use the same wrapped XYZ-to-TMS lookup for both map renderers."""
    column = "count(*)" if count else "tile_data"
    row = db.execute(
        f"SELECT {column} FROM tiles WHERE zoom_level=? "
        "AND tile_column=? AND tile_row=?",
        (z, x % 2**z, 2**z - 1 - y),
    ).fetchone()
    return row[0] if row else None


def get_zoom_delta_from_tile_size(tile_size):
    """Match the existing map's zoom adjustment for larger provider tiles."""
    return int(tile_size / 256) - 1


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


def get_map_tile_plan(settings, zoom, bounds):
    """Select the native parent and display ranges before expanding or prefetching."""
    native_zoom = get_native_tile_zoom(settings, zoom)
    if native_zoom is None:
        return None
    tile_x, tile_y = get_map_tile_range(zoom, bounds)
    return native_zoom, 2 ** (zoom - native_zoom), tile_x, tile_y


def get_lon_lat_from_tile_xy(z, x, y):
    n = 2.0**z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))

    return lon, lat


def get_map_geo_area(z, longitude, latitude, width, height, tile_size):
    """Return the geographic span for logical pixels at the provider's scale."""
    x, y, _, _ = get_tilexy_and_xy_in_tile(z, longitude, latitude, tile_size)
    lon0, lat0 = get_lon_lat_from_tile_xy(z, x, y)
    lon1, lat1 = get_lon_lat_from_tile_xy(z, x + 1, y + 1)
    return abs(lon1 - lon0) * width / tile_size, abs(lat1 - lat0) * height / tile_size


def get_map_tile_range(z, bounds):
    """Return unwrapped X and clipped Y ranges for geographic bounds."""
    lon0, lon1, lat0, lat1 = bounds
    size = 2**z
    tile_x = [math.floor((lon + 180) / 360 * size) for lon in sorted((lon0, lon1))]
    tile_y = [
        get_tilexy_and_xy_in_tile(
            z, lon0, max(-MAX_MERCATOR_LATITUDE, min(MAX_MERCATOR_LATITUDE, lat)), 256
        )[1]
        for lat in sorted((lat0, lat1), reverse=True)
    ]
    return tile_x, [max(0, tile_y[0]), min(size - 1, tile_y[1])]


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


def get_map_tile_coordinates(tile_x, tile_y, factor=1, padding=1):
    """Return visible tiles first, then the border, at the native source zoom."""
    visible = [
        (x, y)
        for x in range(tile_x[0], tile_x[1] + 1)
        for y in range(tile_y[0], tile_y[1] + 1)
    ]
    border = [
        (x, y)
        for x in range(tile_x[0] - padding, tile_x[1] + padding + 1)
        for y in range(tile_y[0] - padding, tile_y[1] + padding + 1)
        if not (tile_x[0] <= x <= tile_x[1] and tile_y[0] <= y <= tile_y[1])
    ]
    return list(dict.fromkeys((x // factor, y // factor) for x, y in visible + border))
