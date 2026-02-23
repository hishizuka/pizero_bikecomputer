import abc
import asyncio
import time as time_module
from datetime import datetime, time

import numpy as np

from modules.app_logger import app_logger
from modules.sensor.sensor import Sensor
from modules.utils.geo import get_dist_on_earth, get_track_str, calc_azimuth
from modules.utils.time import set_time, set_timezone

USED_SAT_CUTOFF = 3
HDOP_CUTOFF_MODERATE = 10.0
HDOP_CUTOFF_FAIR = 20.0

NMEA_MODE_UNKNOWN = 0
NMEA_MODE_NO_FIX = 1
NMEA_MODE_2D = 2
NMEA_MODE_3D = 3


class AbstractSensorGPS(Sensor, metaclass=abc.ABCMeta):
    elements = [
        "lat",
        "lon",
        "alt",
        "raw_lat",
        "raw_lon",
        "raw_alt",
        "pre_lat",
        "pre_lon",
        "pre_alt",
        "pre_track",
        "speed",
        "track",
        "track_str",
        "used_sats",
        "total_sats",
        "used_sats_str",
        "epx",
        "epy",
        "epv",
        "pdop",
        "hdop",
        "vdop",
        "time",
        "utctime",
        "mode",
        "status",
    ]
    # status: 
    #    0=Unknown,
    #    1=Normal,
    #    2=DGPS,
    #    3=RTK Fixed,
    #    4=RTK Floating,
    #    5=DR,
    #    6=GNSSDR,
    #    7=Time (surveyed),
    #    8=Simulated,
    #    9=P(Y)

    is_time_modified = False
    is_fixed = False
    is_altitude_modified = False
    course_index_check = []
    azimuth_cutoff = [0, 360]
    datetime_format = "%Y/%m/%d %H:%M:%S +0000"

    NULL_VALUE = None

    valid_cutoff_dof = (99.0, 99.0, 99.0)

    quit_status = False
    _TIME_SYNC_RETRY_SEC = 10.0

    @property
    def is_real(self):
        return True  # only dummy is not a real GPS

    def sensor_init(self):
        self.reset()
        self._utc_time_task = None
        self._utc_time_pending = None
        self._utc_time_event = None
        self._time_sync_next_allowed = 0.0

        for element in self.elements:
            self.values[element] = np.nan

        self.azimuth_cutoff = [
            self.config.G_GPS_AZIMUTH_CUTOFF,
            360 - self.config.G_GPS_AZIMUTH_CUTOFF,
        ]
        self.config.G_DUMMY_POS_X = self.config.state.get_value("pos_lon", self.config.G_DUMMY_POS_X)
        self.config.G_DUMMY_POS_Y = self.config.state.get_value("pos_lat", self.config.G_DUMMY_POS_Y)

    def reset(self):
        self.values["distance"] = 0

    async def quit(self):
        self.quit_status = True
        if self._utc_time_task is not None and not self._utc_time_task.done():
            self._utc_time_task.cancel()
        await self.sleep()

    def start_coroutine(self):
        asyncio.create_task(self.start())

    async def start(self):
        await self.update()

    @abc.abstractmethod
    async def update(self):
        pass

    def is_null_value(self, value):
        return value == self.NULL_VALUE

    def init_values(self):
        # backup values
        if not np.isnan(self.values["lat"]) and not np.isnan(self.values["lon"]):
            self.values["pre_lat"] = self.values["lat"]
            self.values["pre_lon"] = self.values["lon"]
            self.values["pre_alt"] = self.values["alt"]
            self.values["pre_track"] = self.values["track"]
        # initialize
        for element in self.elements:
            if element in ["pre_lat", "pre_lon", "pre_alt", "pre_track"]:
                continue
            self.values[element] = np.nan

    def is_position_valid(self, lat, lon, mode, status, dop, satellites, error=None):
        valid = True
        if (
            lat is None
            or lon is None
            or type(lon) != float
            or type(lat) != float
            or abs(lat) > 90
            or abs(lon) > 180
            or mode is None
            or mode < NMEA_MODE_3D
            or None in dop
            or any([self.is_null_value(x) for x in dop])
            or any([x >= self.valid_cutoff_dof[i] for i, x in enumerate(dop)])
            or (not self.check_3DGPS_FIX_status(status) and satellites[0] <= USED_SAT_CUTOFF)
        ):
            valid = False
        else:
            if type(lon) != float or type(lat) != float:
                app_logger.error(f"GPS lon&lat are not float: {lon}, {type(lon)}, {lat}, {type(lat)}, {mode}, {dop}, {satellites}")

        return valid
    
    def check_3DGPS_FIX_status(self, status):
        if self.is_null_value(status):
            return False
        else:
            # 3D DGPS FIX
            if status in [2, ]:
                return True
            else:
                return False

    async def get_basic_values(
        self, lat, lon, alt, speed, track, mode, status, error, dop, satellites, gps_time
    ):
        # TODO, this probably has to go in the long term
        self.init_values()

        # our first task is to align the format for each null value, we do it only for GPS
        # that do not use None as NULL_VALUE already, else the values are already correct.
        # (Maybe it could be done on the sensor implementation itself)
        if self.NULL_VALUE is not None:

            def id_or_none(value):
                if isinstance(value, tuple):
                    return [id_or_none(x) for x in value]
                else:
                    return value if not self.is_null_value(value) else None

            lat = id_or_none(lat)
            lon = id_or_none(lon)
            alt = id_or_none(alt)
            speed = id_or_none(speed)
            track = id_or_none(track)
            mode = id_or_none(mode)
            status = id_or_none(status)
            error = id_or_none(error)
            dop = id_or_none(dop)
            # no need to check for satellites, manually computed

        valid_pos = self.is_position_valid(lat, lon, mode, status, dop, satellites, error)

        # coordinate
        if valid_pos:
            self.values["lat"] = lat
            self.values["lon"] = lon
        else:  # copy from pre value
            self.values["lat"] = self.values["pre_lat"]
            self.values["lon"] = self.values["pre_lon"]
        for l in ["lat", "lon"]:
            if np.isnan(self.values[l]) and type(self.values[l]) != float:
                self.values[l] = np.nan
        # raw coordinates
        self.values["raw_lat"] = lat
        self.values["raw_lon"] = lon
        # record coordinates in state
        if not np.any(np.isnan([self.values["lat"], self.values["lon"]])):
            self.config.state.set_value("pos_lat", self.values["lat"])
            self.config.state.set_value("pos_lon", self.values["lon"])

        # GPS distance
        if self.config.G_STOPWATCH_STATUS == "START" and not np.any(
            np.isnan(
                [
                    self.values["pre_lon"],
                    self.values["pre_lat"],
                    self.values["lon"],
                    self.values["lat"],
                ]
            )
        ):
            # 2D distance : (x1, y1), (x2, y2)
            dist = get_dist_on_earth(
                self.values["pre_lon"],
                self.values["pre_lat"],
                self.values["lon"],
                self.values["lat"],
            )
            # need 3D distance? : (x1, y1, z1), (x2, y2, z2)

            # unit: m
            self.values["distance"] += dist
        
        # altitude
        if valid_pos and alt is not None:
            # floor
            if alt < -500:
                self.values["alt"] = -500
            else:
                self.values["alt"] = alt
        else:  # copy from pre value
            self.values["alt"] = self.values["pre_alt"]
        self.values["raw_alt"] = alt

        # speed
        if valid_pos and speed is not None:
            # unit m/s
            if speed <= self.config.G_GPS_SPEED_CUTOFF:
                self.values["speed"] = 0.0
            else:
                self.values["speed"] = speed

        # track
        if (
            valid_pos
            and track is not None
            and speed is not None
            and speed > self.config.G_GPS_SPEED_CUTOFF
        ):
            self.values["track"] = int(track)
            self.values["track_str"] = get_track_str(self.values["track"])
        # for GPS unable to get track
        elif (
            valid_pos
            and track is None
            and speed is not None
            and speed > self.config.G_GPS_SPEED_CUTOFF
        ):
            self.values["track"] = int(
                (
                    calc_azimuth(
                        [self.values["pre_lat"], self.values["lat"]],
                        [self.values["pre_lon"], self.values["lon"]],
                    )
                )[0]
            )
            self.values["track_str"] = get_track_str(self.values["track"])
        else:
            self.values["track"] = self.values["pre_track"]

        # distance in the course
        self.course.get_index(
            self.values["lat"],
            self.values["lon"],
            self.values["track"],
            self.config.G_GPS_SEARCH_RANGE,
            self.config.G_GPS_ON_ROUTE_CUTOFF,
            self.azimuth_cutoff,
        )

        # timezone
        if valid_pos and not self.is_fixed:
            asyncio.create_task(set_timezone(lat, lon))
            self.is_fixed = True

        # gps time
        self.get_utc_time(gps_time, mode)

        # modify altitude with course
        if (
            not self.is_altitude_modified
            and self.course.index.on_course_status
            and len(self.course.altitude)
        ):
            await self.config.logger.sensor.sensor_i2c.update_sealevel_pa(
                self.config.logger.course.altitude[self.course.index.value]
            )
            self.is_altitude_modified = True

        # mode
        self.values["mode"] = mode

        # satellites
        self.values["used_sats"] = satellites[0]
        self.values["total_sats"] = satellites[1]
        if satellites[1] is not None:
            self.values["used_sats_str"] = f"{satellites[0]} / {satellites[1]}"
        else:
            self.values["used_sats_str"] = f"{satellites[0]}"

        # DOP
        for i, key in enumerate(["pdop", "hdop", "vdop"]):
            self.values[key] = dop[i]

        # TODO, save error for gpsd, could be improved, not very resilient
        if error:
            for i, key in enumerate(["epx", "epy", "epv"]):
                self.values[key] = error[i]
        
        # timestamp
        self.values["timestamp"] = datetime.now()

    async def _utc_time_worker(self):
        # Run UTC time parsing and system time sync in a thread to keep the main asyncio loop responsive.
        while not self.quit_status:
            try:
                await self._utc_time_event.wait()
            except asyncio.CancelledError:
                raise

            self._utc_time_event.clear()

            while True:
                pending = self._utc_time_pending
                if pending is None:
                    break
                self._utc_time_pending = None
                gps_time, mode = pending
                try:
                    await asyncio.to_thread(self._update_utc_time_sync, gps_time, mode)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    app_logger.exception("Failed to update UTC time")

    def _update_utc_time_sync(self, gps_time, mode=None):
        # NOTE: This function is executed in a worker thread.
        if self.is_null_value(gps_time):
            return

        if isinstance(gps_time, datetime):
            gps_time = gps_time.isoformat()
        # instance time is to handle pa1010d lib (v0.0.4?),
        # by default it was retuning 1970-01-01 as a date:
        # we keep this logic so it will return later and not try to set the time
        elif isinstance(gps_time, time):
            gps_time = f"1970-01-01T{gps_time.isoformat()}+00:00"
        elif not isinstance(gps_time, str):
            gps_time = str(gps_time)

        self.values["time"] = gps_time
        self.values["utctime"] = gps_time[11:16]  # [11:19] for HH:MM:SS

        # for ublox error
        # ValueError: ('Unknown string format:', '1970-01-01T00:00:00(null')
        # if self.values['time'].find('1970-01-01') >= 0:
        if gps_time[0:4].isdecimal() and int(gps_time[0:4]) < 2000:
            return

        if self.is_time_modified:
            return

        # Avoid expensive system time sync attempts until we have a 3D fix.
        # Some receivers output a plausible UTC timestamp before a full fix.
        try:
            mode_int = int(mode) if mode is not None else None
        except (TypeError, ValueError):
            mode_int = None
        if mode_int is None or mode_int < NMEA_MODE_3D:
            return

        # Throttle time sync attempts to keep the system responsive.
        now = time_module.monotonic()
        if now < self._time_sync_next_allowed:
            return
        self._time_sync_next_allowed = now + self._TIME_SYNC_RETRY_SEC

        try:
            ok = set_time(gps_time)
        except Exception:
            app_logger.exception("Failed to set time")
            ok = False
        if ok:
            self.is_time_modified = True

    def get_utc_time(self, gps_time, mode=None):
        # Schedule UTC time handling in a background thread.
        if self.is_null_value(gps_time):
            return
        self._utc_time_pending = (gps_time, mode)
        if self._utc_time_event is None:
            self._utc_time_event = asyncio.Event()
        if self._utc_time_task is None or self._utc_time_task.done():
            self._utc_time_task = asyncio.create_task(self._utc_time_worker())
        self._utc_time_event.set()

    async def output_dummy(self):
        from .dummy import Dummy_GPS
        await Dummy_GPS(self.config, self.values).update()
