import sys
import argparse
import os
import struct
import subprocess
import configparser
import traceback
import json
import datetime
from math import sin, cos, acos, radians

import numpy as np

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

  #Language defined by G_LANG in gui_config.py
  G_LANG = "EN"

  #loop interval
  G_SENSOR_INTERVAL = 1.0 #[s] for sensor_core, GPS
  G_ANT_INTERVAL = None #for ANT+
  G_I2C_INTERVAL = 0.2 #[s] for I2C (altitude, accelerometer, etc)
  G_DRAW_INTERVAL = 1000 #[ms] for GUI
  G_LOGGING_INTERVAL = 1000 #[ms] for logger_core (log interval)
  G_REALTIME_GRAPH_INTERVAL = 200 #[ms] for pyqt_graph
  
  #log format switch
  G_LOG_WRITE_CSV = False
  G_LOG_WRITE_FIT = True
  G_LOG_WRITE_TCX = False

  #average including ZERO when logging
  G_AVERAGE_INCLUDING_ZERO = {
    "cadence":False,
    "power":True
  }

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
  
  #screenshot dir
  G_SCREENSHOT_DIR = 'screenshot/'
  
  #layout def
  G_LAYOUT_FILE = "layout.yaml"
  
  #log setting
  G_LOG_DIR = "log/"
  G_LOG_DB = G_LOG_DIR + "log.db"
  G_LOG_START_DATE = None

  #config file (use in config only)
  config_file = "setting.conf"
  config_parser = None

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
    'INTERVAL':2, #ANT+ interval: 0:4Hz(0.25s), 1:2Hz(0.5s), 2:1Hz(1.0s)
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
    'DFRobot_RPi_Display': {'size':(250, 122),'touch':False}
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
  G_GPS_ON_ROUTE_CUTOFF = 0 #[m] #generate from course
  G_GPS_SEARCH_RANGE = 0.1 #[km] #100km/h -> 27.7m/s

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
    
    #set dir(for using from pitft desktop)
    if self.G_IS_RASPI:
      self.G_SCREENSHOT_DIR = self.G_INSTALL_PATH + self.G_SCREENSHOT_DIR 
      self.G_LOG_DIR = self.G_INSTALL_PATH + self.G_LOG_DIR
      self.G_LOG_DB = self.G_INSTALL_PATH + self.G_LOG_DB
      self.config_file = self.G_INSTALL_PATH + self.config_file
      self.G_LAYOUT_FILE = self.G_INSTALL_PATH + self.G_LAYOUT_FILE
      
    #object for setting.conf
    self.config_parser = configparser.ConfigParser()
    if os.path.exists(self.config_file):
      self.read_config()

    #mkdir
    if not os.path.exists(self.G_SCREENSHOT_DIR):
      os.mkdir(self.G_SCREENSHOT_DIR)
    if not os.path.exists(self.G_LOG_DIR):
      os.mkdir(self.G_LOG_DIR)

    #get serial number
    self.get_serial()
    
    self.detect_display()
    self.set_resolution()

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

  def exec_cmd(self, cmd):
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

  def exec_cmd_return_value(self, cmd):
    string = ""
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
  
  def quit(self):
    print("quit")
    self.G_QUIT = True
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
    curl_status = self.exec_cmd_return_value(["which", "curl"])
    if curl_status == "":
      print("curl does not exist")
      return

    #file check
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
    
    self.config_parser['STRAVA'] = {}
    for k in self.G_STRAVA.keys():
      self.config_parser['STRAVA'][k] = self.G_STRAVA[k] 

    self.config_parser['BT_ADDRESS'] = {}
    for k in self.G_BT_ADDRESS.keys():
      self.config_parser['BT_ADDRESS'][k] = self.G_BT_ADDRESS[k] 

    with open(self.config_file, 'w') as file:
      self.config_parser.write(file)

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

  def dist_on_earth(self, pos0_lon, pos0_lat, pos1_lon, pos1_lat):
    pos0_rad = [radians(pos0_lon), radians(pos0_lat)]
    pos1_rad = [radians(pos1_lon), radians(pos1_lat)]
    cos_d = \
      sin(pos0_rad[1])*sin(pos1_rad[1]) \
      + cos(pos0_rad[1]) * cos(pos1_rad[1]) * cos(pos0_rad[0] - pos1_rad[0])
    try:
      res = 1000*acos(cos_d)*6378.137
      return res
    except:
      traceback.print_exc()
      print("cos_d =", cos_d)
      print("paramater:", pos0_lon, pos0_lat, pos1_lon, pos1_lat)
      return 0
  