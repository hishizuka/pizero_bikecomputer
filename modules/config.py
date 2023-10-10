import argparse
import asyncio
import datetime
import json
import logging
import os
import shutil
import traceback
import math
from glob import glob

import numpy as np
import oyaml as yaml
from PIL import Image


_IS_RASPI = False
try:
    import RPi.GPIO as GPIO

    GPIO.setmode(GPIO.BCM)
    _IS_RASPI = True
except ImportError:
    pass

from logger import CustomRotatingFileHandler, app_logger
from modules.helper.setting import Setting
from modules.button_config import Button_Config
from modules.utils.cmd import (
    exec_cmd,
    exec_cmd_return_value,
    is_running_as_service,
)
from modules.utils.timer import Timer


BOOT_FILE = "/boot/config.txt"


class Config:
    #######################
    # configurable values #
    #######################

    # loop interval
    G_SENSOR_INTERVAL = 1.0  # [s] for sensor_core
    G_ANT_INTERVAL = 1.0  # [s] for ANT+. 0.25, 0.5, 1.0 only.
    G_I2C_INTERVAL = 1.0  # 0.2 #[s] for I2C (altitude, accelerometer, etc)
    G_GPS_INTERVAL = 1.0  # [s] for GPS
    G_DRAW_INTERVAL = 1000  # [ms] for GUI (QtCore.QTimer)
    G_LOGGING_INTERVAL = 1.0  # [s] for logger_core (log interval)
    G_REALTIME_GRAPH_INTERVAL = 1000  # 200 #[ms] for pyqt_graph

    # log format switch
    G_LOG_WRITE_CSV = True
    G_LOG_WRITE_FIT = True

    # average including ZERO when logging
    G_AVERAGE_INCLUDING_ZERO = {"cadence": False, "power": True}

    # log several altitudes (from DEM and course file)
    G_LOG_ALTITUDE_FROM_DATA_SOURCE = False

    # calculate index on course
    G_COURSE_INDEXING = True

    # gross average speed
    G_GROSS_AVE_SPEED = 15  # [km/h]

    # W'bal
    G_POWER_CP = 150
    G_POWER_W_PRIME = 15000
    G_POWER_W_PRIME_ALGORITHM = "WATERWORTH"  # WATERWORTH, DIFFERENTIAL

    ###########################
    # fixed or pointer values #
    ###########################

    # product name, version
    G_PRODUCT = "Pizero Bikecomputer"
    G_VERSION_MAJOR = 0  # need to be initialized
    G_VERSION_MINOR = 1  # need to be initialized
    G_UNIT_ID = "0000000000000000"  # initialized in get_serial
    G_UNIT_ID_HEX = 0x1A2B3C4D  # initialized in get_serial
    G_UNIT_MODEL = ""
    G_UNIT_HARDWARE = ""

    # layout def
    G_LAYOUT_FILE = "layout.yaml"

    # Language defined by G_LANG in gui_config.py
    G_LANG = "EN"
    G_FONT_FILE = ""

    # courses
    G_COURSE_DIR = "courses"
    G_COURSE_FILE_PATH = os.path.join(G_COURSE_DIR, ".current")
    G_CUESHEET_DISPLAY_NUM = 3  # max: 5
    G_CUESHEET_SCROLL = False
    G_OBEXD_CMD = "/usr/libexec/bluetooth/obexd"
    G_RECEIVE_COURSE_FILE = "bluetooth_content_share.html"

    # log setting
    G_LOG_DIR = "log"
    G_LOG_DB = os.path.join(G_LOG_DIR, "log.db")
    G_LOG_DEBUG_FILE = os.path.join(G_LOG_DIR, "debug.log")
    G_LOG_START_DATE = None

    # asyncio semaphore
    G_COROUTINE_SEM = 100

    # map setting
    # default map (can overwrite in settings.conf)
    G_MAP = "toner"
    G_MAP_CONFIG = {
        # basic map
        "toner": {
            # 0:z(zoom), 1:tile_x, 2:tile_y
            "url": "https://stamen-tiles.a.ssl.fastly.net/toner/{z}/{x}/{y}.png",
            "attribution": "Map tiles by Stamen Design, under CC BY 3.0.<br />Data by OpenStreetMap, under ODbL",
            "tile_size": 256,
        },
        "toner-lite": {
            # 0:z(zoom), 1:tile_x, 2:tile_y
            "url": "https://stamen-tiles.a.ssl.fastly.net/toner-lite/{z}/{x}/{y}.png",
            "attribution": "Map tiles by Stamen Design, under CC BY 3.0.<br />Data by OpenStreetMap, under ODbL",
            "tile_size": 256,
        },
        "toner_2x": {
            # 0:z(zoom), 1:tile_x, 2:tile_y
            "url": "https://stamen-tiles.a.ssl.fastly.net/toner/{z}/{x}/{y}@2x.png",
            "attribution": "Map tiles by Stamen Design, under CC BY 3.0.<br />Data by OpenStreetMap, under ODbL",
            "tile_size": 512,
        },
        "toner-terrain": {
            # 0:z(zoom), 1:tile_x, 2:tile_y
            "url": "https://stamen-tiles.a.ssl.fastly.net/terrain/{z}/{x}/{y}.png",
            "attribution": "Map tiles by Stamen Design, under CC BY 3.0.<br />Data by OpenStreetMap, under ODbL",
            "tile_size": 256,
        },
        "wikimedia": {
            "url": "https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}.png",
            "attribution": "© OpenStreetMap contributors",
            "referer": "https://maps.wikimedia.org/",
            "tile_size": 256,
        },
        "wikimedia_2x": {
            "url": "https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}@2x.png",
            "attribution": "© OpenStreetMap contributors",
            "referer": "https://maps.wikimedia.org/",
            "tile_size": 512,
        },
        # japanese tile
        "jpn_kokudo_chiri_in": {
            "url": "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
            "attribution": "国土地理院",
            "tile_size": 256,
        },
    }

    G_HEATMAP_OVERLAY_MAP_CONFIG = {
        "rwg_heatmap": {
            # start_color: low, white(FFFFFF) is recommended.
            # end_color: high, any color you like.
            "url": "https://heatmap.ridewithgps.com/normalized/{z}/{x}/{y}.png?start_color=%23FFFFFF&end_color=%23FF8800",
            "attribution": "Ride with GPS",
            "tile_size": 256,
            "max_zoomlevel": 16,
            "min_zoomlevel": 10,
        },
        # strava heatmap
        # https://wiki.openstreetmap.org/wiki/Strava
        # bluered / hot / blue / purple / gray
        "strava_heatmap_bluered": {
            "url": "https://heatmap-external-b.strava.com/tiles-auth/ride/bluered/{z}/{x}/{y}.png?px=256&Key-Pair-Id={key_pair_id}&Policy={policy}&Signature={signature}",
            "attribution": "STRAVA",
            "tile_size": 256,
            "max_zoomlevel": 16,
            "min_zoomlevel": 10,
        },
        "strava_heatmap_hot": {
            "url": "https://heatmap-external-b.strava.com/tiles-auth/ride/hot/{z}/{x}/{y}.png?px=256&Key-Pair-Id={key_pair_id}&Policy={policy}&Signature={signature}",
            "attribution": "STRAVA",
            "tile_size": 256,
            "max_zoomlevel": 16,
            "min_zoomlevel": 10,
        },
        "strava_heatmap_blue": {
            "url": "https://heatmap-external-b.strava.com/tiles-auth/ride/blue/{z}/{x}/{y}.png?px=256&Key-Pair-Id={key_pair_id}&Policy={policy}&Signature={signature}",
            "attribution": "STRAVA",
            "tile_size": 256,
            "max_zoomlevel": 16,
            "min_zoomlevel": 10,
        },
        "strava_heatmap_purple": {
            "url": "https://heatmap-external-b.strava.com/tiles-auth/ride/purple/{z}/{x}/{y}.png?px=256&Key-Pair-Id={key_pair_id}&Policy={policy}&Signature={signature}",
            "attribution": "STRAVA",
            "tile_size": 256,
            "max_zoomlevel": 16,
            "min_zoomlevel": 10,
        },
        "strava_heatmap_gray": {
            "url": "https://heatmap-external-b.strava.com/tiles-auth/ride/gray/{z}/{x}/{y}.png?px=256&Key-Pair-Id={key_pair_id}&Policy={policy}&Signature={signature}",
            "attribution": "STRAVA",
            "tile_size": 256,
            "max_zoomlevel": 16,
            "min_zoomlevel": 10,
        },
    }

    G_RAIN_OVERLAY_MAP_CONFIG = {
        # worldwide rain tile
        "rainviewer": {
            "url": "https://tilecache.rainviewer.com/v2/radar/{basetime}/256/{z}/{x}/{y}/6/1_1.png",
            "attribution": "RainViewer",
            "tile_size": 256,
            "max_zoomlevel": 18,
            "min_zoomlevel": 1,
            "time_list": "https://api.rainviewer.com/public/weather-maps.json",
            "nowtime": None,
            "nowtime_func": datetime.datetime.now,  # local?
            "basetime": None,
            "time_interval": 10,  # [minutes]
            "update_minutes": 1,  # typically int(time_interval/2) [minutes]
            "time_format": "unix_timestamp",
        },
        # japanese rain tile
        "jpn_jma_bousai": {
            "url": "https://www.jma.go.jp/bosai/jmatile/data/nowc/{basetime}/none/{validtime}/surf/hrpns/{z}/{x}/{y}.png",
            "attribution": "Japan Meteorological Agency",
            "tile_size": 256,
            "max_zoomlevel": 10,
            "min_zoomlevel": 4,
            "past_time_list": "https://www.jma.go.jp/bosai/jmatile/data/nowc/targetTimes_N1.json",
            "forcast_time_list": "https://www.jma.go.jp/bosai/jmatile/data/nowc/targetTimes_N2.json",
            "nowtime": None,
            "nowtime_func": datetime.datetime.utcnow,
            "basetime": None,
            "validtime": None,
            "time_interval": 5,  # [minutes]
            "update_minutes": 1,  # [minutes]
            "time_format": "%Y%m%d%H%M%S",
        },
    }

    G_WIND_OVERLAY_MAP_CONFIG = {
        # worldwide wind tile
        # https://weather.openportguide.de/index.php/en/weather-forecasts/weather-tiles
        "openportguide": {
            "url": "https://weather.openportguide.de/tiles/actual/wind_stream/0h/{z}/{x}/{y}.png",
            "attribution": "openportguide",
            "tile_size": 256,
            "max_zoomlevel": 7,
            "min_zoomlevel": 0,
            "nowtime": None,
            "nowtime_func": datetime.datetime.utcnow,
            "basetime": None,
            "validtime": None,
            "time_interval": 60,  # [minutes]
            "update_minutes": 30,  # [minutes]
            "time_format": "%H%MZ%d%b%Y",
        },
        # japanese wind tile
        "jpn_scw": {
            "url": "https://{subdomain}.supercweather.com/tl/msm/{basetime}/{validtime}/wa/{z}/{x}/{y}.png",
            "attribution": "SCW",
            "tile_size": 256,
            "max_zoomlevel": 8,
            "min_zoomlevel": 8,
            "inittime": "https://k2.supercweather.com/tl/msm/initime.json?rand={rand}",
            "fl": "https://k2.supercweather.com/tl/msm/{basetime}/fl.json?rand={rand}",
            "nowtime": None,
            "nowtime_func": datetime.datetime.utcnow,
            "timeline": None,
            "basetime": None,
            "validtime": None,
            "subdomain": None,
            "time_interval": 60,  # [minutes]
            "update_minutes": 30,  # [minutes]
            "time_format": "%H%MZ%d%b%Y",  # need upper()
            "referer": "https://supercweather.com/",
        },
    }

    G_DEM_MAP_CONFIG = {
        # worldwide DEM(Digital Elevation Model) map
        # japanese DEM(Digital Elevation Model) map
        "jpn_kokudo_chiri_in_DEM5A": {
            "url": "https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png",  # DEM5A
            "attribution": "国土地理院",
            "fix_zoomlevel": 15,
        },
        "jpn_kokudo_chiri_in_DEM5B": {
            "url": "https://cyberjapandata.gsi.go.jp/xyz/dem5b_png/{z}/{x}/{y}.png",  # DEM5B
            "attribution": "国土地理院",
            "fix_zoomlevel": 15,
        },
        "jpn_kokudo_chiri_in_DEM5C": {
            "url": "https://cyberjapandata.gsi.go.jp/xyz/dem5c_png/{z}/{x}/{y}.png",  # DEM5C
            "attribution": "国土地理院",
            "fix_zoomlevel": 15,
        },
        "jpn_kokudo_chiri_in_DEM10B": {
            "url": "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png",  # DEM10B
            "attribution": "国土地理院",
            "fix_zoomlevel": 14,
        },
    }
    # external input of G_MAP_CONFIG
    G_MAP_LIST = "map.yaml"

    # overlay map
    G_USE_HEATMAP_OVERLAY_MAP = False
    G_HEATMAP_OVERLAY_MAP = "rwg_heatmap"
    G_USE_RAIN_OVERLAY_MAP = False
    G_RAIN_OVERLAY_MAP = "rainviewer"
    G_USE_WIND_OVERLAY_MAP = False
    G_WIND_OVERLAY_MAP = "openportguide"

    # DEM tile (Digital Elevation Model)
    G_DEM_MAP = "jpn_kokudo_chiri_in_DEM5A"

    # screenshot dir
    G_SCREENSHOT_DIR = "screenshots"

    # debug switch (change with --debug option)
    G_IS_DEBUG = False

    # dummy sampling value output (change with --demo option)
    G_DUMMY_OUTPUT = False

    # enable headless mode (keyboard operation)
    G_HEADLESS = False

    # Raspberry Pi detection (detect in __init__())
    G_IS_RASPI = False

    # for read load average in sensor_core
    G_PID = os.getpid()

    # stopwatch state
    G_MANUAL_STATUS = "INIT"
    G_STOPWATCH_STATUS = "INIT"  # with Auto Pause
    # quit status variable
    G_QUIT = False

    # Auto Pause Cutoff [m/s] (overwritten with setting.conf)
    # G_AUTOSTOP_CUTOFF = 0
    G_AUTOSTOP_CUTOFF = 4.0 * 1000 / 3600

    # wheel circumference [m] (overwritten from menu)
    # 700x23c: 2.096, 700x25c: 2.105, 700x28c: 2.136
    G_WHEEL_CIRCUMFERENCE = 2.105

    # ANT Null value
    G_ANT_NULLVALUE = np.nan
    # ANT+ setting (overwritten with setting.conf)
    # [Todo] multiple pairing(2 or more riders), ANT+ ctrl(like edge remote)
    G_ANT = {
        # ANT+ interval internal variable: 0:4Hz(0.25s), 1:2Hz(0.5s), 2:1Hz(1.0s)
        # initialized by G_ANT_INTERVAL in __init()__
        "INTERVAL": 2,
        "STATUS": True,
        "USE": {
            "HR": False,
            "SPD": False,
            "CDC": False,
            "PWR": False,
            "LGT": False,
            "CTRL": False,
            "TEMP": False,
        },
        "NAME": {
            "HR": "HeartRate",
            "SPD": "Speed",
            "CDC": "Cadence",
            "PWR": "Power",
            "LGT": "Light",
            "CTRL": "Control",
            "TEMP": "Temperature",
        },
        "ID": {
            "HR": 0,
            "SPD": 0,
            "CDC": 0,
            "PWR": 0,
            "LGT": 0,
            "CTRL": 0,
            "TEMP": 0,
        },
        "TYPE": {
            "HR": 0,
            "SPD": 0,
            "CDC": 0,
            "PWR": 0,
            "LGT": 0,
            "CTRL": 0,
            "TEMP": 0,
        },
        "ID_TYPE": {
            "HR": 0,
            "SPD": 0,
            "CDC": 0,
            "PWR": 0,
            "LGT": 0,
            "CTRL": 0,
            "TEMP": 0,
        },
        "TYPES": {
            "HR": (0x78,),
            "SPD": (0x79, 0x7B),
            "CDC": (0x79, 0x7A, 0x0B),
            "PWR": (0x0B,),
            "LGT": (0x23,),
            "CTRL": (0x10,),
            "TEMP": (0x19,),
        },
        "TYPE_NAME": {
            0x78: "HeartRate",
            0x79: "Speed and Cadence",
            0x7A: "Cadence",
            0x7B: "Speed",
            0x0B: "Power",
            0x23: "Light",
            0x10: "Control",
            0x19: "Temperature",
        },
        # for display order in ANT+ menu (antMenuWidget)
        "ORDER": ["HR", "SPD", "CDC", "PWR", "LGT", "CTRL", "TEMP"],
    }

    # GPS Null value
    G_GPS_NULLVALUE = "n/a"
    # GPS speed cutoff (the distance in 1 seconds at 0.36km/h is 10cm)
    G_GPS_SPEED_CUTOFF = G_AUTOSTOP_CUTOFF  # m/s
    # timezone (not use, get from GPS position)
    G_TIMEZONE = None
    # GPSd error handling
    G_GPSD_PARAM = {
        "EPX_EPY_CUTOFF": 100.0,
        "EPV_CUTOFF": 100.0,
        "SP1_EPV_CUTOFF": 100.0,
        "SP1_USED_SATS_CUTOFF": 3,
    }

    # fullscreen switch (overwritten with setting.conf)
    G_FULLSCREEN = False

    # display type (overwritten with setting.conf)
    G_DISPLAY = "None"  # PiTFT, MIP, Papirus, MIP_Sharp

    # screen size (need to add when adding new device)
    G_AVAILABLE_DISPLAY = {
        "None": {"size": (400, 240), "touch": True, "color": True},
        "PiTFT": {"size": (320, 240), "touch": True, "color": True},
        "MIP": {
            "size": (400, 240),
            "touch": False,
            "color": True,
        },  # LPM027M128C, LPM027M128B
        "MIP_640": {"size": (640, 480), "touch": False, "color": True},  # LPM044M141A
        "MIP_Sharp": {"size": (400, 240), "touch": False, "color": False},
        "MIP_Sharp_320": {"size": (320, 240), "touch": False, "color": False},
        "Papirus": {"size": (264, 176), "touch": False, "color": False},
        "DFRobot_RPi_Display": {"size": (250, 122), "touch": False, "color": False},
    }
    G_WIDTH = 400
    G_HEIGHT = 240

    G_DISPLAY_PARAM = {
        "SPI_CLOCK": 2000000,
    }
    G_DITHERING_CUTOFF = {
        "LOW": [128, 150, 170],
        "HIGH": [170, 193, 216],
    }
    G_DITHERING_CUTOFF_LOW_INDEX = 2
    G_DITHERING_CUTOFF_HIGH_INDEX = 1

    # auto backlight with spi mip display
    # (PiTFT actually needs max brightness under sunlights, so there are no implementation with PiTFT)
    G_USE_AUTO_BACKLIGHT = True
    G_AUTO_BACKLIGHT_CUTOFF = 30

    # GUI mode
    G_GUI_MODE = "PyQt"

    # PerformanceGraph:
    # 1st: POWER
    # 2nd: HR or W_BAL_PLIME
    # G_GUI_PERFORMANCE_GRAPH_DISPLAY_ITEM = ('POWER', 'HR')
    G_GUI_PERFORMANCE_GRAPH_DISPLAY_ITEM = ("POWER", "W_BAL")
    G_GUI_PERFORMANCE_GRAPH_DISPLAY_RANGE = int(5 * 60 / G_SENSOR_INTERVAL)  # [s]
    G_GUI_MIN_HR = 40
    G_GUI_MAX_HR = 200
    G_GUI_MIN_POWER = 30
    G_GUI_MAX_POWER = 300
    G_GUI_MIN_W_BAL = 0
    G_GUI_MAX_W_BAL = 100
    # acceleration graph (AccelerationGraphWidget)
    G_GUI_ACC_TIME_RANGE = int(1 * 60 / (G_REALTIME_GRAPH_INTERVAL / 1000))  # [s]

    # Graph color by slope
    G_CLIMB_DISTANCE_CUTOFF = 0.3  # [km]
    G_CLIMB_GRADE_CUTOFF = 2  # [%]
    G_SLOPE_CUTOFF = (1, 3, 6, 9, 12, float("inf"))  # by grade
    G_SLOPE_COLOR = (
        (128, 128, 128),  # gray(base)
        (0, 255, 0),  # green
        (255, 255, 0),  # yellow
        (255, 128, 0),  # orange
        (255, 0, 0),  # red
        (128, 0, 0),  # dark red
    )
    G_CLIMB_CATEGORY = [
        {"volume": 8000, "name": "Cat4"},
        {"volume": 16000, "name": "Cat3"},
        {"volume": 32000, "name": "Cat2"},
        {"volume": 64000, "name": "Cat1"},
        {"volume": 80000, "name": "HC"},
    ]

    # map widgets
    # max zoom
    G_MAX_ZOOM = 0
    # for map dummy center: Tokyo station in Japan
    G_DUMMY_POS_X = 139.764710814819
    G_DUMMY_POS_Y = 35.68188106919333
    # for search point on course
    G_GPS_ON_ROUTE_CUTOFF = 50  # [m] #generate from course
    G_GPS_SEARCH_RANGE = 6  # [km] #100km/h -> 27.7m/s
    G_GPS_AZIMUTH_CUTOFF = 60  # degree(30/45/90): 0~G_GPS_AZIMUTH_CUTOFF, (360-G_GPS_AZIMUTH_CUTOFF)~G_GPS_AZIMUTH_CUTOFF
    # for route downsampling cutoff
    G_ROUTE_DISTANCE_CUTOFF = 1.0  # 1.0
    G_ROUTE_AZIMUTH_CUTOFF = 3.0  # 3.0
    G_ROUTE_ALTITUDE_CUTOFF = 1.0
    G_ROUTE_SLOPE_CUTOFF = 2.0
    # for keeping on course seconds
    G_GPS_KEEP_ON_COURSE_CUTOFF = int(60 / G_GPS_INTERVAL)  # [s]

    # STRAVA token (need to write setting.conf manually)
    G_STRAVA_API_URL = {
        "OAUTH": "https://www.strava.com/oauth/token",
        "UPLOAD": "https://www.strava.com/api/v3/uploads",
    }
    G_STRAVA_API = {
        "CLIENT_ID": "",
        "CLIENT_SECRET": "",
        "CODE": "",
        "ACCESS_TOKEN": "",
        "REFRESH_TOKEN": "",
    }
    G_STRAVA_COOKIE = {
        "EMAIL": "",
        "PASSWORD": "",
        "KEY_PAIR_ID": "",
        "POLICY": "",
        "SIGNATURE": "",
    }
    G_UPLOAD_FILE = ""

    G_GOOGLE_DIRECTION_API = {
        "TOKEN": "",
        "HAVE_API_TOKEN": False,
        "URL": "https://maps.googleapis.com/maps/api/directions/json?units=metric",
        "API_MODE": {
            "bicycling": "mode=bicycling",
            "driving": "mode=driving&avoid=tolls|highways",
        },
        "API_MODE_SETTING": "bicycling",
    }

    G_MAPSTOGPX = {
        "URL": "https://mapstogpx.com/load.php?d=default&elev=off&tmode=off&pttype=fixed&o=json&cmt=off&desc=off&descasname=off&w=on",
        "HEADER": {"Referer": "https://mapstogpx.com/index.php"},
        "ROUTE_URL": "",
        "TIMEOUT": 30,
    }

    G_OPENWEATHERMAP_API = {
        "TOKEN": "",
        "HAVE_API_TOKEN": False,
        "URL": "http://api.openweathermap.org/data/2.5/weather",
    }

    G_RIDEWITHGPS_API = {
        "APIKEY": "pizero_bikecomputer",
        "TOKEN": "",
        "HAVE_API_TOKEN": False,
        "USER_ID": "",
        "URL_USER_DETAIL": "https://ridewithgps.com/users/current.json",
        "URL_USER_ROUTES": "https://ridewithgps.com/users/{user}/routes.json?offset={offset}&limit={limit}",
        "USER_ROUTES_NUM": None,
        "USER_ROUTES_START": 0,
        "USER_ROUTES_OFFSET": 10,
        "URL_ROUTE_BASE_URL": "https://ridewithgps.com/routes/{route_id}",
        "URL_ROUTE_DOWNLOAD_DIR": "./courses/ridewithgps/",
        "URL_UPLOAD": "https://ridewithgps.com/trips.json",
        "PARAMS": {
            "apikey": None,
            "version": "2",
            "auth_token": None,
        },
    }

    G_GARMINCONNECT_API = {
        "EMAIL": "",
        "PASSWORD": "",
        "URL_UPLOAD_DIFF": "proxy/upload-service/upload/.fit",  # https://connect.garmin.com/modern/proxy/upload-service/upload/.fit
    }

    G_THINGSBOARD_API = {
        "STATUS": False,
        "HAVE_API_TOKEN": False,
        "SERVER": "demo.thingsboard.io",
        "TOKEN": "",
        "INTERVAL_SEC": 120,
        "TIMEOUT_SEC": 15,
        "AUTO_UPLOAD_VIA_BT": False,
    }

    # IMU axis conversion
    #  X: to North (up rotation is plus)
    #  Y: to West (up rotation is plus)
    #  Z: to down (default is plus)
    G_IMU_AXIS_SWAP_XY = {
        "STATUS": False,  # Y->X, X->Y
    }
    G_IMU_AXIS_CONVERSION = {"STATUS": False, "COEF": np.ones(3)}  # X, Y, Z
    # sometimes axes of magnetic sensor are different from acc or gyro
    G_IMU_MAG_AXIS_SWAP_XY = {
        "STATUS": False,  # Y->X, X->Y
    }
    G_IMU_MAG_AXIS_CONVERSION = {"STATUS": False, "COEF": np.ones(3)}  # X, Y, Z
    G_IMU_MAG_DECLINATION = 0.0

    # Bluetooth tethering
    G_BT_ADDRESSES = {}
    G_BT_USE_ADDRESS = ""

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

    # for get_dist_on_earth
    GEO_R1 = 6378.137
    GEO_R2 = 6356.752314140
    GEO_R1_2 = (GEO_R1 * 1000) ** 2
    GEO_R2_2 = (GEO_R2 * 1000) ** 2
    GEO_E2 = (GEO_R1_2 - GEO_R2_2) / GEO_R1_2
    G_DISTANCE_BY_LAT1S = GEO_R2 * 1000 * 2 * np.pi / 360 / 60 / 60  # [m]

    #######################
    # class objects       #
    #######################
    logger = None
    display = None
    network = None
    bt_pan = None
    ble_uart = None
    setting = None
    gui = None
    gui_config = None
    boot_time = 0

    def __init__(self):
        # Raspbian OS detection
        if _IS_RASPI:
            self.G_IS_RASPI = True

        # get options
        parser = argparse.ArgumentParser()
        parser.add_argument("-f", "--fullscreen", action="store_true", default=False)
        parser.add_argument("-d", "--debug", action="store_true", default=False)
        parser.add_argument("--demo", action="store_true", default=False)
        parser.add_argument("--version", action="version", version="%(prog)s 0.1")
        parser.add_argument("--layout")
        parser.add_argument("--headless", action="store_true", default=False)

        args = parser.parse_args()

        if args.debug:
            self.G_IS_DEBUG = True
        if args.fullscreen:
            self.G_FULLSCREEN = True
        if args.demo:
            self.G_DUMMY_OUTPUT = True
        if args.layout:
            if os.path.exists(args.layout):
                self.G_LAYOUT_FILE = args.layout
        if args.headless:
            self.G_HEADLESS = True
        # show options
        if self.G_IS_DEBUG:
            app_logger.setLevel(logging.DEBUG)
            app_logger.debug(args)

        # read setting.conf and settings.pickle
        self.setting = Setting(self)
        self.setting.read()

        # make sure all folders exist
        os.makedirs(self.G_SCREENSHOT_DIR, exist_ok=True)
        os.makedirs(self.G_LOG_DIR, exist_ok=True)

        if self.G_LOG_DEBUG_FILE:
            delay = not os.path.exists(self.G_LOG_DEBUG_FILE)
            fh = CustomRotatingFileHandler(self.G_LOG_DEBUG_FILE, delay=delay)
            fh.doRollover()
            fh_formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            fh.setFormatter(fh_formatter)
            app_logger.addHandler(fh)

        # layout file
        if not os.path.exists(self.G_LAYOUT_FILE):
            default_layout_file = os.path.join("layouts", "layout-cycling.yaml")
            shutil.copy(default_layout_file, self.G_LAYOUT_FILE)

        # map list
        if os.path.exists(self.G_MAP_LIST):
            self.read_map_list()
        # set default values
        for map_config in [
            self.G_MAP_CONFIG,
            self.G_HEATMAP_OVERLAY_MAP_CONFIG,
            self.G_RAIN_OVERLAY_MAP_CONFIG,
            self.G_WIND_OVERLAY_MAP_CONFIG,
            self.G_DEM_MAP_CONFIG,
        ]:
            for key in map_config:
                if "tile_size" not in map_config[key]:
                    map_config[key]["tile_size"] = 256
                if "referer" not in map_config[key]:
                    map_config[key]["referer"] = None
                if "use_mbtiles" not in map_config[key]:
                    map_config[key]["use_mbtiles"] = False

                if "user_agent" in map_config[key] and map_config[key]["user_agent"]:
                    map_config[key]["user_agent"] = self.G_PRODUCT
                else:
                    map_config[key]["user_agent"] = None

        if self.G_MAP not in self.G_MAP_CONFIG:
            app_logger.error(f"{self.G_MAP} does not exist in {self.G_MAP_LIST}")
            self.G_MAP = "toner"
        if self.G_MAP_CONFIG[self.G_MAP]["use_mbtiles"] and not os.path.exists(
            os.path.join("maptile", f"{self.G_MAP}.mbtiles")
        ):
            self.G_MAP_CONFIG[self.G_MAP]["use_mbtiles"] = False
        self.loaded_dem = None

        self.check_map_dir()

        self.G_RIDEWITHGPS_API["PARAMS"]["apikey"] = self.G_RIDEWITHGPS_API["APIKEY"]
        self.G_RIDEWITHGPS_API["PARAMS"]["auth_token"] = self.G_RIDEWITHGPS_API["TOKEN"]

        # get serial number
        self.get_serial()

        # set ant interval. 0:4Hz(0.25s), 1:2Hz(0.5s), 2:1Hz(1.0s)
        if self.G_ANT_INTERVAL == 0.25:
            self.G_ANT["INTERVAL"] = 0
        elif self.G_ANT_INTERVAL == 0.5:
            self.G_ANT["INTERVAL"] = 1
        else:
            self.G_ANT["INTERVAL"] = 2

        # coroutine loop
        self.init_loop()

        self.log_time = datetime.datetime.now()

        self.button_config = Button_Config(self)

    def init_loop(self, call_from_gui=False):
        if self.G_GUI_MODE == "PyQt":
            if call_from_gui:
                asyncio.set_event_loop(self.loop)
                self.start_coroutine()
        else:
            self.loop = asyncio.get_event_loop()

    def start_coroutine(self):
        self.logger.start_coroutine()
        self.display.start_coroutine()

        # delay init start
        asyncio.create_task(self.delay_init())

    async def delay_init(self):
        await asyncio.sleep(0.01)
        t = Timer(auto_start=True, auto_log=True, text="delay init: {0:.3f} sec")

        # network
        await self.gui.set_boot_status("initialize network modules...")
        from modules.helper.network import Network

        self.network = Network(self)

        # bluetooth
        if self.G_IS_RASPI:
            await self.gui.set_boot_status("initialize bluetooth modules...")

            from modules.helper.bt_pan import (
                BTPanDbus,
                BTPanDbusNext,
                HAS_DBUS_NEXT,
                HAS_DBUS,
            )

            if HAS_DBUS_NEXT:
                self.bt_pan = BTPanDbusNext()
            elif HAS_DBUS:
                self.bt_pan = BTPanDbus()
            if HAS_DBUS_NEXT or HAS_DBUS:
                is_available = await self.bt_pan.check_dbus()
                if is_available:
                    self.G_BT_ADDRESSES = await self.bt_pan.find_bt_pan_devices()

            try:
                from modules.helper.ble_gatt_server import GadgetbridgeService

                self.ble_uart = GadgetbridgeService(self)
            except Exception as e:  # noqa
                app_logger.info(f"Gadgetbridge service not initialized: {e}")

        # logger, sensor
        await self.gui.set_boot_status("initialize sensor...")
        self.logger.delay_init()

        # gui
        await self.gui.set_boot_status("initialize screens...")
        self.gui.delay_init()

        if self.G_HEADLESS:
            asyncio.create_task(self.keyboard_check())

        # resume BT and thingsboard setting
        if self.G_IS_RASPI:
            self.G_BT_USE_ADDRESS = self.setting.get_config_pickle(
                "G_BT_USE_ADDRESS", self.G_BT_USE_ADDRESS
            )
            self.G_THINGSBOARD_API["STATUS"] = self.setting.get_config_pickle(
                "G_THINGSBOARD_API_STATUS", self.G_THINGSBOARD_API["STATUS"]
            )
            self.G_THINGSBOARD_API[
                "AUTO_UPLOAD_VIA_BT"
            ] = self.setting.get_config_pickle(
                "AUTO_UPLOAD_VIA_BT", self.G_THINGSBOARD_API["AUTO_UPLOAD_VIA_BT"]
            )
            # resume BT tethering
            if (
                self.G_BT_USE_ADDRESS
                and not self.G_THINGSBOARD_API["AUTO_UPLOAD_VIA_BT"]
            ):
                await self.bluetooth_tethering()

        delta = t.stop()
        self.boot_time += delta

        await self.logger.resume_start_stop()

    async def keyboard_check(self):
        while not self.G_QUIT:
            app_logger.info(
                "s:start/stop, l: lap, r:reset, p: previous screen, n: next screen, q: quit"
            )
            key = await self.loop.run_in_executor(None, input, "> ")

            if key == "s":
                self.logger.start_and_stop_manual()
            elif key == "l":
                self.logger.count_laps()
            elif key == "r":
                self.logger.reset_count()
            elif key == "n" and self.gui:
                self.gui.scroll_next()
            elif key == "p" and self.gui:
                self.gui.scroll_prev()
            elif key == "q" and self.gui:
                await self.quit()
            ##### temporary #####
            # test hardware key signals
            elif key == "m" and self.gui:
                self.gui.enter_menu()
            elif key == "v" and self.gui:
                self.gui.press_space()
            elif key == "," and self.gui:
                self.gui.press_tab()
            elif key == "." and self.gui:
                self.gui.press_shift_tab()
            elif key == "b" and self.gui:
                self.gui.back_menu()
            elif key == "c" and self.gui:
                self.gui.get_screenshot()

    def set_logger(self, logger):
        self.logger = logger

    def set_display(self, display):
        self.display = display

    def check_map_dir(self):
        if not self.G_MAP_CONFIG[self.G_MAP]["use_mbtiles"]:
            os.makedirs(os.path.join("maptile", self.G_MAP), exist_ok=True)
        os.makedirs(os.path.join("maptile", self.G_HEATMAP_OVERLAY_MAP), exist_ok=True)
        os.makedirs(os.path.join("maptile", self.G_RAIN_OVERLAY_MAP), exist_ok=True)
        os.makedirs(os.path.join("maptile", self.G_WIND_OVERLAY_MAP), exist_ok=True)

        if self.G_LOG_ALTITUDE_FROM_DATA_SOURCE:
            os.makedirs(os.path.join("maptile", self.G_DEM_MAP), exist_ok=True)

    @staticmethod
    def remove_maptiles(map_name):
        path = os.path.join("maptile", map_name)
        if os.path.exists(path):
            files = os.listdir(path)
            dirs = [f for f in files if os.path.isdir(os.path.join(path, f))]
            for d in dirs:
                shutil.rmtree(os.path.join(path, d))

    def get_serial(self):
        if not self.G_IS_RASPI:
            return

        # Extract serial from cpuinfo file
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line[0:6] == "Serial":
                    # include char, not number only
                    self.G_UNIT_ID = (line.split(":")[1]).replace(" ", "").strip()[-8:]
                    self.G_UNIT_ID_HEX = int(self.G_UNIT_ID, 16)
                if line[0:5] == "Model":
                    self.G_UNIT_MODEL = (line.split(":")[1]).strip()
                if line[0:8] == "Hardware":
                    self.G_UNIT_HARDWARE = (line.split(":")[1]).replace(" ", "").strip()

        model_path = "/proc/device-tree/model"
        if self.G_UNIT_MODEL == "" and os.path.exists(model_path):
            with open(model_path, "r") as f:
                self.G_UNIT_MODEL = f.read().replace("\x00", "").strip()

        app_logger.info(
            f"{self.G_UNIT_MODEL}({self.G_UNIT_HARDWARE}), serial:{hex(self.G_UNIT_ID_HEX)}"
        )

    def press_button(self, button_hard, press_button, index):
        self.button_config.press_button(button_hard, press_button, index)

    def change_mode(self):
        self.button_config.change_mode()

    async def kill_tasks(self):
        tasks = asyncio.all_tasks()
        current_task = asyncio.current_task()
        for task in tasks:
            if self.G_GUI_MODE == "PyQt":
                if task == current_task or task.get_coro().__name__ in [
                    "update_display"
                ]:
                    continue
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                app_logger.info(f"cancel task {task.get_coro().__qualname__}")
            else:
                pass

    async def quit(self):
        app_logger.info("quit")
        if self.ble_uart is not None:
            await self.ble_uart.quit()
        await self.network.quit()

        if self.G_MANUAL_STATUS == "START":
            self.logger.start_and_stop_manual()
        self.display.quit()
        self.G_QUIT = True

        await self.logger.quit()
        self.setting.write_config()
        self.setting.delete_config_pickle()

        await asyncio.sleep(0.5)
        await self.kill_tasks()
        self.logger.remove_handler()
        app_logger.info("quit done")

        if self.G_GUI_MODE != "PyQt":
            self.loop.close()

    def poweroff(self):
        # TODO
        #  should be replaced by quit() with power_off option
        #  keep the logic for now but remove the shutdown service eg:
        #  if we are running through a service, stop it and issue power-off command (on rasp-pi only)

        # this returns 0 if active

        if is_running_as_service():
            exec_cmd(["sudo", "systemctl", "stop", "pizero_bikecomputer"])
        if self.G_IS_RASPI:
            exec_cmd(["sudo", "poweroff"])

    def reboot(self):
        if self.G_IS_RASPI:
            exec_cmd(["sudo", "reboot"])

    def update_application(self):
        if self.G_IS_RASPI:
            exec_cmd(["git", "pull", "origin", "master"])
            self.restart_application()

    def restart_application(self):
        if self.G_IS_RASPI:
            exec_cmd(["sudo", "systemctl", "restart", "pizero_bikecomputer"])

    def hardware_wifi_bt(self, status):
        app_logger.info(f"Hardware Wifi/BT: {status}")
        if self.G_IS_RASPI:
            with open(BOOT_FILE, "r") as f:
                data = f.read()
            for dev in ["wifi", "bt"]:
                disable = f"dtoverlay=disable-{dev}"
                if status:
                    if disable in data and f"#{disable}" not in data:
                        # comment it
                        exec_cmd(
                            [
                                "sudo",
                                "sed",
                                "-i",
                                f"s/^dtoverlay\=disable\-{dev}/\#dtoverlay\=disable\-{dev}/",
                                BOOT_FILE,
                            ],
                            False,
                        )
                    # else nothing to do it's not disabled then (not present or commented)
                else:
                    if f"#{disable}" in data:
                        # uncomment it, so it's disabled
                        exec_cmd(
                            [
                                "sudo",
                                "sed",
                                "-i",
                                f"s/^\#dtoverlay\=disable\-{dev}/dtoverlay\=disable\-{dev}/",
                                BOOT_FILE,
                            ],
                            False,
                        )
                    elif disable in data:
                        # do nothing it's already the proper state...
                        pass
                    else:
                        exec_cmd(
                            ["sudo", "sed", "-i", f"$a{disable}", BOOT_FILE], False
                        )
            # UART configuration will change if we disable bluetooth
            # https://www.raspberrypi.com/documentation/computers/configuration.html#primary-and-secondary-uart
            if status:
                exec_cmd(
                    [
                        "sudo",
                        "sed",
                        "-i",
                        "-e",
                        's/^\#DEVICES\="\/dev\/ttyS0"/DEVICES\="\/dev\/ttyS0"/',
                        "/etc/default/gpsd",
                    ],
                    False,
                )
                exec_cmd(
                    [
                        "sudo",
                        "sed",
                        "-i",
                        "-e",
                        's/^DEVICES\="\/dev\/ttyAMA0"/\#DEVICES\="\/dev\/ttyAMA0"/',
                        "/etc/default/gpsd",
                    ],
                    False,
                )
            else:
                exec_cmd(
                    [
                        "sudo",
                        "sed",
                        "-i",
                        "-e",
                        's/^DEVICES\="\/dev\/ttyS0"/\#DEVICES\="\/dev\/ttyS0"/',
                        "/etc/default/gpsd",
                    ],
                    False,
                )
                exec_cmd(
                    [
                        "sudo",
                        "sed",
                        "-i",
                        "-e",
                        's/^\#DEVICES\="\/dev\/ttyAMA0"/DEVICES\="\/dev\/ttyAMA0"/',
                        "/etc/default/gpsd",
                    ],
                    False,
                )

    def get_wifi_bt_status(self):
        if not self.G_IS_RASPI:
            return False, False

        status = {"wlan": False, "bluetooth": False}
        try:
            # json option requires raspbian buster
            raw_status = exec_cmd_return_value(
                ["sudo", "rfkill", "--json"], cmd_print=False
            )
            json_status = json.loads(raw_status)
            # "": Raspberry Pi OS, "rfkilldevices":
            self.parse_wifi_bt_json(json_status, status, ["", "rfkilldevices"])
        except Exception as e:
            app_logger.warning(f"Exception occurred trying to get wifi/bt status: {e}")
        return status["wlan"], status["bluetooth"]

    def parse_wifi_bt_json(self, json_status, status, keys):
        get_status = False
        for k in keys:
            if k not in json_status:
                continue
            for device in json_status[k]:
                if "type" not in device or device["type"] not in ["wlan", "bluetooth"]:
                    continue
                if device["soft"] == "unblocked" and device["hard"] == "unblocked":
                    status[device["type"]] = True
                    get_status = True
            if get_status:
                return

    def onoff_wifi_bt(self, key=None):
        # in the future, manage with pycomman
        if not self.G_IS_RASPI:
            return

        onoff_cmd = {
            "Wifi": {
                True: ["sudo", "rfkill", "block", "wifi"],
                False: ["sudo", "rfkill", "unblock", "wifi"],
            },
            "Bluetooth": {
                True: ["sudo", "rfkill", "block", "bluetooth"],
                False: ["sudo", "rfkill", "unblock", "bluetooth"],
            },
        }
        status = {}
        status["Wifi"], status["Bluetooth"] = self.get_wifi_bt_status()
        exec_cmd(onoff_cmd[key][status[key]])

    async def bluetooth_tethering(self, disconnect=False):
        if not self.G_IS_RASPI or not self.G_BT_USE_ADDRESS or not self.bt_pan:
            return

        if not disconnect:
            res = await self.bt_pan.connect_tethering(
                self.G_BT_ADDRESSES[self.G_BT_USE_ADDRESS]
            )
        else:
            res = await self.bt_pan.disconnect_tethering(
                self.G_BT_ADDRESSES[self.G_BT_USE_ADDRESS]
            )
        return bool(res)

    def check_time(self, log_str):
        t = datetime.datetime.now()
        print("###", log_str, (t - self.log_time).total_seconds())
        self.log_time = t

    def read_map_list(self):
        with open(self.G_MAP_LIST) as file:
            text = file.read()
            map_list = yaml.safe_load(text)
            if map_list is None:
                return
            for key in map_list:
                if map_list[key]["attribution"] is None:
                    map_list[key]["attribution"] = ""
            self.G_MAP_CONFIG.update(map_list)

    def get_track_str(self, drc):
        track_int = int((drc + 22.5) / 45.0)
        return self.TRACK_STR[track_int]

    # return [m]
    def get_dist_on_earth(self, p0_lon, p0_lat, p1_lon, p1_lat):
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
            res = 1000 * math.acos(cos_d) * self.GEO_R1
            return res
        except:
            # traceback.print_exc()
            # print("cos_d =", cos_d)
            # print("parameter:", p0_lon, p0_lat, p1_lon, p1_lat)
            return 0

    # return [m]
    def get_dist_on_earth_array(self, p0_lon, p0_lat, p1_lon, p1_lat):
        # if p0_lon == p1_lon and p0_lat == p1_lat:
        #  return 0
        r0_lon = np.radians(p0_lon)
        r0_lat = np.radians(p0_lat)
        r1_lon = np.radians(p1_lon)
        r1_lat = np.radians(p1_lat)
        # (r0_lon, r0_lat, r1_lon, r1_lat) = map(radians, [p0_lon, p0_lat, p1_lon, p1_lat])
        delta_x = r1_lon - r0_lon
        cos_d = np.sin(r0_lat) * np.sin(r1_lat) + np.cos(r0_lat) * np.cos(
            r1_lat
        ) * np.cos(delta_x)
        try:
            res = 1000 * np.arccos(cos_d) * self.GEO_R1
            return res
        except:
            traceback.print_exc()
            #  #print("cos_d =", cos_d)
            #  #print("parameter:", p0_lon, p0_lat, p1_lon, p1_lat)
            return np.array([])

    # return [m]
    def get_dist_on_earth_hubeny(self, p0_lon, p0_lat, p1_lon, p1_lat):
        if p0_lon == p1_lon and p0_lat == p1_lat:
            return 0
        (r0_lon, r0_lat, r1_lon, r1_lat) = map(
            math.radians, [p0_lon, p0_lat, p1_lon, p1_lat]
        )
        lat_t = (r0_lat + r1_lat) / 2
        w = 1 - self.GEO_E2 * math.sin(lat_t) ** 2
        c2 = math.cos(lat_t) ** 2
        return math.sqrt(
            (self.GEO_R2_2 / w**3) * (r0_lat - r1_lat) ** 2
            + (self.GEO_R1_2 / w) * c2 * (r0_lon - r1_lon) ** 2
        )

    @staticmethod
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

    @staticmethod
    def get_maptile_filename(map_name, z, x, y):
        return "maptile/" + map_name + "/{0}/{1}/{2}.png".format(z, x, y)

    async def get_altitude_from_tile(self, pos):
        if np.isnan(pos[0]) or np.isnan(pos[1]):
            return np.nan
        z = self.G_DEM_MAP_CONFIG[self.G_DEM_MAP]["fix_zoomlevel"]
        f_x, f_y, p_x, p_y = self.get_tilexy_and_xy_in_tile(z, pos[0], pos[1], 256)
        filename = self.get_maptile_filename(self.G_DEM_MAP, z, f_x, f_y)

        if not os.path.exists(filename):
            await self.network.download_demtile(z, f_x, f_y)
            return np.nan
        if os.path.getsize(filename) == 0:
            return np.nan

        if self.loaded_dem != (f_x, f_y):
            self.dem_array = np.asarray(Image.open(filename))
            self.loaded_dem = (f_x, f_y)
        rgb_pos = self.dem_array[p_y, p_x]
        altitude = rgb_pos[0] * (2**16) + rgb_pos[1] * (2**8) + rgb_pos[2]
        if altitude < 2**23:
            altitude = altitude * 0.01
        elif altitude == 2**23:
            altitude = np.nan
        else:
            altitude = (altitude - 2**24) * 0.01

        # print(altitude, filename, p_x, p_y, pos[1], pos[0])
        return altitude

    @staticmethod
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

    @staticmethod
    def get_lon_lat_from_tile_xy(z, x, y):
        n = 2.0**z
        lon = x / n * 360.0 - 180.0
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))

        return lon, lat

    def get_courses(self):
        dirs = sorted(
            glob(os.path.join(self.G_COURSE_DIR, "*.tcx")),
            key=lambda f: os.stat(f).st_mtime,
            reverse=True,
        )

        # heavy: delayed updates required
        # def get_course_info(c):
        #   pattern = {
        #       "name": re.compile(r"<Name>(?P<text>[\s\S]*?)</Name>"),
        #       "distance_meters": re.compile(
        #           r"<DistanceMeters>(?P<text>[\s\S]*?)</DistanceMeters>"
        #       ),
        #       # "track": re.compile(r'<Track>(?P<text>[\s\S]*?)</Track>'),
        #       # "altitude": re.compile(r'<AltitudeMeters>(?P<text>[^<]*)</AltitudeMeters>'),
        #   }
        #   info = {}
        #   with open(c, "r", encoding="utf-8_sig") as f:
        #       tcx = f.read()
        #       match_name = pattern["name"].search(tcx)
        #       if match_name:
        #           info["name"] = match_name.group("text").strip()
        #
        #       match_distance_meter = pattern["distance_meters"].search(tcx)
        #       if match_distance_meter:
        #           info["distance"] = float(match_distance_meter.group("text").strip())
        #   return info

        return [
            {
                "path": f,
                "name": os.path.basename(f),
                # **get_course_info(f)
            }
            for f in dirs
            if os.path.isfile(f) and f != self.G_COURSE_FILE_PATH
        ]
