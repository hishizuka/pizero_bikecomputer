import os
import shutil
import json
import asyncio
import math

from modules.app_logger import app_logger
from .base import AbstractSensorGPS
from modules.utils.cmd import exec_cmd_return_value

_SENSOR_GPS_AIOGPS = False
_SENSOR_GPS_GPS3 = False  # To be deprecated in the next Debian (trixie)
_SENSOR_GPS_GPSD = False  # To be deprecated in the next Debian (trixie)
_SENSER_GPS_STR = ""

try:
    #raise Exception
    from gps import aiogps
    from gps.gps import MODE_SET
    _SENSOR_GPS_AIOGPS = True
    _SENSOR_GPS_GPSD = True
    _SENSER_GPS_STR = "AIOGPS"
except:
    try:
        from gps3 import agps3threaded
        from gps3.misc import satellites_used

        # device test
        _gps3_thread = agps3threaded.AGPS3mechanism()
        _SENSOR_GPS_GPS3 = True
        _SENSOR_GPS_GPSD = True
        _SENSER_GPS_STR = "GPS3"
    except ImportError:
        pass
    except Exception:  # noqa
        app_logger.exception("Failed to init GPS_GPSD")
        try:
            _gps3_thread.stop()
        except:
            pass

if _SENSOR_GPS_GPSD and shutil.which("gpspipe"):
    res, error = exec_cmd_return_value(["gpspipe", "-r", "-n", "2"], cmd_print=False)
    if res:
        message = json.loads(res.split('\n')[1])
        devices = message.get('devices')
        if devices:
            app_logger.info(f"devices: {devices}")


class GPSD(AbstractSensorGPS):
    NULL_VALUE = float("nan") # for official gpsd client
    valid_cutoff_ep = None

    gps_thread = None
    
    def sensor_init(self):
        if _SENSOR_GPS_GPS3:
            self.NULL_VALUE = "n/a" # only for gps3
            self.gps_thread = _gps3_thread
            self.gps_thread.stream_data(
                host=os.environ.get("GPSD_HOST", agps3threaded.HOST),
                port=os.environ.get("GPSD_PORT", agps3threaded.GPSD_PORT),
            )
            self.gps_thread.run_thread()

        super().sensor_init()
        self.valid_cutoff_ep = (
            self.config.G_GPSD_PARAM["EPX_EPY_CUTOFF"],
            self.config.G_GPSD_PARAM["EPX_EPY_CUTOFF"],
            self.config.G_GPSD_PARAM["EPV_CUTOFF"],
        )

    async def quit(self):
        await super().quit()
        if _SENSOR_GPS_GPS3:
            self.gps_thread.stop()

    def is_null_value(self, value):
        if _SENSOR_GPS_GPS3:
            return super().is_null_value(value)
        else:
            if type(value) == float:
                return math.isnan(value)
            else:
                # for gps_time
                return value is None

    async def update(self):
        if self.config.G_DUMMY_OUTPUT:
            await self.output_dummy()
            return

        # https://gpsd.gitlab.io/gpsd/gpsd-client-example-code.html
        # https://gitlab.com/gpsd/gpsd/-/blob/master/gps/gps.py.in
        if _SENSOR_GPS_AIOGPS:
            async with aiogps.aiogps() as gpsd:
                while not self.quit_status:
                    await gpsd.read()
                    if not (MODE_SET & gpsd.valid):
                        continue
                    await self.get_basic_values(
                        gpsd.fix.latitude,
                        gpsd.fix.longitude,
                        gpsd.fix.altitude,
                        gpsd.fix.speed,
                        gpsd.fix.track,
                        gpsd.fix.mode,
                        gpsd.fix.status,
                        (gpsd.fix.epx, gpsd.fix.epy, gpsd.fix.epv),
                        (gpsd.pdop, gpsd.hdop, gpsd.vdop),
                        (gpsd.satellites_used, len(gpsd.satellites)),
                        gpsd.utc,
                    )
                    await asyncio.sleep(0.2)

        elif _SENSOR_GPS_GPS3:
            g = self.gps_thread.data_stream
            while not self.quit_status:
                await self.sleep()
                total, used = satellites_used(g.satellites)
                await self.get_basic_values(
                    g.lat,
                    g.lon,
                    g.alt,
                    g.speed,
                    g.track,
                    g.mode,
                    None,  # status
                    [g.epx, g.epy, g.epv],
                    [g.pdop, g.hdop, g.vdop],
                    (used, total),
                    g.time,
                )
                self.get_sleep_time()

    def is_position_valid(self, lat, lon, mode, status, dop, satellites, error=None):
        valid = super().is_position_valid(lat, lon, mode, status, dop, satellites, error)
        if valid and error:
            epv = error[2]
            # special condition #1
            if None in error or any(
                [x >= self.valid_cutoff_ep[i] for i, x in enumerate(dop)]
            ):
                valid = False
            # special condition #2 (exclude 3D DGPS FIX)
            elif (
                not self.check_3DGPS_FIX_status(status)
                and satellites[0] < self.config.G_GPSD_PARAM["SP1_USED_SATS_CUTOFF"]
                and epv > self.config.G_GPSD_PARAM["SP1_EPV_CUTOFF"]
            ):
                valid = False
        return valid
