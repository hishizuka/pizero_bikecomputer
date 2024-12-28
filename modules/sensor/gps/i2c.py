import asyncio

from logger import app_logger
from .base import AbstractSensorGPS


_SENSOR_GPS_I2C = False
try:
    import pa1010d

    _sensor_i2c_gps = pa1010d.PA1010D()
    _sensor_i2c_gps.read_sentence(timeout=1)
    _SENSOR_GPS_I2C = True
except ImportError:
    pass
except Exception:  # noqa
    app_logger.exception("Failed to init GPS_I2C")


class GPS_I2C(AbstractSensorGPS):
    NULL_VALUE = None

    def is_null_value(self, value):
        return value is self.NULL_VALUE

    def sensor_init(self):
        self.i2c_gps = _sensor_i2c_gps
        super().sensor_init()

    async def update(self):
        if self.config.G_DUMMY_OUTPUT:
            await self.output_dummy()
            return
        
        g = self.i2c_gps

        while not self.quit_status:
            await self.sleep()

            result = g.update()
            if result:
                mode = (
                    int(g.data["mode_fix_type"])
                    if not self.is_null_value(g.data["mode_fix_type"])
                    else self.NULL_VALUE
                )
                speed = (
                    g.data["speed_over_ground"] * 1.852 / 3.6
                    if not self.is_null_value(g.data["speed_over_ground"])
                    else 0
                )
                dop = [
                    float(g.data[x])
                    if g.data[x] not in ["", self.NULL_VALUE]
                    else None
                    for x in ["pdop", "hdop", "vdop"]
                ]

                await self.get_basic_values(
                    g.data["latitude"],
                    g.data["longitude"],
                    g.data["altitude"],
                    speed,
                    self.NULL_VALUE,
                    mode,
                    None,
                    None,
                    dop,
                    (int(g.data["num_sats"] or 0), None),
                    g.data["timestamp"],  # this is a time object not a datetime
                )
            self.get_sleep_time()
