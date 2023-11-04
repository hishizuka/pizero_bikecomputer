import os
import re
from collections import defaultdict

import numpy as np

from logger import app_logger

patterns = {
    "name": re.compile(r"<Name>(?P<text>[\s\S]*?)</Name>"),
    "distance_meters": re.compile(
        r"<DistanceMeters>(?P<text>[\s\S]*?)</DistanceMeters>"
    ),
    "track": re.compile(r"<Track>(?P<text>[\s\S]*?)</Track>"),
    "latitude": re.compile(r"<LatitudeDegrees>(?P<text>[^<]*)</LatitudeDegrees>"),
    "longitude": re.compile(r"<LongitudeDegrees>(?P<text>[^<]*)</LongitudeDegrees>"),
    "altitude": re.compile(r"<AltitudeMeters>(?P<text>[^<]*)</AltitudeMeters>"),
    "distance": re.compile(r"<DistanceMeters>(?P<text>[^<]*)</DistanceMeters>"),
    "time": re.compile(r"<Time>(?P<text>[^<]*)</Time>"),
    "course_point": re.compile(r"<CoursePoint>(?P<text>[\s\S]+)</CoursePoint>"),
    "course_name": re.compile(r"<Name>(?P<text>[^<]*)</Name>"),
    "course_point_type": re.compile(r"<PointType>(?P<text>[^<]*)</PointType>"),
    "course_notes": re.compile(r"<Notes>(?P<text>[^<]*)</Notes>"),
    "course_time": re.compile(r"<Time>(?P<text>[^<]*)</Time>"),
}


class TcxLoader:
    config = None

    @classmethod
    def load_file(cls, file):
        if not os.path.exists(file):
            return None, None
        app_logger.info(f"[{cls.__name__}]: loading {file}")

        # should just return a Course object
        course = {
            "info": {},
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "distance": None,
            "time": None,
        }
        course_points = defaultdict(lambda: np.array([]))

        with open(file, "r", encoding="utf-8_sig") as f:
            tcx = f.read()

            match_name = patterns["name"].search(tcx)
            if match_name:
                course["info"]["Name"] = match_name.group("text").strip()

            match_distance_meter = patterns["distance_meters"].search(tcx)
            if match_distance_meter:
                course["info"]["DistanceMeters"] = round(
                    float(match_distance_meter.group("text").strip()) / 1000, 1
                )

            match_track = patterns["track"].search(tcx)
            if match_track:
                track = match_track.group("text")
                course["latitude"] = np.array(
                    [
                        float(m.group("text").strip())
                        for m in patterns["latitude"].finditer(track)
                    ]
                )
                course["longitude"] = np.array(
                    [
                        float(m.group("text").strip())
                        for m in patterns["longitude"].finditer(track)
                    ]
                )
                course["altitude"] = np.array(
                    [
                        float(m.group("text").strip())
                        for m in patterns["altitude"].finditer(track)
                    ]
                )
                course["distance"] = np.array(
                    [
                        float(m.group("text").strip())
                        for m in patterns["distance"].finditer(track)
                    ]
                )
                course["time"] = np.array(
                    [m.group("text").strip() for m in patterns["time"].finditer(track)]
                )

            match_course_point = patterns["course_point"].search(tcx)

            if match_course_point:
                course_point = match_course_point.group("text")
                course_points["name"] = np.array(
                    [
                        m.group("text").strip()
                        for m in patterns["course_name"].finditer(course_point)
                    ]
                )
                course_points["latitude"] = np.array(
                    [
                        float(m.group("text").strip())
                        for m in patterns["latitude"].finditer(course_point)
                    ]
                )
                course_points["longitude"] = np.array(
                    [
                        float(m.group("text").strip())
                        for m in patterns["longitude"].finditer(course_point)
                    ]
                )
                course_points["type"] = np.array(
                    [
                        m.group("text").strip()
                        for m in patterns["course_point_type"].finditer(course_point)
                    ]
                )
                course_points["notes"] = np.array(
                    [
                        m.group("text").strip()
                        for m in patterns["course_notes"].finditer(course_point)
                    ]
                )
                course_points["time"] = np.array(
                    [
                        m.group("text").strip()
                        for m in patterns["course_time"].finditer(course_point)
                    ]
                )

        valid_course = True
        if len(course["latitude"]) != len(course["longitude"]):
            app_logger.error("Could not parse course")
            valid_course = False
        if not (
            len(course["latitude"])
            == len(course["altitude"])
            == len(course["distance"])
        ):
            app_logger.warning(
                f"Course has missing data: points {len(course['latitude'])} altitude {len(course['altitude'])} "
                f"distance {len(course['distance'])}"
            )
        if not (
            len(course_points["name"])
            == len(course_points["latitude"])
            == len(course_points["longitude"])
            == len(course_points["type"])
        ):
            app_logger.error("Could not parse course points")
            valid_course = False

        if not valid_course:
            course["distance"] = np.array([])
            course["altitude"] = np.array([])
            course["latitude"] = np.array([])
            course["longitude"] = np.array([])
            course_points = defaultdict(lambda: np.array([]))
        else:
            # delete 'Straight' from course points
            if len(course_points["type"]):
                not_straight_cond = np.where(
                    course_points["type"] != "Straight", True, False
                )

                for key in ["name", "latitude", "longitude", "notes", "type", "time"]:
                    course_points[key] = course_points[key][not_straight_cond]

        # if time is given in the field, try to set the course point distance/altitude directly from there
        # if a point can not be found, let's fail and modify_course_point will try to compute it instead
        if (
            course["time"] is not None
            and len(course["time"])
            and len(course_points["time"])
        ):
            distance_error = False
            altitude_error = False

            for point_time in course_points["time"]:
                try:
                    index = np.where(course["time"] == point_time)[0][0]
                except Exception:  # noqa
                    # Point time not found in trackpoint reset and break
                    course_points.distance = np.array([])
                    course_points.altitude = np.array([])
                    break
                if not distance_error:
                    try:
                        # course_point distance is set in [km]
                        course_points["distance"] = np.append(
                            course_points["distance"], course["distance"][index] / 1000
                        )
                    except IndexError:
                        distance_error = True
                        course_points.distance = np.array([])
                if not altitude_error:
                    try:
                        # course_point altitude is set in [m]
                        course_points["altitude"] = np.append(
                            course_points["altitude"], course["altitude"][index]
                        )
                    except IndexError:
                        altitude_error = True
                        course_points.altitude = np.array([])

        # do not keep these in memory
        del course["time"]

        if "time" in course_points:
            del course_points["time"]

        return course, course_points
