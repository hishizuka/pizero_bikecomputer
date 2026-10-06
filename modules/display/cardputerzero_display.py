import os
from pathlib import Path

from modules.app_logger import app_logger

from .display_core import Display


class CardputerZeroDisplay(Display):
    """Use the kernel LCD framebuffer and M5IOE1 backlight."""

    size = (320, 170)
    color = 65536
    brightness = 75
    brightness_table = [0, 10, 25, 50, 75, 100]
    backlight_path = Path("/sys/class/backlight/backlight")

    def __init__(self, config):
        super().__init__(config)
        config.G_DISPLAY_PARAM["USE_DRM"] = False
        self.backlight_max_brightness = 0
        if config.G_DISPLAY_PARAM["USE_BACKLIGHT"]:
            try:
                self.backlight_max_brightness = int(
                    (self.backlight_path / "max_brightness").read_text().strip()
                )
            except (OSError, ValueError):
                pass
            self.has_backlight = self.backlight_max_brightness > 0 and os.access(
                self.backlight_path / "brightness", os.W_OK
            )
            if not self.has_backlight:
                app_logger.warning("CardputerZero backlight is unavailable")
        self.restore_backlight_state()

    def set_brightness(self, brightness):
        if not self.has_backlight:
            return
        brightness = max(0, min(100, brightness))
        value = round(brightness * self.backlight_max_brightness / 100)
        try:
            (self.backlight_path / "brightness").write_text(f"{value}\n")
        except OSError as error:
            app_logger.warning("Failed to set CardputerZero backlight: %s", error)
            return
        self.brightness = brightness

    def set_minimum_brightness(self):
        self.set_brightness(self.brightness_table[1])

    def quit(self):
        self.set_brightness(0)
