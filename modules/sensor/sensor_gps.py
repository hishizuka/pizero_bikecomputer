import time
import datetime
import numpy as np
import re
import traceback

from .sensor import Sensor

#GPS
_SENSOR_GPS = False
try:
  from dateutil import tz
  from dateutil import parser
  from gps3 import gps3
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
  elements = [
    'lat','lon','alt',
    'speed','track', 'track_str',
    'used_sats','total_sats','used_sats_str',
    'epx', 'epy', 'epv','error',
    'time','utctime','mode',
    ]
  is_time_modified = False
  is_fixed = False
  is_altitude_modified = False
  course_index_check = []
  course_index_check_bin = 5 #number of loop by self.config.G_GPS_INTERVAL

  def sensor_init(self):
    if _SENSOR_GPS:
      self.gps_socket = gps3.GPSDSocket()
      self.gps_datastream = gps3.DataStream()
      self.gps_socket.connect()
      self.gps_socket.watch()
    self.reset()
    for element in self.elements:
      self.values[element] = np.nan

  def reset(self):
    self.values['distance'] = 0
    self.reset_course_index()
  
  def reset_course_index(self):
    self.values['course_index'] = 0
    self.values['course_point_index'] = 0
    self.values['course_distance'] = 0
    self.values['on_course_status'] = False
    self.course_index_check = [True]*self.course_index_check_bin

  def quit(self):
    if _SENSOR_GPS:
      self.gps_socket.close()

  def start(self):
    if _SENSOR_GPS and not self.config.G_DUMMY_OUTPUT:
      self.update()
    elif self.config.G_DUMMY_OUTPUT:
      self.dummy_update()
  
  def dummy_update(self):
    course_i = pre_course_i = 0

    while not self.config.G_QUIT:
      self.sleep()
      self.get_sleep_time(self.config.G_GPS_INTERVAL)

      if self.config.logger == None or len(self.config.logger.course.latitude) == 0:
        continue

      #self.values['track_str'] = "-"
      #unit: m/s
      #self.values['speed'] = random.randint(1,6) * 3.6
      self.values['speed'] = (np.random.randint(13,83)/10) #5 - 30km/h
      if self.config.G_STOPWATCH_STATUS == "START":
        #unit: m
        self.values['distance'] += self.values['speed']

      #if self.config.logger != None and len(self.config.logger.course.latitude) > 0:
      lat = self.config.logger.course.latitude
      lon = self.config.logger.course.longitude
      course_n = len(lat)
      
      self.pre_lat = self.values['lat']
      self.pre_lon = self.values['lon']
      if self.config.logger.position_log.shape[0] > 0:
        self.values['lat'] = self.config.logger.position_log[course_i][0]
        self.values['lon'] = self.config.logger.position_log[course_i][1]
        if course_i == pre_course_i:
          course_i += 1
          continue
        else:
          course_i += 1
          pre_course_i += 1
          if course_i == len(self.config.logger.position_log)-1:
            course_i = pre_course_i = 0
            continue
      else:
        rand = 0.5 #np.random.randint(0,10)/10
        self.values['lat'] = lat[course_i]
        self.values['lon'] = lon[course_i]
        if course_i+1 < len(lat):
          self.values['lat'] += (lat[course_i+1] - lat[course_i])*rand
          self.values['lon'] += (lon[course_i+1] - lon[course_i])*rand
        pre_course_i = course_i
        course_i += int(course_n/200)+1
        if course_i >= course_n:
          pre_course_i = 0
          course_i = course_i % course_n
      
      #print("course lat:", self.pre_lat, self.values['lat'])
      #print("course lon:", self.pre_lon, self.values['lon'])
      lat_points = np.array([self.pre_lat, self.values['lat']])
      lon_points = np.array([self.pre_lon, self.values['lon']])
      self.values['track'] = (self.config.calc_azimuth(lat_points, lon_points))[0]

      #calculate course_index separately
      t2 = datetime.datetime.utcnow()
      self.get_course_index()
      print("get_course_index: ", (datetime.datetime.utcnow()-t2).total_seconds(), "sec")

      self.values['timestamp'] = datetime.datetime.now()

  def update(self):
    for new_data in self.gps_socket:
      if self.config.G_QUIT:
        break
      #time.sleep(self.config.G_GPS_INTERVAL)
      self.sleep()
      if new_data:
        self.gps_datastream.unpack(new_data)
        self.get_GPS_values()
      self.get_sleep_time(self.config.G_GPS_INTERVAL)

  def get_GPS_values(self):
    g = self.gps_datastream.TPV
    gs = self.gps_datastream.SKY
    
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
        dist = self.config.get_dist_on_earth(self.pre_lon,self.pre_lat,self.values['lon'],self.values['lat'])
        #need 3D distance? : (x1, y1, z1), (x2, y2, z2)

        if self.config.G_STOPWATCH_STATUS == "START":
          #unit: m
          self.values['distance'] += dist
          
    #speed
    if g['speed'] != self.config.G_GPS_NULLVALUE:
      #unit m/s
      self.values['speed'] = g['speed']
      if self.values['speed'] <= self.config.G_GPS_SPEED_CUTOFF:
        self.values['speed'] = 0.0
    
    #track
    if g['track'] != self.config.G_GPS_NULLVALUE and self.config.G_STOPWATCH_STATUS == "START":
      self.values['track'] = g['track']
      self.values['track_str'] = self.config.get_track_str(self.values['track'])
    
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
        self.values['error'] = np.sqrt(self.values['epx'] * self.values['epy'])
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
    #t2 = datetime.datetime.utcnow()
    self.get_course_index()
    #print("get_course_index: ", (datetime.datetime.utcnow()-t2).total_seconds(), "sec")

    #modify altitude with course
    if self.config.logger != None and not self.is_altitude_modified and self.values['on_course_status']:
      self.config.logger.sensor.sensor_i2c.update_sealevel_pa(
        self.config.logger.course.altitude[self.values['course_index']]
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

  def get_course_index(self):

    if not self.config.G_COURSE_INDEXING:
      self.values['on_course_status'] = False
      return
   
    start = self.values['course_index']
    t = datetime.datetime.utcnow()
    
    #don't search
    #initializing logger
    if self.config.logger == None:
      return
    #no gps value
    if np.isnan(self.values['lon']) or np.isnan(self.values['lat']):
      return
    #not running
    if self.config.G_IS_RASPI and self.config.G_STOPWATCH_STATUS != "START":
      return
    
    course_n = len(self.config.logger.course.longitude)
    if course_n == 0:
      return
    
    #search with numpy
    forward_search_index = self.get_index_with_distance_cutoff(start, self.config.G_GPS_SEARCH_RANGE)
    backword_serach_index = self.get_index_with_distance_cutoff(start, -self.config.G_GPS_SEARCH_RANGE)
    
    b_a_x = self.config.logger.course.points_diff[0]
    b_a_y = self.config.logger.course.points_diff[1]
    lon_diff = self.values['lon'] - self.config.logger.course.longitude
    lat_diff = self.values['lat'] - self.config.logger.course.latitude
    p_a_x = lon_diff[0:-1]
    p_a_y = lat_diff[0:-1]
    p_b_x = lon_diff[1:]
    p_b_y = lat_diff[1:]
    inner_p = (b_a_x*p_a_x + b_a_y*p_a_y)/self.config.logger.course.points_diff_sum_of_squares

    azimuth_diff = np.full(len(self.config.logger.course.azimuth), np.nan)
    if not np.isnan(self.values['track']):
      azimuth_diff = (self.values['track'] - self.config.logger.course.azimuth) % 360

    dist_diff = np.where(
      inner_p <= 0.0,
      np.sqrt(p_a_x**2 + p_a_y**2),
      np.where(
        inner_p >= 1.0,
        np.sqrt(p_b_x**2 + p_b_y**2),
        np.abs(
          b_a_x*p_a_y - b_a_y*p_a_x
          )/self.config.logger.course.points_diff_dist
        )
      )

    #search minimal interval and index close to start
    #1st start -> forward_search_index
    #2nd backword_serach_index -> start
    #3rd forward_search_index -> end of course
    #4th start of course -> backword_serach_index
    search_indexes = [
      [start, forward_search_index],
      [backword_serach_index, start],
      [forward_search_index, course_n-1],
      [0, backword_serach_index],
      ]
    s_state=['forward', 'back', 'end', 'start']

    for i, s in enumerate(search_indexes):
      if s[0] < 0:
        continue
      elif s[0] == s[1]:
        continue
      
      m = s[0]
      if s[1] >= course_n-1:
        m += dist_diff[s[0]:].argmin()
      else:
        m += dist_diff[s[0]:s[1]].argmin()
      
      #check azimuth
      #print("  s:", s, "m:", m, "azimuth:", azimuth_diff[m])
      if np.isnan(azimuth_diff[m]):
        #GPS is lost(return start finally)
        continue
      #if 0 <= azimuth_diff[m] <= 90 or 270 <= azimuth_diff[m] <= 360:
      #if 0 <= azimuth_diff[m] <= 45 or 315 <= azimuth_diff[m] <= 360:
      if 0 <= azimuth_diff[m] <= 30 or 330 <= azimuth_diff[m] <= 360:
        #go forward
        pass
      else:
        #go backword
        continue
      
      if m == 0 and inner_p[0] <= 0.0:
        print("before start of course:", start, "->", m)
        print("\t", self.values['lon'],self.values['lat'],"/", self.config.logger.course.longitude[m], self.config.logger.course.longitude[m])
        self.values['on_course_status'] = False
        self.values['course_distance'] = 0
        self.values['course_index'] =  m
        return
      elif m == len(dist_diff)-1 and inner_p[-1] >= 1.0:
        print("after end of course", start, "->", m)
        print("\t", self.values['lon'],self.values['lat'],"/", self.config.logger.course.longitude[m], self.config.logger.course.longitude[m])
        self.values['on_course_status'] = False
        m = course_n-1
        self.values['course_distance'] = self.config.logger.course.distance[-1]*1000
        self.values['course_index'] =  m
        return
      
      h_lon = self.config.logger.course.longitude[m] + \
        (self.config.logger.course.longitude[m+1]-self.config.logger.course.longitude[m]) * inner_p[m]
      h_lat = self.config.logger.course.latitude[m] + \
        (self.config.logger.course.latitude[m+1]-self.config.logger.course.latitude[m]) * inner_p[m]
      dist_diff_h = self.config.get_dist_on_earth(
        h_lon, 
        h_lat,
        self.values['lon'], 
        self.values['lat']
        )

      #print("  dist_diff_h:", dist_diff_h, " /", self.config.G_GPS_ON_ROUTE_CUTOFF, "[m]")
      if dist_diff_h < self.config.G_GPS_ON_ROUTE_CUTOFF:

        #stay forward while self.course_index_check_bin if search_indexes is except forward
        #prevent from changing course index quickly
        self.course_index_check[:-1] = self.course_index_check[1:]
        if i == 0:
          self.course_index_check[-1] = True
        else:
          self.course_index_check[-1] = False
        if self.course_index_check[-1] == False and np.sum(self.course_index_check) != 0:
          continue

        self.values['on_course_status'] = True
        dist_diff_course = self.config.get_dist_on_earth(
          self.config.logger.course.longitude[m],
          self.config.logger.course.latitude[m],
          self.values['lon'], 
          self.values['lat']
          )
        self.values['course_distance'] = \
          self.config.logger.course.distance[m]*1000 + dist_diff_course
          
        #print("search: ", (datetime.datetime.utcnow()-t).total_seconds(), "sec, index:", m)
        
        self.values['course_index'] =  m

        if len(self.config.logger.course.point_distance) > 0:
          cp_m = np.abs(self.config.logger.course.point_distance - self.values['course_distance']/1000).argmin()
          if (self.config.logger.course.point_distance[cp_m] < self.values['course_distance']/1000):
            cp_m += 1
          if cp_m >= len(self.config.logger.course.point_distance):
            cp_m = len(self.config.logger.course.point_distance)-1
          self.values['course_point_index'] =  cp_m
          #print(self.values['course_distance']/1000, cp_m)
          #print("course_point_index:", self.values['course_point_index'])
        
        if i > 0:
          print(s_state[i], start, "->", m)
          print("\t", self.values['lon'],self.values['lat'],"/", self.config.logger.course.longitude[m], self.config.logger.course.longitude[m])
          print("\t", "azimuth_diff:", azimuth_diff[m])
        
        return

    print("no result:", start)
    self.values['on_course_status'] = False
    #self.values['course_distance'] = self.config.logger.course.distance[start]*1000

  def get_index_with_distance_cutoff(self, start, search_range):
    if self.config.logger == None or len(self.config.logger.course.distance) == 0:
      return 0

    dist_to = self.config.logger.course.distance[start] + search_range
    #print("----get_index_with_distance_cutoff------")  
    #print("start:", start, "course_distance[start]:", self.config.logger.course.distance[start], "search_range:", search_range)
    #print("dist_to:", dist_to, "dist[-1]:", self.config.logger.course.distance[-1])
    #print("----------------------------------------")  
    if dist_to >= self.config.logger.course.distance[-1]:
      return len(self.config.logger.course.distance) - 1
    elif dist_to <= 0:
      return 0

    min_index = 0
    if search_range > 0:
      min_index = start + np.abs((self.config.logger.course.distance[start:] - dist_to)).argmin()
    elif search_range < 0:
      min_index = np.abs((self.config.logger.course.distance[0:start] - dist_to)).argmin()

    return min_index

  def hasGPS(self):
    return _SENSOR_GPS

