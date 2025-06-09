import oyaml as yaml

class MenuConfig:
    def __init__(self, menus_file):
        self.menus_file = menus_file
        self.keys = {
            "MENU": ["MENUS"],
            "SENSORS": ["MENUS", "SENSORS"],
            "WHEEL_SIZE": ["MENUS", "SENSORS", "WHEEL_SIZE"],
            "ADJUST_ALTITUDE": ["MENUS", "SENSORS", "ADJUST_ALTITUDE"],
            "AUTO_STOP": ["MENUS", "SENSORS", "AUTO_STOP"],
            "AUTO_LIGHT": ["MENUS", "SENSORS", "AUTO_LIGHT"],
            "GROSS_AVG_SPEED": ["MENUS", "SENSORS", "GROSS_AVG_SPEED"],
            "ANT_PLUS_SENSORS": ["MENUS", "SENSORS", "ANT_PLUS_SENSORS"],
            "ANT_PLUS_DETAIL": ["MENUS", "SENSORS", "ANT_PLUS_DETAIL"],
            # special naming to match the ANT+ sensor names in Config.G_ANT.ORDER
            "HR": ["MENUS", "SENSORS", "ANT_PLUS_SENSORS", "HEART_RATE"],
            "SPD": ["MENUS", "SENSORS", "ANT_PLUS_SENSORS", "SPEED"],
            "PWR": ["MENUS", "SENSORS", "ANT_PLUS_SENSORS", "POWER"],
            "CDC": ["MENUS", "SENSORS", "ANT_PLUS_SENSORS", "CADENCE"],
            "LGT": ["MENUS", "SENSORS", "ANT_PLUS_SENSORS", "LIGHT"],
            "CTRL": ["MENUS", "SENSORS", "ANT_PLUS_SENSORS", "CONTROL"],
            "TEMP": ["MENUS", "SENSORS", "ANT_PLUS_SENSORS", "TEMPERATURE"],
            "MAP_AND_DATA": ["MENUS", "MAP_AND_DATA"],
            "MAP_OVERLAY": ["MENUS", "MAP_AND_DATA", "MAP_OVERLAY"],
            "WIND_MAP": ["MENUS", "MAP_AND_DATA", "MAP_OVERLAY", "WIND_MAP"],
            "WIND_MAP_LIST": ["MENUS", "MAP_AND_DATA", "MAP_OVERLAY", "WIND_MAP_LIST"],
            "RAIN_MAP": ["MENUS", "MAP_AND_DATA", "MAP_OVERLAY", "RAIN_MAP"],
            "RAIN_MAP_LIST": ["MENUS", "MAP_AND_DATA", "MAP_OVERLAY", "RAIN_MAP_LIST"],
            "HEATMAP": ["MENUS", "MAP_AND_DATA", "MAP_OVERLAY", "HEATMAP"],
            "HEATMAP_LIST": ["MENUS", "MAP_AND_DATA", "MAP_OVERLAY", "HEATMAP_LIST"],
            "SELECT_MAP": ["MENUS", "MAP_AND_DATA", "SELECT_MAP"],
            "EXTERNAL_DATA_SOURCES": ["MENUS", "MAP_AND_DATA", "EXTERNAL_DATA_SOURCES"],
            "DEM_TILE": ["MENUS", "MAP_AND_DATA", "EXTERNAL_DATA_SOURCES", "DEM_TILE"],
            "DEM_TILE_SOURCE": ["MENUS", "MAP_AND_DATA", "EXTERNAL_DATA_SOURCES", "DEM_TILE_SOURCE"],
            "WIND": ["MENUS", "MAP_AND_DATA", "EXTERNAL_DATA_SOURCES", "WIND"],
            "WIND_SOURCE": ["MENUS", "MAP_AND_DATA", "EXTERNAL_DATA_SOURCES", "WIND_SOURCE"],
            "COURSES": ["MENUS", "COURSES"],
            "COURSE_DETAIL": ["MENUS", "COURSES", "COURSE_DETAIL"],
            "COURSES_LIST": ["MENUS", "COURSES", "COURSES_LIST"],
            "COURSE_CALCULATION": ["MENUS", "COURSES", "COURSE_CALCULATION"],
            "COURSE_CANCEL": ["MENUS", "COURSES", "COURSE_CANCEL"],
            "COURSE_EMPTY": ["MENUS", "COURSES", "EMPTY"],
            "LOCAL_STORAGE": ["MENUS", "COURSES", "LOCAL_STORAGE"],
            "RIDE_WITH_GPS": ["MENUS", "COURSES", "RIDE_WITH_GPS"],
            "ANDROID_GOOGLE_MAPS": ["MENUS", "COURSES", "ANDROID_GOOGLE_MAPS"],
            "PROFILE": ["MENUS", "PROFILE"],
            "CP": ["MENUS", "PROFILE", "CP"],
            "W_PRIME_BALANCE": ["MENUS", "PROFILE", "W_PRIME_BALANCE"],
            "CONNECTIVITY": ["MENUS", "CONNECTIVITY"],
            "AUTO_BT_TETHERING": ["MENUS", "CONNECTIVITY", "BT_TETHERING"],
            "SELECT_BT_DEVICE": ["MENUS", "CONNECTIVITY", "SELECT_BT_DEVICE"],
            "LIVE_TRACKING": ["MENUS", "CONNECTIVITY", "LIVE_TRACKING"],
            "GADGET_BRIDGE": ["MENUS", "CONNECTIVITY", "GADGET_BRIDGE"],
            "GET_LOCATION": ["MENUS", "CONNECTIVITY", "GET_LOCATION"],
            "CONNECTIVITY_EMPTY": ["MENUS", "CONNECTIVITY", "EMPTY"],
            "SYSTEM": ["MENUS", "SYSTEM"],
            "NETWORK": ["MENUS", "SYSTEM", "NETWORK"],
            "WIFI_NETWORK": ["MENUS", "SYSTEM", "NETWORK", "WIFI"],
            "BLUETOOTH_NETWORK": ["MENUS", "SYSTEM", "NETWORK", "BLUETOOTH"],
            "BT_TETHERING_NETWORK": ["MENUS", "SYSTEM", "NETWORK", "BT_TETHERING"],
            "IP_ADDRESS_NETWORK": ["MENUS", "SYSTEM", "NETWORK", "IP_ADDRESS"],
            "BRIGHTNESS": ["MENUS", "SYSTEM", "BRIGHTNESS"],
            "POWER_OFF": ["MENUS", "SYSTEM", "POWER_OFF"],
            "LANGUAGE": ["MENUS", "SYSTEM", "LANGUAGE"],
            "UPDATE": ["MENUS", "SYSTEM", "UPDATE"],
            "DEBUG": ["MENUS", "SYSTEM", "DEBUG"],
            "DEBUG_LOG_LEVEL": ["MENUS", "SYSTEM", "DEBUG", "DEBUG_LOG_LEVEL"],
            "DISABLE_ENABLE_WIFI_BT": ["MENUS", "SYSTEM", "DEBUG", "DISABLE_ENABLE_WIFI_BT"],
            "RESTART": ["MENUS", "SYSTEM", "DEBUG", "RESTART"],
            "REBOOT": ["MENUS", "SYSTEM", "DEBUG", "REBOOT"],
            "DEBUG_LOG": ["MENUS", "SYSTEM", "DEBUG", "DEBUG_LOG"],
            "UPLOAD_ACTIVITY": ["MENUS", "UPLOAD_ACTIVITY"],
            "RIDE_WITH_GPS_UPLOAD": ["MENUS", "UPLOAD_ACTIVITY", "RIDE_WITH_GPS"],
            "GARMIN_CONNECT_UPLOAD": ["MENUS", "UPLOAD_ACTIVITY", "GARMIN_CONNECT"],
            "STRAVA_UPLOAD": ["MENUS", "UPLOAD_ACTIVITY", "STRAVA"],
        }


        # Load menus yaml file to determine which menus are displayed in the TopMenu
        # This can be used to simplify/complicate the available settings for the user.
        try:
            with open(self.menus_file) as file:
                text = file.read()
                self.menu_config = yaml.safe_load(text)
        except FileNotFoundError:
            pass

    def write_menus_yaml(self):
        with open(self.menus_file, "w") as file:
            yaml.safe_dump(self.menu_config, file, sort_keys=False)

    def get_path(self, name):
        return self.keys.get(name)

    def list_keys(self):
        return list(self.keys)

    def wrap_menus(self):
        return self.menu_config["WRAP_MENU_LAYOUT"]

    def menu_button_font_size(self):
        return self.menu_config["MENU_BUTTON_FONT_SIZE"]

    # Get the status of a menu item, including its parents.
    # That is, if a parent status is false, the child is also false
    def get_status(self, key):
        path = self.get_path(key)
        return self.get_status_for_path(path)

    # Get the status of a menu item path, including its parents.
    # That is, if a parent status is false, the child is also false
    def get_status_for_path(self, key_path):
        if key_path[0] not in self.menu_config:
            print(f"** Invalid key path: {key_path}")
            raise Exception
        # this is the first key in the path so start there by default
        current = self.menu_config[key_path[0]]
        for key in key_path[1:]:
            if "STATUS" in current and current["STATUS"] is not True:
                return False
            if "STATUS" in current and current["STATUS"] is not True and key not in current.get("SUB_MENUS", {}):
                return False
            if "SUB_MENUS" in current and key in current["SUB_MENUS"]:
                current = current["SUB_MENUS"][key]
            else:
                # create the missing key in the current level and set it to True (visible)
                if "SUB_MENUS" not in current:
                    current["SUB_MENUS"] = {}
                if key not in current["SUB_MENUS"]:
                    # Add the missing key with default structure
                    current["SUB_MENUS"][key] = {
                        "STATUS": True
                    }
                current = current["SUB_MENUS"][key]

        return current.get("STATUS", False)
