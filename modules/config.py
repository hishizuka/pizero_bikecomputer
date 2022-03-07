import sys
import os
import shutil
import struct
import subprocess
import time
import datetime
import argparse
import configparser
import threading
import queue
import traceback
import json
import pickle
import socket
import math

import numpy as np
from PIL import Image
import oyaml as yaml

import asyncio
import aiohttp

_IS_RASPI = False
try:
  import RPi.GPIO as GPIO
  GPIO.setmode(GPIO.BCM)
  #GPIO.setmode(GPIO.BOARD)
  _IS_RASPI = True
except:
  pass

from modules.button_config import Button_Config


class Config():

  #######################
  # configurable values #
  #######################

  #loop interval
  G_SENSOR_INTERVAL = 1.0 #[s] for sensor_core
  G_ANT_INTERVAL = 1.0 #[s] for ANT+. 0.25, 0.5, 1.0 only.
  G_I2C_INTERVAL = 0.5 #[s] for I2C (altitude, accelerometer, etc)
  G_GPS_INTERVAL = 1.0 #[s] for GPS
  G_DRAW_INTERVAL = 1000 #[ms] for GUI (QtCore.QTimer)
  #G_LOGGING_INTERVAL = 1000 #[ms] for logger_core (log interval)
  G_LOGGING_INTERVAL = 1.0 #[s] for logger_core (log interval)
  G_REALTIME_GRAPH_INTERVAL = 200 #[ms] for pyqt_graph
  
  #log format switch
  G_LOG_WRITE_CSV = True
  G_LOG_WRITE_FIT = True

  #average including ZERO when logging
  G_AVERAGE_INCLUDING_ZERO = {
    "cadence":False,
    "power":True
  }

  #log several altitudes (from DEM and course file)
  G_LOG_ALTITUDE_FROM_DATA_SOUCE = False

  #calculate index on course
  G_COURSE_INDEXING = True

  #gross average speed
  G_GROSS_AVE_SPEED = 15 #[km/h]

  #W'bal
  G_POWER_CP = 100
  G_POWER_W_PRIME = 10000
  G_POWER_W_PRIME_ALGORITHM = "WATERWORTH" #WATERWORTH, DIFFERENTIAL

  ###########################
  # fixed or pointer values #
  ###########################

  #product name, version
  G_PRODUCT = "Pizero Bikecomputer"
  G_VERSION_MAJOR = 0 #need to be initialized
  G_VERSION_MINOR = 1 #need to be initialized
  G_UNIT_ID = "0000000000000000" #initialized in get_serial
  G_UNIT_ID_HEX = 0x1A2B3C4D #initialized in get_serial

  #install_dir 
  G_INSTALL_PATH = os.path.expanduser('~') + "/pizero_bikecomputer/"
  
  #layout def
  G_LAYOUT_FILE = "layout.yaml"

  #Language defined by G_LANG in gui_config.py
  G_LANG = "EN"
  G_FONT_FILE = ""
  G_FONT_FULLPATH = ""
  G_FONT_NAME = ""
  
  #course file
  G_COURSE_FILE = "course/course.tcx"
  #G_CUESHEET_FILE = "course/cue_sheet.csv"
  G_CUESHEET_DISPLAY_NUM = 3 #max: 5
  G_CUESHEET_SCROLL = False

  #log setting
  G_LOG_DIR = "log/"
  G_LOG_DB = G_LOG_DIR + "log.db"
  G_LOG_START_DATE = None
  
  #map setting
  #default map (can overwrite in settings.conf)
  G_MAP = 'toner'
  G_MAP_CONFIG = {
    #basic map
    'toner': {
      # 0:z(zoom), 1:tile_x, 2:tile_y
      'url': "http://a.tile.stamen.com/toner/{z}/{x}/{y}.png",
      'attribution': 'Map tiles by Stamen Design, under CC BY 3.0.<br />Data by OpenStreetMap, under ODbL',
      'tile_size': 256,
    },
    'toner_2x': {
      # 0:z(zoom), 1:tile_x, 2:tile_y
      'url': "http://a.tile.stamen.com/toner/{z}/{x}/{y}@2x.png",
      'attribution': 'Map tiles by Stamen Design, under CC BY 3.0.<br />Data by OpenStreetMap, under ODbL',
      'tile_size': 512,
    },
    'wikimedia': {
      'url': "https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}.png",
      'attribution': '© OpenStreetMap contributors',
      'tile_size': 256,
    },
    #japanese tile
    'jpn_kokudo_chiri_in': {
      'url': "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
      'attribution': '国土地理院',
      'tile_size': 256,
    },

    #heatmap
    'strava_heatmap_bluered': {
      'url': "https://heatmap-external-b.strava.com/tiles-auth/ride/bluered/{z}/{x}/{y}.png?px=256",
      'attribution': 'strava',
      'tile_size': 256,
      'max_zoomlevel': 16,
      'min_zoomlevel': 10,
    },
    'rwg_heatmap': {
      #start_color: low, white(FFFFFF) is recommended.
      #end_color: high, any color you like.
      'url': "https://heatmap.ridewithgps.com/normalized/{z}/{x}/{y}.png?start_color=%23FFFFFF&end_color=%23FF8800",
      'attribution': 'ride with gps',
      'tile_size': 256,
      'max_zoomlevel': 16,
      'min_zoomlevel': 10,
    },

    #worldwide rain tile

    #japanese rain tile

    #worldwide wind tile

    #japanese wind tile
    
    #worldwide DEM(Digital Elevation Model) map

    #japanese DEM(Digital Elevation Model) map
    'jpn_kokudo_chiri_in_DEM5A': {
      'url': "https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png", #DEM5A
      'attribution': '国土地理院',
      'fix_zoomlevel':15
    }, 
    'jpn_kokudo_chiri_in_DEM5B': {
      'url': "https://cyberjapandata.gsi.go.jp/xyz/dem5b_png/{z}/{x}/{y}.png", #DEM5B
      'attribution': '国土地理院',
      'fix_zoomlevel':15
    }, 
    'jpn_kokudo_chiri_in_DEM5C': {
      'url': "https://cyberjapandata.gsi.go.jp/xyz/dem5c_png/{z}/{x}/{y}.png", #DEM5C
      'attribution': '国土地理院',
      'fix_zoomlevel':15
    }, 
    'jpn_kokudo_chiri_in_DEM10B': {
      'url': "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png", #DEM10B
      'attribution': '国土地理院',
      'fix_zoomlevel':14
    }, 

  }
  #external input of G_MAP_CONFIG
  G_MAP_LIST = "map.yaml"

  #overlay map
  G_STRAVA_OVERLAY_MAP = "strava_heatmap_bluered"
  G_RAIN_OVERLAY_MAP = "jpn_jma_bousai"
  G_WIND_OVERLAY_MAP =""

  #DEM tile (Digital Elevation Model)
  G_DEM_MAP = 'jpn_kokudo_chiri_in_DEM5A'

  #screenshot dir
  G_SCREENSHOT_DIR = 'screenshot/'

  #debug switch (change with --debug option)
  G_IS_DEBUG = False

  #dummy sampling value output (change with --demo option)
  G_DUMMY_OUTPUT = False
  
  #enable headless mode (keyboard operation)
  G_HEADLESS = False

  #Raspberry Pi detection (detect in __init__())
  G_IS_RASPI = False

  #for read load average in sensor_core
  G_PID = os.getpid()

  #stopwatch state
  G_MANUAL_STATUS = "INIT"
  G_STOPWATCH_STATUS = "INIT" #with Auto Pause
  #quit status variable
  G_QUIT = False

  #Auto Pause Cutoff [m/s] (overwritten with setting.conf)
  #G_AUTOSTOP_CUTOFF = 0 
  G_AUTOSTOP_CUTOFF = 4.0*1000/3600

  #wheel circumference [m] (overwritten from menu)
  #700x23c: 2.096, 700x25c: 2.105, 700x28c: 2.136
  G_WHEEL_CIRCUMFERENCE = 2.105

  #ANT Null value
  G_ANT_NULLVALUE = np.nan
  #ANT+ setting (overwritten with setting.conf)
  #[Todo] multiple pairing(2 or more riders), ANT+ ctrl(like edge remote)
  G_ANT = {
    #ANT+ interval internal variabl: 0:4Hz(0.25s), 1:2Hz(0.5s), 2:1Hz(1.0s)
    #initialized by G_ANT_INTERVAL in __init()__
    'INTERVAL':2, 
    'STATUS':True,
    'USE':{
      'HR':False,
      'SPD':False,
      'CDC':False,
      'PWR':False,
      'LGT':False,
      'CTRL':False,
      },
    'NAME':{
      'HR':'HeartRate',
      'SPD':'Speed',
      'CDC':'Cadence',
      'PWR':'Power',
      'LGT':'Light',
      'CTRL':'Control',
      },
    'ID':{
      'HR':0,
      'SPD':0,
      'CDC':0,
      'PWR':0,
      'LGT':0,
      'CTRL':0,
      },
    'TYPE':{
      'HR':0,
      'SPD':0,
      'CDC':0,
      'PWR':0,
      'LGT':0,
      'CTRL':0,
      },
    'ID_TYPE':{
      'HR':0,
      'SPD':0,
      'CDC':0,
      'PWR':0,
      'LGT':0,
      'CTRL':0,
      },
    'TYPES':{
      'HR':(0x78,),
      'SPD':(0x79,0x7B),
      'CDC':(0x79,0x7A,0x0B),
      'PWR':(0x0B,),
      'LGT':(0x23,),
      'CTRL':(0x10,),
      },
    'TYPE_NAME':{
      0x78:'HeartRate',
      0x79:'Speed and Cadence',
      0x7A:'Cadence',
      0x7B:'Speed',
      0x0B:'Power',
      0x23:'Light',
      0x10:'Control',
      },
    #for display order in ANT+ menu (antMenuWidget)
    'ORDER':['HR','SPD','CDC','PWR','LGT','CTRL'],
   }
  
  #GPS Null value
  G_GPS_NULLVALUE = "n/a"
  #GPS speed cutoff (the distance in 1 seconds at 0.36km/h is 10cm)
  G_GPS_SPEED_CUTOFF = G_AUTOSTOP_CUTOFF #m/s
  #timezone (not use, get from GPS position)
  G_TIMEZONE = None
  #exclude outlier cutoff when passed through the tunnel
  G_GPS_SKIP_CUTOFF = 5

  #fullscreen switch (overwritten with setting.conf)
  G_FULLSCREEN = False
  #display type (overwritten with setting.conf)
  G_DISPLAY = 'PiTFT' #PiTFT, MIP, Papirus, MIP_Sharp
  #screen size (need to add when adding new device)
  G_AVAILABLE_DISPLAY = {
    'PiTFT': {'size':(320, 240),'touch':True, 'color': True},
    'MIP': {'size':(400, 240),'touch':False, 'color': True}, #LPM027M128C, LPM027M128B
    'MIP_640': {'size':(640, 480),'touch':False, 'color': True}, #LPM044M141A
    'MIP_Sharp': {'size':(400, 240),'touch':False, 'color': False},
    'MIP_Sharp_320': {'size':(320, 240),'touch':False, 'color': False},
    'Papirus': {'size':(264, 176),'touch':False, 'color': False},
    'DFRobot_RPi_Display': {'size':(250, 122),'touch':False, 'color': False}
  }
  G_WIDTH = 320
  G_HEIGHT = 240
  #GUI mode
  G_GUI_MODE = "PyQt"
  #G_GUI_MODE = "QML"
  #G_GUI_MODE = "Kivy"

  #PerformanceGraph: 
  # 1st: POWER
  # 2nd: HR or W_BAL_PLIME
  #G_GUI_PERFORMANCE_GRAPH_DISPLAY_ITEM = ('POWER', 'HR')
  G_GUI_PERFORMANCE_GRAPH_DISPLAY_ITEM = ('POWER', 'W_BAL')
  G_GUI_PERFORMANCE_GRAPH_DISPLAY_RANGE = int(5*60/G_SENSOR_INTERVAL) # [s]
  G_GUI_MIN_HR = 40
  G_GUI_MAX_HR = 200
  G_GUI_MIN_POWER = 30
  G_GUI_MAX_POWER = 300
  G_GUI_MIN_W_BAL = 0
  G_GUI_MAX_W_BAL = 100
  #acceleration graph (AccelerationGraphWidget)
  G_GUI_ACC_TIME_RANGE = int(1*60/(G_REALTIME_GRAPH_INTERVAL/1000)) # [s]

  #Graph color by slope
  G_SLOPE_WINDOW_DISTANCE = 500 #m
  G_SLOPE_CUTOFF = (1,3,5,7,9,11,float("inf")) #by grade
  G_SLOPE_COLOR = (
   #(128,128,128,160),  #gray(base)
   #(0,0,255,160),      #blue
   #(0,255,255,160),    #light blue
   #(0,255,0,160),      #green
   #(255,255,0,160),    #yellow
   #(255,128,0,160),    #orange
   #(255,0,0,160),       #red
   (128,128,128),  #gray(base) -> black in 8color(MIP)
   (0,0,255),      #blue
   (0,255,255),    #light blue
   (0,255,0),      #green
   (255,255,0),    #yellow
   (255,128,0),    #orange
   (255,0,0),      #red
  )

  #map widgets
  #max zoom
  G_MAX_ZOOM = 0
  #for map dummy center: Tokyo station in Japan
  G_DUMMY_POS_X = 139.764710814819 
  G_DUMMY_POS_Y = 35.68188106919333 
  #for search point on course
  G_GPS_ON_ROUTE_CUTOFF = 50 #[m] #generate from course
  G_GPS_SEARCH_RANGE = 5 #[km] #100km/h -> 27.7m/s
  #for route downsampling cutoff
  G_ROUTE_DISTANCE_CUTOFF = 1.0 #1.0
  G_ROUTE_AZIMUTH_CUTOFF = 3.0 #3.0
  G_ROUTE_ALTITUDE_CUTOFF = 1.0
  G_ROUTE_SLOPE_CUTOFF = 2.0
  #for keeping on course seconds
  G_GPS_KEEP_ON_COURSE_CUTOFF = int(60/G_GPS_INTERVAL) # [s]

  #STRAVA token (need to write setting.conf manually)
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
    "KEY_PAIR_ID": "",
    "POLICY": "",
    "SIGNATURE": "",
  }
  G_STRAVA_UPLOAD_FILE = ""

  #GOOGLE DIRECTION API TOKEN
  G_GOOGLE_DIRECTION_API = {
    "TOKEN": "",
  }
  G_HAVE_GOOGLE_DIRECTION_API_TOKEN = False
  G_GOOGLE_DIRECTION_API_URL = "https://maps.googleapis.com/maps/api/directions/json?units=metric&language=ja"
  G_GOOGLE_DIRECTION_API_MODE = {
    "BICYCLING": "mode=bicycling",
    "DRIVING": "mode=driving&avoid=tolls|highways",
  }

  G_OPENWEATHERMAP_API = {
    "TOKEN": "",
  }
  G_HAVE_OPENWEATHERMAP_API_TOKEN = False
  G_OPENWEATHERMAP_API_URL = "http://api.openweathermap.org/data/2.5/weather"
  
  #auto backlight with spi mip display
  #(PiTFT actually needs max brightness under sunlights, so there are no implementation with PiTFT)
  G_USE_AUTO_BACKLIGHT = True
  G_AUTO_BACKLIGHT_CUTOFF = 30

  #IMU axis conversion
  #  X: to North (up rotation is plus)
  #  Y: to West (up rotation is plus)
  #  Z: to down (defualt is plus)
  G_IMU_AXIS_SWAP_XY = {
    'STATUS': False, #Y->X, X->Y
  }
  G_IMU_AXIS_CONVERSION = {
    'STATUS': False,
    'COEF': np.ones(3) #X, Y, Z
  }
  G_IMU_MAG_DECLINATION = 0.0

  #blue tooth setting
  G_BT_ADDRESS = {}
  G_BT_CMD_BASE = ["/usr/local/bin/bt-pan","client"]

  #for track
  TRACK_STR = [
    'N','NE','E','SE',
    'S','SW','W','NW',
    'N',
    ]

  #for get_dist_on_earth
  GEO_R1 = 6378.137
  GEO_R2 = 6356.752314140
  GEO_R1_2 = (GEO_R1*1000) ** 2
  GEO_R2_2 = (GEO_R2*1000) ** 2
  GEO_E2 = (GEO_R1_2 - GEO_R2_2) / GEO_R1_2
  G_DISTANCE_BY_LAT1S = GEO_R2*1000 * 2*np.pi/360/60/60 #[m]
  
  #######################
  # class objects       #
  #######################
  
  #LoggerCore
  logger = None

  #GUI (GUI_PyQt)
  gui = None
  gui_config = None

  #config file (store user specified values. readable and editable.)
  config_file = "setting.conf"
  config_parser = None
  #config file (store temporary values. unreadable and uneditable.)
  config_pickle_file = "setting.pickle"
  config_pickle = {}
  config_pickle_write_time = datetime.datetime.utcnow()
  config_pickle_interval = 10 #[s]

  def __init__(self):

    #Raspbian OS detection
    if _IS_RASPI:
      self.G_IS_RASPI = True

    # get options
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--fullscreen", action="store_true", default=False)
    parser.add_argument("-d", "--debug", action="store_true", default=False)
    parser.add_argument("--demo", action="store_true", default=False)
    parser.add_argument('--version', action='version', version='%(prog)s 0.1')
    parser.add_argument("--layout")
    parser.add_argument("--headless", action="store_true", default=False)

    args = parser.parse_args()
    
    if args.debug:
      self.G_IS_DEBUG= True
    if args.fullscreen:
      self.G_FULLSCREEN = True
    if args.demo:
      self.G_DUMMY_OUTPUT = True
    if args.layout:
      if os.path.exists(args.layout):
        self.G_LAYOUT_FILE = args.layout
    if args.headless:
      self.G_HEADLESS = True
    #show options
    if self.G_IS_DEBUG:
      print(args)
    
    #object for setting.conf
    self.config_parser = configparser.ConfigParser()
    if os.path.exists(self.config_file):
      self.read_config()

    if os.path.exists(self.config_pickle_file):
      self.read_config_pickle()

    #set dir(for using from pitft desktop)
    if self.G_IS_RASPI:
      self.G_SCREENSHOT_DIR = self.G_INSTALL_PATH + self.G_SCREENSHOT_DIR 
      self.G_LOG_DIR = self.G_INSTALL_PATH + self.G_LOG_DIR
      self.G_LOG_DB = self.G_INSTALL_PATH + self.G_LOG_DB
      self.config_file = self.G_INSTALL_PATH + self.config_file
      self.G_LAYOUT_FILE = self.G_INSTALL_PATH + self.G_LAYOUT_FILE
      self.G_COURSE_FILE = self.G_INSTALL_PATH + self.G_COURSE_FILE
    
    #layout file
    if not os.path.exists(self.G_LAYOUT_FILE):
      if self.G_IS_RASPI:
        shutil.copy(self.G_INSTALL_PATH+"layouts/"+"layout-cycling.yaml", self.G_LAYOUT_FILE)
      else:
        shutil.copy("./layouts/layout-cycling.yaml", self.G_LAYOUT_FILE)
    
    #font file
    if self.G_FONT_FILE != "" or self.G_FONT_FILE != None:
      if os.path.exists(self.G_FONT_FILE):
        self.G_FONT_FULLPATH = self.G_FONT_FILE

    #map list
    if os.path.exists(self.G_MAP_LIST):
      self.read_map_list()
    #set default values
    for key in self.G_MAP_CONFIG:
      if 'tile_size' not in self.G_MAP_CONFIG[key]:
        self.G_MAP_CONFIG[key]['tile_size'] = 256
      elif 'referer' not in self.G_MAP_CONFIG[key]:
        self.G_MAP_CONFIG[key]['referer'] = None
      
      if 'user_agent' in self.G_MAP_CONFIG[key] and self.G_MAP_CONFIG[key]['user_agent']:
        self.G_MAP_CONFIG[key]['user_agent'] = self.G_PRODUCT
      else:
        self.G_MAP_CONFIG[key]['user_agent'] = None
      
    if self.G_MAP not in self.G_MAP_CONFIG:
      print("don't exist map \"{}\" in {}".format(self.G_MAP, self.G_MAP_LIST), file=sys.stderr)
      self.G_MAP = "toner"
    self.loaded_dem = None

    #mkdir
    if not os.path.exists(self.G_SCREENSHOT_DIR):
      os.mkdir(self.G_SCREENSHOT_DIR)
    if not os.path.exists(self.G_LOG_DIR):
      os.mkdir(self.G_LOG_DIR)
    if not os.path.exists("maptile/"+self.G_MAP):
      os.mkdir("maptile/"+self.G_MAP)
    
    #optional
    if not os.path.exists("maptile/"+self.G_STRAVA_OVERLAY_MAP):
      os.mkdir("maptile/"+self.G_STRAVA_OVERLAY_MAP)
    #if not os.path.exists("maptile/"+self.G_RAIN_OVERLAY_MAP):
    #  os.mkdir("maptile/"+self.G_RAIN_OVERLAY_MAP)
    #if not os.path.exists("maptile/"+self.G_WIND_OVERLAY_MAP):
    #  os.mkdir("maptile/"+self.G_WIND_OVERLAY_MAP)
    if self.G_LOG_ALTITUDE_FROM_DATA_SOUCE and not os.path.exists("maptile/"+self.G_DEM_MAP):
      os.mkdir("maptile/"+self.G_DEM_MAP)

    #get serial number
    self.get_serial()
    
    self.detect_display()
    self.set_resolution()

    self.button_config = Button_Config(self)

    #set ant interval. 0:4Hz(0.25s), 1:2Hz(0.5s), 2:1Hz(1.0s)
    if self.G_ANT_INTERVAL == 0.25:
      self.G_ANT['INTERVAL'] = 0
    elif self.G_ANT_INTERVAL == 0.5:
      self.G_ANT['INTERVAL'] = 1
    else:
      self.G_ANT['INTERVAL'] = 2

    #coroutine loop
    self.loop = asyncio.get_event_loop()
    self.G_COROUTINE_SEM = 100

    self.log_time = datetime.datetime.now()

    #thread for downloading map tiles
    self.download_queue = queue.Queue()
    self.download_thread = threading.Thread(target=self.download_worker, name="download_worker", args=())
    self.download_thread.start()

    self.keyboard_control_thread = None
    if self.G_HEADLESS:
      self.keyboard_control_thread = threading.Thread(target=self.keyboard_check, name="keyboard_check", args=())
      self.keyboard_control_thread.start()

  def keyboard_check(self):
    while(not self.G_QUIT):
      print("s:start/stop, l: lap, r:reset, p: previous screen, n: next screen")
      key = input()

      if key == "s":
        self.logger.start_and_stop_manual()
      elif key == "l":
        self.logger.count_laps()
      elif key == "r":
        self.logger.reset_count()
      elif key == "n" and self.gui != None:
        self.gui.scroll_next()
      elif key == "p" and self.gui != None:
        self.gui.scroll_prev()

  def set_logger(self, logger):
    self.logger = logger

  def detect_display(self):
    hatdir = '/proc/device-tree/hat'
    product_file = hatdir + '/product'
    vendor_file = hatdir + '/vendor'
    
    if (os.path.exists(product_file)) and (os.path.exists(vendor_file)) :
      with open(hatdir + '/product') as f :
        p = f.read()
      with open(hatdir + '/vendor') as f :
        v = f.read()
      print(product_file, ":", p)
      print(vendor_file, ":", v)
      
      #set display
      if (p.find('Adafruit PiTFT HAT - 2.4 inch Resistive Touch') == 0):
        self.G_DISPLAY = 'PiTFT'
      elif (p.find('PaPiRus ePaper HAT') == 0) and (v.find('Pi Supply') == 0) :
        self.G_DISPLAY = 'Papirus'

  def set_resolution(self):
    for key in self.G_AVAILABLE_DISPLAY.keys():
      if self.G_DISPLAY == key:
        self.G_WIDTH = self.G_AVAILABLE_DISPLAY[key]['size'][0]
        self.G_HEIGHT = self.G_AVAILABLE_DISPLAY[key]['size'][1]
        break

  def get_serial(self):
    if not self.G_IS_RASPI:
      return

    # Extract serial from cpuinfo file
    try:
      f = open('/proc/cpuinfo','r')
      for line in f:
        if line[0:6]=='Serial':
          #include char, not number only
          self.G_UNIT_ID = (line.split(':')[1]).replace(' ','').strip()
          self.G_UNIT_ID_HEX = int(self.G_UNIT_ID[-8:])
      f.close()
    except:
      pass
  
  def press_button(self, button_hard, press_button, index):
    self.button_config.press_button(button_hard, press_button, index)

  def change_mode(self):
    self.button_config.change_mode()

  def exec_cmd(self, cmd, cmd_print=True):
    if cmd_print:
      print(cmd)
    ver = sys.version_info
    try:
      if ver[0] >= 3 and ver[1] >= 5:
        subprocess.run(cmd)
      elif ver[0] == 3 and ver[1] < 5:
        #deplicated
        subprocess.call(cmd)
    except:
      traceback.print_exc()

  def exec_cmd_return_value(self, cmd, cmd_print=True):
    string = ""
    if cmd_print:
      print(cmd)
    ver = sys.version_info
    try:
      if ver[0] >= 3 and ver[1] >= 5:
        p = subprocess.run(
          cmd, 
          stdout = subprocess.PIPE,
          stderr = subprocess.PIPE,
          #universal_newlines = True
          )
        string = p.stdout.decode("utf8").strip()
      elif ver[0] == 3 and ver[1] < 5:
        #deplicated
        p = subprocess.Popen(
          cmd,
          stdout = subprocess.PIPE,
          stderr = subprocess.PIPE,
          #universal_newlines = True
          )
        string = p.communicate()[0].decode("utf8").strip()
      return string
    except:
      traceback.print_exc()
  
  def get_maptile_filename(self, map_name, z, x, y):
    return "maptile/"+map_name+"/{0}/{1}/{2}.png".format(z, x, y)
  
  def detect_network(self):
    try:
      socket.setdefaulttimeout(3)
      socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
      return True
    except socket.error as ex:
      return False

  def download_maptile(self, map_name, z, tiles, additional_download=False):
    if not self.detect_network() or self.G_MAP_CONFIG[map_name]['url'] == None:
      return False

    urls = []
    save_paths = []
    request_header = {}

    #make header
    if 'referer' in self.G_MAP_CONFIG[map_name] and self.G_MAP_CONFIG[map_name]['referer'] != None:
      request_header['Referer'] = self.G_MAP_CONFIG[map_name]['referer']
    if 'user_agent' in self.G_MAP_CONFIG[map_name] and self.G_MAP_CONFIG[map_name]['user_agent'] != None:
      request_header['User-Agent'] = self.G_MAP_CONFIG[map_name]['user_agent']

    for tile in tiles:
      os.makedirs("maptile/"+map_name+"/{0}/{1}/".format(z, tile[0]), exist_ok=True)
      url = self.G_MAP_CONFIG[map_name]['url'].format(z=z, x=tile[0], y=tile[1])
      if 'strava_heatmap' in map_name:
        url = url \
          + "&Key-Pair-Id=" + self.G_STRAVA_COOKIE['KEY_PAIR_ID'] \
          + "&Policy=" + self.G_STRAVA_COOKIE['POLICY'] \
          + "&Signature=" + self.G_STRAVA_COOKIE['SIGNATURE']
      save_path = self.get_maptile_filename(map_name, z, *tile)
      urls.append(url)
      save_paths.append(save_path)

    self.download_queue.put((urls, request_header, save_paths))

    if additional_download:
      additional_urls = []
      additional_save_paths = []
      for tile in tiles:
        for i in range(2):
          os.makedirs("maptile/"+map_name+"/{0}/{1}/".format(z+1, 2*tile[0]+i), exist_ok=True)
          for j in range(2):
            url = self.G_MAP_CONFIG[map_name]['url'].format(z=z+1, x=2*tile[0]+i, y=2*tile[1]+j)
            save_path = self.get_maptile_filename(map_name, z+1, 2*tile[0]+i, 2*tile[1]+j)
            additional_urls.append(url)
            additional_save_paths.append(save_path)
      
        if z-1 <= 0:
          continue
        os.makedirs("maptile/"+map_name+"/{0}/{1}/".format(z-1, int(tile[0]/2)), exist_ok=True)
        zoomout_url = self.G_MAP_CONFIG[map_name]['url'].format(z=z-1, x=int(tile[0]/2), y=int(tile[1]/2))
        if zoomout_url not in additional_urls:
          additional_urls.append(zoomout_url)
          additional_save_paths.append(self.get_maptile_filename(map_name, z-1, int(tile[0]/2), int(tile[1]/2)))
      self.download_queue.put((additional_urls, request_header, additional_save_paths))
    
    return True

  def download_worker(self):
    failed = []
    for urls, header, save_paths in iter(self.download_queue.get, None):
      res = self.loop.run_until_complete(self.download_files(urls, header, save_paths))
      self.download_queue.task_done()

      #all False -> give up
      if not any(res) or res == None:
        failed.append((datetime.datetime.now(), urls, header, save_paths))
        print("failed download")
        print(urls)
      #retry
      elif not all(res) and len(urls) > 0 and len(res) > 0 and len(urls) == len(res):
        retry_urls = []
        retry_save_paths = []
        for url, save_path, status in zip(urls, save_paths, res):
          if not status:
            retry_urls.append(url)
            retry_save_paths.append(save_path)
        if len(retry_urls) > 0:
          self.download_queue.put((retry_urls, header, retry_save_paths))

  async def get_http_request(self, session, url, save_path, header):
    try:
      async with session.get(url, headers=header) as dl_file:
        if dl_file.status == 200:
          with open(save_path, mode='wb') as f:
            f.write(await dl_file.read())
            return True
        else:
          return False
    except:
      traceback.print_exc()
      return False

  async def download_files(self, urls, header, save_paths):
    
    tasks = []
    res = None
    async with asyncio.Semaphore(self.G_COROUTINE_SEM):
      async with aiohttp.ClientSession() as session:
        for url, save_path in zip(urls, save_paths):
          tasks.append(self.get_http_request(session, url, save_path, header))
        res = await asyncio.gather(*tasks)
    return res

  def download_demtile(self, z, x, y):
    if not self.detect_network():
      return False
    header = {}
    try:
      os.makedirs("maptile/"+self.G_DEM_MAP+"/{0}/{1}/".format(z, x), exist_ok=True)
      self.download_queue.put((
        [self.G_MAP_CONFIG[self.G_DEM_MAP]['url'].format(z=z, x=x, y=y),],
        header,
        [self.get_maptile_filename(self.G_DEM_MAP, z, x, y),]
        ))
      return True
    except:
      traceback.print_exc()
      return False

  def quit(self):
    print("quit")
    self.download_queue.put(None)
    if self.G_MANUAL_STATUS == "START":
      self.logger.start_and_stop_manual()
    self.G_QUIT = True
    time.sleep(0.1)
    
    self.logger.sensor.sensor_ant.quit()
    self.logger.sensor.sensor_gpio.quit()
    self.logger.sensor.sensor_spi.quit()
    self.logger.sensor.sensor_gps.quit()
    if self.G_IS_RASPI:
      GPIO.cleanup()
    
    self.download_thread.join()
    self.loop.close()

    #time.sleep(self.G_LOGGING_INTERVAL)
    self.logger.quit()
    self.write_config()
    self.delete_config_pickle()

  def poweroff(self):
    if self.G_IS_RASPI:
      shutdown_cmd = ["sudo", "systemctl", "start", "pizero_bikecomputer_shutdown.service"]
      self.exec_cmd(shutdown_cmd)

  def update_application(self):
    if self.G_IS_RASPI:
      update_cmd = ["git", "pull", "origin", "master"]
      self.exec_cmd(update_cmd)
      restart_cmd = ["sudo", "systemctl", "restart", "pizero_bikecomputer.service"]
      self.exec_cmd(restart_cmd)

  def get_wifi_bt_status(self):
    status = {
      'wlan': False,
      'bluetooth': False
    }
    if self.G_IS_RASPI:
      try:
        #json opetion requires raspbian buster
        raw_status = self.exec_cmd_return_value(["rfkill", "--json"])
        json_status = json.loads(raw_status)
        for l in json_status['']:
          if 'type' not in l or l['type'] not in ['wlan', 'bluetooth']:
            continue
          if l['soft'] == 'unblocked':
            status[l['type']] = True
      except:
        pass
    return (status['wlan'], status['bluetooth'])

  def wifi_bt_onoff(self):
    #in future, manage with pycomman
    if self.G_IS_RASPI:
      wifioff_cmd = ["rfkill", "block", "wifi"]
      wifion_cmd  = ["rfkill", "unblock", "wifi"]
      btoff_cmd   = ["rfkill", "block", "bluetooth"]
      bton_cmd    = ["rfkill", "unblock", "bluetooth"]

      wifi_status, bt_status = self.get_wifi_bt_status()

      if wifi_status:
        self.exec_cmd(wifioff_cmd)
      else:
        self.exec_cmd(wifion_cmd)
      if bt_status:
        self.exec_cmd(btoff_cmd)
      else:
        self.exec_cmd(bton_cmd)

  async def get_json(self, url):
     async with aiohttp.ClientSession() as session:
       async with session.get(url) as res:
         json = await res.json()
         return json

  def check_time(self, log_str):
     t = datetime.datetime.now()
     print("###", log_str, (t-self.log_time).total_seconds())
     self.log_time = t

  def get_google_routes(self, x1, y1, x2, y2):

    if not self.detect_network() or self.G_GOOGLE_DIRECTION_API["TOKEN"] == "":
      return None
    if np.any(np.isnan([x1, y1, x2, y2])):
      return None
      
    origin = "origin={},{}".format(y1,x1)
    destination = "destination={},{}".format(y2,x2)
    url = "{}&{}&key={}&{}&{}".format(
      self.G_GOOGLE_DIRECTION_API_URL,
      self.G_GOOGLE_DIRECTION_API_MODE["BICYCLING"],
      self.G_GOOGLE_DIRECTION_API["TOKEN"],
      origin,
      destination
    )
    print(url)
    response = self.loop.run_until_complete(self.get_json(url))
    #print(response)
    return response

  def get_openweathermap_data(self, x, y):

    if not self.detect_network() or self.G_OPENWEATHERMAP_API["TOKEN"] == "":
      return None
    if np.any(np.isnan([x, y])):
      return None
      
    url = "{}?lat={}&lon={}&appid={}".format(
      self.G_OPENWEATHERMAP_API_URL,
      y,
      x,
      self.G_OPENWEATHERMAP_API["TOKEN"],
    )
    print(url)
    response = self.loop.run_until_complete(self.get_json(url))
    #print(response)
    return response

  def strava_upload(self):

    #strava setting check
    if self.G_STRAVA_API["CLIENT_ID"] == "" or \
      self.G_STRAVA_API["CLIENT_SECRET"] == "" or\
      self.G_STRAVA_API["CODE"] == "" or \
      self.G_STRAVA_API["ACCESS_TOKEN"] == "" or \
      self.G_STRAVA_API["REFRESH_TOKEN"] == "":
      print("set strava settings (token, client_id, etc)")
      return

    #curl check
    curl_cmd = shutil.which('curl')
    if curl_cmd == None:
      print("curl does not exist")
      return

    #file check/
    if not os.path.exists(self.G_STRAVA_UPLOAD_FILE):
      print("file does not exist")
      return

    #[Todo] network check

    #reflesh access token
    refresh_cmd = [
      "curl", "-L", "-X" "POST", self.G_STRAVA_API_URL["OAUTH"],
      "-d", "client_id="+self.G_STRAVA_API["CLIENT_ID"],
      "-d", "client_secret="+self.G_STRAVA_API["CLIENT_SECRET"],
      "-d", "code="+self.G_STRAVA_API["CODE"],
      "-d", "grant_type=refresh_token",
      "-d", "refresh_token="+self.G_STRAVA_API["REFRESH_TOKEN"],
    ]
    reflesh_result = self.exec_cmd_return_value(refresh_cmd)
    tokens = json.loads(reflesh_result)
    print(tokens)
    if 'access_token' in tokens and 'refresh_token' in tokens and \
      tokens['access_token'] != self.G_STRAVA_API["ACCESS_TOKEN"]:
      print("update strava tokens")
      self.G_STRAVA_API["ACCESS_TOKEN"] = tokens['access_token']
      self.G_STRAVA_API["REFRESH_TOKEN"] = tokens['refresh_token']
    elif 'message' in tokens and tokens['message'].find('Error') > 0:
      print("error occurs at refreshing tokens")
      return
  
    #upload
    upload_cmd = [
      "curl", "-X" "POST", self.G_STRAVA_API_URL["UPLOAD"],
      "-H", "Authorization: Bearer "+self.G_STRAVA_API["ACCESS_TOKEN"],
      "-F", "data_type=fit",
      "-F", "file=@"+self.G_STRAVA_UPLOAD_FILE,
    ]
    upload_result = self.exec_cmd_return_value(upload_cmd)
    tokens = json.loads(upload_result)
    print(tokens)
    if 'status' in tokens:
      print(tokens['status'])

  def read_config(self):
    self.config_parser.read(self.config_file)
         
    if 'GENERAL' in self.config_parser:
      if 'DISPLAY' in self.config_parser['GENERAL']:
        self.G_DISPLAY = self.config_parser['GENERAL']['DISPLAY']
        self.set_resolution()
      if 'AUTOSTOP_CUTOFF' in self.config_parser['GENERAL']:
        self.G_AUTOSTOP_CUTOFF = int(self.config_parser['GENERAL']['AUTOSTOP_CUTOFF'])/3.6
        self.G_GPS_SPEED_CUTOFF = self.G_AUTOSTOP_CUTOFF
      if 'WHEEL_CIRCUMFERENCE' in self.config_parser['GENERAL']:
        self.G_WHEEL_CIRCUMFERENCE = int(self.config_parser['GENERAL']['WHEEL_CIRCUMFERENCE'])/1000
      if 'GROSS_AVE_SPEED' in self.config_parser['GENERAL']:
        self.G_GROSS_AVE_SPEED = int(self.config_parser['GENERAL']['GROSS_AVE_SPEED'])
      if 'AUTO_BACKLIGHT_CUTOFF' in self.config_parser['GENERAL']:
        self.G_AUTO_BACKLIGHT_CUTOFF = int(self.config_parser['GENERAL']['AUTO_BACKLIGHT_CUTOFF'])
      if 'LANG' in self.config_parser['GENERAL']:
        self.G_LANG = self.config_parser['GENERAL']['LANG'].upper()
      if 'FONT_FILE' in self.config_parser['GENERAL']:
        self.G_FONT_FILE = self.config_parser['GENERAL']['FONT_FILE']
      if 'MAP' in self.config_parser['GENERAL']:
        self.G_MAP = self.config_parser['GENERAL']['MAP'].lower()

    if 'POWER' in self.config_parser:
      if 'CP' in self.config_parser['POWER']:
        self.G_POWER_CP = int(self.config_parser['POWER']['CP'])
      if 'W_PRIME' in self.config_parser['POWER']:
        self.G_POWER_W_PRIME = int(self.config_parser['POWER']['W_PRIME'])

    if 'ANT' in self.config_parser:
      for key in self.config_parser['ANT']:

        if key.upper() == 'STATUS':
          self.G_ANT['STATUS'] = self.config_parser['ANT'].getboolean(key)
          continue
        i = key.rfind("_")
        
        if i < 0:
          continue
        
        key1 = key[0:i]
        key2 = key[i+1:]
        try:
          k1 = key1.upper()
          k2 = key2.upper()
        except:
          continue
        if k1 == 'USE' and k2 in self.G_ANT['ID'].keys(): #['HR','SPD','CDC','PWR']:
          try:
            self.G_ANT[k1][k2] = self.config_parser['ANT'].getboolean(key)
          except:
            pass
        elif k1 in ['ID','TYPE'] and k2 in self.G_ANT['ID'].keys(): #['HR','SPD','CDC','PWR']:
          try:
            self.G_ANT[k1][k2] = self.config_parser['ANT'].getint(key)
          except:
            pass
      for key in self.G_ANT['ID'].keys(): #['HR','SPD','CDC','PWR']:
        if not (0 <= self.G_ANT['ID'][key] <= 0xFFFF) or\
           not self.G_ANT['TYPE'][key] in self.G_ANT['TYPES'][key]:
          self.G_ANT['USE'][key] = False
          self.G_ANT['ID'][key] = 0
          self.G_ANT['TYPE'][key] = 0
        if self.G_ANT['ID'][key] != 0 and self.G_ANT['TYPE'][key] != 0:
          self.G_ANT['ID_TYPE'][key] = \
            struct.pack('<HB', self.G_ANT['ID'][key], self.G_ANT['TYPE'][key]) 
    
    if 'SENSOR_IMU' in self.config_parser:
      for s, c, m in [
        ['AXIS_CONVERSION_STATUS', 'AXIS_CONVERSION_COEF', self.G_IMU_AXIS_CONVERSION], 
        ['AXIS_SWAP_XY_STATUS', '', self.G_IMU_AXIS_SWAP_XY]]:
        if s.lower() in self.config_parser['SENSOR_IMU']:
          m['STATUS'] = self.config_parser['SENSOR_IMU'].getboolean(s)
        if c != '' and c.lower() in self.config_parser['SENSOR_IMU']:
          coef = np.array(json.loads(self.config_parser['SENSOR_IMU'][c]))
          n = m['COEF'].shape[0]
          if np.sum((coef == 1) | (coef == -1)) == n:
            m['COEF'] = coef[0:n]
        if 'MAG_DECLINATION' in self.config_parser['SENSOR_IMU']:
          self.G_IMU_MAG_DECLINATION = int(self.config_parser['SENSOR_IMU']['MAG_DECLINATION'])
      
    if 'STRAVA_API' in self.config_parser:
      for k in self.G_STRAVA_API.keys():
        if k in self.config_parser['STRAVA_API']:
          self.G_STRAVA_API[k] = self.config_parser['STRAVA_API'][k]
    
    if 'STRAVA_COOKIE' in self.config_parser:
      for k in self.G_STRAVA_COOKIE.keys():
        if k in self.config_parser['STRAVA_COOKIE']:
          self.G_STRAVA_COOKIE[k] = self.config_parser['STRAVA_COOKIE'][k]
    
    if 'GOOGLE_DIRECTION_API' in self.config_parser:
      for k in self.G_GOOGLE_DIRECTION_API.keys():
        if k in self.config_parser['GOOGLE_DIRECTION_API']:
          self.G_GOOGLE_DIRECTION_API[k] = self.config_parser['GOOGLE_DIRECTION_API'][k]
      if self.G_GOOGLE_DIRECTION_API["TOKEN"] != "":
        self.G_HAVE_GOOGLE_DIRECTION_API_TOKEN = True
    
    if 'OPENWEATHERMAP_API' in self.config_parser:
      for k in self.G_OPENWEATHERMAP_API.keys():
        if k in self.config_parser['OPENWEATHERMAP_API']:
          self.G_OPENWEATHERMAP_API[k] = self.config_parser['OPENWEATHERMAP_API'][k]
      if self.G_OPENWEATHERMAP_API["TOKEN"] != "":
        self.G_HAVE_OPENWEATHERMAP_API_TOKEN = True

    if 'BT_ADDRESS' in self.config_parser:
      for k in self.config_parser['BT_ADDRESS']:
        self.G_BT_ADDRESS[k] = str(self.config_parser['BT_ADDRESS'][k])

  def write_config(self):

    self.config_parser['GENERAL'] = {}
    self.config_parser['GENERAL']['DISPLAY'] = self.G_DISPLAY
    self.config_parser['GENERAL']['AUTOSTOP_CUTOFF'] = str(int(self.G_AUTOSTOP_CUTOFF*3.6))
    self.config_parser['GENERAL']['WHEEL_CIRCUMFERENCE'] = str(int(self.G_WHEEL_CIRCUMFERENCE*1000))
    self.config_parser['GENERAL']['GROSS_AVE_SPEED'] = str(int(self.G_GROSS_AVE_SPEED))
    self.config_parser['GENERAL']['AUTO_BACKLIGHT_CUTOFF'] = str(int(self.G_AUTO_BACKLIGHT_CUTOFF))
    self.config_parser['GENERAL']['LANG'] = self.G_LANG
    self.config_parser['GENERAL']['FONT_FILE'] = self.G_FONT_FILE
    self.config_parser['GENERAL']['MAP'] = self.G_MAP

    self.config_parser['POWER'] = {}
    self.config_parser['POWER']['CP'] = str(int(self.G_POWER_CP))
    self.config_parser['POWER']['W_PRIME'] = str(int(self.G_POWER_W_PRIME))

    if not self.G_DUMMY_OUTPUT:
      self.config_parser['ANT'] = {}
      self.config_parser['ANT']['STATUS'] = str(self.G_ANT['STATUS'])
      for key1 in ['USE','ID','TYPE']:
        for key2 in self.G_ANT[key1]:
          if key2 in self.G_ANT['ID'].keys(): #['HR','SPD','CDC','PWR']:
            self.config_parser['ANT'][key1+"_"+key2] = str(self.G_ANT[key1][key2])
    
    self.config_parser['SENSOR_IMU'] = {}
    self.config_parser['SENSOR_IMU']['AXIS_SWAP_XY_STATUS'] = str(self.G_IMU_AXIS_SWAP_XY['STATUS'])
    self.config_parser['SENSOR_IMU']['AXIS_CONVERSION_STATUS'] = str(self.G_IMU_AXIS_CONVERSION['STATUS'])
    self.config_parser['SENSOR_IMU']['AXIS_CONVERSION_COEF'] = str(list(self.G_IMU_AXIS_CONVERSION['COEF']))
    self.config_parser['SENSOR_IMU']['MAG_DECLINATION'] = str(int(self.G_IMU_MAG_DECLINATION))

    self.config_parser['STRAVA_API'] = {}
    for k in self.G_STRAVA_API.keys():
      self.config_parser['STRAVA_API'][k] = self.G_STRAVA_API[k] 

    self.config_parser['STRAVA_COOKIE'] = {}
    for k in self.G_STRAVA_COOKIE.keys():
      self.config_parser['STRAVA_COOKIE'][k] = self.G_STRAVA_COOKIE[k]

    self.config_parser['GOOGLE_DIRECTION_API'] = {}
    for k in self.G_GOOGLE_DIRECTION_API.keys():
      self.config_parser['GOOGLE_DIRECTION_API'][k] = self.G_GOOGLE_DIRECTION_API[k] 

    self.config_parser['OPENWEATHERMAP_API'] = {}
    for k in self.G_OPENWEATHERMAP_API.keys():
      self.config_parser['OPENWEATHERMAP_API'][k] = self.G_OPENWEATHERMAP_API[k] 
    
    self.config_parser['BT_ADDRESS'] = {}
    for k in self.G_BT_ADDRESS.keys():
      self.config_parser['BT_ADDRESS'][k] = self.G_BT_ADDRESS[k]

    with open(self.config_file, 'w') as file:
      self.config_parser.write(file)
  
  def read_config_pickle(self):
    with open(self.config_pickle_file, 'rb') as f:
      self.config_pickle = pickle.load(f)

  def set_config_pickle(self, key, value, quick_apply=False):
    self.config_pickle[key] = value
    #write with config_pickle_interval
    t = (datetime.datetime.utcnow()-self.config_pickle_write_time).total_seconds()
    if not quick_apply and t < self.config_pickle_interval:
      return
    with open(self.config_pickle_file, 'wb') as f:
      pickle.dump(self.config_pickle, f)
    self.config_pickle_write_time = datetime.datetime.utcnow()
  
  def get_config_pickle(self, key, default_value):
    if key in self.config_pickle:
      return self.config_pickle[key]
    else:
      return default_value

  #reset 
  def reset_config_pickle(self):
    for k, v in list(self.config_pickle.items()):
      if "mag" in k:
        continue
      del(self.config_pickle[k])
    with open(self.config_pickle_file, 'wb') as f:
      pickle.dump(self.config_pickle, f)

  #quit
  def delete_config_pickle(self):
    for k, v in list(self.config_pickle.items()):
      if "ant+" in k:
        del(self.config_pickle[k])
    with open(self.config_pickle_file, 'wb') as f:
      pickle.dump(self.config_pickle, f)

  def read_map_list(self):
    text = None
    with open(self.G_MAP_LIST) as file:
      text = file.read()
      map_list = yaml.safe_load(text)
      if map_list == None:
        return
      for key in map_list:
        if map_list[key]['attribution'] == None:
          map_list[key]['attribution'] = ""
      self.G_MAP_CONFIG.update(map_list)

  def get_track_str(self, drc):
    track_int = int((drc + 22.5)/45.0)
    return self.TRACK_STR[track_int]
  
  #return [m]
  def get_dist_on_earth(self, p0_lon, p0_lat, p1_lon, p1_lat):
    if p0_lon == p1_lon and p0_lat == p1_lat:
      return 0
    (r0_lon, r0_lat, r1_lon, r1_lat) = map(math.radians, [p0_lon, p0_lat, p1_lon, p1_lat])
    delta_x = r1_lon-r0_lon
    cos_d = math.sin(r0_lat)*math.sin(r1_lat) + math.cos(r0_lat)*math.cos(r1_lat)*math.cos(delta_x)
    try:
      res = 1000*math.acos(cos_d)*self.GEO_R1
      return res
    except:
      #traceback.print_exc()
      #print("cos_d =", cos_d)
      #print("paramater:", p0_lon, p0_lat, p1_lon, p1_lat)
      return 0
  
  #return [m]
  def get_dist_on_earth_array(self, p0_lon, p0_lat, p1_lon, p1_lat):
    #if p0_lon == p1_lon and p0_lat == p1_lat:
    #  return 0
    r0_lon = np.radians(p0_lon)
    r0_lat = np.radians(p0_lat)
    r1_lon = np.radians(p1_lon)
    r1_lat = np.radians(p1_lat)
    #(r0_lon, r0_lat, r1_lon, r1_lat) = map(radians, [p0_lon, p0_lat, p1_lon, p1_lat])
    delta_x = r1_lon-r0_lon
    cos_d = np.sin(r0_lat)*np.sin(r1_lat) + np.cos(r0_lat)*np.cos(r1_lat)*np.cos(delta_x)
    try:
      res = 1000*np.arccos(cos_d)*self.GEO_R1
      return res
    except:
      traceback.print_exc()
    #  #print("cos_d =", cos_d)
    #  #print("paramater:", p0_lon, p0_lat, p1_lon, p1_lat)
      return np.array([])
  
  #return [m]
  def get_dist_on_earth_hubeny(self, p0_lon, p0_lat, p1_lon, p1_lat):
    if p0_lon == p1_lon and p0_lat == p1_lat:
      return 0
    (r0_lon, r0_lat, r1_lon, r1_lat) = map(math.radians, [p0_lon, p0_lat, p1_lon, p1_lat])
    lat_t = (r0_lat + r1_lat) / 2
    w = 1 - self.GEO_E2 * math.sin(lat_t) ** 2
    c2 = math.cos(lat_t) ** 2
    return math.sqrt((self.GEO_R2_2 / w ** 3) * (r0_lat - r1_lat) ** 2 + (self.GEO_R1_2 / w) * c2 * (r0_lon - r1_lon) ** 2)

  def calc_azimuth(self, lat, lon):
    rad_latitude = np.radians(lat)
    rad_longitude = np.radians(lon)
    rad_longitude_delta = rad_longitude[1:] - rad_longitude[0:-1]
    azimuth = np.mod(np.degrees(np.arctan2(
      np.sin(rad_longitude_delta), 
      np.cos(rad_latitude[0:-1])*np.tan(rad_latitude[1:])-np.sin(rad_latitude[0:-1])*np.cos(rad_longitude_delta)
      )), 360).astype(dtype='int16')
    return azimuth
  
  def get_altitude_from_tile(self, pos):
    if np.isnan(pos[0]) or np.isnan(pos[1]):
      return np.nan
    z = self.G_MAP_CONFIG[self.G_DEM_MAP]['fix_zoomlevel']
    f_x, f_y, p_x, p_y = self.get_tilexy_and_xy_in_tile(z, pos[0], pos[1], 256)
    filename = self.get_maptile_filename(self.G_DEM_MAP, z, f_x, f_y)
    
    if not os.path.exists(filename):
      self.download_demtile(z, f_x, f_y)
      return np.nan
    if os.path.getsize(filename) == 0:
      return np.nan

    if self.loaded_dem != (f_x, f_y):
      self.dem_array = np.asarray(Image.open(filename))
      self.loaded_dem = (f_x, f_y)
    rgb_pos = self.dem_array[p_y, p_x]
    altitude = rgb_pos[0]*(2**16) + rgb_pos[1]*(2**8) + rgb_pos[2]
    if altitude < 2**23:
      altitude = altitude*0.01
    elif altitude == 2**23:
      altitude = np.nan
    else:
      altitude = (altitude - 2**24)*0.01

    #print(altitude, filename, p_x, p_y, pos[1], pos[0])
    return altitude

  def get_tilexy_and_xy_in_tile(self, z, x, y, tile_size):
    n = 2.0 ** z
    _y = math.radians(y)
    x_in_tile, tile_x = math.modf((x + 180.0) / 360.0 * n)
    y_in_tile, tile_y = math.modf((1.0 - math.log(math.tan(_y) + (1.0/math.cos(_y))) / math.pi) / 2.0 * n)

    return int(tile_x), int(tile_y), int(x_in_tile*tile_size), int(y_in_tile*tile_size)
  
  def get_lon_lat_from_tile_xy(self, z, x, y):
    n = 2.0 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))

    return lon, lat

  #replacement of dateutil.parser.parse
  def datetime_myparser(self, ts):
    if len(ts) == 14:
      #20190322232414 / 14 chars
      dt = datetime.datetime(
        int(ts[0:4]),    # %Y
        int(ts[4:6]),    # %m
        int(ts[6:8]),   # %d
        int(ts[8:10]),  # %H
        int(ts[10:12]),  # %M
        int(ts[12:14]),  # %s
      )
      return dt
    elif 24 <= len(ts) <= 26:
      #2019-03-22T23:24:14.280604 / 26 chars
      #2019-09-30T12:44:55.000Z   / 24 chars
      dt = datetime.datetime(
        int(ts[0:4]),    # %Y
        int(ts[5:7]),    # %m
        int(ts[8:10]),   # %d
        int(ts[11:13]),  # %H
        int(ts[14:16]),  # %M
        int(ts[17:19]),  # %s
      )
      return dt
    print("err", ts, len(ts))
