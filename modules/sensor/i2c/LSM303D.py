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

# https://www.pololu.com/file/0J703/LSM303D.pdf
# https://www.pololu.com/file/0J434/LSM303DLH-compass-app-note.pdf

### LSM303 Register definitions ###
TEMP_OUT_L = 0x05
TEMP_OUT_H = 0x06
STATUS_REG_M = 0x07
OUT_X_L_M = 0x08
OUT_X_H_M = 0x09
OUT_Y_L_M = 0x0A
OUT_Y_H_M = 0x0B
OUT_Z_L_M = 0x0C
OUT_Z_H_M = 0x0D
WHO_AM_I = 0x0F
INT_CTRL_M = 0x12
INT_SRC_M = 0x13
INT_THS_L_M = 0x14
INT_THS_H_M = 0x15
OFFSET_X_L_M = 0x16
OFFSET_X_H_M = 0x17
OFFSET_Y_L_M = 0x18
OFFSET_Y_H_M = 0x19
OFFSET_Z_L_M = 0x1A
OFFSET_Z_H_M = 0x1B
REFERENCE_X = 0x1C
REFERENCE_Y = 0x1D
REFERENCE_Z = 0x1E
CTRL_REG0 = 0x1F
CTRL_REG1 = 0x20
CTRL_REG2 = 0x21
CTRL_REG3 = 0x22
CTRL_REG4 = 0x23
CTRL_REG5 = 0x24
CTRL_REG6 = 0x25
CTRL_REG7 = 0x26
STATUS_REG_A = 0x27
OUT_X_L_A = 0x28
OUT_X_H_A = 0x29
OUT_Y_L_A = 0x2A
OUT_Y_H_A = 0x2B
OUT_Z_L_A = 0x2C
OUT_Z_H_A = 0x2D
FIFO_CTRL = 0x2E
FIFO_SRC = 0x2F
IG_CFG1 = 0x30
IG_SRC1 = 0x31
IG_THS1 = 0x32
IG_DUR1 = 0x33
IG_CFG2 = 0x34
IG_SRC2 = 0x35
IG_THS2 = 0x36
IG_DUR2 = 0x37
CLICK_CFG = 0x38
CLICK_SRC = 0x39
CLICK_THS = 0x3A
TIME_LIMIT = 0x3B
TIME_LATENCY = 0x3C
TIME_WINDOW = 0x3D
ACT_THS = 0x3E
ACT_DUR = 0x3F

### Mag scales ###
MAG_SCALE_2 = 0x00  # full-scale is +/- 2 Gauss
MAG_SCALE_4 = 0x20  # +/- 4 Gauss
MAG_SCALE_8 = 0x40  # +/- 8 Gauss
MAG_SCALE_12 = 0x60  # +/- 12 Gauss

ACCEL_SCALE = 2  # +/- 2g


class LSM303D(i2c.i2c):
    # address
    SENSOR_ADDRESS = 0x1D  # Assuming SA0 grounded

    # for reset
    # BOOT (0: normal mode; 1: reboot memory content)
    # FIFO (0: disable; 1: enable)
    # FIFO programmable threshold (0: disable; 1: enable)
    # 0 (fixed)
    # 0 (fixed)
    # High-pass filter for click function (0: disable; 1: enable)
    # High-pass filter for interrupt generator 1 (0: disable; 1: enable)
    # High-pass filter for interrupt generator 2 (0: disable; 1: enable)
    RESET_ADDRESS = 0x1F
    RESET_VALUE = 0x00  # or 0b10000000

    # for reading value
    # VALUE_ADDRESS = 0xF7
    # VALUE_BYTES = 6

    # for test
    TEST_ADDRESS = 0x0F
    TEST_VALUE = (0x49,)

    elements_vec = ("acc", "mag")

    acc_factor = ACCEL_SCALE / math.pow(2, 15)

    def init_sensor(self):
        # ODR=3Hz, all accel axes on ## maybe 0x27 is Low Res?
        self.bus.write_byte_data(
            self.SENSOR_ADDRESS, CTRL_REG1, 0x17
        )  # 0x57: 50Hz, 0x17: 3.125Hz
        # set full scale +/- 2g
        self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG2, (3 << 6) | (0 << 3))
        # no interrupt
        self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG3, 0x00)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG4, 0x00)
        # 0x10 = mag 50Hz output rate
        self.bus.write_byte_data(
            self.SENSOR_ADDRESS, CTRL_REG5, 0x80
        )  # 0x80|(4<<2): 50Hz
        # Magnetic Scale +/1 1.3 Gauss
        self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG6, MAG_SCALE_2)
        # 0x00 continuous conversion mode
        self.bus.write_byte_data(self.SENSOR_ADDRESS, CTRL_REG7, 0x00)

    def read(self):
        self.read_acc()
        self.read_mag()

    def read_acc(self):
        # Read the accelerometer and return the x, y and z acceleration as a vector in Gs.
        acc_raw = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, OUT_X_L_A | 0x80, 6)
        self.values["acc"] = list(
            map(
                lambda x: x * self.acc_factor,
                list(struct.unpack("<hhh", bytearray(acc_raw))),
            )
        )

    def read_mag(self):
        # Read the magnetomter and return the raw x, y and z magnetic readings as a vector.
        mag_raw = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, OUT_X_L_M | 0x80, 6)
        self.values["mag"] = list(struct.unpack("<hhh", bytearray(mag_raw)))


if __name__ == "__main__":
    l = LSM303D()
    while True:
        l.read()
        print(
            "{:+.1f}, {:+.1f}, {:+.1f}, {:+.1f}, {:+.1f}, {:+.1f}".format(
                l.values["acc"][0],
                l.values["acc"][1],
                l.values["acc"][2],
                l.values["mag"][0],
                l.values["mag"][1],
                l.values["mag"][2],
            )
        )
        time.sleep(0.1)
