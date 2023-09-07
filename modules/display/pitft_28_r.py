from modules.utils.cmd import exec_cmd
from logger import app_logger

_SENSOR_DISPLAY = True

app_logger.info(f"PiTFT 2.8(r): {_SENSOR_DISPLAY}")

# SCREEN
SCREEN_WIDTH = 320
SCREEN_HEIGHT = 240


class PiTFT28r:
    config = None
    spi = None

    # brightness
    brightness_index = True
    brightness_cmd = {
        0: ["sudo", "/usr/local/bin/disable-pitft"],
        1: ["sudo", "/usr/local/bin/enable-pitft"],
    }
    # brightness_table = [0,100,1000]
    # brightness_table = [0,100,400,700,1000]
    # brightness_index = len(G_Brightness)-1
    # brightness_cmd_init = ["/usr/bin/gpio", "-g", "mode", "18", "pwm"]
    # brightness_cmd_base = ["/usr/bin/gpio", "-g", "pwm", "18"]

    def __init__(self, config):
        self.config = config

        if _SENSOR_DISPLAY:
            self.clear()

    def clear(self):
        pass

    def quit(self):
        if _SENSOR_DISPLAY:
            self.clear()
            # GPIO.output(GPIO_DISP, 1)
            # time.sleep(0.1)

    def change_brightness(self):
        if _SENSOR_DISPLAY:
            self.brightness_index = not self.brightness_index
            cmd = self.brightness_cmd[int(self.brightness_index)]
            exec_cmd(cmd)
