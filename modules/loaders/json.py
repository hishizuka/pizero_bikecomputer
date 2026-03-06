import json
import os

import numpy as np

from modules.app_logger import app_logger
from .base import LoaderBase


class JsonLoader(LoaderBase):
    @staticmethod
    def _as_float_or_none(value):
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def load_file(cls, file):
        if not os.path.exists(file):
            return None, None
        app_logger.info(f"[{cls.__name__}]: loading {file}")

        course = cls.create_course()
        course_points = cls.create_course_points()

        try:
            with open(file, "r", encoding="utf-8_sig") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            app_logger.error("Could not parse course")
            return None, None

        route = payload.get("route") if isinstance(payload, dict) else None
        if not isinstance(route, dict):
            app_logger.error("Could not parse course")
            return None, None

        route_name = route.get("name")
        if route_name is not None:
            course["info"]["Name"] = str(route_name).strip()

        route_distance = cls._as_float_or_none(route.get("distance"))
        if route_distance is not None:
            course["info"]["DistanceMeters"] = round(route_distance / 1000, 1)

        track_points = route.get("track_points")
        if not isinstance(track_points, list):
            track_points = []

        lat_values = []
        lon_values = []
        alt_values = []
        dist_values = []
        last_dist = 0.0
        for point in track_points:
            if not isinstance(point, dict):
                continue
            lon = cls._as_float_or_none(point.get("x"))
            lat = cls._as_float_or_none(point.get("y"))
            if lon is None or lat is None:
                continue

            dist = cls._as_float_or_none(point.get("d"))
            if dist is None:
                dist = last_dist
            else:
                last_dist = dist

            alt = cls._as_float_or_none(point.get("e"))
            if alt is None:
                alt = np.nan

            lon_values.append(lon)
            lat_values.append(lat)
            alt_values.append(alt)
            dist_values.append(dist)

        course["latitude"] = np.array(lat_values)
        course["longitude"] = np.array(lon_values)
        course["altitude"] = np.array(alt_values)
        course["distance"] = np.array(dist_values)

        raw_course_points = route.get("course_points")
        if not isinstance(raw_course_points, list):
            raw_course_points = []

        point_names = []
        point_types = []
        point_latitudes = []
        point_longitudes = []
        point_notes = []
        point_distances = []
        has_all_distances = True
        for point in raw_course_points:
            if not isinstance(point, dict):
                continue

            lon = cls._as_float_or_none(point.get("x"))
            lat = cls._as_float_or_none(point.get("y"))
            if lon is None or lat is None:
                continue

            point_type = cls.normalize_turn_type(point.get("t"))
            if point_type == "Straight":
                continue

            point_name = str(point.get("n", "")).strip()
            point_distance = cls._as_float_or_none(point.get("d"))
            if point_distance is None:
                has_all_distances = False
            else:
                point_distance /= 1000

            point_names.append(point_name)
            point_types.append(point_type)
            point_latitudes.append(lat)
            point_longitudes.append(lon)
            point_notes.append(point_name)
            point_distances.append(point_distance)

        course_points["name"] = np.array(point_names)
        course_points["latitude"] = np.array(point_latitudes)
        course_points["longitude"] = np.array(point_longitudes)
        course_points["type"] = np.array(point_types)
        course_points["notes"] = np.array(point_notes)
        if has_all_distances and len(point_distances):
            course_points["distance"] = np.array(point_distances)

        valid_course = cls.validate_course_data(course, course_points)

        if not valid_course:
            course, course_points = cls.reset_invalid_course_data()

        return course, course_points
