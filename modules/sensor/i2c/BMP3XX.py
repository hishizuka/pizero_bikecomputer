import time
import struct

try:
  #run from top directory (pizero_bikecomputer)
  from . import i2c
except:
  #directly run this program
  import i2c


# temperature resolution
# OSRS_T = 0 # no oversampling
OSRS_T = 1 # x2 oversampling
# OSRS_T = 2 # x4 oversampling
# OSRS_T = 3 # x8 oversampling
# OSRS_T = 4 # x16 oversampling
# OSRS_T = 5 # x32 oversampling

# pressure resolution
# OSRS_P = 0 # no oversampling
# OSRS_P = 1 # x2 oversampling
# OSRS_P = 2 # x4 oversampling
OSRS_P = 3 # x8 oversampling
# OSRS_P = 4 # x16 oversampling
# OSRS_P = 5 # x32 oversampling

# filter settings
# value = (value_n-1 * (FILTER - 1) + raw_data) / FILTER
# FILTER = 0 # OFF
# FILTER = 1 # 2
FILTER = 2 # 4
# FILTER = 3 # 8
# FILTER = 4 # 16

# standby settings
# ODR = 0 # 200Hz, 5ms
# ODR = 1 # 100Hz, 10ms
# ODR = 2 # 50Hz, 20ms
ODR = 3 # 25Hz, 80ms
# ODR = 4 # 25/2Hz, 160ms
# ODR = 5 # 25/4Hz, 320ms
# ODR = 6 # 25/8Hz, 640ms
# ODR = 7 # 25/16Hz, 1.280s

CONFIG_OSR = (OSRS_T << 3) + OSRS_P


class BMP3XX(i2c.i2c):

  #address
  SENSOR_ADDRESS = 0x77

  #for reset
  RESET_ADDRESS = 0x7E
  RESET_VALUE = 0xB6

  #for reading value
  VALUE_ADDRESS = 0x04
  VALUE_BYTES = 6

  #for test
  TEST_ADDRESS = 0x00 #chip_id
  TEST_VALUE = (0x50, 0x60)

  elements = ('temperature', 'pressure')
  temperature = None
  pressure = None

  def init_sensor(self):
    
    # Read data back from 0x31, 21 bytes
    b = struct.unpack(
      "<HHbhhbbHHbbhbb", 
      bytearray(self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, 0x31, 21))
      )

    # Convert the data
    # Temp coefficients
    self.T1 = b[0] / 2 ** -8.0
    self.T2 = b[1] / 2 ** 30.0
    self.T3 = b[2] / 2 ** 48.0

    # Pressure coefficients
    self.P1 = (b[3] - 2 ** 14.0) / 2 ** 20.0
    self.P2 = (b[4] - 2 ** 14.0) / 2 ** 29.0
    self.P3 = b[5] / 2 ** 32.0
    self.P4 = b[6] / 2 ** 37.0
    self.P5 = b[7] / 2 ** -3.0
    self.P6 = b[8] / 2 ** 6.0
    self.P7 = b[9] / 2 ** 8.0
    self.P8 = b[10] / 2 ** 15.0
    self.P9 = b[11] / 2 ** 48.0
    self.P10 = b[12] / 2 ** 48.0
    self.P11 = b[13] / 2 ** 65.0

    #BMP3XX address, 0x77
    #Normal mode(2bit), none(2bit), enable temperature(1bit), enable pressure(1bit) 
    #self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x1B, 0b010011)
    #self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x1B, 0b110011)
    #time.sleep(0.01)
    
    self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x1C, CONFIG_OSR)
    time.sleep(0.01)
    
    self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x1D, ODR)
    time.sleep(0.01)
    
    self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x1F, FILTER << 1)
    time.sleep(0.01)

    self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x1B, 0b010011)
    time.sleep(0.01)

  def read(self):

    self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x1B, 0b010011)
    time.sleep(0.01)
    
    data = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, self.VALUE_ADDRESS, self.VALUE_BYTES)
    
    adc_t = data[5] << 16 | data[4] << 8 | data[3]
    pd1 = adc_t - self.T1
    pd2 = pd1 * self.T2
    temperature = pd2 + (pd1 * pd1) * self.T3
    
    adc_p = data[2] << 16 | data[1] << 8 | data[0]
    pd1 = self.P6 * temperature
    pd2 = self.P7 * temperature ** 2.0
    pd3 = self.P8 * temperature ** 3.0
    po1 = self.P5 + pd1 + pd2 + pd3
    
    pd1 = self.P2 * temperature
    pd2 = self.P3 * temperature ** 2.0
    pd3 = self.P4 * temperature ** 3.0
    po2 = adc_p * (self.P1 + pd1 + pd2 + pd3)
    
    pd1 = adc_p ** 2.0
    pd2 = self.P9 + self.P10 * temperature
    pd3 = pd1 * pd2
    pd4 = pd3 + self.P11 * adc_p ** 3.0
    
    pressure = (po1 + po2 + pd4)/100

    # Output data to screen
    self.values['pressure'] = pressure
    self.values['temperature'] = temperature
    self.pressure = self.values['pressure']
    self.temperature = self.values['temperature']


if __name__=='__main__':
  s = BMP3XX()
  while True:
    time.sleep(1)
    s.read()
    print(s.values['temperature'], s.values['pressure'])
    

