import os
import sqlite3
import datetime
import shutil
import re
import xml.etree.ElementTree as ET
from math import factorial
from crdp import rdp

import numpy as np

import importlib
POLYLINE_DECODER = False
try:
  import polyline
  POLYLINE_DECODER = True
except:
  pass

class LoaderTcx():
  
  config = None
  sensor = None

  #for course
  info = {}
  distance = np.array([])
  altitude = np.array([])
  latitude = np.array([])
  longitude = np.array([])
  points_diff = np.array([]) #for course distance

  azimuth = np.array([])
  slope = np.array([])
  slope_smoothing = np.array([])
  colored_altitude = np.array([])
  climb_segment = []

  #for course points
  point_name = np.array([])
  point_latitude = np.array([])
  point_longitude = np.array([])
  point_type = np.array([])
  point_notes = np.array([])
  point_distance = np.array([])

  def __init__(self, config, sensor):
    print("\tlogger_core : init...")
    super().__init__()
    self.config = config
    self.sensor = sensor

  def reset(self):
    
    #for course
    self.info = {}
    #raw data
    self.distance = np.array([])
    self.altitude = np.array([])
    self.latitude = np.array([])
    self.longitude = np.array([])
    #processed variables
    self.azimuth = np.array([])
    self.slope = np.array([])
    self.slope_smoothing = np.array([])
    self.colored_altitude = np.array([])
    self.points_diff = np.array([])
    self.climb_segment = []

    #for course points
    self.point_name = np.array([])
    self.point_latitude = np.array([])
    self.point_longitude = np.array([])
    self.point_type = np.array([])
    self.point_notes = np.array([])
    self.point_distance = np.array([])
    self.point_altitude = np.array([])

    #for external modules
    self.sensor.sensor_gps.reset_course_index()

  def load(self):
    self.reset()
    self.read_tcx()
    self.downsample()
    self.calc_slope_smoothing()
    self.modify_course_points()
  
  def search_route(self, x1, y1, x2, y2):
    if np.any(np.isnan([x1, y1, x2, y2])):
      return
    self.reset()
    self.get_google_route(x1, y1, x2, y2)
    self.downsample()
    self.calc_slope_smoothing()
    self.modify_course_points()

  def read_tcx(self):
    if not os.path.exists(self.config.G_COURSE_FILE):
      return
    print("loading", self.config.G_COURSE_FILE)
    
    t = datetime.datetime.utcnow()

    #read with regex
    pattern = {
      "name": re.compile(r'<Name>(?P<text>[\s\S]*?)</Name>'),
      "distance_meters": re.compile(r'<DistanceMeters>(?P<text>[\s\S]*?)</DistanceMeters>'),
      "track": re.compile(r'<Track>(?P<text>[\s\S]*?)</Track>'),
      "latitude": re.compile(r'<LatitudeDegrees>(?P<text>[^<]*)</LatitudeDegrees>'),
      "longitude": re.compile(r'<LongitudeDegrees>(?P<text>[^<]*)</LongitudeDegrees>'),
      "altitude": re.compile(r'<AltitudeMeters>(?P<text>[^<]*)</AltitudeMeters>'),
      "distance": re.compile(r'<DistanceMeters>(?P<text>[^<]*)</DistanceMeters>'),
      "course_point": re.compile(r'<CoursePoint>(?P<text>[\s\S]+)</CoursePoint>'),
      "course_name": re.compile(r'<Name>(?P<text>[^<]*)</Name>'),
      "course_point_type": re.compile(r'<PointType>(?P<text>[^<]*)</PointType>'),
      "course_notes": re.compile(r'<Notes>(?P<text>[^<]*)</Notes>'),
    }

    with open(self.config.G_COURSE_FILE, 'r', encoding="utf-8_sig") as f:
      tcx = f.read()

      match_name = pattern["name"].search(tcx)
      if match_name:
        self.info['Name'] = match_name.group('text').strip()
      
      match_distance_meter = pattern["distance_meters"].search(tcx)
      if match_distance_meter:
        self.info['DistanceMeters'] = round(float(match_distance_meter.group('text').strip())/1000,1)

      match_track = pattern["track"].search(tcx)
      if match_track:
        track = match_track.group('text')
        self.latitude = np.array([float(m.group('text').strip()) for m in pattern["latitude"].finditer(track)])
        self.longitude = np.array([float(m.group('text').strip()) for m in pattern["longitude"].finditer(track)])
        self.altitude = np.array([float(m.group('text').strip()) for m in pattern["altitude"].finditer(track)])
        self.distance = np.array([float(m.group('text').strip()) for m in pattern["distance"].finditer(track)])
      
      match_course = pattern["course_point"].search(tcx)
      if match_course:
        course_point = match_course.group('text')
        self.point_name = [m.group('text').strip() for m in pattern["course_name"].finditer(course_point)]
        self.point_latitude = np.array([float(m.group('text').strip()) for m in pattern["latitude"].finditer(course_point)])
        self.point_longitude = np.array([float(m.group('text').strip()) for m in pattern["longitude"].finditer(course_point)])
        self.point_type = [m.group('text').strip() for m in pattern["course_point_type"].finditer(course_point)]
        self.point_notes = [m.group('text').strip() for m in pattern["course_notes"].finditer(course_point)]
    
    print("\tlogger_core : load_course : read tcx(regex): ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")

    check_course = False
    if not (len(self.latitude) == len(self.longitude) == len(self.altitude) == len(self.distance)):
      print("ERROR parse course")
      check_course = True
    if not (len(self.point_name) == len(self.point_latitude) == len(self.point_longitude) == len(self.point_type)):
      print("ERROR parse course point")
      check_course = True
    if check_course:
      self.distance = np.array([])
      self.altitude = np.array([])
      self.latitude = np.array([])
      self.longitude = np.array([])
      self.point_name = np.array([])
      self.point_latitude = np.array([])
      self.point_longitude = np.array([])
      self.point_type = np.array([])
      return
    
    #delete 'Straight' of course points
    if len(self.point_type) > 0:
      ptype = np.array(self.point_type)
      not_straight_cond = np.where(ptype != 'Straight', True, False)
      self.point_type = list(ptype[not_straight_cond])
      if len(self.point_name) > 0:
        self.point_name = list(np.array(self.point_name)[not_straight_cond])
      if len(self.point_latitude) > 0:
        self.point_latitude = np.array(self.point_latitude)[not_straight_cond]
      if len(self.point_longitude) > 0:
        self.point_longitude = np.array(self.point_longitude)[not_straight_cond]
      if len(self.point_notes) > 0:
        self.point_notes = list(np.array(self.point_notes)[not_straight_cond])
  
  def get_google_route(self, x1, y1, x2, y2):
    json_routes = self.config.get_google_routes(x1, y1, x2, y2)
    if not POLYLINE_DECODER or json_routes == None or json_routes["status"] != "OK":
      return
    
    self.info['Name'] = "Google routes"
    self.info['DistanceMeters'] = round(json_routes["routes"][0]["legs"][0]["distance"]["value"]/1000,1)

    points = np.array(polyline.decode(json_routes["routes"][0]["overview_polyline"]["points"]))
    points_detail = []
    self.point_name = []
    self.point_latitude = []
    self.point_longitude = []
    self.point_distance = []
    self.point_type = []
    self.point_notes = []

    dist = 0
    pre_dist = 0
    pattern = {
      "html_remove_1": re.compile(r'\/?\</?\w+\/?\>'),
      "html_remove_2":re.compile(r'\<\S+\>'),
    }
    for step in json_routes["routes"][0]["legs"][0]["steps"]:
      points_detail.extend(polyline.decode(step["polyline"]["points"]))
      dist += pre_dist
      pre_dist = step["distance"]["value"]/1000

      if "maneuver" not in step or any(map(step["maneuver"].__contains__, ('straight', 'merge', 'keep'))):
        continue
        #https://developers.google.com/maps/documentation/directions/get-directions
        #turn-slight-left, turn-sharp-left, turn-left, 
        #turn-slight-right, turn-sharp-right, keep-right, 
        #keep-left, uturn-left, uturn-right, turn-right,
        #straight,
        #ramp-left, ramp-right, 
        #merge,
        #fork-left, fork-right,
        #ferry, ferry-train, 
        #roundabout-left, and roundabout-right
      turn_str = step["maneuver"]
      if turn_str[-4:] == "left":
        turn_str = "Left"
      elif turn_str[-5:] == "right":
        turn_str = "Right"
      self.point_type.append(turn_str)
      self.point_latitude.append(step["start_location"]["lat"])
      self.point_longitude.append(step["start_location"]["lng"])
      self.point_distance.append(dist)
      text = (re.subn(pattern["html_remove_1"],"", step["html_instructions"])[0]).replace(" ","").replace("&nbsp;", "")
      text = re.subn(pattern["html_remove_2"],"",text)[0]
      #self.point_name.append(text)
      self.point_name.append(turn_str)
    points_detail = np.array(points_detail)
    #print(self.point_type)

    self.latitude = np.array(points_detail)[:,0]
    self.longitude = np.array(points_detail)[:,1]
    self.point_latitude = np.array(self.point_latitude)
    self.point_longitude = np.array(self.point_longitude)
    self.point_distance = np.array(self.point_distance)

  def downsample(self):
    len_lat = len(self.latitude)
    len_lon = len(self.longitude)
    len_alt = len(self.altitude)
    len_dist = len(self.distance)

    #empty check
    if len_lat == 0 and len_lon == 0 and len_alt == 0 and len_dist == 0:
      return

    t = datetime.datetime.utcnow()

    try:
      cond = np.array(rdp(np.column_stack([self.longitude, self.latitude]), epsilon=0.0001, return_mask=True))
      if len_alt > 0 and len_dist > 0:
        cond = cond | np.array(rdp(np.column_stack([self.distance, self.altitude]), epsilon=10, return_mask=True))
      self.latitude = self.latitude[cond]
      self.longitude = self.longitude[cond]
      if len_alt > 0:
        self.altitude = self.altitude[cond] #[m]
      if len_dist > 0:
        self.distance = self.distance[cond]/1000 #[km]
    except:
      self.distance = self.distance/1000 #[km]

    #for sensor_gps
    self.azimuth = self.config.calc_azimuth(self.latitude, self.longitude)
    self.points_diff = np.array([np.diff(self.longitude), np.diff(self.latitude)]) 
    self.points_diff_sum_of_squares = self.points_diff[0]**2 + self.points_diff[1]**2
    self.points_diff_dist = np.sqrt(self.points_diff_sum_of_squares)

    if len_dist == 0:
      self.distance = self.config.get_dist_on_earth_array(
        self.longitude[0:-1],
        self.latitude[0:-1],
        self.longitude[1:], 
        self.latitude[1:],
      )/1000
      self.distance = np.insert(self.distance, 0, 0)
      self.distance = np.cumsum(self.distance)
    dist_diff = 1000 * np.diff(self.distance) #[m]

    if len_alt > 0:
      modified_altitude = self.savitzky_golay(self.altitude, 53, 3)
      #do not apply if length is differnet (occurs when too short course)
      if(len(self.altitude) == len(modified_altitude)):
        self.altitude = modified_altitude

      #experimental code
      #np.savetxt('log/course_altitude.csv', self.altitude, fmt='%.3f')
      #np.savetxt('log/course_distance.csv', self.distance, fmt='%.3f')

      #output dem altitude
      #alt_dem = np.zeros(len(self.altitude))
      #for i in range(len(self.altitude)):
      #  alt_dem[i] = self.config.get_altitude_from_tile([self.longitude[i], self.latitude[i]])
      #np.savetxt('log/course_altitude_dem.csv', alt_dem, fmt='%.3f')
    
    diff_dist_max = int(np.max(dist_diff))*2/1000 #[m->km]
    if diff_dist_max > self.config.G_GPS_SEARCH_RANGE: #[km]
      self.config.G_GPS_SEARCH_RANGE = diff_dist_max
    #print("G_GPS_SEARCH_RANGE[km]:", self.config.G_GPS_SEARCH_RANGE, diff_dist_max)

    print("downsampling:{} -> {}".format(len_lat, len(self.latitude)))

    print("\tlogger_core : load_course : downsampling: ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")

  def calc_slope_smoothing(self):
    #parameters
    course_n = len(self.distance)
    diff_num = 4
    LP_coefficient = 0.15

    self.colored_altitude = np.full((course_n, 3), self.config.G_SLOPE_COLOR[0]) #3 is RGB

    if course_n < 2*diff_num or len(self.altitude) < 2*diff_num:
      return
    
    t = datetime.datetime.utcnow()

    dist_diff = np.zeros((diff_num, course_n))
    alt_diff = np.zeros((diff_num, course_n))
    grade = np.zeros((diff_num, course_n))
    dist_diff[0,1:] = self.distance[1:]-self.distance[0:-1]
    alt_diff[0,1:] = self.altitude[1:]-self.altitude[0:-1]
    grade[0,1:] = alt_diff[0, 1:]/(dist_diff[0, 1:]*1000)*100
    for i in range(1, diff_num):
      dist_diff[i, i:-i] = self.distance[2*i:]-self.distance[0:-2*i]
      dist_diff[i, 0:i] = self.distance[i:2*i]-self.distance[0]
      dist_diff[i, -i:] = self.distance[-1]-self.distance[-2*i:-i]
      alt_diff[i, i:-i] = self.altitude[2*i:]-self.altitude[0:-2*i]
      alt_diff[i, 0:i] = self.altitude[i:2*i]-self.altitude[0]
      alt_diff[i, -i:] = self.altitude[-1]-self.altitude[-2*i:-i]
      grade[i] = alt_diff[i]/(dist_diff[i]*1000)*100
    
    grade_mod = np.zeros(course_n)
    cond_all = np.full(course_n, False)
    for i in range(diff_num-1):
      cond = (dist_diff[i] >= self.config.G_CLIMB_DISTANCE_CUTOFF)
      cond_diff = cond ^ cond_all
      grade_mod[cond_diff] = grade[i][cond_diff]
      cond_all = cond
    cond = np.full(course_n, True)
    cond_diff = cond ^ cond_all
    grade_mod[cond_diff] = grade[3][cond_diff]

    #apply LP fileter (forward and backward)
    self.slope_smoothing = np.zeros(course_n)
    self.slope_smoothing[0] = grade_mod[0]
    self.slope_smoothing[-1] = grade_mod[-1]
    #forward
    for i in range(1, course_n-1):
      self.slope_smoothing[i] = grade_mod[i]*LP_coefficient + self.slope_smoothing[i-1]*(1-LP_coefficient)
    #backward
    for i in reversed(range(course_n-1)):
      self.slope_smoothing[i] = self.slope_smoothing[i]*LP_coefficient + self.slope_smoothing[i+1]*(1-LP_coefficient)

    #detect climbs
    slope_smoothing_cat = np.zeros(course_n).astype('uint8')
    for i in range(i, len(self.config.G_SLOPE_CUTOFF)-1):
      slope_smoothing_cat = np.where((self.config.G_SLOPE_CUTOFF[i-1]<self.slope_smoothing)&(self.slope_smoothing<=self.config.G_SLOPE_CUTOFF[i]), i, slope_smoothing_cat)
    slope_smoothing_cat = np.where((self.config.G_SLOPE_CUTOFF[-1]<self.slope_smoothing), len(self.config.G_SLOPE_CUTOFF)-1, slope_smoothing_cat)

    #self.climb_segment = [] #[start_index, end_index, distance, average_grade, volume(=dist*average), cat]
    climb_search_state = False
    climb_start_cutoff = 2
    climb_end_cutoff = 1
    if slope_smoothing_cat[0] >= climb_start_cutoff:
      self.climb_segment.append({'start':0, 'start_point_distance':self.distance[0], 'start_point_altitude':self.altitude[0]})
      climb_search_state = True
    for i in range(1, course_n):
      #search climb end (detect top of climb)
      if climb_search_state and slope_smoothing_cat[i-1] >= climb_end_cutoff and (slope_smoothing_cat[i] < climb_end_cutoff or i == course_n-1):
        end_index = i
        self.climb_segment[-1]['end'] = end_index
        self.climb_segment[-1]['distance'] = self.distance[end_index] - self.distance[self.climb_segment[-1]['start']]
        alt = (self.altitude[end_index] - self.altitude[self.climb_segment[-1]['start']])
        self.climb_segment[-1]['average_grade'] = alt/(self.climb_segment[-1]['distance']*1000)*100
        self.climb_segment[-1]['volume'] = self.climb_segment[-1]['distance']*1000 * self.climb_segment[-1]['average_grade']
        self.climb_segment[-1]['course_point_distance'] = self.distance[end_index]
        self.climb_segment[-1]['course_point_altitude'] = self.altitude[end_index]
        self.climb_segment[-1]['course_point_longitude'] = self.longitude[end_index]
        self.climb_segment[-1]['course_point_latitude'] = self.latitude[end_index]
        if self.climb_segment[-1]['distance'] < self.config.G_CLIMB_DISTANCE_CUTOFF or \
          self.climb_segment[-1]['average_grade'] < self.config.G_CLIMB_GRADE_CUTOFF or \
          self.climb_segment[-1]['volume'] < self.config.G_CLIMB_CATEGORY[0]['volume']:
          #print(self.climb_segment[-1]['distance'], self.climb_segment[-1]['volume'], self.climb_segment[-1]['distance'], self.climb_segment[-1]['average_grade'])
          self.climb_segment.pop()
        else:
          for j in reversed(range(len(self.config.G_CLIMB_CATEGORY))):
            if self.climb_segment[-1]['volume'] > self.config.G_CLIMB_CATEGORY[j]['volume']:
              self.climb_segment[-1]['cat'] = self.config.G_CLIMB_CATEGORY[j]['name']
              break
        climb_search_state = False
      #detect climb start
      elif not climb_search_state and slope_smoothing_cat[i-1] < climb_start_cutoff and slope_smoothing_cat[i] >= climb_start_cutoff:
        self.climb_segment.append({'start':i, 'start_point_distance':self.distance[i], 'start_point_altitude':self.altitude[i]})
        climb_search_state = True

    #print(self.climb_segment)
    self.colored_altitude = np.array(self.config.G_SLOPE_COLOR)[slope_smoothing_cat]

    print("\tlogger_core : load_course : slope_smoothing: ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")

  def modify_course_points(self):
    #make route colors by slope for SimpleMapWidget, CourseProfileWidget
    t = datetime.datetime.utcnow()

    len_pnt_dist = len(self.point_distance)
    len_pnt_alt = len(self.point_altitude)

    #calculate course point distance
    if len_pnt_dist == 0 and len(self.distance) > 0:
      self.point_distance = np.empty(len(self.point_latitude))
    if len_pnt_alt == 0 and len(self.altitude) > 0:
      self.point_altitude = np.zeros(len(self.point_latitude))
    
    min_index = 0
    for i in range(len(self.point_latitude)):
      b_a_x = self.points_diff[0][min_index:]
      b_a_y = self.points_diff[1][min_index:]
      lon_diff = self.point_longitude[i] - self.longitude[min_index:]
      lat_diff = self.point_latitude[i] - self.latitude[min_index:]
      p_a_x = lon_diff[:-1]
      p_a_y = lat_diff[:-1]
      inner_p = (b_a_x*p_a_x + b_a_y*p_a_y)/self.points_diff_sum_of_squares[min_index:]
      inner_p_check = np.where((0.0 <= inner_p) & (inner_p <= 1.0), True, False)

      min_j = None
      min_dist_diff_h = np.inf
      min_dist_delta = 0
      min_alt_delta = 0
      for j in list(*np.where(inner_p_check == True)):
        h_lon = self.longitude[min_index+j] + \
          (self.longitude[min_index+j+1]-self.longitude[min_index+j]) * inner_p[j]
        h_lat = self.latitude[min_index+j] + \
          (self.latitude[min_index+j+1]-self.latitude[min_index+j]) * inner_p[j]
        dist_diff_h = self.config.get_dist_on_earth(h_lon, h_lat, self.point_longitude[i], self.point_latitude[i])

        if dist_diff_h < self.config.G_GPS_ON_ROUTE_CUTOFF and dist_diff_h < min_dist_diff_h:
          if min_j != None and j - min_j > 2:
            continue
          min_j = j
          min_dist_diff_h = dist_diff_h
          min_dist_delta = self.config.get_dist_on_earth(self.longitude[min_index+j], self.latitude[min_index+j], h_lon, h_lat)/1000
          if len(self.altitude) > 0:
            min_alt_delta = (self.altitude[min_index+j+1]-self.altitude[min_index+j]) / (self.distance[min_index+j+1]-self.distance[min_index+j]) * min_dist_delta

      if min_j == None:
        min_j = 0
      min_index = min_index+min_j
      
      if len_pnt_dist == 0 and len(self.distance) > 0:
        self.point_distance[i] = self.distance[min_index] + min_dist_delta
      if len_pnt_alt == 0 and len(self.altitude) > 0:
        self.point_altitude[i] = self.altitude[min_index] + min_alt_delta

    #add climb tops
    #if len(self.climb_segment) > 0:
    #  min_index = 0
    #  for i in range(len(self.climb_segment)):
    #    diff_dist = np.abs(self.point_distance - self.climb_segment[i]['course_point_distance'])
    #    min_index = np.where(diff_dist == np.min(diff_dist))[0][0]+1
    #    self.point_name.insert(min_index, "Top of Climb")
    #    self.point_latitude = np.insert(self.point_latitude, min_index, self.climb_segment[i]['course_point_latitude'])
    #    self.point_longitude = np.insert(self.point_longitude, min_index, self.climb_segment[i]['course_point_longitude'])
    #    self.point_type.insert(min_index, "Summit")
    #    self.point_distance = np.insert(self.point_distance, min_index, self.climb_segment[i]['course_point_distance'])
    #    self.point_altitude = np.insert(self.point_altitude, min_index, self.climb_segment[i]['course_point_altitude'])

    len_lat = len(self.point_latitude)
    len_dist = len(self.distance)
    len_alt = len(self.altitude)
    len_pnt_dist = len(self.point_distance)
    len_pnt_alt = len(self.point_altitude)

    #add start course point
    if len_lat > 0 and len_pnt_dist > 0 and len_dist > 0 and self.point_distance[0] != 0.0:
      self.point_name.insert(0, "Start")
      self.point_latitude = np.insert(self.point_latitude, 0, self.latitude[0])
      self.point_longitude = np.insert(self.point_longitude, 0, self.longitude[0])
      self.point_type.insert(0, "")
      if len_pnt_dist > 0 and len_dist > 0:
        self.point_distance = np.insert(self.point_distance, 0, 0.0)
      if len_pnt_alt > 0 and len_alt > 0:
        self.point_altitude = np.insert(self.point_altitude, 0, self.altitude[0])
    #add end course point
    #print(self.point_latitude, self.latitude, self.point_longitude, self.longitude)
    end_distance = None
    if len(self.latitude) > 0 and len(self.point_longitude) > 0:
      end_distance = self.config.get_dist_on_earth_array(
        self.longitude[-1],
        self.latitude[-1],
        self.point_longitude[-1], 
        self.point_latitude[-1],
        )
    if len_lat > 0 and len_pnt_dist > 0 and len_dist > 0 and end_distance != None and end_distance > 5:
      self.point_name.append("End")
      self.point_latitude = np.append(self.point_latitude, self.latitude[-1])
      self.point_longitude = np.append(self.point_longitude, self.longitude[-1])
      self.point_type.append("")
      if len_pnt_dist > 0 and len_dist > 0:
        self.point_distance = np.append(self.point_distance, self.distance[-1])
      if len_pnt_alt > 0 and len_alt > 0:
        self.point_altitude = np.append(self.point_altitude, self.altitude[-1])
    
    self.point_name = np.array(self.point_name)
    self.point_type = np.array(self.point_type)
    self.point_name = np.array(self.point_name)

    print("\tlogger_core : load_course : modify course points: ", (datetime.datetime.utcnow()-t).total_seconds(), "sec")
  
  def savitzky_golay(self, y, window_size, order, deriv=0, rate=1):
    try:
      window_size = np.abs(np.int(window_size))
      order = np.abs(np.int(order))
    except ValueError as msg:
      raise ValueError("window_size and order have to be of type int")
    if window_size % 2 != 1 or window_size < 1:
      raise TypeError("window_size size must be a positive odd number")
    if window_size < order + 2:
      raise TypeError("window_size is too small for the polynomials order")
    order_range = range(order+1)
    half_window = (window_size -1) // 2
    # precompute coefficients
    b = np.mat([[k**i for i in order_range] for k in range(-half_window, half_window+1)])
    m = np.linalg.pinv(b).A[deriv] * rate**deriv * factorial(deriv)
    # pad the signal at the extremes with
    # values taken from the signal itself
    firstvals = y[0] - np.abs( y[1:half_window+1][::-1] - y[0] )
    lastvals = y[-1] + np.abs(y[-half_window-1:-1][::-1] - y[-1])
    y = np.concatenate((firstvals, y, lastvals))
    return np.convolve( m[::-1], y, mode='valid')

