import numpy as np

from modules.app_logger import app_logger
from modules.utils.crdp import rdp
from modules.utils.filters import savitzky_golay
from modules.utils.geo import calc_azimuth, get_dist_on_earth, get_dist_on_earth_array


def _categorize_slope(slope_smoothing, slope_cutoff):
    slope_smoothing_cat = np.zeros(len(slope_smoothing), dtype="uint8")

    for category in range(1, len(slope_cutoff)):
        lower = slope_cutoff[category - 1]
        upper = slope_cutoff[category]
        slope_smoothing_cat = np.where(
            (lower < slope_smoothing) & (slope_smoothing <= upper),
            category,
            slope_smoothing_cat,
        )

    return slope_smoothing_cat


class CourseProcessor:
    def downsample(self, update_search_range=True):
        len_lat = len(self.latitude)
        len_lon = len(self.longitude)
        len_alt = len(self.altitude)
        len_dist = len(self.distance)

        # empty check
        if not len_lat and not len_lon and not len_alt and not len_dist:
            return

        try:
            cond = np.array(
                rdp(
                    np.column_stack([self.longitude, self.latitude]),
                    epsilon=0.0001,
                    return_mask=True,
                )
            )
            if len_alt and len_dist:
                cond = cond | np.array(
                    rdp(
                        np.column_stack([self.distance, self.altitude]),
                        epsilon=10,
                        return_mask=True,
                    )
                )
            self.latitude = self.latitude[cond]
            self.longitude = self.longitude[cond]
            if len_alt:
                self.altitude = self.altitude[cond]  # [m]
            if len_dist:
                self.distance = self.distance[cond] / 1000  # [km]
        except Exception as e:  # noqa
            app_logger.warning(f"Error during downsampling: {e}")
            self.distance = self.distance / 1000  # [km]

        if not len_dist:
            self.distance = (
                get_dist_on_earth_array(
                    self.longitude[0:-1],
                    self.latitude[0:-1],
                    self.longitude[1:],
                    self.latitude[1:],
                )
                / 1000
            )
            self.distance = np.insert(self.distance, 0, 0)
            self.distance = np.cumsum(self.distance)
        if len_alt:
            modified_altitude = savitzky_golay(self.altitude, 53, 3)
            # do not apply if length is different (occurs when too short course)
            if len(self.altitude) == len(modified_altitude):
                self.altitude = modified_altitude

            # experimental code
            # np.savetxt('log/course_altitude.csv', self.altitude, fmt='%.3f')
            # np.savetxt('log/course_distance.csv', self.distance, fmt='%.3f')

            # output dem altitude
            # alt_dem = np.zeros(len(self.altitude))
            # for i in range(len(self.altitude)):
            #  alt_dem[i] = self.config.api.get_altitude([self.longitude[i], self.latitude[i]])
            # np.savetxt('log/course_altitude_dem.csv', alt_dem, fmt='%.3f')

        if update_search_range:
            self.update_search_range()

        app_logger.info(f"downsampling:{len_lat} -> {len(self.latitude)}")

    def update_search_range(self):
        if len(self.distance) < 2:
            return

        diff_dist_max = int(np.max(1000 * np.diff(self.distance))) * 2 / 1000
        if diff_dist_max > self.config.G_GPS_SEARCH_RANGE:
            self.config.G_GPS_SEARCH_RANGE = diff_dist_max

    # make route colors by slope for MapWidget, CourseProfileWidget
    def calc_slope_smoothing(self):
        # parameters
        course_n = len(self.distance)
        diff_num = 4
        LP_coefficient = 0.15

        self.colored_altitude = np.full(
            (course_n, 3), self.config.G_SLOPE_COLOR[0]
        )  # 3 is RGB

        if course_n < 2 * diff_num or len(self.altitude) < 2 * diff_num:
            return

        dist_diff = np.zeros((diff_num, course_n))
        alt_diff = np.zeros((diff_num, course_n))
        grade = np.zeros((diff_num, course_n))
        dist_diff[0, 1:] = self.distance[1:] - self.distance[0:-1]
        alt_diff[0, 1:] = self.altitude[1:] - self.altitude[0:-1]
        grade[0, 1:] = alt_diff[0, 1:] / (dist_diff[0, 1:] * 1000) * 100

        for i in range(1, diff_num):
            dist_diff[i, i:-i] = self.distance[2 * i :] - self.distance[0 : -2 * i]
            dist_diff[i, 0:i] = self.distance[i : 2 * i] - self.distance[0]
            dist_diff[i, -i:] = self.distance[-1] - self.distance[-2 * i : -i]
            alt_diff[i, i:-i] = self.altitude[2 * i :] - self.altitude[0 : -2 * i]
            alt_diff[i, 0:i] = self.altitude[i : 2 * i] - self.altitude[0]
            alt_diff[i, -i:] = self.altitude[-1] - self.altitude[-2 * i : -i]
            grade[i] = alt_diff[i] / (dist_diff[i] * 1000) * 100

        grade_mod = np.zeros(course_n)
        cond_all = np.full(course_n, False)

        for i in range(diff_num - 1):
            cond = dist_diff[i] >= self.config.G_CLIMB_DISTANCE_CUTOFF
            cond_diff = cond ^ cond_all
            grade_mod[cond_diff] = grade[i][cond_diff]
            cond_all = cond

        cond = np.full(course_n, True)
        cond_diff = cond ^ cond_all
        grade_mod[cond_diff] = grade[3][cond_diff]

        # apply LP filter (forward and backward)
        self.slope_smoothing = np.zeros(course_n)
        self.slope_smoothing[0] = grade_mod[0]
        self.slope_smoothing[-1] = grade_mod[-1]

        # forward
        for i in range(1, course_n - 1):
            self.slope_smoothing[i] = grade_mod[
                i
            ] * LP_coefficient + self.slope_smoothing[i - 1] * (1 - LP_coefficient)

        # backward
        for i in reversed(range(course_n - 1)):
            self.slope_smoothing[i] = self.slope_smoothing[
                i
            ] * LP_coefficient + self.slope_smoothing[i + 1] * (1 - LP_coefficient)

        # detect climbs
        slope_smoothing_cat = _categorize_slope(
            self.slope_smoothing,
            self.config.G_SLOPE_CUTOFF,
        )

        climb_search_state = False
        climb_start_cutoff = 2
        climb_end_cutoff = 1

        if slope_smoothing_cat[0] >= climb_start_cutoff:
            self.climb_segment.append(
                {
                    "start": 0,
                    "start_point_distance": self.distance[0],
                    "start_point_altitude": self.altitude[0],
                }
            )
            climb_search_state = True

        for i in range(1, course_n):
            # search climb end (detect top of climb)
            if (
                climb_search_state
                and slope_smoothing_cat[i - 1] >= climb_end_cutoff
                and (slope_smoothing_cat[i] < climb_end_cutoff or i == course_n - 1)
            ):
                end_index = i
                if slope_smoothing_cat[i] < climb_end_cutoff:
                    end_index -= 1
                if end_index <= self.climb_segment[-1]["start"]:
                    self.climb_segment.pop()
                    climb_search_state = False
                    continue
                self.climb_segment[-1]["end"] = end_index
                self.climb_segment[-1]["distance"] = (
                    self.distance[end_index]
                    - self.distance[self.climb_segment[-1]["start"]]
                )
                alt = (
                    self.altitude[end_index]
                    - self.altitude[self.climb_segment[-1]["start"]]
                )
                self.climb_segment[-1]["average_grade"] = (
                    alt / (self.climb_segment[-1]["distance"] * 1000) * 100
                )
                self.climb_segment[-1]["volume"] = (
                    self.climb_segment[-1]["distance"]
                    * 1000
                    * self.climb_segment[-1]["average_grade"]
                )
                self.climb_segment[-1]["course_point_distance"] = self.distance[
                    end_index
                ]
                self.climb_segment[-1]["course_point_altitude"] = self.altitude[
                    end_index
                ]
                self.climb_segment[-1]["course_point_longitude"] = self.longitude[
                    end_index
                ]
                self.climb_segment[-1]["course_point_latitude"] = self.latitude[
                    end_index
                ]
                if (
                    self.climb_segment[-1]["distance"]
                    < self.config.G_CLIMB_DISTANCE_CUTOFF
                    or self.climb_segment[-1]["average_grade"]
                    < self.config.G_CLIMB_GRADE_CUTOFF
                    or self.climb_segment[-1]["volume"]
                    < self.config.G_CLIMB_CATEGORY[0]["volume"]
                ):
                    # app_logger.debug(f"{self.climb_segment[-1]['distance']}, {self.climb_segment[-1]['volume']}, {self.climb_segment[-1]['distance']}, {self.climb_segment[-1]['average_grade']}")
                    self.climb_segment.pop()
                else:
                    for j in reversed(range(len(self.config.G_CLIMB_CATEGORY))):
                        if (
                            self.climb_segment[-1]["volume"]
                            >= self.config.G_CLIMB_CATEGORY[j]["volume"]
                        ):
                            self.climb_segment[-1]["cat"] = (
                                self.config.G_CLIMB_CATEGORY[j]["name"]
                            )
                            break
                climb_search_state = False
            # detect climb start
            elif (
                not climb_search_state
                and slope_smoothing_cat[i - 1] < climb_start_cutoff
                and slope_smoothing_cat[i] >= climb_start_cutoff
            ):
                self.climb_segment.append(
                    {
                        "start": i,
                        "start_point_distance": self.distance[i],
                        "start_point_altitude": self.altitude[i],
                    }
                )
                climb_search_state = True

        # app_logger.debug(self.climb_segment)
        self.colored_altitude = np.array(self.config.G_SLOPE_COLOR)[slope_smoothing_cat]

    def modify_course_points(self):
        if not self.config.G_COURSE_INDEXING:
            return

        self.azimuth = calc_azimuth(self.latitude, self.longitude)
        self.points_diff = np.array([np.diff(self.longitude), np.diff(self.latitude)])
        self.points_diff_sum_of_squares = (
            self.points_diff[0] ** 2 + self.points_diff[1] ** 2
        )
        self.points_diff_dist = np.sqrt(self.points_diff_sum_of_squares)

        course_points = self.course_points

        len_pnt_lat = len(course_points.latitude)
        len_pnt_dist = len(course_points.distance)
        len_pnt_alt = len(course_points.altitude)
        len_dist = len(self.distance)
        len_alt = len(self.altitude)

        # calculate course point distance/altitude if not both already set
        # If one is already set, it's not going to be overwritten
        # But if both are already set there's no need to recalculate anything
        if not len_pnt_dist or not len_pnt_alt:
            if not len_pnt_dist and len_dist:
                course_points.distance = np.empty(len_pnt_lat)
            if not len_pnt_alt and len_alt:
                course_points.altitude = np.zeros(len_pnt_lat)

            min_index = 0

            for i in range(len_pnt_lat):
                b_a_x = self.points_diff[0][min_index:]
                b_a_y = self.points_diff[1][min_index:]
                lon_diff = course_points.longitude[i] - self.longitude[min_index:]
                lat_diff = course_points.latitude[i] - self.latitude[min_index:]
                p_a_x = lon_diff[:-1]
                p_a_y = lat_diff[:-1]
                inner_p = (
                    b_a_x * p_a_x + b_a_y * p_a_y
                ) / self.points_diff_sum_of_squares[min_index:]
                inner_p_check = np.where(
                    (0.0 <= inner_p) & (inner_p <= 1.0), True, False
                )

                min_j = None
                min_dist_diff_h = np.inf
                min_dist_delta = 0
                min_alt_delta = 0

                for j in list(*np.where(inner_p_check)):
                    h_lon = (
                        self.longitude[min_index + j]
                        + (
                            self.longitude[min_index + j + 1]
                            - self.longitude[min_index + j]
                        )
                        * inner_p[j]
                    )
                    h_lat = (
                        self.latitude[min_index + j]
                        + (
                            self.latitude[min_index + j + 1]
                            - self.latitude[min_index + j]
                        )
                        * inner_p[j]
                    )
                    dist_diff_h = get_dist_on_earth(
                        h_lon,
                        h_lat,
                        course_points.longitude[i],
                        course_points.latitude[i],
                    )

                    if (
                        dist_diff_h < self.config.G_GPS_ON_ROUTE_CUTOFF
                        and dist_diff_h < min_dist_diff_h
                    ):
                        if min_j is not None and j - min_j > 2:
                            continue

                        min_j = j
                        min_dist_diff_h = dist_diff_h
                        min_dist_delta = (
                            get_dist_on_earth(
                                self.longitude[min_index + j],
                                self.latitude[min_index + j],
                                h_lon,
                                h_lat,
                            )
                            / 1000
                        )

                        if len_alt:
                            min_alt_delta = (
                                (
                                    self.altitude[min_index + j + 1]
                                    - self.altitude[min_index + j]
                                )
                                / (
                                    self.distance[min_index + j + 1]
                                    - self.distance[min_index + j]
                                )
                                * min_dist_delta
                            )

                if min_j is None:
                    min_j = 0

                min_index = min_index + min_j

                if not len_pnt_dist and len_dist:
                    course_points.distance[i] = (
                        self.distance[min_index] + min_dist_delta
                    )
                if not len_pnt_alt and len_alt:
                    course_points.altitude[i] = self.altitude[min_index] + min_alt_delta

        # add climb tops
        # if len(self.climb_segment):
        #  min_index = 0
        #  for i in range(len(self.climb_segment)):
        #    diff_dist = np.abs(course_points.distance - self.climb_segment[i]['course_point_distance'])
        #    min_index = np.where(diff_dist == np.min(diff_dist))[0][0]+1
        #    course_points.name.insert(min_index, "Top of Climb")
        #    course_points.latitude = np.insert(course_points._latitude, min_index, self.climb_segment[i]['course_point_latitude'])
        #    course_points.longitude = np.insert(course_points.longitude, min_index, self.climb_segment[i]['course_point_longitude'])
        #    course_points.type.insert(min_index, "Summit")
        #    course_points.distance = np.insert(course_points.distance, min_index, self.climb_segment[i]['course_point_distance'])
        #    course_points.altitude = np.insert(course_points.altitude, min_index, self.climb_segment[i]['course_point_altitude'])

        len_pnt_dist = len(course_points.distance)
        len_pnt_alt = len(course_points.latitude)

        # add start course point
        if (
            len_pnt_lat
            and len_pnt_dist
            and len_dist
            # TODO do not use float
            and course_points.distance[0] != 0.0
        ):
            app_logger.info(
                f"Missing start of the course point, first value is {course_points.distance[0]}, inserting"
            )
            course_points.name = np.insert(course_points.name, 0, "Start")
            course_points.latitude = np.insert(
                course_points.latitude, 0, self.latitude[0]
            )
            course_points.longitude = np.insert(
                course_points.longitude, 0, self.longitude[0]
            )
            course_points.type = np.insert(course_points.type, 0, "")
            course_points.notes = np.insert(course_points.notes, 0, "")
            if len_pnt_dist and len_dist:
                course_points.distance = np.insert(course_points.distance, 0, 0.0)
            if len_pnt_alt and len_alt:
                course_points.altitude = np.insert(
                    course_points.altitude, 0, self.altitude[0]
                )

        # add end course point
        end_distance = None
        if len(self.latitude) and len(course_points.longitude):
            end_distance = get_dist_on_earth(
                self.longitude[-1],
                self.latitude[-1],
                course_points.longitude[-1],
                course_points.latitude[-1],
            )
        if (
            len_pnt_lat
            and len_pnt_dist
            and len_dist
            and end_distance is not None
            and end_distance > 5
        ):
            app_logger.info(
                f"Missing end of the course point last distance is {end_distance}, inserting"
            )
            course_points.name = np.append(course_points.name, "End")
            course_points.latitude = np.append(
                course_points.latitude, self.latitude[-1]
            )
            course_points.longitude = np.append(
                course_points.longitude, self.longitude[-1]
            )
            course_points.type = np.append(course_points.type, "")
            course_points.notes = np.append(course_points.notes, "")
            if len_pnt_dist and len_dist:
                course_points.distance = np.append(
                    course_points.distance, self.distance[-1]
                )
            if len_pnt_alt and len_alt:
                course_points.altitude = np.append(
                    course_points.altitude, self.altitude[-1]
                )
