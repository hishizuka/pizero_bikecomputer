import time


# Vishay VCNL4040 ambient light and proximity sensor.
# https://www.vishay.com/docs/84274/vcnl4040.pdf

ALS_CONF = 0x00
PS_CONF1_CONF2 = 0x03
PS_CONF3_MS = 0x04
PS_DATA = 0x08
ALS_DATA = 0x09
WHITE_DATA = 0x0A
DEVICE_ID = 0x0C

DEVICE_ID_VALUE = 0x0186

ALS_80MS = 0
ALS_160MS = 1
ALS_320MS = 2
ALS_640MS = 3

ALS_SENSITIVITY = {
    ALS_80MS: 0.10,
    ALS_160MS: 0.05,
    ALS_320MS: 0.025,
    ALS_640MS: 0.0125,
}


class VCNL4040:
    SENSOR_ADDRESS = 0x60
    TEST_ADDRESS = DEVICE_ID
    TEST_VALUE = (DEVICE_ID_VALUE,)

    elements = ("light", "proximity", "white")

    ALS_80MS = ALS_80MS
    ALS_160MS = ALS_160MS
    ALS_320MS = ALS_320MS
    ALS_640MS = ALS_640MS

    def __init__(self, bus=1, address=None):
        if address is not None:
            self.SENSOR_ADDRESS = address

        import smbus2

        self.bus = smbus2.SMBus(bus)
        self.values = {
            "light": None,
            "proximity": None,
            "white": None,
        }
        self._light_integration_time = ALS_80MS
        time.sleep(0.01)
        self.init_sensor()

    @classmethod
    def test(cls, bus=1, address=None):
        sensor_address = cls.SENSOR_ADDRESS if address is None else address
        try:
            import smbus2

            with smbus2.SMBus(bus) as i2c_bus:
                device_id = cls._read_word_from_bus(i2c_bus, sensor_address, DEVICE_ID)
            return device_id in cls.TEST_VALUE
        except Exception:
            return False

    @staticmethod
    def _read_word_from_bus(i2c_bus, sensor_address, register):
        data = i2c_bus.read_i2c_block_data(sensor_address, register, 2)
        return data[0] | (data[1] << 8)

    @staticmethod
    def _write_word_to_bus(i2c_bus, sensor_address, register, value):
        i2c_bus.write_i2c_block_data(
            sensor_address,
            register,
            [value & 0xFF, (value >> 8) & 0xFF],
        )

    def _read_word(self, register):
        return self._read_word_from_bus(self.bus, self.SENSOR_ADDRESS, register)

    def _write_word(self, register, value):
        self._write_word_to_bus(self.bus, self.SENSOR_ADDRESS, register, value)

    def _update_word_bits(self, register, mask, value):
        current = self._read_word(register)
        updated = (current & ~mask) | (value & mask)
        self._write_word(register, updated)
        return updated

    def init_sensor(self):
        conf = self._read_word(ALS_CONF)
        self._light_integration_time = (conf >> 6) & 0x03

        self.light_shutdown = False
        self.proximity_shutdown = True

    def read(self):
        self.values["light"] = self.lux
        self.values["proximity"] = self.proximity
        self.values["white"] = self.white

    @property
    def light(self):
        return self._read_word(ALS_DATA)

    @property
    def lux(self):
        return self.light * ALS_SENSITIVITY[self._light_integration_time]

    @property
    def white(self):
        sensitivity = ALS_SENSITIVITY[self._light_integration_time]
        return self._read_word(WHITE_DATA) * sensitivity

    @property
    def proximity(self):
        return self._read_word(PS_DATA)

    @property
    def light_integration_time(self):
        return self._light_integration_time

    @light_integration_time.setter
    def light_integration_time(self, value):
        if value not in ALS_SENSITIVITY:
            raise ValueError("invalid VCNL4040 ALS integration time")

        self._update_word_bits(ALS_CONF, 0x00C0, value << 6)
        self._light_integration_time = value

    @property
    def light_shutdown(self):
        return bool(self._read_word(ALS_CONF) & 0x0001)

    @light_shutdown.setter
    def light_shutdown(self, value):
        self._update_word_bits(ALS_CONF, 0x0001, 0x0001 if value else 0x0000)

    @property
    def proximity_shutdown(self):
        return bool(self._read_word(PS_CONF1_CONF2) & 0x0001)

    @proximity_shutdown.setter
    def proximity_shutdown(self, value):
        self._update_word_bits(
            PS_CONF1_CONF2,
            0x0001,
            0x0001 if value else 0x0000,
        )

    @property
    def white_shutdown(self):
        return bool(self._read_word(PS_CONF3_MS) & 0x8000)

    @white_shutdown.setter
    def white_shutdown(self, value):
        self._update_word_bits(
            PS_CONF3_MS,
            0x8000,
            0x8000 if value else 0x0000,
        )


if __name__ == "__main__":
    sensor = VCNL4040()
    while True:
        print(f"Light: {sensor.lux:.1f} lux, Proximity: {sensor.proximity}")
        time.sleep(1)
