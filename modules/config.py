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
import urllib.error
import urllib.request
import traceback
import json
from math import sin, cos, acos, radians, sqrt, tan, degrees

import numpy as np
import oyaml as yaml

_IS_RASPI = False
try:
  import RPi.GPIO as GPIO
  GPIO.setmode(GPIO.BCM)
  #GPIO.setmode(GPIO.BOARD)
  _IS_RASPI = True
except:
  pass


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

  #calculate index on course
  G_COURSE_INDEXING = True

  ###########################
  # fixed or pointer values #
  ###########################

  #product name, version
  G_PRODUCT = "Pizero Bikecomputer"
  G_VERSION_MAJOR = 0 #need to be initialized
  G_VERSION_MINOR = 1 #need to be initialized
  G_UNIT_ID = "0000000000000000" #initialized in get_serial
  G_UNIT_ID_HEX = 0 #initialized in get_serial

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
  G_CUESHEET_DISPLAY_NUM = 5 #max: 5
  G_CUESHEET_SCROLL = False

  #log setting
  G_LOG_DIR = "log/"
  G_LOG_DB = G_LOG_DIR + "log.db"
  G_LOG_START_DATE = None
  
  #map setting
  #default map (can overwrite in settings.conf)
  G_MAP = 'toner'
  #use dithering (convert command feom imagemagick)
  G_DITHERING = False
  G_MAP_CONFIG = {
    'toner': {
      # 0:z(zoom), 1:tile_x, 2:tile_y
      'url': "http://a.tile.stamen.com/toner/{z}/{x}/{y}.png",
      'attribution': 'Map tiles by Stamen Design, under CC BY 3.0.<br />Data by OpenStreetMap, under ODbL',
    },
    'wikimedia': {
      'url': "https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}.png",
      'attribution': '© OpenStreetMap contributors',
    },
    'jpn_kokudo_chiri_in': {
      'url': "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png",
      'attribution': '国土地理院'
    },
  }
  #external input of G_MAP_CONFIG
  G_MAP_LIST = "map.yaml"

  #config file (use in config only)
  config_file = "setting.conf"
  config_parser = None

  #screenshot dir
  G_SCREENSHOT_DIR = 'screenshot/'

  #debug switch (change with --debug option)
  G_IS_DEBUG = False

  #dummy sampling value output (change with --demo option)
  G_DUMMY_OUTPUT = False

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
      #'CTRL':False,
      },
    'NAME':{
      'HR':'HeartRate',
      'SPD':'Speed',
      'CDC':'Cadence',
      'PWR':'Power',
      #'CTRL':'control',
      },
    'ID':{
      'HR':0,
      'SPD':0,
      'CDC':0,
      'PWR':0,
      #'CTRL':0,
      },
    'TYPE':{
      'HR':0,
      'SPD':0,
      'CDC':0,
      'PWR':0,
      #'CTRL':0,
      },
    'ID_TYPE':{
      'HR':0,
      'SPD':0,
      'CDC':0,
      'PWR':0,
      #'CTRL':0,
      },
    'TYPES':{
      'HR':(0x78,),
      'SPD':(0x79,0x7B),
      'CDC':(0x79,0x7A,0x0B),
      'PWR':(0x0B,),
      #'CTRL':(0x10,),
      },
    'TYPE_NAME':{
      0x78:'HeartRate',
      0x79:'Speed and Cadence',
      0x7A:'Cadence',
      0x7B:'Speed',
      0x0B:'Power',
      #0x10:'Control',
      },
    #for display order in ANT+ menu (antMenuWidget)
    'ORDER':['HR','SPD','CDC','PWR'],
    #'ORDER':['HR','SPD','CDC','PWR','CTRL'],
   }
  
  #GPS Null value
  G_GPS_NULLVALUE = "n/a"
  #GPS speed cutoff (the distance in 1 seconds at 0.36km/h is 10cm)
  G_GPS_SPEED_CUTOFF = G_AUTOSTOP_CUTOFF #m/s
  #timezone (not use, get from GPS position)
  G_TIMEZONE = None

  #fullscreen switch (overwritten with setting.conf)
  G_FULLSCREEN = False
  #display type (overwritten with setting.conf)
  G_DISPLAY = 'PiTFT' #PiTFT, MIP, Papirus
  #screen size (need to add when adding new device)
  G_AVAILABLE_DISPLAY = {
    'PiTFT': {'size':(320, 240),'touch':True},
    'MIP': {'size':(400, 240),'touch':False},
    'Papirus': {'size':(264, 176),'touch':False},
    #'DFRobot_RPi_Display': {'size':(250, 122),'touch':False}
  }
  G_WIDTH = 320
  G_HEIGHT = 240
  #GUI mode
  G_GUI_MODE = "PyQt"
  #G_GUI_MODE = "QML" #not valid

  #hr and power graph (PerformanceGraphWidget)
  G_GUI_HR_POWER_DISPLAY_RANGE = int(1*60/G_SENSOR_INTERVAL) # num (no unit)
  G_GUI_MIN_HR = 50
  G_GUI_MAX_HR = 180
  G_GUI_MIN_POWER = 30
  G_GUI_MAX_POWER = 320
  #acceleration graph (AccelerationGraphWidget)
  G_GUI_REALTIME_GRAPH_RANGE = int(1*60/(G_REALTIME_GRAPH_INTERVAL/1000)) # num (no unit)

  #Graph color by slope
  G_SLOPE_BIN = 500 #m
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
   (255,0,0),      #red
   (255,0,255),    #purple
  )

  #map widgets
  #max zoom
  G_MAX_ZOOM = 0
  #interval distance when mapping track
  G_GPS_DISPLAY_INTERVAL_DISTANCE = 5 #m
  #for map dummy center: Tokyo station in Japan
  G_DUMMY_POS_X = 139.767008
  G_DUMMY_POS_Y = 35.681929
  #for search point on course
  G_GPS_ON_ROUTE_CUTOFF = 50 #[m] #generate from course
  G_GPS_SEARCH_RANGE = 5 #[km] #100km/h -> 27.7m/s

  #STRAVA token (need to write setting.conf manually)
  G_STRAVA = {
    "CLIENT_ID": "",
    "CLIENT_SECRET": "",
    "CODE": "",
    "ACCESS_TOKEN": "",
    "REFRESH_TOKEN": "",
  }
  G_STRAVA_UPLOAD_FILE = ""

  #auto backlight with spi mip display
  #(PiTFT actually needs max brightness under sunlights, so there are no implementation with PiTFT)
  G_USE_AUTO_BACKLIGHT = True
  G_USE_AUTO_CUTOFF = 0

  #blue tooth setting
  G_BT_ADDRESS = {}
  G_BT_CMD_BASE = ["/usr/local/bin/bt-pan","client"]

  #long press threshold of buttons [sec]
  G_BUTTON_LONG_PRESS = 2

  #GPIO button action (short press / long press) from gui (or G_GUIKivy)
  # use in SensorGPIO.my_callback(self, channel)
  # number is from GPIO.setmode(GPIO.BCM)
  G_GPIO_BUTTON_DEF = {
    'PiTFT' : {
      'MAIN':{
        5:("brightness_control()","scroll_menu()"),
        6:("logger.count_laps()","logger.reset_count()"),
        12:("get_screenshot()",""),
        13:("logger.start_and_stop_manual()","quit()"),
        16:("scroll_next()",""),
        },
      'MENU':{
        5:("scroll_menu()","dummy()"),
        6:("dummy()","dummy()"),
        12:("press_space()","dummy()"),
        13:("press_tab()","dummy()"),
        16:("press_down()","dummy()"),
        },
      },
    'Papirus' : {
      'MAIN':{
        16:("scroll_prev()","scroll_menu()"),#SW1(left)
        26:("logger.count_laps()","logger.reset_count()"),#SW2
        20:("logger.start_and_stop_manual()","dummy()"),#SW3
        21:("scroll_next()","dummy()"),#SW4
        },
      'MENU':{
        16:("scroll_menu()","dummy()"),
        26:("press_space()","dummy()"),
        20:("press_tab()","dummy()"),
        21:("press_down()","dummy()"),
        },
      },
    'DFRobot_RPi_Display' : {
      'MAIN':{
        29:("logger.start_and_stop_manual()","logger.reset_count()"),
        28:("scroll_next()","scroll_menu()"),
        },
      'MAIN':{
        29:("press_space()","dummy()"),
        28:("press_down()","scroll_menu()"),
        },
      },
    'Button_Shim' : {
      'MAIN':{
        'A':("scroll_prev","scroll_menu"),
        'B':("logger.count_laps","logger.reset_count"),
        'C':("get_screenshot","dummy"),
        'D':("logger.start_and_stop_manual","dummy"),
        'E':("scroll_next","dummy"),
        },
      'MENU':{
        'A':("scroll_menu","dummy"),
        'B':("brightness_control","dummy"),
        'C':("press_space","dummy"),
        'D':("press_tab","dummy"),
        'E':("press_down","dummy"),
        },
      },
  }
  #[Todo] I2C button action (now it is implemented in ButtonShim directly)
  G_I2C_BUTTON_DEF = {}
  #[Todo] ANT+ Control button action (now it is implemented in ButtonShim directly)
  G_ANT_CTRL_BUTTON_DEF = {}
  
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
    #show options
    if self.G_IS_DEBUG:
      print(args)
    
    #object for setting.conf
    self.config_parser = configparser.ConfigParser()
    if os.path.exists(self.config_file):
      self.read_config()
    
    #set dir(for using from pitft desktop)
    if self.G_IS_RASPI:
      self.G_SCREENSHOT_DIR = self.G_INSTALL_PATH + self.G_SCREENSHOT_DIR 
      self.G_LOG_DIR = self.G_INSTALL_PATH + self.G_LOG_DIR
      self.G_LOG_DB = self.G_INSTALL_PATH + self.G_LOG_DB
      self.config_file = self.G_INSTALL_PATH + self.config_file
      self.G_LAYOUT_FILE = self.G_INSTALL_PATH + self.G_LAYOUT_FILE
      self.G_COURSE_FILE = self.G_INSTALL_PATH + self.G_COURSE_FILE
    
    #font file
    if self.G_FONT_FILE != "" or self.G_FONT_FILE != None:
      if os.path.exists(self.G_FONT_FILE):
        self.G_FONT_FULLPATH = self.G_FONT_FILE

    #map list
    if os.path.exists(self.G_MAP_LIST):
      self.read_map_list()
    if self.G_MAP not in self.G_MAP_CONFIG:
      print("don't exist map \"{}\" in {}".format(self.G_MAP, self.G_MAP_LIST), file=sys.stderr)
      self.G_MAP = "toner"

    #mkdir
    if not os.path.exists(self.G_SCREENSHOT_DIR):
      os.mkdir(self.G_SCREENSHOT_DIR)
    if not os.path.exists(self.G_LOG_DIR):
      os.mkdir(self.G_LOG_DIR)
    if not os.path.exists("maptile/"+self.G_MAP):
      os.mkdir("maptile/"+self.G_MAP)
    if not os.path.exists("maptile/.tmp/"):
      os.mkdir("maptile/.tmp/")
    if not os.path.exists("maptile/.tmp/"+self.G_MAP):
      os.mkdir("maptile/.tmp/"+self.G_MAP)

    #get serial number
    self.get_serial()
    
    self.detect_display()
    self.set_resolution()

    #set ant interval. 0:4Hz(0.25s), 1:2Hz(0.5s), 2:1Hz(1.0s)
    if self.G_ANT_INTERVAL == 0.25:
      self.G_ANT['INTERVAL'] = 0
    elif self.G_ANT_INTERVAL == 0.5:
      self.G_ANT['INTERVAL'] = 1
    else:
      self.G_ANT['INTERVAL'] = 2

    #thread for downloading map tiles
    self.download_queue = queue.Queue()
    self.download_thread = threading.Thread(target=self.download_worker, name="download_worker", args=())
    self.download_thread.start()
    self.convert_cmd = shutil.which('convert')
    if self.G_DITHERING and self.convert_cmd != None:
      self.convert_queue = queue.Queue()
      self.convert_thread = threading.Thread(target=self.convert_worker, name="convert_worker", args=())
      self.convert_thread.start()
    else:
      self.G_DITHERING = False

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
          self.G_UNIT_ID_HEX = eval("0x"+self.G_UNIT_ID[-8:])
      f.close()
    except:
      pass
  
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
  
  def get_maptile_filename(self, z, x, y):
    return "maptile/"+self.G_MAP+"/{0}-{1}-{2}.png".format(z, x, y)

  def get_maptile_filename_tmp(self, z, x, y):
    return "maptile/.tmp/"+self.G_MAP+"/{0}-{1}-{2}.png".format(z, x, y)

  def download_maptile(self, z, x, y):
    try:
      _y = y
      _z = z
      if 'yahoo' in self.G_MAP:
        _z += 1
        _y = 2**(z-1)-y-1 
      #throw cue if convert exists
      map_dst = self.get_maptile_filename(z, x, y)
      tmp_dst = self.get_maptile_filename_tmp(z, x, y)
      dl_dst = map_dst
      if self.G_DITHERING:
        dl_dst = tmp_dst
      self.download_queue.put((
        self.G_MAP_CONFIG[self.G_MAP]['url'].format(z=_z, x=x, y=_y), 
        dl_dst
        ))
      if self.G_DITHERING:
        self.convert_queue.put((dl_dst, map_dst))
      return True
    except:
      #traceback.print_exc()
      return False

  def download_worker(self):
    last_download_time = datetime.datetime.now()
    online = True

    while not self.G_QUIT:
      while online and not self.download_queue.empty():
        url, dst_path = self.download_queue.get()
        if self.download_file(url, dst_path):
          self.download_queue.task_done()
          last_download_time = datetime.datetime.now()
        else:
          online = False
          self.download_queue.put((url, dst_path))
      
      if (datetime.datetime.now()-last_download_time).total_seconds() > 60*3: #[s]
        last_download_time = datetime.datetime.now()
        online = True

      time.sleep(0.5)
      
  def download_file(self, url, dst_path):
    try:
      with urllib.request.urlopen(url, timeout=5) as web_file:
        data = web_file.read()
        with open(dst_path, mode='wb') as local_file:
          local_file.write(data)
          return True
    except urllib.error.URLError as e:
      return False
  
  def convert_worker(self):
    if not self.G_DITHERING:
      return

    #last_convert_time = datetime.datetime.now()
    cue_timestamp = datetime.datetime.now()
    online = True
    dl_dst = map_dst = None

    while not self.G_QUIT:
      if online and not self.convert_queue.empty():
        dl_dst, map_dst = self.convert_queue.get()
        cue_timestamp = datetime.datetime.now()
     
      if dl_dst != None and os.path.exists(dl_dst) and self.convert(dl_dst, map_dst):
        self.convert_queue.task_done()
        dl_dst = map_dst = None
      else:
        online = False
      
      #if not online or dl_dst == None:
      if not online:
        time.sleep(0.5)

      if (datetime.datetime.now()-cue_timestamp).total_seconds() > 3: #[s]
        cue_timestamp = datetime.datetime.now()
        online = True
  
  def convert(self, dl_dst, map_dst):
    try:
      #convert xc:red xc:lime xc:blue xc:cyan xc:magenta xc:yellow xc:white xc:black -append 3bit_rgb.png
      #convert in.png -dither FloydSteinberg -remap mymap.png out.png
      convert_cmd = [self.convert_cmd, dl_dst, "-dither", "FloydSteinberg", "-remap", "img/3bit_rgb.png", dl_dst+".conv"]
      self.exec_cmd(convert_cmd, cmd_print=False)
      shutil.move(dl_dst+".conv", map_dst)
      os.remove(dl_dst)
      return True
    except:
      traceback.print_exc()
      return False
    
  def quit(self):
    print("quit")
    self.G_QUIT = True
    time.sleep(0.1)
    self.logger.sensor.sensor_ant.quit()
    self.logger.sensor.sensor_gpio.quit()
    self.logger.sensor.sensor_spi.quit()
    self.logger.sensor.sensor_gps.quit()
    if self.G_IS_RASPI:
      GPIO.cleanup()
    self.write_config()

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

  def strava_upload(self):

    #strava setting check
    if self.G_STRAVA["CLIENT_ID"] == "" or \
      self.G_STRAVA["CLIENT_SECRET"] == "" or\
      self.G_STRAVA["CODE"] == "" or \
      self.G_STRAVA["ACCESS_TOKEN"] == "" or \
      self.G_STRAVA["REFRESH_TOKEN"] == "":
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
      "curl", "-L", "-X" "POST", "https://www.strava.com/oauth/token",
      "-d", "client_id="+self.G_STRAVA["CLIENT_ID"],
      "-d", "client_secret="+self.G_STRAVA["CLIENT_SECRET"],
      "-d", "code="+self.G_STRAVA["CODE"],
      "-d", "grant_type=refresh_token",
      "-d", "refresh_token="+self.G_STRAVA["REFRESH_TOKEN"],
    ]
    reflesh_result = self.exec_cmd_return_value(refresh_cmd)
    tokens = json.loads(reflesh_result)
    print(tokens)
    if 'access_token' in tokens and 'refresh_token' in tokens and \
      tokens['access_token'] != self.G_STRAVA["ACCESS_TOKEN"]:
      print("update strava tokens")
      self.G_STRAVA["ACCESS_TOKEN"] = tokens['access_token']
      self.G_STRAVA["REFRESH_TOKEN"] = tokens['refresh_token']
    elif 'message' in tokens and tokens['message'].find('Error') > 0:
      print("error occurs at refreshing tokens")
      return
  
    #upload
    upload_cmd = [
      "curl", "-X" "POST", "https://www.strava.com/api/v3/uploads",
      "-H", "Authorization: Bearer "+self.G_STRAVA["ACCESS_TOKEN"],
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
        if k1 == 'USE' and k2 in ['HR','SPD','CDC','PWR']:
          try:
            self.G_ANT[k1][k2] = self.config_parser['ANT'].getboolean(key)
          except:
            pass
        elif k1 in ['ID','TYPE'] and k2 in ['HR','SPD','CDC','PWR']:
          try:
            self.G_ANT[k1][k2] = self.config_parser['ANT'].getint(key)
          except:
            pass
      for key in ['HR','SPD','CDC','PWR']:
        if not (0 <= self.G_ANT['ID'][key] <= 0xFFFF) or\
           not self.G_ANT['TYPE'][key] in self.G_ANT['TYPES'][key]:
          self.G_ANT['USE'][key] = False
          self.G_ANT['ID'][key] = 0
          self.G_ANT['TYPE'][key] = 0
        if self.G_ANT['ID'][key] != 0 and self.G_ANT['TYPE'][key] != 0:
          self.G_ANT['ID_TYPE'][key] = \
            struct.pack('<HB', self.G_ANT['ID'][key], self.G_ANT['TYPE'][key]) 
     
    if 'GENERAL' in self.config_parser:
      if 'DISPLAY' in self.config_parser['GENERAL']:
        self.G_DISPLAY = self.config_parser['GENERAL']['DISPLAY']
        self.set_resolution()
      if 'AUTOSTOP_CUTOFF' in self.config_parser['GENERAL']:
        self.G_AUTOSTOP_CUTOFF = int(self.config_parser['GENERAL']['AUTOSTOP_CUTOFF'])/3.6
        self.G_GPS_SPEED_CUTOFF = self.G_AUTOSTOP_CUTOFF
      if 'LANG' in self.config_parser['GENERAL']:
        self.G_LANG = self.config_parser['GENERAL']['LANG'].upper()
      if 'FONT_FILE' in self.config_parser['GENERAL']:
        self.G_FONT_FILE = self.config_parser['GENERAL']['FONT_FILE']
      if 'MAP' in self.config_parser['GENERAL']:
        self.G_MAP = self.config_parser['GENERAL']['MAP'].lower()
      
    if 'STRAVA' in self.config_parser:
      for k in self.G_STRAVA.keys():
        if k in self.config_parser['STRAVA']:
          self.G_STRAVA[k] = self.config_parser['STRAVA'][k]

    if 'BT_ADDRESS' in self.config_parser:
      for k in self.config_parser['BT_ADDRESS']:
        self.G_BT_ADDRESS[k] = str(self.config_parser['BT_ADDRESS'][k])

  def write_config(self):
    if not self.G_DUMMY_OUTPUT:
      self.config_parser['ANT'] = {}
      self.config_parser['ANT']['STATUS'] = str(self.G_ANT['STATUS'])
      for key1 in ['USE','ID','TYPE']:
        for key2 in self.G_ANT[key1]:
          if key2 in ['HR','SPD','CDC','PWR']:
            self.config_parser['ANT'][key1+"_"+key2] = str(self.G_ANT[key1][key2])
    self.config_parser['GENERAL'] = {}
    self.config_parser['GENERAL']['DISPLAY'] = self.G_DISPLAY
    self.config_parser['GENERAL']['AUTOSTOP_CUTOFF'] = str(int(self.G_AUTOSTOP_CUTOFF*3.6))
    self.config_parser['GENERAL']['LANG'] = self.G_LANG
    self.config_parser['GENERAL']['FONT_FILE'] = self.G_FONT_FILE
    self.config_parser['GENERAL']['MAP'] = self.G_MAP
    
    self.config_parser['STRAVA'] = {}
    for k in self.G_STRAVA.keys():
      self.config_parser['STRAVA'][k] = self.G_STRAVA[k] 

    self.config_parser['BT_ADDRESS'] = {}
    for k in self.G_BT_ADDRESS.keys():
      self.config_parser['BT_ADDRESS'][k] = self.G_BT_ADDRESS[k]

    with open(self.config_file, 'w') as file:
      self.config_parser.write(file)
  
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
    #drc_int = int((drc + 11.25)/22.50)
    track_int = int((drc + 22.5)/45.0)
    return self.TRACK_STR[track_int]
  
  #return [m]
  def get_dist_on_earth(self, p0_lon, p0_lat, p1_lon, p1_lat):
    if p0_lon == p1_lon and p0_lat == p1_lat:
      return 0
    (r0_lon, r0_lat, r1_lon, r1_lat) = map(radians, [p0_lon, p0_lat, p1_lon, p1_lat])
    delta_x = r1_lon-r0_lon
    cos_d = \
      sin(r0_lat)*sin(r1_lat) \
      + cos(r0_lat) * cos(r1_lat) * cos(delta_x)
    try:
      res = 1000*acos(cos_d)*self.GEO_R1
      return res
    except:
      traceback.print_exc()
      print("cos_d =", cos_d)
      print("paramater:", p0_lon, p0_lat, p1_lon, p1_lat)
      return 0
  
  #return [m]
  def get_dist_on_earth_hubeny(self, p0_lon, p0_lat, p1_lon, p1_lat):
    if p0_lon == p1_lon and p0_lat == p1_lat:
      return 0
    (r0_lon, r0_lat, r1_lon, r1_lat) = map(radians, [p0_lon, p0_lat, p1_lon, p1_lat])
    lat_t = (r0_lat + r1_lat) / 2
    w = 1 - self.GEO_E2 * sin(lat_t) ** 2
    c2 = cos(lat_t) ** 2
    return sqrt((self.GEO_R2_2 / w ** 3) * (r0_lat - r1_lat) ** 2 + (self.GEO_R1_2 / w) * c2 * (r0_lon - r1_lon) ** 2)

  def calc_azimuth(self, lat, lon):
    rad_latitude = np.radians(lat)
    rad_longitude = np.radians(lon)
    rad_longitude_delta = rad_longitude[1:] - rad_longitude[0:-1]
    azimuth = np.mod(np.degrees(np.arctan2(
      np.sin(rad_longitude_delta), 
      np.cos(rad_latitude[0:-1])*np.tan(rad_latitude[1:])-np.sin(rad_latitude[0:-1])*np.cos(rad_longitude_delta)
      )), 360).astype(dtype='int16')
    return azimuth

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
