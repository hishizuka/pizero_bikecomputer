from modules.app_logger import app_logger
from modules.utils.cmd import exec_cmd
from .display_core import Display

_SENSOR_DISPLAY = True

app_logger.info(f"PiTFT 2.8(r): {_SENSOR_DISPLAY}")


class PiTFT28r(Display):
    brightness_table = [0, 10, 100]
    brightness = 100
    brightness_index = len(brightness_table) - 1
    minimum_brightness = 10

    has_backlight = True
    allow_auto_backlight = False
    use_auto_backlight = False

    _BACKLIGHT_PATH = "/sys/class/backlight/backlight/brightness"

    size = (320, 240)

    def __init__(self, config):
        super().__init__(config)

        self.brightness_index = len(self.brightness_table) - 1
        self.brightness = -1
        self.set_brightness(self.brightness_table[self.brightness_index])

    def quit(self):
        self.set_brightness(0)

    def set_brightness(self, b):
        if b == self.brightness:
            return

        value = int(max(0, min(100, b)) * 255 / 100)
        exec_cmd(
            [
                "sudo",
                "sh",
                "-c",
                f"echo {value} > {self._BACKLIGHT_PATH}",
            ],
            cmd_print=False
        )
        self.brightness = b
