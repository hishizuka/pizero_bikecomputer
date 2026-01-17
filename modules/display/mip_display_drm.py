import os

from modules.app_logger import app_logger
from modules.utils.cmd import exec_cmd
from .display_core import Display

# Sysfs paths for sharp-drm detection.
_DRM_MODULE_PATH = "/sys/module/sharp_drm"
_DRM_COLORS_PATH = "/sys/module/sharp_drm/parameters/colors"
_DRM_PANEL_TYPE_PATH = "/sys/module/sharp_drm/parameters/panel_type"
_DISPLAY_CLEAR_PATH = "/sys/module/sharp_drm/parameters/display_clear"
_DISPLAY_INVERT_PATH = "/sys/module/sharp_drm/parameters/display_invert"
_QT_QPA_PLATFORM_ENV = "QT_QPA_PLATFORM"


def _read_sysfs_value(path):
    if not path:
        return None
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def detect_sharp_drm():
    driver_path = _get_fb_sysfs_path("device/driver")
    if driver_path and os.path.exists(driver_path):
        try:
            driver_name = os.path.basename(os.path.realpath(driver_path))
            if driver_name == "sharp-drm":
                return True
        except OSError:
            pass

    fb_name_path = _get_fb_sysfs_path("name")
    if fb_name_path and os.path.exists(fb_name_path):
        try:
            with open(fb_name_path) as f:
                if "sharp" in f.read().strip().lower():
                    return True
        except OSError:
            pass

    if os.path.exists(_DRM_MODULE_PATH):
        return True

    return False


def _get_fb_sysfs_path(suffix):
    fb_path = _get_linuxfb_device()
    if fb_path:
        fb_name = os.path.basename(fb_path)
        if fb_name.startswith("fb"):
            return os.path.join("/sys/class/graphics", fb_name, suffix)
    return None


def _get_linuxfb_device():
    value = os.environ.get(_QT_QPA_PLATFORM_ENV, "")
    if not value:
        return None
    parts = value.split(":")
    if not parts or parts[0] != "linuxfb":
        return None
    for part in parts[1:]:
        if part.startswith("fb="):
            fb_path = part.split("=", 1)[1]
            return fb_path if fb_path else None
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


class MipDisplayDrm(Display):
    has_touch = False
    send = False

    def screen_flash_long(self):
        self._write_display_invert("0.8,0.25", "screen_flash_long")

    def screen_flash_short(self):
        self._write_display_invert("0.3,0.25", "screen_flash_short")

    def clear(self):
        if not os.path.exists(_DISPLAY_CLEAR_PATH):
            app_logger.warning(f"DRM sysfs not found: {_DISPLAY_CLEAR_PATH} (clear)")
            return
        exec_cmd(["/bin/sh", "-c", f"echo 1 > {_DISPLAY_CLEAR_PATH}"], cmd_print=False)

    def _write_display_invert(self, value, action_name):
        if not os.path.exists(_DISPLAY_INVERT_PATH):
            app_logger.warning(f"DRM sysfs not found: {_DISPLAY_INVERT_PATH} ({action_name})")
            return
        exec_cmd(["/bin/sh", "-c", f"echo {value} > {_DISPLAY_INVERT_PATH}"], cmd_print=False)
