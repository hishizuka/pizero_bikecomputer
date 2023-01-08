import time
import datetime
import asyncio
import re
import numpy as np

from .sensor import Sensor

  
#GPS
_SENSOR_GPS_BASIC = False
try:
  from dateutil import tz
  from dateutil import parser
  _SENSOR_GPS_BASIC = True
except:
  pass

_SENSOR_GPS_I2C = False
try:
  if _SENSOR_GPS_BASIC:
    import pa1010d
    _sensor_i2c_gps = pa1010d.PA1010D()
    _sensor_i2c_gps.read_sentence(timeout=1)
    _SENSOR_GPS_I2C = True
except:
  pass

_SENSOR_GPS_GPSD = False

try:
  if _SENSOR_GPS_BASIC and not _SENSOR_GPS_I2C:
    from gps3 import agps3threaded
    #device test
    _gps3_thread = agps3threaded.AGPS3mechanism()
    _SENSOR_GPS_GPSD = True
except:
  try:
    _gps3_thread.stop()
  except:
    pass

_SENSOR_GPS_ADAFRUIT_UART = False
try:
  if _SENSOR_GPS_BASIC and not _SENSOR_GPS_I2C and not _SENSOR_GPS_GPSD:
    import serial
    import adafruit_gps
    _uart = serial.Serial("/dev/ttyS0", baudrate=9600, timeout=10)
    _sensor_adafruit_gps = adafruit_gps.GPS(_uart, debug=False)
    _SENSOR_GPS_ADAFRUIT_UART = True
except:
  try:
    _uart.close()
  except:
    pass

if _SENSOR_GPS_GPSD:
  print('GPS ', end='')
if _SENSOR_GPS_ADAFRUIT_UART:
  print('GPS_ADAFRUIT_UART ', end='')
if _SENSOR_GPS_I2C:
  print('GPS_I2C ', end='')

class SensorGPS(Sensor):

  gps_thread = None
  elements = [
    'lat','lon','alt',
    'pre_lat','pre_lon','pre_alt','pre_track',
    'speed','track', 'track_str',
    'used_sats','total_sats','used_sats_str',
    'epx', 'epy', 'epv',
    'pdop', 'hdop', 'vdop',
    'time','utctime','mode',
    ]
  is_time_modified = False
  is_fixed = False
  is_altitude_modified = False
  course_index_check = []
  azimuth_cutoff = [0,360]

  def sensor_init(self):
    if _SENSOR_GPS_GPSD:
      self.gps_thread = _gps3_thread
      self.gps_thread.stream_data()
      self.gps_thread.run_thread()
      self.config.G_GPS_NULLVALUE = "n/a"
    elif _SENSOR_GPS_ADAFRUIT_UART:
      self.adafruit_gps = _sensor_adafruit_gps
      self.config.G_GPS_NULLVALUE = None
      #(GPGLL), GPRMC, (GPVTG), GPGGA, GPGSA, GPGSV, (GPGSR), (GPGST)
      self.adafruit_gps.send_command(b'PMTK314,0,1,0,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0')
      self.adafruit_gps.send_command(b"PMTK220,1000")
    elif _SENSOR_GPS_I2C:
      self.i2c_gps = _sensor_i2c_gps
      self.config.G_GPS_NULLVALUE = None

    self.reset()
    for element in self.elements:
      self.values[element] = np.nan
    
    self.azimuth_cutoff = [self.config.G_GPS_AZIMUTH_CUTOFF, 360-self.config.G_GPS_AZIMUTH_CUTOFF]

  def reset(self):
    self.values['distance'] = 0
    self.reset_course_index()
  
  def reset_course_index(self):
    self.values['course_index'] = 0
    self.values['course_point_index'] = 0
    self.values['course_distance'] = 0
    self.values['course_altitude'] = np.nan
    self.values['on_course_status'] = False
    self.course_index_check = [True]*self.config.G_GPS_KEEP_ON_COURSE_CUTOFF

  async def quit(self):
    await self.sleep()

    if _SENSOR_GPS_GPSD:
      self.gps_thread.stop()
    elif _SENSOR_GPS_ADAFRUIT_UART:
      _uart.close()

  def start_coroutine(self):
    asyncio.create_task(self.start())
    
  async def start(self):
    if not self.config.G_DUMMY_OUTPUT:
      if _SENSOR_GPS_GPSD:
        await self.update()
      elif _SENSOR_GPS_ADAFRUIT_UART:
        await self.update_adafruit()
      elif _SENSOR_GPS_I2C:
        await self.update_i2c()
    else:
      await self.dummy_update()

  async def dummy_update(self):
    course_i = pre_course_i = 0
    #course_i = pre_course_i = 100
    log_speed = 5

    while not self.config.G_QUIT:
      await self.sleep()

      if self.config.logger == None or len(self.config.logger.course.latitude) == 0:
        continue

      #self.values['track_str'] = "-"
      #unit: m/s
      #self.values['speed'] = random.randint(1,6) * 3.6
      self.values['speed'] = (np.random.randint(13,83)/10) #5 - 30km/h

      lat = self.config.logger.course.latitude
      lon = self.config.logger.course.longitude
      dist = self.config.logger.course.distance*1000
      course_n = len(self.config.logger.course.latitude)
      
      self.values['pre_lat'] = self.values['lat']
      self.values['pre_lon'] = self.values['lon']
      self.values['pre_track'] = self.values['track']
      #generate dummy position from log
      if self.config.logger.position_log.shape[0] > 0:
        self.values['lat'] = self.config.logger.position_log[course_i][0]
        self.values['lon'] = self.config.logger.position_log[course_i][1]
        self.values['distance'] = self.config.logger.position_log[course_i][2]
        self.values['track'] = self.config.logger.position_log[course_i][3]
        if(self.values['track'] == None):
          self.values['track'] = self.values['pre_track']
        if course_i == pre_course_i:
          course_i += 1*log_speed
          continue
        else:
          pre_course_i = course_i
          course_i += 1*log_speed
          if course_i >= len(self.config.logger.position_log):
            course_i = pre_course_i = 0
            continue
      #from course
      else:
        rand = 0.5 #np.random.randint(0,10)/10
        self.values['lat'] = lat[course_i]
        self.values['lon'] = lon[course_i]
        self.values['distance'] = dist[course_i]
        if course_i+1 < len(lat):
          self.values['lat'] += (lat[course_i+1] - lat[course_i])*rand
          self.values['lon'] += (lon[course_i+1] - lon[course_i])*rand
          self.values['distance'] += (dist[course_i+1] - dist[course_i])*rand
        pre_course_i = course_i
        course_i += int(course_n/200)+1
        if course_i >= course_n:
          pre_course_i = 0
          course_i = course_i % course_n
        lat_points = np.array([self.values['pre_lat'], self.values['lat']])
        lon_points = np.array([self.values['pre_lon'], self.values['lon']])
        self.values['track'] = int((self.config.calc_azimuth(lat_points, lon_points))[0])
      
      #calculate course_index separately
      #t2 = datetime.datetime.utcnow()
      self.get_course_index()
      #print("get_course_index: ", (datetime.datetime.utcnow()-t2).total_seconds(), "sec")

      self.values['timestamp'] = datetime.datetime.now()
      self.get_sleep_time(self.config.G_GPS_INTERVAL)

  async def update(self):
    g = self.gps_thread.data_stream
    while not self.config.G_QUIT:
      await self.sleep()
      self.init_GPS_values()
      await self.get_GPS_basic_values(
        g.lat,
        g.lon,
        g.alt,
        g.speed,
        g.track,
        g.mode,
        [g.epx, g.epy, g.epv],
        [g.pdop, g.hdop, g.vdop],
      )
      self.get_satellites(g.satellites)
      self.get_utc_time(g.time)
      self.get_sleep_time(self.config.G_GPS_INTERVAL)

  #experimental code
  async def update_adafruit(self):
    g = self.adafruit_gps
    #self.start_time = datetime.datetime.now()
    #self.wait_time = 0
    while not self.config.G_QUIT:
      #print(datetime.datetime.now(), self.wait_time)
      #sleep
      await self.sleep()
      cnt = 0
      #while (datetime.datetime.now() - self.start_time).total_seconds() < self.wait_time:
      #while cnt < 20:
      for i in range(20):
        g.update()
        #print(datetime.datetime.now(), i)
        #cnt += 1
        await asyncio.sleep(0.04)
      #self.start_time = datetime.datetime.now()
      if g.has_fix:
        self.init_GPS_values()
        speed = 0
        if g.speed_knots != self.config.G_GPS_NULLVALUE:
          speed = g.speed_knots * 1.852 / 3.6
        await self.get_GPS_basic_values(
          g.latitude,
          g.longitude,
          g.altitude_m,
          speed,
          g.track_angle_deg,
          g.fix_quality_3d,
          None,
          [g.pdop, g.hdop, g.vdop],
        )
        self.get_satellites_adafruit(g.sats)
        self.get_utc_time(time.strftime("%Y/%m/%d %H:%M:%S +0000", g.timestamp_utc))
      self.get_sleep_time(self.config.G_GPS_INTERVAL)

  async def update_i2c(self):
    g = self.i2c_gps

    while not self.config.G_QUIT:
      await self.sleep()
    
      result = g.update()
      if result:
        self.init_GPS_values()
        speed = 0
        lat = self.config.G_GPS_NULLVALUE
        lon = self.config.G_GPS_NULLVALUE
        timestamp = self.config.G_GPS_NULLVALUE
        if g.data['mode_fix_type'] != None and int(g.data['mode_fix_type']) > 1:
          lat = g.data['latitude']
          lon = g.data['longitude']
        if g.data['timestamp'] != self.config.G_GPS_NULLVALUE:
          timestamp = g.data['timestamp'].strftime("%H:%M:%S +0000") 
        if g.data['speed_over_ground'] != self.config.G_GPS_NULLVALUE:
          speed = g.data['speed_over_ground'] * 1.852 / 3.6
        await self.get_GPS_basic_values(
          lat,
          lon,
          g.data['altitude'],
          speed,
          self.config.G_GPS_NULLVALUE,
          g.data['mode_fix_type'],
          None,
          [g.data['pdop'], g.data['hdop'], g.data['vdop']],
          )
        if g.data['num_sats'] != self.config.G_GPS_NULLVALUE:
          self.values['used_sats_str'] = str(g.data['num_sats'])
          self.values['used_sats'] = g.data['num_sats']
        self.get_utc_time(timestamp)
      self.get_sleep_time(self.config.G_GPS_INTERVAL)

  def init_GPS_values(self):
    #backup values
    if not np.isnan(self.values['lat']) and not np.isnan(self.values['lon']):
      self.values['pre_lat'] = self.values['lat']
      self.values['pre_lon'] = self.values['lon']
      self.values['pre_alt'] = self.values['alt']
      self.values['pre_track'] = self.values['track']
    #initialize
    for element in self.elements:
      if element in ['pre_lat', 'pre_lon', 'pre_alt', 'pre_track']:
        continue
      self.values[element] = np.nan

  async def get_GPS_basic_values(self, lat, lon, alt, speed, track, mode, error, dop):
    valid_pos = False

    #fix
    if mode != self.config.G_GPS_NULLVALUE:
      self.values['mode'] = mode

    #err(GPSd only)
    if error != None:
      for i, key in enumerate(['epx', 'epy', 'epv']):
        if error[i] != self.config.G_GPS_NULLVALUE:
          self.values[key] = error[i]
    
    #DOP
    for i, key in enumerate(['pdop', 'hdop', 'vdop']):
      if dop[i] != self.config.G_GPS_NULLVALUE:
        self.values[key] = dop[i]

    #coordinate
    if lat != self.config.G_GPS_NULLVALUE and lon != self.config.G_GPS_NULLVALUE \
      and (-90 <= lat <= 90) and (-180 <= lon <= 180) \
      and self.values['mode'] == 3 \
      and not np.isnan(self.values['epx']) \
      and not np.isnan(self.values['epy']) \
      and not np.isnan(self.values['epv']) \
      and self.values['epx'] < self.config.G_GPS_GPSD_EPX_EPY_CUTOFF \
      and self.values['epy'] < self.config.G_GPS_GPSD_EPX_EPY_CUTOFF \
      and self.values['epv'] < self.config.G_GPS_GPSD_EPV_CUTOFF:
      valid_pos = True
    
    if valid_pos:
      self.values['lat'] = lat
      self.values['lon'] = lon
    else: #copy from pre value
      self.values['lat'] = self.values['pre_lat']
      self.values['lon'] = self.values['pre_lon']
    
    #altitude
    if valid_pos and alt != self.config.G_GPS_NULLVALUE:
      self.values['alt'] = alt
      #floor
      if self.values['alt'] < -500:
        self.values['alt'] = -500
    else: #copy from pre value
      self.values['alt'] = self.values['pre_alt']

    #GPS distance
    if not np.any(np.isnan([self.values['pre_lon'],self.values['pre_lat'],self.values['lon'],self.values['lat']])):
      #2D distance : (x1, y1), (x2, y2)
      dist = self.config.get_dist_on_earth(
        self.values['pre_lon'],self.values['pre_lat'],self.values['lon'],self.values['lat']
        )
      #need 3D distance? : (x1, y1, z1), (x2, y2, z2)

      if self.config.G_STOPWATCH_STATUS == "START":
        #unit: m
        self.values['distance'] += dist
          
    #speed
    if valid_pos and speed != self.config.G_GPS_NULLVALUE:
      #unit m/s
      self.values['speed'] = speed
      if self.values['speed'] <= self.config.G_GPS_SPEED_CUTOFF:
        self.values['speed'] = 0.0
    
    #track
    if track != self.config.G_GPS_NULLVALUE and speed != self.config.G_GPS_NULLVALUE and \
      self.values['speed'] > self.config.G_GPS_SPEED_CUTOFF:
      self.values['track'] = int(track)
      self.values['track_str'] = self.config.get_track_str(self.values['track'])
    else:
      self.values['track'] = self.values['pre_track']

    #course_index
    #t2 = datetime.datetime.utcnow()
    self.get_course_index()
    #print("get_course_index: ", (datetime.datetime.utcnow()-t2).total_seconds(), "sec")

    #timezone
    if valid_pos and not self.is_fixed and self.values['mode'] == 3: #3D Fix
      self.is_fixed = self.set_timezone()

    #modify altitude with course
    if not self.is_altitude_modified \
      and self.values['on_course_status'] \
      and self.config.logger != None \
      and len(self.config.logger.course.altitude) > 0:
      await self.config.logger.sensor.sensor_i2c.update_sealevel_pa(
        self.config.logger.course.altitude[self.values['course_index']]
        )
      self.is_altitude_modified = True
      pass
    
    #timestamp
    self.values['timestamp'] = datetime.datetime.now()
    
  def get_satellites(self, gs):
    gnum = guse = 0
    
    if not isinstance(gs, list):
      return "0/0"
    for satellites in gs:
      gnum += 1
      if satellites['used']:
        guse += 1
    
    self.values['used_sats'] = guse
    self.values['total_sats'] = gnum
    self.values['used_sats_str'] = str(guse) + "/" + str(gnum)
 
  def get_satellites_adafruit(self, gs):
    gnum = guse = 0
    
    if gs == self.config.G_GPS_NULLVALUE or len(gs) == 0:
      return "0/0"
    for v in gs.values():
      gnum += 1
      if v[3] != self.config.G_GPS_NULLVALUE:
        guse += 1
    
    self.values['used_sats'] = guse
    self.values['total_sats'] = gnum
    self.values['used_sats_str'] = str(guse) + "/" + str(gnum)
  
  def set_timezone(self):
    print('try to modify timezone by gps...')
    lat = self.values['lat']
    lon = self.values['lon']
    if np.isnan(lat) or np.isnan(lon):
      return False
    tzcmd = ['python3', './scripts/set_timezone.py', str(lat), str(lon)]
    self.config.G_TIMEZONE = self.config.exec_cmd_return_value(tzcmd)
    return True
  
  def get_utc_time(self, gps_time):
    #UTC time
    if gps_time == self.config.G_GPS_NULLVALUE:
      return
    
    self.values['time'] = gps_time
    self.values['utctime'] = self.values['time'][11:16] #[11:19] for HH:MM:SS
    
    #for ublox error
    #ValueError: ('Unknown string format:', '1970-01-01T00:00:00(null')
    #if self.values['time'].find('1970-01-01') >= 0:
    if self.values['time'][0:4].isdecimal() and int(self.values['time'][0:4]) < 2000:
      return
    
    if not self.is_time_modified:
      self.is_time_modified = self.set_time()
  
  def set_time(self):
    print('try to modify time by gps...')
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
    #t = datetime.datetime.utcnow()
    
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
      
    #1st search index(a little ahead)
    forward_search_index = min(start + 5, course_n-1)
    #2nd search index(a several kilometers ahead: weak GPS signal, long tunnel)
    forward_search_index_next = max(self.get_index_with_distance_cutoff(start, self.config.G_GPS_SEARCH_RANGE), forward_search_index)
    #3rd search index(backward)
    backword_search_index = self.get_index_with_distance_cutoff(start, -self.config.G_GPS_SEARCH_RANGE)
    
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

    #search with no penalty
    # 1st start -> forward_search_index
    # 2nd forward_search_index -> forward_search_index_next
    #with penalty (continue running while G_GPS_KEEP_ON_COURSE_CUTOFF seconds, then change course_index)
    # 3rd backword_search_index -> start
    # 4th forward_search_index -> end of course
    # 5th start of course -> backword_search_index
    search_indexes = [
      [start, forward_search_index],
      [forward_search_index, forward_search_index_next],
      [backword_search_index, start],
      [forward_search_index_next, course_n-1],
      [0, backword_search_index],
      ]
    s_state=['forward(close)', 'forward(far)', 'back', 'end', 'start']
    penalty_index = 2

    #print()
    for i, s in enumerate(search_indexes):
      #print(i, s)
      if s[0] < 0:
        continue
      elif s[0] == s[1]:
        continue
      
      m = s[0]

      dist_diff_mod = np.where(
        ((0 <= azimuth_diff)&(azimuth_diff <= self.azimuth_cutoff[0])) | ((self.azimuth_cutoff[1] <= azimuth_diff)&(azimuth_diff <= 360)),
        dist_diff,
        np.inf
      )
      #print(dist_diff_mod)
      #print(inner_p)

      if s[1] >= course_n-1:
        m += dist_diff_mod[s[0]:].argmin()
      else:
        m += dist_diff_mod[s[0]:s[1]].argmin()
      
      #check azimuth
      #print("i:{}, s:{}, m:{}, azimuth_diff:{}".format(i, s, m, azimuth_diff[m]))
      #print("self.values['track']:{}, m:{}".format(self.values['track'], m))
      #print(self.config.logger.course.azimuth)
      #print("azimuth_diff:{}".format(azimuth_diff))
      if np.isnan(azimuth_diff[m]):
        #GPS is lost(return start finally)
        continue
      if 0 <= azimuth_diff[m] <= self.azimuth_cutoff[0] or self.azimuth_cutoff[1] <= azimuth_diff[m] <= 360:
        #go forward
        pass
      else:
        #go backward
        #print("self.values['track']:{}, m:{}".format(self.values['track'], m))
        #print(self.config.logger.course.azimuth)
        #print("azimuth_diff:{}".format(azimuth_diff))
        continue
      #print("i:{}, s:{}, m:{}, azimuth_diff:{}, course_index:{}, course_point_index:{}".format(i, s, m, azimuth_diff[m], self.values['course_index'], self.values['course_point_index']))
      #print("\t lat_lon: {}, {}".format(self.values['lat'], self.values['lon']))
      #print("\t course: {}, {}".format(self.config.logger.course.latitude[self.values['course_index']], self.config.logger.course.longitude[self.values['course_index']]))
      #print("\t course_point: {}, {}".format(self.config.logger.course.point_latitude[self.values['course_point_index']], self.config.logger.course.point_longitude[self.values['course_point_index']]))

      #grade check if available
      grade = self.config.logger.sensor.values['integrated']['grade']
      if(not np.isnan(grade) and (grade > self.config.G_SLOPE_CUTOFF[0]) != (self.config.logger.course.slope_smoothing[m] > self.config.G_SLOPE_CUTOFF[0])):
        continue
      
      if m == 0 and inner_p[0] <= 0.0:
        print("before start of course:", start, "->", m)
        print("\t", self.values['lat'],self.values['lon'],"/", self.config.logger.course.latitude[m], self.config.logger.course.longitude[m])
        self.values['on_course_status'] = False
        self.values['course_distance'] = 0
        self.values['course_altitude'] = np.nan
        self.values['course_index'] =  m
        return
      elif m == len(dist_diff)-1 and inner_p[-1] >= 1.0:
        print("after end of course", start, "->", m)
        print("\t", self.values['lat'],self.values['lon'],"/", self.config.logger.course.latitude[m], self.config.logger.course.longitude[m])
        self.values['on_course_status'] = False
        m = course_n-1
        self.values['course_distance'] = self.config.logger.course.distance[-1]*1000
        self.values['course_altitude'] = np.nan
        self.values['course_index'] =  m
        return
      
      h_lon = self.config.logger.course.longitude[m] + \
        (self.config.logger.course.longitude[m+1]-self.config.logger.course.longitude[m]) * inner_p[m]
      h_lat = self.config.logger.course.latitude[m] + \
        (self.config.logger.course.latitude[m+1]-self.config.logger.course.latitude[m]) * inner_p[m]
      dist_diff_h = self.config.get_dist_on_earth(
        h_lon, h_lat,
        self.values['lon'], self.values['lat']
      )

      if dist_diff_h > self.config.G_GPS_ON_ROUTE_CUTOFF:
        #print("dist_diff_h: {:.0f} > cutoff {}[m]".format(dist_diff_h, self.config.G_GPS_ON_ROUTE_CUTOFF))
        #print("\t i:{}, s:{}, m:{}, azimuth_diff:{}, course_point_index:{}".format(i, s, m, azimuth_diff[m], self.values['course_point_index']))
        #print("\t h_lon/h_lat: {}, {}, lat_lon: {}, {}".format(h_lat, h_lon, self.values['lat'], self.values['lon']))
        #print("\t course[m]: {}, {}".format(self.config.logger.course.latitude[m], self.config.logger.course.longitude[m]))
        #print("\t course[m+1]: {}, {}".format(self.config.logger.course.latitude[m+1], self.config.logger.course.longitude[m+1]))
        continue

      #stay forward while self.config.G_GPS_KEEP_ON_COURSE_CUTOFF if search_indexes is except forward
      #prevent from changing course index quickly
      self.course_index_check[:-1] = self.course_index_check[1:]
      if i < penalty_index:
        self.course_index_check[-1] = True
      else:
        self.course_index_check[-1] = False
      if self.course_index_check[-1] == False and np.sum(self.course_index_check) != 0:
        #print("course_index_check failed, self.course_index_check[-1]:{}, np.sum(self.course_index_check):{}".format(self.course_index_check[-1], np.sum(self.course_index_check)))
        #print("\t i:{}, s:{}, m:{}, azimuth_diff:{}, course_point_index:{}".format(i, s, m, azimuth_diff[m+1], self.values['course_point_index']))
        #print("\t {}, {}, {:.2f}m".format(self.values['lat'], self.values['lon'], self.values['course_distance']/1000))
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
      
      if len(self.config.logger.course.altitude) > 0:
        alt_diff_course = 0
        if (m+1 < len(self.config.logger.course.altitude)):
          alt_diff_course = \
            (self.config.logger.course.altitude[m+1]-self.config.logger.course.altitude[m]) \
            /((self.config.logger.course.distance[m+1]-self.config.logger.course.distance[m])*1000)\
            *dist_diff_course
        self.values['course_altitude'] = self.config.logger.course.altitude[m] + alt_diff_course
        
      #print("search: ", (datetime.datetime.utcnow()-t).total_seconds(), "sec, index:", m)
      
      self.values['course_index'] =  m

      if len(self.config.logger.course.point_distance) > 0:
        cp_m = np.abs(self.config.logger.course.point_distance - self.values['course_distance']/1000).argmin()
        #specify next points for displaying in cuesheet widget
        if (self.config.logger.course.point_distance[cp_m] < self.values['course_distance']/1000):
          cp_m += 1
        if cp_m >= len(self.config.logger.course.point_distance):
          cp_m = len(self.config.logger.course.point_distance)-1
        self.values['course_point_index'] =  cp_m
      
      if i >= penalty_index:
        print(s_state[i], start, "->", m)
        print("\t", self.values['lat'],self.values['lon'],"/", self.config.logger.course.latitude[m], self.config.logger.course.longitude[m])
        print("\t", "azimuth_diff:", azimuth_diff[m])
      
      return

    self.values['on_course_status'] = False

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
    return _SENSOR_GPS_GPSD or _SENSOR_GPS_I2C or _SENSOR_GPS_ADAFRUIT_UART

