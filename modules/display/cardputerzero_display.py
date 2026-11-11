from typing import cast

from modules.sensor.bridge.bridge_cardputerzero import CardputerZeroBridge

from .display_core import Display


class CardputerZeroDisplay(Display):
    """Use the kernel LCD framebuffer and M5IOE1 backlight."""

    size = (320, 170)
    color = 65536
    brightness = 75
    brightness_table = [0, 10, 25, 50, 75, 100]

    def __init__(self, config):
        super().__init__(config)
        config.G_DISPLAY_PARAM["USE_DRM"] = False
        self.bridge = cast(CardputerZeroBridge, config.bridge)
        self.has_backlight = self.bridge.has_backlight
        self.restore_backlight_state()

    def set_brightness(self, brightness):
        if not self.has_backlight:
            return
        brightness = max(0, min(100, brightness))
        if self.bridge.set_backlight(brightness):
            self.brightness = brightness

    def set_minimum_brightness(self):
        self.set_brightness(self.brightness_table[1])

    def quit(self):
        self.set_brightness(0)
