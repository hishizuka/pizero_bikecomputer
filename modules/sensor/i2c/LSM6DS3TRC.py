import math
import struct
import time

# https://www.st.com/resource/en/datasheet/lsm6ds3tr-c.pdf
WHO_AM_I = 0x0F
CTRL1_XL = 0x10
CTRL2_G = 0x11
CTRL3_C = 0x12
OUTX_L_G = 0x22
OUTX_L_XL = 0x28


class LSM6DS3TRC:
    """Read acceleration in g and angular velocity in rad/s over I2C."""

    SENSOR_ADDRESS = 0x6A
    CHIP_ID = 0x6A

    def __init__(self, bus=1, address=0x6A):
        import smbus2

        self.address = address
        self.bus = smbus2.SMBus(bus)
        try:
            chip_id = self.bus.read_byte_data(self.address, WHO_AM_I)
            if chip_id != self.CHIP_ID:
                raise ValueError(f"Unexpected LSM6DS3TR-C chip ID: 0x{chip_id:02x}")
            self.bus.write_byte_data(self.address, CTRL3_C, 0x01)
            for _ in range(20):
                time.sleep(0.01)
                if not self.bus.read_byte_data(self.address, CTRL3_C) & 0x01:
                    break
            else:
                raise TimeoutError("LSM6DS3TR-C reset timed out")
            # Block data update, address increment, little-endian output.
            self.bus.write_byte_data(self.address, CTRL3_C, 0x44)
            # 12.5 Hz, accelerometer +/-2 g, gyroscope +/-125 dps.
            self.bus.write_byte_data(self.address, CTRL1_XL, 0x10)
            self.bus.write_byte_data(self.address, CTRL2_G, 0x12)
        except Exception:
            self.bus.close()
            raise

    def _read_vector(self, register, scale):
        data = self.bus.read_i2c_block_data(self.address, register, 6)
        return tuple(value * scale for value in struct.unpack("<hhh", bytes(data)))

    @property
    def acceleration(self):
        # +/-2 g sensitivity: 0.061 mg/LSB.
        return self._read_vector(OUTX_L_XL, 0.000061)

    @property
    def gyro(self):
        # +/-125 dps sensitivity: 4.375 mdps/LSB.
        return self._read_vector(OUTX_L_G, math.radians(0.004375))

    def close(self):
        try:
            self.bus.write_byte_data(self.address, CTRL1_XL, 0x00)
            self.bus.write_byte_data(self.address, CTRL2_G, 0x00)
        finally:
            self.bus.close()
