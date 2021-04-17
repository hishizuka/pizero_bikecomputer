import time
import datetime
import threading
import math
import os

import numpy as np

_IMPORT_PSUTIL = False
try:
  import psutil
  _IMPORT_PSUTIL = True
except:
  pass

from .sensor.sensor_gps import SensorGPS
from .sensor.sensor_ant import SensorANT
from .sensor.sensor_gpio import SensorGPIO
from .sensor.sensor_i2c import SensorI2C
from .sensor.sensor_spi import SensorSPI

#Todo: BLE


class SensorCore():

  config = None
  sensor_gps = None
  sensor_ant = None
  sensor_i2c = None
  sensor_gpio = None
  values = {}
  integrated_value_keys =  [
    'hr','speed','cadence','power',
    'distance','accumulated_power',
    'grade','grade_spd','glide_ratio',
    ]
  process = None
  thread_ant = None
  thread_gps = None
  thread_integrate = None
  threshold = {'HR':15, 'SPD':5, 'CDC':3, 'PWR':3}
  grade_range = 9
  grade_window_size = 5
  graph_keys = [
    'hr_graph', 
    'power_graph', 
    'altitude_kf_graph', 
    'altitude_graph',
    ]
  diff_keys = [
    'alt_diff', 
    'dst_diff', 
    'alt_diff_spd', 
    'dst_diff_spd',
    ]
  lp = 4

  def __init__(self, config):
    self.config = config
    self.values['GPS'] = {}
    self.values['ANT+'] = {}
    self.values['BLE'] = {}
    self.values['I2C'] = {}
    self.values['SPI'] = {}
    self.values['integrated'] = {}
    for key in self.integrated_value_keys:
      self.values['integrated'][key] = np.nan
    self.values['integrated']['distance'] = 0
    self.values['integrated']['accumulated_power'] = 0
    for g in self.graph_keys:
      self.values['integrated'][g] = [np.nan] * self.config.G_GUI_HR_POWER_DISPLAY_RANGE
    for d in self.diff_keys:
      self.values['integrated'][d] = [np.nan] * self.grade_range
    self.values['CPU_MEM'] = ""
    if _IMPORT_PSUTIL:
      self.process = psutil.Process(self.config.G_PID)

    time_profile = [datetime.datetime.now(),] #for time profile
    self.sensor_gps = SensorGPS(config, self.values['GPS'])
    self.thread_gps = threading.Thread(target=self.sensor_gps.start, name="thread_gps", args=())
    time_profile.append(datetime.datetime.now()) #for time profile
    self.sensor_ant = SensorANT(config, self.values['ANT+'])
    self.thread_ant = threading.Thread(target=self.sensor_ant.start, name="thread_ant", args=())
    time_profile.append(datetime.datetime.now()) #for time profile
    self.sensor_i2c = SensorI2C(config, self.values['I2C'])
    self.thread_i2c = threading.Thread(target=self.sensor_i2c.start, name="thread_i2c", args=())
    self.sensor_spi = SensorSPI(config, self.values['SPI'])
    time_profile.append(datetime.datetime.now()) #for time profile
    self.sensor_gpio = SensorGPIO(config, None)
    time_profile.append(datetime.datetime.now()) #for time profile
    
    self.thread_integrate = threading.Thread(target=self.integrate, name="thread_integrate", args=())
    time_profile.append(datetime.datetime.now()) #for time profile
    self.start()
    time_profile.append(datetime.datetime.now()) #for time profile

    sec_diff = [] #for time profile
    for i in range(len(time_profile)):
      if i == 0: continue
      sec_diff.append("{0:.6f}".format((time_profile[i]-time_profile[i-1]).total_seconds()))
    print("\tGPS/ANT+/I2C/GPIO/integrate/start:", sec_diff)

  def start(self):
    self.thread_gps.start()
    self.thread_ant.start()
    self.sensor_gpio.update()
    self.thread_i2c.start()
    self.thread_integrate.start()

  def integrate(self):
    pre_dst = {'ANT+':0, 'GPS': 0} 
    pre_ttlwork = {'ANT+':0}
    pre_alt = {'ANT+':np.nan, 'GPS': np.nan}
    pre_alt_spd = {'ANT+':np.nan}
    pre_grade = pre_grade_spd = pre_glide = self.config.G_ANT_NULLVALUE
    diff_sum = {'alt_diff':0, 'dst_diff':0, 'alt_diff_spd':0, 'dst_diff_spd':0}
    #alias for self.values
    v = {'GPS':self.values['GPS'], 'I2C':self.values['I2C']}
    #loop control
    self.wait_time = self.config.G_SENSOR_INTERVAL
    self.actual_loop_interval = self.config.G_SENSOR_INTERVAL
    time_profile = [None,]
    
    #if True:
    while(not self.config.G_QUIT):
      time.sleep(self.wait_time)
      start_time = datetime.datetime.now()
      #print(start_time)

      time_profile = [start_time,]
      hr = spd = cdc = pwr = self.config.G_ANT_NULLVALUE
      grade = grade_spd = glide = self.config.G_ANT_NULLVALUE
      ttlwork_diff = 0
      dst_diff = {'ANT+':0, 'GPS': 0, 'USE': 0}
      alt_diff = {'ANT+':0, 'GPS': 0, 'USE': 0}
      dst_diff_spd = {'ANT+':0}
      alt_diff_spd = {'ANT+':0}
      grade_use = {'ANT+': False, 'GPS': False}
      time_profile.append(datetime.datetime.now())
      #self.sensor_i2c.update()
      #self.sensor_gps.update()
      self.sensor_ant.update() #for dummy

      now_time = datetime.datetime.now()
      time_profile.append(now_time)

      ant_id_type = self.config.G_ANT['ID_TYPE']
      delta = {'PWR':{0x10:float("inf"), 0x11:float("inf"), 0x12:float("inf")}}
      for key in ['HR','SPD','CDC','GPS']:
        delta[key] = float("inf")
      #need for ANT+ ID update
      for key in ['HR','SPD','CDC','PWR']:
        if self.config.G_ANT['USE'][key] and ant_id_type[key] in self.values['ANT+']:
          v[key] = self.values['ANT+'][ant_id_type[key]]

      #make intervals from timestamp
      for key in ['HR','SPD','CDC']:
        if not self.config.G_ANT['USE'][key]: continue
        if 'timestamp' in v[key]:
          delta[key] = (now_time - v[key]['timestamp']).total_seconds()
        #override:
        #cadence from power
        if self.config.G_ANT['TYPE'][key] == 0x0B and key == 'CDC':
          for page in [0x12,0x10]:
            if not 'timestamp' in v[key][page]: continue
            delta[key] = (now_time - v[key][page]['timestamp']).total_seconds()
            break
        #speed from power
        elif self.config.G_ANT['TYPE'][key] == 0x0B and key == 'SPD':
          if not 'timestamp' in v[key][0x11]: continue
          delta[key] = (now_time - v[key][0x11]['timestamp']).total_seconds()
      #timestamp(power)
      if self.config.G_ANT['USE']['PWR']:
        for page in [0x12,0x11,0x10]:
          if not 'timestamp' in v['PWR'][page]: continue
          delta['PWR'][page] = (now_time - v['PWR'][page]['timestamp']).total_seconds()
      if 'timestamp' in v['GPS']:
        delta['GPS'] = (now_time - v['GPS']['timestamp']).total_seconds()
      
      #HeartRate : ANT+
      if self.config.G_ANT['USE']['HR']:
        if delta['HR'] < self.threshold['HR']:
          hr = v['HR']['hr']
        
      #Cadence : ANT+
      if self.config.G_ANT['USE']['CDC']:
        cdc = 0
        #get from cadence or speed&cadence sensor
        if self.config.G_ANT['TYPE']['CDC'] in [0x79, 0x7A]:
          if delta['CDC'] < self.threshold['CDC']:
            cdc = v['CDC']['cadence']
        #get from powermeter
        elif self.config.G_ANT['TYPE']['CDC'] == 0x0B:
          for page in [0x12,0x10]:
            if not 'timestamp' in v[key][page]: continue
            if delta['CDC'] < self.threshold['CDC']:
              cdc = v['CDC'][page]['cadence']
              break

      #Power : ANT+(assumed crank type > wheel type)
      if self.config.G_ANT['USE']['PWR']:
        pwr = 0
        #page18 > 17 > 16, 16simple is not used
        for page in [0x12,0x11,0x10]:
          if delta['PWR'][page] < self.threshold['PWR']:
            pwr = v['PWR'][page]['power']
            break
     
      #Speed : ANT+(SPD&CDC, (PWR)) > GPS
      if self.config.G_ANT['USE']['SPD']:
        spd = 0
        if self.config.G_ANT['TYPE']['SPD'] in [0x79, 0x7B]:
          if delta['SPD'] < self.threshold['SPD']:
            spd = v['SPD']['speed']
        elif self.config.G_ANT['TYPE']['SPD'] == 0x0B:
          if delta['SPD'] < self.threshold['SPD']:
            spd = v['SPD'][0x11]['speed']
      elif 'timestamp' in v['GPS']:
        spd = 0
        if not np.isnan(v['GPS']['speed']) and delta['GPS'] < self.threshold['SPD']:
          spd = v['GPS']['speed']
 
      #Distance: ANT+(SPD, (PWR)) > GPS
      if self.config.G_ANT['USE']['SPD']:
        #normal speed meter
        if self.config.G_ANT['TYPE']['SPD'] in [0x79, 0x7B]:
          if pre_dst['ANT+'] < v['SPD']['distance']:
            dst_diff['ANT+'] = v['SPD']['distance'] - pre_dst['ANT+']
          pre_dst['ANT+'] = v['SPD']['distance']
        elif self.config.G_ANT['TYPE']['SPD'] == 0x0B:
          if pre_dst['ANT+'] < v['SPD'][0x11]['distance']:
            dst_diff['ANT+'] = v['SPD'][0x11]['distance'] - pre_dst['ANT+']
          pre_dst['ANT+'] = v['SPD'][0x11]['distance']
        dst_diff['USE'] = dst_diff['ANT+']
        grade_use['ANT+'] = True
      if 'timestamp' in v['GPS']:
        if pre_dst['GPS'] < v['GPS']['distance']:
          dst_diff['GPS'] = v['GPS']['distance'] - pre_dst['GPS']
        pre_dst['GPS'] = v['GPS']['distance']
        if not self.config.G_ANT['USE']['SPD'] and dst_diff['GPS'] > 0:
          dst_diff['USE'] = dst_diff['GPS']
          grade_use['GPS'] = True
      
      #Total Power: ANT+
      if self.config.G_ANT['USE']['PWR']:
        #both type are not exist in same ID(0x12:crank, 0x11:wheel)
        # if 0x12 or 0x11 exists, never take 0x10
        for page in [0x12,0x11,0x10]:
          if 'timestamp' in v['PWR'][page]:
            if pre_ttlwork['ANT+'] < v['PWR'][page]['accumulated_power']:
              ttlwork_diff = v['PWR'][page]['accumulated_power'] - pre_ttlwork['ANT+']
            pre_ttlwork['ANT+'] = v['PWR'][page]['accumulated_power']
            #never take other powermeter
            break
     
      #altitude
      #if not np.isnan(v['I2C']['altitude_kalman']):
      if not np.isnan(v['I2C']['pre_altitude']):
        #alt = v['I2C']['altitude_kalman']
        #alt = round(v['I2C']['altitude_kalman'], 1)
        alt = v['I2C']['altitude']
        #for grade (distance base)
        for key in ['ANT+', 'GPS']:
          if dst_diff[key] > 0:
            alt_diff[key] = alt - pre_alt[key]
            pre_alt[key] = alt
        if self.config.G_ANT['USE']['SPD']:
          alt_diff['USE'] = alt_diff['ANT+']
        elif not self.config.G_ANT['USE']['SPD'] and dst_diff['GPS'] > 0:
          alt_diff['USE'] = alt_diff['GPS']
        #for grade (speed base)
        if self.config.G_ANT['USE']['SPD']:
          alt_diff_spd['ANT+'] = alt - pre_alt_spd['ANT+']
          pre_alt_spd['ANT+'] = alt
      
      #grade (distance base)
      if dst_diff['USE'] > 0:
        for key in ['alt_diff', 'dst_diff']:
          self.values['integrated'][key][0:-1] = self.values['integrated'][key][1:]
          self.values['integrated'][key][-1] = eval(key+"['USE']")
          #diff_sum[key] = np.mean(self.values['integrated'][key][-self.grade_window_size:])
          diff_sum[key] = np.nansum(self.values['integrated'][key][-self.grade_window_size:])
        #set grade
        gr = gl = self.config.G_ANT_NULLVALUE
        gr = self.config.G_ANT_NULLVALUE
        x = self.config.G_ANT_NULLVALUE
        y = diff_sum['alt_diff']
        if grade_use['ANT+']:
          x = math.sqrt(abs(diff_sum['dst_diff']**2 - diff_sum['alt_diff']**2))
        elif grade_use['GPS']:
          x = diff_sum['dst_diff'] 
        if x > 0:
          #gr = int(round(100 * y / x))
          gr = self.conv_grade(100 * y / x)
        if y != 0.0:
          gl = int(round(-1 * x / y))
        grade = pre_grade = gr
        glide = pre_glide = gl
      #for sometimes ANT+ distance is 0 although status is running
      elif dst_diff['USE'] == 0 and self.config.G_STOPWATCH_STATUS == "START":
        grade = pre_grade
        glide = pre_glide

      #grade (speed base)
      if self.config.G_ANT['USE']['SPD']:
        dst_diff_spd['ANT+'] = spd * self.actual_loop_interval
        for key in ['alt_diff_spd', 'dst_diff_spd']:
          self.values['integrated'][key][0:-1] = self.values['integrated'][key][1:]
          self.values['integrated'][key][-1] = eval(key+"['ANT+']")
          diff_sum[key] = np.mean(self.values['integrated'][key][-self.grade_window_size:])
          #diff_sum[key] = np.nansum(self.values['integrated'][key][-self.grade_window_size:])
        #set grade
        x = diff_sum['dst_diff_spd']**2 - diff_sum['alt_diff_spd']**2
        y = diff_sum['alt_diff_spd']
        gr = self.config.G_ANT_NULLVALUE
        if x > 0:
          x = math.sqrt(x)
          gr = self.conv_grade(100 * y / x)
        grade_spd = pre_grade_spd = gr
      #for sometimes speed sensor value is missing in running
      elif dst_diff_spd['ANT+'] == 0 and self.config.G_STOPWATCH_STATUS == "START":
        grade_spd = pre_grade_spd
      
      self.values['integrated']['hr'] = hr
      self.values['integrated']['speed'] = spd
      self.values['integrated']['cadence'] = cdc
      self.values['integrated']['power'] = pwr
      self.values['integrated']['distance'] += dst_diff['USE']
      self.values['integrated']['accumulated_power'] += ttlwork_diff
      self.values['integrated']['grade'] = grade
      self.values['integrated']['grade_spd'] = grade_spd
      self.values['integrated']['glide_ratio'] = glide
      
      for g in self.graph_keys:
        self.values['integrated'][g][0:-1] = self.values['integrated'][g][1:]
      self.values['integrated']['hr_graph'][-1] = hr
      self.values['integrated']['power_graph'][-1] = pwr
      #self.values['integrated']['altitude_kf_graph'][-1] = v['I2C']['altitude_kalman']
      self.values['integrated']['altitude_kf_graph'][-1] = v['GPS']['alt']
      self.values['integrated']['altitude_graph'][-1] = v['I2C']['altitude']

      time_profile.append(datetime.datetime.now())

      #toggle auto stop
      #ANT+ or GPS speed is avaiable
      if not np.isnan(spd) and self.config.G_MANUAL_STATUS == "START":
        
        #speed from ANT+ or GPS
        flag_spd = False
        if spd >= self.config.G_AUTOSTOP_CUTOFF:
          flag_spd = True
        
        #use moving status of accelerometer because of excluding erroneous speed values when stopping
        flag_moving = False
        if v['I2C']['m_stat'] == 1:
          flag_moving = True
        
        #flag_moving is not considered (set True) as follows,
        # accelerometer is not available (nan)
        # ANT+ speed sensor is available
        if np.isnan(v['I2C']['m_stat']) or self.config.G_ANT['USE']['SPD']:
          flag_moving = True
  
        if self.config.G_STOPWATCH_STATUS == "STOP" \
          and flag_spd and flag_moving \
          and self.config.logger != None:
          self.config.logger.start_and_stop()
        elif self.config.G_STOPWATCH_STATUS == "START" \
          and (not flag_spd or not flag_moving) \
          and self.config.logger != None:
          self.config.logger.start_and_stop()
          
      #ANT+ or GPS speed is not avaiable
      elif np.isnan(spd) and self.config.G_MANUAL_STATUS == "START":
        #stop recording if speed is broken
        if (self.config.G_ANT['USE']['SPD'] or 'timestamp' in v['GPS']) \
          and self.config.G_STOPWATCH_STATUS == "START"  \
          and self.config.logger != None:
          self.config.logger.start_and_stop()
      #self.sensor_ant.device[self.config.G_ANT['ID_TYPE']['LGT']].send_light_setting_flash_low()
      #time.sleep(1)
      
      #auto backlight
      if self.config.G_USE_AUTO_BACKLIGHT:
        if self.config.G_DISPLAY == 'MIP' and self.sensor_spi.send_display and not np.isnan(v['I2C']['light']):
          if v['I2C']['light'] <= self.config.G_USE_AUTO_CUTOFF:
            self.sensor_spi.display.set_brightness(10)
            self.sensor_ant.set_light_mode("FLASH_LOW", auto=True)
          else:
            self.sensor_spi.display.set_brightness(0)
            self.sensor_ant.set_light_mode("OFF", auto=True)

      #cpu and memory
      if _IMPORT_PSUTIL:
        self.values['CPU_MEM'] = "{0:^2.0f}% ({1}) / ALL {2:^2.0f}%,  {3:^2.0f}%".format(
          self.process.cpu_percent(interval=None),
          self.process.num_threads(),
          psutil.cpu_percent(interval=None),
          self.process.memory_percent(),
          )
       
      #adjust loop time
      time_profile.append(datetime.datetime.now())
      sec_diff = []
      time_progile_sec = 0
      for i in range(len(time_profile)):
        if i == 0: continue
        sec_diff.append("{0:.6f}".format((time_profile[i]-time_profile[i-1]).total_seconds()))
        time_progile_sec += (time_profile[i]-time_profile[i-1]).total_seconds()
      if time_progile_sec > 1.5 * self.config.G_SENSOR_INTERVAL:
        print(
          "too long loop time: ",
          datetime.datetime.now().strftime("%Y%m%d %H:%M:%S"),
          ", sec_diff:",
          sec_diff
          )
   
      loop_time = (datetime.datetime.now() - start_time).total_seconds()
      d1, d2 = divmod(loop_time, self.config.G_SENSOR_INTERVAL)
      if d1 > self.config.G_SENSOR_INTERVAL * 10: #[s]
        print(
          "too long loop_time({}):{:.2f}, d1:{:.0f}, d2:{:.2f}".format(
           self.__class__.__name__,
           loop_time,
           d1,
           d2
           ))
        d1 = d2 = 0
      self.wait_time = self.config.G_SENSOR_INTERVAL - d2
      self.actual_loop_interval = (d1 + 1)*self.config.G_SENSOR_INTERVAL

  def conv_grade(self, gr):
    g = gr
    if -1.5 < g < 1.5:
      g = 0
    return int(g)

  def get_lp_filterd_value(self, value, pre):
    o = p = self.config.G_ANT_NULLVALUE
    #value must be initialized with None
    if np.isnan(pre):
      o = value
    else:
      o = pre*(self.lp-1)/self.lp + value/self.lp
    p = value
    return o, p

  #reset accumulated values
  def reset(self):
    self.sensor_gps.reset()
    self.sensor_ant.reset()
    self.sensor_i2c.reset()
    self.values['integrated']['distance'] = 0
    self.values['integrated']['accumulated_power'] = 0


