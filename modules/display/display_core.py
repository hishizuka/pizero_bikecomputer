import os

from modules.app_logger import app_logger

DEFAULT_RESOLUTION = (400, 240) #(272, 451) #(400, 240)
DEFAULT_COLOR = 8

SUPPORTED_DISPLAYS = {
    # display name, resolution, colors if different from its class default
    "None": None,  # DEFAULT_RESOLUTION

    # MIP Reflective color/mono LCD
    "MIP_JDI_color_400x240": (DEFAULT_RESOLUTION, 8),  # JDI LPM027M128C/LPM027M128B
    "MIP_JDI_color_640x480": ((640, 480), 8), # JDI LPM044M141A
    #"MIP_JDI_color_640x480": ((640, 480), 2), # JDI LPM044M141A
    "MIP_Azumo_color_272x451": ((272, 451), 64), # Azumo 14793-06
    #"MIP_Azumo_color_272x451": ((272, 451), 8), # Azumo 14793-06
    "MIP_Sharp_mono_400x240": (DEFAULT_RESOLUTION, 2), # Sharp LS027B7DH01
    "MIP_Sharp_mono_320x240": ((320, 240), 2), # Sharp LS044Q7DH01

    # e-paper
    "Papirus": None,
    "DFRobot_RPi_Display": None,

    # TFT (obsolete)
    "PiTFT": None,
    "Pirate_Audio": None,
    "Pirate_Audio_old": None,
    "Display_HAT_Mini": (320, 240),
    "ST7789_Breakout": None,
}


# default display (X window)
class Display:
    has_backlight = False
    has_color = True
    has_touch = True
    send = False

    # current auto brightness status (on/off)
    use_auto_backlight = False
    brightness_index = 0
    brightness_table = []

    def __init__(self, config):
        self.config = config

        self.has_backlight = config.G_DISPLAY_PARAM["USE_BACKLIGHT"]
        if self.has_backlight:
            # set initial status
            self.use_auto_backlight = config.G_USE_AUTO_BACKLIGHT

            # set index properly if on
            if self.use_auto_backlight:
                self.brightness_index = len(self.brightness_table)

    @property
    def resolution(self):
        return getattr(self, "size", DEFAULT_RESOLUTION)

    @property
    def colors(self):
        return getattr(self, "color", DEFAULT_COLOR)

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
            # brightness is changing as following if the display has use_auto_backlight feature
            if self.has_backlight:
                self.brightness_index = (self.brightness_index + 1) % (
                    len(self.brightness_table) + 1
                )

                # switch on use_auto_backlight
                if self.brightness_index == len(self.brightness_table):
                    self.use_auto_backlight = True
                # switch off use_auto_backlight and set requested brightness
                else:
                    self.use_auto_backlight = False
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
    elif config.G_DISPLAY.startswith("MIP_"):
        # stop importing when a valid import is found
        from .mip_display_pigpio import _SENSOR_DISPLAY as _SENSOR_DISPLAY_PIGPIO, MipDisplayPigpio
        if _SENSOR_DISPLAY_PIGPIO:
            display = MipDisplayPigpio(config, *SUPPORTED_DISPLAYS[config.G_DISPLAY])
        else:
            from .mip_display_spidev import _SENSOR_DISPLAY as _SENSOR_DISPLAY_SPIDEV, MipDisplaySpidev
            if _SENSOR_DISPLAY_SPIDEV:
                display = MipDisplaySpidev(config, *SUPPORTED_DISPLAYS[config.G_DISPLAY])
    elif config.G_DISPLAY == "Papirus":
        from .papirus_display import _SENSOR_DISPLAY, PapirusDisplay

        if _SENSOR_DISPLAY:
            display = PapirusDisplay(config)
    elif config.G_DISPLAY == "DFRobot_RPi_Display":
        from .dfrobot_rpi_display import _SENSOR_DISPLAY, DFRobotRPiDisplay

        if _SENSOR_DISPLAY:
            display = DFRobotRPiDisplay(config)
    elif config.G_DISPLAY.startswith(("Pirate_Audio", "Display_HAT_Mini")):
        from .st7789_display import _SENSOR_DISPLAY, ST7789Display

        if _SENSOR_DISPLAY:
            if config.G_DISPLAY.startswith("Pirate_Audio"):
                display = ST7789Display(config)
            elif config.G_DISPLAY == "Display_HAT_Mini":
                display = ST7789Display(config, SUPPORTED_DISPLAYS[config.G_DISPLAY])
    elif config.G_DISPLAY == "ST7789_Breakout":
        from .st7789_breakout_display import _SENSOR_DISPLAY, ST7789BreakoutDisplay
        
        if _SENSOR_DISPLAY:
            display = ST7789BreakoutDisplay(config, SUPPORTED_DISPLAYS[config.G_DISPLAY])
    return display
