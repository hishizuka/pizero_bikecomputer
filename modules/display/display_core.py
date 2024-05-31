import os

from logger import app_logger
from modules.config import Config

DEFAULT_RESOLUTION = (400, 240)

SUPPORTED_DISPLAYS = {
    # display name, resolution if different from its class default
    "None": None,  # DEFAULT_RESOLUTION
    "PiTFT": None,
    "MIP": None,  # LPM027M128C, LPM027M128B
    "MIP_640": (640, 480),  # LPM044M141A
    "MIP_Mraa": None,  # LPM027M128C, LPM027M128B
    "MIP_Mraa_640": (640, 480),  # LPM044M141A
    "MIP_Sharp": None,
    "MIP_Sharp_320": (320, 240),
    "Papirus": None,
    "DFRobot_RPi_Display": None,
    "Pirate_Audio": None,
    "Pirate_Audio_old": None,
    "Display_HAT_Mini": (320, 240),
}


# default display (X window)
class Display:
    has_auto_brightness = False
    has_color = True
    has_touch = True
    send = False

    # current auto brightness status (on/off)
    auto_brightness = False
    brightness_index = 0
    brightness_table = None

    def __init__(self, config: Config):
        self.config = config

        if self.has_auto_brightness:
            # set initial status
            self.auto_brightness = config.G_USE_AUTO_BACKLIGHT

            # set index properly if on
            if self.auto_brightness:
                self.brightness_index = len(self.brightness_table)

    @property
    def resolution(self):
        return getattr(self, "size", DEFAULT_RESOLUTION)

    def start_coroutine(self):
        pass

    def quit(self):
        pass

    def update(self, buf, direct_update):
        pass

    def screen_flash_long(self):
        pass

    def screen_flash_short(self):
        pass

    # We can not have auto brightness and an empty brightness table
    def change_brightness(self):
        if self.brightness_table:
            # brightness is changing as following if the display has auto_brightness feature
            # [*self.brightness_table, self.auto_brightness]
            if self.has_auto_brightness:
                self.brightness_index = (self.brightness_index + 1) % (
                    len(self.brightness_table) + 1
                )

                # switch on auto_brightness
                if self.brightness_index == len(self.brightness_table):
                    self.auto_brightness = True
                # switch off auto_brightness and set requested brightness
                else:
                    self.auto_brightness = False
                    self.set_brightness(self.brightness_table[self.brightness_index])
            else:
                # else we just loop over the brightness table
                self.brightness_index = (self.brightness_index + 1) % len(
                    self.brightness_table
                )
                self.set_brightness(self.brightness_table[self.brightness_index])

    def set_brightness(self, b):
        pass


def detect_display():
    hatdir = "/proc/device-tree/hat"
    product_file = f"{hatdir}/product"
    vendor_file = f"{hatdir}/vendor"
    if os.path.exists(product_file) and os.path.exists(vendor_file):
        with open(product_file) as f:
            p = f.read()
        with open(vendor_file) as f:
            v = f.read()
        app_logger.info(f"{product_file}: {p}")
        app_logger.info(f"{vendor_file}: {v}")
        # set display
        if p.find("Adafruit PiTFT HAT - 2.4 inch Resistive Touch") == 0:
            return "PiTFT"
        elif (p.find("PaPiRus ePaper HAT") == 0) and (v.find("Pi Supply") == 0):
            return "Papirus"
    return None


def init_display(config):
    # default dummy display

    display = Display(config)

    if not config.G_IS_RASPI:
        config.G_DISPLAY = "None"
        return display

    auto_detect = detect_display()

    if auto_detect is not None:
        config.G_DISPLAY = auto_detect

    if config.G_DISPLAY == "PiTFT":
        from .pitft_28_r import _SENSOR_DISPLAY, PiTFT28r

        if _SENSOR_DISPLAY:
            display = PiTFT28r(config)
    elif config.G_DISPLAY in ("MIP", "MIP_640"):
        from .mip_display import _SENSOR_DISPLAY, MipDisplay

        if _SENSOR_DISPLAY:
            display = MipDisplay(config, SUPPORTED_DISPLAYS[config.G_DISPLAY])
    elif config.G_DISPLAY.startswith("MIP_Sharp"):
        from .mip_sharp_display import _SENSOR_DISPLAY, MipSharpDisplay

        if _SENSOR_DISPLAY:
            display = MipSharpDisplay(config, SUPPORTED_DISPLAYS[config.G_DISPLAY])
    elif config.G_DISPLAY.startswith("MIP_Mraa"):
        from .mip_mraa_display import _SENSOR_DISPLAY, MipMraaDisplay

        if _SENSOR_DISPLAY:
            display = MipMraaDisplay(config, SUPPORTED_DISPLAYS[config.G_DISPLAY])
    elif config.G_DISPLAY == "Papirus":
        from .papirus_display import _SENSOR_DISPLAY, PapirusDisplay

        if _SENSOR_DISPLAY:
            display = PapirusDisplay(config)
    elif config.G_DISPLAY == "DFRobot_RPi_Display":
        from .dfrobot_rpi_display import _SENSOR_DISPLAY, DFRobotRPiDisplay

        if _SENSOR_DISPLAY:
            display = DFRobotRPiDisplay(config)
    elif config.G_DISPLAY.startswith("Pirate_Audio") or config.G_DISPLAY == "Display_HAT_Mini":
        from .st7789_display import _SENSOR_DISPLAY, ST7789Display

        if _SENSOR_DISPLAY:
            if config.G_DISPLAY.startswith("Pirate_Audio"):
                display = ST7789Display(config)
            elif config.G_DISPLAY == "Display_HAT_Mini":
                display = ST7789Display(config, SUPPORTED_DISPLAYS[config.G_DISPLAY])

    return display
