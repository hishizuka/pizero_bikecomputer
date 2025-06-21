import os
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
import asyncio

import oyaml
import numpy as np
from crdp import rdp

from modules.app_logger import app_logger
from modules.loaders import TcxLoader
from modules.utils.filters import savitzky_golay
from modules.utils.geo import calc_azimuth, get_dist_on_earth, get_dist_on_earth_array
from modules.utils.network import detect_network
from modules.utils.timer import Timer, log_timers

POLYLINE_DECODER = False
try:
    import polyline

    POLYLINE_DECODER = True
except ImportError:
    pass

LOADERS = {"tcx": TcxLoader}


class CourseIndex:
    # current index value
    value = 0
    # also store the course_points index (TODO, should be moved though)
    course_points_index = 0

    on_course_status = False

    altitude = np.nan
    distance = 0

    check = None

    cutoff = None

    def __init__(self, cutoff):
        self.cutoff = cutoff
        self.reset()

    def reset(self):
        self.value = 0
        self.course_points_index = 0
        self.distance = 0
        self.altitude = np.nan
        self.on_course_status = False
        self.check = [True] * self.cutoff


class CoursePoints:
    name = None
    type = None
    altitude = None
    distance = None
    latitude = None
    longitude = None
    notes = None

    def __init__(self):
        self.reset()

    @property
    def is_set(self):
        # https://developer.garmin.com/fit/file-types/course/
        # no field is mandatory, but they will be zeroes/empty anyway so len will not be 0 is coursePoints are set
        return bool(len(self.name))

    def reset(self):
        self.name = np.array([])
        self.type = np.array([])
        self.altitude = np.array([])
        self.distance = np.array([])
        self.latitude = np.array([])
        self.longitude = np.array([])
        self.notes = np.array([])


# we have mutable attributes but course is supposed to be a singleton anyway
class Course:
    config = None

    # for course
    info = {}
    distance = np.array([])
    altitude = np.array([])
    latitude = np.array([])
    longitude = np.array([])

    course_points = None
    index = None

    # calculated
    points_diff = np.array([])
    azimuth = np.array([])
    slope = np.array([])
    slope_smoothing = np.array([])
    colored_altitude = np.array([])
    # [start_index, end_index, distance, average_grade, volume(=dist*average), cat]
    climb_segment = []

    # for wind
    #wind_distance = []
    wind_coordinates = []
    wind_timeline = []
    wind_speed = []
    wind_direction = []

    html_remove_pattern = [
        re.compile(r"\<div.+?\<\/div\>"),
        re.compile(r"\<.+?\>"),
    ]

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.course_points = CoursePoints()
        self.index = CourseIndex(config.G_GPS_KEEP_ON_COURSE_CUTOFF)

    def __str__(self):
        return f"Course:\n" f"{oyaml.dump(self.info, allow_unicode=True)}\n"

    @property
    def is_set(self):
        # we keep checking distance as it's how it was done in the original code,
        # but we can load tcx file with no distance in it load (it gets populated as np.zeros in load)
        return bool(len(self.distance))
    
    @property
    def has_altitude(self):
        return bool(len(self.altitude))
    
    def reset(self, delete_course_file=False, replace=False):
        # for course
        self.info = {}
        # raw data
        self.distance = np.array([])
        self.altitude = np.array([])
        self.latitude = np.array([])
        self.longitude = np.array([])
        # processed variables
        self.points_diff = np.array([])
        self.azimuth = np.array([])
        self.slope = np.array([])
        self.slope_smoothing = np.array([])
        self.colored_altitude = np.array([])
        self.climb_segment = []
        #self.wind_distance = []
        self.wind_coordinates = []
        self.wind_timeline = []
        self.wind_speed = []
        self.wind_direction = []

        if self.course_points:
            self.course_points.reset()

        if delete_course_file:
            if os.path.exists(self.config.G_COURSE_FILE_PATH):
                os.remove(self.config.G_COURSE_FILE_PATH)
            if not replace and self.config.G_THINGSBOARD_API["STATUS"]:
                self.config.api.send_livetrack_course_reset()

    def load(self, file=None):
        # if file is given, copy it to self.config.G_COURSE_FILE_PATH firsthand, we are loading a new course
        if file:
            _, ext = os.path.splitext(file)
            shutil.copy(file, self.config.G_COURSE_FILE_PATH)
            # shutil.copy2(file, self.config.G_COURSE_FILE_PATH)
            # if ext:
            #    os.setxattr(
            #        self.config.G_COURSE_FILE_PATH, "user.ext", ext[1:].encode()
            #    )

        self.reset()

        timers = [
            Timer(auto_start=False, text="  read_file           : {0:.3f} sec"),
            Timer(auto_start=False, text="  downsample          : {0:.3f} sec"),
            Timer(auto_start=False, text="  calc_slope_smoothing: {0:.3f} sec"),
            Timer(auto_start=False, text="  modify_course_points: {0:.3f} sec"),
            Timer(auto_start=False, text="  get_course_wind     : {0:.3f} sec"),
        ]

        with timers[0]:
            # get loader based on the extension
            if os.path.exists(self.config.G_COURSE_FILE_PATH):
                # get file extension in order to find the correct loader
                # extension was set in custom attributes as the current course is always
                # loaded from '.current'
                try:
                    # ext = os.getxattr(
                    #    self.config.G_COURSE_FILE_PATH, "user.ext"
                    # ).decode()
                    ext = "tcx"
                    if ext in LOADERS:
                        course_data, course_points_data = LOADERS[ext].load_file(
                            self.config.G_COURSE_FILE_PATH
                        )
                        if course_data:
                            for k, v in course_data.items():
                                setattr(self, k, v)
                        if course_points_data:
                            for k, v in course_points_data.items():
                                setattr(self.course_points, k, v)
                    else:
                        app_logger.warning(f".{ext} files are not handled")
                except (AttributeError, OSError) as e:
                    app_logger.error(
                        f"Incorrect course file: {e}. Please reload the course and make sure your file"
                        f"has a proper extension set"
                    )
        with timers[1]:
            self.downsample()

        with timers[2]:
            self.calc_slope_smoothing()

        with timers[3]:
            self.modify_course_points()

        with timers[4]:
            asyncio.create_task(self.get_course_wind())

        if self.is_set:
            app_logger.info("[logger] Loading course:")
            log_timers(timers, text_total="  total               : {0:.3f} sec")

        if self.config.G_THINGSBOARD_API["STATUS"]:
            self.config.api.send_livetrack_course_load()

    async def load_google_map_route(self, load_html=False, html_file=None):
        self.reset()

        if load_html:
            with open(html_file, "r", encoding="utf-8") as f:
                s = f.read()
            url_ptn = re.compile(r"\<a\ href\=\"https\:\/\/(.+?)\"\>")
            res = url_ptn.search(s)
            if res:
                self.config.G_MAPSTOGPX["ROUTE_URL"] = res.groups(1)[0]
            else:
                return

        await self.get_google_route_from_mapstogpx(self.config.G_MAPSTOGPX["ROUTE_URL"])
        self.downsample()
        self.calc_slope_smoothing()
        self.modify_course_points()

        if self.config.G_THINGSBOARD_API["STATUS"]:
            self.config.api.send_livetrack_course_load()

        self.config.gui.init_course()

    async def get_google_route_from_mapstogpx(self, url):
        json_routes = await self.config.api.get_google_route_from_mapstogpx(url)

        self.info["Name"] = "Google routes"
        self.info["DistanceMeters"] = round(json_routes["totaldist"] / 1000, 1)

        self.latitude = np.array([p["lat"] for p in json_routes["points"]])
        self.longitude = np.array([p["lng"] for p in json_routes["points"]])

        point_name = []
        point_latitude = []
        point_longitude = []
        point_distance = []
        point_type = []
        point_notes = []

        point_distance.append(0)

        cp = [p for p in json_routes["points"] if len(p) > 2]

        cp_n = len(cp) - 1
        cp_i = -1

        for p in cp:
            cp_i += 1
            # skip
            if ("step" in p and p["step"] in ["straight", "merge", "keep"]) or (
                "step" not in p and cp_i not in [0, cp_n]
            ):
                point_distance[-1] = round(p["dist"]["total"] / 1000, 1)
                continue

            point_latitude.append(p["lat"])
            point_longitude.append(p["lng"])

            if "dist" in p:
                dist = round(p["dist"]["total"] / 1000, 1)
                point_distance.append(dist)

            turn_str = ""

            if "step" in p:
                turn_str = p["step"]
                if turn_str[-4:] == "left":
                    turn_str = "Left"
                elif turn_str[-5:] == "right":
                    turn_str = "Right"

            point_name.append(turn_str)
            point_type.append(turn_str)

            text = ""

            if "dir" in p:
                text = self.remove_html_tag(p["dir"])

            point_notes.append(text)

        point_name[0] = "Start"
        point_name[-1] = "End"

        self.course_points.name = np.array(point_name)
        self.course_points.type = np.array(point_type)
        self.course_points.notes = np.array(point_notes)
        self.course_points.latitude = np.array(point_latitude)
        self.course_points.longitude = np.array(point_longitude)
        self.course_points.distance = np.array(point_distance)

        check_course = False
        if not (len(self.latitude) == len(self.longitude)):
            app_logger.warning("ERROR parse course")
            check_course = True

        if check_course:
            self.latitude = np.array([])
            self.longitude = np.array([])
            self.course_points.reset()
            return

    async def search_route(self, x1, y1, x2, y2):
        if np.any(np.isnan([x1, y1, x2, y2])):
            return

        self.reset()

        await self.get_google_route(x1, y1, x2, y2)

        self.downsample()
        self.calc_slope_smoothing()
        self.modify_course_points()

        if self.config.G_THINGSBOARD_API["STATUS"]:
            self.config.api.send_livetrack_course_load()

    async def get_google_route(self, x1, y1, x2, y2):
        if not POLYLINE_DECODER:
            return

        json_routes = await self.config.api.get_google_routes(x1, y1, x2, y2)

        if json_routes is None or json_routes["status"] != "OK":
            return

        self.info["Name"] = "Google routes"
        self.info["DistanceMeters"] = round(
            json_routes["routes"][0]["legs"][0]["distance"]["value"] / 1000, 1
        )

        # points = np.array(polyline.decode(json_routes["routes"][0]["overview_polyline"]["points"]))
        points_detail = []
        self.course_points.reset()

        dist = 0
        pre_dist = 0

        for step in json_routes["routes"][0]["legs"][0]["steps"]:
            points_detail.extend(polyline.decode(step["polyline"]["points"]))
            dist += pre_dist
            pre_dist = step["distance"]["value"] / 1000

            if "maneuver" not in step or any(
                map(step["maneuver"].__contains__, ("straight", "merge", "keep"))
            ):
                continue
                # https://developers.google.com/maps/documentation/directions/get-directions
                # turn-slight-left, turn-sharp-left, turn-left,
                # turn-slight-right, turn-sharp-right, keep-right,
                # keep-left, uturn-left, uturn-right, turn-right,
                # straight,
                # ramp-left, ramp-right,
                # merge,
                # fork-left, fork-right,
                # ferry, ferry-train,
                # roundabout-left, and roundabout-right
            turn_str = step["maneuver"]
            if turn_str[-4:] == "left":
                turn_str = "Left"
            elif turn_str[-5:] == "right":
                turn_str = "Right"
            self.course_points.type = np.append(self.course_points.type, turn_str)
            self.course_points.latitude = np.append(
                self.course_points.latitude, step["start_location"]["lat"]
            )
            self.course_points.longitude = np.append(
                self.course_points.longitude, step["start_location"]["lng"]
            )
            self.course_points.distance = np.append(self.course_points.distance, dist)
            self.course_points.notes = np.append(
                self.course_points.notes,
                self.remove_html_tag(step["html_instructions"]),
            )
            self.course_points.name = np.append(self.course_points.name, turn_str)
        points_detail = np.array(points_detail)

        self.latitude = np.array(points_detail)[:, 0]
        self.longitude = np.array(points_detail)[:, 1]

    def remove_html_tag(self, text):
        res = text.replace("&nbsp;", "")
        for r in self.html_remove_pattern:
            res = re.subn(r, "", res)[0]
        return res

    def get_ridewithgps_privacycode(self, route_id):
        privacy_code = None
        filename = (
            self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
            + "course-{route_id}.json"
        ).format(route_id=route_id)

        with open(filename, "r") as json_file:
            json_contents = json.load(json_file)
            if "privacy_code" in json_contents["route"]:
                privacy_code = json_contents["route"]["privacy_code"]

        return privacy_code
    
    def downsample(self):
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
        dist_diff = 1000 * np.diff(self.distance)  # [m]

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

        diff_dist_max = int(np.max(dist_diff)) * 2 / 1000  # [m->km]
        if diff_dist_max > self.config.G_GPS_SEARCH_RANGE:  # [km]
            app_logger.debug(
                f"G_GPS_SEARCH_RANGE[km]: {self.config.G_GPS_SEARCH_RANGE} -> {diff_dist_max}"
            )
            self.config.G_GPS_SEARCH_RANGE = diff_dist_max

        app_logger.info(f"downsampling:{len_lat} -> {len(self.latitude)}")

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
        slope_smoothing_cat = np.zeros(course_n).astype("uint8")

        for i in range(i, len(self.config.G_SLOPE_CUTOFF) - 1):
            slope_smoothing_cat = np.where(
                (self.config.G_SLOPE_CUTOFF[i - 1] < self.slope_smoothing)
                & (self.slope_smoothing <= self.config.G_SLOPE_CUTOFF[i]),
                i,
                slope_smoothing_cat,
            )

        slope_smoothing_cat = np.where(
            (self.config.G_SLOPE_CUTOFF[-1] < self.slope_smoothing),
            len(self.config.G_SLOPE_CUTOFF) - 1,
            slope_smoothing_cat,
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
                            > self.config.G_CLIMB_CATEGORY[j]["volume"]
                        ):
                            self.climb_segment[-1][
                                "cat"
                            ] = self.config.G_CLIMB_CATEGORY[j]["name"]
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

    async def get_course_wind(self):
        if not self.is_set or not detect_network():
            return
        
        current_time = datetime.now(timezone.utc)
        self.wind_coordinates.append([self.longitude[0], self.latitude[0]])
        self.wind_timeline.append(current_time)

        dist = self.config.G_GROSS_AVE_SPEED
        index = 0
        while dist < self.distance[-1]:
            index += np.argmin(np.abs(self.distance[index:] - dist))
            self.wind_coordinates.append([self.longitude[index], self.latitude[index]])
            current_time += timedelta(hours=1)
            self.wind_timeline.append(current_time)
            dist += self.config.G_GROSS_AVE_SPEED
        
        rest_dist = int(self.distance[-1]%self.config.G_GROSS_AVE_SPEED)
        if rest_dist > 0:
            self.wind_coordinates.append([self.longitude[-1], self.latitude[-1]])
            current_time += timedelta(hours=rest_dist/self.config.G_GROSS_AVE_SPEED)
            self.wind_timeline.append(current_time)

        #self.wind_speed, self.wind_direction = await self.config.logger.sensor.maptile_with_values.get_wind(
        #    self.wind_coordinates, 
        #    self.wind_timeline,
        #    self.config.G_WIND_OVERLAY_MAP_CONFIG[
        #        self.config.G_WIND_OVERLAY_MAP
        #    ],
        #    self.config.G_WIND_OVERLAY_MAP,
        #)

    def get_index(self, lat, lon, track, search_range, on_route_cutoff, azimuth_cutoff):
        if not self.config.G_COURSE_INDEXING:
            self.index.on_course_status = False
            return

        if np.isnan(lat) or np.isnan(lat):
            return

        # not running
        if self.config.G_IS_RASPI and self.config.G_STOPWATCH_STATUS != "START":
            return

        course_n = len(self.longitude)

        if not course_n:
            return

        start = self.index.value

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

        if not np.isnan(track) and track is not None:
            azimuth_diff = (track - self.azimuth) % 360

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
            # app_logger.debug(f"track:{track}, m:{m}")
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
                # app_logger.debug(f"track:{track}, m:{m}")
                # app_logger.debug(course.azimuth)
                # app_logger.debug(f"azimuth_diff:{azimuth_diff}")
                continue
            app_logger.debug(
                f"i:{i}, s:{s}, m:{m}, azimuth_diff:{azimuth_diff[m]}, course_index:{self.index.value}, course_point_index:{self.index.course_points_index}"
            )
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
                and (grade > self.config.G_SLOPE_CUTOFF[0]) != (self.slope_smoothing[m] > self.config.G_SLOPE_CUTOFF[0])
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

            h_lon = (
                self.longitude[m]
                + (self.longitude[m + 1] - self.longitude[m]) * inner_p[m]
            )
            h_lat = (
                self.latitude[m]
                + (self.latitude[m + 1] - self.latitude[m]) * inner_p[m]
            )
            dist_diff_h = get_dist_on_earth(h_lon, h_lat, lon, lat)

            if dist_diff_h > on_route_cutoff:
                app_logger.debug(
                    f"dist_diff_h: {dist_diff_h:.0f} > cutoff {on_route_cutoff}[m]"
                )
                app_logger.debug(
                    f"\ti:{i}, s:{s}, m:{m}, azimuth_diff:{azimuth_diff[m]}, "
                    f"course_point_index:{self.index.course_points_index}, "
                    f"inner_p[m]:{inner_p[m]}"
                )
                app_logger.debug(
                    f"\th_lat/h_lon: {h_lat}, {h_lon}, lat_lon: {lat}, {lon}"
                )
                app_logger.debug(
                    f"\tcourse[m]: {self.latitude[m]}, {self.longitude[m]}"
                )
                app_logger.debug(
                    f"\tcourse[m+1]: {self.latitude[m+1]}, {self.longitude[m+1]}"
                )
                continue

            # stay forward while self.config.G_GPS_KEEP_ON_COURSE_CUTOFF if search_indexes is except forward
            # prevent from changing course index quickly
            self.index.check[:-1] = self.index.check[1:]
            if i < penalty_index:
                self.index.check[-1] = True
            else:
                self.index.check[-1] = False
            if self.index.check[-1] is False and np.sum(self.index.check) != 0:
                # app_logger.debug(f"course_index_check failed, self.index.check[-1]:{self.index.check[-1]}, np.sum(self.course_index_check):{np.sum(self.index.check)}")
                # app_logger.debug(f"\t i:{i}, s:{s}, m:{m}, azimuth_diff:{azimuth_diff[m+1]}, course_point_index:{self.index.course_points_index}")
                # app_logger.debug(f"\t {lat}, {lon}, {round(self.index.distance/1000,2)}m")
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
