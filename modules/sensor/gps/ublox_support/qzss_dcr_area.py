import csv
import math
from pathlib import Path

from .qzss_dcr import DCX_MESSAGE_TYPE, JMA_MESSAGE_TYPE, _as_list

DEFAULT_POPUP_MARGIN_KM = 100.0

LOCATION_NEAR = "near"
LOCATION_FAR = "far"
LOCATION_UNKNOWN = "unknown"

_JMA_AREA_FIELDS = (
    ("eew", "eew_forecast_regions", "eew_forecast_regions_raw"),
    ("prefecture", "prefectures", "prefectures_raw"),
    ("tsunami", "tsunami_forecast_regions", "tsunami_forecast_regions_raw"),
    ("municipality", "local_governments", "local_governments_raw"),
    ("weather", "weather_forecast_regions", "weather_forecast_regions_raw"),
    ("flood", "flood_forecast_regions", "flood_forecast_regions_raw"),
    ("marine", "marine_forecast_regions", "marine_forecast_regions_raw"),
)
_DCX_JAPAN_AREA_FIELDS = (
    ("dcx", "ex1_target_area_ja", None),
    ("dcx", "ex9_target_area_list_ja", None),
)
_COORDINATE_FIELDS = (
    ("coordinates_of_hypocenter", 500.0),
    ("coordinates_of_typhoon", 500.0),
)
_CODE_DIVISORS = {"prefecture": 1, "weather": 10000, "municipality": 100000}


def coordinate(coordinates):
    if not isinstance(coordinates, dict):
        return None
    try:
        latitude = (
            float(coordinates["lat_d"])
            + float(coordinates.get("lat_m", 0)) / 60
            + float(coordinates.get("lat_s", 0)) / 3600
        )
        longitude = (
            float(coordinates["lon_d"])
            + float(coordinates.get("lon_m", 0)) / 60
            + float(coordinates.get("lon_s", 0)) / 3600
        )
    except (KeyError, TypeError, ValueError):
        return None
    if int(coordinates.get("lat_ns", 0)):
        latitude = -latitude
    if int(coordinates.get("lon_ew", 0)):
        longitude = -longitude
    return latitude, longitude


def _target(label, latitude, longitude, radius_km):
    try:
        return {
            "label": label,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "radius_km": float(radius_km),
        }
    except (TypeError, ValueError):
        return None


def target_key(target):
    return (
        round(target["latitude"], 5),
        round(target["longitude"], 5),
        round(target["radius_km"], 2),
    )


def distance_km(latitude1, longitude1, latitude2, longitude2):
    radius_km = 6371.0088
    latitude1 = math.radians(latitude1)
    latitude2 = math.radians(latitude2)
    delta_latitude = latitude2 - latitude1
    delta_longitude = math.radians(longitude2 - longitude1)
    value = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(latitude1) * math.cos(latitude2) * math.sin(delta_longitude / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


class QzssDcrAreaResolver:
    def __init__(self, csv_path=None):
        self.csv_path = Path(
            csv_path or Path(__file__).with_name("data") / "qzss_japan_area.csv"
        )
        self._by_code = {}
        self._prefectures = []
        self._load()

    @staticmethod
    def _normalize(label):
        return (
            str(label or "")
            .strip()
            .replace(" ", "")
            .replace("　", "")
            .replace("（", "(")
            .replace("）", ")")
        )

    def _load(self):
        if not self.csv_path.exists():
            return
        with self.csv_path.open(encoding="utf-8", newline="") as source:
            for row in csv.DictReader(source):
                namespace = row.get("namespace", "").strip()
                area = _target(
                    row.get("label", "").strip(),
                    row.get("latitude"),
                    row.get("longitude"),
                    row.get("radius_km"),
                )
                code = row.get("code", "").strip()
                if not area or not namespace:
                    continue
                if code:
                    self._by_code.setdefault((namespace, code), []).append(area)
                if namespace == "prefecture":
                    self._prefectures.append(area)

    @staticmethod
    def _prefecture_code(namespace, code):
        try:
            code = int(code)
        except (TypeError, ValueError):
            return ""
        divisor = _CODE_DIVISORS.get(namespace)
        return str(code // divisor) if divisor else ""

    @classmethod
    def _label_matches(cls, area_label, normalized_target):
        area_label = cls._normalize(area_label)
        short_area_label = (
            area_label[:-1]
            if area_label.endswith(("都", "道", "府", "県"))
            else area_label
        )
        return bool(normalized_target) and (
            area_label in normalized_target
            or normalized_target.startswith(short_area_label)
        )

    def _lookup(self, namespace, code, label):
        matches = self._by_code.get((namespace, str(code)))
        if not matches:
            prefecture_code = self._prefecture_code(namespace, code)
            matches = self._by_code.get(("prefecture", prefecture_code))
        if not matches:
            normalized_label = self._normalize(label)
            matches = [
                area
                for area in self._prefectures
                if self._label_matches(area["label"], normalized_label)
            ]
        return matches

    def resolve_area(self, namespace, label, code=""):
        matches = self._lookup(namespace, code, label) or []
        return list({target_key(item): item for item in matches}.values()), not matches

    @staticmethod
    def _area_fields(dcr, fields):
        message_type = dcr.get("message_type")
        if message_type == JMA_MESSAGE_TYPE:
            return _JMA_AREA_FIELDS
        if (
            message_type == DCX_MESSAGE_TYPE
            and fields.get("a2_country_region_name") == "Japan"
        ):
            return _DCX_JAPAN_AREA_FIELDS
        return ()

    def resolve_dcr(self, dcr):
        fields = dcr.get("report_fields") or {}
        targets = []
        unresolved = False

        if dcr.get("message_type") == JMA_MESSAGE_TYPE:
            for field_name, radius_km in _COORDINATE_FIELDS:
                coordinates = coordinate(fields.get(field_name))
                if coordinates:
                    targets.append(
                        _target(
                            field_name,
                            coordinates[0],
                            coordinates[1],
                            radius_km,
                        )
                    )

        ellipse = (
            fields.get(
                "c1_refined_latitude_of_centre_of_main_ellipse",
                fields.get("a12_ellipse_centre_latitude"),
            ),
            fields.get(
                "c2_refined_longitude_of_centre_of_main_ellipse",
                fields.get("a13_ellipse_centre_longitude"),
            ),
            fields.get(
                "c3_refined_length_of_semi_major_axis",
                fields.get("a14_ellipse_semi_major_axis"),
            ),
        )
        if all(value is not None for value in ellipse):
            ellipse_target = _target(
                fields.get("a2_country_region_name", "DCX"),
                *ellipse,
            )
            if ellipse_target:
                targets.append(ellipse_target)
            else:
                unresolved = True

        for namespace, label_field, code_field in self._area_fields(dcr, fields):
            labels = _as_list(fields.get(label_field))
            codes = _as_list(fields.get(code_field)) if code_field else []
            for index, label in enumerate(labels):
                code = codes[index] if index < len(codes) else ""
                matches, missing = self.resolve_area(namespace, label, code)
                targets.extend(matches)
                unresolved = unresolved or missing

        return list({target_key(item): item for item in targets}.values()), unresolved

    @staticmethod
    def evaluate(targets, unresolved, latitude, longitude, margin_km):
        try:
            latitude = float(latitude)
            longitude = float(longitude)
            margin_km = float(margin_km)
        except (TypeError, ValueError):
            return LOCATION_UNKNOWN
        if not math.isfinite(latitude) or not math.isfinite(longitude) or not targets:
            return LOCATION_UNKNOWN

        for target in targets:
            distance = distance_km(
                latitude,
                longitude,
                target["latitude"],
                target["longitude"],
            )
            if distance <= target["radius_km"] + margin_km:
                return LOCATION_NEAR
        return LOCATION_UNKNOWN if unresolved else LOCATION_FAR
