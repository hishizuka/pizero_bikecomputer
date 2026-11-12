from pathlib import Path

from modules.app_logger import app_logger
from .display_core import Display


_BACKLIGHT_PATH = Path("/sys/class/backlight/backlight")


class MipBacklitDisplay(Display):
    brightness_table = [0, 1, 2, 3, 5, 7, 10, 25, 50, 100]
    _PANEL_MINIMUM_BRIGHTNESS = {
        "MIP_JDI_color_400x240": 3,
        "MIP_JDI_color_640x480": 10,
        "MIP_Azumo_color_272x451": 2,
    }

    def __init__(self, config):
        super().__init__(config)

        self.display_name = config.G_DISPLAY
        self.brightness = -1
        self._backlight_max_brightness = 0
        if config.G_DISPLAY_PARAM["USE_BACKLIGHT"]:
            try:
                max_brightness = int((_BACKLIGHT_PATH / "max_brightness").read_text())
                if max_brightness <= 0:
                    raise ValueError("max_brightness must be positive")
                # Check write permissions before exposing the backlight controls.
                for name in ("brightness", "bl_power"):
                    with (_BACKLIGHT_PATH / name).open("r+"):
                        pass
            except (OSError, ValueError) as error:
                app_logger.warning("MIP backlight unavailable: %s", error)
            else:
                self._backlight_max_brightness = max_brightness

        self.has_backlight = self._backlight_max_brightness > 0
        self.allow_auto_backlight = self.has_backlight

    def init_backlight(self):
        self.set_brightness(0)
        self.restore_backlight_state()

    def set_brightness(self, b, force=False):
        if not self.has_backlight:
            return

        try:
            brightness = max(0, min(100, int(b)))
        except (TypeError, ValueError):
            app_logger.warning("Invalid MIP backlight brightness: %r", b)
            return
        if brightness == self.brightness and not force:
            return

        power_path = _BACKLIGHT_PATH / "bl_power"
        raw_brightness = brightness * self._backlight_max_brightness // 100
        try:
            # Set the duty cycle before unblanking to avoid flashing the old level.
            if brightness == 0:
                power_path.write_text("4\n")
            (_BACKLIGHT_PATH / "brightness").write_text(f"{raw_brightness}\n")
            if brightness > 0:
                power_path.write_text("0\n")
        except OSError as error:
            app_logger.warning("Failed to set MIP backlight: %s", error)
            try:
                power_path.write_text("4\n")
            except OSError:
                pass
            self._disable_backlight()
            return

        self.brightness = brightness

    def quit(self):
        self.set_brightness(0, force=True)
        self._disable_backlight()

    def _disable_backlight(self):
        self.has_backlight = False
        self.allow_auto_backlight = False
        self.use_auto_backlight = False

    def set_minimum_brightness(self):
        self.set_brightness(self.minimum_brightness)

    @property
    def minimum_brightness(self):
        preset = self._PANEL_MINIMUM_BRIGHTNESS.get(self.display_name)
        if preset is not None:
            return preset
        if self.size == (400, 240) and self.color != 2:
            return 3
        return 10 if self.size in ((640, 480), (272, 451)) else 0
