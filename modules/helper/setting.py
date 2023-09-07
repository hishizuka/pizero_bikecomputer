import configparser
import pickle
import json
import os
import struct
import datetime

import numpy as np


class Setting:
    config = None
    config_parser = None

    # config file (store user specified values. readable and editable.)
    config_file = "setting.conf"

    # config file (store temporary values. unreadable and uneditable.)
    config_pickle_file = "setting.pickle"
    config_pickle = {}
    config_pickle_write_time = datetime.datetime.utcnow()
    config_pickle_interval = 10  # [s]

    def __init__(self, config):
        self.config = config
        self.config_parser = configparser.ConfigParser()

    def read(self):
        if os.path.exists(self.config_file):
            self.read_config()
        if os.path.exists(self.config_pickle_file):
            self.read_config_pickle()

    def read_config(self):
        self.config_parser.read(self.config_file)

        if "GENERAL" in self.config_parser:
            if "AUTOSTOP_CUTOFF" in self.config_parser["GENERAL"]:
                self.config.G_AUTOSTOP_CUTOFF = (
                    int(self.config_parser["GENERAL"]["AUTOSTOP_CUTOFF"]) / 3.6
                )
                self.config.G_GPS_SPEED_CUTOFF = self.config.G_AUTOSTOP_CUTOFF
            if "WHEEL_CIRCUMFERENCE" in self.config_parser["GENERAL"]:
                self.config.G_WHEEL_CIRCUMFERENCE = (
                    int(self.config_parser["GENERAL"]["WHEEL_CIRCUMFERENCE"]) / 1000
                )
            if "GROSS_AVE_SPEED" in self.config_parser["GENERAL"]:
                self.config.G_GROSS_AVE_SPEED = int(
                    self.config_parser["GENERAL"]["GROSS_AVE_SPEED"]
                )
            if "DISPLAY" in self.config_parser["GENERAL"]:
                self.config.G_DISPLAY = self.config_parser["GENERAL"][
                    "DISPLAY"
                ]  # store temporary
            if "AUTO_BACKLIGHT_CUTOFF" in self.config_parser["GENERAL"]:
                self.config.G_AUTO_BACKLIGHT_CUTOFF = int(
                    self.config_parser["GENERAL"]["AUTO_BACKLIGHT_CUTOFF"]
                )  # store temporary
            if "LANG" in self.config_parser["GENERAL"]:
                self.config.G_LANG = self.config_parser["GENERAL"]["LANG"].upper()
            if "FONT_FILE" in self.config_parser["GENERAL"]:
                self.config.G_FONT_FILE = self.config_parser["GENERAL"]["FONT_FILE"]
            if "MAP" in self.config_parser["GENERAL"]:
                self.config.G_MAP = self.config_parser["GENERAL"]["MAP"].lower()

        if "POWER" in self.config_parser:
            if "CP" in self.config_parser["POWER"]:
                self.config.G_POWER_CP = int(self.config_parser["POWER"]["CP"])
            if "W_PRIME" in self.config_parser["POWER"]:
                self.config.G_POWER_W_PRIME = int(
                    self.config_parser["POWER"]["W_PRIME"]
                )

        if "ANT" in self.config_parser:
            for key in self.config_parser["ANT"]:
                if key.upper() == "STATUS":
                    self.config.G_ANT["STATUS"] = self.config_parser["ANT"].getboolean(
                        key
                    )
                    continue
                i = key.rfind("_")

                if i < 0:
                    continue

                key1 = key[0:i]
                key2 = key[i + 1 :]
                try:
                    k1 = key1.upper()
                    k2 = key2.upper()
                except:
                    continue
                if (
                    k1 == "USE" and k2 in self.config.G_ANT["ID"].keys()
                ):  # ['HR','SPD','CDC','PWR']:
                    try:
                        self.config.G_ANT[k1][k2] = self.config_parser[
                            "ANT"
                        ].getboolean(key)
                    except:
                        pass
                elif (
                    k1 in ["ID", "TYPE"] and k2 in self.config.G_ANT["ID"].keys()
                ):  # ['HR','SPD','CDC','PWR']:
                    try:
                        self.config.G_ANT[k1][k2] = self.config_parser["ANT"].getint(
                            key
                        )
                    except:
                        pass
            for key in self.config.G_ANT["ID"].keys():  # ['HR','SPD','CDC','PWR']:
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
            if "SPI_CLOCK" in self.config_parser["DISPLAY_PARAM"]:
                self.config.G_DISPLAY_PARAM["SPI_CLOCK"] = int(
                    self.config_parser["DISPLAY_PARAM"]["SPI_CLOCK"]
                )

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
            "OPENWEATHERMAP",
            "RIDEWITHGPS",
            "THINGSBOARD",
        ):
            token_str = token + "_API"
            config = eval("self.config.G_" + token + "_API")
            if token_str in self.config_parser:
                for k in config.keys():
                    if k in self.config_parser[token_str]:
                        config[k] = self.config_parser[token_str][k]
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
        self.config_parser["GENERAL"]["DISPLAY"] = self.config.G_DISPLAY
        self.config_parser["GENERAL"]["AUTOSTOP_CUTOFF"] = str(
            int(self.config.G_AUTOSTOP_CUTOFF * 3.6)
        )
        self.config_parser["GENERAL"]["WHEEL_CIRCUMFERENCE"] = str(
            int(self.config.G_WHEEL_CIRCUMFERENCE * 1000)
        )
        self.config_parser["GENERAL"]["GROSS_AVE_SPEED"] = str(
            int(self.config.G_GROSS_AVE_SPEED)
        )
        self.config_parser["GENERAL"]["AUTO_BACKLIGHT_CUTOFF"] = str(
            int(self.config.G_AUTO_BACKLIGHT_CUTOFF)
        )
        self.config_parser["GENERAL"]["LANG"] = self.config.G_LANG
        self.config_parser["GENERAL"]["FONT_FILE"] = self.config.G_FONT_FILE
        self.config_parser["GENERAL"]["MAP"] = self.config.G_MAP

        self.config_parser["POWER"] = {}
        self.config_parser["POWER"]["CP"] = str(int(self.config.G_POWER_CP))
        self.config_parser["POWER"]["W_PRIME"] = str(int(self.config.G_POWER_W_PRIME))

        if not self.config.G_DUMMY_OUTPUT:
            self.config_parser["ANT"] = {}
            self.config_parser["ANT"]["STATUS"] = str(self.config.G_ANT["STATUS"])
            for key1 in ["USE", "ID", "TYPE"]:
                for key2 in self.config.G_ANT[key1]:
                    if (
                        key2 in self.config.G_ANT["ID"].keys()
                    ):  # ['HR','SPD','CDC','PWR']:
                        self.config_parser["ANT"][key1 + "_" + key2] = str(
                            self.config.G_ANT[key1][key2]
                        )

        self.config_parser["SENSOR_IMU"] = {}
        self.config_parser["SENSOR_IMU"]["AXIS_SWAP_XY_STATUS"] = str(
            self.config.G_IMU_AXIS_SWAP_XY["STATUS"]
        )
        self.config_parser["SENSOR_IMU"]["AXIS_CONVERSION_STATUS"] = str(
            self.config.G_IMU_AXIS_CONVERSION["STATUS"]
        )
        self.config_parser["SENSOR_IMU"]["AXIS_CONVERSION_COEF"] = str(
            list(self.config.G_IMU_AXIS_CONVERSION["COEF"])
        )
        self.config_parser["SENSOR_IMU"]["MAG_AXIS_SWAP_XY_STATUS"] = str(
            self.config.G_IMU_MAG_AXIS_SWAP_XY["STATUS"]
        )
        self.config_parser["SENSOR_IMU"]["MAG_AXIS_CONVERSION_STATUS"] = str(
            self.config.G_IMU_MAG_AXIS_CONVERSION["STATUS"]
        )
        self.config_parser["SENSOR_IMU"]["MAG_AXIS_CONVERSION_COEF"] = str(
            list(self.config.G_IMU_MAG_AXIS_CONVERSION["COEF"])
        )
        self.config_parser["SENSOR_IMU"]["MAG_DECLINATION"] = str(
            int(self.config.G_IMU_MAG_DECLINATION)
        )

        self.config_parser["DISPLAY_PARAM"] = {}
        self.config_parser["DISPLAY_PARAM"]["SPI_CLOCK"] = str(
            int(self.config.G_DISPLAY_PARAM["SPI_CLOCK"])
        )

        self.config_parser["GPSD_PARAM"] = {}
        self.config_parser["GPSD_PARAM"]["EPX_EPY_CUTOFF"] = str(
            self.config.G_GPSD_PARAM["EPX_EPY_CUTOFF"]
        )
        self.config_parser["GPSD_PARAM"]["EPV_CUTOFF"] = str(
            self.config.G_GPSD_PARAM["EPV_CUTOFF"]
        )
        self.config_parser["GPSD_PARAM"]["SP1_EPV_CUTOFF"] = str(
            self.config.G_GPSD_PARAM["SP1_EPV_CUTOFF"]
        )
        self.config_parser["GPSD_PARAM"]["SP1_USED_SATS_CUTOFF"] = str(
            self.config.G_GPSD_PARAM["SP1_USED_SATS_CUTOFF"]
        )

        self.config_parser["STRAVA_API"] = {}
        for k in self.config.G_STRAVA_API.keys():
            self.config_parser["STRAVA_API"][k] = self.config.G_STRAVA_API[k]

        self.config_parser["STRAVA_COOKIE"] = {}
        for k in self.config.G_STRAVA_COOKIE.keys():
            self.config_parser["STRAVA_COOKIE"][k] = self.config.G_STRAVA_COOKIE[k]

        for token in (
            "GOOGLE_DIRECTION",
            "OPENWEATHERMAP",
            "RIDEWITHGPS",
            "THINGSBOARD",
        ):
            token_str = token + "_API"
            config = eval("self.config.G_" + token + "_API")
            self.config_parser[token_str] = {}
            self.config_parser[token_str]["TOKEN"] = config["TOKEN"]
            if token == "RIDEWITHGPS":
                self.config_parser[token_str]["APIKEY"] = config["APIKEY"]

        self.config_parser["GARMINCONNECT_API"] = {}
        for k in ["EMAIL", "PASSWORD"]:
            self.config_parser["GARMINCONNECT_API"][
                k
            ] = self.config.G_GARMINCONNECT_API[k]

        with open(self.config_file, "w") as file:
            self.config_parser.write(file)

    def read_config_pickle(self):
        with open(self.config_pickle_file, "rb") as f:
            self.config_pickle = pickle.load(f)

    def set_config_pickle(self, key, value, quick_apply=False):
        self.config_pickle[key] = value
        # write with config_pickle_interval
        t = (datetime.datetime.utcnow() - self.config_pickle_write_time).total_seconds()
        if not quick_apply and t < self.config_pickle_interval:
            return
        with open(self.config_pickle_file, "wb") as f:
            pickle.dump(self.config_pickle, f)
        self.config_pickle_write_time = datetime.datetime.utcnow()

    def get_config_pickle(self, key, default_value):
        if key in self.config_pickle:
            return self.config_pickle[key]
        else:
            return default_value

    # reset
    def reset_config_pickle(self):
        for k, v in list(self.config_pickle.items()):
            if "mag" in k:
                continue
            del self.config_pickle[k]
        with open(self.config_pickle_file, "wb") as f:
            pickle.dump(self.config_pickle, f)

    # quit
    def delete_config_pickle(self):
        for k, v in list(self.config_pickle.items()):
            if "ant+" in k:
                del self.config_pickle[k]
        with open(self.config_pickle_file, "wb") as f:
            pickle.dump(self.config_pickle, f)
