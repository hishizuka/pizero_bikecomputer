import time
import smbus

try:
  #run from top directory (pizero_bikecomputer)
  from . import i2c
except:
  #directly run this program
  import i2c


#for LPS22HB and LPS33HB
# https://strawberry-linux.com/pub/en.DM00386016.pdf

#output data rate
CTRL_REG1_ADDRESS = 0x10
#CTRL_REG1_ODR = 0b001 # 1Hz
CTRL_REG1_ODR = 0b010 # 10Hz
#CTRL_REG1_ODR = 0b011 # 25Hz
#CTRL_REG1_ODR = 0b100 # 50Hz
#CTRL_REG1_ODR = 0b101 # 75Hz

#low pass filter
LOW_PASS_FILTER = 1 # 0: off, 1: on
LOW_PASS_FILTER_CONFIG = 1 # 0: ODR/9, 1: ODR/20

BLOCK_DATA_UPDATE = 1 #0:always, 1:if read

#combine bits for config
CONFIG_REG1 = (CTRL_REG1_ODR << 4) + (LOW_PASS_FILTER << 3) + (LOW_PASS_FILTER_CONFIG << 2) + (BLOCK_DATA_UPDATE << 1) 


class LPS33HW(i2c.i2c):

  #address
  #SENSOR_ADDRESS = 0x5c #0x5C SA0 pin to GND
  SENSOR_ADDRESS = 0x5d #0x5D SA0 pin to VDD_IO

  #for reset
  RESET_ADDRESS = 0x11
  RESET_VALUE = 0b00010100

  #for reading value
  VALUE_ADDRESS = 0x28 #0x2A(HSB), 0x29, 0x28(LSB)
  VALUE_BYTES = 5

  #for test
  TEST_ADDRESS = 0x0F #who_am_i
  TEST_VALUE = 0xB1

  elements = ('temperature', 'pressure')
  temperature = None
  pressure = None
  
  def init_sensor(self):
    self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG1_ADDRESS, CONFIG_REG1)

  def read(self):
    # Temperature(HSB/LSB), Pressure(MSB/LSB/xLSB)
    data = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, self.VALUE_ADDRESS, self.VALUE_BYTES)

    # Output data to screen
    self.values['pressure'] = ((data[2] << 16) | (data[1] << 8) | data[0]) / 4096 
    self.values['temperature'] = ((data[4] << 8) | data[3]) / 100
    self.pressure = self.values['pressure']
    self.temperature = self.values['temperature']

if __name__=='__main__':
  s = LPS33HW()
  while True:
    time.sleep(1)
    s.read()
    print(s.values['temperature'], s.values['pressure'])
    
