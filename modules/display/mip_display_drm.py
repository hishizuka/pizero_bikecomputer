import os

from modules.app_logger import app_logger
from .display_core import Display

# Sysfs paths for sharp-drm detection.
_DRM_MODULE_PATH = "/sys/module/sharp_drm"
_DRM_COLORS_PATH = "/sys/module/sharp_drm/parameters/colors"
_DRM_PANEL_TYPE_PATH = "/sys/module/sharp_drm/parameters/panel_type"
_DISPLAY_CLEAR_PATH = "/sys/module/sharp_drm/parameters/display_clear"
_DISPLAY_INVERT_PATH = "/sys/module/sharp_drm/parameters/display_invert"
_DRM_BACKLIGHT_PATH = "/sys/class/backlight/backlight"
_DRM_BACKLIGHT_BRIGHTNESS_PATH = os.path.join(_DRM_BACKLIGHT_PATH, "brightness")
_DRM_BACKLIGHT_MAX_BRIGHTNESS_PATH = os.path.join(_DRM_BACKLIGHT_PATH, "max_brightness")
_DRM_BACKLIGHT_POWER_PATH = os.path.join(_DRM_BACKLIGHT_PATH, "bl_power")
_QT_QPA_PLATFORM_ENV = "QT_QPA_PLATFORM"


def _read_sysfs_value(path):
    if not path:
        return None
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _write_sysfs_value(path, value, log_failure=True):
    if not os.path.exists(path):
        if log_failure:
            app_logger.warning(f"DRM sysfs not found: {path}")
        return False

    try:
        with open(path, "w") as f:
            f.write(f"{value}\n")
    except OSError as e:
        if log_failure:
            app_logger.warning(f"Failed to write DRM sysfs: {path}: {e}")
        return False

    return True


def _write_backlight_brightness(value, log_failure=True):
    return _write_sysfs_value(
        _DRM_BACKLIGHT_BRIGHTNESS_PATH,
        value,
        log_failure=log_failure,
    )


def _write_backlight_power(value, log_failure=True):
    return _write_sysfs_value(
        _DRM_BACKLIGHT_POWER_PATH,
        value,
        log_failure=log_failure,
    )


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
    brightness_table = [0, 1, 2, 3, 5, 7, 10, 25, 50, 100]
    brightness = 0
    minimum_brightness = 0

    def __init__(self, config):
        super().__init__(config)

        self.display_name = config.G_DISPLAY
        self.backlight_max_brightness = 0
        self.has_backlight = (
            bool(config.G_DISPLAY_PARAM["USE_BACKLIGHT"])
            and self._has_backlight_sysfs()
        )
        if config.G_DISPLAY_PARAM["USE_BACKLIGHT"] and not self.has_backlight:
            app_logger.warning(
                "DRM backlight is unavailable or not writable; disabling it: "
                f"{_DRM_BACKLIGHT_PATH}"
            )

        self.allow_auto_backlight = self.has_backlight
        self.use_auto_backlight = False
        self.brightness_index = 0
        self.brightness = -1
        self.init_minimum_brightness()
        self.set_brightness(0)
        self.restore_backlight_state()

    def quit(self):
        self.clear()
        self.set_brightness(0, force=True)

    def screen_flash_long(self):
        super().screen_flash_long()
        self._write_display_invert("0.8,0.25")

    def screen_flash_short(self):
        super().screen_flash_short()
        self._write_display_invert("0.3,0.25")

    def clear(self):
        _write_sysfs_value(_DISPLAY_CLEAR_PATH, 1)

    def set_brightness(self, b, force=False):
        if not self.has_backlight:
            return

        try:
            brightness = int(b)
        except (TypeError, ValueError):
            app_logger.warning(f"Invalid DRM backlight brightness: {b}")
            return

        brightness = max(0, min(100, brightness))
        if brightness == self.brightness and not force:
            return

        if brightness == 0:
            power_written = _write_backlight_power(4)
            brightness_written = _write_backlight_brightness(0)
            if not power_written or not brightness_written:
                self._disable_backlight()
                return
            self.brightness = brightness
            return

        raw_brightness = int(brightness * self.backlight_max_brightness / 100)
        if not _write_backlight_power(0):
            self._disable_backlight()
            return
        if not _write_backlight_brightness(raw_brightness):
            _write_backlight_power(4)
            self._disable_backlight()
            return

        self.brightness = brightness

    def set_minimum_brightness(self):
        self.set_brightness(self.minimum_brightness)

    def _has_backlight_sysfs(self):
        max_brightness = _read_sysfs_value(_DRM_BACKLIGHT_MAX_BRIGHTNESS_PATH)
        try:
            max_brightness = int(max_brightness)
        except (TypeError, ValueError):
            return False
        if max_brightness <= 0:
            return False

        for path, write_value in (
            (_DRM_BACKLIGHT_BRIGHTNESS_PATH, _write_backlight_brightness),
            (_DRM_BACKLIGHT_POWER_PATH, _write_backlight_power),
        ):
            value = _read_sysfs_value(path)
            if value is None or not write_value(value, log_failure=False):
                return False
        self.backlight_max_brightness = max_brightness
        return True

    def _disable_backlight(self):
        self.has_backlight = False
        self.allow_auto_backlight = False
        self.use_auto_backlight = False

    def init_minimum_brightness(self):
        self.minimum_brightness = self._get_minimum_brightness()

    def _get_minimum_brightness(self):
        if self.display_name == "MIP_JDI_color_400x240":
            return 3
        if self.display_name == "MIP_JDI_color_640x480":
            return 10
        if self.display_name == "MIP_Azumo_color_272x451":
            return 2
        if self.size == (400, 240) and self.color != 2:
            return 3
        if self.size in ((640, 480), (272, 451)):
            return 10
        return 0

    def _write_display_invert(self, value):
        _write_sysfs_value(_DISPLAY_INVERT_PATH, value)
