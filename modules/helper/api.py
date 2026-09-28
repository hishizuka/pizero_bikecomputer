import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
import urllib.parse
import asyncio
import json

import numpy as np

from modules.helper.network import (
    get_bytes,
    get_json,
    post,
)
from modules.helper.maptile import MapTileWithValues
from modules.utils.geo import get_heading_str
from modules.app_logger import app_logger
from modules.helper.garmin_livetrack import (
    GarminLiveTrackApiError,
    GarminLiveTrackClient,
    GarminLiveTrackConfigurationError,
    GarminLiveTrackError,
    GarminLiveTrackMessageHttpError,
)
from modules.helper.livetrack import (
    LiveTrackCoordinator,
    LiveTrackRequest,
    build_livetrack_sample,
    run_with_bt_tethering,
)
from modules.helper.thingsboard_livetrack import ThingsBoardLiveTrackClient

_IMPORT_GARMINCONNECT = False
try:
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectInvalidFileFormatError,
        GarminConnectTooManyRequestsError,
    )

    _IMPORT_GARMINCONNECT = True
except ImportError:
    pass


class api:
    config = None
    UBLOX_ASSISTNOW_RETRY_DELAYS = (15.0, 30.0, 60.0)

    maptile_with_values = None

    send_time = {}
    pre_value = {"OPENMETEO_WIND": [np.nan, np.nan]}
    livetrack_unavailable_reason = None
    livetrack_unavailable_notified = False
    garmin_livetrack_client = None
    garmin_livetrack_unavailable_reason = None
    garmin_livetrack_unavailable_notified = False
    garmin_messages_unavailable_notified = False

    def __init__(self, config):
        self.config = config
        self.send_time = {}

        t = int(time.time())
        self.send_time["OPENMETEO_WIND"] = t

        self.livetrack_unavailable_reason = None
        self.livetrack_unavailable_notified = False
        self.garmin_livetrack_unavailable_reason = None
        self.garmin_livetrack_unavailable_notified = False
        self.garmin_messages_unavailable_notified = False
        self.garmin_stop_failure_notified = False
        self.garmin_stop_retry_task = None

        self.thingsboard_livetrack_client = ThingsBoardLiveTrackClient(
            self.config,
            lambda: self.gadgetbridge_service,
        )
        self.livetrack_unavailable_reason = (
            self.thingsboard_livetrack_client.configuration_reason()
        )

        self.garmin_livetrack_client = GarminLiveTrackClient(
            self.config.G_GARMINCONNECT_API
        )
        self.garmin_livetrack_unavailable_reason = (
            self.garmin_livetrack_client.unavailable_reason()
        )

        self.livetrack_coordinator = self._create_livetrack_coordinator()

        self.maptile_with_values = MapTileWithValues(self.config)

    @property
    def network(self):
        return self.config.network

    @property
    def gadgetbridge_service(self):
        ble_uart = self.config.ble_uart
        if ble_uart is None or not ble_uart.status:
            return None
        return ble_uart

    async def _request_with_bt_tethering(self, caller_name, request, url, **kwargs):
        async with self.network.bt_tethering_session(caller_name) as connected:
            if not connected:
                return None
            return await request(url, **kwargs)

    def _check_livetrack_startup_config(self):
        client = self.thingsboard_livetrack_client
        if not client.enabled():
            return False

        self.livetrack_unavailable_reason = client.configuration_reason()
        if self.livetrack_unavailable_reason is None:
            return True

        self._notify_livetrack_unavailable(
            "livetrack_unavailable_notified",
            self.livetrack_unavailable_reason,
        )

        return False

    def _check_garmin_livetrack_startup_config(self):
        if not self.config.G_GARMINCONNECT_API["LIVETRACK_STATUS"]:
            return False

        reason = self.garmin_livetrack_unavailable_reason
        if reason is None:
            return True

        self._notify_livetrack_unavailable(
            "garmin_livetrack_unavailable_notified",
            reason,
        )
        return False

    def _notify_livetrack_unavailable(
        self, notified_attr, reason, title="LiveTrack disabled"
    ):
        if getattr(self, notified_attr, False):
            return True

        gui = self.config.gui
        popup_multiline = getattr(gui, "show_popup_multiline", None)
        if callable(popup_multiline) and getattr(gui, "msg_queue", None) is None:
            return False

        setattr(self, notified_attr, True)
        app_logger.warning(reason)
        if callable(popup_multiline):
            popup_multiline(
                title,
                reason,
                5,
            )
        else:
            popup = getattr(gui, "show_popup", None)
            if callable(popup):
                popup(title, 5)
        return True

    async def get_google_routes(self, x1, y1, x2, y2):
        if self.config.G_GOOGLE_ROUTES_API["TOKEN"] == "":
            return None
        if np.any(np.isnan([x1, y1, x2, y2])):
            return None

        routes_api = self.config.G_GOOGLE_ROUTES_API
        mode = routes_api["API_MODE"][routes_api["API_MODE_SETTING"]]
        payload = {
            "origin": {
                "location": {"latLng": {"latitude": y1, "longitude": x1}},
            },
            "destination": {
                "location": {"latLng": {"latitude": y2, "longitude": x2}},
            },
            "travelMode": mode["travelMode"],
            "languageCode": self.config.G_LANG.lower(),
            "units": "METRIC",
        }
        if "routeModifiers" in mode:
            payload["routeModifiers"] = mode["routeModifiers"]

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": routes_api["TOKEN"],
            "X-Goog-FieldMask": routes_api["FIELD_MASK"],
        }
        app_logger.debug(
            "Google Routes API request: "
            f"{payload['travelMode']} {y1},{x1} -> {y2},{x2}"
        )
        response = await self._request_with_bt_tethering(
            self.get_google_routes.__name__,
            post,
            routes_api["URL"],
            headers=headers,
            json_data=payload,
            timeout=routes_api["TIMEOUT"],
        )
        app_logger.debug(response)
        return response

    async def get_google_route_from_mapstogpx(self, url):
        return await self._request_with_bt_tethering(
            self.get_google_route_from_mapstogpx.__name__,
            get_json,
            self.config.G_MAPSTOGPX["URL"]
            + "&lang={}&dtstr={}&gdata={}".format(
                self.config.G_LANG.lower(),
                datetime.now().strftime("%Y%m%d_%H%M%S"),
                urllib.parse.quote(url, safe=""),
            ),
            headers=self.config.G_MAPSTOGPX["HEADER"],
            timeout=self.config.G_MAPSTOGPX["TIMEOUT"],
        )

    async def get_ublox_assistnow_chipcode(
        self,
        ztp_token,
        sec_uniqid_raw,
        mon_ver_raw,
    ):
        assistnow_config = self.config.G_GPS_UBLOX["ASSISTNOW"]
        endpoint = assistnow_config["ZTP_ENDPOINT"].strip()
        if not endpoint:
            raise RuntimeError("AssistNow ZTP_ENDPOINT is not configured")

        payload = {
            "token": ztp_token,
            "messages": {
                "UBX-SEC-UNIQID": sec_uniqid_raw.hex().upper(),
                "UBX-MON-VER": mon_ver_raw.hex().upper(),
            },
        }
        data = await post(
            endpoint,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
        )
        if not data:
            raise RuntimeError("AssistNow ZTP failed")
        if "chipcode" not in data:
            message = data.get("Message") or data.get("message") or str(data)
            raise RuntimeError(f"AssistNow ZTP failed: {message[:200]}")
        return data["chipcode"]

    @asynccontextmanager
    async def ublox_assistnow_session(self):
        caller_name = self.ublox_assistnow_session.__name__
        bt_open_result = await self.network.open_bt_tethering(caller_name)
        if not bt_open_result.is_success():
            raise RuntimeError(f"AssistNow BT tethering failed: {bt_open_result.value}")

        try:
            yield
        finally:
            try:
                await self.network.close_bt_tethering(caller_name)
            except Exception as exc:
                app_logger.error(f"close_bt_tethering error: {exc}")

    async def run_ublox_assistnow_session(self, request):
        for retry_count in range(len(self.UBLOX_ASSISTNOW_RETRY_DELAYS) + 1):
            try:
                async with self.ublox_assistnow_session():
                    return await request()
            except Exception as exc:
                if retry_count >= len(self.UBLOX_ASSISTNOW_RETRY_DELAYS):
                    raise
                delay = self.UBLOX_ASSISTNOW_RETRY_DELAYS[retry_count]
                app_logger.warning(
                    "AssistNow communication failed: "
                    f"{exc}; retrying in {delay:g}s "
                    f"(attempt {retry_count + 1}/"
                    f"{len(self.UBLOX_ASSISTNOW_RETRY_DELAYS)})"
                )
                await asyncio.sleep(delay)

    async def get_ublox_assistnow_data(self, chipcode):
        assistnow_config = self.config.G_GPS_UBLOX["ASSISTNOW"]
        service_url = assistnow_config["SERVICE_URL"].strip()
        if not service_url:
            raise RuntimeError("AssistNow SERVICE_URL is not configured")

        params = {
            "chipcode": chipcode,
            "gnss": assistnow_config["GNSS"].strip(),
            "data": assistnow_config["DATA"].strip(),
        }
        if not params["gnss"] or not params["data"]:
            raise RuntimeError("AssistNow GNSS or DATA is not configured")

        data = await get_bytes(
            service_url,
            params=params,
            timeout=float(assistnow_config["TIMEOUT"]),
        )
        if not data:
            raise RuntimeError("AssistNow data failed")
        if not data.startswith(b"\xb5\x62"):
            text = data.decode("utf-8", errors="replace")
            raise RuntimeError(f"AssistNow data is not UBX: {text[:200]}")
        return data

    async def get_openmeteo_temperature_data(self, x, y):
        if np.any(np.isnan([x, y])):
            return None

        vars_str = "temperature_2m,pressure_msl,surface_pressure"
        url = "{}?latitude={}&longitude={}&current={}".format(
            self.config.G_OPENMETEO_API["URL"], y, x, vars_str
        )
        # response["elevation"], response["current"][{vars}]
        return await self._request_with_bt_tethering(
            self.get_openmeteo_temperature_data.__name__, get_json, url
        )

    async def get_openmeteo_current_wind_data(self, pos, forcast_time=None):

        # check pos
        if np.any(np.isnan(pos)):
            return [np.nan, np.nan]

        # check interval
        if forcast_time is None and not self.check_time_interval(
            "OPENMETEO_WIND", self.config.G_OPENMETEO_API["INTERVAL_SEC"], False
        ):
            return self.pre_value["OPENMETEO_WIND"]

        return await self.get_openmeteo_current_wind_data_internal(pos, forcast_time)

    async def get_openmeteo_current_wind_data_internal(self, pos, forcast_time=None):
        variables = (
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
        )
        values = await self.get_openmeteo_data_internal(pos, variables, forcast_time)
        if values is None:
            if forcast_time is None:
                return self.pre_value["OPENMETEO_WIND"]
            return [np.nan, np.nan]

        if forcast_time is None:
            wind_speed = values.get("wind_speed_10m")
            wind_direction = values.get("wind_direction_10m")
            if wind_speed is None or wind_direction is None:
                return self.pre_value["OPENMETEO_WIND"]
            self.pre_value["OPENMETEO_WIND"] = [
                wind_speed,
                wind_direction,
            ]
            return self.pre_value["OPENMETEO_WIND"]

        wind_speeds = values.get("wind_speed_10m")
        wind_directions = values.get("wind_direction_10m")
        if not wind_speeds or not wind_directions:
            return [np.nan, np.nan]
        return [wind_speeds[0], wind_directions[0]]

    async def get_openmeteo_data_internal(self, pos, variables, forecast_time=None):
        time_key = "current" if forecast_time is None else "hourly"
        params = {
            "latitude": pos[1],
            "longitude": pos[0],
            "wind_speed_unit": "ms",
            time_key: ",".join(variables),
        }
        if forecast_time is not None:
            hour = forecast_time.strftime("%Y-%m-%dT%H:%M")
            params["start_hour"] = hour
            params["end_hour"] = hour
        url = "{}?{}".format(
            self.config.G_OPENMETEO_API["URL"], urllib.parse.urlencode(params)
        )
        response = await self._request_with_bt_tethering(
            self.get_openmeteo_data_internal.__name__, get_json, url
        )

        if not isinstance(response, dict):
            return None
        values = response.get(time_key)
        return values if isinstance(values, dict) else None

    async def get_openmeteo_course_weather_data(self, pos, forecast_time):
        if np.any(np.isnan(pos)):
            return None

        variables = (
            "wind_speed_10m",
            "wind_direction_10m",
            "temperature_2m",
            "precipitation",
            "cloud_cover",
        )
        hourly = await self.get_openmeteo_data_internal(pos, variables, forecast_time)
        if hourly is None:
            return None

        weather = {}
        for output_key, response_key in (
            ("wind_speed", "wind_speed_10m"),
            ("wind_direction", "wind_direction_10m"),
            ("temperature", "temperature_2m"),
            ("precipitation", "precipitation"),
            ("cloud_cover", "cloud_cover"),
        ):
            values = hourly.get(response_key)
            if not values or values[0] is None:
                return None
            weather[output_key] = float(values[0])
        return weather

    async def get_ridewithgps_route(self, add=False, reset=False):
        if (
            self.config.G_RIDEWITHGPS_API["APIKEY"] == ""
            or self.config.G_RIDEWITHGPS_API["TOKEN"] == ""
        ):
            return None

        if reset:
            self.config.G_RIDEWITHGPS_API["USER_ROUTES_START"] = 0

        # get user id
        if self.config.G_RIDEWITHGPS_API["USER_ID"] == "":
            response = await get_json(
                self.config.G_RIDEWITHGPS_API["URL_USER_DETAIL"],
                params=self.config.G_RIDEWITHGPS_API["PARAMS"],
            )
            user = response.get("user")
            if user is not None:
                self.config.G_RIDEWITHGPS_API["USER_ID"] = user.get("id")
            if self.config.G_RIDEWITHGPS_API["USER_ID"] is None:
                return

        # get user route (total_num)
        if self.config.G_RIDEWITHGPS_API["USER_ROUTES_NUM"] is None:
            response = await get_json(
                self.config.G_RIDEWITHGPS_API["URL_USER_ROUTES"].format(
                    user=self.config.G_RIDEWITHGPS_API["USER_ID"], offset=0, limit=0
                ),
                params=self.config.G_RIDEWITHGPS_API["PARAMS"],
            )
            self.config.G_RIDEWITHGPS_API["USER_ROUTES_NUM"] = response["results_count"]

        # set offset(start) and limit(end)
        if add:
            if (
                self.config.G_RIDEWITHGPS_API["USER_ROUTES_START"]
                == self.config.G_RIDEWITHGPS_API["USER_ROUTES_NUM"]
            ):
                return None
            self.config.G_RIDEWITHGPS_API[
                "USER_ROUTES_START"
            ] += self.config.G_RIDEWITHGPS_API["USER_ROUTES_OFFSET"]
        offset = (
            self.config.G_RIDEWITHGPS_API["USER_ROUTES_NUM"]
            - self.config.G_RIDEWITHGPS_API["USER_ROUTES_START"]
            - self.config.G_RIDEWITHGPS_API["USER_ROUTES_OFFSET"]
        )
        limit = self.config.G_RIDEWITHGPS_API["USER_ROUTES_OFFSET"]
        if offset < 0:
            limit = offset + limit
            offset = 0
            self.config.G_RIDEWITHGPS_API["USER_ROUTES_START"] = (
                self.config.G_RIDEWITHGPS_API["USER_ROUTES_NUM"]
            )

        # get user route
        response = await get_json(
            self.config.G_RIDEWITHGPS_API["URL_USER_ROUTES"].format(
                user=self.config.G_RIDEWITHGPS_API["USER_ID"],
                offset=offset,
                limit=limit,
            ),
            params=self.config.G_RIDEWITHGPS_API["PARAMS"],
        )
        results = response.get("results")

        return results

    async def get_ridewithgps_files(self, route_id):
        urls = [
            (self.config.G_RIDEWITHGPS_API["URL_ROUTE_BASE_URL"] + ".json").format(
                route_id=route_id
            ),
        ]
        save_paths = [
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "course-{route_id}.json"
            ).format(route_id=route_id),
        ]
        await self.network.download_queue_put(
            {
                "urls": urls,
                "save_paths": save_paths,
                "params": self.config.G_RIDEWITHGPS_API["PARAMS"],
            }
        )
        return True

    def upload_check(self, blank_check, blank_msg, file_check=True):
        # blank check
        for b in blank_check:
            if b == "":
                app_logger.info(blank_msg)
                return False

        # file check
        if file_check and not os.path.exists(self.config.G_UPLOAD_FILE):
            app_logger.warning("file does not exist")
            return False

        return True

    async def strava_upload(self):
        blank_check = [
            self.config.G_STRAVA_API["CLIENT_ID"],
            self.config.G_STRAVA_API["CLIENT_SECRET"],
            self.config.G_STRAVA_API["CODE"],
            self.config.G_STRAVA_API["ACCESS_TOKEN"],
            self.config.G_STRAVA_API["REFRESH_TOKEN"],
        ]
        blank_msg = "set STRAVA settings (token, client_id, etc)"
        if not self.upload_check(blank_check, blank_msg):
            return False

        # reflesh access token
        data = {
            "client_id": self.config.G_STRAVA_API["CLIENT_ID"],
            "client_secret": self.config.G_STRAVA_API["CLIENT_SECRET"],
            "code": self.config.G_STRAVA_API["CODE"],
            "grant_type": "refresh_token",
            "refresh_token": self.config.G_STRAVA_API["REFRESH_TOKEN"],
        }
        tokens = await post(self.config.G_STRAVA_API_URL["OAUTH"], data=data)
        if not tokens:
            app_logger.error("strava token refresh failed (no response)")
            return False

        if (
            "access_token" in tokens
            and "refresh_token" in tokens
            and tokens["access_token"] != self.config.G_STRAVA_API["ACCESS_TOKEN"]
        ):
            # app_logger.debug("update strava tokens")
            self.config.G_STRAVA_API["ACCESS_TOKEN"] = tokens["access_token"]
            self.config.G_STRAVA_API["REFRESH_TOKEN"] = tokens["refresh_token"]
        elif "message" in tokens and tokens["message"].find("Error") > 0:
            app_logger.error("error occurs at refreshing tokens")
            return False

        # upload activity
        headers = {
            "Authorization": "Bearer " + self.config.G_STRAVA_API["ACCESS_TOKEN"]
        }
        data = {"data_type": "fit"}
        with open(self.config.G_UPLOAD_FILE, "rb") as file:
            data["file"] = file
            upload_result = await post(
                self.config.G_STRAVA_API_URL["UPLOAD"], headers=headers, data=data
            )
            if not upload_result:
                app_logger.error("strava upload failed (no response)")
                return False
            if "status" in upload_result:
                app_logger.info(upload_result["status"])

        return True

    async def garmin_upload(self):
        return await asyncio.get_running_loop().run_in_executor(
            None, self.garmin_upload_internal
        )

    def garmin_upload_internal(self):
        if not self.upload_check([], "", file_check=True):
            return False

        # import check
        if not _IMPORT_GARMINCONNECT:
            app_logger.warning("Install garminconnect")
            return False

        try:
            had_credentials = bool(
                self.config.G_GARMINCONNECT_API["EMAIL"]
                or self.config.G_GARMINCONNECT_API["PASSWORD"]
            )
            garmin_api = Garmin(
                email=self.config.G_GARMINCONNECT_API["EMAIL"] or None,
                password=self.config.G_GARMINCONNECT_API["PASSWORD"] or None,
            )
            garmin_api.login(self.config.G_GARMINCONNECT_API["TOKENSTORE"])
            if had_credentials:
                self.config.G_GARMINCONNECT_API["EMAIL"] = ""
                self.config.G_GARMINCONNECT_API["PASSWORD"] = ""
                setting = getattr(self.config, "setting", None)
                write_config = getattr(setting, "write_config", None)
                if callable(write_config):
                    write_config()
                    app_logger.info(
                        "[Garmin] cleared Garmin Connect email/password "
                        "after tokenstore login"
                    )
            if self.config.state.get_value("garmin_session", ""):
                self.config.state.set_value("garmin_session", "", force_apply=True)
        except (
            GarminConnectConnectionError,
            GarminConnectAuthenticationError,
            GarminConnectTooManyRequestsError,
        ) as err:
            app_logger.error(err)
            return False

        try:
            garmin_api.upload_activity(self.config.G_UPLOAD_FILE)
        except GarminConnectConnectionError as err:
            if "API Error 409" in str(err):
                app_logger.info("This activity has already been uploaded.")
                return True
            app_logger.error(err)
            return False
        except (
            GarminConnectAuthenticationError,
            GarminConnectInvalidFileFormatError,
            GarminConnectTooManyRequestsError,
        ) as err:
            app_logger.error(err)
            return False

        return True

    async def rwgps_upload(self):
        blank_check = [
            self.config.G_RIDEWITHGPS_API["APIKEY"],
            self.config.G_RIDEWITHGPS_API["TOKEN"],
        ]
        blank_msg = "set APIKEY or TOKEN of RWGPS"
        if not self.upload_check(blank_check, blank_msg):
            return False

        params = {
            "apikey": self.config.G_RIDEWITHGPS_API["APIKEY"],
            "version": "2",
            "auth_token": self.config.G_RIDEWITHGPS_API["TOKEN"],
            "trip[name]": "",
            "trip[description]": "",
            "trip[bad_elevations]": "false",
        }

        with open(self.config.G_UPLOAD_FILE, "rb") as file:
            response = await post(
                self.config.G_RIDEWITHGPS_API["URL_UPLOAD"],
                params=params,
                data={"file": file},
            )
            if not response:
                app_logger.error("rwgps upload failed (no response)")
                return False
            if response["success"] != 1:
                return False

        return True

    def livetrack_enabled(self):
        return (
            self.config.G_THINGSBOARD_API["STATUS"]
            or self.config.G_GARMINCONNECT_API["LIVETRACK_STATUS"]
        )

    def garmin_livetrack_configuration_reason(self):
        return self.garmin_livetrack_client.configuration_reason()

    def _persist_garmin_credentials_if_cleared(self):
        if not self.garmin_livetrack_client.consume_credentials_cleared():
            return
        self.config.setting.write_config()
        app_logger.info(
            "[Garmin] cleared Garmin Connect email/password after tokenstore login"
        )

    def send_livetrack_data(
        self,
        quick_send=False,
        garmin_action="update",
        include_thingsboard=True,
    ):
        request = LiveTrackRequest(
            garmin_action=garmin_action,
            include_thingsboard=include_thingsboard,
        )
        if not self._can_send_livetrack_request(request):
            return False
        return self.livetrack_coordinator.submit(
            request,
            quick_send=quick_send,
        )

    def _can_send_livetrack_request(self, request):
        if request.garmin_action == "reset":
            return True
        garmin_ready = self._check_garmin_livetrack_startup_config()
        if request.garmin_action == "stop":
            return garmin_ready
        thingsboard_ready = (
            request.include_thingsboard
            and self._check_livetrack_startup_config()
            and self.thingsboard_livetrack_client.has_path()
        )
        return thingsboard_ready or garmin_ready

    def _create_livetrack_coordinator(self):
        return LiveTrackCoordinator(
            lambda: self.config.G_THINGSBOARD_API["INTERVAL_SEC"],
            lambda: build_livetrack_sample(self.config),
            self._execute_livetrack_request,
        )

    async def _execute_livetrack_request(self, request, samples):
        caller_name = self._execute_livetrack_request.__name__
        telemetry_success = garmin_success = False
        send_status = None

        if request.include_thingsboard and self._check_livetrack_startup_config():
            telemetry_success, send_status = (
                await self.thingsboard_livetrack_client.send_samples(
                    samples, caller_name
                )
            )

        garmin_ready = request.garmin_action == "reset" or (
            self._check_garmin_livetrack_startup_config()
        )
        if garmin_ready:
            if request.garmin_action == "reset":
                garmin_status = await self._reset_garmin_livetrack(caller_name)
            elif request.garmin_action == "stop":
                garmin_status = await self._stop_garmin_livetrack(caller_name)
            else:
                garmin_status = await self._send_garmin_livetrack_samples(
                    samples,
                    caller_name,
                    self.config.G_MANUAL_STATUS != "STOP",
                )
            garmin_success = garmin_status in ("success", "not_active")

        if (
            garmin_success
            and request.garmin_action != "update"
            and self.config.G_MANUAL_STATUS == "START"
        ):
            self.livetrack_coordinator.submit(
                LiveTrackRequest(include_thingsboard=False),
                quick_send=True,
            )

        suffix = {"success": "", "open_error": "OE", "close_error": "CE"}.get(
            send_status
        )
        if suffix is not None or garmin_success:
            self.config.logger.sensor.values["integrated"][
                "send_time"
            ] = datetime.now().strftime("%H:%M") + (suffix or "")

        course_status = self.thingsboard_livetrack_client.course_send_status
        if telemetry_success and course_status in ("LOAD", "RESET"):
            revision = self.thingsboard_livetrack_client.course_send_revision
            success = await self.thingsboard_livetrack_client.send_course(
                self.config.logger.course,
                reset=course_status == "RESET",
            )
            self._complete_livetrack_course(
                self.thingsboard_livetrack_client,
                revision,
                success,
            )

        client = self.garmin_livetrack_client
        course_status = client.course_send_status
        if (
            garmin_success
            and request.garmin_action == "update"
            and course_status in ("LOAD", "RESET")
        ):
            revision = client.course_send_revision
            result = await self._send_garmin_livetrack_course(
                caller_name,
                reset=course_status == "RESET",
            )
            self._complete_livetrack_course(
                client,
                revision,
                result in ("success", "not_active"),
            )

        if garmin_success and request.garmin_action == "update":
            messages_status = await self._sync_garmin_message_capability(caller_name)
            if (
                self.config.G_MANUAL_STATUS == "START"
                and self.config.G_GARMINCONNECT_API["LIVETRACK_MESSAGES"]
                and messages_status in ("success", "unchanged")
            ):
                await self._receive_garmin_messages(caller_name)

    async def _run_garmin_transport(
        self,
        caller_name,
        operation,
        *,
        use_gadgetbridge=False,
        gadgetbridge_fallback=False,
        log_prefix="[Garmin]",
        purpose="LiveTrack",
    ):
        gadgetbridge_service = self.gadgetbridge_service if use_gadgetbridge else None
        if gadgetbridge_service is not None:
            try:
                return await operation(gadgetbridge_service)
            except GarminLiveTrackError:
                if not gadgetbridge_fallback:
                    raise
                app_logger.warning(
                    f"{log_prefix}[GB] request failed; falling back to direct HTTP"
                )
        status, value = await run_with_bt_tethering(
            self.network,
            caller_name,
            lambda: operation(None),
            log_prefix=log_prefix,
            purpose=purpose,
        )
        return value if status == "success" else status

    async def _run_garmin_messages_request(self, caller_name, action, operation):
        try:
            self.garmin_livetrack_client.load_btf_credentials()
            result = await self._run_garmin_transport(
                caller_name,
                operation,
                use_gadgetbridge=True,
                log_prefix="[Garmin Messages]",
                purpose="message service",
            )
            if result in ("network_unavailable", "open_error", "close_error"):
                app_logger.debug(
                    f"[Garmin Messages] {action} retry later: status={result}"
                )
            return result
        except GarminLiveTrackMessageHttpError as exc:
            if exc.status_code in (401, 403):
                self._notify_livetrack_unavailable(
                    "garmin_messages_unavailable_notified",
                    str(exc),
                    "Garmin Messages authentication failed",
                )
            else:
                app_logger.debug(f"[Garmin Messages] {action} retry later: {exc}")
        except GarminLiveTrackConfigurationError as exc:
            if self.config.G_GARMINCONNECT_API["LIVETRACK_MESSAGES"]:
                self._notify_livetrack_unavailable(
                    "garmin_messages_unavailable_notified",
                    str(exc),
                    "Garmin Messages unavailable",
                )
        except GarminLiveTrackError as exc:
            suffix = "[GB]" if self.gadgetbridge_service is not None else ""
            app_logger.debug(f"[Garmin Messages]{suffix} {action} retry later: {exc}")
        return "error"

    async def _sync_garmin_message_capability(self, caller_name):
        client = self.garmin_livetrack_client
        enabled = self.config.G_GARMINCONNECT_API["LIVETRACK_MESSAGES"]

        async def sync(gadgetbridge_service):
            return await client.sync_message_capability(
                enabled,
                gadgetbridge_service=gadgetbridge_service,
            )

        return await self._run_garmin_messages_request(caller_name, "capability", sync)

    def request_garmin_message_capability_update(self):
        client = self.garmin_livetrack_client
        if client.active_session(client.load_state()) is None:
            return
        asyncio.create_task(
            self._sync_garmin_message_capability(
                "request_garmin_message_capability_update"
            )
        )

    async def _receive_garmin_messages(self, caller_name):
        client = self.garmin_livetrack_client
        show_message = getattr(self.config.gui, "show_message", None)
        if not callable(show_message):
            app_logger.debug("[Garmin Messages] skipped: display unavailable")
            return

        async def receive(gadgetbridge_service):
            return await client.receive_messages(
                show_message,
                gadgetbridge_service=gadgetbridge_service,
            )

        await self._run_garmin_messages_request(caller_name, "receive", receive)

    async def _run_garmin_livetrack_operation(
        self, caller_name, operation, use_gadgetbridge=True
    ):
        try:
            return await self._run_garmin_transport(
                caller_name,
                operation,
                use_gadgetbridge=use_gadgetbridge,
                gadgetbridge_fallback=use_gadgetbridge,
            )
        except GarminLiveTrackError as exc:
            return self._handle_garmin_livetrack_error(exc)
        finally:
            self._persist_garmin_credentials_if_cleared()

    def _handle_garmin_livetrack_error(self, error):
        self.garmin_livetrack_unavailable_reason = str(error)
        self._notify_livetrack_unavailable(
            "garmin_livetrack_unavailable_notified",
            self.garmin_livetrack_unavailable_reason,
        )
        return "error"

    async def _send_garmin_livetrack_samples(
        self, samples, caller_name, create_session=True
    ):
        client = self.garmin_livetrack_client

        if create_session:
            try:
                start_ready = await self._prepare_garmin_livetrack_start(
                    samples[0], caller_name
                )
            except GarminLiveTrackError as exc:
                return self._handle_garmin_livetrack_error(exc)
            if not start_ready:
                return "deferred"

        async def operation(gadgetbridge_service):
            return await client.post_points(
                samples,
                gadgetbridge_service=gadgetbridge_service,
                create_session=create_session,
            )

        session_active = client.active_session(client.load_state()) is not None

        # Creating a session needs a confirmed response. Existing-session points
        # may use the legacy Gadgetbridge bridge, whose HTTP status is unavailable.
        result = await self._run_garmin_livetrack_operation(
            caller_name,
            operation,
            use_gadgetbridge=session_active,
        )
        if result == "success" and not session_active:
            client.course_send_status = (
                "LOAD" if self.config.logger.course.is_set else "RESET"
            )
        return result

    async def _prepare_garmin_livetrack_start(self, sample, caller_name):
        client = self.garmin_livetrack_client
        state = client.load_state()
        status = client.session_status(state, sample)

        if status == "stop_failed":
            if not self._notify_garmin_stop_failure():
                return False
            client.clear_session(preserve_pending=True)
            return True

        if status == "none":
            if "pendingStop" in state:
                client.clear_session()
            return True
        if status == "current":
            return True
        if status in ("expired", "invalid"):
            app_logger.warning(
                f"[Garmin] discarded {status} local LiveTrack session state"
            )
            client.clear_session()
            return True

        if status == "pending_stop":
            retry_delay = client.pending_retry_delay(state)
            if retry_delay > 0:
                self._schedule_garmin_stop_retry(retry_delay)
                return False
        else:
            client.request_stop()

        result = await self._stop_garmin_livetrack(caller_name)
        return result in ("success", "not_active")

    def _schedule_garmin_stop_retry(self, delay):
        task = self.garmin_stop_retry_task
        if task is not None and not task.done():
            return

        async def retry():
            await asyncio.sleep(delay)
            self.garmin_stop_retry_task = None
            self.livetrack_coordinator.submit(
                LiveTrackRequest(
                    garmin_action="stop",
                    include_thingsboard=False,
                ),
                quick_send=True,
            )

        self.garmin_stop_retry_task = asyncio.create_task(retry())
        app_logger.info(f"[Garmin] LiveTrack stop retry scheduled in {delay:.0f}s")

    def _cancel_garmin_stop_retry(self):
        task = self.garmin_stop_retry_task
        if task is not None and not task.done():
            task.cancel()
        self.garmin_stop_retry_task = None

    def _notify_garmin_stop_failure(self):
        if self.garmin_stop_failure_notified:
            return True
        message = (
            "Garmin LiveTrack could not be stopped. Location sharing may still "
            "be active. Reset the Garmin session from Live Track settings."
        )
        if not self._show_garmin_warning(message, wait_for_gui=True):
            return False
        self.garmin_stop_failure_notified = True
        return True

    def _show_garmin_warning(self, message, wait_for_gui=False):
        gui = self.config.gui
        popup = getattr(gui, "show_popup_multiline", None)
        if (
            wait_for_gui
            and callable(popup)
            and getattr(gui, "msg_queue", False) is None
        ):
            return False
        app_logger.warning(message)
        if callable(popup):
            popup("Garmin LiveTrack", message, 10)
        return True

    async def _stop_garmin_livetrack(self, caller_name, force_reset=False):
        client = self.garmin_livetrack_client
        attempt = client.begin_stop_attempt(force=force_reset)
        if attempt is None:
            if client.active_session(client.load_state()) is None:
                return "not_active"
            if not force_reset:
                self._notify_garmin_stop_failure()
            return "retry_exhausted"

        async def operation(_gadgetbridge_service):
            return await client.stop_session()

        transient = False
        try:
            result = await self._run_garmin_transport(
                caller_name,
                operation,
            )
            transient = result in ("open_error", "network_unavailable")
        except GarminLiveTrackApiError as exc:
            status_code = exc.status_code
            result = f"http_{status_code}" if status_code is not None else "error"
            transient = status_code is None or status_code >= 500
        except GarminLiveTrackError:
            result = "configuration_error"
        finally:
            self._persist_garmin_credentials_if_cleared()

        if (
            result == "close_error"
            and client.active_session(client.load_state()) is None
        ):
            result = "success"
        if result in ("success", "not_active"):
            self._cancel_garmin_stop_retry()
            self.garmin_stop_failure_notified = False
            message = (
                "session stopped"
                if result == "success"
                else "stop skipped: no active session"
            )
            app_logger.info(f"[Garmin] LiveTrack {message}")
        else:
            if not force_reset and attempt < 2 and transient:
                delay = self.network.bt_open_block_duration_sec
                retry_at = time.time() + delay
                client.record_stop_failure(retry_at=retry_at)
                self._schedule_garmin_stop_retry(delay)
            else:
                client.record_stop_failure()
                if not force_reset:
                    self._notify_garmin_stop_failure()
            app_logger.warning(
                f"[Garmin] LiveTrack stop did not complete: status={result}"
            )
        return result

    def send_garmin_livetrack_stop(self):
        if not self._check_garmin_livetrack_startup_config():
            return
        client = self.garmin_livetrack_client
        try:
            if not client.request_stop():
                app_logger.info("[Garmin] LiveTrack stop skipped: no active session")
                return
        except GarminLiveTrackError as exc:
            self.garmin_livetrack_unavailable_reason = str(exc)
            self._notify_livetrack_unavailable(
                "garmin_livetrack_unavailable_notified",
                self.garmin_livetrack_unavailable_reason,
            )
            return
        self.send_livetrack_data(
            quick_send=True,
            garmin_action="stop",
            include_thingsboard=False,
        )

    def reset_garmin_livetrack_session(self):
        return self.send_livetrack_data(
            quick_send=True,
            garmin_action="reset",
            include_thingsboard=False,
        )

    async def _reset_garmin_livetrack(self, caller_name):
        client = self.garmin_livetrack_client
        remote_result = "not_active"
        if client.request_stop():
            remote_result = await self._stop_garmin_livetrack(
                caller_name,
                force_reset=True,
            )

        self._cancel_garmin_stop_retry()
        client.clear_session()
        self.garmin_stop_failure_notified = False
        if remote_result not in ("success", "not_active"):
            message = (
                "Local Garmin LiveTrack state was reset, but the remote session "
                "may still be active."
            )
            self._show_garmin_warning(message)
        else:
            app_logger.info("[Garmin] LiveTrack session state reset")
        return "success"

    async def _send_garmin_livetrack_course(self, caller_name, reset=False):
        async def operation(_gadgetbridge_service):
            return await self.garmin_livetrack_client.send_course(
                self.config.logger.course,
                reset=reset,
            )

        result = await self._run_garmin_livetrack_operation(
            caller_name,
            operation,
            use_gadgetbridge=False,
        )
        if result == "success":
            action = "cleared" if reset else "attached"
            app_logger.info(f"[Garmin] LiveTrack course {action}")
        elif result != "not_active":
            app_logger.warning(
                f"[Garmin] LiveTrack course remains pending: status={result}"
            )
        return result

    def _queue_livetrack_course(self, reset):
        status = "RESET" if reset else "LOAD"
        clients = (
            self.thingsboard_livetrack_client,
            self.garmin_livetrack_client,
        )
        for client in clients:
            client.course_send_revision += 1
            client.course_send_status = status

    @staticmethod
    def _complete_livetrack_course(client, revision, success):
        if success and client.course_send_revision == revision:
            client.course_send_status = ""

    def send_livetrack_course_load(self):
        self._queue_livetrack_course(False)

    def send_livetrack_course_reset(self):
        self._queue_livetrack_course(True)

    def check_time_interval(self, time_key, interval_sec, quick_send):
        t = int(time.time())

        if not quick_send and t - self.send_time[time_key] < interval_sec:
            return False
        self.send_time[time_key] = t
        return True

    async def get_wind(self, pos, forecast_time=None):
        if self.config.G_WIND_DATA_SOURCE.startswith("jpn_scw"):
            w_spd, w_dir = await self.maptile_with_values.get_wind(pos, forecast_time)
        else:
            [w_spd, w_dir] = await self.get_openmeteo_current_wind_data(
                pos, forecast_time
            )

        w_dir_str = get_heading_str(w_dir)
        return w_spd, w_dir, w_dir_str

    async def get_course_weather(self, pos, forecast_time):
        source = self.config.G_COURSE_WEATHER_DATA_SOURCE
        if source.startswith("jpn_scw"):
            return await self.maptile_with_values.get_course_weather(
                pos, forecast_time, source
            )
        return await self.get_openmeteo_course_weather_data(pos, forecast_time)

    async def get_altitude(self, pos):
        return await self.maptile_with_values.get_altitude_from_tile(pos)
