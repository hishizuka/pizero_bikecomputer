import os
import re
from collections import defaultdict

import numpy as np

from logger import app_logger

POLYLINE_DECODER = False
try:
    import polyline

    POLYLINE_DECODER = True
except ImportError:
    pass

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
    "course_point": re.compile(r"<CoursePoint>(?P<text>[\s\S]+)</CoursePoint>"),
    "course_name": re.compile(r"<Name>(?P<text>[^<]*)</Name>"),
    "course_point_type": re.compile(r"<PointType>(?P<text>[^<]*)</PointType>"),
    "course_notes": re.compile(r"<Notes>(?P<text>[^<]*)</Notes>"),
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
        }
        course_points = defaultdict(list)

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

            match_course_point = patterns["course_point"].search(tcx)

            if match_course_point:
                course_point = match_course_point.group("text")
                course_points["name"] = [
                    m.group("text").strip()
                    for m in patterns["course_name"].finditer(course_point)
                ]
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
                course_points["type"] = [
                    m.group("text").strip()
                    for m in patterns["course_point_type"].finditer(course_point)
                ]
                course_points["notes"] = [
                    m.group("text").strip()
                    for m in patterns["course_notes"].finditer(course_point)
                ]

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
            course_points = defaultdict(list)
        else:
            # delete 'Straight' from course points
            if len(course_points["type"]):
                ptype = np.array(course_points["type"])
                not_straight_cond = np.where(ptype != "Straight", True, False)
                course_points["type"] = list(ptype[not_straight_cond])

                for key in ["name", "latitude", "longitude", "notes"]:
                    if len(course_points[key]):
                        # TODO, probably not necessary but kept so logic is 1-1
                        #  we should avoid to mix data types here (or using typings)
                        course_points[key] = np.array(course_points[key])[
                            not_straight_cond
                        ]
                        if key in ["name", "notes"]:
                            course_points[key] = list(course_points[key])

        return course, course_points
