import time
import struct

import math
import numpy as np

try:
    # run from top directory (pizero_bikecomputer)
    from . import i2c
except:
    # directly run this program
    import i2c

# https://www.memsic.com/Public/Uploads/uploadfile/files/20220119/MMC5983MADatasheetRevA.pdf
# https://www.sparkfun.com/products/19895

### MMC5983MA Register definitions ###
OUT_X_L_M = 0x00
OUT_X_H_M = 0x01
OUT_Y_L_M = 0x02
OUT_Y_H_M = 0x03
OUT_Z_L_M = 0x04
OUT_Z_H_M = 0x05
OUT_XYZ = 0x06
TEMP_OUT = 0x07
STATUS = 0x08
CTRL_REG0 = 0x09
CTRL_REG1 = 0x0A
CTRL_REG2 = 0x0B
CTRL_REG3 = 0x0C

# Output resolution
OUTPUT_RATE = 0  # 100Hz
# OUTPUT_RATE = 1 # 200Hz
# OUTPUT_RATE = 2 # 400Hz
# OUTPUT_RATE = 3 # 800Hz

# Continuous Measurement Frequency
# CM_FREQ = 0 #OFF
# CM_FREQ = 1 #1Hz
CM_FREQ = 2  # 10Hz
# CM_FREQ = 3 #20Hz
# CM_FREQ = 4 #50Hz
# CM_FREQ = 5 #100Hz
# CM_FREQ = 6 #200Hz (require OUTPUT_RATE=200Hz)
# CM_FREQ = 7 #1000Hz (require OUTPUT_RATE=800Hz)


class MMC5983MA(i2c.i2c):
    # address
    SENSOR_ADDRESS = 0x30

    # SOFT RESET
    # RESET_ADDRESS = 0x0A
    # RESET_VALUE = 0b10000000

    # RESET
    RESET_ADDRESS = 0x09
    RESET_VALUE = 0x10

    # for reading value
    VALUE_ADDRESS = OUT_X_L_M
    VALUE_BYTES = 6
    VALUE_PATTERN = struct.Struct(">HHH")

    # for test
    TEST_ADDRESS = 0x2F
    TEST_VALUE = (0b00110000,)

    elements = ()
    elements_vec = ("mag",)

    # https://learn.sparkfun.com/tutorials/qwiic-9dof---ism330dhcx-mmc5983ma-hookup-guide#hardware-overview
    # Z Axis is opposite to ISM330DHCX
    z_sign = -1
    # acc_factor = ACCEL_SCALE/math.pow(2, 15)

    def reset_value(self):
        for key in self.elements:
            self.values[key] = np.nan
        for key in self.elements_vec:
            self.values[key] = [0] * 3

    def init_sensor(self):
        # Set
        self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG0, 0x08)
        time.sleep(0.01)

        # Auto_SR_en & INT_meas_done_en
        self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG0, 0x20 | 0x04)
        time.sleep(0.01)

        # set output rate
        self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG1, OUTPUT_RATE)
        time.sleep(0.01)
        # enable Continuous Measurement mode and set frequency
        self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG2, (1 << 3) | CM_FREQ)
        time.sleep(0.01)

    def read(self):
        self.read_mag()

    def read_mag(self):
        # Read the magnetomter and return the raw x, y and z magnetic readings as a vector.
        status = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, STATUS, 1)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, STATUS, status[0] & 0x01)

        mag_xyz = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, OUT_XYZ, 1)
        data = self.bus.read_i2c_block_data(
            self.SENSOR_ADDRESS, self.VALUE_ADDRESS, self.VALUE_BYTES
        )
        mag_raw = list(
            map(lambda x: x << 2, self.VALUE_PATTERN.unpack(bytearray(data)))
        )
        self.values["mag"][0] = (
            ((mag_raw[0] | (((mag_xyz[0] & 0xC0) >> 6) & 0x3)) - 131072) / 16384
        ) * 100
        self.values["mag"][1] = (
            ((mag_raw[1] | (((mag_xyz[0] & 0x30) >> 4) & 0x3)) - 131072) / 16384
        ) * 100
        self.values["mag"][2] = (
            self.z_sign
            * (((mag_raw[2] | (((mag_xyz[0] & 0x03) >> 2) & 0x3)) - 131072) / 16384)
            * 100
        )


if __name__ == "__main__":
    l = MMC5983MA()
    while True:
        l.read()
        print(
            "{:+.1f}, {:+.1f}, {:+.1f}".format(
                l.values["mag"][0],
                l.values["mag"][1],
                l.values["mag"][2],
            )
        )
        time.sleep(0.1)
