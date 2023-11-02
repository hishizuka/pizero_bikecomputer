from logger import app_logger
from modules.utils.cmd import exec_cmd
from .display_core import Display

_SENSOR_DISPLAY = True

app_logger.info(f"PiTFT 2.8(r): {_SENSOR_DISPLAY}")


class PiTFT28r(Display):
    # PiTFT actually needs max brightness under sunlights, so there is no implementation of AUTO_BACKLIGHT
    # There's also only two states enabled or disabled
    brightness_index = 1  # we are on by default
    brightness_table = [0, 100]

    size = (320, 240)

    def quit(self):
        self.set_brightness(0)

    def set_brightness(self, b):
        if b == 0:
            exec_cmd(
                [
                    "sudo",
                    "sh",
                    "-c",
                    r"echo 0 > /sys/class/backlight/soc\:backlight/brightness",
                ]
            )
        elif b == 100:
            exec_cmd(
                [
                    "sudo",
                    "sh",
                    "-c",
                    r"echo 1 /sys/class/backlight/soc\:backlight/brightness",
                ]
            )
