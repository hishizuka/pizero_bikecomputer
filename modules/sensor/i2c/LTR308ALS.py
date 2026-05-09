import time


# Lite-On LTR-308ALS-01 ambient light sensor.
# Datasheet: Lite-On LTR-308ALS-01 Final DS V2.1.

MAIN_CTRL = 0x00
ALS_MEAS_RATE = 0x04
ALS_GAIN = 0x05
PART_ID = 0x06
MAIN_STATUS = 0x07
ALS_DATA = 0x0D

PART_ID_MASK = 0xF0
PART_NUMBER_ID = 0xB0

MAIN_CTRL_SW_RESET = 0x10
MAIN_CTRL_ALS_ENABLE = 0x02

RESOLUTION_20BIT = 0
RESOLUTION_19BIT = 1
RESOLUTION_18BIT = 2
RESOLUTION_17BIT = 3
RESOLUTION_16BIT = 4

RESOLUTION_INTEGRATION_FACTOR = {
    RESOLUTION_20BIT: 4.0,
    RESOLUTION_19BIT: 2.0,
    RESOLUTION_18BIT: 1.0,
    RESOLUTION_17BIT: 0.5,
    RESOLUTION_16BIT: 0.25,
}

MEASUREMENT_RATE_25MS = 0
MEASUREMENT_RATE_50MS = 1
MEASUREMENT_RATE_100MS = 2
MEASUREMENT_RATE_500MS = 3
MEASUREMENT_RATE_1000MS = 5
MEASUREMENT_RATE_2000MS = 6

GAIN_1X = 0
GAIN_3X = 1
GAIN_6X = 2
GAIN_9X = 3
GAIN_18X = 4

GAIN_FACTOR = {
    GAIN_1X: 1.0,
    GAIN_3X: 3.0,
    GAIN_6X: 6.0,
    GAIN_9X: 9.0,
    GAIN_18X: 18.0,
}


class LTR308ALS:
    SENSOR_ADDRESS = 0x53
    TEST_ADDRESS = PART_ID

    elements = ("light", "raw")

    RESOLUTION_20BIT = RESOLUTION_20BIT
    RESOLUTION_19BIT = RESOLUTION_19BIT
    RESOLUTION_18BIT = RESOLUTION_18BIT
    RESOLUTION_17BIT = RESOLUTION_17BIT
    RESOLUTION_16BIT = RESOLUTION_16BIT

    MEASUREMENT_RATE_25MS = MEASUREMENT_RATE_25MS
    MEASUREMENT_RATE_50MS = MEASUREMENT_RATE_50MS
    MEASUREMENT_RATE_100MS = MEASUREMENT_RATE_100MS
    MEASUREMENT_RATE_500MS = MEASUREMENT_RATE_500MS
    MEASUREMENT_RATE_1000MS = MEASUREMENT_RATE_1000MS
    MEASUREMENT_RATE_2000MS = MEASUREMENT_RATE_2000MS

    GAIN_1X = GAIN_1X
    GAIN_3X = GAIN_3X
    GAIN_6X = GAIN_6X
    GAIN_9X = GAIN_9X
    GAIN_18X = GAIN_18X

    def __init__(self, bus=1, address=None, window_factor=1.0):
        if address is not None:
            self.SENSOR_ADDRESS = address

        import smbus2

        self.bus = smbus2.SMBus(bus)
        self.window_factor = float(window_factor)
        self.values = {
            "light": None,
            "raw": None,
        }
        self._resolution = RESOLUTION_18BIT
        self._measurement_rate = MEASUREMENT_RATE_100MS
        self._gain = GAIN_3X
        time.sleep(0.01)
        self.init_sensor()

    @classmethod
    def test(cls, bus=1, address=None):
        sensor_address = cls.SENSOR_ADDRESS if address is None else address
        try:
            import smbus2

            with smbus2.SMBus(bus) as i2c_bus:
                part_id = i2c_bus.read_byte_data(sensor_address, PART_ID)
            return (part_id & PART_ID_MASK) == PART_NUMBER_ID
        except Exception:
            return False

    def _read_byte(self, register):
        return self.bus.read_byte_data(self.SENSOR_ADDRESS, register)

    def _write_byte(self, register, value):
        self.bus.write_byte_data(self.SENSOR_ADDRESS, register, value & 0xFF)

    def init_sensor(self):
        self.set_measurement(RESOLUTION_18BIT, MEASUREMENT_RATE_100MS)
        self.gain = GAIN_3X
        self.active = True

    def soft_reset(self):
        self._write_byte(MAIN_CTRL, MAIN_CTRL_SW_RESET)
        time.sleep(0.01)
        self.init_sensor()

    def read(self):
        self.values["raw"] = self.raw
        self.values["light"] = self.lux

    @property
    def raw(self):
        data = self.bus.read_i2c_block_data(self.SENSOR_ADDRESS, ALS_DATA, 3)
        return ((data[2] & 0x0F) << 16) | (data[1] << 8) | data[0]

    @property
    def light(self):
        return self.raw

    @property
    def lux(self):
        gain = GAIN_FACTOR[self._gain]
        integration = RESOLUTION_INTEGRATION_FACTOR[self._resolution]
        return (
            0.6
            * self.raw
            / (gain * integration)
            * self.window_factor
        )

    @property
    def active(self):
        return bool(self._read_byte(MAIN_CTRL) & MAIN_CTRL_ALS_ENABLE)

    @active.setter
    def active(self, value):
        self._write_byte(MAIN_CTRL, MAIN_CTRL_ALS_ENABLE if value else 0x00)

    @property
    def gain(self):
        return self._gain

    @gain.setter
    def gain(self, value):
        if value not in GAIN_FACTOR:
            raise ValueError("invalid LTR-308ALS gain")
        self._write_byte(ALS_GAIN, value)
        self._gain = value

    @property
    def resolution(self):
        return self._resolution

    @resolution.setter
    def resolution(self, value):
        self.set_measurement(value, self._measurement_rate)

    @property
    def measurement_rate(self):
        return self._measurement_rate

    @measurement_rate.setter
    def measurement_rate(self, value):
        self.set_measurement(self._resolution, value)

    def set_measurement(self, resolution, measurement_rate):
        if resolution not in RESOLUTION_INTEGRATION_FACTOR:
            raise ValueError("invalid LTR-308ALS resolution")
        if measurement_rate not in (
            MEASUREMENT_RATE_25MS,
            MEASUREMENT_RATE_50MS,
            MEASUREMENT_RATE_100MS,
            MEASUREMENT_RATE_500MS,
            MEASUREMENT_RATE_1000MS,
            MEASUREMENT_RATE_2000MS,
        ):
            raise ValueError("invalid LTR-308ALS measurement rate")

        self._write_byte(ALS_MEAS_RATE, (resolution << 4) | measurement_rate)
        self._resolution = resolution
        self._measurement_rate = measurement_rate

    @property
    def status(self):
        return self._read_byte(MAIN_STATUS)

    @property
    def data_ready(self):
        return bool(self.status & 0x08)


if __name__ == "__main__":
    sensor = LTR308ALS()
    while True:
        print(f"Light: {sensor.lux:.1f} lux")
        time.sleep(1)
