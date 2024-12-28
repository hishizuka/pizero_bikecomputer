import asyncio
import os
from datetime import datetime, timezone

from logger import app_logger
from .base import AbstractSensorGPS

_SENSOR_GPS_AIOGPS = False
_SENSOR_GPS_GPSD = False  # To be deprecated in the next Debian (trixie) 

try:
    import gps.aiogps
    _SENSOR_GPS_AIOGPS = True
    _SENSOR_GPS_GPSD = True
    app_logger.info("_SENSOR_GPS_AIOGPS")
except:
    try:
        from gps3 import agps3threaded
        from gps3.misc import satellites_used

        # device test
        _gps3_thread = agps3threaded.AGPS3mechanism()
        _SENSOR_GPS_GPSD = True
        app_logger.info("_SENSOR_GPS_GPSD")
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
        if _SENSOR_GPS_AIOGPS:
            pass
        else:
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
        if _SENSOR_GPS_AIOGPS:
            pass
        else:
            self.gps_thread.stop()

    async def update(self):
        if self.config.G_DUMMY_OUTPUT:
            await self.output_dummy()
            return

        if _SENSOR_GPS_AIOGPS:
            async with gps.aiogps.aiogps() as gpsd:
                data = {}
                for key in [
                    'lat', 'lon', 'alt', 'speed', 'track', 
                    'mode', 'status', 
                    'epx', 'epy', 'epv', 'pdop', 'hdop', 'vdop', 
                    'uSat', 'nSat', 'time'
                ]:
                    data[key] = 'n/a'

                async for msg in gpsd:
                    if msg['class'] not in ['TPV', 'SKY']:
                        continue

                    for key in msg:
                        if key in ('class', 'device'):
                            continue
                        data[key] = msg[key]
                    if msg['class'] == 'TPV':
                        pass
                    elif msg['class'] == 'SKY':
                        pass
                    
                    gps_time = self.NULL_VALUE
                    if data['time'] != self.NULL_VALUE:
                        gps_time = datetime.strptime(data['time'], "%Y-%m-%dT%X.%fZ").replace(
                            tzinfo=timezone.utc
                        )
                    await self.get_basic_values(
                        data['lat'],
                        data['lon'],
                        data['alt'],
                        data['speed'],
                        data['track'],
                        data['mode'],
                        data['status'],
                        [data['epx'], data['epy'], data['epv']], # epx, epy is missing
                        [data['pdop'], data['hdop'], data['vdop']],
                        (data['uSat'], data['nSat']),
                        data['time'],
                    )
                    if self.quit_status:
                        break
        else:
            g = self.gps_thread.data_stream
            while not self.quit_status:
                await self.sleep()
                total, used = satellites_used(g.satellites)
                gps_time = self.NULL_VALUE
                if g.time != self.NULL_VALUE:
                    gps_time = datetime.strptime(g.time, "%Y-%m-%dT%X.%fZ").replace(
                        tzinfo=timezone.utc
                    )
                await self.get_basic_values(
                    g.lat,
                    g.lon,
                    g.alt,
                    g.speed,
                    g.track,
                    g.mode,
                    None,  # g.status (add in gps3)
                    [g.epx, g.epy, g.epv],
                    [g.pdop, g.hdop, g.vdop],
                    (used, total),
                    gps_time,
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
