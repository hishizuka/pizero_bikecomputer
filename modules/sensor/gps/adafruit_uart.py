import asyncio

from logger import app_logger
from .base import AbstractSensorGPS


_SENSOR_GPS_ADAFRUIT_UART = False
try:
    import serial
    import adafruit_gps

    _uart = serial.Serial("/dev/ttyS0", baudrate=9600, timeout=10)
    _sensor_adafruit_gps = adafruit_gps.GPS(_uart, debug=False)
    _SENSOR_GPS_ADAFRUIT_UART = True
except:
    try:
        _uart.close()
    except:
        pass

if _SENSOR_GPS_ADAFRUIT_UART:
    app_logger.info("GPS_ADAFRUIT_UART")


class Adafruit_GPS(AbstractSensorGPS):
    NULL_VALUE = None

    def is_null_value(self, value):
        return value is self.NULL_VALUE

    def sensor_init(self):
        self.adafruit_gps = _sensor_adafruit_gps
        # (GPGLL), GPRMC, (GPVTG), GPGGA, GPGSA, GPGSV, (GPGSR), (GPGST)
        self.adafruit_gps.send_command(b"PMTK314,0,1,0,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0")
        self.adafruit_gps.send_command(b"PMTK220,1000")
        super().sensor_init()

    async def quit(self):
        await super().quit()
        _uart.close()

    # experimental code
    async def update(self):
        g = self.adafruit_gps

        try:
            while True:
                await self.sleep()

                for i in range(10):
                    if not g.update():
                        break
                    await asyncio.sleep(0.05)

                if g.has_fix:
                    speed = (
                        g.speed_knots * 1.852 / 3.6
                        if not self.is_null_value(g.speed_knots)
                        else 0
                    )
                    used, total = self.get_satellites(g.sats)
                    await self.get_basic_values(
                        g.latitude,
                        g.longitude,
                        g.altitude_m,
                        speed,
                        g.track_angle_deg,
                        g.fix_quality_3d,
                        None,
                        [g.pdop, g.hdop, g.vdop],
                        (used, total),
                        g.timestamp_utc,
                    )
                self.get_sleep_time()
        except asyncio.CancelledError:
            pass

    def get_satellites(self, gs):
        gnum = guse = 0

        if self.is_null_value(gs) or not len(gs):
            return 0, 0
        for v in gs.values():
            gnum += 1
            if not self.is_null_value(v[3]):
                guse += 1
        return guse, gnum
