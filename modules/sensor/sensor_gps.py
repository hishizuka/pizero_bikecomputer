import time
import datetime
import math
import random
import numpy as np
import re

from .sensor import Sensor

#GPS
_SENSOR_GPS = False
try:
  from dateutil import tz
  from dateutil import parser
  from gps3 import gps3
  from pyproj import Geod
  from pytz import timezone
  #device test
  _gps_socket = gps3.GPSDSocket()
  _gps_socket.close()
  _SENSOR_GPS = True
except:
  pass
print('  GPS : ',_SENSOR_GPS)


class SensorGPS(Sensor):

  gps_socket = None
  gps_datastream = None
  pre_lat = np.nan
  pre_lon = np.nan
  pre_alt = np.nan
  pre_index = -1
  drc_str = [
      'N','NNE','NE','ENE',
      'E','ESE','SE','SSE',
      'S','SSW','SW','WSW',
      'W','WNW','NW','NNW',
      'N',
    ]
  geo = None
  elements = ['lat','lon','alt',
    'speed','track','track_str',
    'used_sats','total_sats','used_sats_str',
    'epx', 'epy', 'epv','error',
    'time','utctime','mode']
  is_time_modified = False
  is_fixed = False
  is_altitude_modified = False

  def sensor_init(self):
    if _SENSOR_GPS:
      self.geo = Geod(ellps='WGS84')
      self.gps_socket = gps3.GPSDSocket()
      self.gps_datastream = gps3.DataStream()
      self.gps_socket.connect()
      self.gps_socket.watch()
    self.reset()
    self.reset_course_index()
    for element in self.elements:
      self.values[element] = np.nan

  def reset(self):
    self.values['distance'] = 0
  
  def reset_course_index(self):
    self.values['course_index'] = -1
    self.pre_index = -1
    self.first_update_course_index = False

  def quit(self):
    if _SENSOR_GPS:
      self.gps_socket.close()

  def start(self):
    if _SENSOR_GPS:
      self.update()
    elif self.config.G_DUMMY_OUTPUT:
      course_i = 0
      while not self.config.G_QUIT:
        time.sleep(self.config.G_SENSOR_INTERVAL)
        for element in self.elements:
          self.values[element] = np.nan
        #self.values['track_str'] = "-"
        #unit: m/s
        #self.values['speed'] = random.randint(1,6) * 3.6
        self.values['speed'] = (random.randint(13,83)/10) #5 - 30km/h
        if self.config.G_STOPWATCH_STATUS == "START":
          #unit: m
          self.values['distance'] += self.values['speed']
        
        if self.config.logger != None and len(self.config.logger.course_longitude) > 0:
          self.values['lat'] = self.config.logger.course_latitude[course_i]
          self.values['lon'] = self.config.logger.course_longitude[course_i]
          course_i += 5
          course_i = course_i % len(self.config.logger.course_longitude)
          if course_i >= len(self.config.logger.course_longitude)-1:
            course_i = len(self.config.logger.course_longitude)-1
          index = self.values['course_index']
          if index == -1:
            index = 0
          self.values['course_index'] = self.get_course_index(index)

        self.values['timestamp'] = datetime.datetime.now()

  def update(self):
    for new_data in self.gps_socket:
      if self.config.G_QUIT:
        break
      time.sleep(self.config.G_GPS_INTERVAL)
      if new_data:
        self.gps_datastream.unpack(new_data)
        self.get_GPS_values()

  def get_GPS_values(self):
    g = self.gps_datastream.TPV
    gs = self.gps_datastream.SKY
    geo_inv_result = []
    
    if not np.isnan(self.values['lat']) and not np.isnan(self.values['lon']):
      self.pre_lat = self.values['lat']
      self.pre_lon = self.values['lon']
      self.pre_alt = self.values['alt']
    
    #initialize
    for element in self.elements:
      self.values[element] = np.nan
    
    #coordinate
    if g['lat'] != self.config.G_GPS_NULLVALUE and g['lon'] != self.config.G_GPS_NULLVALUE:
      if (-90 <= g['lat'] <= 90) and (-180 <= g['lon'] <= 180):
        self.values['lat'] = g['lat']
        self.values['lon'] = g['lon']
    else: #copy from pre value
        self.values['lat'] = self.pre_lat
        self.values['lon'] = self.pre_lon
    
    #altitude
    if g['alt'] != self.config.G_GPS_NULLVALUE:
      self.values['alt'] = g['alt']
      #floor
      if self.values['alt'] < -500:
        self.values['alt'] = -500
    else: #copy from pre value
        self.values['alt'] = self.pre_alt

    #GPS distance
    if not np.isnan(self.values['lat']) and not np.isnan(self.values['lon']):
      if not np.isnan(self.pre_lon) and not np.isnan (self.pre_lat):
        #2D distance : (x1, y1), (x2, y2)
        geo_inv_result = self.geo.inv(self.values['lon'],self.values['lat'],self.pre_lon,self.pre_lat)
        #need 3D distance? : (x1, y1, z1), (x2, y2, z2)

        if self.config.G_STOPWATCH_STATUS == "START":
          #unit: m
          self.values['distance'] += geo_inv_result[2]
    
    #speed
    if g['speed'] != self.config.G_GPS_NULLVALUE:
      #unit m/s
      self.values['speed'] = g['speed']
      if self.values['speed'] <= self.config.G_GPS_SPEED_CUTOFF:
        self.values['speed'] = 0.0
    
    #track
    if g['track'] != self.config.G_GPS_NULLVALUE and self.values['speed'] > 0.0:
      self.values['track'] = g['track']
      self.values['track_str'] = self.get_direction_arrow_str(self.values['track'])
    
    #satellites
    (self.values['total_sats'], self.values['used_sats'])\
     = self.satellites_used(gs['satellites'])
    self.values['used_sats_str'] \
      = str(self.values['used_sats']) + "/" + str(self.values['total_sats'])
    
    #err
    for error in ['epx', 'epy', 'epv']:
      if g[error] != self.config.G_GPS_NULLVALUE:
        self.values[error] = g[error]
    if type(self.values['epx']) in [float, int] and type(self.values['epy']) in [float, int]\
      and not np.isnan(self.values['epx']) and not np.isnan(self.values['epy']):
        self.values['error'] = math.sqrt(self.values['epx'] * self.values['epy'])
    else:
      self.values['error'] = np.nan
    
    #UTC time
    if g['time'] != self.config.G_GPS_NULLVALUE:
      self.values['time'] = g['time']
      self.values['utctime'] = self.values['time'][11:16] #[11:19] for HH:MM:SS
      if not self.is_time_modified:
        self.is_time_modified = self.set_time()
    
    #fix
    if g['mode'] != self.config.G_GPS_NULLVALUE:
      self.values['mode'] = g['mode']
      if not self.is_fixed and self.values['mode'] == 3: #3D Fix
        self.is_fixed = self.set_timezone()
    
    #timestamp
    self.values['timestamp'] = datetime.datetime.now()

    #course_index
    index = self.values['course_index']
    if index == -1:
      index = 0
    #only update first GPS fix and running for 
    if len(geo_inv_result) > 0 and ( \
      not self.first_update_course_index or \
      (self.first_update_course_index and geo_inv_result[2] >= self.config.G_GPS_SPEED_CUTOFF) \
      ):
      index = self.get_course_index(index)
      self.first_update_course_index = True
    else:
      index = -1
    #get valid value from past
    if index == -1 and self.pre_index != -1:
      self.values['course_index'] = self.pre_index
    #update pre_value with valid value
    if self.values['course_index'] != -1:
      self.pre_index = self.values['course_index']
    #print("index",self.values['course_index'])

    #modify altitude with course
    if not self.is_altitude_modified and self.values['course_index'] != -1:
      self.config.logger.sensor.sensor_i2c.update_sealevel_pa(
        self.config.logger.course_altitude[self.values['course_index']]
        )
      self.is_altitude_modified = True

  def satellites_used(self,feed):
    total_satellites = 0
    used_satellites = 0

    if not isinstance(feed, list):
      return 0, 0
    for satellites in feed:
      total_satellites += 1
      if satellites['used'] is True:
        used_satellites += 1
    return total_satellites, used_satellites
      
  # replace direction arrow?
  def get_direction_arrow_str(self, drc):
    drc_int = int((drc + 11.25)/22.50)
    return self.drc_str[drc_int]

  def set_timezone(self):
    print('attempt to modify timezone by gps...')
    lat = self.values['lat']
    lon = self.values['lon']
    if np.isnan(lat) or np.isnan(lon):
      return False
    tzcmd = ['python3', './scripts/set_timezone.py', str(lat), str(lon)]
    self.config.G_TIMEZONE = self.config.exec_cmd_return_value(tzcmd)
    return True

  def set_time(self):
    print('attempt to modify time by gps...')

    #for ublox error
    #ValueError: ('Unknown string format:', '1970-01-01T00:00:00(null')
    if self.values['time'].find('1970-01-01') >= 0:
      return False
   
    l_time = parser.parse(self.values['time'])
    #kernel version date
    kernel_date = datetime.datetime(2019, 1, 1, 0, 0, 0, 0, tz.tzutc())
    kernel_date_str = self.config.exec_cmd_return_value(['uname', '-v'])
    # "#1253 Thu Aug 15 11:37:30 BST 2019"
    if len(kernel_date_str) >= 34:
      m = re.search(r'^.+(\w{3}) (\d+).+(\d{4})$', kernel_date_str)
      if m:
        time_str = '{:s} {:s} {:s} 00:00:00 UTC'.format(m.group(3), m.group(1), m.group(2))
        kernel_date = parser.parse(time_str)
    if l_time < kernel_date:
      return False
    datecmd = ['sudo', 'date', '-u', '--set', l_time.strftime('%Y/%m/%d %H:%M:%S')]
    self.config.exec_cmd(datecmd)
    return True

  def get_course_index(self, start):

    #don't search
    #initializing logger
    if self.config.logger == None or len(self.config.logger.course_longitude) == 0:
      return -1
    #no gps value
    if np.isnan(self.values['lon']) or np.isnan(self.values['lat']):
      return -1
    
    #search with numpy
    forward_search_index = self.get_index_with_distance_cutoff(start, self.config.G_GPS_SEARCH_RANGE)
    backword_serach_index = self.get_index_with_distance_cutoff(start, -self.config.G_GPS_SEARCH_RANGE)
    

    dist_diff = np.sqrt(
      (self.config.logger.np_course_longitude - self.values['lon'])**2 + \
      (self.config.logger.np_course_latitude - self.values['lat'])**2
      )

    #1st start -> forward_search_index
    #2nd backword_serach_index -> start
    #3rd forward_search_index -> end of course
    #4th start of course -> backword_serach_index
    search_indexes = [
      [start, forward_search_index],
      [backword_serach_index, start],
      [forward_search_index, len(self.config.logger.np_course_longitude)-1],
      [0, backword_serach_index],
      ]
    min_indexes = []
    for s in search_indexes:
      if s[0] == s[1] or s[0] < 0:
        min_indexes.append(-1)
        continue
      min_indexes.append(s[0] + dist_diff[s[0]:s[1]].argmin())
    
    for m in min_indexes:
      if m == -1:
        continue
      result = self.config.dist_on_earth(
        self.config.logger.course_longitude[m], 
        self.config.logger.course_latitude[m], 
        self.values['lon'], 
        self.values['lat']
        )
      if result < self.config.G_GPS_ON_ROUTE_CUTOFF:
        return m

    return -1

  def get_index_with_distance_cutoff(self, start, search_range):
    if self.config.logger == None or len(self.config.logger.course_distance) == 0:
      return

    dist_to = self.config.logger.course_distance[start] + search_range
    if dist_to >= self.config.logger.course_distance[-1]:
      return len(self.config.logger.course_distance) - 1
    elif dist_to <= 0:
      return 0

    min_index = -1
    if search_range > 0:
      min_index = start + np.abs((self.config.logger.np_course_distance[start:] - dist_to)).argmin()
    elif search_range < 0:
      min_index = np.abs((self.config.logger.np_course_distance[0:start] - dist_to)).argmin()

    return min_index

  def hasGPS(self):
    return _SENSOR_GPS

