import datetime
import math
import traceback

import numpy as np

from .sensor import Sensor

#I2C
_SENSOR_I2C = False
try:
  import smbus
  _SENSOR_I2C = True
except:
  pass
print('  I2C : ',_SENSOR_I2C)

#acc
X = 0
Y = 1
Z = 2

G = 9.80665

#kalman filter
from .kalman_filter import KalmanFilter


class SensorI2C(Sensor):

  sensor = {}
  available_sensors = {
    'PRESSURE': {},
    'MOTION': {}, #includes acc, gyro and mag
    'LIGHT': {},
    'BUTTON': {},
    'BATTERY': {},
    }
  motion_sensor = {
    'ACC': False,
    'GYRO': False,
    'MAG': False,
    }
  elements = (
    'temperature', 'pressure_raw', 'pressure_mod', 'pressure', 
    'altitude', 'pre_altitude', 'altitude_kalman', 'vertical_speed', 
    'light',
    'pitch', 'roll', 'yaw', 'pitch_fixed', 'roll_fixed', 
    'heading', 'heading_str', 'motion', 'm_stat', 
    'voltage_battery', 'current_battery', 'voltage_out', 'current_out', 'battery_percentage',
  )
  elements_vec = (
    'acc_raw', 'acc_mod','acc', 
    'gyro_raw', 'gyro_mod','gyro', 
    'mag_raw', 'mag_mod', 'mag'
    )

  values_mod = {}
  elements_vec_mod = ('mag_min', 'mag_max', 'mag_ave')
  
  #for graph
  graph_values = {}
  graph_keys = ('g_acc', )

  #for LP filter
  pre_value = {}
  #for median filter and hampel filter(outlier=spike detection)
  median_keys = ['pressure_mod']
  pre_values_array = {}
  median_val = {}
  pre_value_window_size = 10

  #constants
  #for moving detection
  moving_threshold = 0.001
  #for altitude
  sealevel_pa = 1013.25
  total_ascent_threshold = 2 #[m]

  #for vertical speed
  vspeed_array = []
  vspeed_window_size = 2 # [s]
  timestamp_array = []
  timestamp_size = vspeed_window_size # [s]

  #for kalman filter
  kf = None
  dt = None

  def sensor_init(self):
    self.detect_sensors()
    
    #barometic pressure & temperature sensor
    if self.available_sensors['PRESSURE']['BMP280']:
      self.sensor['i2c_baro_temp'] = self.sensor_bmp280
    elif self.available_sensors['PRESSURE']['BMP280_ORIG']:
      self.sensor['i2c_baro_temp'] = self.sensor_bmp280
    elif self.available_sensors['PRESSURE']['LPS3XHW']:
      self.sensor['i2c_baro_temp'] = self.sensor_lps35hw
    elif self.available_sensors['PRESSURE']['LPS3XHW_ORIG']:
      self.sensor['i2c_baro_temp'] = self.sensor_lps33hw
    elif self.available_sensors['PRESSURE']['BMP3XX']:
      self.sensor['i2c_baro_temp'] = self.sensor_bmp3xx

    #accelerometer & magnetometer sensor
    #acc + mag
    if self.available_sensors['MOTION']['LSM303_ORIG']:
      self.sensor['i2c_imu'] = self.sensor_lsm303
    #acc + gyro
    if self.available_sensors['MOTION']['LSM6DS']:
      self.sensor['i2c_imu'] = self.sensor_lsm6ds
    #mag
    if self.available_sensors['MOTION']['LIS3MDL']:
      self.sensor['i2c_mag'] = self.sensor_lis3mdl
    #acc + gyro + mag
    if self.available_sensors['MOTION']['BMX160']:
      self.sensor['i2c_imu'] = self.sensor_bmx160
    #acc + gyro + mag
    if self.available_sensors['MOTION']['LSM9DS1']:
      self.sensor['i2c_imu'] = self.sensor_lsm9ds1
    
    #light sensor
    if self.available_sensors['LIGHT']['TCS3472']:
      self.sensor['lux'] = self.sensor_tcs3472
    elif self.available_sensors['LIGHT']['VCNL4040']:
      self.sensor['lux'] = self.sensor_vcnl4040

    self.reset()

  def detect_sensors(self):
    
    #pressure sensors
    self.available_sensors['PRESSURE']['LPS3XHW'] = self.detect_pressure_lps3xhw()
    if not self.available_sensors['PRESSURE']['LPS3XHW']:
      self.available_sensors['PRESSURE']['LPS3XHW_ORIG'] = self.detect_pressure_lps3xhw_orig()
    self.available_sensors['PRESSURE']['BMP280'] = self.detect_pressure_bmp280()
    if not self.available_sensors['PRESSURE']['BMP280']:
      self.available_sensors['PRESSURE']['BMP280_ORIG'] = self.detect_pressure_bmp280_orig()
    self.available_sensors['PRESSURE']['BMP3XX'] = self.detect_pressure_bmp3xx()
    
    #motion sensors
    self.available_sensors['MOTION']['LSM303_ORIG'] = self.detect_motion_lsm303_orig()
    self.available_sensors['MOTION']['LIS3MDL'] = self.detect_motion_lis3mdl()
    self.available_sensors['MOTION']['LSM6DS'] = self.detect_motion_lsm6ds()
    self.available_sensors['MOTION']['LSM9DS1'] = self.detect_motion_lsm9ds1()
    self.available_sensors['MOTION']['BMX160'] = self.detect_motion_bmx160()
    if self.available_sensors['MOTION']['LSM303_ORIG']:
      self.motion_sensor['ACC'] = True
      self.motion_sensor['MAG'] = True
    if self.available_sensors['MOTION']['LIS3MDL']:
      self.motion_sensor['MAG'] = True
    if self.available_sensors['MOTION']['LSM6DS']:
      self.motion_sensor['ACC'] = True
      self.motion_sensor['GYRO'] = True
    if self.available_sensors['MOTION']['LSM9DS1']:
      self.motion_sensor['ACC'] = True
      self.motion_sensor['GYRO'] = True
      self.motion_sensor['MAG'] = True
    if self.available_sensors['MOTION']['BMX160']:
      self.motion_sensor['ACC'] = True
      self.motion_sensor['GYRO'] = True
      self.motion_sensor['MAG'] = True

    #light sensors
    self.available_sensors['LIGHT']['TCS3472'] = self.detect_light_tcs3472()
    self.available_sensors['LIGHT']['VCNL4040'] = self.detect_light_vncl4040()

    #button
    self.available_sensors['BUTTON']['BUTTON_SHIM'] = self.detect_button_button_shim()
    
    #battery
    self.available_sensors['BATTERY']['PIJUICE'] = self.detect_battery_pijuice()
    
    #print
    print("  detected I2c sensors:")
    for k in self.available_sensors.keys():
      for kk in self.available_sensors[k]:
        if self.available_sensors[k][kk]:
          print("    {}: {}".format(k, kk))

  def reset(self):
    for key in self.elements:
      self.values[key] = np.nan
    for key in self.elements_vec:
      self.values[key] = np.zeros(3)
    #for LP filter
    for key in self.elements:
      self.pre_value[key] = np.nan
    for key in self.elements_vec:
      self.pre_value[key] = np.full(3, np.nan)
    #for median filter
    for key in self.median_keys:
      self.pre_values_array[key] = np.full(self.pre_value_window_size, np.nan)

    #for temporary values
    for key in self.elements_vec_mod:
      self.values_mod[key] = np.zeros(3)
    self.values_mod['mag_min'] = np.full(3, np.inf)
    self.values_mod['mag_max'] = np.full(3, -np.inf)
    self.mag_average_array = np.zeros((3, int(2/self.config.G_I2C_INTERVAL)+1))

    self.values['total_ascent'] = 0
    self.values['total_descent'] = 0
    self.values['accumulated_altitude'] = 0

    self.values['pitch_fixed'] = 0
    self.values['roll_fixed'] = 0

    self.graph_values = {}
    for g in self.graph_keys:
      self.graph_values[g] = np.full((3, self.config.G_GUI_REALTIME_GRAPH_RANGE), np.nan)
   
    #for moving status
    self.mov_window_size = int(2/self.config.G_I2C_INTERVAL)+1
    self.acc_variance_array = np.zeros((3, self.mov_window_size))
    self.acc_variance = np.zeros(3)
    self.moving = np.ones(self.mov_window_size)
    self.do_position_calibration = True

    self.vspeed_window_size *= int(1 / self.config.G_I2C_INTERVAL)
    self.timestamp_size *= int(1 / self.config.G_I2C_INTERVAL)
    self.timestamp_array = [None] * self.timestamp_size
    self.vspeed_array = [np.nan] * self.vspeed_window_size

    #kalman filter for altitude
    self.dt = self.config.G_I2C_INTERVAL
    self.kf = KalmanFilter(dim_x=2, dim_z=1)
    self.kf.x = np.array([[0], [0]]) 
    self.kf.H = np.array([[1, 0]])
    self.kf.F = np.array([[1, self.dt], [0 ,1]])
    self.kf.P *= 1000.
    self.kf.R = 5
    #self.kf.Q = Q_discrete_white_noise(2, self.dt, .1)
    self.kf.Q = np.array(
      [[.25*self.dt**4, .5*self.dt**3],
       [ .5*self.dt**3,    self.dt**2]])

  def start(self):
    while(not self.config.G_QUIT):
      self.sleep()
      self.update()
      self.get_sleep_time(self.config.G_I2C_INTERVAL)
    
  def update(self):
    #timestamp
    self.values['timestamp'] = datetime.datetime.now()
    self.timestamp_array[0:-1] = self.timestamp_array[1:]
    self.timestamp_array[-1] = self.values['timestamp']

    if self.available_sensors['BUTTON']['BUTTON_SHIM']:
      self.sensor_button_shim.set_func()

    if self.available_sensors['BATTERY']['PIJUICE']:
      bv = self.sensor_pijuice.status.GetBatteryVoltage()
      bc = self.sensor_pijuice.status.GetBatteryCurrent()
      iv = self.sensor_pijuice.status.GetIoVoltage()
      ic = self.sensor_pijuice.status.GetIoCurrent()
      bl = self.sensor_pijuice.status.GetChargeLevel()
      if bv['error'] == 'NO_ERROR':
        self.values['voltage_battery'] = bv['data']/1000
      if bc['error'] == 'NO_ERROR':
        self.values['current_battery'] = bc['data']/1000
      if iv['error'] == 'NO_ERROR':
        self.values['voltage_out'] = iv['data']/1000
      if ic['error'] == 'NO_ERROR':
        self.values['current_out'] = ic['data']/1000
      if bl['error'] == 'NO_ERROR':
        self.values['battery_percentage'] = bl['data']

    self.read_lux()

    self.read_acc()
    self.read_gyro()
    self.read_mag()
    self.calc_motion()
     
    self.read_baro_temp()
    self.calc_altitude()

  def read_lux(self):
    try:
      if self.available_sensors['LIGHT']['TCS3472']:
        self.values['light'] = self.sensor['lux'].light()
      elif self.available_sensors['LIGHT']['VCNL4040']:
        self.values['light'] = self.sensor['lux'].lux
    except:
      return

  #X: to North (up rotation is plus)
  #Y: to West (up rotation is plus)
  #Z: to down (plus)
  def change_axis(self, a):
    #X, Y, Zinversion
    if self.config.G_IMU_AXIS_CONVERSION['STATUS']:
      a = a * self.config.G_IMU_AXIS_CONVERSION['COEF']
    #X-Y swap
    if self.config.G_IMU_AXIS_SWAP_XY['STATUS']:
      #a[1::-1] = a[0:2] * self.config.G_IMU_AXIS_SWAP_XY['COEF']
      a[0:2] = a[1::-1] * self.config.G_IMU_AXIS_SWAP_XY['COEF']
    return a

  def read_acc(self):
    if not self.motion_sensor['ACC']:
      return
    try:
      #get raw acc (normalized by gravitational acceleration, g = 9.80665)
      if self.available_sensors['MOTION']['LSM303_ORIG']:
        self.sensor['i2c_imu'].read_acc()
        self.values['acc_raw'] = np.array(self.sensor['i2c_imu'].values['acc'])
      elif self.available_sensors['MOTION']['LSM6DS']:
        self.values['acc_raw'] = np.array(self.sensor['i2c_imu'].acceleration)/G
      elif self.available_sensors['MOTION']['LSM9DS1']:
        self.values['acc_raw'] = np.array(list(self.sensor['i2c_imu'].acceleration))/G
      elif self.available_sensors['MOTION']['BMX160']:
        self.values['acc_raw'] = np.array(self.sensor['i2c_imu'].accel)/G
    except:
      return
    self.values['acc_raw'] = self.change_axis(self.values['acc_raw'])

    self.values['acc_mod'] = self.values['acc_raw']
    #LP filter
    self.lp_filter('acc_mod', 4)

  def read_gyro(self):
    if not self.motion_sensor['GYRO']:
      return
    try:
      if self.available_sensors['MOTION']['LSM6DS'] or self.available_sensors['MOTION']['BMX160']:
        self.values['gyro_raw'] = np.array(self.sensor['i2c_imu'].gyro)
      elif self.available_sensors['MOTION']['LSM9DS1']:
        self.values['gyro_raw'] = np.array(list(self.sensor['i2c_imu'].gyro))
    except:
      return
    self.values['gyro_raw'] = self.change_axis(self.values['gyro_raw'])
    
    #calibration
    self.mag_average_array[:, 0:-1] = self.mag_average_array[:, 1:]
    self.mag_average_array[:, -1] = self.values['gyro_raw']
    if self.do_position_calibration:
      self.values_mod['mag_ave'] = np.nanmean(self.mag_average_array, axis=1)
    self.values['gyro_mod'] = self.values['gyro_raw'] - self.values_mod['mag_ave']

    #LP filter
    self.lp_filter('gyro_mod', 4)

    #finalize gyro
    self.values['gyro'] = self.values['gyro_mod']

  def read_mag(self):
    if not self.motion_sensor['MAG']:
      return
    try:
      if self.available_sensors['MOTION']['LSM303_ORIG']:
        self.sensor['i2c_imu'].read_mag()
        self.values['mag_raw'] = np.array(self.sensor['i2c_imu'].values['mag'])
      elif self.available_sensors['MOTION']['LIS3MDL']:
        self.values['mag_raw'] = np.array(self.sensor['i2c_mag'].magnetic)
      elif self.available_sensors['MOTION']['LSM9DS1']:
        self.values['mag_raw'] = np.array(list(self.sensor['i2c_imu'].magnetic))
      elif self.available_sensors['MOTION']['BMX160']:
        self.values['mag_raw'] = np.array(self.sensor['i2c_imu'].mag)
    except:
      return
    self.values['mag_raw'] = self.change_axis(self.values['mag_raw'])
    
    self.values['mag_mod'] = self.values['mag_raw']
    #calibration(hard/soft iron distortion)
    self.values_mod['mag_min'] = np.minimum(self.values['mag_mod'], self.values_mod['mag_min'])
    self.values_mod['mag_max'] = np.maximum(self.values['mag_mod'], self.values_mod['mag_max'])
    #hard iron distortion
    self.values['mag_mod'] = self.values['mag_mod'] - (self.values_mod['mag_min'] + self.values_mod['mag_max'])/2
    #soft iron distortion
    avg_delta = (self.values_mod['mag_max'] - self.values_mod['mag_min'])/2
    avg_delta_all = np.sum(avg_delta)/3
    if not np.any(avg_delta == 0):
      scale = avg_delta_all / avg_delta
      self.values['mag_mod'] = self.values['mag_mod']*scale
    
    #LP filter
    self.lp_filter('mag_mod', 4)
      
    #finalize mag
    self.values['mag'] = self.values['mag_mod']

  def calc_motion(self):
    
    #get pitch, roll and yaw into self.values
    self.get_pitch_roll_yaw()

    #detect start/stop status and position(pitch_fixed, roll_fixed)
    self.detect_motion()

    #calc acc based on pitch_fixed and roll_fixed
    self.modified_acc()

  def get_pitch_roll_yaw(self):
    #require acc and mag
    if not self.motion_sensor['ACC'] or not self.motion_sensor['MAG']:
      return
    if np.any(np.isnan(self.motion_sensor['ACC'])) or np.any(np.isnan(self.motion_sensor['MAG'])):
      return

    self.values['pitch'], self.values['roll'] = self.get_pitch_roll(self.values['acc_mod'])
    self.values['yaw'] = self.get_yaw(self.values['mag'], self.values['pitch'], self.values['roll'])

    if np.isnan(self.values['yaw']):
      return

    tilt_heading = self.values['yaw']
    if tilt_heading < 0:
      tilt_heading += 2*math.pi
    if tilt_heading > 2*math.pi:
      tilt_heading -= 2*math.pi
    
    #set heading with yaw
    self.values['heading'] = int(math.degrees(tilt_heading))
    self.values['heading_str'] = self.config.get_track_str(self.values['heading'])
  
  def get_pitch_roll(self, acc):
    roll = math.atan2(acc[1], acc[2])
    pitch = math.atan2(-acc[0], (math.sqrt(acc[1]**2+acc[2]**2)))
    
    return pitch, roll

  def get_yaw(self, mag, pitch, roll):
    cos_p = math.cos(pitch)
    sin_p = math.sin(pitch)
    cos_r = math.cos(roll)
    sin_r = math.sin(roll)
    tiltcomp_x = mag[X]*cos_p + mag[Z]*sin_p
    tiltcomp_y = mag[X]*sin_r*sin_p + mag[Y]*cos_r - mag[Z]*sin_r*cos_p
    tiltcomp_z = mag[X]*cos_r*sin_p + mag[Y]*sin_r + mag[Z]*cos_r*cos_p
    yaw = math.atan2(tiltcomp_y, tiltcomp_x)
    
    return yaw

  def detect_motion(self):
    #require acc
    if not self.motion_sensor['ACC']:
      return
    self.acc_variance_array[:, 0:-1] = self.acc_variance_array[:, 1:]
    self.acc_variance_array[:, -1] = self.values['acc_raw']
    self.acc_variance = np.var(self.acc_variance_array, axis=1)
    moving = 0
    if np.all(self.acc_variance > self.moving_threshold):
      moving = 1
    self.moving[0:-1] = self.moving[1:]
    self.moving[-1] = moving
    #moving status (0:off=stop, 1:on=running)
    self.values['m_stat'] = self.moving[-1]
    
    #calibrate position
    if not self.do_position_calibration or sum(self.moving) != 0:
      return
    pitch, roll = self.get_pitch_roll([
      np.average(self.acc_variance_array[0]),
      np.average(self.acc_variance_array[1]),
      np.average(self.acc_variance_array[2])
      ])
    if pitch != None and roll != None:
      self.values['pitch_fixed'] = pitch
      self.values['roll_fixed'] = roll
      self.do_position_calibration = False
      print("calibrated position")
    #calibrate mag
    
  def modified_acc(self):
    #require acc
    if not self.motion_sensor['ACC']:
      return
    cos_p = math.cos(self.values['pitch_fixed'])
    sin_p = math.sin(self.values['pitch_fixed'])
    cos_r = math.cos(self.values['roll_fixed'])
    sin_r = math.sin(self.values['roll_fixed'])
    #cos_y = math.cos(self.values['yaw_fixed'])
    #sin_y = math.sin(self.values['yaw_fixed'])
    m_pitch = np.array([[cos_p,0,sin_p],[0,1,0],[-sin_p,0,cos_p]])
    m_roll  = np.array([[1,0,0],[0,cos_r,-sin_r],[0,sin_r,cos_r]])
    #m_yaw   = np.array([[cos_y,-sin_y,0],[sin_y,cos_y,0],[0,0,1]])
    #m_acc   = np.array([[ax],[ay],[az]])
    m_acc   = np.array(self.values['acc_mod']).reshape(3,1)
    
    m_acc_mod = m_roll@m_pitch@m_acc
    #m_acc_mod = m_yaw@m_roll@m_pitch@m_acc

    #finalize acc
    self.values['acc'] = m_acc_mod.reshape(3).tolist()
    #remove gravity (converted acceleration - gravity)
    self.values['acc'][Z] -= 1.0

    #position quaternion
    #cosRoll = math.cos(roll*0.5)
    #sinRoll = math.sin(roll*0.5)
    #cosPitch = math.cos(pitch*0.5)
    #sinPitch = math.sin(pitch*0.5)
    #cosYaw = math.cos(yaw*0.5)
    #sinYaw = math.sin(yaw*0.5)
    #q0 = cosRoll * cosPitch * cosYaw + sinRoll * sinPitch * sinYaw
    #q1 = sinRoll * cosPitch * cosYaw - cosRoll * sinPitch * sinYaw
    #q2 = cosRoll * sinPitch * cosYaw + sinRoll * cosPitch * sinYaw
    #q3 = cosRoll * cosPitch * sinYaw - sinRoll * sinPitch * cosYaw

    #convert acceleration to earth coordinates
    #self.values['acc'][X] = (q0**2+q1**2-q2**2-q3**2)*ax + 2*(q1*q2-q0*q3)*ay + 2*(q0*q2+q1*q3)*az
    #self.values['acc'][Y] = 2*(q0*q3+q1*q2)*ax + (q0**2-q1**2+q2**2-q3**2)*ay + 2*(q2*q3-q0*q1)*az
    #self.values['acc'][Z] = 2*(q1*q3-q0*q2)*ax + 2*(q0*q1+q2*q3)*ay + (q0**2-q1**2-q2**2+q3**2)*az

    #modify acc
    acc = [0,0,0]
    self.values['motion'] = math.sqrt(sum(list(map(lambda x: x**2, self.values['acc']))))
    #put into graph
    for g in self.graph_keys:
      self.graph_values[g][:, 0:-1] = self.graph_values[g][:, 1:]
      self.graph_values[g][:, -1] = self.values['acc']
    
  def recalibrate_position(self):
    self.do_position_calibration = True

  def read_baro_temp(self):
    if not any(self.available_sensors['PRESSURE'].values()):
      return

    sp = self.available_sensors['PRESSURE']

    try:
      if ('LPS3XHW_ORIG' in sp and sp['LPS3XHW_ORIG']) \
        or ('BMP280_ORIG' in sp and sp['BMP280_ORIG']):
        self.sensor['i2c_baro_temp'].read()
      self.values['temperature'] = int(self.sensor['i2c_baro_temp'].temperature)
      self.values['pressure_raw'] = self.sensor['i2c_baro_temp'].pressure
    except:
      return
  
    self.values['pressure_mod'] = self.values['pressure_raw']

    #spike detection
    self.median_filter('pressure_mod')
    #outlier(spike) detection
    #sigma is not 3 but 10 for detecting pressure diff 0.3hPa around 1000hPa
    self.hampel_filter('pressure_mod', sigma=10)
    
    #LP filter
    #self.lp_filter('pressure_mod', 8)

    #finalize
    self.values['pressure'] = self.values['pressure_mod']

  def calc_altitude(self):
    if np.isnan(self.values['pressure']):
      return
    
    if not np.isnan(self.values['temperature']):
      self.values['altitude'] = \
        (pow(self.sealevel_pa / self.values['pressure'], (1.0/5.257)) - 1)\
        * (self.values['temperature'] + 273.15) / 0.0065
    else:
      self.values['altitude'] = \
        (pow(self.sealevel_pa / self.values['pressure'], (1.0/5.257)) - 1) * 44330.0 #assume as 15C

    #filterd altitude
    self.update_kf()
    
    if self.config.G_STOPWATCH_STATUS == "START":
      #total ascent/descent
      v = self.values['altitude']
      if np.isnan(self.values['pre_altitude']) and not np.isnan(v):
        self.values['pre_altitude'] = v
      else:
        alt_diff = v - self.values['pre_altitude']
        if abs(alt_diff) > self.total_ascent_threshold:
          if alt_diff > 0: self.values['total_ascent'] += alt_diff
          elif alt_diff < 0: self.values['total_descent'] += -alt_diff
          self.values['accumulated_altitude'] += alt_diff
          self.values['pre_altitude'] = v

      #vertical speed (m/s)
      self.vspeed_array[0:-1] = self.vspeed_array[1:]
      self.vspeed_array[-1] = self.values['altitude']
      if self.timestamp_array[0] != None and self.timestamp_array[-1] != None:
        i = 0
        time_delta = (self.timestamp_array[-1] - self.timestamp_array[i]).total_seconds()
        if time_delta > 0:
          altitude_delta = self.vspeed_array[-1] - self.vspeed_array[i]
          self.values['vertical_speed'] = altitude_delta/ time_delta

  def update_sealevel_pa(self, alt):
    if np.isnan(self.values['pressure']) or np.isnan(self.values['temperature']):
      return
    pre = self.values['pressure']
    temp = self.values['temperature'] + 273.15
    self.sealevel_pa = pre * pow(temp / (temp + 0.0065*alt), (-5.257))
    print('update sealevel pressure')
    print('altitude:', alt, 'm')
    print('pressure:', pre, 'hPa')
    print('temp:', temp, 'C')
    print('sealevel pressure:', self.sealevel_pa, 'hPa')
 
  def lp_filter(self, key, filter_val):
    if key not in self.values:
      return
    if not np.any(np.isnan(self.pre_value[key])):
      self.values[key] = (self.values[key] + (filter_val-1)*self.pre_value[key])/filter_val
    self.pre_value[key] = self.values[key]
    
  def median_filter(self, key):
    if key not in self.median_keys:
      return
    self.pre_values_array[key][0:-1] = self.pre_values_array[key][1:]
    self.pre_values_array[key][-1] = self.values[key]
    self.median_val[key] = np.nanmedian(self.pre_values_array[key])

  def hampel_filter(self, key, sigma=3):
    if key not in self.median_keys:
      return
    hampel_std = 1.4826 * np.nanmedian(np.abs(self.pre_values_array[key] - self.median_val[key]))
    if np.isnan(hampel_std):
      return
    if (np.abs(self.values[key] - self.median_val[key]) > sigma * hampel_std):
      print('detect pressure spike, spike:{:.5f} diff:{:.5f}, median:{:.5f}'.format(self.values[key], np.abs(self.values[key] - self.median_val[key]), self.median_val[key]))
      self.values[key] = self.median_val[key]

  def update_kf(self):
    self.kf.predict()
    self.kf.update(self.values['altitude'])
    self.values['altitude_kalman'] = self.kf.x[0][0]

  def detect_pressure_bmp280(self):
    try:
      import board
      import busio
      import adafruit_bmp280
      i2c = busio.I2C(board.SCL, board.SDA)
      #device test
      self.sensor_bmp280 = adafruit_bmp280.Adafruit_BMP280_I2C(i2c)
      self.sensor_bmp280.mode = adafruit_bmp280.MODE_NORMAL
      self.sensor_bmp280.standby_period = adafruit_bmp280.STANDBY_TC_250
      self.sensor_bmp280.iir_filter = adafruit_bmp280.IIR_FILTER_X16
      self.sensor_bmp280.overscan_pressure = adafruit_bmp280.OVERSCAN_X16
      self.sensor_bmp280.overscan_temperature = adafruit_bmp280.OVERSCAN_X1
      return True
    except:
      return False

  def detect_pressure_bmp280_orig(self):
    try:
      from .i2c.BMP280 import BMP280
      #device test
      if not BMP280.test():
        return False
      self.sensor_bmp280 = BMP280()
      return True
    except:
      return False

  def detect_pressure_lps3xhw(self):
    try:
      import board
      import adafruit_lps35hw
      #device test
      self.sensor_lps35hw = adafruit_lps35hw.LPS35HW(board.I2C())
      #self.sensor_lps35hw.low_pass_enabled = True
      return True
    except:
      return False
  
  def detect_pressure_lps3xhw_orig(self):
    try:
      from .i2c.LPS33HW import LPS33HW
      if not LPS33HW.test():
        return False
      self.sensor_lps33hw = LPS33HW()
      return True
    except:
      return False
 
  def detect_pressure_bmp3xx(self):
    try:
      import board
      import busio
      import adafruit_bmp3xx
      i2c = busio.I2C(board.SCL, board.SDA)
      #device test
      self.sensor_bmp3xx = adafruit_bmp3xx.BMP3XX_I2C(i2c, address=0x76)
      self.sensor_bmp3xx.filter_coefficient = 16
      self.sensor_bmp3xx.pressure_oversampling = 16
      self.sensor_bmp3xx.temperature_oversampling = 1
      return True
    except:
      return False
 
  def detect_motion_lsm6ds(self):
    try:
      import board
      import busio
      import adafruit_lsm6ds
      self.sensor_lsm6ds = adafruit_lsm6ds.LSM6DS33(busio.I2C(board.SCL, board.SDA))
      return True
    except:
      return False

  def detect_motion_lis3mdl(self):
    try:
      import board
      import busio
      import adafruit_lis3mdl
      self.sensor_lis3mdl = adafruit_lis3mdl.LIS3MDL(busio.I2C(board.SCL, board.SDA))
      return True
    except:
      return False

  def detect_motion_lsm303_orig(self):
    try:
      from .i2c.LSM303D import LSM303D
      #device test
      if not LSM303D.test():
        return False
      self.sensor_lsm303 = LSM303D()
      return True
    except:
      return False

  def detect_motion_lsm9ds1(self):
    try:
      import board
      import busio
      import adafruit_lsm9ds1
      self.sensor_lsm9ds1 = adafruit_lsm9ds1.LSM9DS1_I2C(busio.I2C(board.SCL, board.SDA))
      return True
    except:
      return False

  def detect_motion_bmx160(self):
    try:
      import board
      import busio
      import BMX160
      self.sensor_bmx160 = BMX160.BMX160_I2C(busio.I2C(board.SCL, board.SDA))
      return True
    except:
      return False
  
  def detect_light_tcs3472(self):
    try:
      from envirophat import light
      light.light()
      self.sensor_tcs3472 = light
      #device test
      return True
    except:
      return False

  def detect_light_vncl4040(self):
    try:
      import board
      import busio
      import adafruit_vcnl4040
      self.sensor_vcnl4040 = adafruit_vcnl4040.VCNL4040(busio.I2C(board.SCL, board.SDA))
      self.sensor_vcnl4040.proximity_shutdown = True
      #device test
      return True
    except:
      return False

  def detect_button_button_shim(self):
    try:
      from .i2c.button_shim import ButtonShim
      #device test
      self.sensor_button_shim = ButtonShim(self.config)
      return True
    except:
      return False
 
  def detect_battery_pijuice(self):
    try:
      from pijuice import PiJuice
      #device test
      self.sensor_pijuice = PiJuice(1, 0x14)
      res = sensor_pijuice.status.GetStatus()
      if res['error'] == 'COMMUNICATION_ERROR':
        return False
      return True
    except:
      return False
 

