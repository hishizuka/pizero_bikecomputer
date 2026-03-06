from collections import defaultdict

import numpy as np

from modules.app_logger import app_logger
from modules.utils.navigation import normalize_turn_type


class LoaderBase:
    @staticmethod
    def create_course(with_time=False):
        course = {
            "info": {},
            "latitude": np.array([]),
            "longitude": np.array([]),
            "altitude": np.array([]),
            "distance": np.array([]),
        }
        if with_time:
            course["time"] = np.array([])
        return course

    @staticmethod
    def create_course_points():
        return defaultdict(lambda: np.array([]))

    @staticmethod
    def normalize_turn_type(point_type):
        return normalize_turn_type(point_type)

    @classmethod
    def normalize_course_point_types(cls, course_points):
        if "type" not in course_points or not len(course_points["type"]):
            return
        course_points["type"] = np.array(
            [cls.normalize_turn_type(point_type) for point_type in course_points["type"]]
        )

    @staticmethod
    def validate_course_data(course, course_points):
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

        return valid_course

    @classmethod
    def reset_invalid_course_data(cls):
        return cls.create_course(), cls.create_course_points()

    @staticmethod
    def filter_straight_course_points(course_points, keys):
        if not len(course_points["type"]):
            return

        not_straight_cond = np.where(course_points["type"] != "Straight", True, False)
        for key in keys:
            if key in course_points:
                course_points[key] = course_points[key][not_straight_cond]
