import time

import numpy as np
import smbus


class i2c:
    # address
    SENSOR_ADDRESS = None

    # for reset
    RESET_ADDRESS = None
    RESET_VALUE = None

    # for reading value
    VALUE_ADDRESS = None
    VALUE_BYTES = None

    # for test
    TEST_ADDRESS = None
    TEST_VALUE = (None,)

    elements = "value"
    values = {}

    def __init__(self, reset=True):
        self.bus = smbus.SMBus(1)
        if reset:
            self.bus.write_byte_data(
                self.SENSOR_ADDRESS, self.RESET_ADDRESS, self.RESET_VALUE
            )
        time.sleep(0.01)
        self.reset_value()
        self.init_sensor()

    @classmethod
    def test(cls):
        try:
            bus = smbus.SMBus(1)
            v = bus.read_byte_data(cls.SENSOR_ADDRESS, cls.TEST_ADDRESS)
            if v in cls.TEST_VALUE:
                return True
            return False
        except:
            return False

    def reset_value(self):
        for key in self.elements:
            self.values[key] = np.nan

    def init_sensor(self):
        pass

    def read(self):
        pass
