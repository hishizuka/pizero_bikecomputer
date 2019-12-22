import time
import datetime
import math
import traceback
import numpy as np

from .sensor import Sensor

_SENSOR = {
  'ENVIRO':False, 
  'ENVIRO_LED':False,
  'LSM303D':False,
  'BMP280':False,
  'LPS33HW':False,
  'BUTTON_SHIM':False,
  'NONE':False
  }

#enviro_pHat (without BMP280, LSM303D)
try:
  #from envirophat import light, motion, analog
  from envirophat import light
  #device test
  _SENSOR['ENVIRO'] = True
except:
  pass

#enviro_pHat_led
#try:
#  if SENSOR['ENVIRO']:
#    from envirophat import leds
#    #device test
#    leds.off()
#    SENSOR['ENVIRO_LED'] = True
#except:
#  pass

#LSM303D (acceleration sensor of Enviro pHAT)
try:
  from .i2c.LSM303D import LSM303D
  #device test
  if LSM303D.test():
    _SENSOR['LSM303D'] = True
except:
  pass

#import pressure/temperature sensor

#BMP280
try:
  from .i2c.BMP280 import BMP280
  #device test
  if BMP280.test():
    _SENSOR['BMP280'] = True
except:
  pass

#LPS33HW
try:
  if not _SENSOR['BMP280']:
    from .i2c.LPS33HW import LPS33HW
    #device test
    if LPS33HW.test():
      _SENSOR['LPS33HW'] = True
except:
  pass

#BUTTON_SHIM
try:
  from .i2c.button_shim import ButtonShim
  _SENSOR['BUTTON_SHIM'] = True
except:
  pass


if not _SENSOR['ENVIRO'] and not _SENSOR['LSM303D'] \
  and not _SENSOR['BMP280'] and not _SENSOR['LPS33HW'] and not _SENSOR['BUTTON_SHIM']:
  _SENSOR['NONE'] = True


for key in _SENSOR.keys():
  if key != 'NONE' and _SENSOR[key]:
    print('  I2C(', key, ') : ', _SENSOR[key])
if _SENSOR['NONE']:
  print('  I2C : ', not _SENSOR['NONE'])

#acc
X = 0
Y = 1
Z = 2

#kalman filter
from .kalman_filter import KalmanFilter

class SensorI2C(Sensor):

  sensor = {}
  elements = (
    'temperature', 'pressure', 
    'altitude_raw', 'altitude', 'altitude_LP', 'pre_altitude', 'altitude_kalman',
    'vertical_speed', 
    'light',
    'motion', 'm_stat',
    'heading',
    'voltage_battery', 'voltage_in', 'current_in', 'voltage_out', 'current_out', 
    'capacity_in', 'capacity_out', 'battery_percentage',
  )
  elements_xyz = ('acc', 'acc_lp', 'g_acc')

  graph_values = {}
  graph_keys = ('g_acc', )

  #for acceleration sensor
  acc_lp = 0.9

  #for altitude
  sealevel_pa = 1013.25
  #filter_array = {}
  filter_array = {'LP1':[], 'LP2':[]}
  filter_size = {'LP1':1, 'LP2':1}
  # filter settings equal to bmp280 FILTER in i2c/berryimu.py when filter_size = 1
  # value = (value_n-1 * (FILTER - 1) + raw_data) / FILTER
  # filter_val is (FILTER-1)/FILTER
  #LP1: 4 , LP2: 8
  filter_val = {'LP1':4, 'LP2':8}
  median_array = []
  median_val = None
  median_size = 5
  total_ascent_threshold = 2 #[m]
  spike_threshold = -0.0002 #[rate] 1000hPa: spike is less than -0.3hPa
  pre_timestamp_for_spike = None 

  #for vertical speed
  vspeed_array = []
  vspeed_size = 2 # [s]
  vspeed_bin = 2  # [s]
  timestamp_array = []
  timestamp_size = vspeed_size # [s]

  kf = None
  dt = None

  def sensor_init(self):
    self.reset()
    #barometic pressure & temperature sensor
    if _SENSOR['BMP280']:
      self.sensor['i2c_baro_temp'] = BMP280()
    elif _SENSOR['LPS33HW']:
      self.sensor['i2c_baro_temp'] = LPS33HW()
    #accelerometer & magnetometer sensor
    if _SENSOR['LSM303D']:
      self.sensor['i2c_imu'] = LSM303D()
    #button_shim
    if _SENSOR['BUTTON_SHIM']:
      self.button_shim = ButtonShim(self.config)
    
    self.vspeed_size *= int(1 / self.config.G_I2C_INTERVAL)
    self.vspeed_bin *= int(1 / self.config.G_I2C_INTERVAL)
    self.timestamp_size *= int(1 / self.config.G_I2C_INTERVAL)

  def reset(self):
    for key in self.elements:
      self.values[key] = np.nan
    for key in self.elements_xyz:
      self.values[key] = [0,0,0]
    self.values['total_ascent'] = 0
    self.values['total_descent'] = 0
    self.values['accumulated_altitude'] = 0
    #self.filter_array = {'LP1':[], 'LP2':[]}
    self.graph_values = {}
    for g in self.graph_keys:
      self.graph_values[g] = {}
      for i in range(3):
        self.graph_values[g][i] = [np.nan] * self.config.G_GUI_REALTIME_GRAPH_RANGE
    
    #kalman filter for altitude
    self.dt = self.config.G_I2C_INTERVAL
    self.kf = KalmanFilter(dim_x=2, dim_z=1)
    self.kf.x = np.array([[0], [0]]) 
    self.kf.H = np.array([[1, 0]])
    self.kf.F = np.array([[1, self.dt], [0 ,1]])
    self.kf.P *= 1000.
    self.kf.R = 5
    #self.kf.Q = Q_discrete_white_noise(2, self.dt, .1)
    self.kf.Q = np.array([[.25*self.dt**4, .5*self.dt**3],
                          [ .5*self.dt**3,    self.dt**2]])

  def start(self):
    while(not self.config.G_QUIT):
      time.sleep(self.config.G_I2C_INTERVAL)
      self.update()
    
  def update(self):
    #timestamp
    self.values['timestamp'] = datetime.datetime.now()
    if len(self.timestamp_array) >= self.timestamp_size:
      del(self.timestamp_array[0])
    self.timestamp_array.append(self.values['timestamp'])

    if _SENSOR['NONE']:
      return

    if _SENSOR['BUTTON_SHIM']:
      self.button_shim.set_func()

    if _SENSOR['ENVIRO']:
      try:
        #leds.off()
        self.values['light'] = light.light()
      except:
        traceback.print_exc()
   
    if _SENSOR['LSM303D']:
      self.read_acc()
     
    if _SENSOR['BMP280'] or _SENSOR['LPS33HW']:
      self.read_baro_temp()
     
    self.calc_altitude()

  def read_acc(self):
    try:
      self.sensor['i2c_imu'].read()
    except:
      traceback.print_exc()
    
    self.values['heading'] = self.sensor['i2c_imu'].values['heading']
    self.values['m_stat'] = self.sensor['i2c_imu'].values['moving_status']
   
    acc = [0,0,0]

    for i in range(3):
      self.values['acc'][i] = self.sensor['i2c_imu'].values['acc'][i]
      acc[i] = self.values['acc'][i] - 100
      self.values['acc_lp'][i] = self.acc_lp * self.values['acc_lp'][i] + (1 - self.acc_lp) * acc[i]
      self.values['g_acc'][i] = self.values['acc_lp'][i] + 100
    self.values['motion'] = math.sqrt(
      self.values['g_acc'][0]**2
      + self.values['g_acc'][1]**2
      + self.values['g_acc'][2]**2
      )
    #put into graph
    for g in self.graph_keys:
      for i in range(3):
        del(self.graph_values[g][i][0])
        self.graph_values[g][i].append(self.values['g_acc'][i])

  def read_baro_temp(self):
    try:
      self.sensor['i2c_baro_temp'].read()
    except:
      traceback.print_exc()
    
    self.values['temperature'] = int(self.sensor['i2c_baro_temp'].values['temperature'])
    pressure = self.sensor['i2c_baro_temp'].values['pressure']
    pre_pressure = self.values['pressure']
    self.values['pressure'] = pressure

    #spike detection
    pressure_diff = pressure - pre_pressure
    timestamp_diff = np.nan

    #timestamp_diff
    if self.pre_timestamp_for_spike == None:
      if len(self.timestamp_array) >= 1:
        self.pre_timestamp_for_spike = self.timestamp_array[-1]
    else:
      timestamp_diff = (self.timestamp_array[-1]-self.pre_timestamp_for_spike).total_seconds()
    
    #detect spike
    if not np.isnan(pressure_diff) and not np.isnan(timestamp_diff):
      if pressure_diff <= pre_pressure * self.spike_threshold \
        and timestamp_diff < self.config.G_I2C_INTERVAL*1.5:
        print('detect pressure spike, spike:{:.5f} pre:{:.5f}'.format(pressure, pre_pressure))
        self.values['pressure'] = pre_pressure
      else:
        self.pre_timestamp_for_spike = self.timestamp_array[-1]

  def calc_altitude(self):
    if not np.isnan(self.values['pressure']) and not np.isnan(self.values['temperature']):
      self.values['altitude_raw'] =\
        (pow(self.sealevel_pa / self.values['pressure'], (1.0/5.257)) - 1)\
        * (self.values['temperature'] + 273.15) / 0.0065
    elif not np.isnan(self.values['pressure']):
      self.values['altitude_raw'] =\
        (pow(self.sealevel_pa / self.values['pressure'], (1.0/5.257)) - 1) * 44330.0 #15C
    
    if not np.isnan(self.values['altitude_raw']):
      #median
      if len(self.median_array) > self.median_size:
        del(self.median_array[0])
      self.median_array.append(self.values['altitude_raw'])
      self.median_val = np.median(self.median_array)
      
      #filterd altitude
      self.update_lp('LP1') #use median
      self.update_lp('LP2') #use median
      self.update_kf()

      #for display altitude
      self.values['altitude'] = self.values['altitude_raw']
      # LP1: use 1/4 of altitude_raw, LP2: 1/8 of altitude_raw
      self.values['altitude_LP'] = self.filter_array['LP1'][-1]
      
      #total ascent/descent
      if self.config.G_STOPWATCH_STATUS == "START":
        v = self.filter_array['LP2'][-1]
        if np.isnan(self.values['pre_altitude']):
          self.values['pre_altitude'] = v
        else:
          alt_diff = v - self.values['pre_altitude']
          if abs(alt_diff) > self.total_ascent_threshold:
            if alt_diff > 0: self.values['total_ascent'] += alt_diff
            elif alt_diff < 0: self.values['total_descent'] += -alt_diff
            self.values['accumulated_altitude'] += alt_diff
            self.values['pre_altitude'] = v

      #vertical speed (m/s)
      if len(self.vspeed_array) >= self.vspeed_size:
        del(self.vspeed_array[0])
      self.vspeed_array.append(self.values['altitude_raw'])
      if len(self.timestamp_array) >= self.vspeed_bin:
        i = -self.vspeed_bin
        time_delta = (self.timestamp_array[-1] - self.timestamp_array[i]).total_seconds()
        if time_delta > 0:
          altitude_delta = self.vspeed_array[-1] - self.vspeed_array[i]
          self.values['vertical_speed'] = altitude_delta/ time_delta
          
  def calibrate_position(self):
    if _SENSOR['LSM303D']:
      self.sensor['i2c_imu'].calibrate_position()

  def update_sealevel_pa(self, alt):
    if _SENSOR['NONE']:
      return
    if np.isnan(self.values['pressure']) or np.isnan(self.values['temperature']):
      return
    pre = self.values['pressure']
    temp = self.values['temperature'] + 273.15
    self.sealevel_pa = pre * pow(temp / (temp + 0.0065*alt), (-5.257))
    print('altitude:', alt, 'm')
    print('pressure:', pre, 'hPa')
    print('temp:', temp, 'C')
    print('adjust sealevel_pa:', self.sealevel_pa, 'hPa')
 
  def update_lp(self, key):
    value = self.median_val 
    #LP + Median
    if len(self.filter_array[key]) > 0:
      value = 1/self.filter_val[key] * value\
        + (self.filter_val[key]-1)/self.filter_val[key] * self.filter_array[key][-1]
      
    if len(self.filter_array[key]) >= self.filter_size[key]:
      del(self.filter_array[key][0])
    #filter value
    self.filter_array[key].append(value)

  def update_kf(self):
    self.kf.predict()
    self.kf.update(self.values['altitude_raw'])
    self.values['altitude_kalman'] = self.kf.x[0][0]




