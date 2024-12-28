import configparser
import json
import os
import struct

import numpy as np


class Setting:
    config = None
    config_parser = None

    # config file (store user specified values. readable and editable.)
    config_file = "setting.conf"

    def __init__(self, config):
        self.config = config
        self.config_parser = configparser.ConfigParser()

        if os.path.exists(self.config_file):
            self.read()

    def read(self):
        self.config_parser.read(self.config_file)

        if "GENERAL" in self.config_parser:
            c = self.config_parser["GENERAL"]
            if "AUTOSTOP_CUTOFF" in c:
                self.config.G_AUTOSTOP_CUTOFF = (int(c["AUTOSTOP_CUTOFF"]) / 3.6)
                self.config.G_GPS_SPEED_CUTOFF = self.config.G_AUTOSTOP_CUTOFF
            if "WHEEL_CIRCUMFERENCE" in c:
                self.config.G_WHEEL_CIRCUMFERENCE = (
                    int(c["WHEEL_CIRCUMFERENCE"]) / 1000
                )
            if "GROSS_AVE_SPEED" in c:
                self.config.G_GROSS_AVE_SPEED = int(c["GROSS_AVE_SPEED"])
            if "DISPLAY" in c:
                # store temporary
                self.config.G_DISPLAY = c["DISPLAY"]
            if "LANG" in c:
                self.config.G_LANG = c["LANG"].upper()
            if "FONT_FILE" in c:
                self.config.G_FONT_FILE = c["FONT_FILE"]

        if "BT" in self.config_parser:
            c = self.config_parser["BT"]
            if "BT_PAN_DEVICE" in c:
                self.config.G_BT_PAN_DEVICE = c["BT_PAN_DEVICE"]
            if "AUTO_BT_TETHERING" in c:
                self.config.G_AUTO_BT_TETHERING = c.getboolean("AUTO_BT_TETHERING")
            if "GADGETBRIDGE_STATUS" in c:
                self.config.G_GADGETBRIDGE["STATUS"] = c.getboolean("GADGETBRIDGE_STATUS")
            if "GADGETBRIDGE_USE_GPS" in c:
                self.config.G_GADGETBRIDGE["USE_GPS"] = c.getboolean("GADGETBRIDGE_USE_GPS")

        if "MAP_AND_DATA" in self.config_parser:
            c = self.config_parser["MAP_AND_DATA"]
            if "MAP" in c:
                self.config.G_MAP = c["MAP"]
            if "USE_HEATMAP_OVERLAY_MAP" in c:
                self.config.G_USE_HEATMAP_OVERLAY_MAP = c.getboolean("USE_HEATMAP_OVERLAY_MAP")
            if "HEATMAP_OVERLAY_MAP" in c:
                self.config.G_HEATMAP_OVERLAY_MAP = c["HEATMAP_OVERLAY_MAP"]
            if "USE_RAIN_OVERLAY_MAP" in c:
                self.config.G_USE_RAIN_OVERLAY_MAP = c.getboolean("USE_RAIN_OVERLAY_MAP")
            if "RAIN_OVERLAY_MAP" in c:
                self.config.G_RAIN_OVERLAY_MAP = c["RAIN_OVERLAY_MAP"]
            if "USE_WIND_OVERLAY_MAP" in c:
                self.config.G_USE_WIND_OVERLAY_MAP = c.getboolean("USE_WIND_OVERLAY_MAP")
            if "WIND_OVERLAY_MAP" in c:
                self.config.G_WIND_OVERLAY_MAP = c["WIND_OVERLAY_MAP"]
            if "USE_WIND_DATA_SOURCE" in c:
                self.config.G_USE_WIND_DATA_SOURCE = c.getboolean("USE_WIND_DATA_SOURCE")
            if "WIND_DATA_SOURCE" in c:
                self.config.G_WIND_DATA_SOURCE = c["WIND_DATA_SOURCE"]
            if "USE_DEM_TILE" in c:
                self.config.G_USE_DEM_TILE = c.getboolean("USE_DEM_TILE")
            if "DEM_MAP" in c:
                self.config.G_DEM_MAP = c["DEM_MAP"]

        if "POWER" in self.config_parser:
            if "CP" in self.config_parser["POWER"]:
                self.config.G_POWER_CP = int(self.config_parser["POWER"]["CP"])
            if "W_PRIME" in self.config_parser["POWER"]:
                self.config.G_POWER_W_PRIME = int(
                    self.config_parser["POWER"]["W_PRIME"]
                )

        if "ANT" in self.config_parser:
            c = self.config_parser["ANT"]
            for key in c:
                if key.upper() in ["STATUS", "USE_AUTO_LIGHT"]:
                    self.config.G_ANT[key.upper()] = c.getboolean(key)
                    continue

                i = key.rfind("_")
                if i < 0:
                    continue

                k1 = key[0:i].upper()
                k2 = key[i + 1:].upper()
                if k2 in self.config.G_ANT["ID"].keys():
                    if k1 == "USE":
                        self.config.G_ANT[k1][k2] = c.getboolean(key)
                    elif k1 in ["ID", "TYPE"]:
                        self.config.G_ANT[k1][k2] = c.getint(key)

            for key in self.config.G_ANT["ID"].keys():
                if (
                    not (0 <= self.config.G_ANT["ID"][key] <= 0xFFFF)
                    or not self.config.G_ANT["TYPE"][key]
                    in self.config.G_ANT["TYPES"][key]
                ):
                    self.config.G_ANT["USE"][key] = False
                    self.config.G_ANT["ID"][key] = 0
                    self.config.G_ANT["TYPE"][key] = 0
                if (
                    self.config.G_ANT["ID"][key] != 0
                    and self.config.G_ANT["TYPE"][key] != 0
                ):
                    self.config.G_ANT["ID_TYPE"][key] = struct.pack(
                        "<HB",
                        self.config.G_ANT["ID"][key],
                        self.config.G_ANT["TYPE"][key],
                    )

        if "SENSOR_IMU" in self.config_parser:
            for s, c, m in [
                [
                    "AXIS_CONVERSION_STATUS",
                    "AXIS_CONVERSION_COEF",
                    self.config.G_IMU_AXIS_CONVERSION,
                ],
                ["AXIS_SWAP_XY_STATUS", "", self.config.G_IMU_AXIS_SWAP_XY],
                [
                    "MAG_AXIS_CONVERSION_STATUS",
                    "MAG_AXIS_CONVERSION_COEF",
                    self.config.G_IMU_MAG_AXIS_CONVERSION,
                ],
                ["MAG_AXIS_SWAP_XY_STATUS", "", self.config.G_IMU_MAG_AXIS_SWAP_XY],
            ]:
                if s.lower() in self.config_parser["SENSOR_IMU"]:
                    m["STATUS"] = self.config_parser["SENSOR_IMU"].getboolean(s)
                if c != "" and c.lower() in self.config_parser["SENSOR_IMU"]:
                    coef = np.array(json.loads(self.config_parser["SENSOR_IMU"][c]))
                    n = m["COEF"].shape[0]
                    if np.sum((coef == 1) | (coef == -1)) == n:
                        m["COEF"] = coef[0:n]
                if "MAG_DECLINATION" in self.config_parser["SENSOR_IMU"]:
                    self.config.G_IMU_MAG_DECLINATION = int(
                        self.config_parser["SENSOR_IMU"]["MAG_DECLINATION"]
                    )

        if "DISPLAY_PARAM" in self.config_parser:
            c = self.config_parser["DISPLAY_PARAM"]
            if "SPI_CLOCK" in c:
                self.config.G_DISPLAY_PARAM["SPI_CLOCK"] = int(c["SPI_CLOCK"])
            if "PCB_BACKLIGHT" in c:
                self.config.G_PCB_BACKLIGHT = c["PCB_BACKLIGHT"].upper()
            if "USE_BACKLIGHT" in c:
                self.config.G_DISPLAY_PARAM["USE_BACKLIGHT"] = c.getboolean("USE_BACKLIGHT")
            if "AUTO_BACKLIGHT_CUTOFF" in c:
                # store temporary
                self.config.G_AUTO_BACKLIGHT_CUTOFF = int(c["AUTO_BACKLIGHT_CUTOFF"])

        if "GPSD_PARAM" in self.config_parser:
            if "EPX_EPY_CUTOFF" in self.config_parser["GPSD_PARAM"]:
                self.config.G_GPSD_PARAM["EPX_EPY_CUTOFF"] = float(
                    self.config_parser["GPSD_PARAM"]["EPX_EPY_CUTOFF"]
                )
            if "EPV_CUTOFF" in self.config_parser["GPSD_PARAM"]:
                self.config.G_GPSD_PARAM["EPV_CUTOFF"] = float(
                    self.config_parser["GPSD_PARAM"]["EPV_CUTOFF"]
                )
            if "SP1_EPV_CUTOFF" in self.config_parser["GPSD_PARAM"]:
                self.config.G_GPSD_PARAM["SP1_EPV_CUTOFF"] = float(
                    self.config_parser["GPSD_PARAM"]["SP1_EPV_CUTOFF"]
                )
            if "SP1_USED_SATS_CUTOFF" in self.config_parser["GPSD_PARAM"]:
                self.config.G_GPSD_PARAM["SP1_USED_SATS_CUTOFF"] = int(
                    self.config_parser["GPSD_PARAM"]["SP1_USED_SATS_CUTOFF"]
                )

        if "STRAVA_API" in self.config_parser:
            for k in self.config.G_STRAVA_API.keys():
                if k in self.config_parser["STRAVA_API"]:
                    self.config.G_STRAVA_API[k] = self.config_parser["STRAVA_API"][k]

        if "STRAVA_COOKIE" in self.config_parser:
            for k in self.config.G_STRAVA_COOKIE.keys():
                if k in self.config_parser["STRAVA_COOKIE"]:
                    self.config.G_STRAVA_COOKIE[k] = self.config_parser[
                        "STRAVA_COOKIE"
                    ][k]

        for token in (
            "GOOGLE_DIRECTION",
            "RIDEWITHGPS",
            "THINGSBOARD",
        ):
            token_str = token + "_API"
            config = eval("self.config.G_" + token + "_API")
            if token_str in self.config_parser:
                for k in config.keys():
                    c = self.config_parser[token_str]
                    if k in c:
                        if k == "STATUS":
                            config[k] = c.getboolean(k)
                        else:
                            config[k] = c[k]
                if config["TOKEN"] != "":
                    config["HAVE_API_TOKEN"] = True

        if "GARMINCONNECT_API" in self.config_parser:
            for k in ["EMAIL", "PASSWORD"]:
                if k in self.config_parser["GARMINCONNECT_API"]:
                    self.config.G_GARMINCONNECT_API[k] = self.config_parser[
                        "GARMINCONNECT_API"
                    ][k]

    def write_config(self):
        self.config_parser["GENERAL"] = {}
        c = self.config_parser["GENERAL"]
        c["DISPLAY"] = self.config.G_DISPLAY
        c["AUTOSTOP_CUTOFF"] = str(int(self.config.G_AUTOSTOP_CUTOFF * 3.6))
        c["WHEEL_CIRCUMFERENCE"] = str(int(self.config.G_WHEEL_CIRCUMFERENCE * 1000))
        c["GROSS_AVE_SPEED"] = str(int(self.config.G_GROSS_AVE_SPEED))
        c["LANG"] = self.config.G_LANG
        c["FONT_FILE"] = self.config.G_FONT_FILE

        self.config_parser["BT"] = {}
        c = self.config_parser["BT"]
        c["BT_PAN_DEVICE"] = str(self.config.G_BT_PAN_DEVICE)
        c["AUTO_BT_TETHERING"] = str(self.config.G_AUTO_BT_TETHERING)
        c["GADGETBRIDGE_STATUS"] = str(self.config.G_GADGETBRIDGE["STATUS"])
        c["GADGETBRIDGE_USE_GPS"] = str(self.config.G_GADGETBRIDGE["USE_GPS"])

        self.config_parser["MAP_AND_DATA"] = {}
        c = self.config_parser["MAP_AND_DATA"]
        c["MAP"] = self.config.G_MAP
        c["USE_HEATMAP_OVERLAY_MAP"] = str(self.config.G_USE_HEATMAP_OVERLAY_MAP)
        c["HEATMAP_OVERLAY_MAP"] = self.config.G_HEATMAP_OVERLAY_MAP
        c["USE_RAIN_OVERLAY_MAP"] = str(self.config.G_USE_RAIN_OVERLAY_MAP)
        c["RAIN_OVERLAY_MAP"] = self.config.G_RAIN_OVERLAY_MAP
        c["USE_WIND_OVERLAY_MAP"] = str(self.config.G_USE_WIND_OVERLAY_MAP)
        c["WIND_OVERLAY_MAP"] = self.config.G_WIND_OVERLAY_MAP
        c["USE_WIND_DATA_SOURCE"] = str(self.config.G_USE_WIND_DATA_SOURCE)
        c["WIND_DATA_SOURCE"] = self.config.G_WIND_DATA_SOURCE
        c["USE_DEM_TILE"] = str(self.config.G_USE_DEM_TILE)
        c["DEM_MAP"] = self.config.G_DEM_MAP

        self.config_parser["POWER"] = {}
        self.config_parser["POWER"]["CP"] = str(int(self.config.G_POWER_CP))
        self.config_parser["POWER"]["W_PRIME"] = str(int(self.config.G_POWER_W_PRIME))

        if not self.config.G_DUMMY_OUTPUT:
            self.config_parser["ANT"] = {}
            c = self.config_parser["ANT"]
            c["STATUS"] = str(self.config.G_ANT["STATUS"])
            for key1 in ["USE", "ID", "TYPE"]:
                for key2 in self.config.G_ANT[key1]:
                    if (
                        key2 in self.config.G_ANT["ID"].keys()
                    ):  # ['HR','SPD','CDC','PWR']:
                        c[key1 + "_" + key2] = str(self.config.G_ANT[key1][key2])
            c["USE_AUTO_LIGHT"] = str(self.config.G_ANT["USE_AUTO_LIGHT"])

        self.config_parser["SENSOR_IMU"] = {}
        c = self.config_parser["SENSOR_IMU"]
        c["AXIS_SWAP_XY_STATUS"] = str(self.config.G_IMU_AXIS_SWAP_XY["STATUS"])
        c["AXIS_CONVERSION_STATUS"] = str(self.config.G_IMU_AXIS_CONVERSION["STATUS"])
        c["AXIS_CONVERSION_COEF"] = str(self.config.G_IMU_AXIS_CONVERSION["COEF"].tolist())
        c["MAG_AXIS_SWAP_XY_STATUS"] = str(self.config.G_IMU_MAG_AXIS_SWAP_XY["STATUS"])
        c["MAG_AXIS_CONVERSION_STATUS"] = str(self.config.G_IMU_MAG_AXIS_CONVERSION["STATUS"])
        c["MAG_AXIS_CONVERSION_COEF"] = str(self.config.G_IMU_MAG_AXIS_CONVERSION["COEF"].tolist())
        c["MAG_DECLINATION"] = str(int(self.config.G_IMU_MAG_DECLINATION))

        self.config_parser["DISPLAY_PARAM"] = {}
        c = self.config_parser["DISPLAY_PARAM"]
        c["SPI_CLOCK"] = str(int(self.config.G_DISPLAY_PARAM["SPI_CLOCK"]))
        c["PCB_BACKLIGHT"] = str(self.config.G_PCB_BACKLIGHT).lower()
        c["USE_BACKLIGHT"] = str(self.config.G_DISPLAY_PARAM["USE_BACKLIGHT"])
        c["AUTO_BACKLIGHT_CUTOFF"] = str(int(self.config.G_AUTO_BACKLIGHT_CUTOFF))

        self.config_parser["GPSD_PARAM"] = {}
        c = self.config_parser["GPSD_PARAM"]
        c["EPX_EPY_CUTOFF"] = str(self.config.G_GPSD_PARAM["EPX_EPY_CUTOFF"])
        c["EPV_CUTOFF"] = str(self.config.G_GPSD_PARAM["EPV_CUTOFF"])
        c["SP1_EPV_CUTOFF"] = str(self.config.G_GPSD_PARAM["SP1_EPV_CUTOFF"])
        c["SP1_USED_SATS_CUTOFF"] = str(self.config.G_GPSD_PARAM["SP1_USED_SATS_CUTOFF"])

        self.config_parser["STRAVA_API"] = {}
        for k in self.config.G_STRAVA_API.keys():
            self.config_parser["STRAVA_API"][k] = self.config.G_STRAVA_API[k]

        self.config_parser["STRAVA_COOKIE"] = {}
        for k in self.config.G_STRAVA_COOKIE.keys():
            self.config_parser["STRAVA_COOKIE"][k] = self.config.G_STRAVA_COOKIE[k]

        for token in (
            "GOOGLE_DIRECTION",
            "RIDEWITHGPS",
            "THINGSBOARD",
        ):
            token_str = token + "_API"
            config = eval("self.config.G_" + token + "_API")
            self.config_parser[token_str] = {}
            self.config_parser[token_str]["TOKEN"] = config["TOKEN"]
            if token == "RIDEWITHGPS":
                self.config_parser[token_str]["APIKEY"] = config["APIKEY"]
            if token == "THINGSBOARD":
                self.config_parser[token_str]["STATUS"] = str(config["STATUS"])

        self.config_parser["GARMINCONNECT_API"] = {}
        for k in ["EMAIL", "PASSWORD"]:
            self.config_parser["GARMINCONNECT_API"][
                k
            ] = self.config.G_GARMINCONNECT_API[k]

        with open(self.config_file, "w") as file:
            self.config_parser.write(file)
