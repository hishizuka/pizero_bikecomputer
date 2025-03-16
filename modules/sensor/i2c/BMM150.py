import time
import struct

try:
    # run from top directory (pizero_bikecomputer)
    from . import i2c
except:
    # directly run this program
    import i2c

# https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmm150-ds001.pdf

# https://github.com/boschsensortec/BMM150_SensorAPI/tree/master
# (c) 2020 BSD-3-Clause License Bosch Sensortec GmbH

# Reg

PWR_CTRL = 0x4B
MODE_RATE = 0x4C

REP_XY = 0x51
REP_Z = 0x52

DIG_X1 = 0x5D
DIG_Z4_LSB = 0x62
DIG_Z2_LSB = 0x68

# Value

MODE_NORMAL = 0x00
MODE_FORCED = 0x01
MODE_SLEEP  = 0x03

PRESET_LOWPOWER_REP_XY      = 0x01
PRESET_LOWPOWER_REP_Z       = 0x01
PRESET_REGULAR_REP_XY       = 0x04
PRESET_REGULAR_REP_Z        = 0x07
PRESET_HIGH_ACCURACY_REP_XY = 0x17
PRESET_HIGH_ACCURACY_REP_Z  = 0x29
PRESET_ENHANCED_REP_XY      = 0x07
PRESET_ENHANCED_REP_Z       = 0x0D

MAG_ODR_2   = 0x01
MAG_ODR_6   = 0x02
MAG_ODR_8   = 0x03
MAG_ODR_10  = 0x00 # LOWPOWER / REGULAR / ENHANCED
MAG_ODR_15  = 0x04
MAG_ODR_20  = 0x05 # HIGH_ACCURACY mode
MAG_ODR_25  = 0x06
MAG_ODR_30  = 0x07


class BMM150(i2c.i2c):
    # address
    SENSOR_ADDRESS = 0x13 # 0x11

    # for reset (#soft reset)
    RESET_ADDRESS = 0x00 #0x7E
    RESET_VALUE = 0x00 #0xB6

    # for reading value
    VALUE_ADDRESS = 0x42
    VALUE_BYTES = 8

    # for test
    TEST_ADDRESS = 0x40
    TEST_VALUE = (0x00, 0b00110010)

    elements_vec = ("mag",)

    mag_range = 1 #MAG_RANGE_2G
    mag_factor = 1 #(2 << acc_range) / 32768
    
    struct_pattern = struct.Struct("<hhhh")

    def init_sensor(self):

        # Power ON (Sleep)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, PWR_CTRL, 0x01)
        # wait 3ms
        time.sleep(0.003)

        # get trim (if chip_id is ok)
        self.get_trim_data()

        # set op mode and ODR
        self.bus.write_byte_data(
            self.SENSOR_ADDRESS,
            MODE_RATE,
            (self.bus.read_byte_data(self.SENSOR_ADDRESS, MODE_RATE) & 0b11000001) | (MAG_ODR_10 << 3) | (MODE_NORMAL << 1)
        )

        # set preset mode
        self.bus.write_byte_data(self.SENSOR_ADDRESS, REP_XY, PRESET_REGULAR_REP_XY)
        self.bus.write_byte_data(self.SENSOR_ADDRESS, REP_Z, PRESET_REGULAR_REP_Z)

    def get_trim_data(self):
        trim_x1_y1 = bytearray(
            self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, DIG_X1, 2)
        )
        trim_xyz_data = bytearray(
            self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, DIG_Z4_LSB, 4)
        )
        trim_xy1_xy2 = bytearray(
            self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, DIG_Z2_LSB, 10)
        )

        # trim_x1_y1: [dig_x1 dig_y1]
        self.dig_x1, self.dig_y1 = struct.unpack("<bb", trim_x1_y1)

        # trim_xyz_data: [[dig_z4, dig_z4] dig_x2 dig_y2]
        self.dig_z4, self.dig_x2, self.dig_y2 = struct.unpack("<hbb", trim_xyz_data)

        # trim_xy1_xy2: [[dig_z2, dig_z2] [dig_z1, dig_z1] [dig_xyz1, dig_xyz1] [dig_z3, dig_z3] dig_xy2 dig_xy1]
        trim_xy1_xy2[5] = trim_xy1_xy2[5] & 0x7F
        (
            self.dig_z2, self.dig_z1, self.dig_xyz1, self.dig_z3, self.dig_xy2, self.dig_xy1
        ) = struct.unpack("<hhhhbb", trim_xy1_xy2)

        #print(self.dig_x1, self.dig_y1, self.dig_x2, self.dig_y2)
        #print(self.dig_z1, self.dig_z2, self.dig_z3, self.dig_z4, self.dig_xy1, self.dig_xy2, self.dig_xyz1)

        self.dig_x1_m8 = self.dig_x1 * 8
        self.dig_x2_p160 = self.dig_x2 + 0xA0
        self.dig_y2_p160 = self.dig_y2 + 0xA0
        self.dig_y1_m8 = self.dig_y1 * 8
        self.dig_xy1_m128 = self.dig_xy1 * 128
        self.dig_xyz1_m16384 = self.dig_xyz1 * 16384

    def compenstate_x(self, data_x, data_r):
        if data_x == -4096:
            return -32768
        if data_r != 0:
            process_comp_x0 = data_r
        elif self.dig_xyz1 != 0:
            process_comp_x0 = self.dig_xyz1
        else:
            return -32768

        process_comp_x1 = self.dig_xyz1_m16384
        retval = int(process_comp_x1 / process_comp_x0) - 0x4000
        process_comp_x3 = retval * retval
        process_comp_x4 = self.dig_xy2 * (process_comp_x3 / 128)
        process_comp_x5 = self.dig_xy1_m128
        process_comp_x6 = retval * process_comp_x5
        process_comp_x7 = (process_comp_x4 + process_comp_x6) / 512 + 0x100000
        process_comp_x8 = self.dig_x2_p160
        process_comp_x9 = (process_comp_x7 * process_comp_x8) / 4096
        process_comp_x10= data_x * process_comp_x9
        retval = int(process_comp_x10 / 8192)
        retval = (retval + self.dig_x1_m8)/16        
        return retval

    def compenstate_y(self, data_y, data_r):
        if data_y == -4096:
            return -32768
        if data_r != 0:
            process_comp_y0 = data_r
        elif self.dig_xyz1 != 0:
            process_comp_y0 = self.dig_xyz1
        else:
            return -32768

        process_comp_y1 = int(self.dig_xyz1_m16384 / process_comp_y0)
        retval = process_comp_y1 - 0x4000
        process_comp_y3 = retval * retval
        process_comp_y4 = self.dig_xy2 * (process_comp_y3 / 128)
        process_comp_y5 = self.dig_xy1_m128
        process_comp_y6 = (process_comp_y4 + retval * process_comp_y5) / 512
        process_comp_y7 = self.dig_y2_p160
        process_comp_y8 = ((process_comp_y6 + 0x100000) * process_comp_y7) / 4096
        process_comp_y9 = data_y * process_comp_y8
        retval = int(process_comp_y9 / 8192)
        retval = (retval + self.dig_y1_m8) / 16
        return retval

    def compenstate_z(self, data_z, data_r):
        if data_z == -16384:
            return -32768
        if self.dig_z2 == 0 or self.dig_z1 == 0 or data_r == 0 or self.dig_xyz1 == 0:
            return -32768

        process_comp_z0 = data_r - self.dig_xyz1
        process_comp_z1 = (self.dig_z3 * process_comp_z0) / 4
        process_comp_z2 = (data_z - self.dig_z4) * 32768
        process_comp_z3 = self.dig_z1 * (data_r * 2)
        process_comp_z4 = (process_comp_z3 + 32768) / 65536
        retval = (process_comp_z2 - process_comp_z1) / (self.dig_z2 + process_comp_z4)
        retval = min(32767, retval)
        retval = max(-32767, retval)
        retval = retval/16
        return retval

    def read_mag(self):
        data = bytearray(
            self.bus.read_i2c_block_data(
                self.SENSOR_ADDRESS, self.VALUE_ADDRESS, self.VALUE_BYTES
            )
        )
        #print(f"[{data[0]} {data[1]} {data[2]} {data[3]} {data[4]} {data[5]} {data[6]} {data[7]}]")

        # for debug
        #mag_xx = ((data[0]&0xF8) >> 3)  | int(self.uint8_to_int8(data[1])*32)
        #mag_yy = ((data[2]&0xF8) >> 3)  | int(self.uint8_to_int8(data[3])*32)
        #mag_zz = ((data[4]&0xFE) >> 1)  | int(self.uint8_to_int8(data[5])*128)
        #mag_rr = ((data[6]&0xFC) >> 2)  | int(self.uint8_to_int8(data[7])*64)
        #print(f"mag: {mag_xx:+.2f} / {mag_yy:+.2f} / {mag_zz:+.2f} / {mag_rr:+.2f}")

        raw_data = [x >> y for (x, y) in zip(list(self.struct_pattern.unpack(data)), [3, 3, 1, 2])]
        #print(f"mag: {raw_data[0]:+.2f} / {raw_data[1]:+.2f} / {raw_data[2]:+.2f} / {raw_data[3]:+.2f}")

        self.values["mag"] = [
            self.compenstate_x(raw_data[0], raw_data[3]),
            self.compenstate_y(raw_data[1], raw_data[3]),
            self.compenstate_z(raw_data[2], raw_data[3]),
        ]
        #print(f"mag: {self.values['mag'][0]:+.2f} / {self.values['mag'][1]:+.2f} / {self.values['mag'][2]:+.2f}")
        #print()

    def uint8_to_int8(self, number):
        if number <= 127:
            return number
        else:
            return (256-number)*-1

    @property
    def magnetic(self):
        self.read_mag()
        return self.values["mag"]


if __name__ == "__main__":
    import math
    BMM150.test()
    b = BMM150()

    while True:
        b.read_mag()
        print(
            "{:+.2f}, {:+.2f}, {:+.2f} {}".format(
                b.values["mag"][0],
                b.values["mag"][1],
                b.values["mag"][2],
                int(math.degrees(math.atan2(b.values["mag"][1], b.values["mag"][0])))
            )
        )
        time.sleep(0.1)
