import math
import traceback

import numpy as np

# TODO use Decimal not floats

# for get_dist_on_earth
GEO_R1 = 6378.137
GEO_R2 = 6356.752314140
GEO_R1_2 = (GEO_R1 * 1000) ** 2
GEO_R2_2 = (GEO_R2 * 1000) ** 2
GEO_E2 = (GEO_R1_2 - GEO_R2_2) / GEO_R1_2
G_DISTANCE_BY_LAT1S = GEO_R2 * 1000 * 2 * np.pi / 360 / 60 / 60  # [m]

# for track
TRACK_STR = [
    "N",
    "NE",
    "E",
    "SE",
    "S",
    "SW",
    "W",
    "NW",
    "N",
]


def calc_azimuth(lat, lon):
    rad_latitude = np.radians(lat)
    rad_longitude = np.radians(lon)
    rad_longitude_delta = rad_longitude[1:] - rad_longitude[0:-1]
    azimuth = np.mod(
        np.degrees(
            np.arctan2(
                np.sin(rad_longitude_delta),
                np.cos(rad_latitude[0:-1]) * np.tan(rad_latitude[1:])
                - np.sin(rad_latitude[0:-1]) * np.cos(rad_longitude_delta),
            )
        ),
        360,
    ).astype(dtype="int16")
    return azimuth


def calc_y_mod(lat):
    if np.isnan(lat):
        return np.nan
    return GEO_R2 / (GEO_R1 * math.cos(lat / 180 * np.pi))


# return [m]
def get_dist_on_earth(p0_lon, p0_lat, p1_lon, p1_lat):
    if p0_lon == p1_lon and p0_lat == p1_lat:
        return 0
    (r0_lon, r0_lat, r1_lon, r1_lat) = map(
        math.radians, [p0_lon, p0_lat, p1_lon, p1_lat]
    )
    delta_x = r1_lon - r0_lon
    cos_d = math.sin(r0_lat) * math.sin(r1_lat) + math.cos(r0_lat) * math.cos(
        r1_lat
    ) * math.cos(delta_x)
    try:
        res = 1000 * math.acos(cos_d) * GEO_R1
        return res
    except:
        # traceback.print_exc()
        # print("cos_d =", cos_d)
        # print("parameter:", p0_lon, p0_lat, p1_lon, p1_lat)
        return 0


# return [m]
def get_dist_on_earth_array(p0_lon, p0_lat, p1_lon, p1_lat):
    # if p0_lon == p1_lon and p0_lat == p1_lat:
    #  return 0
    r0_lon = np.radians(p0_lon)
    r0_lat = np.radians(p0_lat)
    r1_lon = np.radians(p1_lon)
    r1_lat = np.radians(p1_lat)
    # (r0_lon, r0_lat, r1_lon, r1_lat) = map(radians, [p0_lon, p0_lat, p1_lon, p1_lat])
    delta_x = r1_lon - r0_lon
    cos_d = np.sin(r0_lat) * np.sin(r1_lat) + np.cos(r0_lat) * np.cos(r1_lat) * np.cos(
        delta_x
    )
    try:
        res = 1000 * np.arccos(cos_d) * GEO_R1
        return res
    except:
        traceback.print_exc()
        #  #print("cos_d =", cos_d)
        #  #print("parameter:", p0_lon, p0_lat, p1_lon, p1_lat)
        return np.array([])


# return [m]
def get_dist_on_earth_hubeny(p0_lon, p0_lat, p1_lon, p1_lat):
    if p0_lon == p1_lon and p0_lat == p1_lat:
        return 0
    (r0_lon, r0_lat, r1_lon, r1_lat) = map(
        math.radians, [p0_lon, p0_lat, p1_lon, p1_lat]
    )
    lat_t = (r0_lat + r1_lat) / 2
    w = 1 - GEO_E2 * math.sin(lat_t) ** 2
    c2 = math.cos(lat_t) ** 2
    return math.sqrt(
        (GEO_R2_2 / w**3) * (r0_lat - r1_lat) ** 2
        + (GEO_R1_2 / w) * c2 * (r0_lon - r1_lon) ** 2
    )


def get_mod_lat(lat):
    return lat * calc_y_mod(lat)


def get_mod_lat_np(lat):
    return lat * GEO_R2 / (GEO_R1 * np.cos(lat / 180 * np.pi))


def get_track_str(drc):
    if np.isnan(drc):
        return None
    track_int = int((drc + 22.5) / 45.0)
    return TRACK_STR[track_int]


def get_width_distance(lat, w):
    return w * GEO_R1 * 1000 * 2 * np.pi * math.cos(lat / 180 * np.pi) / 360
