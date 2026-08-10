import asyncio
import hashlib
import json
import math
import struct
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from modules.helper.livetrack import (
    LiveTrackSample,
    load_private_json,
    save_private_json,
    utc_now,
)

API_BASE_URL = "https://api.gcs.garmin.com"
IT_TOKEN_URL = "https://services.garmin.com/api/oauth/token"
DEFAULT_IT_CLIENT_ID = "GARMIN_CONNECT_MOBILE_ANDROID_2025Q2"
DEFAULT_TOKENSTORE = "~/.garminconnect"
IT_TOKEN_FILENAME = "livetrack_it_token.json"
STATE_FILENAME = "livetrack_state.json"
PUBLISHER_TYPE = "WEARABLE"
DEFAULT_DURATION = "PT6H"
DEFAULT_VIEWABLE = "PT24H"
DEFAULT_ALTITUDE_METERS = 3.5
COURSE_PATH = "/tracker/livetrack/api/v1/course"
COURSES_PATH = "/tracker/livetrack/api/v1/courses"
COURSE_SESSION_PATH = "/tracker/livetrack/api/v1/sessions"
FIT_TIMESTAMP_BASE = 0x10000000


class GarminLiveTrackError(RuntimeError):
    """Base exception for Garmin LiveTrack integration."""


class GarminLiveTrackConfigurationError(GarminLiveTrackError):
    """Raised when local Garmin LiveTrack settings are incomplete."""


class GarminLiveTrackApiError(GarminLiveTrackError):
    """Raised when Garmin LiveTrack API calls fail."""


def semicircle(degrees):
    """Convert degrees to the signed semicircle format used by Garmin."""
    if not -180.0 <= degrees <= 180.0:
        raise ValueError(f"Coordinate is outside the supported range: {degrees}")
    return round(degrees * (1 << 31) / 180.0)


def safe_response_details(response):
    """Return short non-secret response details for troubleshooting."""
    details = []
    authenticate = response.headers.get("WWW-Authenticate")
    if authenticate:
        details.append(f"WWW-Authenticate={authenticate}")
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        for key in ("error", "error_description", "code", "message", "reason"):
            value = body.get(key)
            if isinstance(value, (str, int, float, bool)):
                text = str(value).replace("\n", " ").strip()
                if text and len(text) <= 240 and "token=" not in text.lower():
                    details.append(f"{key}={text}")
    return f" ({'; '.join(details)})" if details else ""


def _clean(value):
    value = str(value or "").strip()
    return value or None


def _bounded_int(value, minimum=0, maximum=None):
    if value is None:
        return None
    number = int(value)
    if number < minimum:
        return minimum
    if maximum is not None and number > maximum:
        return maximum
    return number


def _decimal_string(value, default=0.0, minimum=None):
    if value is None:
        value = default
    number = float(value)
    if minimum is not None and number < minimum:
        number = minimum
    return f"{number:.2f}"


def _utc_timestamp(timestamp):
    if timestamp is None:
        return None
    try:
        value = datetime.fromtimestamp(float(timestamp), timezone.utc)
    except (OSError, OverflowError, TypeError, ValueError):
        return None
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _fit_definition(local_num, global_num, fields):
    data = struct.pack("<BBBHB", 0x40 | local_num, 0, 0, global_num, len(fields))
    return data + b"".join(struct.pack("<BBB", *field) for field in fields)


def _fit_crc(data):
    crc = 0
    table = (
        0x0000,
        0xCC01,
        0xD801,
        0x1400,
        0xF001,
        0x3C00,
        0x2800,
        0xE401,
        0xA001,
        0x6C00,
        0x7800,
        0xB401,
        0x5000,
        0x9C01,
        0x8801,
        0x4400,
    )
    for byte in data:
        crc = (crc >> 4) ^ table[crc & 0xF] ^ table[byte & 0xF]
        crc = (crc >> 4) ^ table[crc & 0xF] ^ table[(byte >> 4) & 0xF]
    return crc


def _fit_name(value):
    raw = str(value or "Pi Zero Bikecomputer").encode("utf-8")[:63]
    return raw.decode("utf-8", errors="ignore").encode("utf-8") + b"\0"


def build_course_fit(course):
    """Build a deterministic FIT course from the currently loaded route."""
    latitudes = list(course.latitude)
    longitudes = list(course.longitude)
    distances = list(getattr(course, "distance", ()))
    altitudes = list(getattr(course, "altitude", ()))
    rows = []
    previous_distance = 0.0
    for index, (latitude, longitude) in enumerate(zip(latitudes, longitudes)):
        latitude = float(latitude)
        longitude = float(longitude)
        if not (
            math.isfinite(latitude)
            and math.isfinite(longitude)
            and -90.0 <= latitude <= 90.0
            and -180.0 <= longitude <= 180.0
        ):
            continue
        distance = float(distances[index]) * 1000 if index < len(distances) else 0
        if not math.isfinite(distance):
            distance = previous_distance
        distance = max(previous_distance, distance)
        previous_distance = distance
        altitude = float(altitudes[index]) if index < len(altitudes) else None
        if altitude is not None and not math.isfinite(altitude):
            altitude = None
        rows.append(
            (
                semicircle(latitude),
                semicircle(longitude),
                min(round(distance * 100), 0xFFFFFFFE),
                altitude,
            )
        )
    if not rows:
        raise GarminLiveTrackConfigurationError(
            "Garmin LiveTrack course has no valid positions."
        )

    name = _fit_name(getattr(course, "info", {}).get("Name"))
    fingerprint = hashlib.sha256(name)
    for latitude, longitude, distance, altitude in rows:
        fingerprint.update(struct.pack("<iiI", latitude, longitude, distance))
        fingerprint.update(struct.pack("<d", altitude or 0.0))
    serial_number = int.from_bytes(fingerprint.digest()[:4], "little") or 1
    duration_sec = max(len(rows) - 1, 1)
    end_timestamp = FIT_TIMESTAMP_BASE + duration_sec
    elapsed_ms = duration_sec * 1000

    data = bytearray()
    data += _fit_definition(
        0,
        0,
        ((0, 1, 0x00), (1, 2, 0x84), (2, 2, 0x84), (3, 4, 0x8C), (4, 4, 0x86)),
    )
    data += struct.pack("<BBHHII", 0, 6, 255, 1, serial_number, FIT_TIMESTAMP_BASE)
    data += _fit_definition(
        1,
        31,
        ((4, 1, 0x00), (5, len(name), 0x07), (6, 4, 0x8C)),
    )
    data += struct.pack(f"<BB{len(name)}sI", 1, 2, name, 3)
    data += _fit_definition(
        2,
        19,
        (
            (253, 4, 0x86),
            (2, 4, 0x86),
            (3, 4, 0x85),
            (4, 4, 0x85),
            (5, 4, 0x85),
            (6, 4, 0x85),
            (7, 4, 0x86),
            (8, 4, 0x86),
            (9, 4, 0x86),
        ),
    )
    data += struct.pack(
        "<BIIiiiiIII",
        2,
        end_timestamp,
        FIT_TIMESTAMP_BASE,
        rows[0][0],
        rows[0][1],
        rows[-1][0],
        rows[-1][1],
        elapsed_ms,
        elapsed_ms,
        rows[-1][2],
    )
    data += _fit_definition(
        3,
        21,
        ((253, 4, 0x86), (0, 1, 0x00), (1, 1, 0x00), (4, 1, 0x02)),
    )
    data += struct.pack("<BIBBB", 3, FIT_TIMESTAMP_BASE, 0, 0, 0)

    has_altitude = any(row[3] is not None for row in rows)
    record_fields = [(253, 4, 0x86), (0, 4, 0x85), (1, 4, 0x85)]
    if has_altitude:
        record_fields.append((2, 2, 0x84))
    record_fields.append((5, 4, 0x86))
    data += _fit_definition(4, 20, tuple(record_fields))
    for index, (latitude, longitude, distance, altitude) in enumerate(rows):
        data += struct.pack("<BIii", 4, FIT_TIMESTAMP_BASE + index, latitude, longitude)
        if has_altitude:
            altitude_raw = 0xFFFF
            if altitude is not None:
                altitude_raw = min(max(round((altitude + 500) * 5), 0), 0xFFFE)
            data += struct.pack("<H", altitude_raw)
        data += struct.pack("<I", distance)

    data += struct.pack("<BIBBB", 3, end_timestamp, 0, 9, 0)
    header = struct.pack("<BBHI4s", 14, 0x10, 2014, len(data), b".FIT")
    header += struct.pack("<H", _fit_crc(header))
    body = header + data
    return body + struct.pack("<H", _fit_crc(body))


class GarminLiveTrackClient:
    """Client for Garmin Connect Mobile's private LiveTrack HTTP API."""

    def __init__(self, settings, garmin_cls=None):
        self.settings = settings
        self.garmin_cls = garmin_cls
        self._garmin = None
        self._credentials_cleared = False
        self.course_send_status = "RESET"
        self.course_send_revision = 0

    @property
    def tokenstore_path(self):
        return Path(
            _clean(self.settings.get("TOKENSTORE")) or DEFAULT_TOKENSTORE
        ).expanduser()

    @property
    def state_path(self):
        return self.tokenstore_path / STATE_FILENAME

    @property
    def it_token_path(self):
        return self.tokenstore_path / IT_TOKEN_FILENAME

    def enabled(self):
        return bool(self.settings.get("LIVETRACK_STATUS"))

    def configuration_reason(self):
        if self.garmin_cls is None:
            try:
                import garminconnect  # noqa: F401
            except ImportError:
                return (
                    "Garmin LiveTrack is disabled because garminconnect "
                    "is not installed."
                )

        email = _clean(self.settings.get("EMAIL"))
        password = _clean(self.settings.get("PASSWORD"))
        if not self.tokenstore_path.exists() and not (email and password):
            return (
                "Garmin LiveTrack is disabled because tokenstore or "
                "email/password is not configured."
            )
        try:
            self.publisher(self.load_state())
        except GarminLiveTrackConfigurationError as exc:
            return str(exc)
        return None

    def unavailable_reason(self):
        if not self.enabled():
            return None
        return self.configuration_reason()

    def load_state(self):
        try:
            return load_private_json(self.state_path, default={"schemaVersion": 1})
        except RuntimeError as exc:
            raise GarminLiveTrackConfigurationError(str(exc)) from exc

    def save_state(self, state):
        try:
            save_private_json(self.state_path, state)
        except OSError as exc:
            raise GarminLiveTrackConfigurationError(
                "Garmin LiveTrack state could not be saved."
            ) from exc

    def load_cached_it_token(self, min_ttl_sec=60):
        try:
            data = load_private_json(self.it_token_path, default=None)
        except RuntimeError as exc:
            raise GarminLiveTrackConfigurationError(str(exc)) from exc
        if not isinstance(data, dict):
            return None
        if data.get("clientId") != DEFAULT_IT_CLIENT_ID:
            return None
        token = data.get("accessToken")
        expires_at = data.get("expiresAt")
        if not isinstance(token, str) or not token:
            return None
        try:
            if float(expires_at) - time.time() <= min_ttl_sec:
                return None
        except (TypeError, ValueError):
            return None
        return token

    def login(self):
        if self._garmin is not None:
            return self._garmin
        if self.garmin_cls is None:
            try:
                from garminconnect import Garmin
            except ImportError as exc:
                raise GarminLiveTrackConfigurationError(
                    "Garmin LiveTrack is disabled because garminconnect "
                    "is not installed."
                ) from exc
            self.garmin_cls = Garmin

        email = _clean(self.settings.get("EMAIL"))
        password = _clean(self.settings.get("PASSWORD"))
        garmin = self.garmin_cls(
            email,
            password,
            prompt_mfa=lambda: "",
        )
        try:
            garmin.login(str(self.tokenstore_path))
        except Exception as exc:
            raise GarminLiveTrackConfigurationError(
                "Garmin authentication failed. Run an initial garminconnect login "
                "with email/password and MFA if required."
            ) from exc
        if (email or password) and self.tokenstore_path.exists():
            self.settings["EMAIL"] = ""
            self.settings["PASSWORD"] = ""
            self._credentials_cleared = True
        self._garmin = garmin
        return garmin

    def consume_credentials_cleared(self):
        if not self._credentials_cleared:
            return False
        self._credentials_cleared = False
        return True

    def oauth_headers(self):
        garmin = self.login()
        get_headers = getattr(garmin.client, "get_api_headers", None)
        if not callable(get_headers):
            raise GarminLiveTrackConfigurationError(
                "Installed garminconnect does not expose client.get_api_headers()."
            )
        return {str(key): str(value) for key, value in get_headers().items()}

    def exchange_it_access_token(self, force=False):
        if not force:
            cached_token = self.load_cached_it_token()
            if cached_token:
                return cached_token

        try:
            import requests
        except ImportError as exc:
            raise GarminLiveTrackConfigurationError(
                "Garmin LiveTrack requires the requests package."
            ) from exc

        garmin = self.login()
        di_token = getattr(getattr(garmin, "client", None), "di_token", None)
        if not isinstance(di_token, str) or not di_token:
            raise GarminLiveTrackConfigurationError(
                "Garmin DI token is missing. Refresh the garminconnect tokenstore."
            )

        headers = self.oauth_headers()
        for name in (
            "Authorization",
            "Cookie",
            "Origin",
            "Referer",
            "DI-Backend",
            "connect-csrf-token",
        ):
            headers.pop(name, None)
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            response = requests.post(
                IT_TOKEN_URL,
                params={"grant_type": "connect2_exchange"},
                headers=headers,
                data={
                    "client_id": DEFAULT_IT_CLIENT_ID,
                    "connect_access_token": di_token,
                },
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GarminLiveTrackApiError(
                "Garmin IT token exchange connection failed."
            ) from exc
        if not response.ok:
            raise GarminLiveTrackApiError(
                "Garmin IT token exchange failed with HTTP "
                f"{response.status_code}{safe_response_details(response)}."
            )

        try:
            data = response.json()
            access_token = data["access_token"]
            expires_in = int(data["expires_in"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GarminLiveTrackApiError(
                "Garmin IT token exchange returned an invalid response."
            ) from exc
        if not isinstance(access_token, str) or not access_token or expires_in <= 0:
            raise GarminLiveTrackApiError(
                "Garmin IT token exchange returned an invalid token."
            )

        try:
            save_private_json(
                self.it_token_path,
                {
                    "schemaVersion": 1,
                    "clientId": DEFAULT_IT_CLIENT_ID,
                    "accessToken": access_token,
                    "expiresAt": time.time() + expires_in,
                },
            )
        except OSError as exc:
            raise GarminLiveTrackConfigurationError(
                "Garmin IT token cache could not be saved."
            ) from exc
        return access_token

    def authenticated_headers(self, force_it_refresh=False):
        headers = self.oauth_headers()
        for name in (
            "Cookie",
            "Origin",
            "Referer",
            "DI-Backend",
            "connect-csrf-token",
        ):
            headers.pop(name, None)
        it_token = self.exchange_it_access_token(force=force_it_refresh)
        headers["Authorization"] = f"Bearer {it_token}"
        headers["X-Garmin-Client-ID"] = "GarminConnectMobileAndroid"
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        return headers

    def _request_direct_response(
        self, method, path, payload=None, params=None, files=None, timeout=20
    ):
        try:
            import requests
        except ImportError as exc:
            raise GarminLiveTrackConfigurationError(
                "Garmin LiveTrack requires the requests package."
            ) from exc

        response = None
        for attempt in range(2):
            headers = self.authenticated_headers(force_it_refresh=attempt == 1)
            if path in (COURSE_PATH, COURSE_SESSION_PATH) or path.startswith(
                COURSES_PATH + "/"
            ):
                headers["X-Garmin-Backend"] = "BTF"
            if files is not None:
                headers.pop("Content-Type", None)
            try:
                response = requests.request(
                    method,
                    API_BASE_URL + path,
                    headers=headers,
                    json=payload,
                    params=params,
                    files=files,
                    timeout=timeout,
                )
            except requests.RequestException as exc:
                raise GarminLiveTrackApiError("Garmin GCS connection failed.") from exc
            if response.status_code != 401 or attempt == 1:
                break

        if response is None:
            raise GarminLiveTrackApiError("Garmin GCS returned no response.")
        return response

    @staticmethod
    def _raise_for_response(response):
        if not response.ok:
            request_id = (
                response.headers.get("X-Request-Id")
                or response.headers.get("X-Correlation-Id")
                or "none"
            )
            raise GarminLiveTrackApiError(
                f"Garmin GCS returned HTTP {response.status_code} "
                f"(request id: {request_id}){safe_response_details(response)}."
            )

    @classmethod
    def _require_status(cls, response, expected):
        cls._raise_for_response(response)
        if response.status_code != expected:
            raise GarminLiveTrackApiError(
                "Garmin GCS returned unexpected HTTP "
                f"{response.status_code}; expected {expected}."
            )

    def request_direct(self, method, path, payload=None, params=None):
        response = self._request_direct_response(
            method, path, payload=payload, params=params
        )
        self._raise_for_response(response)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise GarminLiveTrackApiError("Garmin GCS returned non-JSON data.") from exc

    def ensure_course_registered(self, filename, fit_bytes, course_sha):
        response = self._request_direct_response("HEAD", f"{COURSES_PATH}/{course_sha}")
        if response.status_code == 200:
            return
        if response.status_code != 404:
            self._raise_for_response(response)
            raise GarminLiveTrackApiError(
                "Garmin course HEAD returned unexpected HTTP "
                f"{response.status_code}; expected 200 or 404."
            )

        response = self._request_direct_response(
            "POST",
            COURSE_PATH,
            files={"file": (filename, fit_bytes, "application/octet-stream")},
            timeout=90,
        )
        self._require_status(response, 201)
        response = self._request_direct_response("HEAD", f"{COURSES_PATH}/{course_sha}")
        self._require_status(response, 200)

    async def request_via_gadgetbridge(
        self, gadgetbridge_service, method, path, payload=None
    ):
        headers = await asyncio.to_thread(self.authenticated_headers)
        url = API_BASE_URL + path
        try:
            request_http_json = getattr(gadgetbridge_service, "request_http_json", None)
            if callable(request_http_json):
                response = await request_http_json(
                    url,
                    method=method,
                    headers=headers,
                    body=payload,
                    timeout=20,
                )
            else:
                response = await gadgetbridge_service.request_http(
                    url,
                    method=method,
                    headers=headers,
                    body=payload,
                    timeout=20,
                )
        except Exception as exc:
            raise GarminLiveTrackApiError(
                "Garmin GCS request via Gadgetbridge failed."
            ) from exc

        if callable(request_http_json):
            return self.validate_gadgetbridge_response(response)
        if not isinstance(response, dict):
            return None
        body = response.get("resp")
        if not body:
            return None
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise GarminLiveTrackApiError(
                "Garmin GCS returned non-JSON Gadgetbridge data."
            ) from exc
        return self.validate_gadgetbridge_response(parsed)

    @staticmethod
    def validate_gadgetbridge_response(response):
        """Reject Garmin error bodies when Gadgetbridge omits HTTP status."""
        if isinstance(response, dict) and (
            response.get("errors") or response.get("error")
        ):
            request_id = _clean(response.get("requestId")) or "none"
            raise GarminLiveTrackApiError(
                "Garmin GCS rejected the Gadgetbridge request "
                f"(request id: {request_id})."
            )
        return response

    async def request(self, method, path, payload=None, gadgetbridge_service=None):
        if gadgetbridge_service is not None:
            return await self.request_via_gadgetbridge(
                gadgetbridge_service,
                method,
                path,
                payload=payload,
            )
        return await asyncio.to_thread(self.request_direct, method, path, payload)

    def publisher(self, state):
        identifier = state.get("publisherIdentifier")
        if not identifier:
            identifier = str(uuid.uuid4())
            state["publisherIdentifier"] = identifier
            self.save_state(state)
        return {"identifier": identifier, "type": PUBLISHER_TYPE}

    @staticmethod
    def active_session(state):
        session = state.get("activeSession")
        if not isinstance(session, dict) or not session.get("sessionId"):
            return None
        return session

    def create_session_payload(self, sample, publisher):
        return {
            "defaultName": True,
            "duration": DEFAULT_DURATION,
            "locale": "ja-JP",
            "name": "Pi Zero Bikecomputer",
            "position": {
                "lat": semicircle(sample.latitude),
                "lon": semicircle(sample.longitude),
            },
            "publisher": publisher,
            "stravaEnabled": False,
            "viewable": DEFAULT_VIEWABLE,
        }

    @staticmethod
    def find_created_session(response):
        if not isinstance(response, dict):
            raise GarminLiveTrackApiError("Garmin session response is invalid.")
        sessions = response.get("liveTrackSessions")
        if not isinstance(sessions, list) or not sessions:
            raise GarminLiveTrackApiError(
                "Garmin session response has no liveTrackSessions."
            )
        for session in sessions:
            if isinstance(session, dict) and session.get("sessionId"):
                return session
        raise GarminLiveTrackApiError("Garmin session response has no sessionId.")

    async def create_session(self, sample, gadgetbridge_service=None):
        if not sample.has_position():
            return "no_position"

        state = self.load_state()
        if self.active_session(state):
            return "already_active"

        publisher = self.publisher(state)
        payload = self.create_session_payload(sample, publisher)
        response = await self.request(
            "POST",
            "/tracker/gcm-gateway/api/v1/sessions",
            payload=payload,
            gadgetbridge_service=gadgetbridge_service,
        )
        session = self.find_created_session(response)
        server_start = session.get("start") or response.get("start") or utc_now()
        activity_start = _utc_timestamp(sample.activity_start_timestamp) or server_start
        state["activeSession"] = {
            "sessionId": str(session["sessionId"]),
            "url": session.get("url"),
            "createdAt": server_start,
            "activityCreatedAt": activity_start,
            "viewable": payload["viewable"],
            "pointCount": 0,
        }
        state["schemaVersion"] = 1
        self.save_state(state)
        return "created"

    def point_payload(self, samples, publisher, session):
        first_sample = samples[0]
        created_at = str(
            session.get("activityCreatedAt")
            or _utc_timestamp(first_sample.activity_start_timestamp)
            or session.get("createdAt")
            or utc_now()
        )
        point_count = int(session.get("pointCount", 0))
        points = []
        for index, sample in enumerate(samples):
            speed_mps = _decimal_string(sample.speed_mps, minimum=0.0)
            distance_m = _decimal_string(sample.distance_m, minimum=0.0)
            duration = _decimal_string(sample.active_duration_sec, minimum=0.0)
            altitude = sample.altitude_m
            if altitude is None:
                altitude = sample.gps_altitude_m
            if altitude is None:
                altitude = DEFAULT_ALTITUDE_METERS

            fitness_data = {
                "activityCreatedTime": created_at,
                "activityType": "CYCLING",
                "distanceMeters": distance_m,
                "durationSecs": duration,
                "pointStatus": ("MOVING" if float(speed_mps) > 0 else "STATIONARY"),
                "speedMetersPerSec": speed_mps,
                "totalDistanceMeters": distance_m,
                "totalDurationSecs": duration,
            }
            cadence = _bounded_int(sample.cadence_rpm)
            if cadence is not None:
                fitness_data["cadenceCyclesPerMin"] = cadence
            heart_rate = _bounded_int(sample.heart_rate_bpm)
            if heart_rate is not None:
                fitness_data["heartRateBeatsPerMin"] = heart_rate
            if sample.power_w is not None:
                fitness_data["powerWatts"] = _decimal_string(
                    sample.power_w,
                    minimum=0.0,
                )
            fitness_data["accumulatedPowerWatts"] = _decimal_string(
                sample.accumulated_power_j,
                minimum=0.0,
            )
            if point_count == 0 and index == 0:
                fitness_data["eventTypes"] = ["BEGIN"]

            points.append(
                {
                    "altitude": _decimal_string(altitude),
                    "dateTime": _utc_timestamp(sample.timestamp) or utc_now(),
                    "fitnessPointData": fitness_data,
                    "position": {
                        "lat": semicircle(sample.latitude),
                        "lon": semicircle(sample.longitude),
                    },
                    "speed": speed_mps,
                }
            )
        return {
            "publisher": publisher,
            "trackPoints": points,
        }

    async def post_points(
        self, samples, gadgetbridge_service=None, create_session=True
    ):
        samples = [sample for sample in samples if sample.has_position()]
        if not samples:
            return "no_position"

        state = self.load_state()
        if create_session:
            create_status = await self.create_session(
                samples[0],
                gadgetbridge_service=gadgetbridge_service,
            )
            if create_status == "no_position":
                return create_status
            state = self.load_state()
        elif self.active_session(state) is None:
            return "not_active"

        session = self.active_session(state)
        if session is None:
            raise GarminLiveTrackConfigurationError(
                "Garmin LiveTrack session is missing after create."
            )
        publisher = self.publisher(state)
        payload = self.point_payload(samples, publisher, session)
        await self.request(
            "POST",
            "/tracker/livetrack/api/v1/trackpoints",
            payload=payload,
            gadgetbridge_service=gadgetbridge_service,
        )
        session["pointCount"] = int(session.get("pointCount", 0)) + len(
            payload["trackPoints"]
        )
        session["lastPointAt"] = payload["trackPoints"][-1]["dateTime"]
        state["activeSession"] = session
        self.save_state(state)
        return "success"

    @staticmethod
    def stop_payload(publisher):
        return {
            "end": utc_now(),
            "publisher": publisher,
            "viewable": DEFAULT_VIEWABLE,
        }

    async def stop_session(self, gadgetbridge_service=None):
        state = self.load_state()
        session = self.active_session(state)
        if session is None:
            return "not_active"
        publisher = self.publisher(state)
        payload = self.stop_payload(publisher)
        await self.request(
            "PATCH",
            "/tracker/livetrack/api/v1/sessions/",
            payload=payload,
            gadgetbridge_service=gadgetbridge_service,
        )
        state.pop("activeSession", None)
        self.save_state(state)
        return "success"

    async def send_course(self, course, reset=False):
        state = self.load_state()
        session = self.active_session(state)
        if session is None:
            return "not_active"

        publisher = self.publisher(state)
        if reset:
            await self.request(
                "PATCH",
                COURSE_SESSION_PATH,
                payload={"courseIds": [], "publisher": publisher},
            )
            session.pop("courseId", None)
            state["activeSession"] = session
            self.save_state(state)
            return "success"

        fit_bytes = await asyncio.to_thread(build_course_fit, course)
        course_sha = hashlib.sha256(fit_bytes).hexdigest().upper()
        name = _fit_name(getattr(course, "info", {}).get("Name"))[:-1]
        filename = (name.decode("utf-8") or "course") + ".fit"
        await asyncio.to_thread(
            self.ensure_course_registered,
            filename,
            fit_bytes,
            course_sha,
        )
        if session.get("courseId") and session["courseId"] != course_sha:
            await self.request(
                "PATCH",
                COURSE_SESSION_PATH,
                payload={"courseIds": [], "publisher": publisher},
            )
        await self.request(
            "PATCH",
            COURSE_SESSION_PATH,
            payload={"courseIds": [course_sha], "publisher": publisher},
        )
        session["courseId"] = course_sha
        state["activeSession"] = session
        self.save_state(state)
        return "success"
