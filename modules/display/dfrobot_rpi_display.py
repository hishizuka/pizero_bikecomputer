from modules.app_logger import app_logger
from .display_core import Display

_SENSOR_DISPLAY = False

try:
    from DFRobot_RPi_Display.devices.dfrobot_epaper import DFRobot_Epaper_SPI
    _SENSOR_DISPLAY = True
except ImportError:
    pass

app_logger.info(f"DFRobot RPi Display: {_SENSOR_DISPLAY}")

RASPBERRY_SPI_BUS = 0
RASPBERRY_SPI_DEV = 0
RASPBERRY_PIN_CS = 27
RASPBERRY_PIN_CD = 17
RASPBERRY_PIN_BUSY = 4


# e-ink Display Module for Raspberry Pi 4B/3B+/Zero W version 1.0


class DFRobotRPiDisplay(Display):
    epaper = None

    has_color = False
    has_touch = False
    send = True

    size = (250, 122)

    def __init__(self, config):
        super().__init__(config)

        self.epaper = DFRobot_Epaper_SPI(
            RASPBERRY_SPI_BUS,
            RASPBERRY_SPI_DEV,
            RASPBERRY_PIN_CS,
            RASPBERRY_PIN_CD,
            RASPBERRY_PIN_BUSY,
        )
        self.epaper.begin()
        self.clear()

    def clear(self):
        self.epaper.clear(self.epaper.WHITE)
        self.epaper.flush(self.epaper.FULL)

    def update(self, im_array, direct_update=False):
        self.epaper.bitmap(
            0,
            0,  # start X and Y
            (~im_array).tobytes(),
            im_array.shape[1] * 8,
            im_array.shape[0],  # screen size
            65535,
            0,  # background color(white), drawing color(black)
        )
        self.epaper.flush(self.epaper.PART)

    def quit(self):
        self.clear()
