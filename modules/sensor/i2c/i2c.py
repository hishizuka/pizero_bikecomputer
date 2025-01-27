import time

import numpy as np
import smbus


class i2c:
    # address
    #SENSOR_ADDRESS = None

    # for reset
    #RESET_ADDRESS = None
    #RESET_VALUE = None

    # for reading value
    #VALUE_ADDRESS = None
    #VALUE_BYTES = None

    # for test
    #TEST_ADDRESS = None
    #TEST_VALUE = (None,)

    elements = ()
    elements_vec = ()
    values = {}

    def __init__(self, bus=1, reset=True, address=None):
        self.bus = smbus.SMBus(bus)
        if address is not None:
            self.SENSOR_ADDRESS = address
        if reset:
            self.bus.write_byte_data(
                self.SENSOR_ADDRESS, self.RESET_ADDRESS, self.RESET_VALUE
            )
        time.sleep(0.01)
        self.reset_value()
        self.init_sensor()

    @classmethod
    def test(cls, bus=1, address=None):
        if address is not None:
            cls.SENSOR_ADDRESS = address
        try:
            bus = smbus.SMBus(bus)
            v = bus.read_byte_data(cls.SENSOR_ADDRESS, cls.TEST_ADDRESS)
            if v in cls.TEST_VALUE:
                return True
            return False
        except:
            return False

    def reset_value(self):
        for key in self.elements:
            self.values[key] = np.nan
        for key in self.elements_vec:
            self.values[key] = [0] * 3

    def init_sensor(self):
        pass

    def read(self):
        pass
