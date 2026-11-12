import asyncio
import os
from pathlib import Path

from modules.app_logger import app_logger
from .mip_backlight import MipBacklitDisplay

# Sysfs paths for sharp-drm detection.
_DRM_SPI_DRIVER_PATH = Path("/sys/bus/spi/drivers/sharp-drm")
_DRM_COLORS_PATH = "/sys/module/sharp_drm/parameters/colors"
_DRM_PANEL_TYPE_PATH = "/sys/module/sharp_drm/parameters/panel_type"
_DRM_DITHER_ALGO_PATH = "/sys/module/sharp_drm/parameters/dither_algo"
_DRM_BLUE_NOISE_PATH = "/sys/module/sharp_drm/parameters/blue_noise_2197"
_DISPLAY_CLEAR_PATH = "/sys/module/sharp_drm/parameters/display_clear"
_DISPLAY_INVERT_PATH = "/sys/module/sharp_drm/parameters/display_invert"
_QT_QPA_PLATFORM_ENV = "QT_QPA_PLATFORM"
_QML_FB_DEVICE_ENV = "PIZERO_QML_FB_DEVICE"
_FB_SYSFS_ROOT = "/sys/class/graphics"


def _read_sysfs_value(path):
    if not path:
        return None
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _write_sysfs_value(path, value):
    try:
        with open(path, "w") as f:
            f.write(f"{value}\n")
    except OSError as e:
        app_logger.warning(f"Failed to write DRM sysfs: {path}: {e}")
        return False

    return True


def detect_sharp_drm():
    driver_path = _get_fb_sysfs_path("device/driver")
    if (
        driver_path
        and os.path.exists(driver_path)
        and os.path.basename(os.path.realpath(driver_path)) == "sharp-drm"
    ):
        return True
    fb_name = get_fb_name()
    if fb_name and "sharp" in fb_name.lower():
        return True

    # DKMS can leave the module loaded even when SPI0 uses spidev.
    return any(_DRM_SPI_DRIVER_PATH.glob("spi*.*"))


def _get_fb_sysfs_path(suffix):
    fb_path = _get_linuxfb_device()
    if fb_path:
        fb_name = os.path.basename(fb_path)
        if fb_name.startswith("fb"):
            return os.path.join("/sys/class/graphics", fb_name, suffix)
    return None


def _get_linuxfb_device():
    value = os.environ.get(_QT_QPA_PLATFORM_ENV, "")
    if value:
        parts = value.split(":")
        if parts and parts[0] == "linuxfb":
            for part in parts[1:]:
                if part.startswith("fb="):
                    fb_path = part.split("=", 1)[1]
                    return fb_path if fb_path else None

    fb_path = os.environ.get(_QML_FB_DEVICE_ENV)
    if fb_path:
        return fb_path

    try:
        fb_names = sorted(os.listdir(_FB_SYSFS_ROOT))
    except OSError:
        return None
    for fb_name in fb_names:
        if not fb_name.startswith("fb"):
            continue
        name = _read_sysfs_value(os.path.join(_FB_SYSFS_ROOT, fb_name, "name"))
        if name and "sharp" in name.lower():
            return os.path.join("/dev", fb_name)
    return None


def get_fb_name():
    return _read_sysfs_value(_get_fb_sysfs_path("name"))


def get_fb_resolution():
    value = _read_sysfs_value(_get_fb_sysfs_path("virtual_size"))
    if value:
        parts = value.split(",")
        if len(parts) >= 2:
            try:
                return (int(parts[0]), int(parts[1]))
            except ValueError:
                pass

    return None


def get_sharp_drm_colors():
    value = _read_sysfs_value(_DRM_COLORS_PATH)
    if value and value.isdigit():
        return int(value)
    return None


def get_sharp_drm_panel_type():
    value = _read_sysfs_value(_DRM_PANEL_TYPE_PATH)
    if not value:
        return None
    value = value.strip().lower()
    return value or None


class MipDisplayDrm(MipBacklitDisplay):
    # Labels map to persistent mode names and the driver's algorithm/noise pair.
    DITHERING_MODES = {
        2: {
            "Off": ("off", 0, 0),
            "Ordered": ("ordered", 1, 0),
        },
        8: {
            "Off": ("off", 0, 0),
            "Ordered (27)": ("ordered", 2, 0),
            "Ordered (125)": ("ordered_high", 3, 0),
            "Error Diffusion": ("error_diffusion", 6, 0),
        },
        64: {
            "Off": ("off", 0, 0),
            "Ordered (343)": ("ordered", 4, 0),
            "Ordered (2197)": ("ordered_high", 5, 0),
            "Blue Noise (2197)": ("blue_noise", 5, 1),
            "Error Diffusion": ("error_diffusion", 6, 0),
        },
    }

    has_touch = False
    send = False

    def __init__(self, config):
        super().__init__(config)

        self.init_backlight()
        self._read_dithering_state()
        if self.dithering_modes:
            mode = config.G_DISPLAY_DITHERING[self._dithering_colors]
            if mode is not None:
                self._apply_dithering(self._dithering_colors, mode)
                self._read_dithering_state()

    def _read_dithering_state(self):
        self._dithering_colors = get_sharp_drm_colors()
        self.dithering_modes = {}
        self.dithering_mode = None
        modes = self.DITHERING_MODES.get(self._dithering_colors)
        if modes is None:
            return
        algorithm = _read_sysfs_value(_DRM_DITHER_ALGO_PATH)
        if algorithm is None:
            return
        blue_noise = "0"
        if self._dithering_colors == 64:
            blue_noise = _read_sysfs_value(_DRM_BLUE_NOISE_PATH)
            if blue_noise is None:
                return

        for label, (mode, algo, noise) in modes.items():
            self.dithering_modes[label] = mode
            if algorithm == str(algo) and (algo != 5 or blue_noise == str(noise)):
                self.dithering_mode = mode

    async def refresh_dithering(self):
        await asyncio.to_thread(self._read_dithering_state)

    def _apply_dithering(self, colors, mode):
        if colors not in self.DITHERING_MODES or get_sharp_drm_colors() != colors:
            return False
        for name, algorithm, blue_noise in self.DITHERING_MODES[colors].values():
            if name != mode:
                continue
            if colors == 64 and not _write_sysfs_value(
                _DRM_BLUE_NOISE_PATH, blue_noise
            ):
                return False
            return _write_sysfs_value(_DRM_DITHER_ALGO_PATH, algorithm)
        app_logger.warning("Invalid DRM dithering mode for %s colors: %s", colors, mode)
        return False

    async def set_dithering(self, mode):
        colors = self._dithering_colors
        applied = await asyncio.to_thread(self._apply_dithering, colors, mode)
        await self.refresh_dithering()
        if applied and self._dithering_colors == colors and self.dithering_mode == mode:
            self.config.G_DISPLAY_DITHERING[colors] = mode
            return True
        return False

    def quit(self):
        self.clear()
        super().quit()

    def screen_flash_long(self):
        super().screen_flash_long()
        self._write_display_invert("0.8,0.25")

    def screen_flash_short(self):
        super().screen_flash_short()
        self._write_display_invert("0.3,0.25")

    def clear(self):
        _write_sysfs_value(_DISPLAY_CLEAR_PATH, 1)

    def _write_display_invert(self, value):
        _write_sysfs_value(_DISPLAY_INVERT_PATH, value)
