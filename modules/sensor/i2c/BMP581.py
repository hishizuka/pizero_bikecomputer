import time

try:
    # run from top directory (pizero_bikecomputer)
    from . import i2c
except:
    # directly run this program
    import i2c

# https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmp581-ds004.pdf
# https://github.com/BoschSensortec/BMP5-Sensor-API
# https://github.com/sparkfun/SparkFun_BMP581_Arduino_Library

# Over Sampling Rate(OSR): temperature
# OSRS_T = 0 # no oversampling
OSRS_T = 1  # x2 oversampling
# OSRS_T = 2 # x4 oversampling
# OSRS_T = 3 # x8 oversampling
# OSRS_T = 4 # x16 oversampling
# OSRS_T = 5 # x32 oversampling
# OSRS_T = 6 # x64 oversampling
# OSRS_T = 7 # x128 oversampling

# Over Sampling Rate(OSR): pressure
# OSRS_P = 0 # no oversampling
# OSRS_P = 1 # x2 oversampling
# OSRS_P = 2 # x4 oversampling
OSRS_P = 3  # x8 oversampling
# OSRS_P = 4 # x16 oversampling
# OSRS_P = 5 # x32 oversampling
# OSRS_P = 6 # x64 oversampling
# OSRS_P = 7 # x128 oversampling

# power mode
# POWER_MODE = 0 # standby
POWER_MODE = 1  # Normal mode
# POWER_MODE = 2 # Forced mode
# POWER_MODE = 3 # Non-Stop mode

# Output Data Rate(ODR)
# ODR = 0x00 # 240Hz
# ODR = 0x04 # 160Hz
# ODR = 0x06 # 140Hz
# ODR = 0x08 # 120Hz
# ODR = 0x0C # 80Hz
# ODR = 0x0E # 60Hz
# ODR = 0x11 # 40Hz
# ODR = 0x15 # 20Hz
ODR = 0x17  # 10Hz
# ODR = 0x18 # 5Hz
# ODR = 0x19 # 4Hz
# ODR = 0x1A # 3Hz
# ODR = 0x1B # 2Hz
# ODR = 0x1C # 1Hz
# ODR = 0x1D # 0.500Hz
# ODR = 0x1E # 0.250Hz
# ODR = 0x1F # 0.125Hz

# filter settings
# value = (value_n-1 * (FILTER - 1) + raw_data) / FILTER
# FILTER_T = 0 # OFF
# FILTER_T = 1 # 2
FILTER_T = 2  # 4
# FILTER_T = 3 # 8
# FILTER_T = 4 # 16
# FILTER_T = 5 # 32
# FILTER_T = 6 # 64
# FILTER_T = 7 # 128

# FILTER_P = 0 # OFF
# FILTER_P = 1 # 2
FILTER_P = 2  # 4
# FILTER_P = 3 # 8
# FILTER_P = 4 # 16
# FILTER_P = 5 # 32
# FILTER_P = 6 # 64
# FILTER_P = 7 # 128

CONFIG_OSR_ENABLEPRESS = (1 << 6) + (OSRS_P << 3) + OSRS_T
CONFIG_POWER_ODR = (1 << 7) + (ODR << 2) + POWER_MODE
CONFIG_POWER_ODR_WITH_STANDBY_MODE = (1 << 7) + (ODR << 2) + 0
CONFIG_FILTER_1 = (1 << 5) + (1 << 3) + (1 << 1) + 1
CONFIG_FILTER_2 = (FILTER_P << 3) + FILTER_T


class BMP581(i2c.i2c):
    # address
    SENSOR_ADDRESS = 0x47  # or 0x46

    # for reset
    RESET_ADDRESS = 0x7E
    RESET_VALUE = 0xB6

    # for reading value
    VALUE_ADDRESS = 0x1D
    VALUE_BYTES = 6

    # for test
    TEST_ADDRESS = 0x01  # chip_id
    TEST_VALUE = (0x50,)

    elements = ("temperature", "pressure")
    temperature = None
    pressure = None

    def init_sensor(self):
        # enable pressure and config OSR
        self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x36, CONFIG_OSR_ENABLEPRESS)
        time.sleep(0.01)

        # enable pressure and config OSR
        # self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x37, CONFIG_POWER_ODR)
        self.bus.write_byte_data(
            self.SENSOR_ADDRESS, 0x37, CONFIG_POWER_ODR_WITH_STANDBY_MODE
        )
        time.sleep(0.01)

        # IIR Filter (need to set Standby mode)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x30, CONFIG_FILTER_1)
        time.sleep(0.01)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x31, CONFIG_FILTER_2)
        time.sleep(0.01)
        # return Normal mode
        self.bus.write_byte_data(self.SENSOR_ADDRESS, 0x37, CONFIG_POWER_ODR)
        time.sleep(0.01)

    def read(self):
        data = self.bus.read_i2c_block_data(
            self.SENSOR_ADDRESS, self.VALUE_ADDRESS, self.VALUE_BYTES
        )
        temperature = int.from_bytes(data[0:3], "little") / 65536
        pressure = int.from_bytes(data[3:6], "little") / 6400

        # Output data to screen
        self.values["pressure"] = pressure
        self.values["temperature"] = temperature
        self.pressure = self.values["pressure"]
        self.temperature = self.values["temperature"]


if __name__ == "__main__":
    s = BMP581()
    while True:
        s.read()
        print(s.values["temperature"], s.values["pressure"])
        time.sleep(1)
