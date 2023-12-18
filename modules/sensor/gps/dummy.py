import asyncio
from datetime import datetime

import numpy as np

from modules.utils.geo import calc_azimuth, get_track_str
from .base import AbstractSensorGPS


class Dummy_GPS(AbstractSensorGPS):
    LOG_SPEED = 5
    COURSE_DIVIDE_FACTOR = 500
    COURSE_RAND_FACTOR = 0.5  # np.random.randint(0,10)/10

    @property
    def is_real(self):
        return False

    def set_position_from_log(self, current_position):
        self.values["lat"] = current_position[0]
        self.values["lon"] = current_position[1]
        self.values["distance"] = current_position[2]
        self.values["track"] = current_position[3]
        if self.values["lat"] is None or self.values["lon"] is None:
            self.values["lat"] = np.nan
            self.values["lon"] = np.nan
        if self.values["track"] is None:
            self.values["track"] = self.values["pre_track"]
            self.values["track_str"] = get_track_str(self.values["track"])

    def set_position_from_course(self, course, idx):
        lat = course.latitude
        lon = course.longitude
        dist = course.distance * 1000

        self.values["lat"] = lat[idx]
        self.values["lon"] = lon[idx]
        self.values["distance"] = dist[idx]

        if idx + 1 < len(lat):
            self.values["lat"] += (lat[idx + 1] - lat[idx]) * self.COURSE_RAND_FACTOR
            self.values["lon"] += (lon[idx + 1] - lon[idx]) * self.COURSE_RAND_FACTOR
            self.values["distance"] += (
                dist[idx + 1] - dist[idx]
            ) * self.COURSE_RAND_FACTOR
        self.values["track"] = int(
            (
                calc_azimuth(
                    [self.values["pre_lat"], self.values["lat"]],
                    [self.values["pre_lon"], self.values["lon"]],
                )
            )[0]
        )
        if not np.isnan(self.values["track"]):
            self.values["track_str"] = get_track_str(self.values["track"])

    async def update(self):
        if not self.config.G_DUMMY_OUTPUT:
            return
        course_i = pre_course_i = 0

        try:
            while True:
                await self.sleep()

                if self.config.logger is None or (
                    not self.config.logger.course.is_set
                    and self.config.logger.position_log.shape[0] == 0
                ):
                    continue

                # unit: m/s
                # self.values['speed'] = random.randint(1,6) * 3.6
                self.values["speed"] = np.random.randint(13, 83) / 10  # 5 - 30km/h

                self.values["pre_lat"] = self.values["lat"]
                self.values["pre_lon"] = self.values["lon"]
                self.values["pre_track"] = self.values["track"]

                # generate dummy position from log
                if self.config.logger.position_log.shape[0] > 0:
                    self.set_position_from_log(
                        self.config.logger.position_log[course_i]
                    )

                    if course_i == pre_course_i:
                        course_i += 1 * self.LOG_SPEED
                        continue
                    else:
                        pre_course_i = course_i
                        course_i += 1 * self.LOG_SPEED
                        if course_i >= len(self.config.logger.position_log):
                            course_i = pre_course_i = 0
                            continue

                # from course
                else:
                    # TODO No need to do this for each loop, unless the course can be changed in between  ?
                    course_n = len(self.config.logger.course.latitude)

                    self.set_position_from_course(
                        self.config.logger.course, course_i
                    )

                    pre_course_i = course_i
                    course_i += int(course_n / self.COURSE_DIVIDE_FACTOR) + 1
                    if course_i >= course_n:
                        pre_course_i = 0
                        course_i = course_i % course_n

                self.config.logger.course.get_index(
                    self.values["lat"],
                    self.values["lon"],
                    self.values["track"],
                    self.config.G_GPS_SEARCH_RANGE,
                    self.config.G_GPS_ON_ROUTE_CUTOFF,
                    self.azimuth_cutoff,
                )

                self.values["timestamp"] = datetime.now()
                self.get_sleep_time(self.config.G_GPS_INTERVAL)

        except asyncio.CancelledError:
            pass
