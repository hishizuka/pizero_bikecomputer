import time
import smbus

try:
  #run from top directory (pizero_bikecomputer)
  from . import i2c
except:
  #directly run this program
  import i2c


#for BMP280
# https://ae-bst.resource.bosch.com/media/_tech/media/datasheets/BST-BMP280-DS001.pdf

# power mode
# POWER_MODE=0 # sleep mode
# POWER_MODE=1 # forced mode
# POWER_MODE=2 # forced mode
POWER_MODE=3 # normal mode

# temperature resolution
# OSRS_T = 0 # skipped
OSRS_T = 1 # 16 Bit
# OSRS_T = 2 # 17 Bit
# OSRS_T = 3 # 18 Bit
# OSRS_T = 4 # 19 Bit
# OSRS_T = 5 # 20 Bit

# pressure resolution
# OSRS_P = 0 # pressure measurement skipped
# OSRS_P = 1 # 16 Bit ultra low power
# OSRS_P = 2 # 17 Bit low power
# OSRS_P = 3 # 18 Bit standard resolution
# OSRS_P = 4 # 19 Bit high resolution
OSRS_P = 5 # 20 Bit ultra high resolution

# filter settings
# value = (value_n-1 * (FILTER - 1) + raw_data) / FILTER
# FILTER = 0 # OFF
# FILTER = 1 # 2
# FILTER = 2 # 4
# FILTER = 3 # 8
FILTER = 4 # 16

# standby settings
# T_SB = 0 # 000 0.5ms
T_SB = 1 # 001 62.5 ms
# T_SB = 2 # 010 125 ms
# T_SB = 3 # 011 250ms
# T_SB = 4 # 100 500ms
# T_SB = 5 # 101 1000ms
# T_SB = 6 # 110 2000ms
# T_SB = 7 # 111 4000ms

CONFIG = (T_SB << 5) + (FILTER << 2) # combine bits for config
CTRL_MEAS = (OSRS_T << 5) + (OSRS_P << 2) + POWER_MODE # combine bits for ctrl_meas


class BMP280(i2c.i2c):

  #address
  SENSOR_ADDRESS = 0x77

  #for reset
  RESET_ADDRESS = 0xE0
  RESET_VALUE = 0xB6

  #for reading value
  VALUE_ADDRESS = 0xF7
  VALUE_BYTES = 6

  #for test
  TEST_ADDRESS = 0xD0 #chip_id
  TEST_VALUE = 0x58

  elements = ('temperature', 'pressure')

  def init_sensor(self):
    
    # BMP280 address, 0x77
    # Read data back from 0x88(136), 24 bytes
    b1 = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, 0x88, 24)

    # Convert the data
    # Temp coefficents
    self.dig_T1 = b1[1] * 256 + b1[0]
    self.dig_T2 = b1[3] * 256 + b1[2]
    if self.dig_T2 > 32767 :
        self.dig_T2 -= 65536
    self.dig_T3 = b1[5] * 256 + b1[4]
    if self.dig_T3 > 32767 :
        self.dig_T3 -= 65536

    # Pressure coefficents
    self.dig_P1 = b1[7] * 256 + b1[6]
    self.dig_P2 = b1[9] * 256 + b1[8]
    if self.dig_P2 > 32767 :
        self.dig_P2 -= 65536
    self.dig_P3 = b1[11] * 256 + b1[10]
    if self.dig_P3 > 32767 :
        self.dig_P3 -= 65536
    self.dig_P4 = b1[13] * 256 + b1[12]
    if self.dig_P4 > 32767 :
        self.dig_P4 -= 65536
    self.dig_P5 = b1[15] * 256 + b1[14]
    if self.dig_P5 > 32767 :
        self.dig_P5 -= 65536
    self.dig_P6 = b1[17] * 256 + b1[16]
    if self.dig_P6 > 32767 :
        self.dig_P6 -= 65536
    self.dig_P7 = b1[19] * 256 + b1[18]
    if self.dig_P7 > 32767 :
        self.dig_P7 -= 65536
    self.dig_P8 = b1[21] * 256 + b1[20]
    if self.dig_P8 > 32767 :
        self.dig_P8 -= 65536
    self.dig_P9 = b1[23] * 256 + b1[22]
    if self.dig_P9 > 32767 :
        self.dig_P9 -= 65536

    # Select Control measurement register, 0xF4(244)
    self.bus.write_byte_data(self.SENSOR_ADDRESS, 0xF4, CTRL_MEAS)
    # Select Configuration register, 0xF5(245)
    self.bus.write_byte_data(self.SENSOR_ADDRESS, 0xF5, CONFIG)
    #self.bus.write_byte_data(SENSOR_ADDRESS, CTRL_REG1_ADDRESS, CONFIG_REG1)

  def read(self):
    # Temperature(HSB/LSB), Pressure(MSB/LSB/xLSB)
    data = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, self.VALUE_ADDRESS, self.VALUE_BYTES)

    # Convert pressure and temperature data to 19-bits
    # combine 3 bytes  msb 12 bits left, lsb 4 bits left, xlsb 4 bits right
    adc_p = ((data[0] * 65536) + (data[1] * 256) + (data[2] & 0xF0)) / 16
    #adc_p = ((data[0] << 16) | (data[1] << 8) | (data[2] & 0xF0)) / 16
    adc_t = ((data[3] * 65536) + (data[4] * 256) + (data[5] & 0xF0)) / 16
    #adc_t = ((data[3] << 16) | (data[4] << 8) + (data[5] & 0xF0)) / 16

    # Temperature offset calculations
    var1 = ((adc_t) / 16384.0 - (self.dig_T1) / 1024.0) * (self.dig_T2)
    var2 = (((adc_t) / 131072.0 - (self.dig_T1) / 8192.0) * ((adc_t)/131072.0 - (self.dig_T1)/8192.0)) * (self.dig_T3)
    t_fine = (var1 + var2)
    cTemp = (var1 + var2) / 5120.0
    #fTemp = cTemp * 1.8 + 32

    # Pressure offset calculations
    var1 = (t_fine / 2.0) - 64000.0
    var2 = var1 * var1 * (self.dig_P6) / 32768.0
    var2 = var2 + var1 * (self.dig_P5) * 2.0
    var2 = (var2 / 4.0) + ((self.dig_P4) * 65536.0)
    var1 = ((self.dig_P3) * var1 * var1 / 524288.0 + (self.dig_P2) * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * (self.dig_P1)
    p = 1048576.0 - adc_p
    p = (p - (var2 / 4096.0)) * 6250.0 / var1
    var1 = (self.dig_P9) * p * p / 2147483648.0
    var2 = p * (self.dig_P8) / 32768.0
    pressure = (p + (var1 + var2 + (self.dig_P7)) / 16.0) / 100

    # Output data to screen
    self.values['temperature'] = cTemp
    self.values['pressure'] = pressure


if __name__=='__main__':
  s = BMP280()
  while True:
    time.sleep(1)
    s.read()
    print(s.values['temperature'], s.values['pressure'])
    

