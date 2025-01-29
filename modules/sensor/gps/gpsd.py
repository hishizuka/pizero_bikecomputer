import os
from datetime import datetime, timezone

from modules.app_logger import app_logger
from .base import AbstractSensorGPS

_SENSOR_GPS_AIOGPS = False
_SENSOR_GPS_GPS = False
_SENSOR_GPS_GPS3 = False
_SENSOR_GPS_GPSD = False  # To be deprecated in the next Debian (trixie)
_SENSER_GPS_STR = ""

try:
    raise Exception
    from gps import aiogps
    _SENSOR_GPS_AIOGPS = True
    _SENSOR_GPS_GPSD = True
    _SENSER_GPS_STR = "AIOGPS"
except:
    try:
        raise Exception
        from gps import gps
        from gps.watch_options import WATCH_ENABLE
        
        _SENSOR_GPS_GPS = True
        _SENSOR_GPS_GPSD = True
        _SENSER_GPS_STR = "GPS"
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


class GPSD(AbstractSensorGPS):
    gps_thread = None

    valid_cutoff_ep = None

    def sensor_init(self):
        if _SENSOR_GPS_GPS3:
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

    def init_data(self):
        data = {}
        for key in [
            'lat', 'lon', 'alt', 'speed', 'track', 
            'mode', 'status', 
            'epx', 'epy', 'epv', 'pdop', 'hdop', 'vdop', 
            'uSat', 'nSat', 'time'
        ]:
            data[key] = self.NULL_VALUE
        return data

    async def set_data(self, msg, data):
        if msg['class'] not in ['TPV', 'SKY']:
            return False
        if msg['class'] == 'SKY' and 'satellites' not in msg:
            return False

        for key in msg:
            if key in ('class', 'device'):
                continue
            data[key] = msg[key]
        await self.get_basic_values(
            data['lat'],
            data['lon'],
            data['alt'],
            data['speed'],
            data['track'],
            data['mode'],
            data['status'],
            [data['epx'], data['epy'], data['epv']],
            [data['pdop'], data['hdop'], data['vdop']],
            (data['uSat'], data['nSat']),
            data['time'],
        )
        return True

    async def update(self):
        if self.config.G_DUMMY_OUTPUT:
            await self.output_dummy()
            return

        if _SENSOR_GPS_AIOGPS:
            async with aiogps.aiogps() as gpsd:
                data = self.init_data()
                async for msg in gpsd:
                    if not await self.set_data(msg, data):
                        continue
                    if self.quit_status:
                        break
        elif _SENSOR_GPS_GPS:
            data = self.init_data()
            gpsd = gps(mode=WATCH_ENABLE)
            skip_sleep = False
            skip_get_sleep_time = True
            for msg in gpsd:
                if not skip_sleep:
                    await self.sleep()
                if not await self.set_data(msg, data):
                    continue
                if self.quit_status:
                    break
                if not skip_get_sleep_time:
                    self.get_sleep_time()
                skip_sleep = not skip_sleep
                skip_get_sleep_time = not skip_get_sleep_time
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
            if None in error or any(
                [x >= self.valid_cutoff_ep[i] for i, x in enumerate(dop)]
            ):
                valid = False
            # special condition #1
            elif (
                satellites[0] < self.config.G_GPSD_PARAM["SP1_USED_SATS_CUTOFF"]
                and epv > self.config.G_GPSD_PARAM["SP1_EPV_CUTOFF"]
            ):
                valid = False
        return valid
