import os

import numpy as np

from modules.app_logger import app_logger
from .base import LoaderBase

try:
    from fitparse import FitFile
except ImportError:
    FitFile = None


SEMICIRCLES_TO_DEGREES = 180 / 2**31


class FitLoader(LoaderBase):
    available = FitFile is not None

    @staticmethod
    def _position(value):
        if value is None:
            return None
        return float(value) * SEMICIRCLES_TO_DEGREES

    @staticmethod
    def _text(value):
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        return str(value or "").strip()

    @classmethod
    def load_file(cls, file):
        if not os.path.exists(file):
            return None, None
        if FitFile is None:
            app_logger.error("fitparse is required to load FIT courses")
            return None, None

        app_logger.info(f"[{cls.__name__}]: loading {file}")
        course = cls.create_course()
        course_points = cls.create_course_points()

        latitudes = []
        longitudes = []
        altitudes = []
        distances = []
        point_names = []
        point_types = []
        point_latitudes = []
        point_longitudes = []
        point_distances = []

        try:
            fit_file = FitFile(file)

            for message in fit_file.get_messages("course"):
                name = cls._text(message.get_value("name"))
                if name:
                    course["info"]["Name"] = name
                    break

            for message in fit_file.get_messages("record"):
                latitude = cls._position(message.get_value("position_lat"))
                longitude = cls._position(message.get_value("position_long"))
                if latitude is None or longitude is None:
                    continue

                altitude = message.get_value("enhanced_altitude")
                if altitude is None:
                    altitude = message.get_value("altitude")

                latitudes.append(latitude)
                longitudes.append(longitude)
                altitudes.append(altitude)
                distances.append(message.get_value("distance"))

            for message in fit_file.get_messages("course_point"):
                latitude = cls._position(message.get_value("position_lat"))
                longitude = cls._position(message.get_value("position_long"))
                if latitude is None or longitude is None:
                    continue

                point_type = cls.normalize_turn_type(message.get_value("type"))
                point_name = cls._text(message.get_value("name")) or point_type

                point_names.append(point_name)
                point_types.append(point_type)
                point_latitudes.append(latitude)
                point_longitudes.append(longitude)
                point_distances.append(message.get_value("distance"))
        except (OSError, TypeError, ValueError) as e:
            app_logger.error(f"Could not parse FIT course: {e}")
            return None, None

        course["latitude"] = np.array(latitudes)
        course["longitude"] = np.array(longitudes)

        if altitudes and all(value is not None for value in altitudes):
            course["altitude"] = np.array(altitudes, dtype=float)
        if distances and all(value is not None for value in distances):
            course["distance"] = np.array(distances, dtype=float)
            course["info"]["DistanceMeters"] = round(
                float(course["distance"][-1]) / 1000, 1
            )

        course_points["name"] = np.array(point_names)
        course_points["type"] = np.array(point_types)
        course_points["latitude"] = np.array(point_latitudes)
        course_points["longitude"] = np.array(point_longitudes)
        course_points["notes"] = np.array(point_names)
        if point_distances and all(value is not None for value in point_distances):
            course_points["distance"] = np.array(point_distances, dtype=float) / 1000

        valid_course = cls.validate_course_data(course, course_points)
        if not valid_course:
            course, course_points = cls.reset_invalid_course_data()
        else:
            cls.filter_straight_course_points(
                course_points,
                ["name", "latitude", "longitude", "notes", "type", "distance"],
            )

        return course, course_points
