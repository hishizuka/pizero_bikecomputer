import asyncio
import json
import os
import re
import shutil

import numpy as np
import oyaml

from modules.app_logger import app_logger
from modules.utils.navigation import maneuver_to_turn_type
from modules.utils.timer import Timer, log_timers

from .loaders import FitLoader, JsonLoader, TcxLoader
from .matcher import CourseMatcher
from .processor import (
    CourseProcessor,
    _categorize_slope as _processor_slope,
)
from .state import CourseData, CourseIndex
from .weather import CourseWeatherService

POLYLINE_DECODER = False
try:
    import polyline

    POLYLINE_DECODER = True
except ImportError:
    pass

LOADERS = {"fit": FitLoader, "tcx": TcxLoader, "json": JsonLoader}


def _categorize_slope(slope_smoothing, slope_cutoff):
    return _processor_slope(slope_smoothing, slope_cutoff)


class Course(CourseProcessor, CourseMatcher):
    """Keep the legacy course API while delegating specialized work."""

    config = None
    on_route_exit_ratio = 1.2
    on_route_rescue_ratio = 1.35
    on_route_centroid_window = 2

    html_remove_pattern = [
        re.compile(r"\<div.+?\<\/div\>"),
        re.compile(r"\<.+?\>"),
    ]

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.__dict__.update(vars(CourseData()))
        self.index = CourseIndex(config.G_GPS_KEEP_ON_COURSE_CUTOFF)
        self._weather_task = None
        self._course_revision = 0
        self.load_weather_status = 0
        self.wind_course_indices = []
        self.wind_timeline = []
        self.wind_speed = []
        self.wind_direction = []

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

    @property
    def has_weather(self):
        return bool(len(self.wind_speed))

    def _resolve_preferred_course_file(self, file_path):
        _, ext = os.path.splitext(file_path)
        if ext.lower() != ".tcx":
            return file_path

        json_path = os.path.splitext(file_path)[0] + ".json"
        if not os.path.exists(json_path):
            return file_path

        app_logger.info(f"prefer json course file: {json_path}")
        return json_path

    @staticmethod
    def _read_first_non_whitespace_char(file_path):
        try:
            with open(file_path, "r", encoding="utf-8_sig") as f:
                chunk = f.read(4096)
        except (OSError, UnicodeDecodeError):
            return ""

        stripped = chunk.lstrip()
        if not stripped:
            return ""
        return stripped[0]

    def _detect_course_file_extension(self, file_path):
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        if ext in LOADERS:
            return ext

        try:
            with open(file_path, "rb") as f:
                if f.read(12)[8:12] == b".FIT":
                    return "fit"
        except OSError:
            return ""

        first_char = self._read_first_non_whitespace_char(file_path)
        if first_char == "<":
            return "tcx"
        if first_char in ("{", "["):
            return "json"
        return ""

    def _cancel_weather_load(self):
        if self._weather_task is not None and not self._weather_task.done():
            self._weather_task.cancel()
        self._weather_task = None

    def _schedule_course_weather(self):
        self._cancel_weather_load()
        self._weather_task = asyncio.create_task(self.get_course_wind())

    def reset(self, delete_course_file=False, replace=False):
        self.__dict__.update(vars(CourseData()))
        self.index.reset()
        self._course_revision += 1
        self._cancel_weather_load()
        self.load_weather_status = 0
        self.wind_course_indices = []
        self.wind_timeline = []
        self.wind_speed = []
        self.wind_direction = []

        if delete_course_file:
            if os.path.exists(self.config.G_COURSE_FILE_PATH):
                os.remove(self.config.G_COURSE_FILE_PATH)
            if not replace:
                self.config.api.send_livetrack_course_reset()

    def _queue_livetrack_course(self):
        if self.is_set:
            self.config.api.send_livetrack_course_load()
        else:
            self.config.api.send_livetrack_course_reset()

    def load(self, file=None):
        # if file is given, copy it to self.config.G_COURSE_FILE_PATH firsthand, we are loading a new course
        if file:
            file = self._resolve_preferred_course_file(file)
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
        ]

        with timers[0]:
            # get loader based on the extension
            if os.path.exists(self.config.G_COURSE_FILE_PATH):
                try:
                    ext = self._detect_course_file_extension(
                        self.config.G_COURSE_FILE_PATH
                    )
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
                        app_logger.warning(
                            f"course file format is not handled: {self.config.G_COURSE_FILE_PATH}"
                        )
                except (AttributeError, OSError) as e:
                    app_logger.error(
                        f"Incorrect course file: {e}. Please reload the course."
                    )
        with timers[1]:
            self.downsample()

        with timers[2]:
            self.calc_slope_smoothing()

        with timers[3]:
            self.modify_course_points()

        if self.is_set:
            app_logger.info("[logger] Loading course:")
            log_timers(timers, text_total="  total               : {0:.3f} sec")

        self._schedule_course_weather()
        self._queue_livetrack_course()

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

        self._schedule_course_weather()
        self._queue_livetrack_course()

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
            turn_str = maneuver_to_turn_type(p.get("step"))

            # skip
            if ("step" in p and not turn_str) or (
                "step" not in p and cp_i not in [0, cp_n]
            ):
                point_distance[-1] = round(p["dist"]["total"] / 1000, 1)
                continue

            point_latitude.append(p["lat"])
            point_longitude.append(p["lng"])

            if "dist" in p:
                dist = round(p["dist"]["total"] / 1000, 1)
                point_distance.append(dist)

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

        self._schedule_course_weather()
        self._queue_livetrack_course()

    async def get_google_route(self, x1, y1, x2, y2):
        if not POLYLINE_DECODER:
            return

        json_routes = await self.config.api.get_google_routes(x1, y1, x2, y2)

        routes = json_routes.get("routes") if json_routes else None
        if not routes:
            app_logger.warning("Google Routes API returned no route")
            return

        route = routes[0]
        self.info["Name"] = "Google Routes"
        self.info["DistanceMeters"] = round(route.get("distanceMeters", 0) / 1000, 1)

        points_detail = []
        self.course_points.reset()

        dist = 0
        pre_dist = 0

        steps = []
        for leg in route.get("legs", []):
            steps.extend(leg.get("steps", []))

        for step in steps:
            encoded_polyline = step.get("polyline", {}).get("encodedPolyline")
            if encoded_polyline:
                points_detail.extend(polyline.decode(encoded_polyline))
            dist += pre_dist
            pre_dist = step.get("distanceMeters", 0) / 1000

            navigation_instruction = step.get("navigationInstruction", {})
            turn_str = maneuver_to_turn_type(navigation_instruction.get("maneuver"))

            if not turn_str:
                continue

            start_location = step.get("startLocation", {}).get("latLng", {})
            start_lat = start_location.get("latitude")
            start_lon = start_location.get("longitude")
            if start_lat is None or start_lon is None:
                continue

            self.course_points.type = np.append(self.course_points.type, turn_str)
            self.course_points.latitude = np.append(
                self.course_points.latitude, start_lat
            )
            self.course_points.longitude = np.append(
                self.course_points.longitude, start_lon
            )
            self.course_points.distance = np.append(self.course_points.distance, dist)
            self.course_points.notes = np.append(
                self.course_points.notes,
                self.remove_html_tag(navigation_instruction.get("instructions", "")),
            )
            self.course_points.name = np.append(self.course_points.name, turn_str)

        if not points_detail:
            encoded_polyline = route.get("polyline", {}).get("encodedPolyline")
            if encoded_polyline:
                points_detail.extend(polyline.decode(encoded_polyline))

        if not points_detail:
            return

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

    async def get_course_wind(self):
        if not self.config.G_USE_WIND_DATA_SOURCE or not self.is_set:
            return

        revision = self._course_revision
        self.load_weather_status = 1
        weather = await CourseWeatherService.fetch(self)
        if revision != self._course_revision:
            return

        (
            self.wind_course_indices,
            self.wind_timeline,
            self.wind_speed,
            self.wind_direction,
        ) = weather
        self.load_weather_status = 2

    def reset_load_weather_status(self):
        self.load_weather_status = 0
