import time
import smbus
import struct

import math
import numpy as np

try:
  #run from top directory (pizero_bikecomputer)
  from . import i2c
except:
  #directly run this program
  import i2c

# Todo:
#  coordinate swap and inversion from mounting
#   typically, Y <-> X, X, Y, Z
#  why acc is 1G

# https://www.pololu.com/file/0J703/LSM303D.pdf
# https://www.pololu.com/file/0J434/LSM303DLH-compass-app-note.pdf

### LSM303 Register definitions ###
TEMP_OUT_L      = 0x05
TEMP_OUT_H      = 0x06
STATUS_REG_M    = 0x07
OUT_X_L_M       = 0x08
OUT_X_H_M       = 0x09
OUT_Y_L_M       = 0x0A
OUT_Y_H_M       = 0x0B
OUT_Z_L_M       = 0x0C
OUT_Z_H_M       = 0x0D
WHO_AM_I        = 0x0F
INT_CTRL_M      = 0x12
INT_SRC_M       = 0x13
INT_THS_L_M     = 0x14
INT_THS_H_M     = 0x15
OFFSET_X_L_M    = 0x16
OFFSET_X_H_M    = 0x17
OFFSET_Y_L_M    = 0x18
OFFSET_Y_H_M    = 0x19
OFFSET_Z_L_M    = 0x1A
OFFSET_Z_H_M    = 0x1B
REFERENCE_X     = 0x1C
REFERENCE_Y     = 0x1D
REFERENCE_Z     = 0x1E
CTRL_REG0       = 0x1F
CTRL_REG1       = 0x20
CTRL_REG2       = 0x21
CTRL_REG3       = 0x22
CTRL_REG4       = 0x23
CTRL_REG5       = 0x24
CTRL_REG6       = 0x25
CTRL_REG7       = 0x26
STATUS_REG_A    = 0x27
OUT_X_L_A       = 0x28
OUT_X_H_A       = 0x29
OUT_Y_L_A       = 0x2A
OUT_Y_H_A       = 0x2B
OUT_Z_L_A       = 0x2C
OUT_Z_H_A       = 0x2D
FIFO_CTRL       = 0x2E
FIFO_SRC        = 0x2F
IG_CFG1         = 0x30
IG_SRC1         = 0x31
IG_THS1         = 0x32
IG_DUR1         = 0x33
IG_CFG2         = 0x34
IG_SRC2         = 0x35
IG_THS2         = 0x36
IG_DUR2         = 0x37
CLICK_CFG       = 0x38
CLICK_SRC       = 0x39
CLICK_THS       = 0x3A
TIME_LIMIT      = 0x3B
TIME_LATENCY    = 0x3C
TIME_WINDOW     = 0x3D
ACT_THS         = 0x3E
ACT_DUR         = 0x3F

### Mag scales ###
MAG_SCALE_2     = 0x00 # full-scale is +/- 2 Gauss
MAG_SCALE_4     = 0x20 # +/- 4 Guass
MAG_SCALE_8     = 0x40 # +/- 8 Guass
MAG_SCALE_12    = 0x60 # +/- 12 Guass

ACCEL_SCALE     = 2 # +/- 2g

X = 0
Y = 1
Z = 2


class LSM303D(i2c.i2c):

  #address
  SENSOR_ADDRESS = 0x1D # Assuming SA0 grounded

  #for reset
  # BOOT (0: normal mode; 1: reboot memory content)
  # FIFO (0: disable; 1: enable)
  # FIFO programmable threshold (0: disable; 1: enable)
  # 0 (fixed)
  # 0 (fixed)
  # High-pass filter for click function (0: disable; 1: enable)
  # High-pass filter for interrupt generator 1 (0: disable; 1: enable)
  # High-pass filter for interrupt generator 2 (0: disable; 1: enable)
  RESET_ADDRESS = 0x1F
  RESET_VALUE = 0x00 #or 0b10000000

  #for reading value
  #VALUE_ADDRESS = 0xF7
  #VALUE_BYTES = 6

  #for test
  TEST_ADDRESS = 0x0F
  TEST_VALUE = 0x49
  
  elements = (
    'heading', 'heading_raw', 
    'pitch', 'roll', 'yaw', 
    'pitch_fixed', 'roll_fixed', 
    'grade', 'moving_status',
    )
  elements_vec = ('acc', 'acc_raw', 'acc_cal', 'mag', 'mag_raw', 'mag_cal')

  tilt_heading = 0

  moving_threshold = 0.001

  def reset_value(self):
    for key in self.elements:
      self.values[key] = np.nan
    for key in self.elements_vec:
      self.values[key] = [0] * 3
      #self.values[key] = {}
      #for i in range(X, Z+1):
      #  self.values[key][i] = np.nan
   
    self.mov_bin = 10
    self.acc_var = {}
    self.acc_var_value = np.zeros(3)
    for i in range(X, Z+1):
      self.acc_var[i] = [0] * self.mov_bin
    self.moving = [1] * self.mov_bin
    self.values['pitch_fixed'] = 0
    self.values['roll_fixed'] = 0
    self.do_calibrate_position = True
  
  def init_sensor(self):

    # ODR=50hz, all accel axes on ## maybe 0x27 is Low Res?
    self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG1, 0x57)
    # set full scale +/- 2g
    self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG2, (3<<6)|(0<<3))
    # no interrupt
    self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG3, 0x00) 
    self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG4, 0x00)
    # 0x10 = mag 50Hz output rate
    self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG5, 0x80|(4<<2))
    # Magnetic Scale +/1 1.3 Guass
    self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG6, MAG_SCALE_2)
    # 0x00 continuous conversion mode
    self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG7, 0x00)

  def read(self):

    #Read the magnetomter and return the raw x, y and z magnetic readings as a vector.
    mag_raw = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, OUT_X_L_M|0x80, 6)
    self.values['mag_raw'] = list(struct.unpack("<hhh", bytearray(mag_raw)))
    self.values['mag_raw'][2] = -self.values['mag_raw'][2]
    for i in range(X, Z+1):
      self.values['mag_cal'][i] = self.values['mag_raw'][i]
      self.values['mag'][i] = self.values['mag_raw'][i]

    #Read the accelerometer and return the x, y and z acceleration as a vector in Gs.
    acc_raw = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, OUT_X_L_A|0x80, 6)
    accel = list(struct.unpack("<hhh", bytearray(acc_raw)))
    accel[2] = -accel[2]
    for i in range(X, Z+1):
      self.values['acc_raw'][i] = accel[i] / math.pow(2, 15) * ACCEL_SCALE
      self.values['acc_cal'][i] = self.values['acc_raw'][i]
      self.values['acc'][i] = self.values['acc_raw'][i]
    #print(self.values['acc_raw'])

    ###################################
    # move to some functions          #
    ###################################
    
    pitch, roll = self.get_pitch_roll(self.values['acc_raw'])
    if pitch != None and roll != None:
      self.values['pitch'] = pitch
      self.values['roll'] = roll
      yaw = self.get_yaw(
        self.values['mag_raw'], 
        self.values['pitch'], 
        self.values['roll']
        )
      if yaw != None:
        self.values['yaw'] = yaw
        self.tilt_heading = self.values['yaw']
        if self.tilt_heading < 0:
          self.tilt_heading += 2*math.pi
        if self.tilt_heading > 2*math.pi:
          self.tilt_heading -= 2*math.pi
        self.values['heading'] = int(math.degrees(self.tilt_heading))
   
    #convert acc to bicyle
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
    m_acc   = np.array(self.values['acc_raw']).reshape(3,1)
    
    m_acc_mod = m_roll@m_pitch@m_acc
    #m_acc_mod = m_yaw@m_roll@m_pitch@m_acc
    self.values['acc'] = m_acc_mod.reshape(3).tolist()

    #remove gravity (converted acceleration - gravity)
    self.values['acc'][Z] -= 1.0

    try:
      self.values['grade'] = 100*math.tan(self.values['roll'] - self.values['roll_fixed'])
    except:
      pass

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
   

    ##########################################

    #stop detection
    for i in range(X, Z+1):
      if len(self.acc_var[i]) > self.mov_bin:
        del(self.acc_var[i][0])
      self.acc_var[i].append(self.values['acc_raw'][i])
      self.acc_var_value[i] = np.var(self.acc_var[i])
    moving = 0
    if self.acc_var_value[0] > self.moving_threshold \
      and self.acc_var_value[1] > self.moving_threshold \
      and self.acc_var_value[2] > self.moving_threshold:
      moving = 1
    if len(self.moving) > self.mov_bin:
      del(self.moving[0])
    self.moving.append(moving)
    self.values['moving_status'] = self.moving[-1]
    
    if self.do_calibrate_position and sum(self.moving) == 0:
      pitch, roll = self.get_pitch_roll([
        np.average(self.acc_var[0]),
        np.average(self.acc_var[1]),
        np.average(self.acc_var[2])
        ])
      if pitch != None and roll != None:
        self.values['pitch_fixed'] = pitch
        self.values['roll_fixed'] = roll
        self.do_calibrate_position = False
        print("calibrated position")

  def get_pitch_roll(self, acc):
    #a tilt compensated heading calculated from the magnetometer data.
    pitch = roll = None
    truncate = [0,0,0]
    for i in range(X, Z+1):
      truncate[i] = math.copysign(min(math.fabs(acc[i]), 1.0), acc[i])
    try:
      pitch = math.asin(-1*truncate[X])
      # set roll to zero if pitch approaches 0 or 1
      roll = math.asin(truncate[Y]/math.cos(pitch)) if abs(math.cos(pitch)) >= abs(truncate[Y]) else 0
    except:
      pass
    return pitch, roll 

  def get_yaw(self, mag, pitch, roll):
    yaw = None
    cos_p = math.cos(pitch)
    sin_p = math.sin(pitch)
    cos_r = math.cos(roll)
    sin_r = math.sin(roll)
    tiltcomp_x = mag[X]*cos_p + mag[Z]*sin_p
    tiltcomp_y = mag[X]*sin_r*sin_p + mag[Y]*cos_r - mag[Z]*sin_r*cos_p
    tiltcomp_z = mag[X]*cos_r*sin_p + mag[Y]*sin_r + mag[Z]*cos_r*cos_p

    try:
      yaw = math.atan2(tiltcomp_x, tiltcomp_y)
    except:
      pass
    return yaw
 
  def calibrate_position(self):
    self.do_calibrate_position = True

  def is_mag_ready(self):
    return (self.bus.read_byte_data(self.SENSOR_ADDRESS, STATUS_REG_M) & 0x03) > 0


if __name__=="__main__":
  l = LSM303D()
  while True:
    l.read()
    print("{:+.1f}, {:+.1f}, {:+.1f}, {:+.1f}, {:+.1f}, {:+.1f}, {:+.1f},{:+.1f}".format(
      l.values['pitch'],
      l.values['roll'],
      l.values['yaw'],
      l.values['acc'][0],
      l.values['acc'][1],
      l.values['acc'][2],
      l.values['grade'],
      math.degrees(l.values['roll']-l.values['roll_fixed'])
      ))
    time.sleep(0.1)


