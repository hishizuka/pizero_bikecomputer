import os
import sqlite3
import datetime
import shutil
import xml.etree.ElementTree as ET

import numpy as np
import PyQt5.QtCore as QtCore

from . import sensor_core
from .logger import logger_csv
from .logger import logger_fit
from .logger import logger_tcx

#ambient
_IMPORT_AMBIENT = False
try:
  import ambient2
  _IMPORT_AMBIENT = True
except:
  pass


class LoggerCore(QtCore.QObject):
  
  config = None
  sensor = None
  
  #for loading course
  course_filename = None

  #for DB
  con = None
  cur = None
  
  #for timer
  signal_start = QtCore.pyqtSignal()
  signal_stop = QtCore.pyqtSignal()
  count = 0
  count_lap = 0
  lap = 0
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
  pre_lon = None
  pre_lat = None
 
  #for course (need to reset)
  course_info = {}
  course_distance = []
  course_altitude = []
  course_latitude = []
  course_longitude = []
  course_slope = []
  course_slope_smoothing = []
  lat_by_slope = []
  lon_by_slope = []
  colored_altitude = []

  #numpy
  np_course_distance = np.array([])
  np_course_altitude = np.array([])
  np_course_latitude = np.array([])
  np_course_longitude = np.array([])

  #for course points (need to reset)
  course_point_name = []
  course_point_latitude = []
  course_point_longitude = []
  course_point_point_type = []
  course_point_notes = []
  course_point_distance = []

  #send online
  send_time = None
  send_online_interval_sec = 30
  am = None

  def __init__(self, config):
    print("\tlogger_core : init...")
    super().__init__()
    self.config = config
    self.sensor = sensor_core.SensorCore(self.config)
    self.csv = logger_csv.LoggerCsv(self.config)
    self.fit = logger_fit.LoggerFit(self.config)
    self.tcx = logger_tcx.LoggerTcx(self.config)
    self.signal_start.connect(self.timer_start)
    self.signal_stop.connect(self.timer_stop)
    t = datetime.datetime.utcnow()
    if _IMPORT_AMBIENT:
      self.am = ambient.Ambient("8192", "2930b14626cec495","317fbd7966d4cacf")
      self.send_time = datetime.datetime.now()
    print("\tlogger_core : setup ambient...: done", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    #loading course -> move to config value and loading from screen
    self.course_filename = "course/course.tcx" 
    if self.config.G_IS_RASPI:
      self.course_filename = self.config.G_INSTALL_PATH + self.course_filename
    t = datetime.datetime.utcnow()
    print("\tlogger_core : loading course...")
    if os.path.exists(self.course_filename):
      self.load_course()
    print("\tlogger_core : loading course...: done", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    
    for k in self.lap_keys:
      self.record_stats['pre_lap_avg'][k] = 0
      self.record_stats['lap_avg'][k] = 0
      self.record_stats['entire_avg'][k] = 0
      self.record_stats['pre_lap_max'][k] = 0
      self.record_stats['lap_max'][k] = 0
      self.record_stats['entire_max'][k] = 0

    #sqlite3
    self.init_db()
    con = sqlite3.connect(self.config.G_LOG_DB)
    cur = con.cursor()    
    cur.execute("SELECT timestamp FROM BIKECOMPUTER_LOG LIMIT 1")
    first_row = cur.fetchone()
    if first_row == None:
      self.init_value() 
    else: self.resume(cur)
    cur.close()
    con.close()

    #StopWatch Loop in 1 seconds
    self.timer = QtCore.QTimer()
    self.timer.setInterval(self.config.G_LOGGING_INTERVAL)
    self.timer.timeout.connect(self.do_countup)

  def init_db(self):
    con = sqlite3.connect(self.config.G_LOG_DB)
    cur = con.cursor()
    cur.execute("SELECT * FROM sqlite_master WHERE type='table' and name='BIKECOMPUTER_LOG'")
    if cur.fetchone() == None:
      con.execute("""CREATE TABLE BIKECOMPUTER_LOG(
        timestamp DATETIME,
        lap INTEGER, 
        timer INTEGER,
        total_timer_time,
        position_lat FLOAT,
        position_long FLOAT,
        gps_altitude FLOAT,
        gps_distance FLOAT,
        gps_mode INTEGER,
        gps_used_sats INTEGER,
        gps_total_sats INTEGER,
        gps_track INTEGER,
        heart_rate INTEGER,
        cadence INTEGER,
        distance FLOAT,
        speed FLOAT,
        power INTEGER,
        accumulated_power INTEGER,
        temperature FLOAT,
        pressure FLOAT,
        altitude FLOAT,
        heading INTEGER,
        motion FLOAT,
        acc_x FLOAT,
        acc_y FLOAT,
        acc_z FLOAT,
        voltage_battery FLOAT,
        voltage_in FLOAT,
        current_in FLOAT,
        voltage_out FLOAT,
        current_out FLOAT,
        capacity_in FLOAT,
        capacity_out FLOAT,
        battery_percentage FLOAT,
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
      cur.execute("CREATE INDEX lap_index ON BIKECOMPUTER_LOG(lap)")
      cur.execute("CREATE INDEX total_timer_time_index ON BIKECOMPUTER_LOG(total_timer_time)")
      cur.execute("CREATE INDEX timestamp_index ON BIKECOMPUTER_LOG(timestamp)")
      con.commit()
    cur.close()
    con.close()
      
  def do_countup(self):
    self.count += 1
    self.count_lap += 1
    self.record_log()

  def start_and_stop_manual(self):
    self.sensor.sensor_spi.screen_flash_short()
    if self.config.G_MANUAL_STATUS != "START":
      self.start_and_stop("STOP")
      self.config.G_MANUAL_STATUS = "START"
      self.config.gui.change_start_stop_button(self.config.G_MANUAL_STATUS)
      print("->M START\t", datetime.datetime.now())
    elif self.config.G_MANUAL_STATUS == "START":
      #button
      self.start_and_stop("START")
      self.config.G_MANUAL_STATUS = "STOP"
      self.config.gui.change_start_stop_button(self.config.G_MANUAL_STATUS)
      print("->M STOP\t", datetime.datetime.now())
 
  def start_and_stop(self, status=None):
    if status != None:
      self.config.G_STOPWATCH_STATUS = status
    if self.config.G_STOPWATCH_STATUS != "START":
      #self.timer.start()
      self.signal_start.emit()
      self.config.G_STOPWATCH_STATUS = "START"
      print("->START\t", datetime.datetime.now())
    elif self.config.G_STOPWATCH_STATUS == "START":
      #self.timer.stop()
      self.signal_stop.emit()
      self.config.G_STOPWATCH_STATUS = "STOP"
      print("->STOP\t", datetime.datetime.now())
  
  def timer_start(self):
    self.timer.start()
  def timer_stop(self):
    self.timer.stop()

  def count_laps(self):
    if self.count == 0: return
    self.sensor.sensor_spi.screen_flash_short()
    self.lap += 1
    self.count_lap = 0
    for k in self.lap_keys:
      self.record_stats['pre_lap_avg'][k] = self.record_stats['lap_avg'][k]
      self.record_stats['pre_lap_max'][k] = self.record_stats['lap_max'][k]
      self.record_stats['lap_max'][k] = 0
      self.record_stats['lap_avg'][k] = 0
    for k2 in ["cadence","power"]:
      self.average["lap"][k2]["count"] = 0
      self.average["lap"][k2]["sum"] = 0
    self.record_log()

  def reset_count(self):
    if self.config.G_MANUAL_STATUS != "START" and self.count > 0:
      #start reset
      self.sensor.sensor_spi.screen_flash_long()
      if self.config.G_LOG_WRITE_CSV:
        t = datetime.datetime.now()
        if not self.csv.write_log():
          return
        print("Write csv :", (datetime.datetime.now()-t).total_seconds(),"sec")
      if self.config.G_LOG_WRITE_FIT:
        t = datetime.datetime.now()
        if not self.fit.write_log():
          return
        print("Write Fit :", (datetime.datetime.now()-t).total_seconds(),"sec")
      if self.config.G_LOG_WRITE_TCX:
        if not self.tcx.write_log():
          return
      t = datetime.datetime.now()
      self.init_value()
      ## backup and reset database
      shutil.move(self.config.G_LOG_DB, self.config.G_LOG_DB+"-"+self.config.G_LOG_START_DATE)
      self.init_db()
      print("DELETE :", (datetime.datetime.now()-t).total_seconds(),"sec")

  def init_value(self):
      #clear lap
      self.count = 0
      self.count_lap = 0
      self.lap = 0
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
      #reset accumulated values
      self.sensor.reset()

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
      "total_descent":self.sensor.values['I2C']['total_descent']
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
        if k in ['heart_rate', 'speed']:
          lap_avg = self.record_stats['lap_avg'][k]
          x1 = lap_avg * (self.count_lap - 1) + v
          t1 = self.count_lap
          avg = self.record_stats['entire_avg'][k]
          x2 = avg * (self.count - 1) + v
          t2 = self.count
        #average including/excluding zero (cadence, power)
        elif k in ['cadence', 'power']:
          if v == 0 and not self.config.G_AVERAGE_INCLUDING_ZERO[k]:
            continue
          for l_e in ['lap','entire']:
            self.average[l_e][k]['sum'] += v
            self.average[l_e][k]['count'] += 1
          x1 = self.average['lap'][k]['sum']
          x2 = self.average['entire'][k]['sum']
          t1 = self.average['lap'][k]['count']
          t2 = self.average['entire'][k]['count']
        #update lap average
        if t1 == 0: continue
        if t2 == 0: continue
        self.record_stats['lap_avg'][k] = x1 / t1
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
    con = sqlite3.connect(self.config.G_LOG_DB)
    cur = con.cursor()
    now_time = datetime.datetime.utcnow()
    cur.execute("""\
      INSERT INTO BIKECOMPUTER_LOG VALUES(\
        ?,?,?,?,\
        ?,?,?,?,?,?,?,?,\
        ?,?,?,?,?,?,\
        ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,\
        ?,?,?,?,?,?,?,?,\
        ?,?,?,?,\
        ?,?,?,?,?,?,?,?\
      )""",
      (now_time,
       self.lap,
       self.count_lap,
       self.count,
       ###
       self.sensor.values['GPS']['lat'],
       self.sensor.values['GPS']['lon'],
       self.sensor.values['GPS']['alt'],
       self.sensor.values['GPS']['distance'],
       self.sensor.values['GPS']['mode'],
       self.sensor.values['GPS']['used_sats'],
       self.sensor.values['GPS']['total_sats'],
       self.sensor.values['GPS']['track'],
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
       self.sensor.values['I2C']['altitude'],
       self.sensor.values['I2C']['heading'],
       self.sensor.values['I2C']['motion'],
       self.sensor.values['I2C']['acc'][0],
       self.sensor.values['I2C']['acc'][1],
       self.sensor.values['I2C']['acc'][2],
       self.sensor.values['I2C']['voltage_battery'],
       self.sensor.values['I2C']['voltage_in'],
       self.sensor.values['I2C']['current_in'],
       self.sensor.values['I2C']['voltage_out'],
       self.sensor.values['I2C']['current_out'],
       self.sensor.values['I2C']['capacity_in'],
       self.sensor.values['I2C']['capacity_out'],
       self.sensor.values['I2C']['battery_percentage'],
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
    con.commit()
    t2 = (datetime.datetime.utcnow() - now_time).total_seconds()
    if self.count % 1800 == 10:
      print("### DB insert ({}s) : {:.3f}s".format(self.count, t2))
    cur.close()
    con.close()

    #send online
    self.send_ambient()

  def resume(self, cur):
    cur.execute("SELECT count(*) FROM BIKECOMPUTER_LOG")
    v = cur.fetchone()
    if v[0] == 0: return
    
    print("resume existing rides...")
    row_all = "\
      lap,timer,total_timer_time,\
      distance,accumulated_power,total_ascent,total_descent,\
      lap_heart_rate,lap_cadence,lap_distance,lap_speed,lap_power,\
      lap_accumulated_power,lap_total_ascent,lap_total_descent,\
      avg_heart_rate,avg_cadence,avg_speed,avg_power,\
      lap_cad_count,lap_cad_sum,lap_power_count,lap_power_sum,\
      avg_cad_count,avg_cad_sum,avg_power_count,avg_power_sum"
    cur.execute("\
      SELECT %s FROM BIKECOMPUTER_LOG\
      WHERE total_timer_time = (SELECT MAX(total_timer_time) FROM BIKECOMPUTER_LOG)" \
      % (row_all))
    value = list(cur.fetchone())
    (self.lap, self.count_lap,self.count) = value[0:3]

    sn = self.sensor.values['integrated']
    i2c = self.sensor.values['I2C']
    (sn['distance'],sn['accumulated_power'],i2c['total_ascent'],i2c['total_descent']) = value[3:7]
    
    index = 7
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
    cur.execute("SELECT MAX(LAP) FROM BIKECOMPUTER_LOG")
    max_lap = (cur.fetchone())[0]
    #get max
    max_row = "MAX(heart_rate), MAX(cadence), MAX(speed), MAX(power)"
    main_item = ['heart_rate', 'cadence', 'speed', 'power']
    cur.execute("SELECT %s FROM BIKECOMPUTER_LOG" % (max_row))
    max_value = list(cur.fetchone())
    for i,k in enumerate(main_item):
      self.record_stats['entire_max'][k] = 0
      if max_value[i] != None:
        self.record_stats['entire_max'][k] = max_value[i]
    #get lap max
    cur.execute("SELECT %s FROM BIKECOMPUTER_LOG WHERE LAP = %s" % (max_row,max_lap))
    max_value = list(cur.fetchone())
    for i,k in enumerate(main_item):
      self.record_stats['lap_max'][k] = 0
      if max_value[i] != None:
        self.record_stats['lap_max'][k] = max_value[i]
    #get pre lap
    if max_lap >= 1:
      cur.execute("\
        SELECT %s FROM BIKECOMPUTER_LOG\
        WHERE LAP = %s AND total_timer_time = (\
          SELECT MAX(total_timer_time) FROM BIKECOMPUTER_LOG\
          WHERE LAP = %s)" \
        % (row_all,max_lap-1,max_lap-1))
      value = list(cur.fetchone())
      
      index = 3
      for k in ['distance', 'accumulated_power', 'total_ascent', 'total_descent']:
        self.record_stats['pre_lap_max'][k] = value[index]
        index +=1
      for k in self.lap_keys:
        self.record_stats['pre_lap_avg'][k] = value[index]
        index += 1
      
      #max
      cur.execute("SELECT %s FROM BIKECOMPUTER_LOG WHERE LAP = %s" % (max_row,max_lap-1))
      max_value = list(cur.fetchone())
      for i,k in enumerate(main_item):
        self.record_stats['pre_lap_max'][k] = max_value[i]
    #print(self.record_stats)
    #print(self.average)
 
  def update_track(self, timestamp):
    #if self.config.G_STOPWATCH_STATUS != "START": return
    con = sqlite3.connect(self.config.G_LOG_DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    lon = []
    lat = []
    timestamp_new = timestamp
    select_base = " \
      SELECT timestamp,position_lat,position_long \
        FROM BIKECOMPUTER_LOG \
        WHERE position_lat is not null AND position_long is not null \
        "
    
    #t = datetime.datetime.utcnow()

    if timestamp is None:
      cur.execute(select_base)
    else:
      cur.execute(select_base + "AND timestamp > '%s'" % timestamp)

    for row in cur:
      if row[1] != None and row[2] != None:
        #for first data(accepted)
        if self.pre_lat == None and self.pre_lon == None:
          lon.append(row[2])
          lat.append(row[1])
          self.pre_lat = row[1]
          self.pre_lon = row[2]
          continue

        #skip if same position
        if row[1] == self.pre_lat and row[2] == self.pre_lon:
          continue
        #for rest data
        dist = self.config.dist_on_earth(row[2], row[1], self.pre_lon, self.pre_lat)
        if dist >= self.config.G_GPS_DISPLAY_INTERVAL_DISTANCE:
          #if True:
          lon.append(row[2])
          lat.append(row[1])
          self.pre_lat = row[1]
          self.pre_lon = row[2]
      timestamp_new = row[0]

    #print("\tlogger_core : update_track(old) ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    #t = datetime.datetime.utcnow()
    
    #if timestamp is None:
    #  cur.execute(select_base)
    #else:
    #  cur.execute(select_base + "AND timestamp > '%s'" % timestamp)
    #test = np.array(cur.fetchall())
    #if(test.shape[0] > 0):
    #  test2 = np.array(test[:,1:], dtype='float32')
    #  drop_test = np.insert(np.any(np.diff(test2, axis=0) == 0, axis=1), 0, False)
    #  test3 = test[~drop_test,:]
    #  #print(test.shape, test2.shape, test3.shape)
    #  timestamp_new = test[-1,0]

    #print("\tlogger_core : update_track(new) ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    
    cur.close()
    con.close()

    #print("\tlogger_core : return length: ", len(lon))
    return timestamp_new, lon, lat

  def load_course(self):
    
    # namespace 
    NS = {'TCDv2': 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2'}
    
    print(self.course_filename)
    
    t = datetime.datetime.utcnow()
    
    tree = ET.parse(self.course_filename)
    tcx_root = tree.getroot()
    
    print("\tlogger_core : load_course : ET parse", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    t = datetime.datetime.utcnow()
    
    courses = tcx_root.find('TCDv2:Courses', NS)
    course = courses.find('TCDv2:Course', NS)

    #summary
    self.course_info['Name'] = course.find('TCDv2:Name', NS).text
    Lap = course.find('TCDv2:Lap', NS)
    self.course_info['DistanceMeters'] = float(Lap.find('TCDv2:DistanceMeters', NS).text)
    
    #track
    track = course.find('TCDv2:Track', NS)
    track_points = track.findall('TCDv2:Trackpoint', NS)

    #coursepoint
    course_points = course.findall('TCDv2:CoursePoint', NS)

    pre_alt = pre_dist = None
    pre_dist_slope = None
    dist_diff = dist_sum = 0
    alt_start = alt_end = None
    slope = 0
    slope_smoothing = pre_slope_smoothing = None
    max_dist = 0
    self.sensor.sensor_gps.reset_course_index()
    
    print("\tlogger_core : load_course : initialize", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    t = datetime.datetime.utcnow()

    name = position = latitude = longitude = point_type = notes = None
    TCDv2_prefix = "{"+NS['TCDv2']+"}"
    
    for i, cp in enumerate(course_points):
      #search
      for child in cp:
        if child.tag == TCDv2_prefix+"Name":
          name = child.text
        elif child.tag == TCDv2_prefix+"Position":
          for position_child in child:
            if position_child.tag == TCDv2_prefix+"LatitudeDegrees":
              latitude = float(position_child.text)
            elif position_child.tag == TCDv2_prefix+"LongitudeDegrees":
              longitude = float(position_child.text)
        elif child.tag == TCDv2_prefix+"PointType":
          point_type = child.text
        elif child.tag == TCDv2_prefix+"Notes":
          notes = child.text

      self.course_point_name.append(name)
      self.course_point_latitude.append(latitude)
      self.course_point_longitude.append(longitude)
      self.course_point_point_type.append(point_type)
      self.course_point_notes.append(notes)

    print("\tlogger_core : load_course : course point:", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    t = datetime.datetime.utcnow()

    position = latitude = longitude = distance = altitude = None
    for i, tp in enumerate(track_points):
      
      values = {}
      for child in tp.iter():
        values[child.tag] = child.text
      try:
        latitude = float(values[TCDv2_prefix+"LatitudeDegrees"])
        longitude = float(values[TCDv2_prefix+"LongitudeDegrees"])
        distance = float(values[TCDv2_prefix+"DistanceMeters"])
        altitude = float(values[TCDv2_prefix+"AltitudeMeters"])
      except:
        continue
      
      if i == 0:
        dist_diff = 0
        dist_sum = 0
        alt_start = altitude
        alt_end = altitude
        pre_dist_slope = distance
      elif i > 0:
        dist_diff = distance - pre_dist
        dist_sum += dist_diff
        
        #skip storing if distance diff is too short
        if dist_sum < self.config.G_GPS_DISPLAY_INTERVAL_DISTANCE:
          continue
        
        #make slope by each dist_diff
        if dist_diff > 0:
          slope = 100*(altitude - pre_alt)/ dist_diff
        #stock max dist_diff for self.config.G_GPS_ON_ROUTE_CUTOFF
        if dist_diff > max_dist:
          max_dist = dist_diff
        
        #make slope_smoothing by distance (self.config.G_SLOPE_BIN)
        if distance - pre_dist_slope >= self.config.G_SLOPE_BIN:
          alt_end = altitude
          slope_smoothing = 100*(alt_end - alt_start)/ (distance - pre_dist_slope)
          
          #reset
          pre_dist_slope = distance
          alt_start = alt_end
          #last one is first value of filling slope_smoothing
          pre_slope_smoothing = slope_smoothing
        else:
          slope_smoothing = None
        
        dist_sum = 0
      
      self.course_distance.append(distance/1000)
      self.course_altitude.append(altitude)
      self.course_latitude.append(latitude)
      self.course_longitude.append(longitude)
      self.course_slope.append(slope)
      self.course_slope_smoothing.append(slope_smoothing)

      pre_alt = altitude
      pre_dist = distance
    
    print("\tlogger_core : load_course : read loop block: ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")

    #update G_GPS_ON_ROUTE_CUTOFF from course
    self.config.G_GPS_ON_ROUTE_CUTOFF = int(max_dist / 2) + 1
    if np.ceil(max_dist)/1000 > self.config.G_GPS_SEARCH_RANGE: #[km]
      self.config.G_GPS_SEARCH_RANGE = np.ceil(max_dist)/1000
    print("G_GPS_ON_ROUTE_CUTOFF:", self.config.G_GPS_ON_ROUTE_CUTOFF)
    print("course length:", len(track_points), "->", len(self.course_distance))

    t = datetime.datetime.utcnow()

    #####################
    # LOOP(NUMPY) START #
    #####################
    latitude = longitude = distance = altitude = None
    dist_sum = pre_dist = 0
    dist_diff = None
    max_dist = 0
    pre_dist = pre_dist_slope = pre_alt = np.nan
    alt_start = alt_end = None
    first_track = True

    track_points_n = len(track_points)
    self.np_course_distance = np.empty(track_points_n)
    self.np_course_altitude = np.empty(track_points_n)
    self.np_course_latitude = np.empty(track_points_n)
    self.np_course_longitude = np.empty(track_points_n)
    self.np_course_slope = np.empty(track_points_n)
    self.np_course_slope_smoothing = np.empty(track_points_n)
    tmp_i = 0
    
    for tp in track_points:
      values = {}
      for child in tp.iter():
        values[child.tag] = child.text
      try:
        latitude = float(values[TCDv2_prefix+"LatitudeDegrees"])
        longitude = float(values[TCDv2_prefix+"LongitudeDegrees"])
        distance = float(values[TCDv2_prefix+"DistanceMeters"])
        altitude = float(values[TCDv2_prefix+"AltitudeMeters"])
      except:
        continue
      
      #reduce points
      dist_diff = distance - pre_dist
      dist_sum += dist_diff
      if not first_track and dist_sum < self.config.G_GPS_DISPLAY_INTERVAL_DISTANCE:
        continue
      
      #make slope by each dist_diff
      if not first_track and dist_diff > 0:
        slope = 100*(altitude - pre_alt)/ dist_diff
      #stock max dist_diff for self.config.G_GPS_ON_ROUTE_CUTOFF
      if not first_track and dist_diff > max_dist:
        max_dist = dist_diff
      
      #make slope_smoothing by distance (self.config.G_SLOPE_BIN)
      if not first_track and distance - pre_dist_slope >= self.config.G_SLOPE_BIN:
        alt_end = altitude
        slope_smoothing = 100*(alt_end - alt_start)/ (distance - pre_dist_slope)
        
        #reset
        pre_dist_slope = distance
        alt_start = alt_end
        #last one is first value of filling slope_smoothing
        pre_slope_smoothing = slope_smoothing
      else:
        slope_smoothing = None

      pre_dist = distance
      pre_alt = altitude
      
      if not first_track:
        dist_sum = 0
      else:
        first_track = False
        alt_start = altitude
        alt_end = altitude
        pre_dist_slope = distance

      self.np_course_latitude[tmp_i] = latitude
      self.np_course_longitude[tmp_i] = longitude
      self.np_course_distance[tmp_i] = distance/1000
      self.np_course_altitude[tmp_i] = altitude
      self.np_course_slope[tmp_i] = slope
      self.np_course_slope_smoothing[tmp_i] = slope_smoothing
      tmp_i += 1
    
    self.np_course_latitude = self.np_course_latitude[0:tmp_i]
    self.np_course_longitude = self.np_course_longitude[0:tmp_i]
    self.np_course_distance = self.np_course_distance[0:tmp_i]
    self.np_course_altitude = self.np_course_altitude[0:tmp_i]
    self.np_course_slope = self.np_course_slope[0:tmp_i]
    self.np_course_slope_smoothing = self.np_course_slope_smoothing[0:tmp_i]

    #dist, alt -> dist_diff, alt_diff -> slope
    #np_course_distance_diff = np.diff(self.np_course_distance)
    #np_course_altitude_diff = np.diff(self.np_course_altitude)
    #self.np_course_slope = np_course_altitude_diff / np_course_distance_diff
    #np_course_slope_smoothing = np.array(self.course_slope_smoothing)
    
    print("\tlogger_core : load_course : read loop block(numpy): ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    print("course length:", len(track_points), "->", len(self.np_course_distance))
    t = datetime.datetime.utcnow()
    
    ###################
    # LOOP(NUMPY) END #
    ###################

    #fill slope_smoothing 
    for i in list(reversed(range(len(self.course_slope_smoothing)))):
      if self.course_slope_smoothing[i] != None:
        pre_slope_smoothing = self.course_slope_smoothing[i]
      else:
        self.course_slope_smoothing[i] = pre_slope_smoothing
    print("\tlogger_core : load_course : fill course_slope_smoothing: ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    t = datetime.datetime.utcnow()
    
    #make data
    # for SimpleMapWidget: lat_by_slope, lon_by_slope
    # for SimpleMapWidget: colored_altitude
    lat_n = len(self.course_latitude)

    for i in range(len(self.config.G_SLOPE_CUTOFF)):
      self.lat_by_slope.append([np.nan,]*lat_n)
      self.lon_by_slope.append([np.nan,]*lat_n)
    self.colored_altitude = [None,]*lat_n

    for i in range(1,lat_n):
      j = 0
      for cutoff in self.config.G_SLOPE_CUTOFF:
        if self.course_slope_smoothing[i] <= cutoff:
          break
        j += 1 
      #j = np.min(np.where(cutoff_array >= self.course_slope_smoothing[i]))
      
      self.lat_by_slope[j][i-1] = self.course_latitude[i-1]
      self.lat_by_slope[j][i] = self.course_latitude[i]
      self.lon_by_slope[j][i-1] = self.course_longitude[i-1]
      self.lon_by_slope[j][i] = self.course_longitude[i]
      self.colored_altitude[i] = self.config.G_SLOPE_COLOR[j]
    
    print("\tlogger_core : load_course : fill slope: ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    t = datetime.datetime.utcnow()

    self.course_point_distance = [None,]*len(self.course_point_latitude)
    min_index = 0
    for i in range(len(self.course_point_latitude)):
      dist_diff = np.sqrt(
        (self.np_course_longitude[min_index:] - self.course_point_longitude[i])**2 + \
        (self.np_course_latitude[min_index:] - self.course_point_latitude[i])**2
        )
      index = dist_diff.argmin()
      self.course_point_distance[i] = self.np_course_distance[min_index+index]
      min_index = min_index+index
    
    print("\tlogger_core : load_course : course point distance: ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
    t = datetime.datetime.utcnow()

  def send_ambient(self):
    if not _IMPORT_AMBIENT or self.config.G_MANUAL_STATUS != "START":
      return
    t = datetime.datetime.now()
    if (t - self.send_time).total_seconds() < self.send_online_interval_sec:
      return
    self.send_time = t
    try:
      d = {
        'd1': self.sensor.values['integrated']['speed'] * 3.6,
        'd2': self.sensor.values['integrated']['hr'], 
        'd3': self.sensor.values['integrated']['cadence'],
        'd4': self.sensor.values['integrated']['power'],
        'd5': self.sensor.values['I2C']['altitude'],
        'd6': self.sensor.values['integrated']['distance']/1000,
        'd7': self.sensor.values['integrated']['accumulated_power']/1000,
        'd8': self.sensor.values['I2C']['temperature'],
        'lat':self.sensor.values['GPS']['lat'], 
        'lng':self.sensor.values['GPS']['lon']
        }
      d_send = {}
      for k,v in d.items():
        if not np.isnan(v):
          d_send[k] = v
      r = self.am.send(d_send)
      print(r,d_send)
    #except requests.exceptions.RequestException as e:
    #  print('request failed: ', e)
    except:
      pass



