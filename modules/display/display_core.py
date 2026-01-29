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

MIP_DISPLAY_PARAMS = {
    name: {
        "size": params[0],
        "color": params[1],
        "has_touch": False,
        "has_color": params[1] != 2,
    }
    for name, params in SUPPORTED_DISPLAYS.items()
    if name.startswith("MIP_") and params is not None
}


# default display (X window)
class Display:
    # Device capabilities; override in display subclasses.
    has_backlight = False
    # Auto backlight mode availability (device + user setting).
    allow_auto_backlight = False
    has_color = True
    has_touch = True
    send = False

    # Backlight control state (auto backlight is used by MIP displays).
    use_auto_backlight = False
    brightness_index = 0
    brightness_table = []

    def __init__(self, config):
        self.config = config

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
        status_bar = self._get_status_bar()
        if status_bar is None:
            return
        status_bar.flash_background(
            [
                (status_bar.FLASH_YELLOW, 0.5),
                (status_bar.BASE_BG_COLOR, 0.5),
                (status_bar.FLASH_YELLOW, 0.5),
            ]
        )

    def screen_flash_short(self):
        status_bar = self._get_status_bar()
        if status_bar is None:
            return
        status_bar.flash_background([(status_bar.FLASH_YELLOW, 1.0)])

    def clear(self):
        pass

    def _get_status_bar(self):
        gui = getattr(self.config, "gui", None)
        if gui is None:
            return None
        return getattr(gui, "status_bar", None)

    def change_brightness(self):
        # Cycle manual brightness levels and optionally add an auto-backlight slot.
        if not self.brightness_table:
            return

        auto_slot = 1 if self.allow_auto_backlight else 0
        self.brightness_index = (self.brightness_index + 1) % (
            len(self.brightness_table) + auto_slot
        )

        # Auto backlight is selected only when allowed and the extra slot is reached.
        if self.allow_auto_backlight and self.brightness_index == len(self.brightness_table):
            self.use_auto_backlight = True
            return

        # Otherwise apply a fixed brightness from the table.
        self.use_auto_backlight = False
        self.set_brightness(self.brightness_table[self.brightness_index])

    def set_brightness(self, b):
        pass

    def set_minimum_brightness(self):
        pass


def _init_mip_drm_display(config):
    from .mip_display_drm import MipDisplayDrm

    display = MipDisplayDrm(config)

    params = MIP_DISPLAY_PARAMS.get(config.G_DISPLAY)
    detected_name = None
    fb_info = None
    if params is None:
        fb_info = _detect_mip_drm_fb_info()
        if fb_info:
            detected_name = _select_mip_drm_display_name(
                fb_info["resolution"],
                fb_info["colors"],
                fb_info["bpp"],
                fb_info["panel_type"],
            )
            if detected_name:
                params = MIP_DISPLAY_PARAMS.get(detected_name)
            if params is None and fb_info["resolution"]:
                params = _build_mip_params_from_fb_info(fb_info)

    if params:
        display.size = params["size"]
        display.color = params["color"]
        display.has_color = params["has_color"]
        display.has_touch = params["has_touch"]
        if detected_name:
            app_logger.info(
                f"MIP DRM auto-detected: {detected_name} ({_format_fb_info(fb_info)})"
            )
        elif fb_info:
            app_logger.info(f"MIP DRM display params from fb ({_format_fb_info(fb_info)})")
    else:
        app_logger.warning(f"unknown MIP display: {config.G_DISPLAY}")

    config.G_DISPLAY_PARAM["USE_DRM"] = True
    app_logger.info("MIP DRM backend enabled (Qt direct rendering)")
    return display


def _format_fb_info(fb_info):
    if not fb_info:
        return "fb: unknown"
    parts = []
    if fb_info.get("name"):
        parts.append(f"name={fb_info['name']}")
    if fb_info.get("resolution"):
        parts.append(f"res={fb_info['resolution'][0]}x{fb_info['resolution'][1]}")
    if fb_info.get("bpp") is not None:
        parts.append(f"bpp={fb_info['bpp']}")
    if fb_info.get("colors") is not None:
        parts.append(f"colors={fb_info['colors']}")
    if fb_info.get("panel_type"):
        parts.append(f"panel_type={fb_info['panel_type']}")
    return "fb: " + ", ".join(parts) if parts else "fb: unknown"


def _detect_mip_drm_fb_info():
    from .mip_display_drm import (
        detect_sharp_drm,
        get_fb_name,
        get_fb_resolution,
        get_sharp_drm_colors,
        get_sharp_drm_panel_type,
    )

    if not detect_sharp_drm():
        return None

    return _build_mip_drm_fb_info(
        get_fb_name(),
        get_fb_resolution(),
        get_sharp_drm_colors(),
        get_sharp_drm_panel_type(),
    )


def _build_mip_drm_fb_info(fb_name, resolution, colors, panel_type):
    colors, bpp = _resolve_mip_colors_and_bpp(colors)
    return {
        "name": fb_name,
        "resolution": resolution,
        "bpp": bpp,
        "colors": colors,
        "panel_type": panel_type,
    }


def _resolve_mip_colors_and_bpp(colors):
    bpp = _map_sharp_colors_to_bpp(colors)
    if bpp is None:
        return 8, 3
    return colors, bpp


def _build_mip_params_from_fb_info(fb_info):
    return {
        "size": fb_info["resolution"],
        "color": fb_info["colors"],
        "has_color": False if fb_info["colors"] == 2 else True,
        "has_touch": False,
    }


def _select_mip_drm_display_name(resolution, colors, bpp, panel_type):
    if resolution is None:
        return None
    if panel_type == "jdi":
        if resolution == (640, 480) and colors in (2, 8):
            return "MIP_JDI_color_640x480"
        if resolution == (400, 240) and colors in (2, 8):
            return "MIP_JDI_color_400x240"
        if resolution == (272, 451) and colors in (8, 64):
            return "MIP_Azumo_color_272x451"
    if panel_type == "sharp_mono":
        if resolution == (320, 240) and colors == 2:
            return "MIP_Sharp_mono_320x240"
        if resolution == (400, 240) and colors == 2:
            return "MIP_Sharp_mono_400x240"
    return None


def _map_sharp_colors_to_bpp(colors):
    if colors is None:
        return None
    if colors < 2:
        return None
    if colors & (colors - 1) != 0:
        return None
    return colors.bit_length() - 1


def detect_display(config):
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
        elif p.find("Capacitive Touch HAT - MPR121") == 0 and v.find("Adafruit") == 0:
            # PiTFT 2.4 Capacitive Touch version
            return "PiTFT"
        elif (p.find("PaPiRus ePaper HAT") == 0) and (v.find("Pi Supply") == 0):
            return "Papirus"

    if config.G_DISPLAY.startswith("MIP_"):
        if not config.G_DISPLAY_PARAM.get("USE_DRM_FORCED", False):
            from .mip_display_drm import detect_sharp_drm

            use_drm = detect_sharp_drm()
            config.G_DISPLAY_PARAM["USE_DRM"] = use_drm
            if use_drm:
                app_logger.info("sharp-drm detected, USE_DRM enabled")
    return None


def init_display(config):
    # default dummy display
    display = Display(config)

    if not config.G_IS_RASPI:
        config.G_DISPLAY = "None"
        return display

    auto_detect = detect_display(config)

    if auto_detect is not None:
        config.G_DISPLAY = auto_detect

    if config.G_DISPLAY == "PiTFT":
        from .pitft_28_r import _SENSOR_DISPLAY, PiTFT28r

        if _SENSOR_DISPLAY:
            display = PiTFT28r(config)
    elif config.G_DISPLAY.startswith("MIP_"):
        if bool(config.G_DISPLAY_PARAM.get("USE_DRM", False)):
            display = _init_mip_drm_display(config)
        else:
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
    elif config.G_DISPLAY == "None" and bool(config.G_DISPLAY_PARAM.get("USE_DRM", False)):
        from .mip_display_drm import detect_sharp_drm

        if detect_sharp_drm():
            display = _init_mip_drm_display(config)
    return display
