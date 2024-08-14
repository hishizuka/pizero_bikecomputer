import os
import traceback
import time
from datetime import datetime
import socket
import urllib.parse
import asyncio

import numpy as np

from modules.utils.network import detect_network
from modules.helper.network import (
    post,
    get_json,
)
from modules.helper.maptile import (
    MapTileWithValues,
    get_headwind
)
from modules.utils.geo import get_track_str
from logger import app_logger

_IMPORT_GARMINCONNECT = False
try:
    from garth.exc import GarthHTTPError
    import requests
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
        GarminConnectTooManyRequestsError,
    )

    _IMPORT_GARMINCONNECT = True
except ImportError:
    pass

_IMPORT_STRAVA_COOKIE = False
try:
    from stravacookies import StravaCookieFetcher

    _IMPORT_STRAVA_COOKIE = True
except ImportError:
    pass

_IMPORT_THINGSBOARD = False
try:
    from tb_device_mqtt import TBDeviceMqttClient, TBPublishInfo

    _IMPORT_THINGSBOARD = True
except ImportError:
    pass


class api:
    config = None

    thingsboard_client = None
    course_send_status = "RESET"
    
    maptile_with_values = None

    send_livetrack_data_lock = False

    send_time = {}
    pre_value = {
        "OPENMETEO_WIND": [np.nan, np.nan]
    }

    def __init__(self, config):
        self.config = config

        t = int(time.time())
        self.send_time["OPENMETEO_WIND"] = t

        if _IMPORT_THINGSBOARD:
            self.thingsboard_client = TBDeviceMqttClient(
                self.config.G_THINGSBOARD_API["SERVER"],
                1883,
                self.config.G_THINGSBOARD_API["TOKEN"],
            )
            self.send_time["THINGSBOARD"] = t

        self.maptile_with_values = MapTileWithValues(self.config)

    async def get_google_routes(self, x1, y1, x2, y2):
        if not detect_network() or self.config.G_GOOGLE_DIRECTION_API["TOKEN"] == "":
            return None
        if np.any(np.isnan([x1, y1, x2, y2])):
            return None

        origin = f"origin={y1},{x1}"
        destination = f"destination={y2},{x2}"
        language = f"language={self.config.G_LANG}"
        url = "{}&{}&key={}&{}&{}&{}".format(
            self.config.G_GOOGLE_DIRECTION_API["URL"],
            self.config.G_GOOGLE_DIRECTION_API["API_MODE"][
                self.config.G_GOOGLE_DIRECTION_API["API_MODE_SETTING"]
            ],
            self.config.G_GOOGLE_DIRECTION_API["TOKEN"],
            origin,
            destination,
            language,
        )
        # print(url)
        response = await get_json(url)
        # print(response)
        return response

    async def get_google_route_from_mapstogpx(self, url):
        response = await get_json(
            self.config.G_MAPSTOGPX["URL"]
            + "&lang={}&dtstr={}&gdata={}".format(
                self.config.G_LANG.lower(),
                datetime.now().strftime("%Y%m%d_%H%M%S"),
                urllib.parse.quote(url, safe=""),
            ),
            headers=self.config.G_MAPSTOGPX["HEADER"],
            timeout=self.config.G_MAPSTOGPX["TIMEOUT"],
        )

        return response

    async def get_openmeteo_temperature_data(self, x, y):
        if not detect_network():
            return None
        if np.any(np.isnan([x, y])):
            return None

        vars_str = "temperature_2m,pressure_msl,surface_pressure"
        url = "{}?latitude={}&longitude={}&current={}".format(
            self.config.G_OPENMETEO_API["URL"],
            y,
            x,
            vars_str
        )
        response = await get_json(url)
        # response["elevation"], response["current"][{vars}]
        return response

    async def get_openmeteo_current_wind_data(self, pos):

        # check pos
        if np.any(np.isnan(pos)):
            return [np.nan, np.nan]

        # check interval
        if not self.check_time_interval(
            "OPENMETEO_WIND",
            self.config.G_OPENMETEO_API["INTERVAL_SEC"],
            False
        ):
            return self.pre_value["OPENMETEO_WIND"]
        
        # check network
        if not self.config.G_AUTO_BT_TETHERING and not detect_network():
            return self.pre_value["OPENMETEO_WIND"]

        asyncio.create_task(self.get_openmeteo_current_wind_data_internal(pos))
        return self.pre_value["OPENMETEO_WIND"]
    
    async def get_openmeteo_current_wind_data_internal(self, pos):

        # open connection
        f_name = self.get_openmeteo_current_wind_data_internal.__name__
        if not await self.config.network.open_bt_tethering(f_name):
            return

        vars_str = "wind_speed_10m,wind_direction_10m,wind_gusts_10m"
        url = "{}?latitude={}&longitude={}&current={}&wind_speed_unit=ms".format(
            self.config.G_OPENMETEO_API["URL"],
            pos[1],
            pos[0],
            vars_str
        )
        response = await get_json(url)
        # response["elevation"], response["current"][{vars}]

        # close connection
        await self.config.network.close_bt_tethering(f_name)

        if "current" in response:
            self.pre_value["OPENMETEO_WIND"] = [
                response["current"]["wind_speed_10m"],
                response["current"]["wind_direction_10m"]
            ]

    async def get_ridewithgps_route(self, add=False, reset=False):
        if (
            not detect_network()
            or self.config.G_RIDEWITHGPS_API["APIKEY"] == ""
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
            self.config.G_RIDEWITHGPS_API[
                "USER_ROUTES_START"
            ] = self.config.G_RIDEWITHGPS_API["USER_ROUTES_NUM"]

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
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_BASE_URL"]
                + "/hover_preview.png"
            ).format(route_id=route_id),
            # (self.config.G_RIDEWITHGPS_API["URL_ROUTE_BASE_URL"]+"/thumb.png").format(route_id=route_id),
            # not implemented
            # https://ridewithgps.com/routes/full/{route_id}.png
            # https://ridewithgps.com/routes/{route_id}/hover_preview@2x.png
        ]
        save_paths = [
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "course-{route_id}.json"
            ).format(route_id=route_id),
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "preview-{route_id}.png"
            ).format(route_id=route_id),
            # (self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]+"thumb-{route_id}.png").format(route_id=route_id),
        ]
        await self.config.network.download_queue.put(
            {
                "urls": urls,
                "save_paths": save_paths,
                "params": self.config.G_RIDEWITHGPS_API["PARAMS"],
            }
        )
        return True

    async def get_ridewithgps_files_with_privacy_code(self, route_id, privacy_code):
        urls = [
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_BASE_URL"]
                + "/elevation_profile.jpg?privacy_code={privacy_code}"
            ).format(route_id=route_id, privacy_code=privacy_code),
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_BASE_URL"]
                + ".tcx?privacy_code={privacy_code}"
            ).format(route_id=route_id, privacy_code=privacy_code),
        ]
        save_paths = [
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "elevation_profile-{route_id}.jpg"
            ).format(route_id=route_id),
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "course-{route_id}.tcx"
            ).format(route_id=route_id),
        ]
        await self.config.network.download_queue.put(
            {
                "urls": urls,
                "save_paths": save_paths,
                "params": self.config.G_RIDEWITHGPS_API["PARAMS"],
            }
        )
        return True

    def check_ridewithgps_files(self, route_id, mode):
        save_paths = [
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "course-{route_id}.json"
            ).format(route_id=route_id),
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "preview-{route_id}.png"
            ).format(route_id=route_id),
            # with privacy_code
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "elevation_profile-{route_id}.jpg"
            ).format(route_id=route_id),
            (
                self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]
                + "course-{route_id}.tcx"
            ).format(route_id=route_id),
        ]

        start = 0
        end = len(save_paths)
        if mode == "1st":
            end = 2
        elif mode == "2nd":
            start = 2

        for filename in save_paths[start:end]:
            if not os.path.exists(filename) or os.path.getsize(filename) == 0:
                return False

        return True

    def upload_check(self, blank_check, blank_msg, file_check=True):
        # network check
        if not detect_network():
            app_logger.warning("No Internet connection")
            return False

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
        tokens = await post(
            self.config.G_STRAVA_API_URL["OAUTH"], data=data
        )

        if (
            "access_token" in tokens
            and "refresh_token" in tokens
            and tokens["access_token"] != self.config.G_STRAVA_API["ACCESS_TOKEN"]
        ):
            # print("update strava tokens")
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
            if "status" in upload_result:
                app_logger.info(upload_result["status"])

        return True

    async def garmin_upload(self):
        return await asyncio.get_running_loop().run_in_executor(
            None, self.garmin_upload_internal
        )

    def garmin_upload_internal(self):
        blank_check = [
            self.config.G_GARMINCONNECT_API["EMAIL"],
            self.config.G_GARMINCONNECT_API["PASSWORD"],
        ]
        blank_msg = "set EMAIL or PASSWORD of Garmin Connect"
        if not self.upload_check(blank_check, blank_msg):
            return False

        # import check
        if not _IMPORT_GARMINCONNECT:
            app_logger.warning("Install garminconnect")
            return False

        try:
            tokenstore = self.config.state.get_value("garmin_session", "")
            if tokenstore == "":
                raise ValueError
            else:
                garmin_api = Garmin()
                garmin_api.login(tokenstore)
        except (
            ValueError,
            GarthHTTPError,
            GarminConnectAuthenticationError
        ):
            try:
                garmin_api = Garmin(
                    email=self.config.G_GARMINCONNECT_API["EMAIL"],
                    password=self.config.G_GARMINCONNECT_API["PASSWORD"]
                )
                garmin_api.login()
                self.config.state.set_value(
                    "garmin_session", garmin_api.garth.dumps(), force_apply=True
                )
            except (
                GarthHTTPError,
                GarminConnectAuthenticationError,
                requests.exceptions.HTTPError
            ) as err:
                app_logger.error(err)
                return False

        end_status = False

        for i in range(3):
            try:
                garmin_api.upload_activity(self.config.G_UPLOAD_FILE)
                end_status = True
                break
            except GarthHTTPError as err:
                # detect 409 in garth.exc.GarthHTTPError
                # Error in request: 409 Client Error: Conflict for url: https://connectapi.garmin.com/upload-service/upload
                if " 409 " in str(err):
                    app_logger.info("This activity has already been uploaded.")
                    end_status = True
                    break
            except (
                GarminConnectConnectionError,
                GarminConnectAuthenticationError,
                GarminConnectTooManyRequestsError,
            ) as err:
                app_logger.error(type(err))
                app_logger.error(err)
                return end_status

            time.sleep(1.0)

        return end_status

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
            if response["success"] != 1:
                return False

        return True

    def get_strava_cookie(self):
        blank_check = [
            self.config.G_STRAVA_COOKIE["EMAIL"],
            self.config.G_STRAVA_COOKIE["PASSWORD"],
        ]
        blank_msg = "set EMAIL or PASSWORD of STRAVA"
        if not self.upload_check(blank_check, blank_msg, file_check=False):
            return False

        # import check
        if not _IMPORT_STRAVA_COOKIE:
            app_logger.warning("Install stravacookies")
            return

        if not detect_network():
            return None

        strava_cookie = StravaCookieFetcher()
        try:
            strava_cookie.fetchCookies(
                self.config.G_STRAVA_COOKIE["EMAIL"],
                self.config.G_STRAVA_COOKIE["PASSWORD"],
            )
            self.config.G_STRAVA_COOKIE["KEY_PAIR_ID"] = strava_cookie.keyPairId
            self.config.G_STRAVA_COOKIE["POLICY"] = strava_cookie.policy
            self.config.G_STRAVA_COOKIE["SIGNATURE"] = strava_cookie.signature
        except:
            traceback.print_exc()

    def thingsboard_check(self):
        return (self.thingsboard_client is not None)

    def send_livetrack_data(self, quick_send=False):

        # check lock
        if self.send_livetrack_data_lock:
            return

        # check interval
        if not self.check_time_interval(
            "THINGSBOARD",
            self.config.G_THINGSBOARD_API["INTERVAL_SEC"],
            quick_send
        ):
            return

        # check module and network (common with send_livetrack_course_load/send_livetrack_course_reset)
        if not self.check_livetrack():
            return
        asyncio.create_task(self.send_livetrack_data_internal(quick_send))

    def check_livetrack(self):
        # import check
        if not _IMPORT_THINGSBOARD:
            # print("Install tb-mqtt-client")
            return False
        # network check
        if not self.config.G_AUTO_BT_TETHERING and not detect_network():
            # print("No Internet connection")
            return False
        return True

    async def send_livetrack_data_internal(self, quick_send=False):

        self.send_livetrack_data_lock = True
        f_name = self.send_livetrack_data_internal.__name__
        timestamp_str = ""
        t = int(time.time())
        if not self.config.G_DUMMY_OUTPUT:
            timestamp_str = datetime.fromtimestamp(t).strftime("%m/%d %H:%M")
        # app_logger.info(f"[TB] start, network: {bool(detect_network())}")

        # open connection
        v = self.config.logger.sensor.values
        if not await self.config.network.open_bt_tethering(f_name):
            v["integrated"]["send_time"] = (datetime.now().strftime("%H:%M") + "OE")
            self.send_livetrack_data_lock = False
            return

        speed = v["integrated"]["speed"]
        if not np.isnan(speed):
            speed = int(speed * 3.6)
        distance = v["integrated"]["distance"]
        if not np.isnan(distance):
            distance = round(distance / 1000, 1)

        data = {
            "ts": t * 1000,
            "values": {
                "timestamp": timestamp_str,
                "speed": speed,
                "distance": distance,
                "heartrate": v["integrated"]["ave_heart_rate_60s"],
                "power": v["integrated"]["ave_power_60s"],
                "work": int(v["integrated"]["accumulated_power"] / 1000),
                # 'w_prime_balance': v["integrated"]["w_prime_balance_normalized"],
                "temperature": v["integrated"]["temperature"],
                # 'altitude': v["I2C"]["altitude"],
                "latitude": v["GPS"]["lat"],
                "longitude": v["GPS"]["lon"],
            },
        }

        try:
            self.thingsboard_client.connect()
            res = self.thingsboard_client.send_telemetry(data).get()
            if res != TBPublishInfo.TB_ERR_SUCCESS:
                app_logger.error(f"[BT] thingsboard upload error: {res}")
            else:
                v["integrated"]["send_time"] = datetime.now().strftime("%H:%M")
        except socket.timeout as e:
            app_logger.error(f"[BT] socket timeout: {e}")
        except socket.error as e:
            app_logger.error(f"[BT] socket error: {e}")
        finally:
            self.thingsboard_client.disconnect()
        await asyncio.sleep(5)

        if self.course_send_status == "LOAD":
            await self.send_livetrack_course()
        elif self.course_send_status == "RESET":
            await self.send_livetrack_course(reset=True)

        # close connection
        if not await self.config.network.close_bt_tethering(f_name):
            v["integrated"]["send_time"] = (datetime.now().strftime("%H:%M") + "CE")
        # app_logger.info(f"[TB] end, network: {bool(detect_network())}")

        self.send_livetrack_data_lock = False

    async def send_livetrack_course(self, reset=False):
        if not reset and (
            not len(self.config.logger.course.latitude)
            or not len(self.config.logger.course.longitude)
        ):
            return

        course = []
        if not reset:
            c = np.stack(
                [
                    self.config.logger.course.latitude,
                    self.config.logger.course.longitude,
                ],
                axis=1,
            ).tolist()
            course = c + c[-2:0:-1]

        # send as polygon sources
        data = {"perimeter": course}

        # open connection
        f_name = self.send_livetrack_course.__name__
        if not await self.config.network.open_bt_tethering(f_name):
            return

        self.thingsboard_client.connect()
        res = self.thingsboard_client.send_telemetry(data).get()
        if res != TBPublishInfo.TB_ERR_SUCCESS:
            app_logger.error(f"thingsboard upload error: {res}")
        self.thingsboard_client.disconnect()

        # close connection
        await self.config.network.close_bt_tethering(f_name)
        
        self.course_send_status = ""

    def send_livetrack_course_load(self):
        self.course_send_status = "LOAD"
        if not self.check_livetrack():
            return
        asyncio.create_task(self.send_livetrack_course(False))

    def send_livetrack_course_reset(self):
        self.course_send_status = "RESET"
        if not self.check_livetrack():
            return
        asyncio.create_task(self.send_livetrack_course(True))
    
    def check_time_interval(self, time_key, interval_sec, quick_send):
        t = int(time.time())

        if not quick_send and t - self.send_time[time_key] < interval_sec:
            return False
        self.send_time[time_key] = t
        return True

    async def get_wind(self, pos, track):
        if self.config.G_WIND_DATA_SOURCE.startswith("jpn_scw"):
            w_spd, w_dir = await self.maptile_with_values.get_wind(pos)
        else:
            [w_spd, w_dir] = await self.get_openmeteo_current_wind_data(pos)
        
        w_dir_str = get_track_str(w_dir)
        
        headwind = get_headwind(w_spd, w_dir, track)
        
        # app_logger.info(f"pos:[{pos[0]:.5f},{pos[1]:.5f}], w_spd:{w_spd}, w_dir:{w_dir}, w_dir_str:{w_dir_str}, headwind:{headwind}")
        return w_spd, w_dir, w_dir_str, headwind
    
    async def get_altitude(self, pos):
        return await self.maptile_with_values.get_altitude_from_tile(pos)

