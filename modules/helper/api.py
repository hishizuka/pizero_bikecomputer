import os
import traceback
import random
import time
import asyncio
import aiofiles

import numpy as np

_IMPORT_GARMINCONNECT = False
try:
  from garminconnect import (
    Garmin,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
    GarminConnectAuthenticationError,
  )
  _IMPORT_GARMINCONNECT = True
except:
  pass

_IMPORT_STRAVA_COOKIE = False
try:
  from stravacookies import StravaCookieFetcher
  _IMPORT_STRAVA_COOKIE = True
except:
  pass

class api():

  config = None

  def __init__(self, config):
    self.config = config

  async def get_google_routes(self, x1, y1, x2, y2):

    if not self.config.detect_network() or self.config.G_GOOGLE_DIRECTION_API["TOKEN"] == "":
      return None
    if np.any(np.isnan([x1, y1, x2, y2])):
      return None
      
    origin = "origin={},{}".format(y1,x1)
    destination = "destination={},{}".format(y2,x2)
    url = "{}&{}&key={}&{}&{}".format(
      self.config.G_GOOGLE_DIRECTION_API["URL"],
      self.config.G_GOOGLE_DIRECTION_API["API_MODE"][self.config.G_GOOGLE_DIRECTION_API["API_MODE_SETTING"]],
      self.config.G_GOOGLE_DIRECTION_API["TOKEN"],
      origin,
      destination
    )
    #print(url)
    response = await self.config.network.get_json(url)
    #print(response)
    return response

  async def get_openweathermap_data(self, x, y):

    if not self.config.detect_network() or self.config.G_OPENWEATHERMAP_API["TOKEN"] == "":
      return None
    if np.any(np.isnan([x, y])):
      return None
      
    url = "{}?lat={}&lon={}&appid={}".format(
      self.config.G_OPENWEATHERMAP_API["URL"],
      y,
      x,
      self.config.G_OPENWEATHERMAP_API["TOKEN"],
    )
    #print(url)
    response = await self.config.network.get_json(url)
    #print(response)
    return response

  async def get_ridewithgps_route(self, add=False, reset=False):

    if not self.config.detect_network() or self.config.G_RIDEWITHGPS_API["APIKEY"] == "" or self.config.G_RIDEWITHGPS_API["TOKEN"] == "":
      return None
    
    if reset:
      self.config.G_RIDEWITHGPS_API["USER_ROUTES_START"] = 0

    #get user id
    if self.config.G_RIDEWITHGPS_API["USER_ID"] == "":
      response = await self.config.network.get_json(
        self.config.G_RIDEWITHGPS_API["URL_USER_DETAIL"], 
        params=self.config.G_RIDEWITHGPS_API["PARAMS"]
      )
      user = response.get("user")
      if user != None:
        self.config.G_RIDEWITHGPS_API["USER_ID"] = user.get("id")
      if self.config.G_RIDEWITHGPS_API["USER_ID"] == None:
        return
    
    #get user route (total_num)
    if self.config.G_RIDEWITHGPS_API["USER_ROUTES_NUM"] == None:
      response = await self.config.network.get_json(
        self.config.G_RIDEWITHGPS_API["URL_USER_ROUTES"].format(
          user = self.config.G_RIDEWITHGPS_API["USER_ID"],
          offset = 0,
          limit = 0
        ), 
        params=self.config.G_RIDEWITHGPS_API["PARAMS"]
      )
      self.config.G_RIDEWITHGPS_API["USER_ROUTES_NUM"] = response["results_count"]

    #set offset(start) and limit(end)
    if add:
      if self.config.G_RIDEWITHGPS_API["USER_ROUTES_START"] == self.config.G_RIDEWITHGPS_API["USER_ROUTES_NUM"]:
        return None
      self.config.G_RIDEWITHGPS_API["USER_ROUTES_START"] += self.config.G_RIDEWITHGPS_API["USER_ROUTES_OFFSET"]
    offset = self.config.G_RIDEWITHGPS_API["USER_ROUTES_NUM"] - self.config.G_RIDEWITHGPS_API["USER_ROUTES_START"]  - self.config.G_RIDEWITHGPS_API["USER_ROUTES_OFFSET"]
    limit = self.config.G_RIDEWITHGPS_API["USER_ROUTES_OFFSET"]
    if offset < 0:
      limit = offset + limit
      offset = 0
      self.config.G_RIDEWITHGPS_API["USER_ROUTES_START"] = self.config.G_RIDEWITHGPS_API["USER_ROUTES_NUM"]

    #get user route
    response = await self.config.network.get_json(
      self.config.G_RIDEWITHGPS_API["URL_USER_ROUTES"].format(
        user = self.config.G_RIDEWITHGPS_API["USER_ID"],
        offset = offset,
        limit = limit
      ), 
      params=self.config.G_RIDEWITHGPS_API["PARAMS"]
    )
    results = response.get("results")

    return results

  async def get_ridewithgps_files(self, route_id):
    urls = [
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_BASE_URL"]+".json").format(route_id=route_id),
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_BASE_URL"]+"/hover_preview.png").format(route_id=route_id),
      #(self.config.G_RIDEWITHGPS_API["URL_ROUTE_BASE_URL"]+"/thumb.png").format(route_id=route_id),
      #not implemented
      #https://ridewithgps.com/routes/full/{route_id}.png
      #https://ridewithgps.com/routes/{route_id}/hover_preview@2x.png
    ]
    save_paths = [
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]+"course-{route_id}.json").format(route_id=route_id),
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]+"preview-{route_id}.png").format(route_id=route_id),
      #(self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]+"thumb-{route_id}.png").format(route_id=route_id),
    ]
    await self.config.network.download_queue.put({'urls':urls, 'save_paths':save_paths, 'params':self.config.G_RIDEWITHGPS_API["PARAMS"]})
    return True
  
  async def get_ridewithgps_files_with_privacy_code(self, route_id, privacy_code):
    urls = [
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_BASE_URL"]+"/elevation_profile.jpg?privacy_code={privacy_code}").format(route_id=route_id, privacy_code=privacy_code),
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_BASE_URL"]+".tcx?privacy_code={privacy_code}").format(route_id=route_id, privacy_code=privacy_code),
    ]
    save_paths = [
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]+"elevation_profile-{route_id}.jpg").format(route_id=route_id),
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]+"course-{route_id}.tcx").format(route_id=route_id),
    ]
    await self.config.network.download_queue.put({'urls':urls, 'save_paths':save_paths, 'params':self.config.G_RIDEWITHGPS_API["PARAMS"]})
    return True

  def check_ridewithgps_files(self, route_id, mode):

    save_paths = [
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]+"course-{route_id}.json").format(route_id=route_id),
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]+"preview-{route_id}.png").format(route_id=route_id),
      #with privacy_code
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]+"elevation_profile-{route_id}.jpg").format(route_id=route_id),
      (self.config.G_RIDEWITHGPS_API["URL_ROUTE_DOWNLOAD_DIR"]+"course-{route_id}.tcx").format(route_id=route_id),
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
    #network check
    if not self.config.detect_network():
      print("No Internet connection")
      return False

    #blank check
    for b in blank_check:
      if b == "":
        print(blank_msg)
        return False
    
    #file check
    if file_check and not os.path.exists(self.config.G_UPLOAD_FILE):
      print("file does not exist")
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

    #reflesh access token
    data = {
      "client_id": self.config.G_STRAVA_API["CLIENT_ID"],
      "client_secret": self.config.G_STRAVA_API["CLIENT_SECRET"],
      "code": self.config.G_STRAVA_API["CODE"],
      "grant_type": "refresh_token",
      "refresh_token": self.config.G_STRAVA_API["REFRESH_TOKEN"],
    }
    tokens = await self.config.network.post(
      self.config.G_STRAVA_API_URL["OAUTH"], 
      data=data
    )

    if 'access_token' in tokens and 'refresh_token' in tokens and \
      tokens['access_token'] != self.config.G_STRAVA_API["ACCESS_TOKEN"]:
      #print("update strava tokens")
      self.config.G_STRAVA_API["ACCESS_TOKEN"] = tokens['access_token']
      self.config.G_STRAVA_API["REFRESH_TOKEN"] = tokens['refresh_token']
    elif 'message' in tokens and tokens['message'].find('Error') > 0:
      print("error occurs at refreshing tokens")
      return False
  
    #upload activity
    headers = {"Authorization": "Bearer " + self.config.G_STRAVA_API["ACCESS_TOKEN"]}
    data = {"data_type": "fit"}
    async with aiofiles.open(self.config.G_UPLOAD_FILE, "rb") as file:
      data["file"] = open(self.config.G_UPLOAD_FILE, 'rb')
      upload_result = await self.config.network.post(
        self.config.G_STRAVA_API_URL["UPLOAD"], 
        headers=headers,
        data=data
      )
      if 'status' in upload_result:
        print(upload_result['status'])
    
    return True

  async def garmin_upload(self):
    return await asyncio.get_running_loop().run_in_executor(None, self.garmin_upload_internal)

  def garmin_upload_internal(self):
    blank_check = [
      self.config.G_GARMINCONNECT_API["EMAIL"],
      self.config.G_GARMINCONNECT_API["PASSWORD"],
    ]
    blank_msg = "set EMAIL or PASSWORD of Garmin Connect"
    if not self.upload_check(blank_check, blank_msg):
      return False

    #import check
    if not _IMPORT_GARMINCONNECT:
      print("Install garminconnect")
      return False

    try:
      saved_session = self.config.setting.get_config_pickle("garmin_session", None)
      garmin_api = Garmin(session_data=saved_session)
      garmin_api.login()
    except (FileNotFoundError, GarminConnectAuthenticationError):
      try:
        garmin_api = Garmin(self.config.G_GARMINCONNECT_API["EMAIL"], self.config.G_GARMINCONNECT_API["PASSWORD"])
        garmin_api.login()
        self.config.set_config_pickle("garmin_session", garmin_api.session_data, quick_apply=True)
      except (
        GarminConnectConnectionError,
        GarminConnectAuthenticationError,
        GarminConnectTooManyRequestsError
      ) as err:
        print(err)
        return False
      else:
        traceback.print_exc()
        return False

    end_status = False

    for i in range(3):
      try:
        garmin_api.upload_fit_activity(self.config.G_UPLOAD_FILE)
        end_status = True
        break
      except (
          GarminConnectConnectionError,
          GarminConnectAuthenticationError,
          GarminConnectTooManyRequestsError,
      ) as err:
        print(err)
      else:
        traceback.print_exc()
      time.sleep(1.0)
    
    return end_status
  
  async def rwgps_upload(self):
    blank_check = [
      self.config.G_RIDEWITHGPS_API["APIKEY"],
      self.config.G_RIDEWITHGPS_API["TOKEN"]
    ]
    blank_msg = "set APIKEY or TOKEN of RWGPS"
    if not self.upload_check(blank_check, blank_msg):
      return False

    params = {
      "apikey": self.config.G_RIDEWITHGPS_API["APIKEY"],
      "version": "2",
      "auth_token": self.config.G_RIDEWITHGPS_API["TOKEN"],
    }

    async with aiofiles.open(self.config.G_UPLOAD_FILE, 'rb') as file:
      response = await self.config.network.post(
        self.config.G_RIDEWITHGPS_API["URL_UPLOAD"], 
        params=params,
        data={"file": file}
      )
      if response["success"] != 1:
        return False

    return True

  async def get_scw_list(self, wind_config, mode=None):
    #network check
    if not self.config.detect_network():
      print("No Internet connection")
      return None

    url = None
    if mode == 'inittime':
      url = wind_config['inittime'].format(rand=random.random())
    elif mode == 'fl':
      url = wind_config['fl'].format(basetime=wind_config['basetime'], rand=random.random())

    try:
      response = await self.config.network.get_json(
        url, 
        headers={'referer': wind_config['referer']}
      )
    except:
      response = None
    return response

  def get_strava_cookie(self):
    blank_check = [
      self.config.G_STRAVA_COOKIE["EMAIL"],
      self.config.G_STRAVA_COOKIE["PASSWORD"],
    ]
    blank_msg = "set EMAIL or PASSWORD of STRAVA"
    if not self.upload_check(blank_check, blank_msg, file_check=False):
      return False

    #import check
    if not _IMPORT_STRAVA_COOKIE:
      print("Install stravacookies")
      return
    
    if not self.config.detect_network():
      return None

    strava_cookie = StravaCookieFetcher()
    try:
      strava_cookie.fetchCookies(self.config.G_STRAVA_COOKIE["EMAIL"], self.config.G_STRAVA_COOKIE["PASSWORD"])
      self.config.G_STRAVA_COOKIE["KEY_PAIR_ID"] = strava_cookie.keyPairId
      self.config.G_STRAVA_COOKIE["POLICY"] = strava_cookie.policy
      self.config.G_STRAVA_COOKIE["SIGNATURE"] = strava_cookie.signature
    except:
      traceback.print_exc()
      