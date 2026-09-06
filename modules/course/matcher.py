import numpy as np

from modules.app_logger import app_logger
from modules.utils.geo import get_dist_on_earth


class CourseMatcher:
    def _project_point_to_segment(self, segment_index, inner_p):
        max_segment_index = len(self.longitude) - 2
        if max_segment_index < 0:
            return None

        segment_index = int(max(0, min(segment_index, max_segment_index)))
        inner = float(inner_p[segment_index])
        inner = max(0.0, min(inner, 1.0))

        h_lon = (
            self.longitude[segment_index]
            + (self.longitude[segment_index + 1] - self.longitude[segment_index])
            * inner
        )
        h_lat = (
            self.latitude[segment_index]
            + (self.latitude[segment_index + 1] - self.latitude[segment_index]) * inner
        )
        return float(h_lon), float(h_lat)

    def _get_projection_centroid(self, center_segment_index, inner_p, window_size):
        max_segment_index = len(self.longitude) - 2
        if max_segment_index < 0:
            return None

        start_index = max(0, int(center_segment_index) - int(window_size))
        end_index = min(max_segment_index, int(center_segment_index) + int(window_size))

        lon_sum = 0.0
        lat_sum = 0.0
        weight_sum = 0.0

        for segment_index in range(start_index, end_index + 1):
            projected = self._project_point_to_segment(segment_index, inner_p)
            if projected is None:
                continue

            h_lon, h_lat = projected
            distance_from_center = abs(segment_index - int(center_segment_index))
            # Keep nearby segments dominant while still blending neighbors.
            weight = 1.0 / (distance_from_center + 1.0)

            lon_sum += h_lon * weight
            lat_sum += h_lat * weight
            weight_sum += weight

        if weight_sum <= 0:
            return None

        return lon_sum / weight_sum, lat_sum / weight_sum

    def get_index(
        self,
        lat,
        lon,
        heading_gps_deg,
        search_range,
        on_route_cutoff,
        azimuth_cutoff,
    ):
        if not self.config.G_COURSE_INDEXING:
            self.index.on_course_status = False
            return

        if np.isnan(lat) or np.isnan(lon):
            return

        # not running
        if self.config.G_IS_RASPI and self.config.G_STOPWATCH_STATUS != "START":
            return

        course_n = len(self.longitude)

        if not course_n:
            return

        start = self.index.value
        was_on_course = bool(self.index.on_course_status)

        # 1st search index(a little ahead)
        forward_search_index = min(start + 5, course_n - 1)
        # 2nd search index(a several kilometers ahead: weak GPS signal, long tunnel)
        forward_search_index_next = max(
            self.get_index_with_distance_cutoff(start, search_range),
            forward_search_index,
        )
        # 3rd search index(backward)
        backward_search_index = self.get_index_with_distance_cutoff(
            start, -search_range
        )

        b_a_x = self.points_diff[0]
        b_a_y = self.points_diff[1]
        lon_diff = lon - self.longitude
        lat_diff = lat - self.latitude
        p_a_x = lon_diff[0:-1]
        p_a_y = lat_diff[0:-1]
        p_b_x = lon_diff[1:]
        p_b_y = lat_diff[1:]
        inner_p = (b_a_x * p_a_x + b_a_y * p_a_y) / self.points_diff_sum_of_squares

        azimuth_diff = np.full(len(self.azimuth), np.nan)

        if not np.isnan(heading_gps_deg) and heading_gps_deg is not None:
            azimuth_diff = (heading_gps_deg - self.azimuth) % 360

        dist_diff = np.where(
            inner_p <= 0.0,
            np.sqrt(p_a_x**2 + p_a_y**2),
            np.where(
                inner_p >= 1.0,
                np.sqrt(p_b_x**2 + p_b_y**2),
                np.abs(b_a_x * p_a_y - b_a_y * p_a_x) / self.points_diff_dist,
            ),
        )

        # search with no penalty
        # 1st start -> forward_search_index
        # 2nd forward_search_index -> forward_search_index_next
        # with penalty (continue running while G_GPS_KEEP_ON_COURSE_CUTOFF seconds, then change course_index)
        # 3rd backward_search_index -> start
        # 4th forward_search_index -> end of course
        # 5th start of course -> backward_search_index
        search_indexes = [
            [start, forward_search_index],
            [forward_search_index, forward_search_index_next],
            [backward_search_index, start],
            [forward_search_index_next, course_n - 1],
            [0, backward_search_index],
        ]
        s_state = ["forward(close)", "forward(far)", "back", "end", "start"]
        penalty_index = 2

        for i, s in enumerate(search_indexes):
            if s[0] < 0:
                continue
            elif s[0] == s[1]:
                continue

            m = s[0]

            dist_diff_mod = np.where(
                ((0 <= azimuth_diff) & (azimuth_diff <= azimuth_cutoff[0]))
                | ((azimuth_cutoff[1] <= azimuth_diff) & (azimuth_diff <= 360)),
                dist_diff,
                np.inf,
            )
            # app_logger.debug(f"azimuth_diff: {azimuth_diff[s[0]:s[1]]}")
            # app_logger.debug(f"dist_diff_mod: {dist_diff_mod[s[0]:s[1]]}")
            # app_logger.debug(f"inner_p: {inner_p[s[0]:s[1]]}")

            if s[1] >= course_n - 1:
                m += dist_diff_mod[s[0] :].argmin()
            else:
                m += dist_diff_mod[s[0] : s[1]].argmin()

            # check azimuth
            # app_logger.debug(f"i:{i}, s:{s}, m:{m}, azimuth_diff:{azimuth_diff[m]}, {len(azimuth_diff)}")
            # app_logger.debug(f"heading_gps_deg:{heading_gps_deg}, m:{m}")
            # app_logger.debug(f"self.azimuth:{self.azimuth}, {len(self.azimuth)}")
            # app_logger.debug(f"azimuth_diff:{azimuth_diff}")
            if np.isnan(azimuth_diff[m]):
                # GPS is lost(return start finally)
                continue
            if (
                0 <= azimuth_diff[m] <= azimuth_cutoff[0]
                or azimuth_cutoff[1] <= azimuth_diff[m] <= 360
            ):
                # go forward
                pass
            else:
                # go backward
                # app_logger.debug(f"heading_gps_deg:{heading_gps_deg}, m:{m}")
                # app_logger.debug(self.azimuth)
                # app_logger.debug(f"azimuth_diff:{azimuth_diff}")
                continue
            # app_logger.debug(
            #    f"i:{i}, s:{s}, m:{m}, azimuth_diff:{azimuth_diff[m]}, course_index:{self.index.value}, course_point_index:{self.index.course_points_index}"
            # )
            # app_logger.debug(f"\t lat_lon: {lat}, {lon}")
            # app_logger.debug(f"\t course: {self.latitude[self.index.value]}, {self.longitude[self.index.value]}")
            # app_logger.debug(f"\t course_point: {self.course_points.latitude[self.index.course_points_index]}, {self.course_points.longitude[self.index.course_points_index]}")

            # grade check if available
            grade = self.config.logger.sensor.values["integrated"]["grade"]
            if (
                not np.isnan(grade)
                and len(self.slope_smoothing) > 0
                # prevent directional false detection on uphill round-trip courses.
                # both in climbing condition or not.
                and (grade > self.config.G_SLOPE_CUTOFF[0])
                != (self.slope_smoothing[m] > self.config.G_SLOPE_CUTOFF[0])
            ):
                continue

            if m == 0 and inner_p[0] <= 0.0:
                continue
            elif m == len(dist_diff) - 1 and inner_p[-1] >= 1.0:
                app_logger.info(f"after end of course {start} -> {m}")
                app_logger.info(
                    f"\t {lat} {lon} / {self.latitude[m]} {self.longitude[m]}",
                )
                self.index.on_course_status = False
                m = course_n - 1
                self.index.distance = self.distance[-1] * 1000
                self.index.altitude = np.nan
                self.index.value = m
                return

            projected = self._project_point_to_segment(m, inner_p)
            if projected is None:
                continue
            h_lon, h_lat = projected
            dist_diff_h = get_dist_on_earth(h_lon, h_lat, lon, lat)
            dist_diff_eval = dist_diff_h

            centroid = self._get_projection_centroid(
                m,
                inner_p,
                self.on_route_centroid_window,
            )
            if centroid is not None:
                c_lon, c_lat = centroid
                dist_diff_centroid = get_dist_on_earth(c_lon, c_lat, lon, lat)
                dist_diff_eval = min(dist_diff_eval, dist_diff_centroid)

            on_route_cutoff_eval = float(on_route_cutoff)
            if was_on_course:
                on_route_cutoff_eval *= self.on_route_exit_ratio

            if dist_diff_eval > on_route_cutoff_eval:
                continue

            # stay forward while self.config.G_GPS_KEEP_ON_COURSE_CUTOFF if search_indexes is except forward
            # prevent from changing course index quickly
            self.index.check[:-1] = self.index.check[1:]
            if i < penalty_index:
                self.index.check[-1] = True
            else:
                self.index.check[-1] = False
            if self.index.check[-1] is False and np.sum(self.index.check) != 0:
                continue

            self.index.on_course_status = True
            dist_diff_course = get_dist_on_earth(
                self.longitude[m],
                self.latitude[m],
                lon,
                lat,
            )
            self.index.distance = self.distance[m] * 1000 + dist_diff_course

            if len(self.altitude):
                alt_diff_course = 0
                if m + 1 < len(self.altitude):
                    alt_diff_course = (
                        (self.altitude[m + 1] - self.altitude[m])
                        / ((self.distance[m + 1] - self.distance[m]) * 1000)
                        * dist_diff_course
                    )
                self.index.altitude = self.altitude[m] + alt_diff_course

            # app_logger.debug(f"index: {m}")
            self.index.value = m

            if len(self.course_points.distance):
                cp_m = np.abs(
                    self.course_points.distance - self.index.distance / 1000
                ).argmin()
                # specify next points for displaying in cuesheet widget
                if self.course_points.distance[cp_m] < self.index.distance / 1000:
                    cp_m += 1
                if cp_m >= len(self.course_points.distance):
                    cp_m = len(self.course_points.distance) - 1
                self.index.course_points_index = cp_m

            if i >= penalty_index:
                app_logger.info(f"{s_state[i]} {start} -> {m}")
                app_logger.info(
                    f"\t {lat} {lon} / {self.latitude[m]} {self.longitude[m]}"
                )
                app_logger.info(f"\t azimuth_diff: {azimuth_diff[m]}")

            return

        if was_on_course and len(dist_diff):
            rescue_segment = int(np.argmin(dist_diff))
            projected = self._project_point_to_segment(rescue_segment, inner_p)
            if projected is not None:
                h_lon, h_lat = projected
                rescue_distance = get_dist_on_earth(h_lon, h_lat, lon, lat)
                rescue_cutoff = float(on_route_cutoff) * self.on_route_rescue_ratio
                if rescue_distance <= rescue_cutoff:
                    self.index.on_course_status = True
                    return

        self.index.on_course_status = False

    def get_index_with_distance_cutoff(self, start, search_range):
        if not self.is_set:
            return 0

        dist_to = self.distance[start] + search_range
        if dist_to >= self.distance[-1]:
            return len(self.distance) - 1
        elif dist_to <= 0:
            return 0

        min_index = 0
        if search_range > 0:
            min_index = start + np.abs((self.distance[start:] - dist_to)).argmin()
        elif search_range < 0:
            min_index = np.abs((self.distance[0:start] - dist_to)).argmin()

        return min_index
