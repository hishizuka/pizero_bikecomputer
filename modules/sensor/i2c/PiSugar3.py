import time

import numpy as np

try:
    # run from top directory (pizero_bikecomputer)
    from . import i2c
except:
    # directly run this program
    import i2c

# https://github.com/PiSugar/PiSugar/wiki/PiSugar-3-Series


class PiSugar3(i2c.i2c):
    # address
    SENSOR_ADDRESS = 0x57

    # for reset
    # RESET_ADDRESS = 0x7E
    # RESET_VALUE = 0xB6

    # for reading value
    BATTERY_LEVEL_ADDRESS = 0x2A
    BATTERY_VOLTAGE_ADDRESS = 0x22
    BATTERY_VOLTAGE_BYTES = 2

    # for test
    TEST_ADDRESS = 0x00  # pisugar version
    TEST_VALUE = (0x03,)

    elements = ("battery_level", "battery_voltage")
    battery_level = None
    battery_voltage = None

    battery_curve = [
        (4.10, 100.0),
        (4.05, 95.0),
        (3.90, 88.0),
        (3.80, 77.0),
        (3.70, 65.0),
        (3.62, 55.0),
        (3.58, 49.0),
        (3.49, 25.6),
        (3.32, 4.5),
        (3.1, 0.0),
    ]

    BATTERY_LEVEL_AVE_LEN = 60
    battery_level_array = [np.nan,] * BATTERY_LEVEL_AVE_LEN

    def __init__(self):
        super().__init__(reset=False)

    def read(self):
        
        self.battery_level = self.bus.read_byte_data(
            self.SENSOR_ADDRESS, self.BATTERY_LEVEL_ADDRESS
        )
        v = self.bus.read_i2c_block_data(
            self.SENSOR_ADDRESS, self.BATTERY_VOLTAGE_ADDRESS, self.BATTERY_VOLTAGE_BYTES
        )
        self.battery_voltage = ((v[0] << 8) + v[1])/1000

        self.battery_level_array[:-1] = self.battery_level_array[1:]
        self.battery_level_array[-1] = self.get_battery_level_from_curve(self.battery_voltage)

        self.values["battery_level"] = int(round(np.nanmean(self.battery_level_array), 0))
        self.values["battery_voltage"] = self.battery_voltage

    def get_battery_level_from_curve(self, v):
        if v >= self.battery_curve[0][0]:
            return 100
        elif v < self.battery_curve[-1][0]:
            return 0
        for i in range(1, len(self.battery_curve)):
            v_low = self.battery_curve[i][0]
            l_low = self.battery_curve[i][1]
            if v >= v_low:
                v_high = self.battery_curve[i-1][0]
                l_high = self.battery_curve[i-1][1]
                percent = (v - v_low) / (v_high - v_low)
                return int(round(l_low + percent * (l_high - l_low), 0))
        return 0


if __name__ == "__main__":
    s = PiSugar3()
    while True:
        s.read()
        print(s.values["battery_level"], s.values["battery_voltage"])
        time.sleep(1)
