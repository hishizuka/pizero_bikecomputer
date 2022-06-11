import os
import sqlite3
import signal
import datetime
import shutil
import time
import threading
import queue
import traceback

import numpy as np
from crdp import rdp

from . import sensor_core
from .logger import loader_tcx
from .logger import logger_csv
from .logger import logger_fit

#ambient
# online uploading service in Japan
# https://ambidata.io
#_IMPORT_AMBIENT = False
#try:
#  #disable
#  #import ambient
#  #_IMPORT_AMBIENT = True
#  pass
#except:
#  pass


class LoggerCore():
  
  config = None
  sensor = None

  #for db
  con = None
  cur = None
  lock = None
  event = None

  #for timer
  values = {
    "count": 0,
    "count_lap": 0,
    "lap": 0,
    "elapsed_time": 0, #[s]
    "start_time": None, 
    "gross_ave_spd": 0, #[km/h]
    "gross_diff_time": "00:00", #"+-hh:mm" (string)
  }
  record_stats = {
    "pre_lap_avg":{},
    "lap_avg":{},
    "entire_avg":{},
    "pre_lap_max":{},
    "lap_max":{},
    "entire_max":{}
  }
  lap_keys = [
    "heart_rate",
    "cadence",
    "distance",
    "speed",
    "power",
    "accumulated_power",
    "total_ascent",
    "total_descent",
  ]
  #for power and cadence (including / not including zero)
  average = {
    "lap":{
      "cadence":{"count":0,"sum":0},
      "power":{"count":0,"sum":0}},
    "entire":{
      "cadence":{"count":0,"sum":0},
      "power":{"count":0,"sum":0}}
  }

  #for update_track
  pre_lat = None
  pre_lon = None
  
  #for store_short_log_for_update_track
  short_log_dist = []
  short_log_lat = []
  short_log_lon = []
  short_log_timestamp = []
  short_log_limit = 120
  short_log_available = True
  short_log_lock = False

  #send online
  send_time = None
  send_online_interval_sec = 30
  am = None

  #for debug
  position_log = np.array([])

  def __init__(self, config):
    print("\tlogger_core : init...")
    super().__init__()
    self.config = config
    self.sensor = sensor_core.SensorCore(self.config)
    self.course = loader_tcx.LoaderTcx(self.config, self.sensor)
    self.logger_csv = logger_csv.LoggerCsv(self.config)
    self.logger_fit = logger_fit.LoggerFit(self.config)

    #if _IMPORT_AMBIENT:
    #  t = datetime.datetime.utcnow()
    #  self.am = ambient.Ambient()
    #  self.send_time = datetime.datetime.now()
    #  print("\tlogger_core : setup ambient...: done", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    
    t = datetime.datetime.utcnow()
    print("\tlogger_core : loading course...")
    self.course.load()
    print("\tlogger_core : loading course...: done", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    
    for k in self.lap_keys:
      self.record_stats['pre_lap_avg'][k] = 0
      self.record_stats['lap_avg'][k] = 0
      self.record_stats['entire_avg'][k] = 0
      self.record_stats['pre_lap_max'][k] = 0
      self.record_stats['lap_max'][k] = 0
      self.record_stats['entire_max'][k] = 0

    #sqlite3 
    #usage of sqlite3 is "insert" only, so check_same_thread=False
    self.con = sqlite3.connect(self.config.G_LOG_DB, check_same_thread=False)
    self.cur = self.con.cursor()
    self.init_db()
    self.cur.execute("SELECT timestamp FROM BIKECOMPUTER_LOG LIMIT 1")
    first_row = self.cur.fetchone()
    if first_row == None:
      self.reset() 
    else:
      self.resume()
      #resume START/STOP status if temporary values exist
      self.config.G_MANUAL_STATUS = \
        self.config.get_config_pickle("G_MANUAL_STATUS", self.config.G_MANUAL_STATUS)
      if self.config.G_MANUAL_STATUS == "START":
        self.config.G_MANUAL_STATUS = "STOP"
      else:
        self.config.G_MANUAL_STATUS = "START"
      self.start_and_stop_manual()
    
    #thread for downloading map tiles
    self.sql_queue = queue.Queue()
    self.sql_thread = threading.Thread(target=self.sql_worker, name="sql_worker", args=())
    self.sql_thread.start()

    self.is_handler_on = False
    try:
      signal.signal(signal.SIGALRM, self.count_up)
      signal.setitimer(signal.ITIMER_REAL, self.config.G_LOGGING_INTERVAL, self.config.G_LOGGING_INTERVAL)
    except:
      #for windows
      traceback.print_exc()
      #pass

  def quit(self):
    self.sql_queue.put(None)
    self.cur.close()
    self.con.close()
  
  def sql_worker(self):
    for sql in iter(self.sql_queue.get, None):
      self.cur.execute(*sql)
      self.con.commit()

  def init_db(self):
    self.cur.execute("SELECT * FROM sqlite_master WHERE type='table' and name='BIKECOMPUTER_LOG'")
    if self.cur.fetchone() == None:
      self.con.execute("""CREATE TABLE BIKECOMPUTER_LOG(
        timestamp DATETIME,
        lap INTEGER, 
        timer INTEGER,
        total_timer_time INTEGER,
        position_lat FLOAT,
        position_long FLOAT,
        gps_altitude FLOAT,
        gps_speed FLOAT,
        gps_distance FLOAT,
        gps_mode INTEGER,
        gps_used_sats INTEGER,
        gps_total_sats INTEGER,
        gps_track INTEGER,
        gps_epx FLOAT,
        gps_epy FLOAT,
        gps_epv FLOAT,
        gps_pdop FLOAT,
        gps_hdop FLOAT,
        gps_vdop FLOAT,
        heart_rate INTEGER,
        cadence INTEGER,
        distance FLOAT,
        speed FLOAT,
        power INTEGER,
        accumulated_power INTEGER,
        temperature FLOAT,
        pressure FLOAT,
        humidity INTEGER,
        altitude FLOAT,
        course_altitude FLOAT,
        dem_altitude FLOAT,
        heading INTEGER,
        motion INTEGER,
        acc_x FLOAT,
        acc_y FLOAT,
        acc_z FLOAT,
        gyro_x FLOAT,
        gyro_y FLOAT,
        gyro_z FLOAT,
        light INTEGER,
        cpu_percent INTEGER,
        total_ascent FLOAT,
        total_descent FLOAT,
        lap_heart_rate INTEGER,
        lap_cadence INTEGER,
        lap_distance FLOAT,
        lap_speed FLOAT,
        lap_power INTEGER,
        lap_accumulated_power INTEGER,
        lap_total_ascent FLOAT,
        lap_total_descent FLOAT,
        avg_heart_rate INTEGER,
        avg_cadence INTEGER,
        avg_speed FLOAT,
        avg_power INTEGER,
        lap_cad_count INTEGER,
        lap_cad_sum INTEGER,
        avg_cad_count INTEGER,
        avg_cad_sum INTEGER,
        lap_power_count INTEGER,
        lap_power_sum INTEGER,
        avg_power_count INTEGER,
        avg_power_sum INTEGER
      )""")
      self.cur.execute("CREATE INDEX lap_index ON BIKECOMPUTER_LOG(lap)")
      self.cur.execute("CREATE INDEX total_timer_time_index ON BIKECOMPUTER_LOG(total_timer_time)")
      self.cur.execute("CREATE INDEX timestamp_index ON BIKECOMPUTER_LOG(timestamp)")
      self.con.commit()
      
  def count_up(self, arg1, arg2):  
    self.calc_gross()
    if self.config.G_STOPWATCH_STATUS != "START" or self.is_handler_on:
      return
    self.is_handler_on = True
    self.values['count'] += 1
    self.values['count_lap'] += 1
    self.record_log()
    self.is_handler_on = False

  def start_and_stop_manual(self):
    self.sensor.sensor_spi.screen_flash_short()
    if self.config.G_MANUAL_STATUS != "START":
      print("->M START\t", datetime.datetime.now())
      self.start_and_stop("STOP")
      self.config.G_MANUAL_STATUS = "START"
      if self.config.gui != None:
        self.config.gui.change_start_stop_button(self.config.G_MANUAL_STATUS)
      if self.values['start_time'] == None:
        self.values['start_time'] = int(datetime.datetime.utcnow().timestamp())
    elif self.config.G_MANUAL_STATUS == "START":
      print("->M STOP\t", datetime.datetime.now())
      self.start_and_stop("START")
      self.config.G_MANUAL_STATUS = "STOP"
      if self.config.gui != None:
        self.config.gui.change_start_stop_button(self.config.G_MANUAL_STATUS)
    self.config.set_config_pickle("G_MANUAL_STATUS", self.config.G_MANUAL_STATUS, quick_apply=True)
 
  def start_and_stop(self, status=None):
    if status != None:
      self.config.G_STOPWATCH_STATUS = status
    if self.config.G_STOPWATCH_STATUS != "START":
      self.config.G_STOPWATCH_STATUS = "START"
      print("->START\t", datetime.datetime.now())
    elif self.config.G_STOPWATCH_STATUS == "START":
      self.config.G_STOPWATCH_STATUS = "STOP"
      print("->STOP\t", datetime.datetime.now())
  
  def count_laps(self):
    if self.values['count'] == 0: return
    self.sensor.sensor_spi.screen_flash_short()
    self.values['lap'] += 1
    self.values['count_lap'] = 0
    for k in self.lap_keys:
      self.record_stats['pre_lap_avg'][k] = self.record_stats['lap_avg'][k]
      self.record_stats['pre_lap_max'][k] = self.record_stats['lap_max'][k]
      self.record_stats['lap_max'][k] = 0
      self.record_stats['lap_avg'][k] = 0
    for k2 in ["cadence","power"]:
      self.average["lap"][k2]["count"] = 0
      self.average["lap"][k2]["sum"] = 0
    self.record_log()
    print("->LAP:", self.values['lap'], "\t", datetime.datetime.now())

  def reset_count(self):
    if self.config.G_MANUAL_STATUS == "START" or self.values['count'] == 0:
      return
      
    #reset
    self.sensor.sensor_spi.screen_flash_long()

    #close db connect
    self.cur.close()
    self.con.close()

    if self.config.G_LOG_WRITE_CSV:
      t = datetime.datetime.now()
      if not self.logger_csv.write_log():
        return
      print("Write csv :", (datetime.datetime.now()-t).total_seconds(),"sec")
    if self.config.G_LOG_WRITE_FIT:
      t = datetime.datetime.now()
      if not self.logger_fit.write_log():
        return
      print("Write Fit({}) : {} sec".format(logger_fit.MODE,(datetime.datetime.now()-t).total_seconds()))
    
    # backup and reset database
    t = datetime.datetime.now()
    shutil.move(self.config.G_LOG_DB, self.config.G_LOG_DB+"-"+self.config.G_LOG_START_DATE)
    
    self.reset()

    #restart db connect
    #usage of sqlite3 is "insert" only, so check_same_thread=False
    self.con = sqlite3.connect(self.config.G_LOG_DB, check_same_thread=False)
    self.cur = self.con.cursor()
    self.init_db()
    print("DELETE :", (datetime.datetime.now()-t).total_seconds(),"sec")

    #reset temporary values
    self.config.reset_config_pickle()
    
    #reset accumulated values
    self.sensor.reset()

  def reset(self):
    #clear lap
    self.values['count'] = 0
    self.values['count_lap'] = 0
    self.values['lap'] = 0
    self.values['elapsed_time'] = 0
    self.values['start_time'] = None
    self.values['gross_ave_spd'] = 0
    self.values['gross_diff_time'] = "00:00"

    for k in self.lap_keys:
      self.record_stats['pre_lap_avg'][k] = 0
      self.record_stats['lap_avg'][k] = 0
      self.record_stats['entire_avg'][k] = 0
      self.record_stats['pre_lap_max'][k] = 0
      self.record_stats['lap_max'][k] = 0
      self.record_stats['entire_max'][k] = 0
    for k1 in self.average.keys():
      for k2 in ["cadence","power"]:
        self.average[k1][k2]["count"] = 0
        self.average[k1][k2]["sum"] = 0

  def record_log(self):
    #need to detect location delta for smart recording
    
    #get present value
    value = {
      "heart_rate":self.sensor.values['integrated']['hr'],
      "cadence":self.sensor.values['integrated']['cadence'],
      "distance":self.sensor.values['integrated']['distance'],
      "speed":self.sensor.values['integrated']['speed'],
      "power":self.sensor.values['integrated']['power'],
      "accumulated_power":self.sensor.values['integrated']['accumulated_power'],
      "total_ascent":self.sensor.values['I2C']['total_ascent'],
      "total_descent":self.sensor.values['I2C']['total_descent'],
      "dem_altitude":self.sensor.values['integrated']['dem_altitude'],
      "cpu_percent":self.sensor.values['integrated']['cpu_percent'],
    }
     
    #update lap stats if value is not Null
    for k,v in value.items():
      #skip when null value(np.nan)
      if v in [self.config.G_GPS_NULLVALUE, self.config.G_ANT_NULLVALUE]:
        continue
      #get average
      if k in ['heart_rate', 'cadence', 'speed', 'power']:
        x1 = t1 = 0 #for lap_avg = x1 / t1
        x2 = t2 = 0 #for entire_ave = x2 / t2

        #heart_rate : hr_sum / t
        #speed : distance / t
        #power : power_sum / t (exclude/include zero)
        #cadence : cad_sum / t (exclude/include zero)
        if k in ['heart_rate']:
          x1 = self.record_stats['lap_avg'][k] * (self.values['count_lap'] - 1) + v
          t1 = self.values['count_lap']
          x2 = self.record_stats['entire_avg'][k] * (self.values['count'] - 1) + v
          t2 = self.values['count']
        elif k in ['speed']:
          x1 = self.record_stats['lap_avg']['distance'] #[m]
          t1 = self.values['count_lap'] #[s]
          x2 = value['distance'] #[m]
          t2 = self.values['count'] #[s]
        #average including/excluding zero (cadence, power)
        elif k in ['cadence', 'power']:
          if v == 0 and not self.config.G_AVERAGE_INCLUDING_ZERO[k]:
            continue
          for l_e in ['lap','entire']:
            self.average[l_e][k]['sum'] += v
            self.average[l_e][k]['count'] += 1
          x1 = self.average['lap'][k]['sum']
          t1 = self.average['lap'][k]['count']
          x2 = self.average['entire'][k]['sum']
          t2 = self.average['entire'][k]['count']
        #update lap average
        if t1 > 0:
          self.record_stats['lap_avg'][k] = x1 / t1
        if t2 > 0:
          self.record_stats['entire_avg'][k] = x2 / t2
      #get lap distance, accumulated_power, total_ascent, total_descent
      elif k in ['distance', 'accumulated_power', 'total_ascent', 'total_descent']:
        # v is valid value
        x1 = self.record_stats['pre_lap_max'][k]
        if np.isnan(x1): x1 = 0
        self.record_stats['lap_avg'][k]  = v - x1
      
      #update max
      if k in ['heart_rate', 'cadence', 'speed', 'power']:
        if self.record_stats['lap_max'][k] < v:
          self.record_stats['lap_max'][k] = v
        if self.record_stats['entire_max'][k] < v:
          self.record_stats['entire_max'][k] = v
      elif k in ['distance', 'accumulated_power', 'total_ascent', 'total_descent']:
        self.record_stats['lap_max'][k] = v
   
    ## SQLite
    now_time = datetime.datetime.utcnow()
    #self.cur.execute("""\
    sql = ("""\
      INSERT INTO BIKECOMPUTER_LOG VALUES(\
        ?,?,?,?,\
        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,\
        ?,?,?,?,?,?,\
        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,\
        ?,?,?,?,?,?,?,?,\
        ?,?,?,?,\
        ?,?,?,?,?,?,?,?\
      )""",
      (
      now_time,
      self.values['lap'],
      self.values['count_lap'],
      self.values['count'],
      ###
      self.sensor.values['GPS']['lat'],
      self.sensor.values['GPS']['lon'],
      self.sensor.values['GPS']['alt'],
      self.sensor.values['GPS']['speed'],
      self.sensor.values['GPS']['distance'],
      self.sensor.values['GPS']['mode'],
      self.sensor.values['GPS']['used_sats'],
      self.sensor.values['GPS']['total_sats'],
      self.sensor.values['GPS']['track'],
      self.sensor.values['GPS']['epx'],
      self.sensor.values['GPS']['epy'],
      self.sensor.values['GPS']['epv'],
      self.sensor.values['GPS']['pdop'],
      self.sensor.values['GPS']['hdop'],
      self.sensor.values['GPS']['vdop'],
      ###
      value['heart_rate'],
      value['cadence'],
      value['distance'],
      value['speed'],
      value['power'],
      value['accumulated_power'],
      ###
      self.sensor.values['I2C']['temperature'],
      self.sensor.values['I2C']['pressure'],
      self.sensor.values['I2C']['humidity'], #
      self.sensor.values['I2C']['altitude'],
      self.sensor.values['GPS']['course_altitude'],
      value['dem_altitude'],
      self.sensor.values['I2C']['heading'],
      self.sensor.values['I2C']['m_stat'],
      #self.sensor.values['I2C']['acc'][0],
      #self.sensor.values['I2C']['acc'][1],
      #self.sensor.values['I2C']['acc'][2],
      self.sensor.values['I2C']['acc_graph'][0],
      self.sensor.values['I2C']['acc_graph'][1],
      self.sensor.values['I2C']['acc_graph'][2],
      self.sensor.values['I2C']['gyro_mod'][0],
      self.sensor.values['I2C']['gyro_mod'][1],
      self.sensor.values['I2C']['gyro_mod'][2],
      self.sensor.values['I2C']['light'],
      value['cpu_percent'],
      value['total_ascent'],
      value['total_descent'],
      ###
      self.record_stats['lap_avg']['heart_rate'],
      self.record_stats['lap_avg']['cadence'],
      self.record_stats['lap_avg']['distance'],
      self.record_stats['lap_avg']['speed'],
      self.record_stats['lap_avg']['power'],
      self.record_stats['lap_avg']['accumulated_power'],
      self.record_stats['lap_avg']['total_ascent'],
      self.record_stats['lap_avg']['total_descent'],
      ###
      self.record_stats['entire_avg']['heart_rate'],
      self.record_stats['entire_avg']['cadence'],
      self.record_stats['entire_avg']['speed'],
      self.record_stats['entire_avg']['power'],
      ###
      self.average['lap']['cadence']['count'],
      self.average['lap']['cadence']['sum'],
      self.average['entire']['cadence']['count'],
      self.average['entire']['cadence']['sum'],
      self.average['lap']['power']['count'],
      self.average['lap']['power']['sum'],
      self.average['entire']['power']['count'],
      self.average['entire']['power']['sum']
      )
    )
    #self.con.commit()
    self.sql_queue.put((sql))

    self.store_short_log_for_update_track(
      value['distance'],
      self.sensor.values['GPS']['lat'],
      self.sensor.values['GPS']['lon'],
      now_time,
      )

    #send online
    #self.send_ambient()

  def calc_gross(self):
    #elapsed_time
    if self.values['start_time'] == None:
      return
    #[s]
    self.values['elapsed_time'] = int(datetime.datetime.utcnow().timestamp() - self.values['start_time'])

    #gross_ave_spd
    if self.values['elapsed_time'] == 0:
      return
    #[m]/[s]
    self.values['gross_ave_spd'] = self.sensor.values['integrated']['distance']/self.values['elapsed_time']
    
    #gross_diff_time
    if self.config.G_GROSS_AVE_SPEED == 0:
      return
    #[km]/[km/h] = +-[h] -> +-[m]
    diff_time = \
      (self.sensor.values['integrated']['distance']/1000-self.config.G_GROSS_AVE_SPEED*self.values['elapsed_time']/3600) \
      / self.config.G_GROSS_AVE_SPEED * 60
    diff_h, diff_m = divmod(abs(diff_time), 60)
    diff_m = int(diff_m)
    diff_time_sign = "+"
    if np.sign(diff_time) < 0:
      diff_time_sign = "-"
    if diff_h == 0 and diff_m == 0:
      diff_time_sign = ""
    self.values['gross_diff_time'] = "{:}{:02.0f}:{:02.0f}".format(diff_time_sign, diff_h, diff_m)
    
    #print(self.values['elapsed_time'], self.values['gross_ave_spd'], self.values['gross_diff_time'], round(diff_time,1))

  def resume(self):
    self.cur.execute("SELECT count(*) FROM BIKECOMPUTER_LOG")
    res = self.cur.fetchone()
    if res[0] == 0:
      return
    
    print("resume existing rides...")
    row_all = "\
      lap,timer,total_timer_time,\
      distance,accumulated_power,total_ascent,total_descent,altitude,\
      position_lat, position_long, \
      lap_heart_rate,lap_cadence,lap_distance,lap_speed,lap_power,\
      lap_accumulated_power,lap_total_ascent,lap_total_descent,\
      avg_heart_rate,avg_cadence,avg_speed,avg_power,\
      lap_cad_count,lap_cad_sum,lap_power_count,lap_power_sum,\
      avg_cad_count,avg_cad_sum,avg_power_count,avg_power_sum"
    self.cur.execute("\
      SELECT %s FROM BIKECOMPUTER_LOG\
      WHERE total_timer_time = (SELECT MAX(total_timer_time) FROM BIKECOMPUTER_LOG) \
      AND lap = (SELECT MAX(lap) FROM BIKECOMPUTER_LOG)" \
      % (row_all))
    value = list(self.cur.fetchone())
    (self.values['lap'], self.values['count_lap'], self.values['count']) = value[0:3]

    sn = self.sensor.values['integrated']
    i2c = self.sensor.values['I2C']
    gps = self.sensor.values['GPS']
    sn['distance'] += value[3]
    sn['accumulated_power'] += value[4]
    i2c['total_ascent'] += value[5]
    i2c['total_descent'] += value[6]
    #None -> np.nan
    (i2c['pre_altitude'],gps['pre_lat'],gps['pre_lon']) = np.array(value[7:10], dtype=np.float)

    index = 10
    for k in self.lap_keys:
      self.record_stats['lap_avg'][k] = value[index]
      index += 1
    for k in ['heart_rate', 'cadence', 'speed', 'power']:
      self.record_stats['entire_avg'][k] = value[index]
      index += 1
    for k1 in ['lap','entire']:
      for k2 in ['cadence','power']:
        for k3 in ['count','sum']:
          self.average[k1][k2][k3] = value[index]
          index += 1
    #print(self.average)
    
    #get lap
    self.cur.execute("SELECT MAX(LAP) FROM BIKECOMPUTER_LOG")
    max_lap = (self.cur.fetchone())[0]
    
    #get max
    max_row = "MAX(heart_rate), MAX(cadence), MAX(speed), MAX(power)"
    main_item = ['heart_rate', 'cadence', 'speed', 'power']
    self.cur.execute("SELECT %s FROM BIKECOMPUTER_LOG" % (max_row))
    max_value = list(self.cur.fetchone())
    for i,k in enumerate(main_item):
      self.record_stats['entire_max'][k] = 0
      if max_value[i] != None:
        self.record_stats['entire_max'][k] = max_value[i]
    
    #get lap max
    self.cur.execute("SELECT %s FROM BIKECOMPUTER_LOG WHERE LAP = %s" % (max_row,max_lap))
    max_value = list(self.cur.fetchone())
    for i,k in enumerate(main_item):
      self.record_stats['lap_max'][k] = 0
      if max_value[i] != None:
        self.record_stats['lap_max'][k] = max_value[i]
    
    #get pre lap
    if max_lap >= 1:
      self.cur.execute("\
        SELECT %s FROM BIKECOMPUTER_LOG\
        WHERE LAP = %s AND total_timer_time = (\
          SELECT MAX(total_timer_time) FROM BIKECOMPUTER_LOG\
          WHERE LAP = %s)" \
        % (row_all,max_lap-1,max_lap-1))
      value = list(self.cur.fetchone())
      
      index = 3
      for k in ['distance', 'accumulated_power', 'total_ascent', 'total_descent']:
        self.record_stats['pre_lap_max'][k] = value[index]
        index +=1
      for k in self.lap_keys:
        self.record_stats['pre_lap_avg'][k] = value[index]
        index += 1
      
      #max
      self.cur.execute("SELECT %s FROM BIKECOMPUTER_LOG WHERE LAP = %s" % (max_row,max_lap-1))
      max_value = list(self.cur.fetchone())
      for i,k in enumerate(main_item):
        self.record_stats['pre_lap_max'][k] = max_value[i]
    #print(self.record_stats)
    #print(self.average)

    #start_time
    self.cur.execute("SELECT MIN(timestamp) FROM BIKECOMPUTER_LOG")
    first_row = self.cur.fetchone()
    if first_row[0] != None:
      self.values['start_time'] = int(self.config.datetime_myparser(first_row[0]).timestamp()-1)

    #if not self.config.G_IS_RASPI and self.config.G_DUMMY_OUTPUT:
    if self.config.G_DUMMY_OUTPUT:
      self.cur.execute("SELECT position_lat,position_long,distance,gps_track FROM BIKECOMPUTER_LOG")
      self.position_log = np.array(self.cur.fetchall())

  def store_short_log_for_update_track(self, dist, lat, lon, timestamp):
    if not self.short_log_available:
      return
    if lat == self.config.G_GPS_NULLVALUE or lon == self.config.G_GPS_NULLVALUE:
      return
    if len(self.short_log_dist) > 0 and self.short_log_dist[-1] == dist:
      return
    if (len(self.short_log_lat) > 0 and self.short_log_lat[-1] == lat) and \
       (len(self.short_log_lon) > 0 and self.short_log_lon[-1] == lon):
      return
    if len(self.short_log_lat) > self.short_log_limit:
      self.clear_short_log()
      self.short_log_available = False
      return
  
    self.short_log_lock = True
    self.short_log_dist.append(dist)
    self.short_log_lat.append(lat)
    self.short_log_lon.append(lon)
    self.short_log_timestamp.append(timestamp)
    self.short_log_lock = False
    self.short_log_available = True
    #print("append", len(self.short_log_dist), len(self.short_log_lat), len(self.short_log_lon))
  
  def clear_short_log(self):
    while self.short_log_lock:
      print("locked: clear_short_log")
      time.sleep(0.02)
    self.short_log_dist = []
    self.short_log_lat = []
    self.short_log_lon = []
    self.short_log_timestamp = []

  def update_track(self, timestamp):
    lon = np.array([])
    lat = np.array([])
    timestamp_new = timestamp
    #t = datetime.datetime.utcnow()
    
    timestamp_delta = None
    if timestamp != None:
      timestamp_delta = \
        (datetime.datetime.utcnow() - timestamp).total_seconds()
    
    #make_tmp_db = False
    lat_raw = np.array([])
    lon_raw = np.array([])
    dist_raw = np.array([])
    
    #get values from short_log to db in logging
    if timestamp_delta != None and self.short_log_available:
      while self.short_log_lock:
        print("locked: get values")
        time.sleep(0.02)
      lat_raw = np.array(self.short_log_lat)
      lon_raw = np.array(self.short_log_lon)
      dist_raw = np.array(self.short_log_dist)
      if len(self.short_log_lon) > 0:
        timestamp_new = self.short_log_timestamp[-1]
      self.clear_short_log()
      self.short_log_available = True
    #get values from copied db when initial execution or migration from short_log to db in logging
    else:
      db_file = self.config.G_LOG_DB+".tmp"
      shutil.copy(self.config.G_LOG_DB, db_file)

      query = \
        "SELECT distance,position_lat,position_long FROM BIKECOMPUTER_LOG " + \
        "WHERE position_lat is not null AND position_long is not null "
      if timestamp != None:
        query = query + "AND timestamp > '%s'" % timestamp

      con = sqlite3.connect(db_file)
      cur = con.cursor()
      cur.execute(query)
      res_array = np.array(cur.fetchall())
      if(len(res_array.shape) > 0 and res_array.shape[0] > 0):
        dist_raw = res_array[:,0].astype('float32') #[m]
        lat_raw = res_array[:,1].astype('float32')
        lon_raw = res_array[:,2].astype('float32')
      
      #timestamp
      cur.execute("SELECT MAX(timestamp) FROM BIKECOMPUTER_LOG")
      first_row = cur.fetchone()
      if first_row[0] != None:
        timestamp_new = self.config.datetime_myparser(first_row[0])
      
      cur.close()
      con.close()
      os.remove(db_file)
      self.short_log_available = True

    #print("lat_raw", len(lat_raw))
    if len(lat_raw) > 0 and (len(lat_raw) == len(lon_raw) == len(dist_raw)):
      #downsampling
      try:
        cond = np.array(rdp(np.column_stack([lon_raw, lat_raw]), epsilon=0.0001, return_mask=True))
        lat = lat_raw[cond]
        lon = lon_raw[cond]
      except:
        lat = lat_raw
        lon = lon_raw

    if timestamp is None:
      timestamp_new = datetime.datetime.utcnow()
    
    #print("\tlogger_core : update_track(new) ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")

    return timestamp_new, lon, lat

  #def send_ambient(self):
  #  if not _IMPORT_AMBIENT or self.config.G_MANUAL_STATUS != "START":
  #    return
  #  t = datetime.datetime.now()
  #  if (t - self.send_time).total_seconds() < self.send_online_interval_sec:
  #    return
  #  self.send_time = t
  #  try:
  #    d = {
  #      'd1': self.sensor.values['integrated']['speed'] * 3.6,
  #      'd2': self.sensor.values['integrated']['hr'], 
  #      'd3': self.sensor.values['integrated']['cadence'],
  #      'd4': self.sensor.values['integrated']['power'],
  #      'd5': self.sensor.values['I2C']['altitude'],
  #      'd6': self.sensor.values['integrated']['distance']/1000,
  #      'd7': self.sensor.values['integrated']['accumulated_power']/1000,
  #      'd8': self.sensor.values['I2C']['temperature'],
  #      'lat':self.sensor.values['GPS']['lat'], 
  #      'lng':self.sensor.values['GPS']['lon']
  #      }
  #    d_send = {}
  #    for k,v in d.items():
  #      if not np.isnan(v):
  #        d_send[k] = v
  #    r = self.am.send(d_send)
  #    print(r,d_send)
  #  #except requests.exceptions.RequestException as e:
  #  #  print('request failed: ', e)
  #  except:
  #    pass
