import argparse
import asyncio
from datetime import datetime
import logging
import os
import shutil
from glob import glob

import numpy as np
import oyaml as yaml

from modules.app_logger import CustomRotatingFileHandler, app_logger
from modules.map_config import add_map_config
from modules.helper.setting import Setting
from modules.button_config import Button_Config
from modules.helper.state import AppState
from modules.utils.cmd import (
    exec_cmd,
    is_running_as_service,
)
from modules.utils.map import (
    remove_maptiles
)
from modules.utils.timer import Timer


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

    # calculate index on course
    G_COURSE_INDEXING = True

    # gross average speed
    G_GROSS_AVE_SPEED = 15  # [km/h]

    # W'bal
    G_POWER_CP = 150
    G_POWER_W_PRIME = 15000
    G_POWER_W_PRIME_ALGORITHM = "WATERWORTH"  # WATERWORTH, DIFFERENTIAL

    G_USE_PCB_PIZERO_BIKECOMPUTER = False
    G_PCB_BACKLIGHT = ""  # "PIZERO_BIKECOMPUTER", "SWITCH_SCIENCE_MIP_BOARD"

    ###########################
    # fixed or pointer values #
    ###########################

    # product name, version
    G_PRODUCT = "Pizero Bikecomputer"
    G_VERSION_MAJOR = 0  # need to be initialized
    G_VERSION_MINOR = 1  # need to be initialized
    G_UNIT_ID = "0000000000000000"  # initialized in get_serial
    G_UNIT_ID_HEX = 0x00000000  # initialized in get_serial
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
    G_LOG_OUTPUT_FILE = False
    G_LOG_DEBUG_FILE = os.path.join(G_LOG_DIR, "debug.log")

    # map setting
    # default map (can overwrite in settings.conf)
    G_MAP = "wikimedia"
    G_MAP_CONFIG = {}
    # external input of G_MAP_CONFIG
    G_MAP_LIST = "map.yaml"

    # overlay map
    G_USE_HEATMAP_OVERLAY_MAP = False
    G_HEATMAP_OVERLAY_MAP = "rwg_heatmap"
    G_HEATMAP_OVERLAY_MAP_CONFIG = {}
    G_USE_RAIN_OVERLAY_MAP = False
    G_RAIN_OVERLAY_MAP = "rainviewer"
    G_RAIN_OVERLAY_MAP_CONFIG = {}
    G_USE_WIND_OVERLAY_MAP = False
    G_WIND_OVERLAY_MAP = "openportguide"
    G_WIND_OVERLAY_MAP_CONFIG = {}

    # DEM tile (Digital Elevation Model)
    G_USE_DEM_TILE = False
    G_DEM_MAP = "jpn_kokudo_chiri_in_DEM5A" #mapbox_terrain_rgb, jpn_kokudo_chiri_in_DEM5A
    G_DEM_MAP_CONFIG = {}

    # wind speed, direction and headwind
    G_USE_WIND_DATA_SOURCE = True
    G_WIND_DATA_SOURCE = "openmeteo" #openmeteo(worldwide), jpn_scw(japan)

    # screenshot dir
    G_SCREENSHOT_DIR = "screenshots"

    # dummy sampling value output (change with --demo option)
    G_DUMMY_OUTPUT = False

    # enable headless mode (keyboard operation)
    G_HEADLESS = False

    # Raspberry Pi detection (detect in __init__())
    G_IS_RASPI = False

    # stopwatch state
    G_MANUAL_STATUS = "INIT"
    G_STOPWATCH_STATUS = "INIT"  # with Auto Pause

    # auto pause cutoff [m/s] (overwritten with setting.conf)
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
            "HR": 0, "SPD": 0, "CDC": 0, "PWR": 0, "LGT": 0, "CTRL": 0, "TEMP": 0,
        },
        "TYPE": {
            "HR": 0, "SPD": 0, "CDC": 0, "PWR": 0, "LGT": 0, "CTRL": 0, "TEMP": 0,
        },
        "ID_TYPE": {
            "HR": 0, "SPD": 0, "CDC": 0, "PWR": 0, "LGT": 0, "CTRL": 0, "TEMP": 0,
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

        "USE_AUTO_LIGHT": False,
    }

    # GPS speed cutoff (the distance in 1 seconds at 0.36km/h is 10cm)
    G_GPS_SPEED_CUTOFF = G_AUTOSTOP_CUTOFF  # m/s
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
    # PiTFT, MIP, MIP_640, MIP_Mraa, MIP_Mraa_640, MIP_Sharp, MIP_Sharp_320, 
    # Papirus, DFRobot_RPi_Display, Pirate_Audio, Pirate_Audio_old(Y button is GPIO 20), Display_HAT_Mini
    G_DISPLAY = "None"

    G_DISPLAY_PARAM = {
        "SPI_CLOCK": 2000000,
        "USE_BACKLIGHT": False,
    }

    # auto backlight
    G_USE_AUTO_BACKLIGHT = True
    G_AUTO_BACKLIGHT_CUTOFF = 10

    # GUI mode
    G_GUI_MODE = "PyQt"
    #G_GUI_MODE = "QML"
    #G_GUI_MODE = "Kivy"

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

    G_UPLOAD_FILE = ""
    G_AUTO_UPLOAD = False
    G_AUTO_UPLOAD_SERVICE = {"STRAVA": True, "RWGPS": False, "GARMIN": False,}
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
    }

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

    G_OPENMETEO_API = {
        "URL" : "https://api.open-meteo.com/v1/forecast",
        "INTERVAL_SEC": 300,
    }

    G_THINGSBOARD_API = {
        "STATUS": False,
        "HAVE_API_TOKEN": False,
        "SERVER": "demo.thingsboard.io",
        "TOKEN": "",
        "INTERVAL_SEC": 180,
    }
    G_GADGETBRIDGE = {
        "STATUS": False,
        "USE_GPS": False,
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
    G_IMU_CALIB = {
        "MAG": False,
        "PITCH_ROLL": False,
    }

    # Bluetooth tethering
    G_BT_ADDRESSES = {}
    G_BT_PAN_DEVICE = ""
    G_AUTO_BT_TETHERING = False

    #######################
    # class objects       #
    #######################
    logger = None
    display = None
    network = None
    api = None
    bt_pan = None
    ble_uart = None
    setting = None
    state = None
    gui = None
    gui_config = None
    boot_time = 0

    def __init__(self):
        # Raspbian OS detection
        proc_model = "/proc/device-tree/model"
        if os.path.exists(proc_model) and os.path.exists(proc_model):
            with open(proc_model) as f:
                p = f.read()
                if p.find("Raspberry Pi") == 0:
                    self.G_IS_RASPI = True
                elif p.lower().startswith("radxa zero"):
                    self.G_IS_RASPI = True
                    self.G_DISPLAY_PARAM["SPI_CLOCK"] = 10000000

        # get options
        parser = argparse.ArgumentParser()
        parser.add_argument("-f", "--fullscreen", action="store_true", default=False)
        parser.add_argument("-d", "--debug", action="store_true", default=False)
        parser.add_argument("--demo", action="store_true", default=False)
        parser.add_argument("--version", action="version", version="%(prog)s 0.1")
        parser.add_argument("--layout")
        parser.add_argument("--gui")
        parser.add_argument("--headless", action="store_true", default=False)
        parser.add_argument("--output_log", action="store_true", default=False)
        parser.add_argument("--calib_mag", action="store_true", default=False)
        parser.add_argument("--calib_pitch_roll", action="store_true", default=False)

        args = parser.parse_args()

        if args.debug:
            app_logger.setLevel(logging.DEBUG)
            app_logger.debug(args)
        if args.fullscreen:
            self.G_FULLSCREEN = True
        if args.demo:
            self.G_DUMMY_OUTPUT = True
        if args.layout and os.path.exists(args.layout):
            self.G_LAYOUT_FILE = args.layout
        if args.gui and args.gui in ["PyQt", "QML", "Kivy", "None"]:
            self.G_GUI_MODE = args.gui
        if args.headless:
            self.G_HEADLESS = True
        if args.output_log:
            self.G_LOG_OUTPUT_FILE = True
        if args.calib_mag:
            self.G_IMU_CALIB["MAG"] = True
            self.G_I2C_INTERVAL = 0.1
        if args.calib_pitch_roll:
            self.G_IMU_CALIB["PITCH_ROLL"] = True

        # read setting.conf and state.pickle
        self.setting = Setting(self)
        self.state = AppState()

        #add map settings
        add_map_config(self)

        # add test settings
        try:
            from modules.test_code.test_code import add_test_config
            add_test_config(self)
        except:
            pass

        # make sure all folders exist
        os.makedirs(self.G_SCREENSHOT_DIR, exist_ok=True)
        os.makedirs(self.G_LOG_DIR, exist_ok=True)

        if self.G_LOG_OUTPUT_FILE and self.G_LOG_DEBUG_FILE:
            delay = not os.path.exists(self.G_LOG_DEBUG_FILE)
            fh = CustomRotatingFileHandler(self.G_LOG_DEBUG_FILE, delay=delay)
            fh.doRollover()
            fh_formatter = logging.Formatter(
                "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"
            )
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

        if self.G_MAP not in self.G_MAP_CONFIG:
            app_logger.error(f"{self.G_MAP} does not exist in {self.G_MAP_LIST}")
            self.G_MAP = "wikimedia"
        if self.G_MAP_CONFIG[self.G_MAP].get("use_mbtiles") and not os.path.exists(
            os.path.join("maptile", f"{self.G_MAP}.mbtiles")
        ):
            self.G_MAP_CONFIG[self.G_MAP]["use_mbtiles"] = False

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

        self.log_time = datetime.now()

        self.button_config = Button_Config(self)

    def init_loop(self, call_from_gui=False):
        if self.G_GUI_MODE in ["PyQt", "QML"]:
            if call_from_gui:
                # workaround for latest qasync and older version(~0.24.0)
                asyncio.events._set_running_loop(self.loop)
                asyncio.set_event_loop(self.loop)
                self.start_coroutine()
        else:
            if call_from_gui:
                self.loop = asyncio.get_event_loop()
                self.loop.set_debug(True)
                asyncio.set_event_loop(self.loop)

    def start_coroutine(self):
        self.logger.start_coroutine()
        self.display.start_coroutine()

        # delay init start
        asyncio.create_task(self.delay_init())
    
    async def start_coroutine_async(self):
        self.start_coroutine()

    async def delay_init(self):
        await asyncio.sleep(0.01)
        t = Timer(auto_start=True, auto_log=True, text="delay init: {0:.3f} sec")

        # network
        await self.gui.set_boot_status("initialize network modules...")
        from modules.helper.api import api
        from modules.helper.network import Network

        self.api = api(self)
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

        # logger, sensor
        await self.gui.set_boot_status("initialize sensor...")
        self.logger.delay_init()

        # GadgetBridge (has to be before gui but after sensors for proper init state of buttons)
        if self.G_IS_RASPI:
            try:
                from modules.helper.ble_gatt_server import GadgetbridgeService

                self.ble_uart = GadgetbridgeService(
                    self.G_PRODUCT,
                    self.logger.sensor.sensor_gps,
                    self.gui,
                    (
                        self.G_GADGETBRIDGE["STATUS"],
                        self.G_GADGETBRIDGE["USE_GPS"],
                    ),
                )

            except Exception as e:  # noqa
                app_logger.info(f"Gadgetbridge service not initialized: {e}")

        # gui
        await self.gui.set_boot_status("initialize screens...")
        self.gui.delay_init()

        if self.G_HEADLESS:
            asyncio.create_task(self.keyboard_check())

        delta = t.stop()
        self.boot_time += delta

        await self.logger.resume_start_stop()

    async def keyboard_check(self):
        try:
            while True:
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
        except asyncio.CancelledError:
            pass

    def set_logger(self, logger):
        self.logger = logger

    def set_display(self, display):
        self.display = display

    def check_map_dir(self):
        if not self.G_MAP_CONFIG[self.G_MAP].get("use_mbtiles"):
            os.makedirs(os.path.join("maptile", self.G_MAP), exist_ok=True)
        os.makedirs(os.path.join("maptile", self.G_HEATMAP_OVERLAY_MAP), exist_ok=True)
        os.makedirs(os.path.join("maptile", self.G_RAIN_OVERLAY_MAP), exist_ok=True)
        os.makedirs(os.path.join("maptile", self.G_WIND_OVERLAY_MAP), exist_ok=True)

        if self.G_USE_DEM_TILE:
            os.makedirs(os.path.join("maptile", self.G_DEM_MAP), exist_ok=True)
    
    def delete_weather_overlay_tiles(self):
        remove_maptiles(
            self.G_RAIN_OVERLAY_MAP,
            self.G_RAIN_OVERLAY_MAP_CONFIG[self.G_RAIN_OVERLAY_MAP]["basetime"]
        )
        remove_maptiles(
            self.G_WIND_OVERLAY_MAP,
            self.G_WIND_OVERLAY_MAP_CONFIG[self.G_WIND_OVERLAY_MAP]["basetime"]
        )

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
            f"{self.G_UNIT_MODEL}({self.G_UNIT_HARDWARE}), serial:{self.G_UNIT_ID_HEX:X}"
        )

    async def kill_tasks(self):
        tasks = asyncio.all_tasks()
        current_task = asyncio.current_task()
        for task in tasks:
            if self.G_GUI_MODE in ["PyQt", "QML"]:
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

        await self.logger.quit()
        self.setting.write_config()
        self.state.delete()

        self.delete_weather_overlay_tiles()

        await asyncio.sleep(0.5)
        await self.kill_tasks()
        self.logger.remove_handler()

        app_logger.info("quit done")

    async def power_off(self):
        service_state = is_running_as_service() if self.G_IS_RASPI else False
        
        await self.quit()
        if service_state and self.G_IS_RASPI:
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

    def check_time(self, log_str):
        t = datetime.now()
        app_logger.info(f"### {log_str}, {(t - self.log_time).total_seconds()}")
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
